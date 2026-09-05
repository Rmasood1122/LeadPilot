"""M9 — native CRM API: dashboard aggregates, data grid, notes, tags,
saved views, custom fields, and the SSE real-time stream.

CONVENTIONS THIS ROUTER FOLLOWS (none of them invented here)

  auth        `Depends(get_current_user)` from app/api/deps.py on every route
              except the SSE stream, which authenticates by ticket -- see
              `crm_stream` for why it cannot use the header.
  ownership   app/services/crm_service.py::owned_lead / owned_strategy, the
              same lead -> strategy -> product -> user_id chain
              app/api/leads.py walks. Always 404, never 403, so a probe
              cannot distinguish "not yours" from "does not exist".
  rate limit  `enforce_rate_limit(...)` as the handler's FIRST statement, not
              a route dependency. app/core/rate_limiting.py documents why at
              length: as a dependency it runs before FastAPI validates the
              body, so a typo'd payload burns a slot having created nothing.
              tests/test_rate_limit_ordering.py pins that ordering.
"""

# NOTE: deliberately NO `from __future__ import annotations` here, matching
# every other router in this package. With postponed evaluation, FastAPI's
# get_typed_return_annotation resolves a `-> None` return annotation to the
# NoneType *class*, which is truthy, so it becomes a response model -- and
# every 204 route in this file then fails at import with "Status code 204 must
# not have a response body". Without it, Python stores a literal `None`, which
# is falsy, and FastAPI correctly reads it as "no response model".

import asyncio
import json
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.logging import get_logger
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import (
    CrmActivityKind,
    CrmCustomField,
    CrmCustomFieldValue,
    CrmFieldType,
    CrmLeadTag,
    CrmNote,
    CrmSavedView,
    CrmTag,
    CrmViewType,
    Lead,
    LeadStatus,
    User,
)
from app.services import crm_events, crm_service

logger = get_logger("api.crm")

router = APIRouter(prefix="/crm", tags=["crm"])

_WRITE_LIMIT = "RATE_LIMIT_CRM_WRITE"

# The status transition map is NOT redefined here. app/api/ui_support.py owns
# it, the kanban already validates against it, and a second copy would be a
# second thing to update -- and the moment the two disagree, the same drag is
# legal on one screen and rejected on the other.
from app.api.ui_support import _ALLOWED_TRANSITIONS  # noqa: E402


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=10_000)


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    # A theme token name, never a hex value: the app recolors from CSS
    # variables and a stored hex would be the one element ignoring the preset.
    color_token: str = Field(default="muted", max_length=20)


class LeadPatchIn(BaseModel):
    """Inline edit from the grid. Every field optional; only what is sent is
    written, so the grid can PATCH a single cell without reading the row
    first and racing another editor's change to a different column."""

    status: LeadStatus | None = None
    owner_user_id: uuid.UUID | None = None
    priority: str | None = Field(default=None, max_length=20)
    next_action_at: datetime | None = None
    custom: dict | None = None


class BulkPatchIn(BaseModel):
    lead_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    status: LeadStatus | None = None
    add_tag_ids: list[uuid.UUID] | None = None
    remove_tag_ids: list[uuid.UUID] | None = None


class SavedViewIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    view_type: CrmViewType = CrmViewType.GRID
    filters_json: dict = Field(default_factory=dict)
    sort_json: list = Field(default_factory=list)
    columns_json: list = Field(default_factory=list)
    is_default: bool = False


class CustomFieldIn(BaseModel):
    key: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=100)
    field_type: CrmFieldType = CrmFieldType.TEXT
    options_json: list | None = None
    sort_order: int = 0


class GridQueryIn(BaseModel):
    """POSTed rather than sent as a query string.

    A saved view's filter set is a nested structure ({"company": {"op":
    "contains", "value": "..."}}), and encoding that into query parameters
    means inventing a serialisation, hitting URL length limits on a wide
    filter set, and writing filter values into every access log. POST with a
    JSON body avoids all three. It is a read, so it is idempotent and
    deliberately not rate-limited as a write.
    """

    strategy_id: uuid.UUID | None = None
    filters: dict = Field(default_factory=dict)
    sort: list[dict] = Field(default_factory=list)
    search: str | None = Field(default=None, max_length=200)
    tag_ids: list[uuid.UUID] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=crm_service.MAX_GRID_LIMIT)
    offset: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Dashboard (4 pages)
# ---------------------------------------------------------------------------


@router.get("/dashboard/pipeline")
def dashboard_pipeline(
    strategy_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Page 1 — funnel, stage conversion, bookings this week/month, trend."""
    if strategy_id is not None:
        crm_service.owned_strategy(db, strategy_id, current_user)
    return crm_service.dashboard_pipeline(db, current_user, strategy_id)


@router.get("/dashboard/leads")
def dashboard_leads(
    strategy_id: uuid.UUID | None = None,
    stuck_after_days: int = Query(default=7, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Page 2 — velocity, source mix, verification quality, stuck leads."""
    if strategy_id is not None:
        crm_service.owned_strategy(db, strategy_id, current_user)
    return crm_service.dashboard_leads(db, current_user, strategy_id,
                                       stuck_after_days)


@router.get("/dashboard/campaigns")
def dashboard_campaigns(
    strategy_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Page 3 — per-sequence/channel rates, A/B variants, bounce vs threshold."""
    if strategy_id is not None:
        crm_service.owned_strategy(db, strategy_id, current_user)
    return crm_service.dashboard_campaigns(db, current_user, strategy_id)


@router.get("/dashboard/activity")
def dashboard_activity(
    strategy_id: uuid.UUID | None = None,
    lead_id: uuid.UUID | None = None,
    kind: list[str] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    # An OPAQUE cursor from a previous response's `next_before`, not a bare
    # timestamp: activity timestamps tie routinely, so the cursor has to carry
    # the whole sort key. See crm_service.dashboard_activity.
    before: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Page 4 — the account-wide activity feed."""
    if strategy_id is not None:
        crm_service.owned_strategy(db, strategy_id, current_user)
    return crm_service.dashboard_activity(
        db, current_user, strategy_id=strategy_id, lead_id=lead_id,
        kinds=kind, limit=limit, before=before,
    )


# ---------------------------------------------------------------------------
# Grid
# ---------------------------------------------------------------------------


@router.post("/grid")
def crm_grid(
    body: GridQueryIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if body.strategy_id is not None:
        crm_service.owned_strategy(db, body.strategy_id, current_user)
    return crm_service.grid_page(
        db, current_user,
        strategy_id=body.strategy_id, filters=body.filters, sort=body.sort,
        search=body.search, tag_ids=body.tag_ids,
        limit=body.limit, offset=body.offset,
    )


@router.patch("/leads/{lead_id}")
def patch_lead(
    lead_id: uuid.UUID,
    body: LeadPatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Inline cell edit.

    Sits ALONGSIDE app/api/ui_support.py's PATCH /leads/{id} rather than
    replacing it: the kanban's contract is `{status}` in, `{id, status}` out,
    and widening that response would change a shape the pipeline page and the
    mobile app already consume. Status changes here run through the same
    _ALLOWED_TRANSITIONS map, so the two endpoints cannot diverge on what a
    legal move is.
    """
    enforce_rate_limit(str(current_user.id), "crm_write", _WRITE_LIMIT)

    lead = crm_service.owned_lead(db, lead_id, current_user)
    changed: list[str] = []

    if body.status is not None and body.status is not lead.status:
        if body.status not in _ALLOWED_TRANSITIONS.get(lead.status, set()):
            raise HTTPException(
                status_code=422,
                detail=(f"cannot move a lead from {lead.status.value} to "
                        f"{body.status.value}"),
            )
        previous = lead.status.value
        lead.status = body.status
        crm_service.log_activity(
            db, lead, CrmActivityKind.STATUS_CHANGED, actor=current_user,
            from_value=previous, to_value=body.status.value,
        )
        # The moment the CURRENT stage was entered -- the measurement the
        # velocity dashboard needs and that nothing before M9 recorded.
        meta = crm_service.get_or_create_meta(db, lead)
        meta.stage_entered_at = datetime.now(timezone.utc)
        changed.append("status")

    if "owner_user_id" in body.model_fields_set:
        meta = crm_service.get_or_create_meta(db, lead)
        previous_owner = meta.owner_user_id
        # Only the account holder can own their own leads. Team accounts are
        # not built (SYSTEM_HANDOFF: "Multi-tenant team accounts" is not
        # built), so accepting an arbitrary user id here would let one account
        # write another account's id into its own rows -- harmless today,
        # and exactly the kind of thing that becomes a real leak the day
        # sharing ships.
        if body.owner_user_id is not None and body.owner_user_id != current_user.id:
            raise HTTPException(
                status_code=422,
                detail="owner_user_id must be the authenticated user "
                       "(team accounts are not supported yet)",
            )
        meta.owner_user_id = body.owner_user_id
        crm_service.log_activity(
            db, lead, CrmActivityKind.OWNER_CHANGED, actor=current_user,
            from_value=str(previous_owner) if previous_owner else None,
            to_value=str(body.owner_user_id) if body.owner_user_id else None,
        )
        changed.append("owner_user_id")

    if "priority" in body.model_fields_set:
        meta = crm_service.get_or_create_meta(db, lead)
        previous_priority = meta.priority
        meta.priority = body.priority
        crm_service.log_activity(
            db, lead, CrmActivityKind.FIELD_CHANGED, actor=current_user,
            from_value=previous_priority, to_value=body.priority,
            meta={"field": "priority"},
        )
        changed.append("priority")

    if "next_action_at" in body.model_fields_set:
        meta = crm_service.get_or_create_meta(db, lead)
        meta.next_action_at = body.next_action_at
        changed.append("next_action_at")

    if body.custom:
        fields = {
            field.key: field
            for field in db.execute(
                select(CrmCustomField)
                .where(CrmCustomField.user_id == current_user.id)
            ).scalars().all()
        }
        for key, raw in body.custom.items():
            field = fields.get(key)
            if field is None:
                raise HTTPException(status_code=422,
                                    detail=f"unknown custom field '{key}'")
            value_text, value_json = crm_service.coerce_field_value(field, raw)
            row = db.execute(
                select(CrmCustomFieldValue).where(
                    CrmCustomFieldValue.field_id == field.id,
                    CrmCustomFieldValue.lead_id == lead.id,
                )
            ).scalars().first()
            previous = (crm_service.decode_field_value(row)
                        if row is not None else None)
            if row is None:
                row = CrmCustomFieldValue(field_id=field.id, lead_id=lead.id)
                db.add(row)
            row.value_text = value_text
            row.value_json = value_json
            crm_service.log_activity(
                db, lead, CrmActivityKind.FIELD_CHANGED, actor=current_user,
                from_value=str(previous) if previous is not None else None,
                to_value=str(raw) if raw is not None else None,
                meta={"field": key},
            )
            changed.append(f"custom.{key}")

    db.commit()
    db.refresh(lead)
    return {"id": str(lead.id), "status": lead.status.value, "changed": changed}


@router.post("/leads/bulk")
def bulk_patch_leads(
    body: BulkPatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Bulk status change and bulk tag add/remove from the grid's selection.

    PARTIAL SUCCESS IS THE CONTRACT, deliberately. Selecting 200 rows and
    moving them all to `contacted` will legitimately include some rows whose
    current status makes that transition illegal. Failing the whole batch on
    the first one means the user has to find and deselect it by hand with no
    indication of which it was. So legal moves are applied, illegal ones are
    reported per-lead in `skipped`, and the response says how many of each.
    """
    enforce_rate_limit(str(current_user.id), "crm_write", _WRITE_LIMIT)

    updated: list[str] = []
    skipped: list[dict] = []

    # Resolve every lead first: an id belonging to another account must 404
    # the whole request rather than being quietly skipped, because a silent
    # skip is indistinguishable from "that lead had nothing to change" and
    # would make cross-tenant probing free.
    leads = [crm_service.owned_lead(db, lead_id, current_user)
             for lead_id in body.lead_ids]

    owned_tag_ids: set[uuid.UUID] = set()
    requested_tags = list(body.add_tag_ids or []) + list(body.remove_tag_ids or [])
    if requested_tags:
        owned_tag_ids = set(db.execute(
            select(CrmTag.id).where(CrmTag.id.in_(requested_tags),
                                    CrmTag.user_id == current_user.id)
        ).scalars().all())
        missing = set(requested_tags) - owned_tag_ids
        if missing:
            raise HTTPException(status_code=404, detail="tag not found")

    for lead in leads:
        if body.status is not None and body.status is not lead.status:
            if body.status not in _ALLOWED_TRANSITIONS.get(lead.status, set()):
                skipped.append({
                    "lead_id": str(lead.id),
                    "reason": (f"cannot move from {lead.status.value} to "
                               f"{body.status.value}"),
                })
                continue
            previous = lead.status.value
            lead.status = body.status
            crm_service.log_activity(
                db, lead, CrmActivityKind.STATUS_CHANGED, actor=current_user,
                from_value=previous, to_value=body.status.value,
                meta={"bulk": True},
            )
            meta = crm_service.get_or_create_meta(db, lead)
            meta.stage_entered_at = datetime.now(timezone.utc)

        for tag_id in body.add_tag_ids or []:
            exists = db.execute(
                select(CrmLeadTag.id).where(CrmLeadTag.lead_id == lead.id,
                                            CrmLeadTag.tag_id == tag_id)
            ).scalars().first()
            if exists is None:
                db.add(CrmLeadTag(lead_id=lead.id, tag_id=tag_id))
                crm_service.log_activity(
                    db, lead, CrmActivityKind.TAG_ADDED, actor=current_user,
                    to_value=str(tag_id), meta={"bulk": True},
                )

        for tag_id in body.remove_tag_ids or []:
            row = db.execute(
                select(CrmLeadTag).where(CrmLeadTag.lead_id == lead.id,
                                         CrmLeadTag.tag_id == tag_id)
            ).scalars().first()
            if row is not None:
                db.delete(row)
                crm_service.log_activity(
                    db, lead, CrmActivityKind.TAG_REMOVED, actor=current_user,
                    from_value=str(tag_id), meta={"bulk": True},
                )

        updated.append(str(lead.id))

    db.commit()
    return {"updated": updated, "updated_count": len(updated),
            "skipped": skipped, "skipped_count": len(skipped)}


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


@router.get("/leads/{lead_id}/notes")
def list_notes(
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    crm_service.owned_lead(db, lead_id, current_user)
    rows = db.execute(
        select(CrmNote).where(CrmNote.lead_id == lead_id)
        .order_by(CrmNote.created_at.desc())
    ).scalars().all()
    return {"items": [
        {
            "id": str(note.id),
            "lead_id": str(note.lead_id),
            "body": note.body,
            "author_user_id": (str(note.author_user_id)
                               if note.author_user_id else None),
            "created_at": note.created_at.isoformat() if note.created_at else None,
            "updated_at": note.updated_at.isoformat() if note.updated_at else None,
        }
        for note in rows
    ]}


@router.post("/leads/{lead_id}/notes", status_code=201)
def create_note(
    lead_id: uuid.UUID,
    body: NoteIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    enforce_rate_limit(str(current_user.id), "crm_write", _WRITE_LIMIT)

    lead = crm_service.owned_lead(db, lead_id, current_user)
    note = CrmNote(lead_id=lead.id, author_user_id=current_user.id,
                   body=body.body)
    db.add(note)
    db.flush()
    crm_service.log_activity(
        db, lead, CrmActivityKind.NOTE_ADDED, actor=current_user,
        # The note's first line, not its body: the feed is a timeline, and a
        # 10,000-character note pasted into it makes every other entry
        # unreadable. The full text is one click away on the lead.
        to_value=body.body.splitlines()[0][:200] if body.body else None,
        meta={"note_id": str(note.id)},
    )
    db.commit()
    db.refresh(note)
    return {"id": str(note.id), "lead_id": str(note.lead_id),
            "body": note.body,
            "author_user_id": str(note.author_user_id),
            "created_at": note.created_at.isoformat() if note.created_at else None}


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(
    note_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    enforce_rate_limit(str(current_user.id), "crm_write", _WRITE_LIMIT)

    note = db.get(CrmNote, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="note not found")
    # Ownership is the LEAD's, not the note author's: the note hangs off a
    # lead, and reaching it requires owning that lead.
    lead = crm_service.owned_lead(db, note.lead_id, current_user)
    crm_service.log_activity(
        db, lead, CrmActivityKind.NOTE_DELETED, actor=current_user,
        from_value=note.body.splitlines()[0][:200] if note.body else None,
    )
    db.delete(note)
    db.commit()


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


@router.get("/tags")
def list_tags(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    rows = db.execute(
        select(CrmTag).where(CrmTag.user_id == current_user.id)
        .order_by(CrmTag.name)
    ).scalars().all()
    return {"items": [
        {"id": str(tag.id), "name": tag.name, "color_token": tag.color_token}
        for tag in rows
    ]}


@router.post("/tags", status_code=201)
def create_tag(
    body: TagIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    enforce_rate_limit(str(current_user.id), "crm_write", _WRITE_LIMIT)

    existing = db.execute(
        select(CrmTag).where(CrmTag.user_id == current_user.id,
                             CrmTag.name == body.name)
    ).scalars().first()
    if existing is not None:
        # Idempotent rather than 409. The grid creates a tag by typing its
        # name; typing one that already exists means "use that one", not
        # "show me an error".
        return {"id": str(existing.id), "name": existing.name,
                "color_token": existing.color_token, "created": False}
    tag = CrmTag(user_id=current_user.id, name=body.name,
                 color_token=body.color_token)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return {"id": str(tag.id), "name": tag.name,
            "color_token": tag.color_token, "created": True}


@router.delete("/tags/{tag_id}", status_code=204)
def delete_tag(
    tag_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    enforce_rate_limit(str(current_user.id), "crm_write", _WRITE_LIMIT)

    tag = db.get(CrmTag, tag_id)
    if tag is None or tag.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="tag not found")
    # Detach explicitly rather than leaning on ON DELETE CASCADE.
    #
    # The FK does declare the cascade, and PostgreSQL honours it -- but SQLite
    # does not enforce foreign keys unless PRAGMA foreign_keys=ON, and the test
    # suite runs on SQLite with it off. So the cascade path is exercised
    # nowhere except production, which is the worst place to find out it was
    # wrong. Deleting the associations here makes the behaviour identical on
    # both dialects and leaves the FK cascade as a backstop rather than the
    # mechanism.
    db.execute(delete(CrmLeadTag).where(CrmLeadTag.tag_id == tag.id))
    db.delete(tag)
    db.commit()


@router.post("/leads/{lead_id}/tags/{tag_id}", status_code=201)
def add_tag_to_lead(
    lead_id: uuid.UUID,
    tag_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    enforce_rate_limit(str(current_user.id), "crm_write", _WRITE_LIMIT)

    lead = crm_service.owned_lead(db, lead_id, current_user)
    tag = db.get(CrmTag, tag_id)
    if tag is None or tag.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="tag not found")
    exists = db.execute(
        select(CrmLeadTag).where(CrmLeadTag.lead_id == lead.id,
                                 CrmLeadTag.tag_id == tag.id)
    ).scalars().first()
    if exists is not None:
        return {"lead_id": str(lead.id), "tag_id": str(tag.id), "created": False}
    db.add(CrmLeadTag(lead_id=lead.id, tag_id=tag.id))
    crm_service.log_activity(db, lead, CrmActivityKind.TAG_ADDED,
                             actor=current_user, to_value=tag.name)
    db.commit()
    return {"lead_id": str(lead.id), "tag_id": str(tag.id), "created": True}


@router.delete("/leads/{lead_id}/tags/{tag_id}", status_code=204)
def remove_tag_from_lead(
    lead_id: uuid.UUID,
    tag_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    enforce_rate_limit(str(current_user.id), "crm_write", _WRITE_LIMIT)

    lead = crm_service.owned_lead(db, lead_id, current_user)
    tag = db.get(CrmTag, tag_id)
    if tag is None or tag.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="tag not found")
    row = db.execute(
        select(CrmLeadTag).where(CrmLeadTag.lead_id == lead.id,
                                 CrmLeadTag.tag_id == tag.id)
    ).scalars().first()
    if row is not None:
        db.delete(row)
        crm_service.log_activity(db, lead, CrmActivityKind.TAG_REMOVED,
                                 actor=current_user, from_value=tag.name)
        db.commit()


# ---------------------------------------------------------------------------
# Activity (per lead)
# ---------------------------------------------------------------------------


@router.get("/leads/{lead_id}/activity")
def lead_activity(
    lead_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    before: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    return crm_service.dashboard_activity(
        db, current_user, lead_id=lead_id, limit=limit, before=before
    )


# ---------------------------------------------------------------------------
# Saved views
# ---------------------------------------------------------------------------


def _view_out(view: CrmSavedView) -> dict:
    return {
        "id": str(view.id),
        "name": view.name,
        "view_type": view.view_type.value,
        "filters_json": view.filters_json,
        "sort_json": view.sort_json,
        "columns_json": view.columns_json,
        "is_default": view.is_default,
        "created_at": view.created_at.isoformat() if view.created_at else None,
    }


def _clear_other_defaults(db: Session, user: User, view_type: CrmViewType,
                          keep_id: uuid.UUID | None) -> None:
    """At most one default per (user, view_type).

    Enforced here rather than by a partial unique index: SQLite and
    PostgreSQL both support one, but with divergent syntax that would need
    two dialect branches in the migration to express a rule that is one
    UPDATE at the call site.
    """
    others = db.execute(
        select(CrmSavedView).where(
            CrmSavedView.user_id == user.id,
            CrmSavedView.view_type == view_type,
            CrmSavedView.is_default.is_(True),
        )
    ).scalars().all()
    for other in others:
        if keep_id is None or other.id != keep_id:
            other.is_default = False


@router.get("/views")
def list_views(
    view_type: CrmViewType | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    query = select(CrmSavedView).where(CrmSavedView.user_id == current_user.id)
    if view_type is not None:
        query = query.where(CrmSavedView.view_type == view_type)
    rows = db.execute(query.order_by(CrmSavedView.name)).scalars().all()
    return {"items": [_view_out(view) for view in rows]}


@router.post("/views", status_code=201)
def create_view(
    body: SavedViewIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    enforce_rate_limit(str(current_user.id), "crm_write", _WRITE_LIMIT)

    clash = db.execute(
        select(CrmSavedView).where(CrmSavedView.user_id == current_user.id,
                                   CrmSavedView.view_type == body.view_type,
                                   CrmSavedView.name == body.name)
    ).scalars().first()
    if clash is not None:
        raise HTTPException(status_code=409,
                            detail=f"a {body.view_type.value} view named "
                                   f"'{body.name}' already exists")
    view = CrmSavedView(
        user_id=current_user.id, name=body.name, view_type=body.view_type,
        filters_json=body.filters_json, sort_json=body.sort_json,
        columns_json=body.columns_json, is_default=body.is_default,
    )
    db.add(view)
    db.flush()
    if body.is_default:
        _clear_other_defaults(db, current_user, body.view_type, view.id)
    db.commit()
    db.refresh(view)
    return _view_out(view)


@router.put("/views/{view_id}")
def update_view(
    view_id: uuid.UUID,
    body: SavedViewIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    enforce_rate_limit(str(current_user.id), "crm_write", _WRITE_LIMIT)

    view = db.get(CrmSavedView, view_id)
    if view is None or view.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="view not found")
    view.name = body.name
    view.view_type = body.view_type
    view.filters_json = body.filters_json
    view.sort_json = body.sort_json
    view.columns_json = body.columns_json
    view.is_default = body.is_default
    if body.is_default:
        _clear_other_defaults(db, current_user, body.view_type, view.id)
    db.commit()
    db.refresh(view)
    return _view_out(view)


@router.delete("/views/{view_id}", status_code=204)
def delete_view(
    view_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    enforce_rate_limit(str(current_user.id), "crm_write", _WRITE_LIMIT)

    view = db.get(CrmSavedView, view_id)
    if view is None or view.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="view not found")
    db.delete(view)
    db.commit()


# ---------------------------------------------------------------------------
# Custom fields
# ---------------------------------------------------------------------------


@router.get("/fields")
def list_fields(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    rows = db.execute(
        select(CrmCustomField).where(CrmCustomField.user_id == current_user.id)
        .order_by(CrmCustomField.sort_order, CrmCustomField.label)
    ).scalars().all()
    return {"items": [
        {"id": str(field.id), "key": field.key, "label": field.label,
         "field_type": field.field_type.value,
         "options_json": field.options_json, "sort_order": field.sort_order}
        for field in rows
    ]}


@router.post("/fields", status_code=201)
def create_field(
    body: CustomFieldIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    enforce_rate_limit(str(current_user.id), "crm_write", _WRITE_LIMIT)

    if body.field_type is CrmFieldType.SELECT and not body.options_json:
        raise HTTPException(status_code=422,
                            detail="a select field requires options_json")
    clash = db.execute(
        select(CrmCustomField).where(CrmCustomField.user_id == current_user.id,
                                     CrmCustomField.key == body.key)
    ).scalars().first()
    if clash is not None:
        raise HTTPException(status_code=409,
                            detail=f"field '{body.key}' already exists")
    field = CrmCustomField(
        user_id=current_user.id, key=body.key, label=body.label,
        field_type=body.field_type, options_json=body.options_json,
        sort_order=body.sort_order,
    )
    db.add(field)
    db.commit()
    db.refresh(field)
    return {"id": str(field.id), "key": field.key, "label": field.label,
            "field_type": field.field_type.value,
            "options_json": field.options_json,
            "sort_order": field.sort_order}


@router.delete("/fields/{field_id}", status_code=204)
def delete_field(
    field_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Deletes the definition AND every value stored under it.

    There is no soft-delete: a hidden field that still owns data is a field
    the user cannot see, cannot edit and cannot get rid of.

    The values are removed explicitly for the same reason as in delete_tag --
    SQLite does not enforce the FK cascade, so leaning on it would leave the
    behaviour untested everywhere except production.
    """
    enforce_rate_limit(str(current_user.id), "crm_write", _WRITE_LIMIT)

    field = db.get(CrmCustomField, field_id)
    if field is None or field.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="field not found")
    db.execute(
        delete(CrmCustomFieldValue)
        .where(CrmCustomFieldValue.field_id == field.id)
    )
    db.delete(field)
    db.commit()


# ---------------------------------------------------------------------------
# Real-time stream (SSE)
# ---------------------------------------------------------------------------

# Ticket TTL. Long enough to survive a slow page load between minting and
# connecting, short enough that a ticket leaked through a log or a Referer
# header is useless by the time anyone reads it.
STREAM_TICKET_TTL_SECONDS = 60
_TICKET_PREFIX = "crm:stream:ticket:"


def _monotonic() -> float:
    """Wall-clock source for the connection cap, as a seam.

    Not inlined as `asyncio.get_event_loop().time()` so that the cap can be
    tested deterministically. The underlying clock is time.monotonic(), whose
    resolution on Windows is ~15.6ms -- two calls in the same tick return an
    identical value, so a test that sets the cap low and waits for it to fire
    is a race against the clock granularity rather than an assertion about
    the code.
    """
    return asyncio.get_event_loop().time()


@router.post("/stream/ticket")
def create_stream_ticket(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Mint a single-use ticket for GET /crm/stream.

    WHY A TICKET AND NOT THE BEARER TOKEN

    `EventSource` cannot set request headers -- that is a limitation of the
    browser API, not a choice here -- so the credential has to travel in the
    URL. Putting the access token there writes a JWT valid for the next hour
    into the server access log, the browser history, and any Referer sent by
    a page the stream URL appears on.

    A ticket is random, single-use, expires in 60 seconds, and grants exactly
    one capability: read this user's CRM event channel. Leaking one costs
    nothing meaningful.

    Not rate-limited as a write because it writes no application data, and
    limiting it would break the reconnect path the moment a flaky mobile
    connection needs several tickets in a row -- which is exactly when the
    feature has to keep working.
    """
    ticket = secrets.token_urlsafe(32)
    try:
        from app.core.redis_client import get_sync_redis

        get_sync_redis().setex(
            f"{_TICKET_PREFIX}{ticket}", STREAM_TICKET_TTL_SECONDS,
            str(current_user.id),
        )
    except Exception as exc:
        # No Redis means no pub/sub either, so the stream could not deliver
        # anything. Say so plainly instead of handing out a ticket that will
        # be rejected a moment later; the client falls back to polling.
        logger.warning("crm.stream_ticket_failed", error=str(exc))
        raise HTTPException(
            status_code=503,
            detail="real-time stream unavailable; the client should poll",
        )
    return {"ticket": ticket, "expires_in": STREAM_TICKET_TTL_SECONDS}


def _redeem_ticket(ticket: str) -> str:
    """Exchange a ticket for a user id, consuming it. Raises 401 if invalid.

    GETDEL, not GET-then-DELETE: two commands leave a window where the same
    ticket can be redeemed twice concurrently.
    """
    from app.core.redis_client import get_sync_redis

    try:
        user_id = get_sync_redis().getdel(f"{_TICKET_PREFIX}{ticket}")
    except Exception as exc:
        logger.warning("crm.stream_redeem_failed", error=str(exc))
        raise HTTPException(status_code=503,
                            detail="real-time stream unavailable")
    if not user_id:
        raise HTTPException(status_code=401,
                            detail="invalid or expired stream ticket")
    return user_id


@router.get("/stream")
async def crm_stream(request: Request, ticket: str = Query(...)) -> StreamingResponse:
    """Server-Sent Events: this user's CRM changes, as they commit.

    UNGATED BY PLAN, deliberately. A subscription costs one Redis connection,
    and the React Query poll fallback would hand a free-tier user the same
    data thirty seconds later anyway -- so a plan gate here would buy no
    saving and cost the free tier a worse product. The cost controls that do
    apply are the per-user channel and MAX_STREAM_SECONDS below.

    NOT `Depends(get_current_user)`: EventSource cannot send an
    Authorization header. Authentication is the ticket minted by
    POST /crm/stream/ticket, which is single-use and expires in 60s.

    SSE rather than WebSocket: every event here travels server -> client, the
    browser reconnects on its own, and it is plain HTTP -- so it passes
    through the same nginx/Railway path as the rest of the API with no
    upgrade handling to configure.
    """
    from app.config import settings

    max_seconds = int(getattr(settings, "crm_stream_max_seconds", 3600))
    if max_seconds <= 0:
        # KILL SWITCH, matching support_chat_enabled: a non-positive cap turns
        # the stream off without a deploy. It refuses the connection rather
        # than accepting one and immediately asking for a reconnect -- that
        # would put every open tab into a tight connect/disconnect loop, which
        # is worse than no real-time at all. 503 is the signal the client
        # already handles by falling back to polling.
        raise HTTPException(
            status_code=503,
            detail="real-time stream disabled; the client should poll",
        )

    user_id = _redeem_ticket(ticket)
    keepalive_seconds = 20

    async def event_stream():
        from app.core.redis_client import get_redis

        redis = get_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe(crm_events.channel_for(user_id))
        started = _monotonic()
        try:
            # Tells the client the stream is live before any event arrives, so
            # the UI can show "connected" rather than sitting in an
            # indeterminate state until the first change happens to occur.
            yield f"event: ready\ndata: {json.dumps({'user_id': user_id})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                if _monotonic() - started > max_seconds:
                    # Ask the client to reconnect rather than holding a worker
                    # slot for a tab someone left open over a weekend.
                    yield "event: reconnect\ndata: {}\n\n"
                    break
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=keepalive_seconds,
                )
                if message is None:
                    # A comment line: keeps proxies and mobile radios from
                    # deciding an idle connection is a dead one.
                    yield ": keepalive\n\n"
                    continue
                payload = message.get("data")
                if not payload:
                    continue
                try:
                    parsed = json.loads(payload)
                    name = parsed.get("event", "message")
                    data = json.dumps(parsed.get("data", {}))
                except (TypeError, ValueError):
                    continue
                yield f"event: {name}\ndata: {data}\n\n"
        except asyncio.CancelledError:  # client went away mid-await
            raise
        finally:
            try:
                await pubsub.unsubscribe()
                # redis-py renamed PubSub.close() to aclose() in 5.0.1 and
                # deprecated the old name. The pin is >=5.0,<6.0, which spans
                # the rename, so prefer the new name and fall back.
                closer = getattr(pubsub, "aclose", None) or pubsub.close
                await closer()
            except Exception:  # already gone; nothing to clean up
                pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            # nginx buffers proxied responses by default, which holds every
            # event until the buffer fills -- turning a live feed into a
            # batch delivery. nginx/ has a proxy_buffering directive for the
            # deployed path; this header covers any proxy that honours it.
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

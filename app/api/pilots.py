"""F09 -- 30-Day Pilot Mode (docs/features/f09-pilot-mode.md).

GET   /pilots/template            the criteria catalogue (no targets pre-filled)
POST  /pilots                     start: criteria locked from here on
GET   /pilots                     this account's pilots, newest first
GET   /pilots/current             the active pilot, else the latest, else null
GET   /pilots/{id}                one pilot: live progress, or its verdict
PATCH /pilots/{id}                {scorecard_emails} -- the only mutable field
POST  /pilots/{id}/end            end early (a verdict is written)
GET   /pilots/{id}/export         verdict PDF / CSV, ended pilots only

Behind `pilot_mode_enabled` (System Settings, default off): every route is a
409 while it is off (the F08 "disabled by the administrator" pattern).

TENANCY. current_user is the workspace owner (app/services/auth.py), and every
read filters pilots by that id; another account's pilot is a 404. Writes by an
SDR are refused by the RBAC gate (rbac.SDR_BLOCKED_PREFIXES has /pilots).

READS NEVER WRITE. A pilot whose 30 days are over shows "verdict pending"
until ends_at + pilot_mode_verdict_grace_hours; the hourly sweep then freezes
the verdict. Only owner/manager actions end a pilot early: "end now" (POST
/pilots/{id}/end) and starting the next pilot once the previous one's grace
period is over. A download sets `exported_at` only when an owner or manager
makes it, so the success metric counts the buyer's exports. Nothing here
touches billing.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import Pilot, User
from app.services import pilot_mode

router = APIRouter(tags=["pilots"])

DISABLED_DETAIL = "Pilot mode is disabled by the administrator"


class PilotStartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Validated in the service (types are checked there on purpose: a JSON
    # 5.0 or true must be refused, not coerced to 5 or 1).
    criteria: dict = Field(default_factory=dict)
    strategy_ids: list[uuid.UUID] | None = Field(default=None, max_length=200)
    scorecard_emails: bool = True


class PilotPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scorecard_emails: bool


def _enabled(db: Session = Depends(get_db)) -> None:
    if not pilot_mode.is_enabled(db):
        raise HTTPException(status_code=409, detail=DISABLED_DETAIL)


def _owned(db: Session, user: User, pilot_id: uuid.UUID) -> Pilot:
    pilot = pilot_mode.get_owned(db, user.id, pilot_id)
    if pilot is None:
        raise HTTPException(status_code=404, detail="pilot not found")
    return pilot


def _raise(exc: pilot_mode.PilotError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/pilots/template", dependencies=[Depends(_enabled)])
def get_template(current_user: User = Depends(get_current_user)) -> dict:
    return pilot_mode.template()


@router.post("/pilots", status_code=201, dependencies=[Depends(_enabled)])
def start(body: PilotStartIn, request: Request, db: Session = Depends(get_db),
          current_user: User = Depends(get_current_user)) -> dict:
    actor = getattr(request.state, "actor", None) or current_user
    try:
        pilot = pilot_mode.start_pilot(
            db, current_user, criteria=body.criteria,
            strategy_ids=body.strategy_ids, scorecard_emails=body.scorecard_emails,
            actor_id=actor.id)
    except pilot_mode.PilotError as exc:
        _raise(exc)
    return pilot_mode.pilot_out(db, pilot, with_progress=True)


@router.get("/pilots", dependencies=[Depends(_enabled)])
def list_pilots(db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)) -> dict:
    return {"items": [pilot_mode.pilot_out(db, pilot)
                      for pilot in pilot_mode.list_pilots(db, current_user.id)]}


@router.get("/pilots/current", dependencies=[Depends(_enabled)])
def get_current(db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)) -> dict:
    pilot = pilot_mode.current(db, current_user.id)
    return {"pilot": pilot_mode.pilot_out(db, pilot, with_progress=True) if pilot else None}


@router.get("/pilots/{pilot_id}", dependencies=[Depends(_enabled)])
def get_pilot(pilot_id: uuid.UUID, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)) -> dict:
    pilot = _owned(db, current_user, pilot_id)
    return pilot_mode.pilot_out(db, pilot, with_progress=True)


@router.patch("/pilots/{pilot_id}", dependencies=[Depends(_enabled)])
def patch_pilot(pilot_id: uuid.UUID, body: PilotPatchIn, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)) -> dict:
    pilot = _owned(db, current_user, pilot_id)
    pilot = pilot_mode.set_scorecard_emails(db, pilot, body.scorecard_emails)
    return pilot_mode.pilot_out(db, pilot)


@router.post("/pilots/{pilot_id}/end", dependencies=[Depends(_enabled)])
def end_early(pilot_id: uuid.UUID, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)) -> dict:
    """End now. Before day 30 this is an early end (verdict over the days so
    far); after day 30 -- in the grace period or past it, before the sweep got
    there -- it freezes the full 30-day verdict now (`completed`). Either way
    the answer is 200 with the ended pilot and its verdict."""
    pilot = _owned(db, current_user, pilot_id)
    if pilot.status != pilot_mode.ACTIVE:
        raise HTTPException(status_code=409, detail="This pilot has already ended.")
    reason = (pilot_mode.COMPLETED if pilot_mode.is_over(pilot)
              else pilot_mode.ENDED_EARLY)
    pilot = pilot_mode.end_pilot(db, pilot, reason=reason)
    return pilot_mode.pilot_out(db, pilot)


@router.get("/pilots/{pilot_id}/export", dependencies=[Depends(_enabled)],
            response_class=Response,
            responses={200: {"content": {"text/csv": {}, "application/pdf": {}}}})
def export_verdict(
    pilot_id: uuid.UUID,
    request: Request,
    format: str = Query(default="pdf", pattern="^(csv|pdf)$"),  # noqa: A002
    view: str = Query(default="verdict", pattern="^(verdict|campaigns)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """The end-of-pilot download. Aggregates only (no prospect names or
    emails); the full account data is POST /me/data-export."""
    pilot = _owned(db, current_user, pilot_id)
    if pilot.status != pilot_mode.ENDED or pilot.verdict_json is None:
        raise HTTPException(status_code=409,
                            detail="The export is offered when the pilot's verdict is final.")
    stem = f"leadpilot-pilot-verdict-{pilot.start_date.isoformat()}"
    headers = {"Cache-Control": "private, no-store"}
    if format == "pdf":
        content, media = pilot_mode.verdict_pdf(pilot), "application/pdf"
        headers["Content-Disposition"] = f'attachment; filename="{stem}.pdf"'
    else:
        content = pilot_mode.verdict_csv(pilot, view=view)
        media = "text/csv; charset=utf-8"
        suffix = "" if view == "verdict" else "-campaigns"
        headers["Content-Disposition"] = f'attachment; filename="{stem}{suffix}.csv"'
    # The success metric is "the buyer exported": a viewer's or SDR's
    # download is a read and writes nothing.
    if getattr(request.state, "workspace_role", "owner") in ("owner", "manager"):
        pilot_mode.mark_exported(db, pilot)
    return Response(content=content, media_type=media, headers=headers)

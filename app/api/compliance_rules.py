"""Feature 8 — admin editing of compliance rules.

GET    /admin/compliance-rules?workspace_id=   baseline, hard bounds, global rows,
                                               and that workspace's rows
PUT    /admin/compliance-rules                 upsert one (scope, region, channel)
DELETE /admin/compliance-rules/{rule_id}
GET    /admin/compliance-rules/effective?workspace_id=&region=&channel=
                                               what a send there resolves to now
GET    /admin/compliance-rules/workspaces      the selector's options

Deployment admins only (require_admin). Values are validated with the same
function the resolver uses, so anything the API accepts the engine applies;
an invalid row can only come from raw SQL, and the resolver fails closed on it.
"""

# No `from __future__ import annotations` -- see the note in app/api/crm.py.

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.config import settings
from app.core.logging import get_logger
from app.db.base import get_db
from app.db.models import ComplianceRule, User, Workspace
from app.services import compliance_rules as rules

logger = get_logger("api.compliance_rules")

router = APIRouter(prefix="/admin/compliance-rules", tags=["admin"])


class RuleIn(BaseModel):
    workspace_id: uuid.UUID | None = None
    region: str = Field(default=rules.ANY, max_length=10)
    channel: str = Field(default=rules.ANY, max_length=20)
    send_start_hour: int | None = None
    send_end_hour: int | None = None
    skip_weekends: bool | None = None
    daily_cap: int | None = None
    consent_required: bool | None = None
    bounce_pause_threshold: float | None = None
    note: str | None = Field(default=None, max_length=200)


def _out(row: ComplianceRule) -> dict:
    return {
        "id": str(row.id),
        "scope": row.scope,
        "workspace_id": str(row.workspace_id) if row.workspace_id else None,
        "region": row.region,
        "channel": row.channel,
        **{name: getattr(row, name) for name in rules.RULE_FIELDS},
        "note": row.note,
        "problems": rules._row_errors(row),  # noqa: SLF001 -- surfaced to the admin
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _effective_out(eff: rules.Effective) -> dict:
    return {**{name: getattr(eff, name) for name in rules.RULE_FIELDS},
            "window_empty": eff.window_empty, "failed_closed": eff.failed_closed,
            "rule_ids": list(eff.rule_ids)}


@router.get("")
def list_rules(workspace_id: uuid.UUID | None = None, db: Session = Depends(get_db),
               _admin: User = Depends(require_admin)) -> dict:
    scopes = [rules.GLOBAL] + ([str(workspace_id)] if workspace_id else [])
    rows = db.execute(select(ComplianceRule).where(ComplianceRule.scope.in_(scopes))
                      .order_by(ComplianceRule.scope, ComplianceRule.region,
                                ComplianceRule.channel)).scalars().all()
    return {
        "baseline": _effective_out(rules.baseline()),
        "baseline_caps": {c: rules.baseline_cap(c) for c in rules.CHANNELS if c != rules.ANY},
        "hard_bounds": {"hour_min": rules.HOUR_MIN, "hour_max": rules.HOUR_MAX,
                        "bounce_max": settings.bounce_rate_pause_threshold},
        "regions": list(rules.REGIONS),
        "channels": list(rules.CHANNELS),
        "rules": [_out(r) for r in rows],
    }


@router.get("/workspaces")
def list_workspaces(db: Session = Depends(get_db),
                    _admin: User = Depends(require_admin)) -> list[dict]:
    rows = db.execute(select(Workspace, User.email)
                      .join(User, User.id == Workspace.owner_user_id)
                      .order_by(Workspace.name)).all()
    return [{"id": str(ws.id), "name": ws.name, "owner_email": email} for ws, email in rows]


@router.get("/effective")
def effective(workspace_id: uuid.UUID | None = None,
              region: str = Query(default=rules.ANY), channel: str = Query(default=rules.ANY),
              db: Session = Depends(get_db), _admin: User = Depends(require_admin)) -> dict:
    if region not in rules.REGIONS or channel not in rules.CHANNELS:
        raise HTTPException(status_code=422, detail="unknown region or channel")
    return _effective_out(rules.resolve_for(db, workspace_id, region, channel))


@router.put("")
def upsert_rule(body: RuleIn, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)) -> dict:
    if body.region not in rules.REGIONS:
        raise HTTPException(status_code=422, detail=f"region must be one of {rules.REGIONS}")
    if body.channel not in rules.CHANNELS:
        raise HTTPException(status_code=422, detail=f"channel must be one of {rules.CHANNELS}")
    values = body.model_dump(include=set(rules.RULE_FIELDS))
    problems = rules.errors(values, body.channel)
    if problems:
        raise HTTPException(status_code=422, detail="; ".join(problems))
    if all(v is None for v in values.values()):
        raise HTTPException(status_code=422, detail="a rule must set at least one field")
    if body.workspace_id is not None and db.get(Workspace, body.workspace_id) is None:
        raise HTTPException(status_code=404, detail="workspace not found")

    scope = str(body.workspace_id) if body.workspace_id else rules.GLOBAL
    row = db.execute(select(ComplianceRule).where(
        ComplianceRule.scope == scope, ComplianceRule.region == body.region,
        ComplianceRule.channel == body.channel)).scalar_one_or_none()
    if row is None:
        row = ComplianceRule(scope=scope, workspace_id=body.workspace_id,
                             region=body.region, channel=body.channel)
        db.add(row)
    for name, value in values.items():
        setattr(row, name, value)
    row.note = body.note
    row.updated_by_user_id = admin.id
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("admin.compliance_rule_upserted", scope=scope, region=body.region,
                channel=body.channel, admin_id=str(admin.id))
    return _out(row)


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: uuid.UUID, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)) -> Response:
    row = db.get(ComplianceRule, rule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="rule not found")
    db.delete(row)
    db.commit()
    logger.info("admin.compliance_rule_deleted", rule_id=str(rule_id), admin_id=str(admin.id))
    return Response(status_code=204)

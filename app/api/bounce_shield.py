"""F01 -- Waterfall Enrichment + Bounce Shield endpoints.

GET    /leads/{lead_id}/email-verdict          verdict, override, send decision, attempts
POST   /leads/{lead_id}/email-verdict/refresh  re-verify the current address
POST   /leads/{lead_id}/email-override         allow sending to a non-verified address
DELETE /leads/{lead_id}/email-override         take that back
GET    /bounce-shield/metrics                  the F01 success metric + cost ledger

Every lead is resolved through app/api/leads.py::_owned_lead (another
account's lead is a 404), and every ledger read filters by the owner's id.
None of these routes sends anything: releasing blocked messages returns them
to SCHEDULED, and the send task re-checks every gate.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.leads import _owned_lead
from app.config import settings
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import Lead, User
from app.services import bounce_shield, rbac
from app.services import waterfall_enrichment as wf

router = APIRouter(tags=["bounce-shield"])


def _get_verifier():
    """The configured EmailVerifier (Hunter). Tests monkeypatch this."""
    import app.integrations.hunter  # noqa: F401,PLC0415 -- registers the adapter
    from app.integrations.base import get_email_verifier  # noqa: PLC0415

    return get_email_verifier(settings.email_verifier_provider)


def _require_manager(request: Request, action: str) -> None:
    role = getattr(request.state, "workspace_role", None) or "owner"
    if not rbac.at_least(role, "manager"):
        raise HTTPException(status_code=403,
                            detail=f"{action} needs an owner or manager in this workspace.")


def _actor_id(request: Request, current_user: User):
    actor = getattr(request.state, "actor", None)
    return getattr(actor, "id", None) or current_user.id


def _verdict_out(db: Session, lead: Lead, current_user: User) -> dict:
    record = wf.verdict_record(lead)
    bound = wf.verdict_for(lead)
    override = bounce_shield.override_for(lead)
    decision = bounce_shield.decide(db, lead)
    return {
        "lead_id": str(lead.id),
        "email": lead.email,
        "verdict": ({k: v for k, v in bound.items() if k != "email_sha256"}
                    if bound else None),
        # A record exists but is for an address the lead no longer has.
        "verdict_is_stale_address": record is not None and bound is None,
        "override": ({k: v for k, v in override.items() if k != "email_sha256"}
                     if override else None),
        "send_decision": {
            # What the shield WOULD decide; when it is off nothing is blocked.
            "shield_enabled": bounce_shield.enabled(db),
            "allowed": decision.allowed or not bounce_shield.enabled(db),
            "would_allow": decision.allowed,
            "tag": decision.tag,
            "reason": decision.reason,
        },
        "attempts": bounce_shield.attempts_for_lead(db, current_user.id, lead),
        "settings": bounce_shield.settings_out(db),
    }


@router.get("/leads/{lead_id}/email-verdict")
def get_email_verdict(lead_id: uuid.UUID, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)) -> dict:
    lead = _owned_lead(db, lead_id, current_user)
    return _verdict_out(db, lead, current_user)


@router.post("/leads/{lead_id}/email-verdict/refresh")
def refresh_email_verdict(lead_id: uuid.UUID, request: Request,
                          db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)) -> dict:
    """Re-verify the lead's current address. Spends one verifier call unless
    the 30-day provider cache already holds the answer."""
    # First statement (tests/test_rate_limit_ordering.py): each call can spend
    # a paid verification. FastAPI has already validated the path by now.
    enforce_rate_limit(str(current_user.id), "bounce_shield_refresh", "RATE_LIMIT_AI_ACTION")
    lead = _owned_lead(db, lead_id, current_user)
    if not (bounce_shield.enabled(db) or wf.enabled(db)):
        raise HTTPException(status_code=409,
                            detail="Waterfall enrichment and Bounce Shield are both off.")
    try:
        record = bounce_shield.refresh(db, lead, _get_verifier(),
                                       actor_id=_actor_id(request, current_user),
                                       owner_id=current_user.id)
    except bounce_shield.OverrideRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    released = 0
    if bounce_shield.decide(db, lead).allowed:
        released = bounce_shield.requeue_blocked(db, lead)
    out = _verdict_out(db, lead, current_user)
    out["cached"] = bool(record.get("cached"))
    out["released_messages"] = released
    return out


class OverrideIn(BaseModel):
    #: Why sending to an address that is not verified-valid is acceptable.
    #: Recorded on the lead and in the compliance audit log.
    reason: str = Field(min_length=5, max_length=300)


@router.post("/leads/{lead_id}/email-override")
def set_email_override(lead_id: uuid.UUID, body: OverrideIn, request: Request,
                       db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)) -> dict:
    lead = _owned_lead(db, lead_id, current_user)
    _require_manager(request, "Overriding the bounce shield")
    if not bounce_shield.enabled(db):
        raise HTTPException(status_code=409, detail="Bounce Shield is off.")
    try:
        bounce_shield.set_override(db, lead, actor_id=_actor_id(request, current_user),
                                   owner_id=current_user.id, reason=body.reason)
    except bounce_shield.OverrideRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    released = bounce_shield.requeue_blocked(db, lead)
    out = _verdict_out(db, lead, current_user)
    out["released_messages"] = released
    return out


@router.delete("/leads/{lead_id}/email-override")
def delete_email_override(lead_id: uuid.UUID, request: Request,
                          db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)) -> dict:
    lead = _owned_lead(db, lead_id, current_user)
    _require_manager(request, "Removing a bounce shield override")
    removed = bounce_shield.clear_override(db, lead, actor_id=_actor_id(request, current_user),
                                           owner_id=current_user.id, why="removed by a user")
    out = _verdict_out(db, lead, current_user)
    out["removed"] = removed
    return out


@router.get("/bounce-shield/metrics")
def bounce_shield_metrics(days: int = Query(default=30, ge=1, le=365),
                          db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)) -> dict:
    return bounce_shield.metrics(db, current_user.id, days=days, verifier=_get_verifier())

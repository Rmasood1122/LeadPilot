"""F10 -- Champion Tracker + Staleness Check endpoints.

GET    /leads/{lead_id}/role-check            role state, send decision, held messages, move
POST   /leads/{lead_id}/role-check/refresh    one role check now (spends a lookup)
POST   /leads/{lead_id}/role-check/confirm    a person confirms the role -> releases holds
GET    /champions/moves                       the account's recorded job changes
POST   /champions/moves/{move_id}/dismiss     a wrong detection -> lifts the block
GET    /champions/held                        the account's held messages
GET    /champions/metrics                     the F10 success metric + budget

Every lead is resolved through app/api/leads.py::_owned_lead (another
account's lead is a 404); every move and held-message query filters by the
owner's id. None of these routes sends anything: a release returns messages
to SCHEDULED and the send task re-checks every gate.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.leads import _owned_lead
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import User
from app.services import champion_tracker, rbac

router = APIRouter(tags=["champion-tracker"])


def _get_source():
    """The configured LeadSource (Apollo). Tests monkeypatch this."""
    from app.workers.champion_tasks import _get_source as worker_source  # noqa: PLC0415

    return worker_source()


def _get_verifier():
    """The configured EmailVerifier (Hunter). Tests monkeypatch this."""
    from app.workers.champion_tasks import _get_verifier as worker_verifier  # noqa: PLC0415

    return worker_verifier()


def _require_manager(request: Request, action: str) -> None:
    role = getattr(request.state, "workspace_role", None) or "owner"
    if not rbac.at_least(role, "manager"):
        raise HTTPException(status_code=403,
                            detail=f"{action} needs an owner or manager in this workspace.")


def _actor_id(request: Request, current_user: User):
    actor = getattr(request.state, "actor", None)
    return getattr(actor, "id", None) or current_user.id


@router.get("/leads/{lead_id}/role-check")
def get_role_check(lead_id: uuid.UUID, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)) -> dict:
    lead = _owned_lead(db, lead_id, current_user)
    return champion_tracker.role_check_out(db, lead, current_user.id)


@router.post("/leads/{lead_id}/role-check/refresh")
def refresh_role_check(lead_id: uuid.UUID, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)) -> dict:
    """Re-verify this prospect's role now. Spends one lead-source lookup
    unless the 30-day cache holds it; the account's monthly cap applies."""
    # First statement (tests/test_rate_limit_ordering.py): each call can spend
    # a paid lookup. FastAPI has already validated the path by now.
    enforce_rate_limit(str(current_user.id), "champion_refresh", "RATE_LIMIT_AI_ACTION")
    lead = _owned_lead(db, lead_id, current_user)
    if not champion_tracker.enabled(db):
        raise HTTPException(status_code=409, detail="The champion tracker is off.")
    inactive = champion_tracker.inactive_reason(lead)
    if inactive:
        # An erased person is never looked up again; a dropped lead is closed.
        raise HTTPException(status_code=409,
                            detail=f"This prospect is {inactive}; nothing is looked up.")
    source = _get_source()
    if not champion_tracker._source_available(source):
        raise HTTPException(status_code=409, detail="No lead-source credentials are configured.")
    result = champion_tracker.reverify(db, lead, source, _get_verifier(), trigger="manual")
    out = champion_tracker.role_check_out(db, lead, current_user.id)
    out["result"] = result
    return out


class ConfirmIn(BaseModel):
    #: Why the person is known to still hold the role. Recorded and audited.
    reason: str = Field(min_length=5, max_length=300)
    #: Take the provider's newer title (when a title change was found).
    adopt_title: bool = False


@router.post("/leads/{lead_id}/role-check/confirm")
def confirm_role(lead_id: uuid.UUID, body: ConfirmIn, request: Request,
                 db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)) -> dict:
    lead = _owned_lead(db, lead_id, current_user)
    _require_manager(request, "Confirming a prospect's role")
    try:
        result = champion_tracker.confirm(db, lead, actor_id=_actor_id(request, current_user),
                                          owner_id=current_user.id, reason=body.reason,
                                          adopt_title=body.adopt_title)
    except champion_tracker.Refused as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    out = champion_tracker.role_check_out(db, lead, current_user.id)
    out["released_messages"] = result["released"]
    out["adopted_title"] = result["adopted_title"]
    return out


@router.get("/champions/moves")
def list_moves(limit: int = Query(default=50, ge=1, le=200),
               offset: int = Query(default=0, ge=0),
               db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)) -> dict:
    return champion_tracker.list_moves(db, current_user.id, limit=limit, offset=offset)


class DismissIn(BaseModel):
    reason: str = Field(min_length=5, max_length=300)


@router.post("/champions/moves/{move_id}/dismiss")
def dismiss_move(move_id: uuid.UUID, body: DismissIn, request: Request,
                 db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)) -> dict:
    move = champion_tracker.owned_move(db, current_user.id, move_id)
    if move is None:
        raise HTTPException(status_code=404, detail="move not found")
    _require_manager(request, "Dismissing a recorded job change")
    try:
        champion_tracker.dismiss_move(db, move, actor_id=_actor_id(request, current_user),
                                      owner_id=current_user.id, reason=body.reason)
    except champion_tracker.Refused as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return champion_tracker.move_out(db, move)


@router.get("/champions/held")
def held_messages(limit: int = Query(default=100, ge=1, le=500),
                  db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> dict:
    return champion_tracker.held_list(db, current_user.id, limit=limit)


@router.get("/champions/metrics")
def champion_metrics(days: int = Query(default=90, ge=1, le=365),
                     db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)) -> dict:
    return champion_tracker.metrics(db, current_user.id, days=days)

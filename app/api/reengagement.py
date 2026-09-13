"""Feature 5 — opt-in post-sequence re-engagement settings.

GET  /strategies/{id}/reengagement   settings, caps, sends today/this week,
                                     and how many leads would qualify now
PUT  /strategies/{id}/reengagement   {enabled?, delay_days?, daily_cap?, weekly_cap?}

Ownership follows the codebase rule: a campaign that is not yours is a 404.
Changing these needs an owner or manager -- turning on a campaign-wide send is
the same kind of decision as launching one, which an SDR needs approval for.
Values outside the admin ceilings are REFUSED (422), not silently clamped, so
what the panel shows is what was saved. See app/services/reengagement.py.
"""

# No `from __future__ import annotations` -- see the note in app/api/crm.py.

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.analytics import _owned_strategy
from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import User
from app.services import rbac, reengagement

router = APIRouter(tags=["reengagement"])


class ReengagementIn(BaseModel):
    enabled: bool | None = None
    delay_days: int | None = Field(default=None, ge=1, le=365)
    daily_cap: int | None = Field(default=None, ge=0, le=1000)
    weekly_cap: int | None = Field(default=None, ge=0, le=5000)


@router.get("/strategies/{strategy_id}/reengagement")
def get_reengagement(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    strategy = _owned_strategy(strategy_id, db, current_user)
    return reengagement.status(db, strategy)


@router.put("/strategies/{strategy_id}/reengagement")
def put_reengagement(
    strategy_id: uuid.UUID,
    body: ReengagementIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    strategy = _owned_strategy(strategy_id, db, current_user)
    role = getattr(request.state, "workspace_role", None) or "owner"
    if not rbac.at_least(role, "manager"):
        raise HTTPException(status_code=403,
                            detail="Re-engagement settings need a manager in this workspace.")

    limit = reengagement.ceilings(db)
    if body.enabled and not reengagement.allowed(db):
        raise HTTPException(status_code=409,
                            detail="Re-engagement is turned off for this deployment.")
    if body.daily_cap is not None and body.daily_cap > limit["daily_cap"]:
        raise HTTPException(status_code=422,
                            detail=f"daily_cap may be at most {limit['daily_cap']}")
    if body.weekly_cap is not None and body.weekly_cap > limit["weekly_cap"]:
        raise HTTPException(status_code=422,
                            detail=f"weekly_cap may be at most {limit['weekly_cap']}")
    if body.delay_days is not None and body.delay_days < limit["min_delay_days"]:
        raise HTTPException(status_code=422,
                            detail=f"delay_days must be at least {limit['min_delay_days']}")

    daily = body.daily_cap if body.daily_cap is not None else strategy.reengagement_daily_cap
    weekly = body.weekly_cap if body.weekly_cap is not None else strategy.reengagement_weekly_cap
    if weekly < daily:
        raise HTTPException(status_code=422,
                            detail="weekly_cap must be at least the daily_cap")

    if body.enabled is not None:
        strategy.reengagement_enabled = body.enabled
    if body.delay_days is not None:
        strategy.reengagement_delay_days = body.delay_days
    strategy.reengagement_daily_cap = daily
    strategy.reengagement_weekly_cap = weekly
    db.commit()
    return reengagement.status(db, strategy)

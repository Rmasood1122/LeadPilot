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
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.analytics import _owned_strategy
from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import ReengagementPlan, User
from app.services import crm_service, rbac, reengagement, reengagement_memory

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


# ---------------------------------------------------------------------------
# Part 1 Feature 7 — re-engagement memory ("not now" is not "never")
#
# A different object from the settings above. Those configure a CAMPAIGN-wide
# opt-in sweep; these are per-PROSPECT dated return visits created by a "not
# now" reply, each carrying the reason that prospect gave. New sub-paths, no
# collision with the two endpoints above.
# ---------------------------------------------------------------------------


class RescheduleIn(BaseModel):
    #: A day, not a datetime: the unit of this feature is "come back in
    #: March", and asking someone to pick a minute would be theatre.
    due_on: date


class CancelIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


def _owned_plan(db: Session, plan_id: uuid.UUID, current_user: User) -> ReengagementPlan:
    """404, not 403, for someone else's plan — existence must not be probeable."""
    plan = db.get(ReengagementPlan, plan_id)
    if plan is None or plan.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="plan not found")
    return plan


@router.get("/reengagement/plans")
def list_reengagement_plans(
    status: str | None = Query(default="scheduled",
                               pattern="^(scheduled|due|sent|cancelled|all)$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Dated return visits, soonest first — the list of promises to keep."""
    return reengagement_memory.list_plans(
        db, current_user.id, status=None if status == "all" else status,
        limit=limit, offset=offset)


@router.get("/leads/{lead_id}/reengagement-plans")
def lead_reengagement_plans(lead_id: uuid.UUID, db: Session = Depends(get_db),
                            current_user: User = Depends(get_current_user)) -> list[dict]:
    """Every "not now" this prospect has given, newest first."""
    lead = crm_service.owned_lead(db, lead_id, current_user)
    return reengagement_memory.for_lead(db, lead.id)


@router.post("/reengagement/plans/{plan_id}/reschedule")
def reschedule_plan(plan_id: uuid.UUID, body: RescheduleIn,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)) -> dict:
    """Move the date. A person who knows the prospect knows better than the
    interval table, so this works on a plan the sweep has already marked due."""
    plan = _owned_plan(db, plan_id, current_user)
    if plan.status in ("sent", "cancelled"):
        raise HTTPException(status_code=409,
                            detail=f"this plan is already {plan.status}")
    if body.due_on <= datetime.now(timezone.utc).date():
        raise HTTPException(status_code=422, detail="pick a date in the future")
    reengagement_memory.reschedule(
        db, plan, datetime.combine(body.due_on, datetime.min.time(), tzinfo=timezone.utc))
    return reengagement_memory.plan_out(db, plan)


@router.post("/reengagement/plans/{plan_id}/cancel")
def cancel_plan(plan_id: uuid.UUID, body: CancelIn, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)) -> dict:
    """Never come back to this one. A reason is required — a cancelled promise
    is worth understanding later."""
    plan = _owned_plan(db, plan_id, current_user)
    if plan.status in ("sent", "cancelled"):
        raise HTTPException(status_code=409,
                            detail=f"this plan is already {plan.status}")
    reengagement_memory.cancel(db, plan, body.reason)
    return reengagement_memory.plan_out(db, plan)

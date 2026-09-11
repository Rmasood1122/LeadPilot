"""Feature Group 3 API: revenue analytics, campaign costs, the per-step funnel,
smart send time and reply sentiment.

GET    /analytics/revenue?date_from&date_to
GET    /costs · POST /costs · PATCH /costs/{id} · DELETE /costs/{id}
GET    /strategies/{id}/funnel
GET    /strategies/{id}/send-time
PUT    /strategies/{id}/send-time            {"smart_send_time": bool}
POST   /strategies/{id}/send-time/recompute
GET    /strategies/{id}/sentiment?weeks=12

Ownership follows the codebase rule: anything not yours is a 404.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.analytics import _owned_strategy
from app.api.deps import get_current_user
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import CampaignCost, User
from app.services import funnel, reply_sentiment, revenue_analytics, send_windows

router = APIRouter(tags=["revenue-analytics"])

CostCategory = Literal["data", "tools", "ai", "time", "ads", "other"]
_MAX_SPAN_DAYS = 3 * 366


# --------------------------------------------------------------------------
# Revenue
# --------------------------------------------------------------------------


@router.get("/analytics/revenue")
def revenue(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    today = datetime.now(timezone.utc).date()
    date_to = date_to or today
    date_from = date_from or (date_to - timedelta(days=89))
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to")
    if (date_to - date_from).days > _MAX_SPAN_DAYS:
        raise HTTPException(status_code=422, detail="the period may span at most 3 years")
    return revenue_analytics.report(db, current_user.id, date_from, date_to)


# --------------------------------------------------------------------------
# Costs
# --------------------------------------------------------------------------


class CostIn(BaseModel):
    strategy_id: uuid.UUID | None = None
    category: CostCategory = "other"
    description: str = Field(default="", max_length=300)
    amount: float | None = Field(default=None, ge=0, le=100_000_000)
    hours: float | None = Field(default=None, ge=0, le=10_000)
    hourly_rate: float | None = Field(default=None, ge=0, le=100_000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    incurred_on: date | None = None

    @model_validator(mode="after")
    def _amount_or_time(self):
        if self.amount is None and (self.hours is None or self.hourly_rate is None):
            raise ValueError("give an amount, or hours and an hourly_rate")
        return self


class CostPatch(BaseModel):
    strategy_id: uuid.UUID | None = None
    category: CostCategory | None = None
    description: str | None = Field(default=None, max_length=300)
    amount: float | None = Field(default=None, ge=0, le=100_000_000)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    incurred_on: date | None = None


def _cost_out(cost: CampaignCost) -> dict:
    return {
        "id": str(cost.id),
        "strategy_id": str(cost.strategy_id) if cost.strategy_id else None,
        "category": cost.category,
        "description": cost.description,
        "amount_cents": cost.amount_cents,
        "amount": round((cost.amount_cents or 0) / 100, 2),
        "currency": cost.currency,
        "hours": cost.hours,
        "incurred_on": cost.incurred_on.isoformat() if cost.incurred_on else None,
        "created_at": cost.created_at.isoformat() if cost.created_at else None,
    }


def _owned_cost(cost_id: uuid.UUID, db: Session, user: User) -> CampaignCost:
    cost = db.get(CampaignCost, cost_id)
    if cost is None or cost.user_id != user.id:
        raise HTTPException(status_code=404, detail="cost not found")
    return cost


@router.get("/costs")
def list_costs(
    strategy_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    query = select(CampaignCost).where(CampaignCost.user_id == current_user.id)
    if strategy_id is not None:
        _owned_strategy(strategy_id, db, current_user)
        query = query.where(CampaignCost.strategy_id == strategy_id)
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = db.execute(query.order_by(CampaignCost.incurred_on.desc(),
                                     CampaignCost.created_at.desc())
                      .limit(limit).offset(offset)).scalars().all()
    return {"total": total, "items": [_cost_out(c) for c in rows]}


@router.post("/costs", status_code=201)
def create_cost(
    body: CostIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if body.strategy_id is not None:
        _owned_strategy(body.strategy_id, db, current_user)
    amount = body.amount if body.amount is not None else body.hours * body.hourly_rate
    cost = CampaignCost(
        user_id=current_user.id, strategy_id=body.strategy_id, category=body.category,
        description=body.description.strip(), amount_cents=round(amount * 100),
        currency=body.currency.upper(), hours=body.hours,
        incurred_on=body.incurred_on or datetime.now(timezone.utc).date(),
    )
    db.add(cost)
    db.commit()
    db.refresh(cost)
    return _cost_out(cost)


@router.patch("/costs/{cost_id}")
def update_cost(
    cost_id: uuid.UUID,
    body: CostPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    cost = _owned_cost(cost_id, db, current_user)
    fields = body.model_dump(exclude_unset=True)
    if "strategy_id" in fields and fields["strategy_id"] is not None:
        _owned_strategy(fields["strategy_id"], db, current_user)
    if "strategy_id" in fields:
        cost.strategy_id = fields["strategy_id"]
    if fields.get("category"):
        cost.category = fields["category"]
    if fields.get("description") is not None:
        cost.description = fields["description"].strip()
    if fields.get("amount") is not None:
        cost.amount_cents = round(fields["amount"] * 100)
    if fields.get("currency"):
        cost.currency = fields["currency"].upper()
    if fields.get("incurred_on"):
        cost.incurred_on = fields["incurred_on"]
    db.commit()
    return _cost_out(cost)


@router.delete("/costs/{cost_id}", status_code=204)
def delete_cost(
    cost_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    db.delete(_owned_cost(cost_id, db, current_user))
    db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------
# Funnel, send time, sentiment
# --------------------------------------------------------------------------


@router.get("/strategies/{strategy_id}/funnel")
def strategy_funnel(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _owned_strategy(strategy_id, db, current_user)
    return funnel.step_funnel(db, strategy_id)


class SendTimeIn(BaseModel):
    smart_send_time: bool


@router.get("/strategies/{strategy_id}/send-time")
def get_send_time(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    return send_windows.status(db, _owned_strategy(strategy_id, db, current_user))


@router.put("/strategies/{strategy_id}/send-time")
def set_send_time(
    strategy_id: uuid.UUID,
    body: SendTimeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    strategy = _owned_strategy(strategy_id, db, current_user)
    strategy.smart_send_time = body.smart_send_time
    db.commit()
    moved = send_windows.reslot_scheduled(db, strategy) if body.smart_send_time else 0
    return {**send_windows.status(db, strategy), "rescheduled": moved}


@router.post("/strategies/{strategy_id}/send-time/recompute")
def recompute_send_time(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    enforce_rate_limit(str(current_user.id), "send_time_recompute", "RATE_LIMIT_AI_ACTION")
    strategy = _owned_strategy(strategy_id, db, current_user)
    result = send_windows.compute(db, strategy)
    moved = 0
    if result.get("windows") and strategy.smart_send_time:
        moved = send_windows.reslot_scheduled(db, strategy)
    return {**send_windows.status(db, strategy), "result": result["status"],
            "rescheduled": moved}


@router.get("/strategies/{strategy_id}/sentiment")
def strategy_sentiment(
    strategy_id: uuid.UUID,
    weeks: int = Query(default=12, ge=2, le=52),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _owned_strategy(strategy_id, db, current_user)
    return reply_sentiment.trend(db, strategy_id, weeks=weeks)

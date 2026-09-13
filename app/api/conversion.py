"""Live conversion probability (Feature A5).

GET  /leads/{lead_id}/conversion              the live estimate + the stored state
POST /leads/{lead_id}/conversion/reactivate   a person overrides a cooling/archived call
GET  /conversion/at-risk                      the account's cooling / archived leads
GET  /strategies/{strategy_id}/channel-performance   outcome-weighted channel + slot scores
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import Lead, Product, Strategy, User
from app.services import conversion_probability, crm_service, send_time_optimizer

router = APIRouter(tags=["conversion"])


@router.get("/leads/{lead_id}/conversion")
def lead_conversion(lead_id: uuid.UUID, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)) -> dict:
    lead = crm_service.owned_lead(db, lead_id, current_user)
    return {"live": conversion_probability.compute(db, lead).as_dict(),
            "stored": conversion_probability.stored_out(lead)}


@router.post("/leads/{lead_id}/conversion/reactivate")
def reactivate_lead(lead_id: uuid.UUID, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)) -> dict:
    lead = crm_service.owned_lead(db, lead_id, current_user)
    if (lead.engagement_state or "active") not in ("cooling", "archived"):
        raise HTTPException(status_code=409, detail="This lead is not cooling or archived.")
    return conversion_probability.reactivate(db, lead)


@router.get("/conversion/at-risk")
def at_risk(state: str = Query(default="cooling", pattern="^(cooling|archived)$"),
            limit: int = Query(default=100, ge=1, le=500),
            db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user)) -> list[dict]:
    rows = db.execute(
        select(Lead).join(Strategy, Strategy.id == Lead.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == current_user.id, Lead.engagement_state == state)
        .order_by(Lead.conversion_probability_at.desc()).limit(limit)
    ).scalars().all()
    return [{"lead_id": str(lead.id), "full_name": lead.full_name, "company": lead.company,
             **conversion_probability.stored_out(lead)} for lead in rows]


@router.get("/strategies/{strategy_id}/channel-performance")
def channel_performance(strategy_id: uuid.UUID, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)) -> dict:
    strategy = db.get(Strategy, strategy_id)
    product = db.get(Product, strategy.product_id) if strategy else None
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="strategy not found")
    return {"channels": send_time_optimizer.channel_conversion_rates(db, strategy_id),
            "slots": send_time_optimizer.outcome_weighted_slots(db, strategy_id),
            "booking_weight": send_time_optimizer.BOOKING_WEIGHT}

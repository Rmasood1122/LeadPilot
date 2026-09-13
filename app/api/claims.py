"""Claim engine audit endpoints (Feature A1).

GET /leads/{lead_id}/claim-checks    every claim decision for one lead, newest first
GET /claim-checks/summary            the account's verified/stripped/rewritten counts
                                     by category over the last N days

Owner-scoped like every lead route (Phase A): a lead that is not the caller's
is a 404, not a 403, so ids of other tenants' leads cannot be probed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import ClaimVerificationLog, Lead, Product, Strategy, User
from app.services import claim_verification

router = APIRouter(tags=["claims"])


def _owned_lead(db: Session, lead_id: uuid.UUID, user: User) -> Lead:
    lead = db.execute(
        select(Lead).join(Strategy, Strategy.id == Lead.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .where(Lead.id == lead_id, Product.user_id == user.id)
    ).scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead


@router.get("/leads/{lead_id}/claim-checks")
def lead_claim_checks(lead_id: uuid.UUID, limit: int = Query(default=100, ge=1, le=500),
                      db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)) -> list[dict]:
    lead = _owned_lead(db, lead_id, current_user)
    return claim_verification.lead_log(db, lead.id, limit=limit)


@router.get("/claim-checks/summary")
def claim_summary(days: int = Query(default=30, ge=1, le=365),
                  db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.execute(
        select(ClaimVerificationLog.category, ClaimVerificationLog.verdict,
               func.count(ClaimVerificationLog.id))
        .where(ClaimVerificationLog.user_id == current_user.id,
               ClaimVerificationLog.created_at >= since)
        .group_by(ClaimVerificationLog.category, ClaimVerificationLog.verdict)
    ).all()
    totals = {"verified": 0, "stripped": 0, "rewritten": 0}
    by_category: dict[str, dict[str, int]] = {}
    for category, verdict, count in rows:
        totals[verdict] = totals.get(verdict, 0) + int(count)
        by_category.setdefault(category, {})[verdict] = int(count)
    return {"days": days, "totals": totals, "by_category": by_category}

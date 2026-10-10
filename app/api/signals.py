"""F02 Signal Radar endpoints.

GET  /leads/{lead_id}/signals          the lead's dated signals, best first
POST /leads/{lead_id}/signals/refresh  re-derive from STORED data (no vendor call)
GET  /signals/report                   the success metric for the caller's account

Owner-scoped like every lead route: a lead that is not the caller's is a 404,
not a 403, so other tenants' lead ids cannot be probed. Signal rows are read
with BOTH the lead and `lead_signals.user_id` filters.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import Lead, Product, Strategy, User
from app.services import signal_radar, system_settings

router = APIRouter(tags=["signals"])


def _owned_lead(db: Session, lead_id: uuid.UUID, user: User) -> Lead:
    lead = db.execute(
        select(Lead).join(Strategy, Strategy.id == Lead.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .where(Lead.id == lead_id, Product.user_id == user.id)
    ).scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead


def _payload(db: Session, lead: Lead, user: User) -> dict:
    now = datetime.now(timezone.utc)
    claim_engine_on = bool(system_settings.get(db, "claim_verification_enabled"))
    rows = signal_radar.ranked(signal_radar.for_lead(db, lead, user.id), now)
    signals = [signal_radar.describe(r, now, claim_engine_on=claim_engine_on) for r in rows]
    top = next((s for s in signals if s["citable"]), None)
    return {"lead_id": str(lead.id), "enabled": True, "claim_verification": claim_engine_on,
            "signals": signals, "top": top}


@router.get("/leads/{lead_id}/signals")
def lead_signals(lead_id: uuid.UUID, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)) -> dict:
    lead = _owned_lead(db, lead_id, current_user)
    if not signal_radar.enabled(db):
        return {"lead_id": str(lead.id), "enabled": False, "claim_verification": None,
                "signals": [], "top": None}
    return _payload(db, lead, current_user)


@router.post("/leads/{lead_id}/signals/refresh")
def refresh_lead_signals(lead_id: uuid.UUID, db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)) -> dict:
    """Re-derive from what is already stored on the lead and its strategy. This
    never calls a vendor -- posts and news are refreshed by the send path."""
    lead = _owned_lead(db, lead_id, current_user)
    if not signal_radar.enabled(db):
        raise HTTPException(status_code=409, detail="Signal Radar is turned off")
    result = signal_radar.refresh(db, lead, owner_id=current_user.id)
    if "error" in result:
        raise HTTPException(status_code=500, detail="could not derive signals")
    return {**_payload(db, lead, current_user), "refresh": result}


@router.get("/signals/report")
def signals_report(days: int = Query(default=90, ge=1, le=365),
                   db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)) -> dict:
    """Reads history only, so it answers with the flag off too (`enabled`
    says which); turning the flag off must not hide what was already sent."""
    return {"enabled": signal_radar.enabled(db),
            **signal_radar.report(db, current_user.id, days=days)}

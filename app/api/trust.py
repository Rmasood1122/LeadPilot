"""Trust & deliverability API (Feature Group 9).

    GET  /deliverability              health + blacklist status per sending domain
    POST /deliverability/check        run the checks now (rate-limited)
    GET  /compliance/audit            the account's per-send compliance log
    GET  /leads/{lead_id}/compliance  region, regime, legal basis, audit rows
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import ComplianceAuditLog, Lead, Product, Strategy, User
from app.services import compliance_audit, deliverability

router = APIRouter(tags=["trust"])


@router.get("/deliverability")
def get_deliverability(db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)) -> dict:
    return deliverability.status(db, current_user.id)


@router.post("/deliverability/check")
def run_deliverability_check(db: Session = Depends(get_db),
                             current_user: User = Depends(get_current_user)) -> dict:
    enforce_rate_limit(str(current_user.id), "deliverability_check", "RATE_LIMIT_AI_ACTION")
    deliverability.run_checks(db, current_user.id)
    return deliverability.status(db, current_user.id)


@router.get("/compliance/audit")
def compliance_audit_log(lead_id: uuid.UUID | None = None,
                         limit: int = Query(default=100, ge=1, le=500),
                         db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)) -> list[dict]:
    query = select(ComplianceAuditLog).where(ComplianceAuditLog.user_id == current_user.id)
    if lead_id is not None:
        query = query.where(ComplianceAuditLog.lead_id == lead_id)
    rows = db.execute(query.order_by(ComplianceAuditLog.ts.desc()).limit(limit)).scalars()
    return [compliance_audit.audit_out(r) for r in rows]


@router.get("/leads/{lead_id}/compliance")
def lead_compliance(lead_id: uuid.UUID, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)) -> dict:
    lead = db.get(Lead, lead_id)
    owner = db.execute(select(Product.user_id).join(Strategy, Strategy.product_id == Product.id)
                       .where(Strategy.id == lead.strategy_id)).scalar_one_or_none() \
        if lead is not None else None
    if lead is None or owner != current_user.id:
        raise HTTPException(status_code=404, detail="lead not found")
    return compliance_audit.lead_summary(db, lead)

"""Trust & deliverability API (Feature Group 9).

    GET  /deliverability              health + blacklist status per sending domain
    POST /deliverability/check        run the checks now (rate-limited)
    GET  /deliverability/mailboxes    Part 1 Feature 4: per-MAILBOX health,
                                      the auto-throttle state and its reason
    POST /deliverability/mailboxes/refresh          recompute now
    POST /deliverability/mailboxes/{ref}/resume     un-pause (a human decision)
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
from app.services import compliance_audit, deliverability, mailbox_health

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


@router.get("/deliverability/mailboxes")
def get_mailbox_health(db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)) -> dict:
    """Part 1 Feature 4: one row per sending mailbox — its 0-100 score, the
    auth/complaint/bounce/volume inputs behind it, and whether sending is
    currently throttled or paused, with the reason in words.

    A connected mailbox nothing has scored yet is listed as `unchecked`, not
    omitted: "we have not looked" is a state the settings page has to show."""
    return mailbox_health.status(db, current_user.id)


@router.post("/deliverability/mailboxes/refresh")
def refresh_mailbox_health(db: Session = Depends(get_db),
                           current_user: User = Depends(get_current_user)) -> dict:
    """Recompute now instead of waiting for the four-hourly sweep."""
    enforce_rate_limit(str(current_user.id), "mailbox_health_refresh", "RATE_LIMIT_AI_ACTION")
    mailbox_health.refresh(db, current_user.id)
    return mailbox_health.status(db, current_user.id)


@router.post("/deliverability/mailboxes/{mailbox_ref}/resume")
def resume_mailbox(mailbox_ref: str, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)) -> dict:
    """Un-pause a mailbox the health sweep paused.

    Deliberately a human decision and nothing else: a later refresh that
    happens to score higher never resumes sending on its own, for the same
    reason the bounce pause and the blacklist pause do not."""
    try:
        mailbox_health.resume(db, current_user.id, mailbox_ref,
                              actor_user_id=current_user.id)
    except LookupError:
        raise HTTPException(status_code=404, detail="mailbox not found")
    return mailbox_health.status(db, current_user.id)


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

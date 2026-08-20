"""M5 UI-support endpoints - small additions the frontend consumes.
Each is flagged in the M5 summary. No business logic duplicated: these
read existing state or delegate to existing engine/adapter code.

GET   /strategies                    - list (id, status, flow, product name)
GET   /strategies/{id}/document      - final strategy + GTM documents
PATCH /leads/{id}                    - manual kanban status transition,
                                       VALIDATED server-side (the UI's drag
                                       map mirrors, never replaces, this)
GET   /strategies/{id}/sequences     - list sequences with steps
GET   /integrations/status           - connection cards data (secrets MASKED)
POST  /integrations/{provider}/test  - health_check() for apollo|hunter|gmail
GET   /suppression                   - read-only suppression list
POST  /suppression                   - manual add (permanent by design)

NOTE: this router is included in app/main.py BEFORE strategies_router, so
its `/strategies` GET is the one actually served - every route here needed
its own owner check added directly (can't rely on strategies.py's checks
shadowing it, they don't run for these paths).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.db.base import get_db
from app.db.models import (
    GmailAccount,
    Lead,
    LeadStatus,
    Product,
    Sequence,
    Strategy,
    SuppressionEntry,
    User,
)

router = APIRouter(tags=["ui-support"])

# Same transition map the frontend mirrors (src/lib/api/leads.ts). The
# BACKEND is authoritative: a drag the UI shouldn't have offered still
# gets a 422 here.
_ALLOWED_TRANSITIONS: dict[LeadStatus, set[LeadStatus]] = {
    LeadStatus.SOURCED: {LeadStatus.DROPPED},
    LeadStatus.ENRICHED: {LeadStatus.DROPPED},
    LeadStatus.EMAIL_FOUND: {LeadStatus.DROPPED},
    LeadStatus.VERIFIED: {LeadStatus.FLAGGED, LeadStatus.DROPPED},
    LeadStatus.FLAGGED: {LeadStatus.VERIFIED, LeadStatus.DROPPED},
    LeadStatus.DROPPED: set(),
    LeadStatus.CONTACTED: {LeadStatus.REPLIED},
    LeadStatus.REPLIED: {LeadStatus.MEETING_BOOKED},
    LeadStatus.MEETING_BOOKED: set(),
}


def _owned_strategy(db: Session, strategy_id: uuid.UUID, current_user: User) -> Strategy:
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    product = db.get(Product, strategy.product_id)
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="strategy not found")
    return strategy


def _owned_lead(db: Session, lead_id: uuid.UUID, current_user: User) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="lead not found")
    strategy = db.get(Strategy, lead.strategy_id)
    product = db.get(Product, strategy.product_id) if strategy else None
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead


@router.get("/strategies")
def list_strategies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    rows = db.execute(
        select(Strategy, Product.name)
        .join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == current_user.id)
        .order_by(Strategy.created_at.desc())
    ).all()
    return [
        {
            "id": str(s.id),
            "product_id": str(s.product_id),
            "product_name": name,
            "flow_type": s.flow_type.value,
            "status": s.status.value,
            "campaign_state": s.campaign_state,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s, name in rows
    ]


@router.get("/strategies/{strategy_id}/document")
def strategy_document(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    strategy = _owned_strategy(db, strategy_id, current_user)
    return {
        "strategy_document": strategy.strategy_document,
        "gtm_document": strategy.gtm_document,
    }


class LeadPatch(BaseModel):
    status: LeadStatus


@router.patch("/leads/{lead_id}")
def patch_lead(
    lead_id: uuid.UUID,
    body: LeadPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    lead = _owned_lead(db, lead_id, current_user)
    if body.status is not lead.status and body.status not in \
            _ALLOWED_TRANSITIONS.get(lead.status, set()):
        raise HTTPException(
            status_code=422,
            detail=f"cannot move a lead from {lead.status.value} to "
                   f"{body.status.value}",
        )
    lead.status = body.status
    db.commit()
    return {"id": str(lead.id), "status": lead.status.value}


@router.get("/strategies/{strategy_id}/sequences")
def list_sequences(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    _owned_strategy(db, strategy_id, current_user)
    rows = db.execute(
        select(Sequence).where(Sequence.strategy_id == strategy_id)
        .order_by(Sequence.created_at)
    ).scalars().all()
    return [
        {
            "id": str(seq.id),
            "strategy_id": str(seq.strategy_id),
            "name": seq.name,
            "channel": seq.channel.value,
            "status": seq.status.value,
            "booking_url": seq.booking_url,
            "steps": [
                {
                    "step_no": st.step_no,
                    "template": st.template,
                    "variant": st.variant,
                    "delay_days": st.delay_days,
                    "channel": st.channel.value if st.channel else None,
                    "whatsapp_kind": st.whatsapp_kind.value
                    if st.whatsapp_kind else None,
                    "whatsapp_template_id": str(st.whatsapp_template_id)
                    if st.whatsapp_template_id else None,
                }
                for st in seq.steps
            ],
        }
        for seq in rows
    ]


def _mask(secret: str) -> str | None:
    if not secret:
        return None
    return f"{secret[:3]}...{secret[-2:]}" if len(secret) > 6 else "***"


@router.get("/integrations/status")
def integrations_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    account = db.execute(
        select(GmailAccount).where(GmailAccount.user_id == current_user.id)
    ).scalars().first()
    return {
        "gmail": {
            "connected": account is not None,
            "email": account.email_address if account else None,
            "healthy": None,  # populated by POST /integrations/gmail/test
        },
        "whatsapp": {
            "configured": bool(settings.whatsapp_access_token
                               and settings.whatsapp_phone_number_id),
            "phone_number_id": settings.whatsapp_phone_number_id or None,
            "webhook_ok": None,
        },
        "apollo": {"key_set": bool(settings.apollo_api_key),
                   "masked": _mask(settings.apollo_api_key)},
        "hunter": {"key_set": bool(settings.hunter_api_key),
                   "masked": _mask(settings.hunter_api_key)},
        "calendly": {"token_set": bool(settings.calendly_api_token)},
    }


@router.post("/integrations/{provider}/test")
def test_integration(
    provider: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    try:
        if provider == "apollo":
            from app.integrations.apollo import ApolloSource
            return {"healthy": ApolloSource().health_check()}
        if provider == "hunter":
            from app.integrations.hunter import HunterVerifier
            return {"healthy": HunterVerifier().health_check()}
        if provider == "whatsapp":
            from app.integrations.whatsapp import WhatsAppChannel
            return {"healthy": WhatsAppChannel(session=db).health_check()}
        if provider == "gmail":
            from app.integrations.gmail import GmailChannel, get_account
            account = get_account(db, current_user)
            return {"healthy": GmailChannel(account=account,
                                            session=db).health_check()}
    except Exception:
        return {"healthy": False}
    raise HTTPException(status_code=404, detail="unknown provider")


class SuppressionIn(BaseModel):
    email: str | None = None
    phone: str | None = None
    reason: str = "manual"


# Suppression list is intentionally GLOBAL, not per-user - a person who
# unsubscribed or was GDPR-deleted must never be re-contactable by ANY
# account on this deployment. No owner check here by design (unlike
# everything else in this file).
@router.get("/suppression")
def list_suppression(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    rows = db.execute(
        select(SuppressionEntry).order_by(SuppressionEntry.ts.desc())
    ).scalars().all()
    return {"entries": [
        {"email": r.email, "phone": r.phone, "reason": r.reason,
         "ts": r.ts.isoformat() if r.ts else None}
        for r in rows
    ]}


@router.post("/suppression", status_code=201)
def add_suppression(
    body: SuppressionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not body.email and not body.phone:
        raise HTTPException(status_code=422,
                            detail="email or phone is required")
    entry = SuppressionEntry(
        email=body.email.lower().strip() if body.email else None,
        phone=body.phone.strip() if body.phone else None,
        reason=f"manual_{body.reason}"[:200],
    )
    db.add(entry)
    db.commit()
    return {"ok": True,
            "note": "suppression entries are permanent by design - there "
                    "is no delete endpoint"}
"""Compliance and consent layer (Part 1, Feature 9).

GET  /compliance/consent                  the consent ledger for this account
GET  /leads/{lead_id}/consent             per-channel: may we contact them, why not
POST /leads/{lead_id}/consent/withdraw    "stop contacting me", every channel at once
GET  /compliance/requirements             what each region demands, per channel

New paths. `/compliance/audit` (FG9) is untouched: that answers "on what basis
did you send this?", one row per send. These answer "when did they tell you to
stop, and what did you do about it?".
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import User
from app.services import consent, crm_service

router = APIRouter(tags=["compliance"])


class WithdrawIn(BaseModel):
    #: Where the instruction came from. Recorded verbatim in the ledger — "a
    #: person asked on the phone" and "they clicked unsubscribe" are different
    #: facts and a regulator may care which.
    source: str = Field(default="manual", max_length=40)
    detail: str | None = Field(default=None, max_length=300)


@router.get("/compliance/requirements")
def compliance_requirements(
    region: str | None = Query(default=None, max_length=10),
    _current_user: User = Depends(get_current_user),
) -> dict:
    """What each regime demands, per channel — stated once, here, so the send
    path, the UI and the tests cannot drift apart about it."""
    regions = [region] if region else list(consent.REGIMES) + [None]
    return {
        "channels": list(consent.CHANNELS),
        "regions": [
            {"region": value, "regime": consent.regime_for(value),
             "channels": {channel: consent.requirements_for(value, channel)
                          for channel in consent.CHANNELS}}
            for value in regions
        ],
        "note": ("A record of what was checked and what was done. Not legal "
                 "advice."),
    }


@router.get("/compliance/consent")
def consent_ledger(
    lead_id: uuid.UUID | None = None,
    identifier: str | None = Query(default=None, max_length=320),
    kind: str | None = Query(default=None,
                             pattern="^(granted|withdrawn|suppressed|erased)$"),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Every change of consent, newest first.

    Searchable by `identifier` on purpose: when someone writes "I asked you to
    stop three months ago", the address is the only thing you have."""
    return consent.ledger(db, current_user.id, lead_id=lead_id, identifier=identifier,
                          kind=kind, limit=limit, offset=offset)


@router.get("/leads/{lead_id}/consent")
def lead_consent(lead_id: uuid.UUID, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)) -> dict:
    """Per channel: may we contact this person, and if not, why not.

    The one screen that answers "why is this prospect not being messaged?"
    without reading four tables."""
    lead = crm_service.owned_lead(db, lead_id, current_user)
    return consent.lead_status(db, lead)


@router.post("/leads/{lead_id}/consent/withdraw")
def withdraw_consent(lead_id: uuid.UUID, body: WithdrawIn,
                     db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)) -> dict:
    """"Stop contacting me", applied to the whole person at once.

    Email, phone, LinkedIn AND WhatsApp, in one act, with a ledger entry per
    channel plus one for the instruction itself. Idempotent: withdrawing twice
    adds no duplicate suppression rows."""
    enforce_rate_limit(str(current_user.id), "consent_withdraw", "RATE_LIMIT_CRM_WRITE")
    lead = crm_service.owned_lead(db, lead_id, current_user)
    result = consent.suppress_everywhere(db, lead, source=body.source,
                                         reason=f"withdrawn_{body.source}"[:200],
                                         actor=current_user, detail=body.detail)
    return {**result, **consent.lead_status(db, lead)}

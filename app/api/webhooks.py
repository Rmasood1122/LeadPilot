"""Webhooks — Calendly booking events (M3 Chunk 5).

invitee.created  -> lead meeting_booked, sequences stop, `booked` outcome
invitee.canceled -> lead back to replied, event recorded
Deliveries are signature-verified and idempotent (Calendly retries)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import (
    EnrollmentStatus,
    Lead,
    LeadStatus,
    Outcome,
    OutcomeEvent,
    ProcessedWebhook,
    Product,
    SequenceEnrollment,
    Strategy,
)
from app.integrations.calendly import (
    extract_event_id,
    tenant_id_from_payload,
    verify_webhook_signature,
)
from app.services import notifications
from app.services import sequence_engine as engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/calendly")
async def calendly_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    raw = await request.body()
    signature = request.headers.get("Calendly-Webhook-Signature")
    if not verify_webhook_signature(raw, signature):
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    payload = await request.json()
    event_id = extract_event_id(payload, raw)

    # Idempotency: record first, act once. A retried delivery hits the
    # unique (provider, event_id) constraint and is acknowledged as a dupe.
    db.add(ProcessedWebhook(provider="calendly", event_id=event_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"ok": True, "duplicate": True}

    event_type = payload.get("event")  # TODO: verify against current Calendly docs
    invitee = payload.get("payload") or {}
    email = (invitee.get("email") or "").lower().strip()
    if not email:
        return {"ok": True, "matched": False, "reason": "no invitee email"}

    # WHICH ACCOUNT does this booking belong to? A Calendly delivery carries no
    # tenant identity, so we put ours into the booking link as a UTM parameter
    # and read it back here (app/integrations/calendly.py::TENANT_TRACKING_PARAM).
    #
    # If it is absent or unparseable we QUARANTINE the booking: acknowledge the
    # delivery so Calendly stops retrying, log it loudly, and match nothing.
    # The alternative - falling back to the old global `Lead.email ==` lookup -
    # is precisely the cross-tenant bug this replaces: with two customers
    # prospecting the same person it would flip the wrong account's lead, stop
    # their sequences and write a booking into their learning loop. Never guess
    # a tenant.
    tenant_id = tenant_id_from_payload(payload)
    if tenant_id is None:
        logger.warning(
            "calendly booking for %s carried no usable tenant id (event=%s, "
            "id=%s) - quarantined, no lead matched. A link generated before "
            "tenant tagging, or an organically-found one.",
            email, event_type, event_id,
        )
        return {"ok": True, "matched": False, "reason": "no tenant id",
                "quarantined": True}

    lead = db.execute(
        select(Lead)
        .join(Strategy, Strategy.id == Lead.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .where(Lead.email == email, Product.user_id == tenant_id)
    ).scalars().first()
    if lead is None:
        return {"ok": True, "matched": False}

    if event_type == "invitee.created":
        lead.status = LeadStatus.MEETING_BOOKED
        db.add(Outcome(lead_id=lead.id, event=OutcomeEvent.BOOKED,
                       channel="calendly",
                       meta_json={"calendly_event": event_id}))
        db.commit()
        enrollments = db.execute(
            select(SequenceEnrollment).where(SequenceEnrollment.lead_id == lead.id)
        ).scalars().all()
        for e in enrollments:
            if e.status is not EnrollmentStatus.STOPPED:
                engine.stop_enrollment(db, e, reason="meeting_booked")

        # Push to the lead's owner. This handler is `async def`, so the
        # asyncio.run() convention used elsewhere would raise inside the
        # running loop - notifications.dispatch handles that and never raises,
        # so the booking stays recorded regardless.
        owner = notifications.owner_of_lead(db, lead)
        if owner is not None:
            notifications.dispatch(notifications.notify_meeting_booked(
                owner, lead.id,
                attendee_name=invitee.get("name") or lead.full_name,
            ))
        else:
            logger.warning("lead %s has no resolvable owner - no booking "
                           "notification", lead.id)
        return {"ok": True, "matched": True, "action": "booked"}

    if event_type == "invitee.canceled":
        lead.status = LeadStatus.REPLIED
        db.add(Outcome(lead_id=lead.id, event=OutcomeEvent.REPLIED,
                       channel="calendly",
                       meta_json={"calendly_event": event_id, "canceled": True}))
        db.commit()
        return {"ok": True, "matched": True, "action": "canceled"}

    return {"ok": True, "matched": True, "action": "ignored", "event": event_type}

"""WhatsApp Cloud API webhooks — Milestone 4, Chunk 1.

GET  /webhooks/whatsapp  — Meta's verification handshake (hub challenge).
POST /webhooks/whatsapp  — signed event deliveries:
    * message STATUS updates (sent/delivered/read/failed)
        -> update our Message row + write Outcome events
        -> "failed" also runs the bounce path (stop enrollments, rate check)
    * INBOUND user messages
        -> stored as InboundReply linked to the lead (matched by phone)
        -> Lead.whatsapp_last_inbound_at persisted NOW (this timestamp is
           what opens the 24h customer-service window in Chunk 3)
        -> STOP/opt-out style text is treated EXACTLY like an unsubscribe,
           immediately: suppression list + hard stop of all sequences.
           This rule ships in Chunk 1, not later.

Deliveries are signature-verified (X-Hub-Signature-256) and idempotent —
Meta retries deliveries, and one delivery can carry MANY events, so dedupe
is per event id, not per delivery.

Payload structure notes are marked `# TODO: verify against current
WhatsApp Cloud API docs` wherever not 100% certain.
"""

import hashlib
import hmac
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db.base import get_db
from app.db.models import (
    InboundReply,
    Lead,
    LeadStatus,
    Message,
    MessageStatus,
    Outcome,
    OutcomeEvent,
    ProcessedWebhook,
)
from app.integrations.whatsapp import META_STATUS_MAP, normalize_phone
from app.services import sequence_engine as engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])

# Deterministic opt-out detection for Chunk 1 (no LLM dependency in the
# webhook hot path). Chunk 3 adds full reply classification for everything
# that is NOT an opt-out; opt-outs must never wait for that.
_OPT_OUT_TERMS = {
    "stop", "unsubscribe", "opt out", "optout", "cancel",
    "remove me", "stop messaging me", "no more messages",
}


def _is_opt_out(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in _OPT_OUT_TERMS or any(
        t.startswith(term) for term in ("stop", "unsubscribe")
    )


# --------------------------------------------------------------------------
# Signature validation
# --------------------------------------------------------------------------


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """X-Hub-Signature-256: 'sha256=' + HMAC-SHA256(app_secret, raw_body).
    # TODO: verify against current WhatsApp Cloud API docs (header name +
    exact scheme). Constant-time compare; missing secret => reject all
    (fail-closed), never accept-all."""
    if not settings.whatsapp_app_secret:
        logger.error("WHATSAPP_APP_SECRET unset — rejecting webhook delivery")
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.whatsapp_app_secret.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature_header.removeprefix("sha256="), expected)


# --------------------------------------------------------------------------
# GET — verification handshake
# --------------------------------------------------------------------------


@router.get("/webhooks/whatsapp", response_class=PlainTextResponse)
def whatsapp_verify(
    # TODO: verify against current WhatsApp Cloud API docs (exact query
    # param names; Meta uses dotted names hub.mode / hub.verify_token /
    # hub.challenge, aliased here since dots aren't valid identifiers)
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> PlainTextResponse:
    if (
        hub_mode == "subscribe"
        and settings.whatsapp_webhook_verify_token
        and hmac.compare_digest(hub_verify_token or "", settings.whatsapp_webhook_verify_token)
    ):
        return PlainTextResponse(hub_challenge or "")
    raise HTTPException(status_code=403, detail="verification failed")


# --------------------------------------------------------------------------
# POST — event deliveries
# --------------------------------------------------------------------------


@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    raw = await request.body()
    if not verify_signature(raw, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    payload = await request.json()
    processed, duplicates = 0, 0

    # TODO: verify against current WhatsApp Cloud API docs (payload shape:
    # {"object": "whatsapp_business_account", "entry": [{"changes":
    # [{"field": "messages", "value": {"statuses": [...], "messages": [...],
    # "metadata": {"phone_number_id": ...}, "contacts": [...]}}]}]})
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            field = change.get("field")
            value = change.get("value") or {}

            # Template review verdicts arrive as their own change field.
            # TODO: verify against current WhatsApp docs (field name
            # 'message_template_status_update' and value keys: event,
            # message_template_id, message_template_name,
            # message_template_language, reason)
            if field == "message_template_status_update":
                if _claim_event(db, _template_event_id(value)):
                    _handle_template_status(db, value)
                    processed += 1
                else:
                    duplicates += 1
                continue

            phone_number_id = (value.get("metadata") or {}).get("phone_number_id")

            for status_ev in value.get("statuses") or []:
                if _claim_event(db, _status_event_id(status_ev)):
                    _handle_status(db, status_ev)
                    processed += 1
                else:
                    duplicates += 1

            for msg in value.get("messages") or []:
                if _claim_event(db, msg.get("id") or ""):
                    _handle_inbound(db, msg, phone_number_id)
                    processed += 1
                else:
                    duplicates += 1

    return {"ok": True, "processed": processed, "duplicates": duplicates}


def _status_event_id(status_ev: dict) -> str:
    """A message emits several status events under the SAME wamid, so the
    dedupe key must include the status value, else 'delivered' would be
    swallowed as a duplicate of 'sent'."""
    return f"{status_ev.get('id', '')}:{status_ev.get('status', '')}"


def _claim_event(db: Session, event_id: str) -> bool:
    """Insert-first idempotency (same pattern as the Calendly webhook):
    returns True exactly once per (provider, event_id)."""
    if not event_id or event_id.startswith(":"):
        return False
    db.add(ProcessedWebhook(provider="whatsapp", event_id=event_id))
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


# --------------------------------------------------------------------------
# Template review verdicts (Chunk 2)
# --------------------------------------------------------------------------


def _template_event_id(value: dict) -> str:
    """These events carry no delivery id, so the dedupe key is built from
    the template identity + verdict (a template can be re-reviewed after
    resubmission, so the meta id + event pair is the natural key)."""
    tid = value.get("message_template_id") or value.get("message_template_name") or ""
    return f"tmpl:{tid}:{value.get('event', '')}"


def _handle_template_status(db: Session, value: dict) -> None:
    from app.services import whatsapp_templates as tmpl_svc
    from app.db.models import WhatsAppTemplate

    meta_id = str(value.get("message_template_id") or "")
    name = value.get("message_template_name")
    language = value.get("message_template_language")
    event = value.get("event") or ""  # e.g. APPROVED / REJECTED
    reason = value.get("reason")

    query = select(WhatsAppTemplate)
    if meta_id:
        query = query.where(WhatsAppTemplate.meta_template_id == meta_id)
    elif name and language:
        query = query.where(WhatsAppTemplate.name == name,
                            WhatsAppTemplate.language == language)
    else:
        logger.info("template status event with no identity — ignored")
        return
    template = db.execute(
        query.order_by(WhatsAppTemplate.version.desc()).limit(1)
    ).scalars().first()
    if template is None:
        logger.info("template status event for unknown template %s — ignored",
                    meta_id or name)
        return
    tmpl_svc.apply_meta_status(db, template, meta_status=event, reason=reason,
                               meta_template_id=meta_id or None)


# --------------------------------------------------------------------------
# Status updates -> Message rows + outcomes
# --------------------------------------------------------------------------


def _handle_status(db: Session, status_ev: dict) -> None:
    wamid = status_ev.get("id")
    meta_status = (status_ev.get("status") or "").lower()
    # TODO: verify against current WhatsApp Cloud API docs (status values
    # and error object shape under statuses[].errors)
    message = db.execute(
        select(Message).where(Message.provider_message_id == wamid)
    ).scalars().first()
    if message is None:
        logger.info("whatsapp status for unknown wamid %s — ignored", wamid)
        return

    mapped = META_STATUS_MAP.get(meta_status)
    if mapped is not None and message.status is not MessageStatus.FAILED:
        message.status = mapped
    if meta_status == "failed":
        errors = status_ev.get("errors") or []
        message.error = "; ".join(
            str(e.get("title") or e.get("message") or e) for e in errors
        ) or "whatsapp delivery failed"

    lead = db.get(Lead, message.lead_id)

    if meta_status == "read" and lead is not None:
        db.add(Outcome(lead_id=lead.id, message_id=message.id,
                       event=OutcomeEvent.OPENED, channel="whatsapp",
                       meta_json={"channel": "whatsapp"}))
    db.commit()

    if meta_status == "failed" and lead is not None:
        # Undeliverable number == the WhatsApp analogue of a hard bounce:
        # reuse the M3 bounce path (bounce outcome, stop enrollments,
        # strategy bounce-rate check with its auto-pause threshold).
        engine.record_bounce(db, lead, message=message,
                             meta={"channel": "whatsapp", "wamid": wamid},
                             channel="whatsapp")


# --------------------------------------------------------------------------
# Inbound messages -> InboundReply + window timestamp (+ instant opt-out)
# --------------------------------------------------------------------------


def _inbound_text(msg: dict) -> str:
    """Extract a text body tolerantly. Non-text types (image, audio,
    button replies...) degrade to their type name so we still persist the
    event. # TODO: verify against current WhatsApp Cloud API docs
    (message type list and per-type payload shape)"""
    msg_type = msg.get("type")
    if msg_type == "text":
        return (msg.get("text") or {}).get("body") or ""
    if msg_type == "button":
        return (msg.get("button") or {}).get("text") or ""
    if msg_type == "interactive":
        interactive = msg.get("interactive") or {}
        reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
        return reply.get("title") or ""
    return f"[{msg_type or 'unknown'} message]"


def _handle_inbound(db: Session, msg: dict, phone_number_id: str | None) -> None:
    from_phone = normalize_phone(msg.get("from") or "")
    body = _inbound_text(msg)

    received_at = None
    ts = msg.get("timestamp")
    if ts:
        try:
            received_at = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except (ValueError, TypeError, OSError):
            received_at = None
    received_at = received_at or datetime.now(timezone.utc)

    # Match lead by phone (normalized digits vs stored value — stored
    # phones may contain '+'/spaces from enrichment).
    lead = None
    if from_phone:
        candidates = db.execute(
            select(Lead).where(Lead.phone.isnot(None))
        ).scalars().all()
        # NOTE: linear scan is acceptable at Chunk-1 scale; Chunk 3 adds a
        # normalized-phone column/index when window lookups make this hot.
        for c in candidates:
            if normalize_phone(c.phone or "") == from_phone:
                lead = c
                break

    reply_row = InboundReply(
        lead_id=lead.id if lead else None,
        account_ref=phone_number_id,
        channel="whatsapp",
        thread_ref=from_phone or None,
        from_address=from_phone or (msg.get("from") or "unknown"),
        subject=None,
        body=body,
        classification=None,  # set below by the classification flow
        received_at=received_at,
    )
    db.add(reply_row)

    if lead is not None:
        # THE window anchor — the 24h service-window check reads this live.
        lead.whatsapp_last_inbound_at = received_at
        if lead.status in (LeadStatus.CONTACTED, LeadStatus.VERIFIED):
            lead.status = LeadStatus.REPLIED
    db.commit()

    # Feature 2: classify what the human does next. After the commit, and off
    # this thread -- Meta retries a webhook that does not answer quickly, and
    # a retry here would mean a second copy of the same message.
    from app.workers import reply_tasks  # noqa: PLC0415

    reply_tasks.enqueue(reply_row.id)

    if lead is None:
        return

    from app.services import whatsapp_optin as optin_svc
    from app.db.models import OptInSource

    if _is_opt_out(body):
        # Opt-out ships in Chunk 1: exactly like an unsubscribe — instant
        # suppression (email AND phone) + hard stop of every sequence.
        # Chunk 2 adds the audit row FIRST (revoke_opt_in appends opted_out
        # + suppresses the phone), then unsubscribe_lead covers the email
        # side + stops non-WhatsApp sequences too.
        reply_row.classification = "unsubscribe_request"
        db.commit()
        optin_svc.revoke_opt_in(
            db, lead,
            source=OptInSource.INBOUND_MESSAGE,
            evidence=f"inbound STOP message {msg.get('id') or '(no id)'}",
        )
        engine.unsubscribe_lead(db, lead, source="whatsapp_stop",
                                channel="whatsapp")
        logger.info("whatsapp opt-out processed for lead %s", lead.id)
    else:
        # They messaged US: if their consent status was unknown, that
        # inbound message IS an opt-in event (they initiated contact).
        # Explicit opted_out is never silently upgraded — the service
        # refuses, a human reviews that conversation.
        optin_svc.record_inbound_initiation(db, lead, wamid=msg.get("id"))
        # M4 Chunk 3: same Claude classification + UNIFIED stop rules as
        # email replies — a WhatsApp reply stops pending email steps too.
        # (This writes the REPLIED outcome with channel='whatsapp'.)
        from app.workers.outreach_tasks import route_whatsapp_inbound_impl
        route_whatsapp_inbound_impl(db, lead, reply_row)

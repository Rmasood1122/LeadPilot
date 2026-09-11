"""Feature Group 6 API — AI calls, phone consent, provider webhooks.

  GET    /strategies/{id}/calls         the campaign's Calls tab
  GET    /leads/{id}/calls              the lead's calls
  GET    /calls/{id}                    one call, with transcript + analysis
  POST   /leads/{id}/call               "Call now" (same gates as a sequence call)
  PUT    /leads/{id}/phone-consent      record consent (source + evidence)
  DELETE /leads/{id}/phone-consent      revoke it
  POST   /webhooks/vapi                 PUBLIC: status + end-of-call reports
  POST   /webhooks/elevenlabs           PUBLIC: post-call transcription

WEBHOOK AUTHENTICATION (fail closed -- no secret configured, no delivery accepted)
  vapi        `x-vapi-secret` (the serverUrlSecret we set on every call) or
              X-LeadPilot-Signature: sha256=HMAC(secret, body), against the
              `vapi.webhook_secret` credential
  elevenlabs  ElevenLabs-Signature: t=<ts>,v0=HMAC_SHA256(secret, "<ts>.<body>"),
              against `elevenlabs.webhook_secret`
"""

# NOTE: deliberately NO `from __future__ import annotations` (FastAPI).

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.leads import _owned_lead, _owned_strategy
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import Call, CallOutcome, CrmActivityKind, Lead, ProcessedWebhook, Strategy, User
from app.services import credentials, crm_events, phone_calls, system_settings
from app.workers import call_tasks

router = APIRouter(tags=["calls"])


class CallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lead_id: uuid.UUID
    provider: str
    to_number: str
    status: str
    outcome: CallOutcome | None
    duration_seconds: int | None
    recording_url: str | None
    voicemail_audio_url: str | None
    ended_reason: str | None
    analysis_json: dict | None
    error: str | None
    created_at: datetime
    ended_at: datetime | None
    lead_name: str | None = None


class CallDetail(CallOut):
    script_json: dict | None
    voicemail_text: str | None
    transcript: str | None


class ConsentIn(BaseModel):
    source: str = Field(min_length=3, max_length=200,
                        description="How consent was obtained, e.g. 'web form 2026-09-01'")


class CallNowIn(BaseModel):
    brief: str = Field(default="Introduce the offer and ask for a short meeting.",
                       max_length=2000)


def _with_names(db: Session, calls: list[Call]) -> list[CallOut]:
    out = []
    for call in calls:
        item = CallOut.model_validate(call)
        lead = db.get(Lead, call.lead_id)
        item.lead_name = (lead.full_name or lead.company) if lead else None
        out.append(item)
    return out


@router.get("/strategies/{strategy_id}/calls", response_model=list[CallOut])
def strategy_calls(strategy_id: uuid.UUID, limit: int = Query(default=100, ge=1, le=500),
                   db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)) -> list[CallOut]:
    _owned_strategy(db, strategy_id, current_user)
    rows = db.execute(select(Call).where(Call.strategy_id == strategy_id)
                      .order_by(Call.created_at.desc()).limit(limit)).scalars().all()
    return _with_names(db, list(rows))


@router.get("/leads/{lead_id}/calls", response_model=list[CallDetail])
def lead_calls(lead_id: uuid.UUID, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)) -> list:
    _owned_lead(db, lead_id, current_user)
    return list(db.execute(select(Call).where(Call.lead_id == lead_id)
                           .order_by(Call.created_at.desc())).scalars().all())


@router.get("/calls/{call_id}", response_model=CallDetail)
def get_call(call_id: uuid.UUID, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)) -> Call:
    call = db.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="call not found")
    try:
        _owned_lead(db, call.lead_id, current_user)
    except HTTPException:
        raise HTTPException(status_code=404, detail="call not found") from None
    return call


@router.put("/leads/{lead_id}/phone-consent")
def record_consent(lead_id: uuid.UUID, body: ConsentIn, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)) -> dict:
    lead = _owned_lead(db, lead_id, current_user)
    lead.phone_consent_at = datetime.now(timezone.utc)
    lead.phone_consent_source = body.source.strip()
    crm_events.record_activity(db, lead.id, CrmActivityKind.FIELD_CHANGED,
                               actor_user_id=current_user.id, to_value="phone consent recorded",
                               meta={"field": "phone_consent", "source": lead.phone_consent_source})
    db.commit()
    return {"phone_consent_at": lead.phone_consent_at, "phone_consent_source": lead.phone_consent_source}


@router.delete("/leads/{lead_id}/phone-consent", status_code=204)
def revoke_consent(lead_id: uuid.UUID, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)) -> None:
    lead = _owned_lead(db, lead_id, current_user)
    lead.phone_consent_at = None
    lead.phone_consent_source = None
    crm_events.record_activity(db, lead.id, CrmActivityKind.FIELD_CHANGED,
                               actor_user_id=current_user.id, to_value="phone consent revoked",
                               meta={"field": "phone_consent"})
    db.commit()


@router.post("/leads/{lead_id}/call", response_model=CallDetail, status_code=201)
def call_now(lead_id: uuid.UUID, body: CallNowIn, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)) -> Call:
    """Place one AI call now -- through every gate a sequence call passes
    except the send window (the user is pressing the button, on purpose)."""
    enforce_rate_limit(str(current_user.id), "ai_action", "RATE_LIMIT_AI_ACTION")
    lead = _owned_lead(db, lead_id, current_user)
    from app.integrations import voice_providers  # noqa: PLC0415
    from app.integrations.outreach_base import OutboundMessage  # noqa: PLC0415
    from app.integrations.phone_channel import PhoneChannel  # noqa: PLC0415
    from app.workers.lead_tasks import is_suppressed  # noqa: PLC0415

    if not system_settings.get(db, "phone_calling_enabled"):
        raise HTTPException(status_code=409, detail="AI calling is disabled by the administrator")
    if not phone_calls.e164(lead.phone):
        raise HTTPException(status_code=422, detail="this lead has no dialable phone number")
    if is_suppressed(db, lead.email, lead.phone, linkedin=lead.linkedin_url):
        raise HTTPException(status_code=409, detail="this contact is on the suppression list")
    if not phone_calls.consent_ok(db, lead):
        raise HTTPException(status_code=409,
                            detail="no phone consent recorded for this lead -- record it first")
    vapi, eleven = voice_providers.get_clients(db, current_user.id)
    if vapi is None and not (eleven is not None and eleven.can_call):
        raise HTTPException(status_code=503, detail="no AI voice provider is configured")
    if not phone_calls.reserve_call_slot(db, current_user.id):
        raise HTTPException(status_code=429, detail="daily AI call limit reached")

    strategy = db.get(Strategy, lead.strategy_id)
    try:
        call, meta = phone_calls.prepare_call(db, strategy, lead, body.brief,
                                              owner_id=current_user.id)
        db.commit()
        result = PhoneChannel(session=db, vapi=vapi, eleven=eleven).send(OutboundMessage(
            message_id=str(uuid.uuid4()), lead_id=str(lead.id), to_address=call.to_number,
            body=call.script_json["first_message"], metadata=meta))
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        phone_calls.release_call_slot(current_user.id)
        raise HTTPException(status_code=502, detail=f"the call could not be placed: {exc}") from exc
    if not result.ok:
        phone_calls.mark_send_failed(db, call, result.error or "call failed", current_user.id)
        raise HTTPException(status_code=502, detail=f"the call could not be placed: {result.error}")
    call.provider_call_id = result.provider_message_id
    call.provider = (result.raw or {}).get("provider") or call.provider
    call.status = "ringing"
    db.commit()
    return call


# ---------------------------------------------------------------------------
# Provider webhooks
# ---------------------------------------------------------------------------


def _hmac_ok(secret: str, raw: bytes, header: str | None) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header.removeprefix("sha256="), expected)


def verify_vapi(raw: bytes, headers, secret: str | None) -> bool:
    if not secret:
        return False
    static = headers.get("x-vapi-secret")
    if static:
        return hmac.compare_digest(static, secret)
    return _hmac_ok(secret, raw, headers.get("X-LeadPilot-Signature"))


def verify_elevenlabs(raw: bytes, header: str | None, secret: str | None) -> bool:
    if not secret or not header:
        return False
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts, given = parts["t"], parts["v0"]
    except (ValueError, KeyError):
        return False
    expected = hmac.new(secret.encode(), f"{ts}.{raw.decode()}".encode(),
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, given)


def _dedupe(db: Session, provider: str, event_id: str) -> bool:
    db.add(ProcessedWebhook(provider=provider, event_id=event_id[:200]))
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


_VAPI_STATUS = {"queued": "queued", "ringing": "ringing", "in-progress": "in_progress",
                "forwarding": "in_progress", "ended": "ended"}


@router.post("/webhooks/vapi")
async def vapi_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    """# TODO: verify against current Vapi docs (server message shapes)"""
    raw = await request.body()
    if not verify_vapi(raw, request.headers, credentials.get_secret(db, "vapi", "webhook_secret")):
        raise HTTPException(status_code=401, detail="invalid webhook signature")
    payload = json.loads(raw or b"{}")
    msg = payload.get("message") or payload
    kind = msg.get("type")
    call_obj = msg.get("call") or {}
    call = db.execute(select(Call).where(Call.provider_call_id == call_obj.get("id"))
                      ).scalar_one_or_none() if call_obj.get("id") else None
    if call is None:
        return {"ok": True, "matched": False}

    if kind == "status-update":
        call.status = _VAPI_STATUS.get(str(msg.get("status")), call.status)
        db.commit()
        return {"ok": True, "status": call.status}

    if kind == "end-of-call-report":
        if not _dedupe(db, "vapi", f"eoc:{call_obj['id']}"):
            return {"ok": True, "duplicate": True}
        artifact = msg.get("artifact") or {}
        started, ended = _parse_ts(msg.get("startedAt")), _parse_ts(msg.get("endedAt"))
        duration = msg.get("durationSeconds")
        if duration is None and started and ended:
            duration = int((ended - started).total_seconds())
        needs_analysis = phone_calls.record_end_of_call(
            db, call, ended_reason=msg.get("endedReason"),
            transcript=msg.get("transcript") or artifact.get("transcript"),
            recording_url=msg.get("recordingUrl") or artifact.get("recordingUrl"),
            duration_seconds=int(duration) if duration is not None else None,
            started_at=started, ended_at=ended)
        if needs_analysis:
            call_tasks.enqueue_analysis(call.id)
        return {"ok": True, "outcome": call.outcome.value if call.outcome else None,
                "analysis_queued": needs_analysis}

    return {"ok": True, "action": "ignored", "type": kind}


@router.post("/webhooks/elevenlabs")
async def elevenlabs_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    """# TODO: verify against current ElevenLabs docs (post_call_transcription)"""
    raw = await request.body()
    if not verify_elevenlabs(raw, request.headers.get("ElevenLabs-Signature"),
                             credentials.get_secret(db, "elevenlabs", "webhook_secret")):
        raise HTTPException(status_code=401, detail="invalid webhook signature")
    payload = json.loads(raw or b"{}")
    data = payload.get("data") or {}
    conversation_id = data.get("conversation_id")
    call = db.execute(select(Call).where(Call.provider == "elevenlabs",
                                         Call.provider_call_id == conversation_id)
                      ).scalar_one_or_none() if conversation_id else None
    if call is None:
        return {"ok": True, "matched": False}
    if not _dedupe(db, "elevenlabs", f"eoc:{conversation_id}"):
        return {"ok": True, "duplicate": True}
    turns = data.get("transcript") or []
    transcript = "\n".join(f"{t.get('role', '?')}: {t.get('message', '')}"
                           for t in turns if isinstance(t, dict))
    meta = data.get("metadata") or {}
    needs_analysis = phone_calls.record_end_of_call(
        db, call, ended_reason=str(meta.get("termination_reason") or data.get("status") or ""),
        transcript=transcript, recording_url=None,
        duration_seconds=meta.get("call_duration_secs"))
    if needs_analysis:
        call_tasks.enqueue_analysis(call.id)
    return {"ok": True, "analysis_queued": needs_analysis}

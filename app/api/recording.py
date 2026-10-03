"""Feature 3 — recording bots and the recording provider's webhook.

POST /meetings/{id}/recording-bot   send a Recall.ai bot to record + transcribe
POST /webhooks/recall               transcript.done / transcript.failed

The webhook authenticates with Recall's Svix signature against the admin's
`recall.webhook_secret` (Admin > Integrations). WITH NO SECRET SET IT IS CLOSED
(503), the same stance as POST /meetings/{id}/transcript: a transcript is the
verbatim contents of a private call. See app/services/meeting_recording.py.
"""

# No `from __future__ import annotations` -- see the note in app/api/crm.py.

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.meetings import _owned_meeting
from app.core.logging import get_logger
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import MeetingStatus, ProcessedWebhook, User
from app.integrations import recall
from app.integrations.plumbing import CircuitOpenError, ExternalAPIError
from app.services import credentials, meeting_recording

logger = get_logger("api.recording")

router = APIRouter(tags=["recording"])


def _status_out(meeting) -> dict:
    return {
        "meeting_id": str(meeting.id),
        "recording": bool(meeting.recording_bot_id),
        "transcript_status": meeting.transcript_status,
        "transcript_deadline_at": (meeting.transcript_deadline_at.isoformat()
                                   if meeting.transcript_deadline_at else None),
        "summary_source": meeting.summary_source,
    }


@router.post("/meetings/{meeting_id}/recording-bot")
def start_recording_bot(
    meeting_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Send a recording bot to this meeting. Calling it again is a no-op."""
    enforce_rate_limit(str(current_user.id), "calendar_write", "RATE_LIMIT_CALENDAR_WRITE")

    meeting = _owned_meeting(db, meeting_id, current_user)
    if meeting.status in (MeetingStatus.COMPLETED, MeetingStatus.CANCELLED):
        raise HTTPException(status_code=409,
                            detail="this meeting is over; there is nothing left to record")
    try:
        meeting_recording.start_bot(db, meeting)
    except credentials.IntegrationNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except recall.RecallNotConfigured as exc:
        raise HTTPException(status_code=503,
                            detail="Recall.ai is misconfigured -- check its region "
                                   "under Admin > Integrations") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ExternalAPIError, CircuitOpenError) as exc:
        logger.warning("recording.bot_create_failed", meeting_id=str(meeting.id), error=str(exc))
        raise HTTPException(status_code=502,
                            detail="the recording provider could not start a bot -- "
                                   "try again, or take notes and summarise from them") from exc
    return _status_out(meeting)


@router.get("/meetings/{meeting_id}/recording-bot")
def recording_status(
    meeting_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    return _status_out(_owned_meeting(db, meeting_id, current_user))


@router.post("/webhooks/recall")
async def recall_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    secret = credentials.get_secret(db, recall.PROVIDER, "webhook_secret")
    if not secret:
        raise HTTPException(status_code=503,
                            detail="Recall webhooks are disabled -- set recall.webhook_secret "
                                   "under Admin > Integrations")
    raw = await request.body()
    if not recall.verify_webhook(raw, request.headers, secret):
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    msg_id = request.headers.get("webhook-id") or request.headers.get("svix-id") or ""
    # Record first, act once: a redelivery hits UNIQUE (provider, event_id).
    db.add(ProcessedWebhook(provider=recall.PROVIDER, event_id=msg_id[:200]))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"ok": True, "duplicate": True}

    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="malformed payload") from exc
    result = meeting_recording.handle_event(db, payload if isinstance(payload, dict) else {})
    # `event` is structlog's positional message argument -- the provider's
    # event name travels as recall_event.
    logger.info("recording.webhook", recall_event=str((payload or {}).get("event")),
                result=result)
    return {"ok": True, "result": result}

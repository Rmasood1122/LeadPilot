"""Meeting transcripts from a recording provider, feeding the AI summary (Feature 3).

FEATURES.md used to say "nothing calls the transcript endpoint yet". This is the
missing client: a Recall.ai bot records the call, Recall's webhook says the
transcript is ready, and the transcript is pulled in and summarised together
with the user's live notes -- never instead of them.

THE SUMMARY NEVER WAITS FOR THE TRANSCRIPT
Ending a meeting queues the summary immediately, exactly as before, from
whatever exists (usually just the notes; summary_source = "notes"). If a bot is
recording, the meeting also gets a transcript_deadline_at. A transcript that
arrives -- before the deadline or after -- replaces the notes-only summary with
one built from transcript + notes (summary_source = "transcript"); the
action-item merge keeps ticked boxes ticked. A transcript that never arrives
leaves the notes-only summary in place, and the sweep marks the wait timed_out
so the UI can say so instead of spinning forever.

TENANCY
A webhook is matched to a meeting ONLY by meetings.recording_bot_id, a unique
column this service wrote when it created the bot. The bot's metadata.meeting_id
is a cross-check, never a lookup key: a payload that names a different meeting
than the bot we recorded is refused rather than guessed at. Same rule as the
Calendly quarantine -- never guess a tenant.

IDEMPOTENCY
  * one bot per meeting: a conditional UPDATE claims the meeting before the
    provider is called, so a double click cannot start two bots;
  * one processing per delivery: processed_webhooks (provider, webhook-id);
  * one transcript per meeting: a meeting already `received` ignores repeats.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Meeting, MeetingStatus
from app.services import system_settings

logger = logging.getLogger(__name__)

REQUESTING = "requesting"
PENDING = "pending"
RECEIVED = "received"
FAILED = "failed"
TIMED_OUT = "timed_out"

TRANSCRIPT_EVENTS = ("transcript.done", "transcript.failed")

# Same ceiling as the chunk endpoint (app/api/meetings.py).
MAX_TRANSCRIPT_CHARS = 250_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def wait_minutes(db: Session) -> int:
    return int(system_settings.get(db, "meeting_transcript_wait_minutes"))


# --------------------------------------------------------------------------
# Starting a bot
# --------------------------------------------------------------------------


def start_bot(db: Session, meeting: Meeting, *, client=None) -> Meeting:
    """Send a recording bot to the meeting. Idempotent per meeting.

    Raises ValueError (no join URL), credentials.IntegrationNotConfigured, or
    the adapter's ExternalAPIError/CircuitOpenError -- the router turns each
    into a clear status. On any failure the claim is released, so the user can
    try again.
    """
    if meeting.recording_bot_id:
        return meeting
    if not meeting.meeting_url:
        raise ValueError("this meeting has no join URL to send a recording bot to")

    claimed = db.execute(
        update(Meeting)
        .where(Meeting.id == meeting.id, Meeting.recording_bot_id.is_(None),
               Meeting.transcript_status.is_(None))
        .values(transcript_status=REQUESTING)
        .execution_options(synchronize_session="fetch")
    ).rowcount
    db.commit()
    if claimed != 1:
        db.refresh(meeting)
        return meeting

    try:
        if client is None:
            from app.integrations import recall  # noqa: PLC0415

            client = recall.client_for(db)
        bot = client.create_bot(
            meeting.meeting_url,
            join_at=_aware(meeting.start_at),
            metadata={"meeting_id": str(meeting.id)},
        )
        bot_id = str(bot.get("id") or "").strip()
        if not bot_id:
            raise ValueError("the recording provider returned no bot id")
    except Exception:
        meeting.transcript_status = None
        db.commit()
        raise

    meeting.recording_bot_id = bot_id[:100]
    meeting.transcript_status = PENDING
    db.commit()
    logger.info("recording bot %s started for meeting %s", bot_id, meeting.id)
    return meeting


def set_deadline(db: Session, meeting: Meeting, now: datetime) -> None:
    """Start the transcript wait when a recorded meeting ends. Called by /end;
    does not commit and never blocks the summary."""
    if meeting.transcript_status == PENDING and meeting.transcript_deadline_at is None:
        meeting.transcript_deadline_at = now + timedelta(minutes=wait_minutes(db))


# --------------------------------------------------------------------------
# Webhook events
# --------------------------------------------------------------------------


def handle_event(db: Session, payload: dict, *, enqueue=None) -> str:
    """Route one verified, de-duplicated Recall delivery. Returns what happened."""
    event = str(payload.get("event") or "")
    if event not in TRANSCRIPT_EVENTS:
        return "ignored"
    data = payload.get("data") or {}
    bot = data.get("bot") or {}
    bot_id = str(bot.get("id") or "").strip()
    if not bot_id:
        return "no_bot_id"

    meeting = db.execute(
        select(Meeting).where(Meeting.recording_bot_id == bot_id)
    ).scalar_one_or_none()
    if meeting is None:
        # Acknowledged so the provider stops retrying; matched to nothing.
        logger.warning("recall webhook for unknown bot %s quarantined", bot_id)
        return "unknown_bot"
    claimed_meeting = str((bot.get("metadata") or {}).get("meeting_id") or "")
    if claimed_meeting and claimed_meeting != str(meeting.id):
        logger.error("recall webhook for bot %s names meeting %s but the bot belongs "
                     "to meeting %s -- refused", bot_id, claimed_meeting, meeting.id)
        return "metadata_mismatch"

    if event == "transcript.failed":
        if meeting.transcript_status in (PENDING, TIMED_OUT):
            meeting.transcript_status = FAILED
            db.commit()
        return "failed"

    if meeting.transcript_status == RECEIVED:
        return "already_received"
    transcript_id = str((data.get("transcript") or {}).get("id") or "") or None
    if enqueue is None:
        from app.workers.calendar_tasks import fetch_meeting_transcript  # noqa: PLC0415

        def enqueue(meeting_id, tid):
            fetch_meeting_transcript.delay(str(meeting_id), tid)
    enqueue(meeting.id, transcript_id)
    return "queued"


# --------------------------------------------------------------------------
# Fetching the transcript
# --------------------------------------------------------------------------


def fetch_transcript(db: Session, meeting_id: uuid.UUID, transcript_id: str | None = None,
                     *, client=None, summarise=None) -> str:
    """Pull the finished transcript into the meeting and upgrade its summary.

    The provider's transcript REPLACES any chunk-streamed text: both describe
    the same call, and concatenating them would feed the summary every
    sentence twice.
    """
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        return "missing"
    if meeting.transcript_status == RECEIVED:
        return "already_received"
    if not meeting.recording_bot_id:
        return "no_bot"

    if client is None:
        from app.integrations import recall  # noqa: PLC0415

        client = recall.client_for(db)
    text = client.fetch_transcript_text(meeting.recording_bot_id, transcript_id)
    if not text.strip():
        meeting.transcript_status = FAILED
        db.commit()
        return "empty"

    meeting.transcript = text[:MAX_TRANSCRIPT_CHARS]
    meeting.transcript_status = RECEIVED
    db.commit()

    if meeting.status is MeetingStatus.COMPLETED:
        if summarise is None:
            from app.workers.calendar_tasks import generate_summary_impl  # noqa: PLC0415

            summarise = generate_summary_impl
        result = summarise(db, meeting.id)
        return f"received_summarised:{result}"
    # Still in progress (the transcript beat End): /end will summarise it.
    return "received"


def expire_waits(db: Session, now: datetime | None = None) -> int:
    """Mark transcript waits past their deadline as timed_out.

    Nothing else to do: the notes-only summary was generated when the meeting
    ended. A transcript that arrives later is still accepted and still
    upgrades the summary.
    """
    now = now or _now()
    rows = db.execute(
        select(Meeting).where(Meeting.transcript_status == PENDING,
                              Meeting.transcript_deadline_at.isnot(None),
                              Meeting.transcript_deadline_at < now)
    ).scalars().all()
    for meeting in rows:
        meeting.transcript_status = TIMED_OUT
    db.commit()
    return len(rows)

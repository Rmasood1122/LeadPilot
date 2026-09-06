"""Engagement Hub, Feature 3 — the meeting API.

Same conventions as app/api/calendar.py: `Depends(get_current_user)` on every
route, ownership answered as 404 rather than 403, and `enforce_rate_limit` as
the handler's first statement rather than a route dependency.

THE ONE EXCEPTION IS POST /meetings/{id}/transcript
It is a webhook, not a user action: the caller is a browser extension or a
recording provider (Recall.ai and friends), neither of which can hold a user's
JWT. It authenticates by HMAC-SHA256 over the raw request body using
MEETING_RECORDING_WEBHOOK_SECRET -- the same scheme
app/integrations/calendly.py::verify_webhook_signature and the WhatsApp
webhook already use, with the same constant-time comparison.

WITH NO SECRET SET, THAT ENDPOINT IS CLOSED (503), not open. A transcript is
the most sensitive thing this feature stores -- the verbatim contents of a
private sales call -- and an unauthenticated write path to it that appears by
default the moment the feature ships is not a trade-off worth making. An
operator who wants transcript ingestion sets the variable.

WHY PLATFORM CREATION FAILS SOFT
POST /meetings with platform=google_meet asks Google for a Calendar event. If
Google says no (scope not granted, account not connected, API down), the
meeting is still created -- with no join URL and a `platform_error` in the
response. The alternative is refusing to record a meeting the user has
actually scheduled because a third party was unavailable, and then having no
row to attach their notes to when the call happens anyway on a link they
pasted into Slack.
"""

# NOTE: deliberately NO `from __future__ import annotations` -- see the same
# note in app/api/crm.py and app/api/calendar.py.

import hashlib
import hmac
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.core.logging import get_logger
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import (
    BookingStatus,
    CalendarBooking,
    CalendarBookingPage,
    Meeting,
    MeetingParticipant,
    MeetingParticipantRole,
    MeetingPlatform,
    MeetingStatus,
    User,
)
from app.services import calendar_service as cal

logger = get_logger("api.meetings")

router = APIRouter(prefix="/meetings", tags=["meetings"])

_WRITE_LIMIT = "RATE_LIMIT_CALENDAR_WRITE"

SIGNATURE_HEADER = "X-LeadPilot-Signature"

# Cap on how much transcript one meeting may accumulate. Roughly 250k
# characters is several hours of speech; past that the far more likely
# explanation is a stuck streaming client appending the same chunk forever,
# and an unbounded Text column filled by an unauthenticated-shaped endpoint is
# a disk-space incident waiting to happen.
MAX_TRANSCRIPT_CHARS = 250_000


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class MeetingCreateIn(BaseModel):
    """Either from a booking, or standalone.

    booking_id fills start/end/title/lead from the booking. Without it,
    start_at and end_at are required -- a meeting with no time is not a
    meeting, and defaulting it to "now" would put a fictional call on the
    user's calendar.
    """

    booking_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    platform: MeetingPlatform = MeetingPlatform.CUSTOM
    title: str | None = Field(default=None, max_length=200)
    meeting_url: str | None = Field(default=None, max_length=1000)
    start_at: datetime | None = None
    end_at: datetime | None = None

    @field_validator("end_at")
    @classmethod
    def _after_start(cls, value, info):
        start = info.data.get("start_at")
        if value is not None and start is not None and value <= start:
            raise ValueError("end_at must be after start_at")
        return value


class ParticipantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str | None
    email: str | None
    role: MeetingParticipantRole
    joined_at: datetime | None
    left_at: datetime | None


class MeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID | None
    lead_id: uuid.UUID | None
    platform: MeetingPlatform
    title: str | None
    meeting_url: str | None
    start_at: datetime
    end_at: datetime
    actual_start_at: datetime | None
    actual_end_at: datetime | None
    status: MeetingStatus
    summary: str | None
    sentiment: str | None
    action_items: list | None
    key_points: list | None
    next_steps: list | None
    recording_url: str | None


class MeetingDetailOut(MeetingOut):
    """Everything, including the two big Text columns.

    A separate model from MeetingOut on purpose: the list endpoint must not
    ship a transcript per row. At a few thousand characters each that is
    megabytes of response for a screen that renders titles and times.
    """

    raw_notes: str | None
    ai_notes: str | None
    transcript: str | None
    participants: list[ParticipantOut]


class MeetingCreateOut(MeetingDetailOut):
    # Present and non-null only when a platform integration was asked for and
    # declined. See the module docstring for why this is a field and not a
    # failed request.
    platform_error: str | None = None


class NotesIn(BaseModel):
    raw_notes: str = Field(default="", max_length=100_000)


class TranscriptChunkIn(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    speaker: str | None = Field(default=None, max_length=120)
    recording_url: str | None = Field(default=None, max_length=2000)


class ActionItemsIn(BaseModel):
    """The checkbox list writing back.

    Sent as the whole list rather than a per-item PATCH, because the list is
    what the user sees and edits as one thing, and there is no stable item id
    to address (see calendar_tasks._merge_action_items for why there is not).
    """

    action_items: list[dict] = Field(default_factory=list, max_length=50)


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------


def _owned_meeting(db: Session, meeting_id: uuid.UUID,
                   current_user: User) -> Meeting:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None or meeting.host_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="meeting not found")
    return meeting


def _aware(value):
    """UTC-aware view of a timestamptz column. See outreach_tasks._aware."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _detail(meeting: Meeting) -> dict:
    data = MeetingDetailOut.model_validate(meeting).model_dump()
    return data


# ---------------------------------------------------------------------------
# Create / read
# ---------------------------------------------------------------------------


@router.post("", response_model=MeetingCreateOut, status_code=201)
def create_meeting(
    payload: MeetingCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    enforce_rate_limit(str(current_user.id), "calendar_write", _WRITE_LIMIT)

    booking = None
    if payload.booking_id is not None:
        booking = cal.owned_booking(db, payload.booking_id, current_user)
        if booking.status is BookingStatus.CANCELLED:
            raise HTTPException(
                status_code=409,
                detail="that booking is cancelled — book a new slot first",
            )

    start_at = payload.start_at or (_aware(booking.start_at) if booking else None)
    end_at = payload.end_at or (_aware(booking.end_at) if booking else None)
    if start_at is None or end_at is None:
        raise HTTPException(
            status_code=422,
            detail="start_at and end_at are required when no booking_id is given",
        )
    if end_at <= start_at:
        raise HTTPException(status_code=422,
                            detail="end_at must be after start_at")

    lead_id = payload.lead_id or (booking.lead_id if booking else None)
    title = payload.title or _title_for(db, booking)

    meeting = Meeting(
        booking_id=booking.id if booking else None,
        host_user_id=current_user.id,
        lead_id=lead_id,
        platform=payload.platform,
        title=title,
        meeting_url=payload.meeting_url,
        start_at=start_at,
        end_at=end_at,
        status=MeetingStatus.SCHEDULED,
    )

    platform_error = None
    if not meeting.meeting_url:
        meeting.meeting_url, meeting.external_event_id, platform_error = (
            _provision_link(db, current_user, meeting, booking)
        )

    db.add(meeting)
    db.flush()
    _seed_participants(db, meeting, current_user, booking)

    if booking is not None and meeting.meeting_url and not booking.meeting_link:
        # Put the join URL on the booking too, so the confirmation the invitee
        # already has and the one a re-send would produce agree.
        booking.meeting_link = meeting.meeting_url[:500]
    db.commit()

    return {**_detail(meeting), "platform_error": platform_error}


def _title_for(db: Session, booking: CalendarBooking | None) -> str:
    if booking is None:
        return "Meeting"
    page = db.get(CalendarBookingPage, booking.booking_page_id)
    name = booking.invitee_name or booking.invitee_email
    return f"{page.title} — {name}"[:200] if page else f"Meeting — {name}"[:200]


def _seed_participants(db: Session, meeting: Meeting, host: User,
                       booking: CalendarBooking | None) -> None:
    """The host, plus the invitee when the meeting came from a booking.

    Written at creation rather than at join time because the participant list
    is also the answer to "who is this call with?" on a screen shown before
    anybody joins.
    """
    db.add(MeetingParticipant(
        meeting_id=meeting.id, email=getattr(host, "email", None),
        role=MeetingParticipantRole.HOST,
    ))
    if booking is not None:
        db.add(MeetingParticipant(
            meeting_id=meeting.id, name=booking.invitee_name,
            email=booking.invitee_email, role=MeetingParticipantRole.CLIENT,
        ))


def _provision_link(db: Session, user: User, meeting: Meeting,
                    booking: CalendarBooking | None):
    """(join_url, external_event_id, error). Never raises — see the docstring.

    CUSTOM is not an error case: it means "the user will paste their own
    link", and asking a provider for one would be wrong.
    """
    attendees = [booking.invitee_email] if booking else []
    try:
        if meeting.platform is MeetingPlatform.GOOGLE_MEET:
            from app.integrations.google_meet import create_meet_event  # noqa: PLC0415

            result = create_meet_event(
                db, user, summary=meeting.title or "Meeting",
                start_at=meeting.start_at, end_at=meeting.end_at,
                attendee_emails=attendees,
            )
        elif meeting.platform is MeetingPlatform.ZOOM:
            from app.integrations.zoom import create_zoom_meeting  # noqa: PLC0415

            minutes = max(
                1,
                int((meeting.end_at - meeting.start_at).total_seconds() // 60),
            )
            result = create_zoom_meeting(
                topic=meeting.title or "Meeting", start_at=meeting.start_at,
                duration_minutes=minutes,
            )
        else:
            # TEAMS has no adapter yet, and CUSTOM never wants one. Both mean
            # the same thing here: the user supplies the URL.
            return None, None, None
    except Exception as exc:  # noqa: BLE001 — see the module docstring
        logger.warning("meetings.platform_link_failed",
                       platform=meeting.platform.value, error=str(exc))
        return None, None, f"{type(exc).__name__}: {exc}"

    return (result.get("join_url") or None,
            result.get("external_event_id") or None, None)


@router.get("", response_model=list[MeetingOut])
def list_meetings(
    status: MeetingStatus | None = None,
    lead_id: uuid.UUID | None = None,
    start_from: datetime | None = None,
    start_to: datetime | None = None,
    upcoming: bool | None = Query(
        default=None,
        description="true = start_at in the future; false = in the past",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Meeting]:
    query = select(Meeting).where(Meeting.host_user_id == current_user.id)
    if status is not None:
        query = query.where(Meeting.status == status)
    if lead_id is not None:
        query = query.where(Meeting.lead_id == lead_id)
    if start_from is not None:
        query = query.where(Meeting.start_at >= start_from)
    if start_to is not None:
        query = query.where(Meeting.start_at < start_to)
    if upcoming is not None:
        now = datetime.now(timezone.utc)
        # `end_at` rather than `start_at` for the upcoming test: a call that
        # started ten minutes ago and runs for an hour is still upcoming from
        # the user's point of view, and dropping it off the "upcoming" list
        # the moment it begins is how somebody loses the Join button.
        query = (query.where(Meeting.end_at >= now) if upcoming
                 else query.where(Meeting.end_at < now))
        query = query.order_by(Meeting.start_at.asc() if upcoming
                               else Meeting.start_at.desc())
    else:
        query = query.order_by(Meeting.start_at.desc())
    return db.execute(query.limit(limit)).scalars().all()


@router.get("/{meeting_id}", response_model=MeetingDetailOut)
def get_meeting(
    meeting_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Meeting:
    return _owned_meeting(db, meeting_id, current_user)


# ---------------------------------------------------------------------------
# The meeting itself: start, notes, end
# ---------------------------------------------------------------------------


@router.post("/{meeting_id}/start", response_model=MeetingDetailOut)
def start_meeting(
    meeting_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Meeting:
    """Mark in_progress and stamp actual_start_at. Idempotent.

    Pressing Start twice must not reset the timer -- the second press comes
    from a refreshed tab, and moving actual_start_at would shorten the
    recorded duration of a call that is still running.
    """
    enforce_rate_limit(str(current_user.id), "calendar_write", _WRITE_LIMIT)

    meeting = _owned_meeting(db, meeting_id, current_user)
    if meeting.status is MeetingStatus.COMPLETED:
        raise HTTPException(status_code=409,
                            detail="this meeting has already ended")
    if meeting.actual_start_at is None:
        meeting.actual_start_at = datetime.now(timezone.utc)
    meeting.status = MeetingStatus.IN_PROGRESS
    db.commit()
    return meeting


@router.put("/{meeting_id}/notes", response_model=MeetingDetailOut)
def update_notes(
    meeting_id: uuid.UUID,
    payload: NotesIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Meeting:
    """Replace the user's live notes. The autosave target.

    A full replace, not an append: the client owns a textarea and sends its
    contents. Appending would duplicate everything already typed on every
    10-second save.
    """
    enforce_rate_limit(str(current_user.id), "calendar_write", _WRITE_LIMIT)

    meeting = _owned_meeting(db, meeting_id, current_user)
    meeting.raw_notes = payload.raw_notes
    db.commit()
    return meeting


@router.post("/{meeting_id}/end", response_model=MeetingDetailOut)
def end_meeting(
    meeting_id: uuid.UUID,
    generate_summary: bool = Query(
        default=True, description="Queue the AI summary as a background task"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Meeting:
    """Mark completed, then queue the summary.

    The summary runs in the background rather than inline: it is a model call
    over a full transcript, and the user has just pressed End Meeting and
    stood up. Making them watch a spinner for it -- or worse, having the
    request time out and leave the meeting stuck in_progress -- is the wrong
    shape for the moment. The panel polls, and
    POST /{id}/generate-summary is there for "run it again, now".
    """
    enforce_rate_limit(str(current_user.id), "calendar_write", _WRITE_LIMIT)

    meeting = _owned_meeting(db, meeting_id, current_user)
    now = datetime.now(timezone.utc)
    if meeting.actual_start_at is None:
        # Ended without ever being started (the user took notes and closed the
        # tab). Recorded honestly rather than left NULL, so the duration the
        # summary prompt sees is a real number.
        meeting.actual_start_at = _aware(meeting.start_at) or now
    if meeting.actual_end_at is None:
        meeting.actual_end_at = now
    meeting.status = MeetingStatus.COMPLETED
    db.commit()

    if generate_summary:
        _enqueue_summary(meeting.id)
    return meeting


def _enqueue_summary(meeting_id: uuid.UUID) -> None:
    from app.workers.calendar_tasks import generate_meeting_summary  # noqa: PLC0415

    try:
        generate_meeting_summary.delay(str(meeting_id))
    except Exception as exc:  # noqa: BLE001
        # A broker outage must not un-end a meeting. The user can press
        # Generate summary again once the queue is back.
        logger.warning("meetings.summary_enqueue_failed",
                       meeting_id=str(meeting_id), error=str(exc))


# ---------------------------------------------------------------------------
# Transcript ingestion (HMAC, not JWT — see the module docstring)
# ---------------------------------------------------------------------------


def _verify_signature(raw_body: bytes, header: str | None) -> bool:
    """Constant-time HMAC-SHA256 over the raw body.

    Accepts both "sha256=<hex>" and a bare hex digest, because the two
    recording providers this is written against disagree about the prefix and
    neither is wrong.
    """
    secret = (settings.meeting_recording_webhook_secret or "").strip()
    if not secret or not header:
        return False
    given = header.strip()
    if given.startswith("sha256="):
        given = given[len("sha256="):]
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, given)


@router.post("/{meeting_id}/transcript")
async def append_transcript(
    meeting_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Append one transcript chunk. Authenticated by HMAC, NOT by JWT.

    503 when no secret is configured: with no secret there is no way to
    authenticate the caller, and the safe default for a write path into the
    verbatim contents of a private call is closed.
    """
    if not (settings.meeting_recording_webhook_secret or "").strip():
        raise HTTPException(
            status_code=503,
            detail="transcript ingestion is disabled — set "
                   "MEETING_RECORDING_WEBHOOK_SECRET to enable it",
        )

    raw = await request.body()
    if not _verify_signature(raw, request.headers.get(SIGNATURE_HEADER)):
        raise HTTPException(status_code=401, detail="invalid signature")

    payload = TranscriptChunkIn.model_validate_json(raw)
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        # 404 even though the caller is authenticated: the secret is
        # deployment-wide, so a valid signature says "a trusted integration",
        # not "an integration entitled to this meeting". There is nothing to
        # disclose about which meeting ids exist.
        raise HTTPException(status_code=404, detail="meeting not found")

    existing = meeting.transcript or ""
    if len(existing) >= MAX_TRANSCRIPT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"transcript has reached its {MAX_TRANSCRIPT_CHARS}-character "
                   f"limit for this meeting",
        )

    line = (f"{payload.speaker}: {payload.text}" if payload.speaker
            else payload.text)
    meeting.transcript = (f"{existing}\n{line}" if existing else line)
    if payload.recording_url and not meeting.recording_url:
        meeting.recording_url = payload.recording_url
    db.commit()
    return {"ok": True, "length": len(meeting.transcript)}


# ---------------------------------------------------------------------------
# Summary + action items
# ---------------------------------------------------------------------------


@router.post("/{meeting_id}/generate-summary", response_model=MeetingDetailOut)
def generate_summary_now(
    meeting_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Meeting:
    """Run the summary inline and return the updated meeting.

    Inline here, background on /end, deliberately: this endpoint exists
    because a human pressed "Generate summary" and is looking at a spinner
    they chose. Both call the same generate_summary_impl, so the two paths
    cannot produce different results.
    """
    enforce_rate_limit(str(current_user.id), "calendar_write", _WRITE_LIMIT)

    from app.workers.calendar_tasks import generate_summary_impl  # noqa: PLC0415

    meeting = _owned_meeting(db, meeting_id, current_user)
    if not (meeting.transcript or meeting.raw_notes):
        raise HTTPException(
            status_code=422,
            detail="there is nothing to summarise — this meeting has no "
                   "transcript and no notes",
        )
    result = generate_summary_impl(db, meeting.id)
    if not result.startswith("ok"):
        raise HTTPException(status_code=502,
                            detail=f"summary generation failed: {result}")
    db.refresh(meeting)
    return meeting


@router.get("/{meeting_id}/action-items")
def get_action_items(
    meeting_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """The parsed action items, as a structured list.

    Always a list, never null: the frontend renders it directly, and a null
    here would mean every consumer needs its own `?? []`.
    """
    meeting = _owned_meeting(db, meeting_id, current_user)
    items = meeting.action_items or []
    return {
        "meeting_id": str(meeting.id),
        "items": items,
        "open_count": sum(1 for i in items if not i.get("done")),
    }


@router.put("/{meeting_id}/action-items")
def save_action_items(
    meeting_id: uuid.UUID,
    payload: ActionItemsIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Write back the checkbox list (and any items the user typed).

    Normalised through the same cleaner the generator uses, so an item added
    by hand and an item extracted by the model have identical shape -- the UI
    should not be able to tell them apart, and neither should the CRM handler
    that turns them into tasks.
    """
    enforce_rate_limit(str(current_user.id), "calendar_write", _WRITE_LIMIT)

    from app.services.meeting_ai import _clean_action_items  # noqa: PLC0415

    meeting = _owned_meeting(db, meeting_id, current_user)
    meeting.action_items = _clean_action_items(payload.action_items, limit=50)
    db.commit()
    return {"meeting_id": str(meeting.id), "items": meeting.action_items}

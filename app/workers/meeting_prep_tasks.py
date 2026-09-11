"""Feature Group 7 Celery tasks — brief generation and pre-meeting reminders.

Both run on the `notifications` queue (see notification_tasks.py for why).

THE REMINDER SWEEP IS AT-MOST-ONCE
Beat runs send_meeting_reminders every five minutes. Each reminder is CLAIMED
with a conditional UPDATE (`... SET reminder_24h_sent_at = now WHERE id = :id
AND reminder_24h_sent_at IS NULL`) and only the worker whose UPDATE touched the
row sends it. Two overlapping sweeps, or a sweep retried after a crash, cannot
double-notify. The trade is deliberate: a crash between the claim and the send
loses that one reminder, and a missed reminder is better than a phone buzzing
twice for the same meeting.

WHICH REMINDER FIRES
  > 1h before the call and <= 24h before  -> the "coming up" reminder, once
  <= 1h before the call                     -> the 1-hour reminder carrying
                                               the opening-60-seconds script
A meeting booked 40 minutes out gets only the 1-hour reminder; its 24h slot is
claimed silently so a later sweep does not send a stale "tomorrow" message.
Nothing fires for a meeting that has already started.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.db.models import Lead, MeetingPrepBrief
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

REMINDER_24H = timedelta(hours=24)
REMINDER_1H = timedelta(hours=1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Requesting a brief (called from the booking hooks)
# ---------------------------------------------------------------------------


def request_prep(db: Session, lead: Lead, *, source: str,
                 external_ref: str | None = None,
                 meeting_start_at: datetime | None = None,
                 meeting_url: str | None = None,
                 booking_id: uuid.UUID | None = None,
                 meeting_id: uuid.UUID | None = None,
                 user_id: uuid.UUID | None = None) -> MeetingPrepBrief | None:
    """Create/refresh the brief row for a booking and queue its generation.

    Never raises: this runs inside the Calendly webhook and the post-booking
    task, and neither may fail because a brief could not be requested.
    """
    from app.services import meeting_prep, notifications, system_settings  # noqa: PLC0415

    try:
        if not system_settings.get(db, "meeting_prep_enabled"):
            return None
        owner = user_id or notifications.owner_of_lead(db, lead)
        if owner is None:
            logger.warning("lead %s has no owner -- no meeting prep brief", lead.id)
            return None
        brief = meeting_prep.upsert_brief(
            db, lead, user_id=owner, source=source, external_ref=external_ref,
            meeting_start_at=meeting_start_at, meeting_url=meeting_url,
            booking_id=booking_id, meeting_id=meeting_id,
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("could not create a meeting prep brief for lead %s: %s",
                       lead.id, exc)
        return None
    enqueue_generation(brief.id)
    return brief


def enqueue_generation(brief_id) -> bool:
    """Queue generation. Never raises; tests monkeypatch this."""
    try:
        generate_meeting_prep.apply_async(args=[str(brief_id)], retry=False)
        return True
    except Exception as exc:  # noqa: BLE001
        # The brief row exists in PENDING, so the lead page shows Regenerate
        # and the user can produce it by hand. Nothing is lost.
        logger.warning("could not queue meeting prep %s: %s", brief_id, exc)
        return False


@celery_app.task(name="app.workers.meeting_prep_tasks.generate_meeting_prep",
                 bind=True, max_retries=2)
def generate_meeting_prep(self, brief_id: str) -> str:
    from app.services import meeting_prep  # noqa: PLC0415

    session = SessionLocal()
    try:
        from app.db.models import Lead, MeetingPrepBrief, Strategy  # noqa: PLC0415
        from app.services import usage_meter  # noqa: PLC0415

        brief = session.get(MeetingPrepBrief, uuid.UUID(brief_id))
        lead = session.get(Lead, brief.lead_id) if brief else None
        strategy = session.get(Strategy, lead.strategy_id) if lead else None
        with usage_meter.owner_scope(session, strategy, "meeting_prep"):
            return meeting_prep.generate_brief(session, uuid.UUID(brief_id))
    except Exception as exc:
        session.rollback()
        logger.exception("meeting prep task failed for %s -- retrying", brief_id)
        raise self.retry(exc=exc, countdown=60)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------


def _claim(db: Session, brief_id, column: str, now: datetime) -> bool:
    col = getattr(MeetingPrepBrief, column)
    result = db.execute(
        update(MeetingPrepBrief)
        .where(MeetingPrepBrief.id == brief_id, col.is_(None))
        .values({column: now})
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return result.rowcount == 1


def _hours_phrase(delta: timedelta) -> str:
    hours = max(1, round(delta.total_seconds() / 3600))
    if hours >= 20:
        return "tomorrow"
    return f"in {hours} hour{'s' if hours != 1 else ''}"


def send_meeting_reminders_impl(db: Session, now: datetime | None = None) -> dict:
    from app.services import event_bus, meeting_prep, system_settings  # noqa: PLC0415

    now = now or _now()
    want_24h = system_settings.get(db, "meeting_reminder_24h_enabled")
    want_1h = system_settings.get(db, "meeting_reminder_1h_enabled")
    sent = {"24h": 0, "1h": 0}

    due = db.execute(
        select(MeetingPrepBrief).where(
            MeetingPrepBrief.cancelled_at.is_(None),
            MeetingPrepBrief.meeting_start_at.isnot(None),
            MeetingPrepBrief.meeting_start_at > now,
            MeetingPrepBrief.meeting_start_at <= now + REMINDER_24H,
        )
    ).scalars().all()

    for brief in due:
        start = _aware(brief.meeting_start_at)
        until = start - now
        lead = db.get(Lead, brief.lead_id)
        if lead is None:
            continue
        name = lead.full_name or lead.email or "your prospect"
        company = f" ({lead.company})" if lead.company else ""
        link = meeting_prep.prep_link(lead.id)

        if until <= REMINDER_1H:
            # Inside the last hour: the 24h slot is spent either way.
            if brief.reminder_24h_sent_at is None:
                _claim(db, brief.id, "reminder_24h_sent_at", now)
            if not want_1h or brief.reminder_1h_sent_at is not None:
                continue
            if not _claim(db, brief.id, "reminder_1h_sent_at", now):
                continue
            script = (brief.opening_script or "").strip()
            event_bus.emit(
                db, brief.user_id, "meeting_reminder_1h",
                title=f"Meeting in 1 hour: {name}{company}",
                body=script[:900] if script else "Open your prep brief before the call.",
                deep_link=link,
                data={"leadId": str(lead.id), "briefId": str(brief.id)},
                slack_text=(f"*Your opening 60 seconds:*\n>{script}" if script
                            else "Your prep brief is ready to read."),
            )
            sent["1h"] += 1
        else:
            if not want_24h or brief.reminder_24h_sent_at is not None:
                continue
            if not _claim(db, brief.id, "reminder_24h_sent_at", now):
                continue
            phrase = _hours_phrase(until)
            when = start.strftime("%A %H:%M UTC")
            event_bus.emit(
                db, brief.user_id, "meeting_reminder_24h",
                title=f"Meeting {phrase}: {name}{company}",
                body=f"{when}. Read the prep brief before the call.",
                deep_link=link,
                data={"leadId": str(lead.id), "briefId": str(brief.id)},
            )
            sent["24h"] += 1
    return sent


@celery_app.task(name="app.workers.meeting_prep_tasks.send_meeting_reminders")
def send_meeting_reminders() -> dict:
    session = SessionLocal()
    try:
        return send_meeting_reminders_impl(session)
    finally:
        session.close()

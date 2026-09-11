"""M9 real-time event bus: CRM changes -> Redis pub/sub -> SSE stream.

WHY THIS IS A SESSION LISTENER AND NOT A publish() CALL AT EACH WRITE SITE

`Lead.status` and `Outcome` rows are written from at least ten places:
app/workers/lead_tasks.py (four separate transitions in the sourcing chain),
app/workers/outreach_tasks.py (three), app/services/sequence_engine.py,
app/services/whatsapp_optin.py, app/api/webhooks.py (Calendly booking),
app/api/webhooks_whatsapp.py, app/api/ui_support.py (the kanban PATCH), and
now app/api/crm.py. Threading a publish() call through all of them means ten
edits to milestone code this feature is supposed to be additive to, and --
more to the point -- an eleventh write site added next year would silently
not appear in the CRM's live feed, with nothing failing to say so.

A SQLAlchemy session listener is one registration that covers all of them,
including Celery workers, because every session in this process is built by
the same `sessionmaker` in app/db/base.py.

WHY TWO PHASES

`after_flush` is where the changes are still inspectable (`session.dirty` is
populated, and the session can still run the query that resolves a lead to its
owning user through strategy -> product -> user_id). But a flush is not a
commit: publishing there would announce events for a transaction that then
rolls back, and a client would render a status change that never happened.

So `after_flush` collects and resolves, `after_commit` publishes, and
`after_rollback` discards. The buffer hangs off the session's `info` dict, so
concurrent sessions never see each other's pending events.

FAILURE MODE: SILENT AND OPEN

Redis being down must never turn a working lead update into a 500. Every
publish is wrapped; a failure is logged at warning and swallowed, exactly like
app/core/rate_limiting.py::enforce_rate_limit does. The frontend's React Query
poll is the safety net that makes that acceptable -- a dropped event costs the
user up to one poll interval of staleness, not a lost write.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger

logger = get_logger("services.crm_events")

# One Redis channel per user. Per-user rather than one global channel because
# the SSE endpoint must not receive another account's events at all -- filtering
# them out in application code would mean every subscriber sees every event
# and a filtering bug becomes a cross-tenant data leak.
CHANNEL_PREFIX = "crm:events:"

# Buffer key on Session.info.
_BUFFER_KEY = "_crm_pending_events"

# Event names on the wire. The frontend switches on these to decide which
# React Query cache key to patch.
EVENT_LEAD_UPDATED = "lead.updated"
EVENT_LEAD_STATUS_CHANGED = "lead.status_changed"
EVENT_NOTE_CREATED = "note.created"
EVENT_OUTCOME_CREATED = "outcome.created"
EVENT_ACTIVITY_CREATED = "activity.created"


def channel_for(user_id: uuid.UUID | str) -> str:
    return f"{CHANNEL_PREFIX}{user_id}"


def _json_default(value: Any) -> str:
    if isinstance(value, (uuid.UUID,)):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def publish(user_id: uuid.UUID | str, event_name: str, payload: dict) -> None:
    """Publish one event to a user's channel. Never raises.

    Public so that a caller with a reason to emit an event the listeners
    cannot see (a bulk UPDATE issued as raw SQL, which bypasses the ORM unit
    of work entirely) can do so explicitly.
    """
    body = json.dumps(
        {"event": event_name, "data": payload}, default=_json_default
    )
    try:
        from app.core.redis_client import get_sync_redis

        get_sync_redis().publish(channel_for(user_id), body)
    except Exception as exc:  # Redis down: the poll fallback covers it.
        # NOT `event=`. get_logger() returns a structlog bound logger, whose
        # first positional argument IS the `event` field -- passing a keyword
        # of that name raises TypeError ("got multiple values for argument
        # 'event'"). Which would mean this except block, the one whose entire
        # job is to swallow a Redis failure, raised out of an after_commit
        # hook and turned a successful write into a 500. Exactly the failure
        # it exists to prevent.
        logger.warning("crm_events.publish_failed", crm_event=event_name,
                       error=str(exc))


# ---------------------------------------------------------------------------
# Owner resolution
# ---------------------------------------------------------------------------


def _owner_of_lead(session: Session, lead_id: uuid.UUID) -> uuid.UUID | None:
    """lead -> strategy -> product -> user_id, the same chain _owned_lead walks.

    One query with two joins rather than three `session.get()` calls, because
    this runs inside a flush on every write that touches a lead.
    """
    from app.db.models import Lead, Product, Strategy

    return session.execute(
        select(Product.user_id)
        .select_from(Lead)
        .join(Strategy, Strategy.id == Lead.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .where(Lead.id == lead_id)
    ).scalar_one_or_none()


def _strategy_of_lead(session: Session, lead_id: uuid.UUID) -> uuid.UUID | None:
    from app.db.models import Lead

    return session.execute(
        select(Lead.strategy_id).where(Lead.id == lead_id)
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Collection (after_flush) -> publication (after_commit)
# ---------------------------------------------------------------------------


def _buffer(session: Session) -> list[tuple]:
    return session.info.setdefault(_BUFFER_KEY, [])


def _queue(session: Session, user_id: uuid.UUID | None, event_name: str,
           payload: dict) -> None:
    if user_id is None:
        # An orphaned lead (its strategy or product was deleted). Nothing to
        # notify -- there is no owner to notify.
        return
    _buffer(session).append((user_id, event_name, payload))


def _lead_status_changed(obj) -> tuple[str | None, str | None] | None:
    """Return (old, new) if this instance's `status` was modified in this flush.

    Reads SQLAlchemy's attribute history rather than comparing against a
    snapshot we would otherwise have to maintain ourselves.
    """
    from sqlalchemy import inspect as sa_inspect

    history = sa_inspect(obj).attrs.status.history
    if not history.has_changes():
        return None
    old = history.deleted[0] if history.deleted else None
    new = history.added[0] if history.added else None
    return (
        old.value if hasattr(old, "value") else old,
        new.value if hasattr(new, "value") else new,
    )


@event.listens_for(Session, "after_flush")
def _crm_after_flush(session: Session, _flush_context) -> None:
    """Collect events for everything this flush created or changed.

    Deliberately tolerant: any exception here would abort a flush that was
    otherwise fine, turning "the live feed missed an event" into "the write
    failed". The feed is the thing that is allowed to degrade.
    """
    try:
        from app.db.models import CrmActivity, CrmNote, Lead, Outcome

        for obj in session.new:
            if isinstance(obj, CrmNote):
                owner = _owner_of_lead(session, obj.lead_id)
                _queue(session, owner, EVENT_NOTE_CREATED, {
                    "note_id": str(obj.id),
                    "lead_id": str(obj.lead_id),
                    "body": obj.body,
                    "author_user_id": (str(obj.author_user_id)
                                       if obj.author_user_id else None),
                })
            elif isinstance(obj, CrmActivity):
                owner = _owner_of_lead(session, obj.lead_id)
                _queue(session, owner, EVENT_ACTIVITY_CREATED, {
                    "activity_id": str(obj.id),
                    "lead_id": str(obj.lead_id),
                    "strategy_id": (str(obj.strategy_id)
                                    if obj.strategy_id else None),
                    "kind": obj.kind.value if obj.kind is not None else None,
                    "from_value": obj.from_value,
                    "to_value": obj.to_value,
                })
            elif isinstance(obj, Outcome):
                if obj.lead_id is None:
                    # System-level outcomes (ab_promoted, circuit_opened) have
                    # a strategy but no lead, so there is no CRM row to patch.
                    continue
                owner = _owner_of_lead(session, obj.lead_id)
                _queue(session, owner, EVENT_OUTCOME_CREATED, {
                    "lead_id": str(obj.lead_id),
                    "event": obj.event.value if obj.event is not None else None,
                    "channel": obj.channel,
                })
            elif isinstance(obj, Lead):
                owner = _owner_of_lead(session, obj.id)
                _queue(session, owner, EVENT_LEAD_UPDATED, {
                    "lead_id": str(obj.id),
                    "strategy_id": (str(obj.strategy_id)
                                    if obj.strategy_id else None),
                    "status": (obj.status.value
                               if obj.status is not None else None),
                    "created": True,
                })

        for obj in session.dirty:
            if not isinstance(obj, Lead):
                continue
            if not session.is_modified(obj, include_collections=False):
                continue
            owner = _owner_of_lead(session, obj.id)
            payload = {
                "lead_id": str(obj.id),
                "strategy_id": (str(obj.strategy_id)
                                if obj.strategy_id else None),
                "status": obj.status.value if obj.status is not None else None,
            }
            transition = _lead_status_changed(obj)
            if transition is not None:
                old, new = transition
                _queue(session, owner, EVENT_LEAD_STATUS_CHANGED, {
                    **payload, "from": old, "to": new,
                })
            else:
                _queue(session, owner, EVENT_LEAD_UPDATED, payload)
    except Exception as exc:  # never break a flush over the live feed
        logger.warning("crm_events.collect_failed", error=str(exc))


@event.listens_for(Session, "after_commit")
def _crm_after_commit(session: Session) -> None:
    """Publish what the committed transaction actually changed."""
    pending = session.info.pop(_BUFFER_KEY, None)
    if not pending:
        return
    for user_id, event_name, payload in pending:
        publish(user_id, event_name, payload)


@event.listens_for(Session, "after_rollback")
def _crm_after_rollback(session: Session) -> None:
    """Discard. A rolled-back status change must not reach any client."""
    session.info.pop(_BUFFER_KEY, None)


@event.listens_for(Session, "after_soft_rollback")
def _crm_after_soft_rollback(session: Session, _previous_transaction) -> None:
    """Same, for a nested/savepoint rollback.

    tests/conftest.py runs every test inside an outer transaction it rolls
    back, so without this the buffer would leak from one test into the next
    session that happens to reuse the object.
    """
    session.info.pop(_BUFFER_KEY, None)


def install() -> None:
    """No-op marker.

    The listeners above register at import time; this exists so the import in
    app/main.py and app/workers/celery_app.py reads as a deliberate
    installation rather than an unused import a linter or a future cleanup
    would delete -- which would disable the entire live feed with no test
    failing, since every consumer degrades gracefully to polling.
    """
    return None


# ---------------------------------------------------------------------------
# Engagement Hub (Feature 4) — bookings and meetings in the CRM timeline
# ---------------------------------------------------------------------------
#
# WHY THESE ARE FUNCTIONS AND NOT MORE SESSION LISTENERS
# The listeners above exist because `Lead.status` and `Outcome` are written
# from a dozen places nobody can enumerate reliably. Bookings and meetings are
# the opposite: there are exactly three moments that matter (a booking is
# made, a meeting is completed, an action item is extracted), each has one
# call site, and each needs context a listener could not recover from the row
# alone -- which summary text to attach, whose action item it is.
#
# So they are ordinary functions. They write CrmActivity/CrmNote rows, and the
# after_flush listener above then publishes those to the live feed for free:
# the real-time stream needs no change to carry meeting events.
#
# THEY DO NOT COMMIT. Every one of them is called inside a transaction the
# caller owns (a request handler, or a Celery task that has other writes to
# make in the same unit of work). Committing here would split that work in two
# and leave a booking that half-happened if the second half failed.


def _activity(session, lead_id, kind, *, actor_user_id=None, from_value=None,
              to_value=None, meta=None):
    """Append one CrmActivity row, resolving strategy_id from the lead.

    strategy_id is denormalized on that table (see its model docstring) so the
    account-wide feed can filter by strategy without a join; resolving it here
    means no caller has to remember to.
    """
    from app.db.models import CrmActivity

    activity = CrmActivity(
        lead_id=lead_id,
        strategy_id=_strategy_of_lead(session, lead_id),
        actor_user_id=actor_user_id,
        kind=kind,
        from_value=(str(from_value)[:200] if from_value is not None else None),
        to_value=(str(to_value)[:200] if to_value is not None else None),
        meta_json=meta or {},
    )
    session.add(activity)
    return activity


def record_activity(session, lead_id, kind, *, actor_user_id=None,
                    from_value=None, to_value=None, meta=None):
    """Public entry point for feature-expansion writers (meeting prep, meeting
    outcomes, deals, calls). Same contract as the helpers below: one
    CrmActivity row, strategy_id resolved from the lead, and NO commit."""
    return _activity(session, lead_id, kind, actor_user_id=actor_user_id,
                     from_value=from_value, to_value=to_value, meta=meta)


def on_booking_created(session: Session, lead_id: uuid.UUID,
                       booking_id: uuid.UUID, *, when: datetime | None = None,
                       page_title: str | None = None):
    """A lead booked a slot: one "Meeting Booked" row on their timeline.

    Deliberately does NOT also write an OutcomeEvent.BOOKED. The caller
    (app/workers/calendar_tasks.py::on_booking_created) writes that one, for
    the reason migration 0019 spells out at length: `outcomes` is the learning
    loop's event log and `crm_activities` is the UI's audit trail, a booking
    legitimately produces one row in each, and having two places write to
    `outcomes` for the same event is how a rate ends up counting it twice.
    """
    from app.db.models import CrmActivityKind

    return _activity(
        session, lead_id, CrmActivityKind.MEETING_BOOKED,
        to_value=(when.isoformat() if when else None),
        meta={"booking_id": str(booking_id), "page_title": page_title,
              "source": "leadpilot_calendar"},
    )


def on_meeting_completed(session: Session, lead_id: uuid.UUID,
                         meeting_id: uuid.UUID, *, summary: str | None = None,
                         host_user_id: uuid.UUID | None = None):
    """The call happened: a timeline row, plus the AI summary as a CRM note.

    The summary is attached as a NOTE rather than living only on the meeting
    row because the note panel is where a user looks before their next touch
    on this lead, and a summary they have to open a different screen to read
    is a summary they will not read. The meeting row keeps the canonical copy;
    this is a pointer with the text inlined.
    """
    from app.db.models import CrmActivityKind, CrmNote

    activity = _activity(
        session, lead_id, CrmActivityKind.MEETING_COMPLETED,
        actor_user_id=host_user_id,
        meta={"meeting_id": str(meeting_id)},
    )
    text = (summary or "").strip()
    if text:
        session.add(CrmNote(
            lead_id=lead_id,
            # NULL author, like every other machine-written row in this
            # schema: the feed uses actor_user_id being NULL to distinguish
            # "you wrote this" from "the system did".
            author_user_id=None,
            body=f"Meeting summary (AI):\n\n{text}"[:10_000],
        ))
    return activity


def on_action_item_created(session: Session, lead_id: uuid.UUID, item: dict, *,
                           meeting_id: uuid.UUID | None = None,
                           actor_user_id: uuid.UUID | None = None):
    """An action item becomes a CRM task.

    THERE IS NO `crm_tasks` TABLE, and this does not add one. The CRM's task
    surface already exists and is `crm_lead_meta.next_action_at` -- the "Next
    action" column in the grid, which is what a user filters and sorts on to
    decide who to work today. A new table would give action items their own
    parallel to-do list that nothing else on the screen reads.

    So: the item's text is written as a note (visible in the lead panel), a
    TASK_CREATED activity records where it came from, and `next_action_at` is
    advanced to the item's due date -- but only FORWARD-safely: an existing
    earlier due date is left alone, because a summary generated after the call
    must not push out a task the user set for tomorrow morning.
    """
    from app.db.models import CrmActivityKind, CrmNote

    text = str((item or {}).get("text") or "").strip()
    if not text:
        return None

    owner = str((item or {}).get("owner") or "us")
    session.add(CrmNote(
        lead_id=lead_id,
        author_user_id=None,
        body=f"Action item ({'you' if owner == 'us' else 'client'}): {text}"[:10_000],
    ))
    activity = _activity(
        session, lead_id, CrmActivityKind.TASK_CREATED,
        actor_user_id=actor_user_id,
        to_value=text,
        meta={"meeting_id": str(meeting_id) if meeting_id else None,
              "owner": owner, "due": (item or {}).get("due")},
    )

    due = _parse_due(item.get("due") if item else None)
    if due is not None:
        from app.services.crm_service import get_or_create_meta  # noqa: PLC0415

        meta = get_or_create_meta(session, session.get(_lead_model(), lead_id))
        current = meta.next_action_at
        if current is not None and current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        if current is None or due < current:
            meta.next_action_at = due
    return activity


def _lead_model():
    from app.db.models import Lead

    return Lead


def _parse_due(raw) -> datetime | None:
    """A YYYY-MM-DD due date as an aware UTC datetime, or None.

    Returns None for anything unparseable rather than raising: the value comes
    from a model's JSON output, and a malformed date is a reason to skip the
    reminder, not to fail the whole summary write.
    """
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).strip()[:19])
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

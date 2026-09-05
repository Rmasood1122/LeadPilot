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
from datetime import datetime
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

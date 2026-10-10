"""Send-time HOLDS: one definition of "a message a guard parked for later".

A send-time guard may hold a message instead of sending or cancelling it:
status FAILED, with the guard's prefix on `message.error`, so the message is
kept, visible and releasable:

    F01 Bounce Shield    'bounce_shield: '     (app/services/bounce_shield.py)

A later guard that holds the same way adds its prefix to HOLD_PREFIXES.

A held message is still the message for its step. Everything that asks "is a
step already pending for this enrollment?" (the follow-up sweep in
app/workers/outreach_tasks.py) must count it, or it creates a second copy of
the step while the first is held, and every copy sends on release. And a
release must put back AT MOST ONE message per (sequence, lead, step) -- this
module does both, for every guard, so no guard can drift from the others.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.models import Message, MessageStatus

# The prefixes, as literals so this module imports nothing from the guards.
# Each guard's tests assert its own ERROR_PREFIX is listed.
BOUNCE_SHIELD_PREFIX = "bounce_shield: "        # F01
HOLD_PREFIXES: tuple[str, ...] = (BOUNCE_SHIELD_PREFIX,)

# A message in one of these states IS the step: a held copy of it is redundant.
_LIVE = (MessageStatus.SCHEDULED, MessageStatus.SENDING, MessageStatus.SENT,
         MessageStatus.AWAITING_REVIEW)

DUPLICATE_ERROR = "duplicate of a held step - cancelled on release"


def held_clause(prefixes: tuple[str, ...] = HOLD_PREFIXES):
    """SQL: this message is held by one of `prefixes`."""
    return and_(Message.status == MessageStatus.FAILED,
                or_(*[Message.error.like(f"{p}%") for p in prefixes]))


def pending_clause():
    """SQL: this message is pending for its step -- scheduled, being sent, or
    held by a guard."""
    return or_(Message.status.in_([MessageStatus.SCHEDULED, MessageStatus.SENDING]),
               held_clause())


def release(db: Session, lead_id, prefix: str, now: datetime | None = None) -> int:
    """Return `lead_id`'s messages held under `prefix` to SCHEDULED, due now --
    at most ONE per (sequence, step). Extra held copies, and held copies of a
    step that already has a live message, are CANCELLED. Commits. Returns the
    number released. A released message goes back through every gate."""
    now = now or datetime.now(timezone.utc)
    held = db.execute(
        select(Message).where(Message.lead_id == lead_id, held_clause((prefix,)))
        .order_by(Message.created_at, Message.id)
    ).scalars().all()
    if not held:
        return 0
    live = {(row.sequence_id, row.step_no) for row in db.execute(
        select(Message.sequence_id, Message.step_no).where(
            Message.lead_id == lead_id, Message.status.in_(_LIVE))).all()}
    released = 0
    for message in held:
        key = (message.sequence_id, message.step_no)
        if key in live:
            message.status = MessageStatus.CANCELLED
            message.error = DUPLICATE_ERROR
            continue
        message.status = MessageStatus.SCHEDULED
        message.scheduled_at = now
        message.error = None
        live.add(key)
        released += 1
    db.commit()
    return released

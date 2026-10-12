"""Send-time HOLDS: one definition of "a message a guard parked for later".

Three guards in the send chokepoint hold a message instead of sending or
cancelling it: status FAILED, with the guard's prefix on `message.error`, so
the message is kept, visible and releasable:

    F01 Bounce Shield    'bounce_shield: '     (app/services/bounce_shield.py)
    F10 Champion Tracker 'champion_tracker: '  (app/services/champion_tracker.py)
    Plan entitlement     'plan_limit: '        (app/services/plan_holds.py)

A held message is still the message for its step. Everything that asks "is a
step already pending for this enrollment?" (the follow-up sweep in
app/workers/outreach_tasks.py) must count it, or it creates a second copy of
the step while the first is held, and every copy sends on release. The same
is true of a message parked in the human review queue (status
AWAITING_REVIEW, app/services/send_review.py): approving it returns it to
SCHEDULED, so a sweep copy made while it waited would send the step twice. And a
release must put back AT MOST ONE message per (sequence, lead, step) -- this
module does both, for every guard, so neither can drift from the other.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.models import Message, MessageStatus

# The prefixes, as literals so this module imports nothing from the guards.
# Each guard asserts its own ERROR_PREFIX is listed (tests/test_champion_tracker.py).
BOUNCE_SHIELD_PREFIX = "bounce_shield: "        # F01
CHAMPION_TRACKER_PREFIX = "champion_tracker: "  # F10
PLAN_LIMIT_PREFIX = "plan_limit: "              # plan downgrade (plan_holds.py)
HOLD_PREFIXES: tuple[str, ...] = (BOUNCE_SHIELD_PREFIX, CHAMPION_TRACKER_PREFIX,
                                  PLAN_LIMIT_PREFIX)

# A message in one of these states IS the step: a held copy of it is redundant.
_LIVE = (MessageStatus.SCHEDULED, MessageStatus.SENDING, MessageStatus.SENT,
         MessageStatus.AWAITING_REVIEW)

DUPLICATE_ERROR = "duplicate of a held step - cancelled on release"

# Daily send approval holds a message differently: it stays SCHEDULED, moved to
# the next local midnight, with this prefix (daily_send_approval.ERROR_PREFIX;
# asserted equal in tests/test_gaps_sweep_2.py). Not in HOLD_PREFIXES, which
# describe FAILED-status holds.
DAILY_APPROVAL_PREFIX = "daily_send_approval: "

#: prefix -> (kind, label) for the "On hold" badge (hold_of below).
_HOLD_KINDS: dict[str, tuple[str, str]] = {
    BOUNCE_SHIELD_PREFIX: ("bounce_shield", "Bounce Shield"),
    CHAMPION_TRACKER_PREFIX: ("champion_tracker", "Champion Tracker"),
    PLAN_LIMIT_PREFIX: ("plan_limit", "Plan limit"),
    DAILY_APPROVAL_PREFIX: ("daily_send_approval", "Daily approval"),
}


def hold_of(status, error: str | None) -> dict | None:
    """Why a message is ON HOLD, for display -- or None when it is not held.

    The ONE place the UI learns "held, not failed": a guard-held message is
    stored as FAILED and used to be shown as a plain failure. Returns
    {"kind", "label", "reason"} where `reason` is the guard's own text with
    its prefix removed. Covers the FAILED-status guard holds (Bounce Shield,
    Champion Tracker, plan limit), the daily-approval hold (SCHEDULED +
    prefix) and the human review queue (AWAITING_REVIEW)."""
    status = getattr(status, "value", status)
    text = error or ""
    if status == MessageStatus.AWAITING_REVIEW.value:
        return {"kind": "send_review", "label": "Send review",
                "reason": "waiting for approval in the review queue"}
    allowed = {MessageStatus.FAILED.value: HOLD_PREFIXES,
               MessageStatus.SCHEDULED.value: (DAILY_APPROVAL_PREFIX,)}.get(status, ())
    for prefix in allowed:
        if text.startswith(prefix):
            kind, label = _HOLD_KINDS[prefix]
            return {"kind": kind, "label": label,
                    "reason": text[len(prefix):].strip() or label}
    return None


def held_clause(prefixes: tuple[str, ...] = HOLD_PREFIXES):
    """SQL: this message is held by one of `prefixes`."""
    return and_(Message.status == MessageStatus.FAILED,
                or_(*[Message.error.like(f"{p}%") for p in prefixes]))


#: A message that is the step and will still go out (or is going out now).
PENDING_STATUSES = (MessageStatus.SCHEDULED, MessageStatus.SENDING,
                    MessageStatus.AWAITING_REVIEW)


def not_held_clause(prefixes: tuple[str, ...] = HOLD_PREFIXES):
    """SQL: this message is NOT held. Spelled out instead of ~held_clause()
    because a NULL `error` makes the negated LIKE NULL, which would drop
    ordinary failures (error NULL) from a count."""
    return or_(Message.status != MessageStatus.FAILED, Message.error.is_(None),
               and_(*[~Message.error.like(f"{p}%") for p in prefixes]))


def pending_clause():
    """SQL: this message is pending for its step -- scheduled, being sent,
    waiting in the review queue, or held by a guard."""
    return or_(Message.status.in_(PENDING_STATUSES), held_clause())


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

"""Send-time plan entitlement: what a downgrade does to messages already queued.

THE GAP
Plans are enforced when a sequence is CREATED and every time it is LAUNCHED
(app/api/sequences.py `_enforce_plan`: max_sequence_steps and channels). A
sequence launched on Growth keeps its scheduled messages after the account
drops to Free, and nothing at send time looked at the plan again -- so a Free
account kept sending LinkedIn steps and steps 6-15 of a 15-step sequence it is
no longer paying for.

THE BEHAVIOUR (code truth; needs founder confirmation, see
docs/program/fixes/platform-gaps.md item 3)
At send time (app/workers/outreach_tasks.py send_message_impl), the strategy
OWNER's CURRENT plan -- users.plan, which billing._sync_plan keeps in step
with the subscription -- must cover the message:

  channel     the message's channel is in PLANS[plan]["channels"]
              (check_send_channel; every message, every origin)
  step limit  an ordinary sequence message (origin NULL: scheduled steps and
              automatic follow-ups of a step) has step_no <= max_sequence_steps
              (-1 = unlimited). Re-engagement and Reply Copilot rows have their
              own switches and caps and are not numbered as sequence steps, so
              only the channel rule applies to them.

A message the plan no longer covers is HELD, not cancelled and not sent:
status FAILED with error "plan_limit: <reason>" -- the same hold convention as
F01 Bounce Shield and F10 Champion Tracker (app/services/send_holds.py). That
means it is kept and visible on the lead with the reason, it counts as the
pending message for its step (so the follow-up sweep does not create a second
copy), it is never transmitted, and the enrollment is NOT stopped. Steps the
plan still covers keep sending.

WHO IS NOT CHECKED (review decision 2026-10-11, founder item)
  * enrollments created before PLAN_HOLD_EFFECTIVE_AT: campaigns launched
    before plan enforcement shipped (PR #58) or before this check existed
    keep the behaviour they were launched under -- freezing them mid-flight
    would stop paying customers' live campaigns overnight;
  * operator accounts (users.is_admin);
  * a Reply Copilot answer a PERSON approved (origin "reply_copilot", draft
    not auto_sent): someone read the prospect's reply and chose to answer it.
    An AUTO-sent copilot answer is checked like any other message.

WHY HOLD AND NOT CANCEL
A downgrade is often temporary (a failed card, a plan change mid-month).
Cancelling would silently throw away work the customer built and paid for;
holding keeps it, says why, and never sends unpaid-for outreach.

RELEASE
release_sweep() (beat, every 15 minutes: app/workers/plan_hold_tasks.py) puts
a lead's plan holds back to SCHEDULED, through send_holds.release, as soon as
the owner's CURRENT plan covers one of them again -- an upgrade unfreezes the
campaign with no change to billing code. A released message goes back through
every gate, this one included.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.plans import (
    PlanLimitExceeded,
    check_send_channel,
    get_plan,
)
from app.db.models import (
    Lead,
    Message,
    MessageStatus,
    Product,
    ReplyDraft,
    SequenceEnrollment,
    Strategy,
    User,
)
from app.services import send_holds

logger = logging.getLogger(__name__)

ERROR_PREFIX = send_holds.PLAN_LIMIT_PREFIX
AUDIT_HELD = "held_plan_limit"
SEND_RESULT = "held_plan_limit"

# Enrollments created before this instant are grandfathered (see WHO IS NOT
# CHECKED). UTC. A constant, not a setting: moving it is a reviewed change.
PLAN_HOLD_EFFECTIVE_AT = datetime(2026, 10, 12, 0, 0, 0, tzinfo=timezone.utc)

REPLY_COPILOT_ORIGIN = "reply_copilot"  # app/services/reply_copilot.ORIGIN

# Most leads one sweep looks at (oldest holds first); the rest wait 15 min.
SWEEP_LEAD_LIMIT = 500


def _plan_name(owner: User) -> str:
    return str(getattr(owner.plan, "value", owner.plan) or "free")


def send_block(owner: User, message: Message) -> str | None:
    """Why `owner`'s current plan does not cover `message`, or None if it does.

    Pure: reads the plan definitions in app/core/plans.py, no queries."""
    try:
        check_send_channel(owner, message.channel)
    except PlanLimitExceeded as exc:
        return exc.message
    if message.origin is None:
        plan_name = _plan_name(owner)
        plan = get_plan(plan_name)
        limit = plan.get("max_sequence_steps", -1)
        if limit != -1 and int(message.step_no or 1) > int(limit):
            return (f"{plan['display_name']} plan allows {limit} sequence steps; "
                    f"this is step {message.step_no}.")
    return None


def hold_message(message: Message, reason: str) -> None:
    """Hold (the caller audits and commits). Kept, visible, never sent."""
    message.status = MessageStatus.FAILED
    message.error = f"{ERROR_PREFIX}{reason}"[:1000]


def _aware(value: datetime | None) -> datetime | None:
    """SQLite returns DateTime(timezone=True) naive; treat it as UTC."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _person_approved_copilot_answer(session: Session, message: Message) -> bool:
    if message.origin != REPLY_COPILOT_ORIGIN:
        return False
    draft = session.execute(
        select(ReplyDraft).where(ReplyDraft.message_id == message.id)
    ).scalar_one_or_none()
    # No draft row = no proof a person approved it: checked like the rest.
    return draft is not None and not bool(draft.auto_sent)


def applies(session: Session, owner: User, message: Message,
            enrollment: SequenceEnrollment | None) -> bool:
    """Is this message subject to the send-time plan check at all?"""
    if bool(getattr(owner, "is_admin", False)):
        return False
    started = _aware(enrollment.created_at) if enrollment is not None else None
    if started is not None and started < PLAN_HOLD_EFFECTIVE_AT:
        return False
    return not _person_approved_copilot_answer(session, message)


def check(session: Session, owner: User, message: Message,
          enrollment: SequenceEnrollment | None) -> str | None:
    """The hold reason for `message` under `owner`'s current plan, or None
    when it may proceed (exempt, or covered)."""
    if not applies(session, owner, message, enrollment):
        return None
    return send_block(owner, message)


def release_sweep(session: Session, now: datetime | None = None,
                  limit: int = SWEEP_LEAD_LIMIT) -> dict:
    """Release plan holds the owner's current plan covers again.

    Per lead: if ANY of its plan-held messages would now pass check(), all of
    the lead's plan holds go back to SCHEDULED through send_holds.release
    (one per step, duplicates cancelled). One that is still not covered is
    simply held again by the send path. Commits (send_holds.release does).
    NOTHING here sends."""
    now = now or datetime.now(timezone.utc)
    rows = session.execute(
        select(Message, User, SequenceEnrollment)
        .join(Lead, Lead.id == Message.lead_id)
        .join(Strategy, Strategy.id == Lead.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .join(User, User.id == Product.user_id)
        .outerjoin(SequenceEnrollment,
                   (SequenceEnrollment.sequence_id == Message.sequence_id)
                   & (SequenceEnrollment.lead_id == Message.lead_id))
        .where(send_holds.held_clause((ERROR_PREFIX,)))
        .order_by(Message.created_at)
    ).all()
    by_lead: dict = {}
    for message, owner, enrollment in rows:
        if message.lead_id not in by_lead and len(by_lead) >= limit:
            continue
        by_lead.setdefault(message.lead_id, []).append((message, owner, enrollment))
    counts = {"held_leads": len(by_lead), "released_leads": 0, "released_messages": 0}
    for lead_id, held in by_lead.items():
        if all(check(session, owner, message, enrollment) is not None
               for message, owner, enrollment in held):
            continue
        released = send_holds.release(session, lead_id, ERROR_PREFIX, now)
        if released:
            counts["released_leads"] += 1
            counts["released_messages"] += released
    if counts["released_leads"]:
        logger.info("plan holds released: %s", counts)
    return counts

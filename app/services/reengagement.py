"""Opt-in post-sequence re-engagement (Feature 5).

WHY THIS WAS DELIBERATELY UNBUILT, AND WHAT CHANGED
FEATURES.md Part 5 left completed sequences alone because sweeping them is an
unbounded mass-send: every lead who ever finished a sequence, every sweep, with
no user-facing cap. This module ships it with the cap and the opt-in as the
design, not as settings bolted on afterwards:

  * OFF per campaign by default (strategies.reengagement_enabled), and only an
    owner or manager can turn it on;
  * its OWN daily and rolling-weekly caps, clamped to admin ceilings -- and a
    re-engagement send still counts against the channel's ordinary daily cap;
  * AT MOST ONCE per enrollment, guaranteed by UNIQUE(enrollment_id) on
    reengagement_attempts rather than by a lock or a query;
  * every send goes through outreach_tasks.send_message_impl -- suppression,
    campaign and enrollment state, the conversion gate, the send window, the
    daily cap -- plus this feature's own switch and cap, re-checked at send
    time by send_time_hold(). No bypass.

WHO IS ELIGIBLE -- "last outcome neutral"
  enrollment COMPLETED, never re-engaged, nothing pending;
  lead status still `contacted` (not replied, booked, closed, dropped...);
  no REPLIED / BOOKED / WON / LOST outcome since this sequence first sent;
  never UNSUBSCRIBED / OPTED_OUT / BOUNCED, not suppressed, not archived by the
  conversion gate;
  the last send was on EMAIL (see CHANNELS) and at least delay_days ago.

TENANCY
Candidates are always found per strategy through lead.strategy_id AND
sequence.strategy_id, and ineligibility() refuses an enrollment whose sequence
and lead disagree about the campaign -- a shape that should not exist, and
exactly the shape a cross-tenant bug would produce.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    ChannelType,
    EnrollmentStatus,
    Lead,
    LeadStatus,
    Message,
    MessageStatus,
    Outcome,
    OutcomeEvent,
    ReengagementAttempt,
    Sequence,
    SequenceEnrollment,
    Strategy,
)
from app.services import system_settings

logger = logging.getLogger(__name__)

ORIGIN = "reengagement"
OUTCOME_SOURCE = "reengagement"

# Channels a re-engagement may go out on. Email only, deliberately:
#   WhatsApp -- a cold message needs an approved template and there is no step
#               to name one (the same reason the auto follow-up skips it);
#   LinkedIn -- the channel resolves `auto` into a connection request for a
#               lead who is not connected, i.e. a second invitation;
#   phone    -- an unprompted AI call to someone who never answered a sequence
#               is a different compliance conversation (TCPA).
CHANNELS = (ChannelType.EMAIL,)

# A reply, a booking or a decision -- the lead engaged, so this is not neutral.
ENGAGED_EVENTS = (OutcomeEvent.REPLIED, OutcomeEvent.BOOKED, OutcomeEvent.WON,
                  OutcomeEvent.LOST)
# Ever, on any campaign: these people asked not to be contacted or cannot be.
EXIT_EVENTS = (OutcomeEvent.UNSUBSCRIBED, OutcomeEvent.OPTED_OUT, OutcomeEvent.BOUNCED)

# How many completed enrollments one sweep inspects per campaign before giving
# up on filling its allowance. Bounds the sweep's cost on a campaign whose
# completed leads are mostly ineligible.
_SCAN_LIMIT = 500


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Switches and caps
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Limits:
    daily_cap: int
    weekly_cap: int
    delay_days: int


def allowed(session: Session) -> bool:
    return bool(system_settings.get(session, "reengagement_allowed"))


def ceilings(session: Session) -> dict:
    return {
        "daily_cap": int(system_settings.get(session, "reengagement_daily_cap_ceiling")),
        "weekly_cap": int(system_settings.get(session, "reengagement_weekly_cap_ceiling")),
        "min_delay_days": int(system_settings.get(session, "reengagement_min_delay_days")),
    }


def effective_limits(session: Session, strategy: Strategy) -> Limits:
    """The campaign's settings, clamped to the admin ceilings.

    Clamping runs in the restrictive direction only: a cap is lowered to its
    ceiling, a delay is raised to the minimum. An admin lowering a ceiling
    therefore takes effect on every campaign at the next check, without
    rewriting any campaign's stored choice.
    """
    limit = ceilings(session)
    return Limits(
        daily_cap=max(0, min(int(strategy.reengagement_daily_cap or 0), limit["daily_cap"])),
        weekly_cap=max(0, min(int(strategy.reengagement_weekly_cap or 0), limit["weekly_cap"])),
        delay_days=max(int(strategy.reengagement_delay_days or 0), limit["min_delay_days"]),
    )


def sent_counts(session: Session, strategy: Strategy, now: datetime) -> tuple[int, int]:
    """Re-engagement messages SENT for this campaign today (UTC) and in the
    last 7 days. Counted from message rows, scoped through the lead."""
    day_start = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    base = (
        select(func.count(Message.id))
        .join(Lead, Lead.id == Message.lead_id)
        .where(Lead.strategy_id == strategy.id,
               Message.origin == ORIGIN,
               Message.status == MessageStatus.SENT)
    )
    today = session.execute(base.where(Message.sent_at >= day_start)).scalar_one()
    week = session.execute(base.where(Message.sent_at >= now - timedelta(days=7))).scalar_one()
    return int(today), int(week)


def allowance_left(session: Session, strategy: Strategy, now: datetime) -> int:
    limits = effective_limits(session, strategy)
    today, week = sent_counts(session, strategy, now)
    return max(0, min(limits.daily_cap - today, limits.weekly_cap - week))


# --------------------------------------------------------------------------
# Eligibility
# --------------------------------------------------------------------------


def _last_sent(session: Session, enrollment: SequenceEnrollment) -> Message | None:
    return session.execute(
        select(Message)
        .where(Message.sequence_id == enrollment.sequence_id,
               Message.lead_id == enrollment.lead_id,
               Message.status == MessageStatus.SENT)
        .order_by(Message.sent_at.desc(), Message.step_no.desc())
    ).scalars().first()


def _first_sent_at(session: Session, enrollment: SequenceEnrollment) -> datetime | None:
    return _aware(session.execute(
        select(func.min(Message.sent_at))
        .where(Message.sequence_id == enrollment.sequence_id,
               Message.lead_id == enrollment.lead_id,
               Message.status == MessageStatus.SENT)
    ).scalar_one())


def ineligibility(session: Session, enrollment: SequenceEnrollment,
                  now: datetime | None = None, *, preview: bool = False) -> str | None:
    """Why this enrollment may NOT be re-engaged now, or None when it may.

    `preview` skips the two on/off switches, so the settings panel can say how
    many leads WOULD qualify before anyone turns the feature on.
    """
    from app.services import sequence_engine as engine  # noqa: PLC0415
    from app.workers.lead_tasks import is_suppressed  # noqa: PLC0415

    now = now or _now()
    if enrollment.status is not EnrollmentStatus.COMPLETED:
        return "enrollment_not_completed"
    lead = session.get(Lead, enrollment.lead_id)
    sequence = session.get(Sequence, enrollment.sequence_id)
    if lead is None or sequence is None or sequence.strategy_id != lead.strategy_id:
        return "tenant_mismatch"
    strategy = session.get(Strategy, lead.strategy_id)
    if strategy is None:
        return "tenant_mismatch"

    if not preview:
        if not allowed(session):
            return "disabled_globally"
        if not strategy.reengagement_enabled:
            return "disabled"
    if strategy.campaign_state != engine.CAMPAIGN_ACTIVE:
        return "campaign_paused"
    if lead.status is not LeadStatus.CONTACTED:
        return f"lead_{lead.status.value}"
    if lead.engagement_state == "archived":
        return "lead_archived"

    if session.execute(select(ReengagementAttempt.id).where(
            ReengagementAttempt.enrollment_id == enrollment.id)).first() is not None:
        return "already_attempted"
    if session.execute(select(Message.id).where(
            Message.sequence_id == enrollment.sequence_id,
            Message.lead_id == enrollment.lead_id,
            Message.status.in_([MessageStatus.SCHEDULED, MessageStatus.SENDING]),
    ).limit(1)).first() is not None:
        return "pending_message"

    last = _last_sent(session, enrollment)
    if last is None or last.sent_at is None:
        return "never_sent"
    if last.channel not in CHANNELS:
        return "channel_not_supported"
    if now - _aware(last.sent_at) < timedelta(days=effective_limits(session, strategy).delay_days):
        return "too_soon"

    first = _first_sent_at(session, enrollment)
    engaged = select(Outcome.id).where(Outcome.lead_id == lead.id,
                                       Outcome.event.in_(ENGAGED_EVENTS))
    if first is not None:
        engaged = engaged.where(Outcome.ts >= first)
    if session.execute(engaged.limit(1)).first() is not None:
        return "engaged"
    if session.execute(select(Outcome.id).where(
            Outcome.lead_id == lead.id, Outcome.event.in_(EXIT_EVENTS)).limit(1)).first():
        return "opted_out_or_bounced"
    if is_suppressed(session, lead.email, lead.phone, linkedin=lead.linkedin_url):
        return "suppressed"
    return None


def candidates(session: Session, strategy: Strategy, now: datetime, limit: int,
               *, preview: bool = False) -> list[SequenceEnrollment]:
    """Up to `limit` eligible enrollments of ONE campaign, oldest first."""
    if limit <= 0:
        return []
    rows = session.execute(
        select(SequenceEnrollment)
        .join(Sequence, Sequence.id == SequenceEnrollment.sequence_id)
        .join(Lead, Lead.id == SequenceEnrollment.lead_id)
        .where(Sequence.strategy_id == strategy.id,
               Lead.strategy_id == strategy.id,
               SequenceEnrollment.status == EnrollmentStatus.COMPLETED,
               Lead.status == LeadStatus.CONTACTED,
               ~exists().where(ReengagementAttempt.enrollment_id == SequenceEnrollment.id))
        .order_by(SequenceEnrollment.updated_at, SequenceEnrollment.id)
        .limit(_SCAN_LIMIT)
    ).scalars().all()
    found: list[SequenceEnrollment] = []
    for enrollment in rows:
        if ineligibility(session, enrollment, now, preview=preview) is None:
            found.append(enrollment)
            if len(found) >= limit:
                break
    return found


# --------------------------------------------------------------------------
# Claim + send-time hold
# --------------------------------------------------------------------------


def claim(session: Session, enrollment: SequenceEnrollment, lead: Lead,
          strategy: Strategy) -> ReengagementAttempt | None:
    """Insert the attempt row. None when another run already holds it.

    Commits immediately and on its own: the claim must be durable before any
    message exists, or a crash between the two would leave nothing to stop a
    retry from creating a second message.
    """
    attempt = ReengagementAttempt(enrollment_id=enrollment.id, lead_id=lead.id,
                                  strategy_id=strategy.id, status="claimed")
    session.add(attempt)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return None
    return attempt


def send_time_hold(session: Session, strategy: Strategy, lead: Lead, message: Message,
                   now: datetime) -> str | None:
    """This feature's own gates, re-checked by send_message_impl immediately
    before transmitting a re-engagement message. None = carry on.

    A switch turned off since scheduling CANCELS the message. An exhausted cap
    DEFERS it to the next day's window -- never drops it, the same rule every
    other cap in the send path follows.
    """
    from app.services import sequence_engine as engine  # noqa: PLC0415

    if not allowed(session) or not strategy.reengagement_enabled:
        message.status = MessageStatus.CANCELLED
        message.error = "re-engagement was turned off before this message sent"
        session.commit()
        return "cancelled_reengagement_off"
    if lead.status is not LeadStatus.CONTACTED:
        message.status = MessageStatus.CANCELLED
        message.error = f"lead is now {lead.status.value}; re-engagement no longer applies"
        session.commit()
        return "cancelled_lead_engaged"
    if allowance_left(session, strategy, now) <= 0:
        tomorrow = now.astimezone(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        message.scheduled_at = engine.next_window_slot(tomorrow, engine.lead_timezone(lead))
        session.commit()
        return "deferred_reengagement_cap"
    return None


# --------------------------------------------------------------------------
# Status (settings panel)
# --------------------------------------------------------------------------


def status(session: Session, strategy: Strategy, now: datetime | None = None) -> dict:
    now = now or _now()
    limits = effective_limits(session, strategy)
    today, week = sent_counts(session, strategy, now)
    return {
        "enabled": bool(strategy.reengagement_enabled),
        "allowed": allowed(session),
        "delay_days": int(strategy.reengagement_delay_days),
        "daily_cap": int(strategy.reengagement_daily_cap),
        "weekly_cap": int(strategy.reengagement_weekly_cap),
        "effective": {"daily_cap": limits.daily_cap, "weekly_cap": limits.weekly_cap,
                      "delay_days": limits.delay_days},
        "ceilings": ceilings(session),
        "sent_today": today,
        "sent_this_week": week,
        # Counted as if the feature were on, capped at the scan limit, so the
        # panel can show the size of what turning it on would start.
        "eligible_now": len(candidates(session, strategy, now, _SCAN_LIMIT, preview=True)),
        "eligible_scan_limit": _SCAN_LIMIT,
        "channels": [c.value for c in CHANNELS],
    }

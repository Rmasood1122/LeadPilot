"""The sequence engine — all outreach business rules live HERE, not in
channels and not in templates.

Hard stop conditions (engine-enforced, per project spec):
    replied -> stop | unsubscribed -> stop + suppression | bounced -> stop
    meeting_booked -> stop.  A stopped enrollment can NEVER send again.

Compliance core (chunk 3):
    - suppression re-checked immediately before EVERY send, no exceptions
    - visible unsubscribe footer with sender identity (CAN-SPAM) +
      List-Unsubscribe / List-Unsubscribe-Post one-click headers
    - per-account daily caps with a configurable warm-up ramp; sends over
      today's allowance are DEFERRED, never dropped
    - business-hours send window in the lead's timezone (fallback config)
    - bounce-rate monitor: campaign auto-pauses above the threshold

Every time-dependent function takes an explicit `now` so behavior is
deterministic and fully testable.
"""

import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    ChannelType,
    EnrollmentStatus,
    GmailAccount,
    Lead,
    LeadStatus,
    Message,
    MessageStatus,
    Outcome,
    OutcomeEvent,
    Sequence,
    SequenceEnrollment,
    SequenceStep,
    Strategy,
    SuppressionEntry,
)
from app.services import crypto
from app.workers.lead_tasks import is_suppressed

logger = logging.getLogger(__name__)

CAMPAIGN_ACTIVE = "active"
CAMPAIGN_PAUSED_BOUNCE = "paused_bounce_rate"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Send window (lead timezone, business hours, weekend skip)
# --------------------------------------------------------------------------


def lead_timezone(lead: Lead) -> str:
    tz = (lead.enrichment_json or {}).get("timezone")
    if tz:
        try:
            ZoneInfo(tz)
            return tz
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return settings.send_window_timezone


def next_window_slot(dt: datetime, tz_name: str) -> datetime:
    """Earliest instant >= dt inside the send window (returned in UTC)."""
    tz = ZoneInfo(tz_name)
    local = dt.astimezone(tz)
    start_h, end_h = settings.send_window_start_hour, settings.send_window_end_hour

    for _ in range(14):  # never loops more than two weeks
        is_weekend = local.weekday() >= 5 and settings.send_window_skip_weekends
        if not is_weekend:
            if local.time() < time(start_h):
                local = local.replace(hour=start_h, minute=0, second=0, microsecond=0)
                return local.astimezone(timezone.utc)
            if time(start_h) <= local.time() < time(end_h):
                return local.astimezone(timezone.utc)
        # past today's window (or weekend): next day at window start
        local = (local + timedelta(days=1)).replace(
            hour=start_h, minute=0, second=0, microsecond=0
        )
    raise RuntimeError("could not find a send window slot within 14 days")


def in_send_window(dt: datetime, tz_name: str) -> bool:
    return next_window_slot(dt, tz_name) <= dt


# --------------------------------------------------------------------------
# Daily caps + warm-up
# --------------------------------------------------------------------------


def daily_allowance(account: GmailAccount, on_date: date) -> int:
    """Warm-up ramp: start low, add the increment each day, cap at the
    configured daily cap. Day 0 = the day the account was connected."""
    connected = account.created_at.date() if account.created_at else on_date
    age_days = max(0, (on_date - connected).days)
    ramped = settings.gmail_warmup_start_sends + settings.gmail_warmup_daily_increment * age_days
    return min(settings.gmail_daily_cap, ramped)


def sends_today(session: Session, sender_ref: str, now: datetime) -> int:
    day_start = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return session.execute(
        select(func.count(Message.id)).where(
            Message.sender_ref == sender_ref,
            Message.status == MessageStatus.SENT,
            Message.sent_at >= day_start,
        )
    ).scalar_one()


def allowance_left(session: Session, account: GmailAccount, now: datetime) -> int:
    return daily_allowance(account, now.astimezone(timezone.utc).date()) - sends_today(
        session, str(account.id), now
    )


# --------------------------------------------------------------------------
# WhatsApp daily cap + warm-up (M4 Chunk 3) — same defer-never-drop rule
# --------------------------------------------------------------------------


def whatsapp_sends_today(session: Session, now: datetime) -> int:
    day_start = now.astimezone(timezone.utc).replace(hour=0, minute=0,
                                                     second=0, microsecond=0)
    return session.execute(
        select(func.count(Message.id)).where(
            Message.channel == ChannelType.WHATSAPP,
            Message.status == MessageStatus.SENT,
            Message.sent_at >= day_start,
        )
    ).scalar_one()


def whatsapp_daily_allowance(session: Session, on_date: date) -> int:
    """Warm-up ramp for the WhatsApp number, anchored to the date of the
    FIRST WhatsApp message ever sent (there is no per-user account row
    like Gmail's — one business number per deployment)."""
    first_sent = session.execute(
        select(func.min(Message.sent_at)).where(
            Message.channel == ChannelType.WHATSAPP,
            Message.status == MessageStatus.SENT,
        )
    ).scalar_one()
    if first_sent is None:
        return settings.whatsapp_warmup_start_sends
    first_date = first_sent.date() if isinstance(first_sent, datetime) else on_date
    age_days = max(0, (on_date - first_date).days)
    ramped = (settings.whatsapp_warmup_start_sends
              + settings.whatsapp_warmup_daily_increment * age_days)
    return min(settings.whatsapp_daily_cap, ramped)


def whatsapp_allowance_left(session: Session, now: datetime) -> int:
    return whatsapp_daily_allowance(
        session, now.astimezone(timezone.utc).date()
    ) - whatsapp_sends_today(session, now)


# --------------------------------------------------------------------------
# Enrollment lifecycle
# --------------------------------------------------------------------------


def enroll_leads(
    session: Session,
    sequence: Sequence,
    lead_statuses: list[LeadStatus] | None = None,
    now: datetime | None = None,
) -> int:
    """Enroll matching leads and schedule their step-1 message. Idempotent:
    already-enrolled leads are skipped (unique constraint backs this)."""
    now = now or _now()
    lead_statuses = lead_statuses or [LeadStatus.VERIFIED]
    steps = sorted(sequence.steps, key=lambda s: s.step_no)
    if not steps:
        raise ValueError("sequence has no steps")

    # Feature Group 5: a sequence that OPENS on LinkedIn needs a profile URL,
    # not an email -- a lead Apollo found no email for is still reachable.
    opens_on_linkedin = steps[0].effective_channel(sequence) is ChannelType.LINKEDIN
    address = Lead.linkedin_url.isnot(None) if opens_on_linkedin else Lead.email.isnot(None)
    leads = session.execute(
        select(Lead).where(
            Lead.strategy_id == sequence.strategy_id,
            Lead.status.in_(lead_statuses),
            address,
        )
    ).scalars().all()

    enrolled = 0
    existing = {
        e.lead_id for e in session.execute(
            select(SequenceEnrollment).where(SequenceEnrollment.sequence_id == sequence.id)
        ).scalars()
    }
    for lead in leads:
        if lead.id in existing or is_suppressed(session, lead.email, lead.phone,
                                                linkedin=lead.linkedin_url):
            continue
        enrollment = SequenceEnrollment(sequence_id=sequence.id, lead_id=lead.id)
        session.add(enrollment)
        session.flush()
        _schedule_step_message(session, sequence, enrollment, lead, steps[0], base_time=now)
        enrolled += 1
    session.commit()
    return enrolled


def stop_enrollment(session: Session, enrollment: SequenceEnrollment, reason: str) -> None:
    """HARD STOP. Cancels every pending message. Irreversible by design —
    a stopped enrollment can never send again."""
    enrollment.status = EnrollmentStatus.STOPPED
    enrollment.stop_reason = reason
    pending = session.execute(
        select(Message).where(
            Message.sequence_id == enrollment.sequence_id,
            Message.lead_id == enrollment.lead_id,
            Message.status.in_([MessageStatus.SCHEDULED, MessageStatus.SENDING]),
        )
    ).scalars().all()
    for msg in pending:
        msg.status = MessageStatus.CANCELLED
        msg.error = f"enrollment stopped: {reason}"
    session.commit()


def pause_enrollment(session: Session, enrollment: SequenceEnrollment,
                     until: datetime) -> None:
    """Soft pause (out-of-office): pending messages move past `until`."""
    enrollment.status = EnrollmentStatus.PAUSED
    enrollment.paused_until = until
    lead = session.get(Lead, enrollment.lead_id)
    pending = session.execute(
        select(Message).where(
            Message.sequence_id == enrollment.sequence_id,
            Message.lead_id == enrollment.lead_id,
            Message.status == MessageStatus.SCHEDULED,
        )
    ).scalars().all()
    for msg in pending:
        msg.scheduled_at = next_window_slot(until, lead_timezone(lead))
    session.commit()


def resume_due_enrollments(session: Session, now: datetime | None = None) -> int:
    now = now or _now()
    due = session.execute(
        select(SequenceEnrollment).where(
            SequenceEnrollment.status == EnrollmentStatus.PAUSED,
            SequenceEnrollment.paused_until <= now,
        )
    ).scalars().all()
    for e in due:
        e.status = EnrollmentStatus.ACTIVE
        e.paused_until = None
    session.commit()
    return len(due)


def _schedule_step_message(
    session: Session,
    sequence: Sequence,
    enrollment: SequenceEnrollment,
    lead: Lead,
    step: SequenceStep,
    base_time: datetime,
) -> Message:
    """Create the SCHEDULED message row for a step (body rendered at send
    time; the send task persists it before transmitting)."""
    when = next_window_slot(base_time + timedelta(days=step.delay_days if step.step_no > 1 else 0),
                            lead_timezone(lead))
    # Feature Group 3: with smart send time on, hold the step for the
    # campaign's next top engagement window (bounded; a no-op otherwise).
    from app.services import send_windows  # noqa: PLC0415

    when = send_windows.next_smart_slot(session, sequence.strategy, when,
                                        lead_timezone(lead), spread_key=lead.id)
    msg = Message(
        sequence_id=sequence.id,
        lead_id=lead.id,
        # M4 Chunk 3: the step's channel wins; NULL falls back to the
        # sequence's channel (all M3 sequences behave exactly as before).
        channel=step.effective_channel(sequence),
        step_no=step.step_no,
        template=step.template,
        variant=step.variant,
        whatsapp_kind=step.whatsapp_kind,
        whatsapp_template_id=step.whatsapp_template_id,
        status=MessageStatus.SCHEDULED,
        scheduled_at=when,
    )
    session.add(msg)
    session.commit()
    return msg


def schedule_next_step(session: Session, message: Message, now: datetime) -> Message | None:
    """After a successful send: schedule the following step, or complete
    the enrollment when there is none."""
    enrollment = session.execute(
        select(SequenceEnrollment).where(
            SequenceEnrollment.sequence_id == message.sequence_id,
            SequenceEnrollment.lead_id == message.lead_id,
        )
    ).scalar_one()
    enrollment.current_step = message.step_no

    sequence = session.get(Sequence, message.sequence_id)
    next_steps = [s for s in sequence.steps if s.step_no > message.step_no]
    if enrollment.status is not EnrollmentStatus.ACTIVE:
        session.commit()
        return None
    if not next_steps:
        enrollment.status = EnrollmentStatus.COMPLETED
        _flag_if_all_skipped(session, enrollment)
        session.commit()
        return None
    step = min(next_steps, key=lambda s: s.step_no)
    lead = session.get(Lead, message.lead_id)
    return _schedule_step_message(session, sequence, enrollment, lead, step, base_time=now)


def skip_message(session: Session, message: Message,
                 reason: str, now: datetime) -> Message | None:
    """M4 Chunk 3 engine rule: mark a message SKIPPED (with the reason,
    e.g. 'skipped_no_optin') and advance the sequence to its NEXT step —
    a lead without WhatsApp opt-in loses the WhatsApp touch, not the whole
    sequence. Returns the next scheduled message, if any."""
    message.status = MessageStatus.SKIPPED
    message.error = reason
    session.commit()
    logger.info("message %s skipped: %s (lead %s)",
                message.id, reason, message.lead_id)
    return schedule_next_step(session, message, now=now)


def _flag_if_all_skipped(session: Session, enrollment: SequenceEnrollment) -> None:
    """An enrollment that completed without a single successful send —
    every step skipped — is flagged for user attention via stop_reason
    (visible in the campaign overview); typical cause: an all-WhatsApp
    sequence and a lead who never opted in."""
    statuses = session.execute(
        select(Message.status).where(
            Message.sequence_id == enrollment.sequence_id,
            Message.lead_id == enrollment.lead_id,
        )
    ).scalars().all()
    if statuses and all(st is MessageStatus.SKIPPED for st in statuses):
        enrollment.stop_reason = "completed_all_skipped_needs_attention"


# --------------------------------------------------------------------------
# Compliant email assembly (chunk 3)
# --------------------------------------------------------------------------


def make_unsubscribe_token(lead_id: uuid.UUID) -> str:
    return crypto.encrypt_json({"lead_id": str(lead_id), "purpose": "unsubscribe"})


def parse_unsubscribe_token(token: str) -> uuid.UUID:
    data = crypto.decrypt_json(token)
    if data.get("purpose") != "unsubscribe":
        raise ValueError("not an unsubscribe token")
    return uuid.UUID(data["lead_id"])


def compliance_footer(unsubscribe_url: str) -> str:
    return (
        "\n\n--\n"
        f"{settings.sender_identity}\n"
        f"Don't want these emails? Unsubscribe instantly: {unsubscribe_url}"
    )


def build_compliant_email(lead: Lead, subject: str, body: str) -> tuple[str, str, dict, str]:
    """Returns (subject, body_with_footer, headers, token). Headers carry
    RFC 8058 one-click unsubscribe."""
    token = make_unsubscribe_token(lead.id)
    url = f"{settings.public_base_url.rstrip('/')}/unsubscribe/{token}"
    headers = {
        "List-Unsubscribe": f"<{url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }
    # Feature Group 9: GDPR / UK and CASL recipients get the notice their
    # regime asks for (right to object / sender + unsubscribe route).
    from app.services import compliance_audit  # noqa: PLC0415

    notice = compliance_audit.region_notice(lead)
    if notice:
        body = f"{body}\n\n{notice}"
    return subject, body + compliance_footer(url), headers, token


# --------------------------------------------------------------------------
# Unsubscribe + bounce handling (shared by endpoint, send task, replies)
# --------------------------------------------------------------------------


def _enrollments_for_lead(session: Session, lead_id: uuid.UUID) -> list[SequenceEnrollment]:
    return session.execute(
        select(SequenceEnrollment).where(SequenceEnrollment.lead_id == lead_id)
    ).scalars().all()


def _outcome(session: Session, lead: Lead, event: OutcomeEvent,
             message_id: uuid.UUID | None = None, meta: dict | None = None,
             channel: str = "email") -> None:
    session.add(Outcome(lead_id=lead.id, message_id=message_id, event=event,
                        channel=channel, meta_json=meta or {}))


def unsubscribe_lead(session: Session, lead: Lead, source: str,
                     message_id: uuid.UUID | None = None,
                     channel: str = "email") -> None:
    """One action for BOTH the unsubscribe click and an
    unsubscribe_request reply: instant suppression + hard stop."""
    if lead.email and not is_suppressed(session, email=lead.email):
        session.add(SuppressionEntry(email=lead.email.lower().strip(),
                                     reason=f"unsubscribed_{source}"))
    if lead.phone and not is_suppressed(session, phone=lead.phone):
        session.add(SuppressionEntry(phone=lead.phone.strip(),
                                     reason=f"unsubscribed_{source}"))
    # Feature Group 5: an opt-out on any channel covers LinkedIn too.
    if lead.linkedin_url and not is_suppressed(session, linkedin=lead.linkedin_url):
        from app.db.models import LinkedInSuppression  # noqa: PLC0415
        from app.services.linkedin_outreach import normalize_profile  # noqa: PLC0415

        profile = normalize_profile(lead.linkedin_url)
        if profile:
            session.add(LinkedInSuppression(profile=profile,
                                            reason=f"unsubscribed_{source}"))
    _outcome(session, lead, OutcomeEvent.UNSUBSCRIBED, message_id,
             {"source": source}, channel=channel)
    session.commit()
    for enrollment in _enrollments_for_lead(session, lead.id):
        if enrollment.status is not EnrollmentStatus.STOPPED:
            stop_enrollment(session, enrollment, reason="unsubscribed")
    session.commit()


def record_bounce(session: Session, lead: Lead, message: Message | None = None,
                  meta: dict | None = None, channel: str = "email") -> None:
    """Bounce: outcome + stop + drop lead + campaign bounce-rate check."""
    if message is not None:
        message.status = MessageStatus.BOUNCED
    lead.status = LeadStatus.DROPPED
    _outcome(session, lead, OutcomeEvent.BOUNCED,
             message.id if message else None, meta, channel=channel)
    session.commit()
    for enrollment in _enrollments_for_lead(session, lead.id):
        if enrollment.status is not EnrollmentStatus.STOPPED:
            stop_enrollment(session, enrollment, reason="bounced")
    strategy = session.get(Strategy, lead.strategy_id)
    check_bounce_rate(session, strategy)


def check_bounce_rate(session: Session, strategy: Strategy) -> bool:
    """Auto-pause the whole campaign above the threshold (config), once at
    least BOUNCE_MIN_SENDS messages have been sent. Returns True if paused."""
    sent = session.execute(
        select(func.count(Message.id))
        .join(Lead, Lead.id == Message.lead_id)
        .where(Lead.strategy_id == strategy.id,
               Message.status.in_([MessageStatus.SENT, MessageStatus.BOUNCED]))
    ).scalar_one()
    if sent < settings.bounce_min_sends:
        return False
    bounced = session.execute(
        select(func.count(Outcome.id))
        .join(Lead, Lead.id == Outcome.lead_id)
        .where(Lead.strategy_id == strategy.id, Outcome.event == OutcomeEvent.BOUNCED)
    ).scalar_one()
    rate = bounced / sent
    if rate > settings.bounce_rate_pause_threshold and strategy.campaign_state == CAMPAIGN_ACTIVE:
        strategy.campaign_state = CAMPAIGN_PAUSED_BOUNCE
        strategy.campaign_pause_reason = (
            f"bounce rate {rate:.1%} exceeded {settings.bounce_rate_pause_threshold:.0%} "
            f"({bounced}/{sent}) — human review required"
        )
        session.commit()
        logger.warning("campaign paused for strategy %s: %s",
                       strategy.id, strategy.campaign_pause_reason)

        # The owner has to know: an auto-paused campaign sends nothing until a
        # human resumes it. dispatch() never raises, so the pause stands even
        # if the push fails.
        from app.services import notifications  # noqa: PLC0415

        owner = notifications.owner_of_strategy(session, strategy)
        if owner is not None:
            notifications.dispatch(
                notifications.notify_campaign_paused(owner, strategy.id)
            )
            # Feature Group 4: Slack ("campaign auto-paused") + webhooks;
            # push=False because the M7 push above already went.
            from app.workers import notification_tasks  # noqa: PLC0415

            notification_tasks.enqueue_event(
                owner, "campaign_paused", push=False, title="Campaign auto-paused",
                body=strategy.campaign_pause_reason or "Bounce rate over the limit.",
                deep_link=f"/campaigns?strategy={strategy.id}",
                data={"strategyId": str(strategy.id)},
                webhook_payload={"strategy_id": str(strategy.id), "trigger": "bounce_rate",
                                 "reason": strategy.campaign_pause_reason,
                                 "bounce_rate": round(rate, 4)},
            )
        else:
            logger.warning("strategy %s has no resolvable owner - no pause "
                           "notification", strategy.id)
        return True
    return False


# --------------------------------------------------------------------------
# Engagement Hub (Feature 4) — a pending meeting pauses outreach
# --------------------------------------------------------------------------
#
# WHY PAUSE AND NOT STOP
# The M3 rule is that a booked meeting is a hard stop (see the module
# docstring, and app/api/webhooks.py where the Calendly path applies it). That
# is right for Calendly, where LeadPilot finds out a meeting exists and nothing
# ever tells it the meeting fell through: a link the invitee cancels produces a
# separate `invitee.canceled` delivery that may or may not arrive, so treating
# the booking as terminal is the safe reading.
#
# A booking made on LeadPilot's OWN calendar is different. We own the row. We
# know the moment it is cancelled, because the cancellation is a request to
# this API. So the honest state is PAUSED -- "do not send while a meeting is
# pending" -- and a cancelled meeting puts the lead back into the sequence
# where it left off, instead of stranding a warm lead in a state the engine
# defines as irreversible.
#
# stop_enrollment stays exactly as it is and keeps its irreversibility. This is
# an additional state, not a weakening of that one.

MEETING_PAUSE_REASON = "meeting_pending"

# How long after a meeting ends before the sequence is allowed to resume on
# its own. A day, because the useful outcome of a call is recorded by a human
# within a day of it happening (won, lost, replied), and any of those already
# stops the enrollment through the existing rules. This timer only matters for
# the call nobody wrote up -- and there, resuming outreach a full day later is
# better than never touching the lead again.
MEETING_PAUSE_GRACE = timedelta(days=1)


def pause_for_meeting(session: Session, lead: Lead,
                      until: datetime | None = None,
                      now: datetime | None = None) -> int:
    """Pause every ACTIVE enrollment for `lead` while a meeting is pending.

    Returns how many were paused. Never touches STOPPED enrollments -- a lead
    who unsubscribed and later booked through a colleague's link must not have
    their outreach quietly resurrected by this.

    `until` defaults to one day after `now`; callers that know the meeting's
    end time pass end + MEETING_PAUSE_GRACE, so the resume sweep
    (resume_due_enrollments, already run on every dispatch tick) picks the
    lead back up on its own if nothing else happened.
    """
    now = now or _now()
    until = until or (now + MEETING_PAUSE_GRACE)
    paused = 0
    for enrollment in _enrollments_for_lead(session, lead.id):
        if enrollment.status is not EnrollmentStatus.ACTIVE:
            continue
        pause_enrollment(session, enrollment, until=until)
        enrollment.stop_reason = MEETING_PAUSE_REASON
        paused += 1
    session.commit()
    if paused:
        logger.info("paused %d enrollment(s) for lead %s until %s "
                    "(meeting pending)", paused, lead.id, until.isoformat())
    return paused


def resume_after_meeting_cancelled(session: Session, lead: Lead,
                                   now: datetime | None = None) -> int:
    """Undo pause_for_meeting when the meeting is cancelled.

    Only resumes enrollments THIS feature paused -- the stop_reason check is
    what keeps a cancelled meeting from also un-pausing an out-of-office pause
    that has nothing to do with it, which would send into an inbox the engine
    has been told is unattended.
    """
    now = now or _now()
    resumed = 0
    for enrollment in _enrollments_for_lead(session, lead.id):
        if enrollment.status is not EnrollmentStatus.PAUSED:
            continue
        if enrollment.stop_reason != MEETING_PAUSE_REASON:
            continue
        enrollment.status = EnrollmentStatus.ACTIVE
        enrollment.paused_until = None
        enrollment.stop_reason = None
        # The pause pushed every scheduled message out to `paused_until`.
        # Pulling them back to the next send window is what makes "resume"
        # mean resume rather than "resume, tomorrow".
        pending = session.execute(
            select(Message).where(
                Message.sequence_id == enrollment.sequence_id,
                Message.lead_id == enrollment.lead_id,
                Message.status == MessageStatus.SCHEDULED,
            )
        ).scalars().all()
        for msg in pending:
            msg.scheduled_at = next_window_slot(now, lead_timezone(lead))
        resumed += 1
    session.commit()
    return resumed

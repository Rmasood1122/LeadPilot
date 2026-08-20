"""Outreach Celery tasks — dispatcher (Beat), idempotent send, reply polling.

The send task is the LAST LINE of compliance enforcement: it re-checks the
suppression list, the campaign state, the enrollment state, the send
window and the daily allowance immediately before transmitting — no
matter what was true when the message was scheduled. There is no bypass
flag anywhere in this codebase, by design.

All `_impl` functions take a Session + explicit `now` so the test suite
drives them deterministically with fakes and SQLite.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.base import SessionLocal
from app.db.models import (
    ChannelType,
    EnrollmentStatus,
    GmailAccount,
    InboundReply,
    Lead,
    LeadStatus,
    Message,
    MessageStatus,
    OptInSource,
    OptInStatus,
    Outcome,
    OutcomeEvent,
    Product,
    Sequence,
    SequenceEnrollment,
    Strategy,
    WhatsAppStepKind,
    WhatsAppTemplate,
    WhatsAppTemplateStatus,
)
from app.integrations.outreach_base import OutboundMessage, OutreachChannel
from app.services import sequence_engine as engine
from app.services.message_personalization import (
    preview_whatsapp_body,
    render_message,
    render_whatsapp_variables,
)
from app.services.reply_classification import classify_reply
from app.services import whatsapp_optin as optin_svc
from app.services.whatsapp_window import window_state_for_lead
from app.workers.celery_app import celery_app
from app.workers.lead_tasks import is_suppressed

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Channel/account resolution (tests monkeypatch _get_channel)
# --------------------------------------------------------------------------


def _account_for_strategy(session: Session, strategy: Strategy) -> GmailAccount:
    product = session.get(Product, strategy.product_id)
    account = session.execute(
        select(GmailAccount).where(GmailAccount.user_id == product.user_id)
    ).scalar_one_or_none()
    if account is None:
        raise RuntimeError(
            f"no connected Gmail account for user of strategy {strategy.id} — "
            "connect one via /integrations/gmail/auth-url first"
        )
    return account


def _get_channel(session: Session, account: GmailAccount) -> OutreachChannel:
    from app.integrations.gmail import GmailChannel
    return GmailChannel(account=account, session=session)


def _get_whatsapp_channel(session: Session) -> OutreachChannel:
    """Tests monkeypatch THIS function (like _get_channel for Gmail)."""
    from app.integrations.whatsapp import WhatsAppChannel
    return WhatsAppChannel(session=session)


# --------------------------------------------------------------------------
# Dispatcher (Celery Beat): find due messages, enqueue sends
# --------------------------------------------------------------------------


def dispatch_due_messages_impl(session: Session, now: datetime | None = None,
                               enqueue=None) -> list[str]:
    """Resume due paused enrollments, then enqueue every due SCHEDULED
    message whose campaign is active. Returns the enqueued message ids."""
    now = now or _now()
    enqueue = enqueue or (lambda mid: send_message.delay(mid))

    engine.resume_due_enrollments(session, now)

    rows = session.execute(
        select(Message, Strategy)
        .join(Lead, Lead.id == Message.lead_id)
        .join(Strategy, Strategy.id == Lead.strategy_id)
        .where(Message.status == MessageStatus.SCHEDULED,
               Message.scheduled_at <= now)
        .order_by(Message.scheduled_at)
    ).all()

    enqueued: list[str] = []
    for message, strategy in rows:
        if strategy.campaign_state != engine.CAMPAIGN_ACTIVE:
            continue  # paused campaigns send nothing
        enqueue(str(message.id))
        enqueued.append(str(message.id))
    return enqueued


# --------------------------------------------------------------------------
# The send task (idempotent, compliance-enforcing)
# --------------------------------------------------------------------------


def send_message_impl(session: Session, message_id: uuid.UUID,
                      channel: OutreachChannel | None = None,
                      now: datetime | None = None) -> str:
    now = now or _now()
    message = session.get(Message, message_id)
    if message is None:
        return "missing"

    # ---- idempotency guards: a retry can NEVER double-send ----------------
    if message.status is MessageStatus.SENT:
        return "already_sent"
    if message.status is MessageStatus.SENDING:
        # A previous attempt claimed it and may have transmitted before
        # crashing. Never resend automatically.
        logger.warning("message %s stuck in 'sending' — flagged, not resent", message_id)
        return "in_flight_needs_review"
    if message.status is not MessageStatus.SCHEDULED:
        return f"skipped_{message.status.value}"

    lead = session.get(Lead, message.lead_id)
    sequence = session.get(Sequence, message.sequence_id)
    strategy = session.get(Strategy, lead.strategy_id)
    enrollment = session.execute(
        select(SequenceEnrollment).where(
            SequenceEnrollment.sequence_id == message.sequence_id,
            SequenceEnrollment.lead_id == message.lead_id,
        )
    ).scalar_one_or_none()

    # ---- hard gates (checked at SEND time, always) -------------------------
    if strategy.campaign_state != engine.CAMPAIGN_ACTIVE:
        return "campaign_paused"
    if enrollment is None or enrollment.status is EnrollmentStatus.STOPPED:
        message.status = MessageStatus.CANCELLED
        message.error = "enrollment stopped"
        session.commit()
        return "cancelled_stopped"
    if enrollment.status is EnrollmentStatus.PAUSED:
        return "enrollment_paused"
    is_whatsapp = message.channel is ChannelType.WHATSAPP
    target = lead.phone if is_whatsapp else lead.email
    if not target or is_suppressed(session, lead.email, lead.phone):
        message.status = MessageStatus.CANCELLED
        message.error = "suppressed at send time" if target else "no address for channel"
        session.commit()
        if enrollment.status is not EnrollmentStatus.STOPPED:
            engine.stop_enrollment(session, enrollment, reason="suppressed")
        return "cancelled_suppressed"

    # ---- WhatsApp engine rules (defense in depth — the adapter's own
    # guard re-checks all of this; the ENGINE checks it too so a lead
    # without opt-in is SKIPPED and the sequence continues, rather than
    # the whole sequence dying on a ComplianceError) --------------------------
    if is_whatsapp:
        if optin_svc.current_status(session, lead.id) is not OptInStatus.OPTED_IN:
            engine.skip_message(session, message, reason="skipped_no_optin", now=now)
            return "skipped_no_optin"

        if message.whatsapp_kind is WhatsAppStepKind.TEXT:
            # Free-form: re-check the 24h window at ACTUAL send time. A
            # message queued while the window was open but expired by now
            # fails CLOSED into needs_template — never silently sent.
            state = window_state_for_lead(lead, now)
            if not state.open:
                message.status = MessageStatus.NEEDS_TEMPLATE
                message.error = (
                    "24h customer-service window closed before send — "
                    "convert this step to an approved template or wait "
                    "for the lead to message again"
                )
                session.commit()
                return "needs_template_window_closed"
        else:
            # Template step: the referenced template must STILL be
            # approved at send time (it may have been rejected or
            # superseded since scheduling).
            tmpl = (session.get(WhatsAppTemplate, message.whatsapp_template_id)
                    if message.whatsapp_template_id else None)
            if tmpl is None or tmpl.status is not WhatsAppTemplateStatus.APPROVED:
                message.status = MessageStatus.NEEDS_TEMPLATE
                message.error = (
                    "referenced template is missing or no longer approved "
                    "— re-submit or pick an approved template"
                )
                session.commit()
                return "needs_template_not_approved"

    # ---- send window --------------------------------------------------------
    tz = engine.lead_timezone(lead)
    if not engine.in_send_window(now, tz):
        message.scheduled_at = engine.next_window_slot(now, tz)
        session.commit()
        return "deferred_window"

    # ---- daily cap + warm-up (per channel; deferred, never dropped) ---------
    if is_whatsapp:
        account = None
        if engine.whatsapp_allowance_left(session, now) <= 0:
            tomorrow = now.astimezone(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)
            message.scheduled_at = engine.next_window_slot(tomorrow, tz)
            session.commit()
            return "deferred_cap"
    else:
        account = _account_for_strategy(session, strategy)
        if engine.allowance_left(session, account, now) <= 0:
            tomorrow = now.astimezone(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)
            message.scheduled_at = engine.next_window_slot(tomorrow, tz)
            session.commit()
            return "deferred_cap"

    # ---- claim (scheduled -> sending), render, persist BEFORE transmit ----
    message.status = MessageStatus.SENDING
    message.sender_ref = (
        f"whatsapp:{settings.whatsapp_phone_number_id}" if is_whatsapp
        else str(account.id)
    )
    session.commit()

    try:
        if is_whatsapp:
            outbound = _render_whatsapp_outbound(session, strategy, lead,
                                                 message, now)
        else:
            outbound = _render_email_outbound(session, strategy, lead,
                                              sequence, message)
        session.commit()  # rendered content persisted before the send

        if channel is None:
            channel = (_get_whatsapp_channel(session) if is_whatsapp
                       else _get_channel(session, account))
        result = channel.send(outbound)
    except Exception as exc:
        # Import from the canonical module, not from the adapter. whatsapp.py
        # used to declare its own ComplianceError and this caught THAT class;
        # now there is only one, which also means this branch would catch a
        # compliance block raised on the EMAIL render path, so the resulting
        # status has to depend on the channel: NEEDS_TEMPLATE is a WhatsApp
        # state and would be nonsense on an email row.
        from app.core.exceptions import ComplianceError
        if isinstance(exc, ComplianceError):
            # A compliance guard fired (suppression/opt-in/window/template).
            # Never retried — surfaced for attention.
            message.status = (MessageStatus.NEEDS_TEMPLATE if is_whatsapp
                              else MessageStatus.FAILED)
            message.error = f"ComplianceError: {exc}"
            session.commit()
            return "blocked_compliance"
        message.status = MessageStatus.SCHEDULED  # transient: retry later
        message.error = f"{type(exc).__name__}: {exc}"
        session.commit()
        raise

    if not result.ok:
        if result.permanent_failure:
            message.status = MessageStatus.FAILED
            message.error = result.error
            session.commit()
            return "failed_permanent"
        message.status = MessageStatus.SCHEDULED
        message.error = result.error
        session.commit()
        return "failed_transient"

    message.status = MessageStatus.SENT
    message.sent_at = now
    message.provider_message_id = result.provider_message_id
    message.thread_ref = result.thread_ref
    session.add(Outcome(lead_id=lead.id, message_id=message.id,
                        event=OutcomeEvent.SENT,
                        channel=message.channel.value,
                        meta_json={"step_no": message.step_no, "variant": message.variant}))
    if lead.status in (LeadStatus.VERIFIED, LeadStatus.FLAGGED):
        lead.status = LeadStatus.CONTACTED
    session.commit()

    engine.schedule_next_step(session, message, now=now)
    return "sent"


def _render_email_outbound(session: Session, strategy: Strategy, lead: Lead,
                           sequence: Sequence, message: Message) -> OutboundMessage:
    # Tag the scheduling link with the owning tenant so the Calendly webhook
    # can resolve the booking back to THIS account instead of guessing by
    # email across every tenant. This is the only place a booking link reaches
    # a lead (the WhatsApp text path passes booking_url=None, and templates
    # carry no scheduling link), so tagging here covers all outbound links.
    from app.integrations.calendly import tag_booking_url  # noqa: PLC0415
    from app.services import notifications  # noqa: PLC0415

    booking_url = tag_booking_url(
        sequence.booking_url, notifications.owner_of_strategy(session, strategy)
    )
    subject, body = render_message(session, strategy, lead,
                                   _step_of(session, message), booking_url)
    subject, body, headers, token = engine.build_compliant_email(lead, subject, body)
    message.subject = subject
    message.body = body
    message.unsubscribe_token = token
    return OutboundMessage(
        message_id=str(message.id),
        lead_id=str(lead.id),
        to_address=lead.email,
        subject=subject,
        body=body,
        headers=headers,
        thread_ref=_thread_ref_for_followup(session, message),
    )


def _render_whatsapp_outbound(session: Session, strategy: Strategy, lead: Lead,
                              message: Message, now: datetime) -> OutboundMessage:
    """Build the WhatsApp OutboundMessage: template variables filled via
    the same personalization path as email, rendered preview persisted on
    the row BEFORE transmit."""
    if message.whatsapp_kind is WhatsAppStepKind.TEXT:
        # Reply-handling step inside an open window: the step brief is
        # rendered by the same email personalizer minus subject.
        _, body = render_message(session, strategy, lead,
                                 _step_of(session, message), None)
        message.body = body
        return OutboundMessage(
            message_id=str(message.id),
            lead_id=str(lead.id),
            to_address=lead.phone,
            body=body,
            metadata={"kind": "text"},
        )

    tmpl = session.get(WhatsAppTemplate, message.whatsapp_template_id)
    step = _step_of(session, message)
    values = render_whatsapp_variables(
        session, strategy, lead,
        template_body=tmpl.body or "",
        variable_descriptions=tmpl.variable_descriptions_json or {},
        variable_mapping=getattr(step, "variable_mapping_json", None),
    )
    message.body = preview_whatsapp_body(tmpl.body or "", values)
    components = []
    if values:
        components = [{
            "type": "body",
            # TODO: verify against current WhatsApp Cloud API docs
            # (parameters array: [{"type": "text", "text": ...}, ...]
            # ordered by variable number)
            "parameters": [
                {"type": "text", "text": values[n]}
                for n in sorted(values, key=lambda x: int(x))
            ],
        }]
    return OutboundMessage(
        message_id=str(message.id),
        lead_id=str(lead.id),
        to_address=lead.phone,
        body=message.body,
        metadata={
            "kind": "template",
            "template_name": tmpl.name,
            "language": tmpl.language,
            "components": components,
        },
    )


def _step_of(session: Session, message: Message):
    from app.db.models import SequenceStep
    step = session.execute(
        select(SequenceStep).where(SequenceStep.sequence_id == message.sequence_id,
                                   SequenceStep.step_no == message.step_no)
    ).scalar_one_or_none()
    if step is not None:
        return step
    # Step edited/removed after scheduling: fall back to the snapshot.
    return SequenceStep(sequence_id=message.sequence_id, step_no=message.step_no,
                        template=message.template, variant=message.variant, delay_days=0)


def _thread_ref_for_followup(session: Session, message: Message) -> str | None:
    if message.step_no <= 1:
        return None
    prev = session.execute(
        select(Message).where(Message.sequence_id == message.sequence_id,
                              Message.lead_id == message.lead_id,
                              Message.step_no < message.step_no,
                              Message.thread_ref.isnot(None))
        .order_by(Message.step_no.desc())
    ).scalars().first()
    return prev.thread_ref if prev else None


# --------------------------------------------------------------------------
# Reply polling + routing (chunk 4)
# --------------------------------------------------------------------------


def poll_account_replies_impl(session: Session, account: GmailAccount,
                              channel: OutreachChannel | None = None,
                              now: datetime | None = None) -> int:
    now = now or _now()
    channel = channel or _get_channel(session, account)
    since = account.last_poll_at or (now - timedelta(days=2))
    inbound = channel.fetch_replies(since=since)
    handled = 0
    for msg in inbound:
        route_inbound_impl(session, msg, account)
        handled += 1
    account.last_poll_at = now
    session.commit()
    return handled


def _notify_new_reply(session: Session, lead: Lead) -> None:
    """Push "new reply" to the lead's owner. Shared by the email and WhatsApp
    inbound routers so both resolve the recipient the same way."""
    from app.services import notifications  # noqa: PLC0415

    owner = notifications.owner_of_lead(session, lead)
    if owner is None:
        logger.warning("lead %s has no resolvable owner - no reply notification",
                       lead.id)
        return
    notifications.dispatch(
        notifications.notify_new_reply(owner, lead.id, company=lead.company)
    )


def route_inbound_impl(session: Session, inbound, account: GmailAccount) -> str:
    """Match an inbound message to a lead and apply the routing rules.
    Never auto-replies to humans."""
    # Every lookup below is scoped to the leads owned by the user whose Gmail
    # account received this message. Both used to be global: an inbound reply
    # was matched to the FIRST lead anywhere in the database with that address
    # (`select(Lead).where(Lead.email == ...)`, no tenancy filter). If two
    # customers prospected the same person - routine in B2B - a reply landing
    # in one account's inbox flipped the other customer's lead to REPLIED,
    # stopped their sequences, wrote a REPLIED outcome into their learning
    # loop, and on an "unsubscribe_request" suppressed their lead. This is the
    # same cross-tenant matching class Phase A fixed in whatsapp_optin.py.
    owned_lead_ids = (
        select(Lead.id)
        .join(Strategy, Strategy.id == Lead.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == account.user_id)
    )

    matched_message: Message | None = None
    if inbound.thread_ref:
        matched_message = session.execute(
            select(Message)
            .where(Message.thread_ref == inbound.thread_ref,
                   Message.lead_id.in_(owned_lead_ids))
            .order_by(Message.step_no.desc())
        ).scalars().first()

    lead: Lead | None = None
    if matched_message is not None:
        lead = session.get(Lead, matched_message.lead_id)
    elif inbound.from_address:
        addr = inbound.from_address.strip()
        lead = session.execute(
            select(Lead).where(Lead.email == addr.lower(),
                               Lead.id.in_(owned_lead_ids))
        ).scalars().first() or session.execute(
            select(Lead).where(Lead.email == inbound.from_address,
                               Lead.id.in_(owned_lead_ids))
        ).scalars().first()

    classification = classify_reply(inbound.from_address, inbound.subject, inbound.body)

    session.add(InboundReply(
        lead_id=lead.id if lead else None,
        message_id=matched_message.id if matched_message else None,
        account_ref=str(account.id),
        channel="email",
        thread_ref=inbound.thread_ref,
        from_address=inbound.from_address,
        subject=inbound.subject,
        body=inbound.body,
        classification=classification,
        received_at=inbound.received_at,
    ))
    session.commit()

    if lead is None:
        return f"unmatched_{classification}"

    enrollments = [
        e for e in session.execute(
            select(SequenceEnrollment).where(SequenceEnrollment.lead_id == lead.id)
        ).scalars()
    ]

    if classification == "unsubscribe_request":
        # Treated EXACTLY like an unsubscribe click — immediately.
        engine.unsubscribe_lead(session, lead, source="reply",
                                message_id=matched_message.id if matched_message else None)
        return classification

    if classification == "bounce":
        engine.record_bounce(session, lead, matched_message,
                             meta={"from": inbound.from_address})
        return classification

    if classification == "out_of_office":
        until = (inbound.received_at or datetime.now(timezone.utc)) + timedelta(
            days=settings.ooo_reschedule_days
        )
        for e in enrollments:
            if e.status is EnrollmentStatus.ACTIVE:
                engine.pause_enrollment(session, e, until=until)
        return classification

    # interested / question / objection / not_interested → stop + record
    for e in enrollments:
        if e.status is not EnrollmentStatus.STOPPED:
            engine.stop_enrollment(session, e, reason=f"replied_{classification}")
    lead.status = LeadStatus.REPLIED
    session.add(Outcome(lead_id=lead.id,
                        message_id=matched_message.id if matched_message else None,
                        event=OutcomeEvent.REPLIED,
                        channel="email",
                        meta_json={"classification": classification}))
    session.commit()
    # A human replied - tell the lead's owner. dispatch() never raises, so a
    # push failure cannot undo the stop/outcome writes above.
    _notify_new_reply(session, lead)

    return classification


def route_whatsapp_inbound_impl(session: Session, lead: Lead,
                                reply: InboundReply) -> str:
    """Classify a non-STOP inbound WhatsApp message with the SAME Claude
    classifier as email and apply the SAME unified stop rules (M4 Chunk 3):
    a WhatsApp reply stops the WHOLE sequence — including pending cold
    email steps — because engine.stop_enrollment stops enrollments, not
    channels. WhatsApp delivery failures never arrive here (Meta reports
    them via status webhooks, already mapped to the bounce path), but the
    'bounce' class is still handled for robustness.
    Never auto-replies to humans."""
    classification = classify_reply(reply.from_address, None, reply.body)
    reply.classification = classification
    session.commit()

    enrollments = [
        e for e in session.execute(
            select(SequenceEnrollment).where(SequenceEnrollment.lead_id == lead.id)
        ).scalars()
    ]

    if classification == "unsubscribe_request":
        # A phrased opt-out the keyword matcher missed — same effect as
        # STOP: audit row + suppression on both identifiers + full stop.
        optin_svc.revoke_opt_in(session, lead, source=OptInSource.INBOUND_MESSAGE,
                                evidence=f"classified unsubscribe_request "
                                         f"(inbound reply {reply.id})")
        engine.unsubscribe_lead(session, lead, source="whatsapp_reply",
                                channel="whatsapp")
        return classification

    if classification == "bounce":
        engine.record_bounce(session, lead, None,
                             meta={"from": reply.from_address},
                             channel="whatsapp")
        return classification

    if classification == "out_of_office":
        until = (reply.received_at or datetime.now(timezone.utc)) + timedelta(
            days=settings.ooo_reschedule_days
        )
        for e in enrollments:
            if e.status is EnrollmentStatus.ACTIVE:
                engine.pause_enrollment(session, e, until=until)
        return classification

    # interested / question / objection / not_interested -> stop EVERYTHING
    for e in enrollments:
        if e.status is not EnrollmentStatus.STOPPED:
            engine.stop_enrollment(session, e, reason=f"replied_{classification}")
    lead.status = LeadStatus.REPLIED
    session.add(Outcome(lead_id=lead.id, event=OutcomeEvent.REPLIED,
                        channel="whatsapp",
                        meta_json={"classification": classification}))
    session.commit()
    # A human replied - tell the lead's owner. dispatch() never raises, so a
    # push failure cannot undo the stop/outcome writes above.
    _notify_new_reply(session, lead)

    return classification


# --------------------------------------------------------------------------
# Celery wrappers + Beat entry points
# --------------------------------------------------------------------------


@celery_app.task(name="leadpilot.outreach.dispatch")
def dispatch_due_messages() -> int:
    session = SessionLocal()
    try:
        return len(dispatch_due_messages_impl(session))
    finally:
        session.close()


@celery_app.task(name="leadpilot.outreach.send", bind=True, max_retries=3)
def send_message(self, message_id: str) -> str:
    session = SessionLocal()
    try:
        return send_message_impl(session, uuid.UUID(message_id))
    except Exception as exc:
        session.rollback()
        logger.exception("send failed for message %s — retrying", message_id)
        raise self.retry(exc=exc, countdown=60)
    finally:
        session.close()


@celery_app.task(name="leadpilot.outreach.poll_replies")
def poll_replies() -> int:
    session = SessionLocal()
    try:
        total = 0
        for account in session.execute(select(GmailAccount)).scalars().all():
            try:
                total += poll_account_replies_impl(session, account)
            except Exception:
                logger.exception("reply polling failed for account %s", account.id)
        return total
    finally:
        session.close()

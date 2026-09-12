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
from app.services import message_personalization as personalization
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
                      now: datetime | None = None,
                      outcome_source: str | None = None) -> str:
    """Send one message, re-checking every compliance gate at send time.

    `outcome_source` tags the OutcomeEvent.SENT row this writes with WHY the
    send happened. It is None for the ordinary scheduled path (whose outcome
    meta stays byte-identical to what M3 wrote, so the learning loop's
    existing aggregates are untouched) and "auto_followup" when Feature 1's
    sweep drove it -- which is what makes an automatic send distinguishable
    from a sequenced one in the audit trail and in the learning loop.
    """
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
    # Feature Group 5: the LinkedIn channel addresses the lead's profile.
    is_linkedin = message.channel is ChannelType.LINKEDIN
    # Feature Group 6: the phone channel dials the lead's number.
    is_phone = message.channel is ChannelType.PHONE
    target = (lead.phone if (is_whatsapp or is_phone)
              else lead.linkedin_url if is_linkedin else lead.email)
    if not target or is_suppressed(session, lead.email, lead.phone,
                                   linkedin=lead.linkedin_url):
        message.status = MessageStatus.CANCELLED
        message.error = "suppressed at send time" if target else "no address for channel"
        _audit(session, strategy, lead, message,
               "blocked_suppressed" if target else "blocked_no_address")
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
            _audit(session, strategy, lead, message, "skipped_no_consent")
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
    li_account = li_action = None
    if is_linkedin:
        # Profile lookup, connect/message/InMail decision, account rotation
        # and the per-account daily ceiling -- see _prepare_linkedin.
        account = None
        prepared = _prepare_linkedin(session, strategy, lead, message, now, tz)
        if isinstance(prepared, str):
            return prepared
        li_account, li_action = prepared
    elif is_phone:
        # Admin switch, consent, dialable number, provider, daily call cap --
        # see _prepare_phone. The send window above already bounds calling
        # hours to the lead's local business day.
        account = None
        stopped = _prepare_phone(session, strategy, lead, message, now, tz)
        if stopped is not None:
            return stopped
    elif is_whatsapp:
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
    if is_linkedin:
        message.sender_ref = f"linkedin:{li_account.id}"
        message.linkedin_account_id = li_account.id
        message.linkedin_action = li_action
    elif is_phone:
        message.sender_ref = "phone:ai_voice"
    else:
        message.sender_ref = (
            f"whatsapp:{settings.whatsapp_phone_number_id}" if is_whatsapp
            else str(account.id)
        )
    session.commit()

    try:
        if is_linkedin:
            outbound = _render_linkedin_outbound(session, strategy, lead, message,
                                                 li_account, li_action)
        elif is_phone:
            outbound = _render_phone_outbound(session, strategy, lead, message)
        elif is_whatsapp:
            outbound = _render_whatsapp_outbound(session, strategy, lead,
                                                 message, now)
        else:
            outbound = _render_email_outbound(session, strategy, lead,
                                              sequence, message)
        session.commit()  # rendered content persisted before the send

        if channel is None:
            if is_linkedin:
                channel = _get_linkedin_channel(session, strategy)
            elif is_phone:
                channel = _get_phone_channel(session, strategy)
            else:
                channel = (_get_whatsapp_channel(session) if is_whatsapp
                           else _get_channel(session, account))
        result = channel.send(outbound)
    except Exception as exc:
        if li_account is not None:
            # A request LinkedIn never received is not usage.
            from app.services import linkedin_limits  # noqa: PLC0415

            linkedin_limits.release(li_account, li_action, now=now)
        if is_phone:
            # The call was never placed: mark it failed and give the daily
            # call slot back.
            _phone_send_failed(session, strategy, message,
                               f"{type(exc).__name__}: {exc}", now)
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
        if li_account is not None:
            from app.services import linkedin_limits  # noqa: PLC0415

            linkedin_limits.release(li_account, li_action, now=now)
        if is_phone:
            _phone_send_failed(session, strategy, message, result.error or "call failed", now)
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
    if li_account is not None:
        from app.services import linkedin_outreach  # noqa: PLC0415

        linkedin_outreach.after_send(session, lead, li_account, li_action, result, now)
    if is_phone:
        # "Sent" = the call was placed. What happened on it arrives on the
        # provider's webhook (app/api/calls.py).
        from app.services import phone_calls  # noqa: PLC0415

        call = phone_calls.call_for_message(session, message)
        if call is not None:
            call.provider_call_id = result.provider_message_id
            call.provider = (result.raw or {}).get("provider") or call.provider
            call.status = "ringing"
    sent_meta = {"step_no": message.step_no, "variant": message.variant}
    if outcome_source:
        sent_meta["source"] = outcome_source
    session.add(Outcome(lead_id=lead.id, message_id=message.id,
                        event=OutcomeEvent.SENT,
                        channel=message.channel.value,
                        meta_json=sent_meta))
    if lead.status in (LeadStatus.VERIFIED, LeadStatus.FLAGGED):
        lead.status = LeadStatus.CONTACTED
    # Feature Group 9: the region, regime and checks behind this send, in the
    # same commit as the send itself.
    _audit(session, strategy, lead, message, "sent")
    session.commit()

    engine.schedule_next_step(session, message, now=now)
    return "sent"


def _audit(session: Session, strategy: Strategy, lead: Lead, message: Message,
           decision: str) -> None:
    """Add a compliance_audit_log row (committed by the caller). Never raises:
    an audit failure must not turn into a send that silently did not happen."""
    try:
        from app.services import compliance_audit, notifications  # noqa: PLC0415

        compliance_audit.record(session, lead=lead, message=message,
                                channel=message.channel.value, decision=decision,
                                user_id=notifications.owner_of_strategy(session, strategy))
    except Exception:
        logger.exception("compliance audit for message %s failed", message.id)


def _render_email_outbound(session: Session, strategy: Strategy, lead: Lead,
                           sequence: Sequence, message: Message) -> OutboundMessage:
    # Tag the scheduling link with the owning tenant so the Calendly webhook
    # can resolve the booking back to THIS account instead of guessing by
    # email across every tenant. This is the only place a booking link reaches
    # a lead (the WhatsApp text path passes booking_url=None, and templates
    # carry no scheduling link), so tagging here covers all outbound links.
    from app.integrations.calendly import tag_booking_url  # noqa: PLC0415
    from app.services import notifications  # noqa: PLC0415

    from app.services import personalization_context  # noqa: PLC0415

    owner_id = notifications.owner_of_strategy(session, strategy)
    # Feature Group 2: refresh the lead's recent posts / company news if stale,
    # right before writing. Never raises -- a failed fetch means an email
    # without that hook, never a send that did not happen.
    personalization_context.ensure_fresh(session, lead, owner_id=owner_id)
    booking_url = tag_booking_url(sequence.booking_url, owner_id)
    used: dict = {}
    subject, body = render_message(session, strategy, lead,
                                   _step_of(session, message), booking_url,
                                   inputs_out=used)
    subject, body, headers, token = engine.build_compliant_email(lead, subject, body)
    message.subject = subject
    message.body = body
    message.unsubscribe_token = token
    message.personalization_json = used or None
    # Feature Group 3: an HTML twin of the same text carrying the open pixel,
    # unless tracking is off or the lead is in the EU/EEA/UK.
    from app.services import open_tracking  # noqa: PLC0415

    metadata = {}
    if open_tracking.tracking_enabled(session, lead):
        metadata["html_body"] = open_tracking.html_body(
            body, open_tracking.pixel_url(message.id))
    return OutboundMessage(
        message_id=str(message.id),
        lead_id=str(lead.id),
        to_address=lead.email,
        subject=subject,
        body=body,
        headers=headers,
        thread_ref=_thread_ref_for_followup(session, message),
        metadata=metadata,
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


# --------------------------------------------------------------------------
# Feature Group 5 — LinkedIn
# --------------------------------------------------------------------------


def _get_linkedin_channel(session: Session, strategy: Strategy) -> OutreachChannel:
    """Tests monkeypatch THIS function (like _get_channel for Gmail)."""
    from app.integrations.linkedin_channel import LinkedInChannel  # noqa: PLC0415
    from app.services import linkedin_outreach, notifications  # noqa: PLC0415

    owner = notifications.owner_of_strategy(session, strategy)
    return LinkedInChannel(session=session,
                           client=linkedin_outreach.client_for(session, owner))


def _prepare_linkedin(session: Session, strategy: Strategy, lead: Lead,
                      message: Message, now: datetime, tz: str):
    """Everything a LinkedIn send decides before it may claim the message.

    Returns (account, action) with the account's daily slot RESERVED, or a
    status string when the send ends here:
      failed_linkedin_not_configured   no Unipile credentials (permanent)
      failed_no_linkedin_account       the owner has no active account
      failed_linkedin_account_gone     the account that owns this lead's
                                       conversation was disconnected
      skipped_linkedin_not_connected   a message step, request still pending
                                       (the sequence continues, like a
                                       WhatsApp step for a lead without opt-in)
      deferred_cap                     every eligible account is at its ceiling
    """
    from app.services import linkedin_limits, notifications  # noqa: PLC0415
    from app.services import linkedin_outreach as li  # noqa: PLC0415

    def _fail(code: str, reason: str) -> str:
        message.status = MessageStatus.FAILED
        message.error = reason
        session.commit()
        return code

    owner = notifications.owner_of_strategy(session, strategy)
    client = li.client_for(session, owner)
    if client is None:
        return _fail("failed_linkedin_not_configured",
                     "LinkedIn is not configured (Admin > Integrations > Unipile)")
    if not li.active_accounts(session, owner):
        return _fail("failed_no_linkedin_account",
                     "no active LinkedIn account connected (Settings > Integrations)")
    pinned = li.relationship_account(session, lead)
    if lead.linkedin_account_id and (pinned is None or not pinned.is_active):
        return _fail("failed_linkedin_account_gone",
                     "the LinkedIn account that owns this conversation is "
                     "disconnected -- reconnect it to continue")

    li.refresh_profile(session, client, lead, owner)   # raises -> task retry
    action = li.resolve_action(_step_of(session, message).linkedin_action, lead)
    if action == li.WAIT:
        engine.skip_message(session, message, reason="skipped_linkedin_not_connected", now=now)
        return "skipped_linkedin_not_connected"

    account = linkedin_limits.pick_account(session, owner, action,
                                           required_account_id=lead.linkedin_account_id,
                                           now=now)
    if account is None and action == "inmail" and lead.linkedin_connection_status is None:
        # No InMail-capable account with credits: a connection request is the
        # next best first touch.
        action = "connect"
        account = linkedin_limits.pick_account(session, owner, action,
                                               required_account_id=lead.linkedin_account_id,
                                               now=now)
    if account is None:
        tomorrow = now.astimezone(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        message.scheduled_at = engine.next_window_slot(tomorrow, tz)
        session.commit()
        return "deferred_cap"
    return account, action


def _render_linkedin_outbound(session: Session, strategy: Strategy, lead: Lead,
                              message: Message, account, action: str) -> OutboundMessage:
    from app.services import linkedin_outreach  # noqa: PLC0415

    rendered = linkedin_outreach.render(session, strategy, lead,
                                        _step_of(session, message), action)
    message.body = rendered["text"]
    message.subject = rendered.get("subject")
    return OutboundMessage(
        message_id=str(message.id),
        lead_id=str(lead.id),
        to_address=lead.linkedin_provider_id or lead.linkedin_url,
        body=rendered["text"],
        subject=rendered.get("subject"),
        thread_ref=lead.linkedin_chat_id,
        metadata={"action": action, "account_id": account.unipile_account_id,
                  "provider_id": lead.linkedin_provider_id,
                  "chat_id": lead.linkedin_chat_id},
    )


# --------------------------------------------------------------------------
# Feature Group 6 — AI phone calls
# --------------------------------------------------------------------------


def _get_phone_channel(session: Session, strategy: Strategy) -> OutreachChannel:
    """Tests monkeypatch THIS function."""
    from app.integrations import voice_providers  # noqa: PLC0415
    from app.integrations.phone_channel import PhoneChannel  # noqa: PLC0415
    from app.services import notifications  # noqa: PLC0415

    vapi, eleven = voice_providers.get_clients(
        session, notifications.owner_of_strategy(session, strategy))
    return PhoneChannel(session=session, vapi=vapi, eleven=eleven)


def _prepare_phone(session: Session, strategy: Strategy, lead: Lead, message: Message,
                   now: datetime, tz: str) -> str | None:
    """The phone channel's gates. None = proceed (a call slot is reserved);
    a status string = the send ends here:
      failed_calling_disabled         the admin has not enabled AI calling
      failed_bad_number               the number cannot be dialled
      skipped_no_call_consent         no recorded consent (sequence continues)
      failed_calling_not_configured   no Vapi / ElevenLabs credentials
      deferred_cap                    the owner's daily call limit is reached
    See app/services/phone_calls.py for why consent is required.
    """
    from app.integrations import voice_providers  # noqa: PLC0415
    from app.services import notifications, phone_calls, system_settings  # noqa: PLC0415

    def _fail(code: str, reason: str) -> str:
        message.status = MessageStatus.FAILED
        message.error = reason
        session.commit()
        return code

    if not system_settings.get(session, "phone_calling_enabled"):
        return _fail("failed_calling_disabled", "AI calling is disabled (Admin > System Settings)")
    if not phone_calls.e164(lead.phone):
        return _fail("failed_bad_number", "the lead's phone number cannot be dialled")
    if not phone_calls.consent_ok(session, lead):
        engine.skip_message(session, message, reason="skipped_no_call_consent", now=now)
        return "skipped_no_call_consent"
    owner = notifications.owner_of_strategy(session, strategy)
    vapi, eleven = voice_providers.get_clients(session, owner)
    if vapi is None and not (eleven is not None and eleven.can_call):
        return _fail("failed_calling_not_configured",
                     "no AI voice provider configured (Admin > Integrations > Vapi / ElevenLabs)")
    if not phone_calls.reserve_call_slot(session, owner, now=now):
        tomorrow = now.astimezone(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        message.scheduled_at = engine.next_window_slot(tomorrow, tz)
        session.commit()
        return "deferred_cap"
    return None


def _render_phone_outbound(session: Session, strategy: Strategy, lead: Lead,
                           message: Message) -> OutboundMessage:
    from app.services import notifications, phone_calls  # noqa: PLC0415

    owner = notifications.owner_of_strategy(session, strategy)
    call, meta = phone_calls.prepare_call(session, strategy, lead,
                                          _step_of(session, message).template,
                                          owner_id=owner, message=message)
    message.body = call.script_json["first_message"]
    message.subject = None
    return OutboundMessage(message_id=str(message.id), lead_id=str(lead.id),
                           to_address=call.to_number, body=message.body, metadata=meta)


def _phone_send_failed(session: Session, strategy: Strategy, message: Message,
                       error: str, now: datetime) -> None:
    from app.services import notifications, phone_calls  # noqa: PLC0415

    phone_calls.mark_send_failed(session, phone_calls.call_for_message(session, message),
                                 error, notifications.owner_of_strategy(session, strategy), now)


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


def _notify_new_reply(session: Session, lead: Lead, classification: str | None = None,
                      channel: str = "email") -> None:
    """Push "new reply" to the lead's owner. Shared by the email, WhatsApp and
    LinkedIn inbound routers so all resolve the recipient the same way."""
    from app.services import notifications  # noqa: PLC0415

    owner = notifications.owner_of_lead(session, lead)
    if owner is None:
        logger.warning("lead %s has no resolvable owner - no reply notification",
                       lead.id)
        return
    notifications.dispatch(
        notifications.notify_new_reply(owner, lead.id, company=lead.company)
    )
    # Feature Group 4: outbound webhooks for every reply; Slack only for an
    # interested one (the spec's "interested reply received"). push=False on
    # both -- the M7 push above already told the phone.
    from app.services import event_bus  # noqa: PLC0415
    from app.workers import notification_tasks  # noqa: PLC0415

    who = lead.full_name or lead.email or "A lead"
    payload = {"lead": event_bus.lead_payload(lead), "channel": channel,
               "classification": classification}
    link = f"/leads/detail?id={lead.id}"
    notification_tasks.enqueue_event(
        owner, "reply_received", push=False, slack=False, title="A lead replied",
        body=f"{who} replied on {channel} ({classification or 'unclassified'}).",
        deep_link=link, data={"leadId": str(lead.id)}, webhook_payload=payload)
    if classification == "interested":
        notification_tasks.enqueue_event(
            owner, "reply_interested", push=False, title="Interested reply",
            body=f"{who}{f' ({lead.company})' if lead.company else ''} replied with "
                 f"interest on {channel}.",
            deep_link=link, data={"leadId": str(lead.id)}, webhook_payload=payload)


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

    classification = classify_reply(inbound.from_address, inbound.subject, inbound.body,
                                    session=session)

    reply_row = InboundReply(
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
    )
    session.add(reply_row)
    session.commit()

    # Feature 2: classify what the HUMAN should do next. Dispatched AFTER the
    # commit so the task can never look up a row that is not there yet, and
    # before the routing below so a slow model call cannot delay the hard
    # stop / suppression that routing performs. enqueue() never raises.
    from app.workers import reply_tasks  # noqa: PLC0415

    reply_tasks.enqueue(reply_row.id)

    if lead is None:
        return f"unmatched_{classification}"
    # Feature Group 9: a machine's "reply" is stored (above) but is not a
    # reply -- the sequence neither stops nor advances, nothing is counted.
    if classification == "automated_response":
        return classification

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
    _notify_new_reply(session, lead, classification, "email")

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
    classification = classify_reply(reply.from_address, None, reply.body, session=session)
    reply.classification = classification
    session.commit()
    if classification == "automated_response":   # Feature Group 9
        return classification

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
    _notify_new_reply(session, lead, classification, "whatsapp")

    return classification


# --------------------------------------------------------------------------
# Feature Group 5: LinkedIn inbound routing
# (the section header below is kept for the Celery wrappers)
# --------------------------------------------------------------------------


def route_linkedin_inbound_impl(session: Session, lead: Lead,
                                reply: InboundReply) -> str:
    """Classify a LinkedIn reply with the SAME classifier and apply the SAME
    unified stop rules as email and WhatsApp. An unsubscribe request
    suppresses the email, the phone AND the LinkedIn profile. Never
    auto-replies to humans."""
    classification = classify_reply(reply.from_address, None, reply.body, session=session)
    reply.classification = classification
    session.commit()
    if classification == "automated_response":   # Feature Group 9
        return classification

    enrollments = list(session.execute(
        select(SequenceEnrollment).where(SequenceEnrollment.lead_id == lead.id)
    ).scalars())

    if classification == "unsubscribe_request":
        engine.unsubscribe_lead(session, lead, source="linkedin_reply", channel="linkedin")
        return classification

    if classification == "out_of_office":
        until = (reply.received_at or datetime.now(timezone.utc)) + timedelta(
            days=settings.ooo_reschedule_days)
        for e in enrollments:
            if e.status is EnrollmentStatus.ACTIVE:
                engine.pause_enrollment(session, e, until=until)
        return classification

    if classification == "bounce":
        return classification   # not meaningful on LinkedIn; recorded above

    for e in enrollments:
        if e.status is not EnrollmentStatus.STOPPED:
            engine.stop_enrollment(session, e, reason=f"replied_{classification}")
    lead.status = LeadStatus.REPLIED
    session.add(Outcome(lead_id=lead.id, event=OutcomeEvent.REPLIED, channel="linkedin",
                        meta_json={"classification": classification}))
    session.commit()
    _notify_new_reply(session, lead, classification, "linkedin")
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
        # Feature Group 3: every model call made while rendering this send is
        # attributed to its campaign (usage_meter).
        from app.services import usage_meter  # noqa: PLC0415

        message = session.get(Message, uuid.UUID(message_id))
        sequence = session.get(Sequence, message.sequence_id) if message else None
        strategy = session.get(Strategy, sequence.strategy_id) if sequence else None
        with usage_meter.owner_scope(session, strategy, "outreach"):
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


# --------------------------------------------------------------------------
# Engagement Hub, Feature 1 — automated follow-up
# --------------------------------------------------------------------------
#
# WHAT THIS DOES THAT THE SEQUENCE ENGINE DOES NOT
# schedule_next_step already queues step N+1 the moment step N sends, on the
# step's `delay_days` timer. That covers the happy path completely, and this
# sweep must not fire for it -- two systems scheduling the same follow-up is
# how a prospect receives the same message twice.
#
# So the sweep's central guard is: SKIP ANY ENROLLMENT THAT ALREADY HAS A
# PENDING MESSAGE. What is left is the population the engine currently drops
# on the floor:
#
#   * a send that failed permanently (status FAILED) -- the enrollment stays
#     ACTIVE with nothing queued behind it, forever;
#   * a WhatsApp step that fell to NEEDS_TEMPLATE because the 24h window
#     closed or a template lost approval -- documented, expected, and
#     currently terminal for that lead;
#   * a step deleted or renumbered after its message was scheduled.
#
# In each case a real prospect was contacted, said nothing, and the system
# quietly stopped. That is what this fixes.
#
# ENROLLMENT STATUS: ACTIVE ONLY.
# COMPLETED enrollments (every step sent, no reply) are deliberately out of
# scope. Sweeping them would auto-DM every lead who ever finished a sequence,
# on every sweep, with no upper bound on how many follow-ups one lead
# receives -- a mass-send this system has no user-facing control for. If that
# behaviour is wanted it needs its own cap, its own opt-in and its own row in
# the compliance story.
#
# IDEMPOTENCY IS TWO LAYERS, NOT ONE.
# The Redis lock (followup:{enrollment_id}:{step_no}, 2h TTL) stops two
# workers acting on the same overdue enrollment. The message row's own
# SCHEDULED -> SENDING claim in send_message_impl stops a double transmit if
# the lock ever fails open (Redis down). The lock is an optimisation for the
# common case; the claim is the guarantee.

FOLLOWUP_LOCK_PREFIX = "followup:"

# How far into the future an auto follow-up message is dated when it is
# created. It is NOT a delay: send_followup_impl transmits it immediately in
# the same task, and send_message_impl does not look at scheduled_at.
#
# It exists so the 60-second beat dispatcher cannot claim the row in the
# window between INSERT and send. If it did, the message would still send
# exactly once (the SENDING claim guarantees that) but it would be sent by the
# generic path, and the OutcomeEvent would be written without
# source="auto_followup" -- so the audit trail would lose the one fact that
# says this send was automatic.
_FOLLOWUP_DISPATCH_GUARD = timedelta(minutes=5)


def _followup_lock_key(enrollment_id, step_no: int) -> str:
    return f"{FOLLOWUP_LOCK_PREFIX}{enrollment_id}:{step_no}"


def _acquire_followup_lock(enrollment_id, step_no: int) -> bool:
    """SET NX EX. True when this caller owns the follow-up.

    FAILS OPEN. If Redis is unreachable this returns True and the send goes
    ahead protected only by the message row's SENDING claim. The alternative
    -- failing closed -- means a Redis outage silently stops every follow-up
    in the product with nothing surfacing that it has, which is a worse
    failure than the one it would be preventing.
    """
    try:
        from app.core.redis_client import get_sync_redis  # noqa: PLC0415

        return bool(get_sync_redis().set(
            _followup_lock_key(enrollment_id, step_no), "1",
            nx=True, ex=settings.followup_lock_ttl_seconds,
        ))
    except Exception as exc:  # noqa: BLE001
        logger.warning("follow-up lock unavailable (%s) — relying on the "
                       "message SENDING claim for enrollment %s step %s",
                       exc, enrollment_id, step_no)
        return True


def _aware(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes for timestamptz columns; PostgreSQL does
    not. Every value in those columns is UTC, so this restates that rather
    than converting -- without it the arithmetic below raises on SQLite only,
    i.e. in the test suite and nowhere else."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _last_sent_message(session: Session, enrollment: SequenceEnrollment) -> Message | None:
    return session.execute(
        select(Message)
        .where(Message.sequence_id == enrollment.sequence_id,
               Message.lead_id == enrollment.lead_id,
               Message.status == MessageStatus.SENT)
        .order_by(Message.step_no.desc(), Message.sent_at.desc())
    ).scalars().first()


def _has_pending_message(session: Session, enrollment: SequenceEnrollment) -> bool:
    return session.execute(
        select(Message.id).where(
            Message.sequence_id == enrollment.sequence_id,
            Message.lead_id == enrollment.lead_id,
            Message.status.in_([MessageStatus.SCHEDULED, MessageStatus.SENDING]),
        ).limit(1)
    ).scalars().first() is not None


def _replied_since(session: Session, lead_id, since: datetime | None) -> bool:
    """Has this lead replied since the last message went out?

    Scoped by time rather than "has ever replied", because a lead can reply to
    one campaign and be legitimately enrolled in another later. `outcomes` has
    no enrollment_id to filter on -- it is keyed on lead and message -- so the
    send time of the message we are following up is the boundary that makes
    the question answerable.
    """
    query = select(Outcome.id).where(Outcome.lead_id == lead_id,
                                     Outcome.event == OutcomeEvent.REPLIED)
    if since is not None:
        query = query.where(Outcome.ts >= since)
    return session.execute(query.limit(1)).scalars().first() is not None


def _step_for(session: Session, sequence_id, step_no: int):
    from app.db.models import SequenceStep  # noqa: PLC0415

    return session.execute(
        select(SequenceStep).where(SequenceStep.sequence_id == sequence_id,
                                   SequenceStep.step_no == step_no)
    ).scalars().first()


def check_followup_due_impl(session: Session, now: datetime | None = None,
                            enqueue=None) -> list[tuple[str, int]]:
    """Find enrollments whose last message has gone unanswered past its step's
    follow-up window. Returns the (enrollment_id, step_no) pairs enqueued.

    `step_no` is the step the follow-up WILL send: last_sent + 1. It is part
    of the lock key, so a lead can receive step 3's follow-up after step 2's
    without the second being mistaken for a retry of the first.
    """
    now = now or _now()
    enqueue = enqueue or (lambda eid, step: send_followup_task.delay(eid, step))

    enrollments = session.execute(
        select(SequenceEnrollment).where(
            SequenceEnrollment.status == EnrollmentStatus.ACTIVE
        )
    ).scalars().all()

    due: list[tuple[str, int]] = []
    for enrollment in enrollments:
        # The guard that keeps this out of the sequence engine's way. See the
        # section comment above.
        if _has_pending_message(session, enrollment):
            continue

        last = _last_sent_message(session, enrollment)
        if last is None or last.sent_at is None:
            continue

        step = _step_for(session, enrollment.sequence_id, last.step_no)
        if step is not None and not step.followup_enabled:
            continue
        delay_hours = step.followup_delay_hours if step is not None else 72

        sent_at = _aware(last.sent_at)
        if now - sent_at < timedelta(hours=delay_hours):
            continue
        if _replied_since(session, enrollment.lead_id, sent_at):
            continue

        # A campaign the user paused sends nothing, automatic or not. Checked
        # here as well as in send_message_impl so a paused campaign does not
        # burn a lock and a task per sweep.
        lead = session.get(Lead, enrollment.lead_id)
        strategy = session.get(Strategy, lead.strategy_id) if lead else None
        if strategy is None or strategy.campaign_state != engine.CAMPAIGN_ACTIVE:
            continue

        next_step_no = last.step_no + 1
        enqueue(str(enrollment.id), next_step_no)
        due.append((str(enrollment.id), next_step_no))

    return due


def send_followup_impl(session: Session, enrollment_id: uuid.UUID, step_no: int,
                       now: datetime | None = None) -> str:
    """Send one automatic follow-up. Idempotent; safe to call twice.

    Two shapes, decided by whether the sequence has a step `step_no`:
      * IT DOES  -- schedule that step's message and send it now. This is the
        stalled-sequence recovery: the step exists, its message failed or was
        never created, and this puts the lead back on the rails.
      * IT DOES NOT -- generate a follow-up brief from the lead's own history
        (message_personalization.build_followup_brief) and send it as step
        `step_no` on the same channel as the last message. The message row
        carries the generated brief as its `template`, so the ordinary render
        path personalizes it at send time exactly like a human-written step.
    """
    now = now or _now()
    enrollment = session.get(SequenceEnrollment, enrollment_id)
    if enrollment is None:
        return "missing"
    if enrollment.status is not EnrollmentStatus.ACTIVE:
        return f"skipped_{enrollment.status.value}"
    if _has_pending_message(session, enrollment):
        # The engine scheduled something between the sweep and now.
        return "skipped_already_pending"

    if not _acquire_followup_lock(enrollment_id, step_no):
        return "locked"

    last = _last_sent_message(session, enrollment)
    if last is None or last.sent_at is None:
        return "no_prior_send"
    if _replied_since(session, enrollment.lead_id, _aware(last.sent_at)):
        return "skipped_replied"

    lead = session.get(Lead, enrollment.lead_id)
    sequence = session.get(Sequence, enrollment.sequence_id)
    strategy = session.get(Strategy, lead.strategy_id)
    if strategy.campaign_state != engine.CAMPAIGN_ACTIVE:
        return "campaign_paused"

    step = _step_for(session, enrollment.sequence_id, step_no)
    if step is not None:
        channel = step.effective_channel(sequence)
        template = step.template
        variant = step.variant
        whatsapp_kind = step.whatsapp_kind
        whatsapp_template_id = step.whatsapp_template_id
        mode = "sequence_step"
    else:
        # The auto-DM fallback. Same channel as the last message: a lead who
        # has only ever been emailed should not suddenly receive a WhatsApp
        # message from an automation, and the opt-in state that would make
        # that legal is a decision a human makes, not a fallback.
        channel = last.channel
        if channel is ChannelType.WHATSAPP:
            # A cold WhatsApp message requires an approved template, and there
            # is no step to name one. Generating free-form copy here would
            # either be blocked by the adapter's compliance guard or, worse,
            # sent inside a window the lead did not open. Email-only fallback.
            logger.info("no auto follow-up for enrollment %s: last channel was "
                        "WhatsApp and a generated follow-up has no approved "
                        "template", enrollment_id)
            return "skipped_whatsapp_needs_template"
        template = personalization.build_followup_brief(
            session, strategy, lead, channel=channel.value
        )
        variant = last.variant
        whatsapp_kind = None
        whatsapp_template_id = None
        mode = "auto_dm"

    message = Message(
        sequence_id=enrollment.sequence_id,
        lead_id=lead.id,
        channel=channel,
        step_no=step_no,
        template=template,
        variant=variant,
        whatsapp_kind=whatsapp_kind,
        whatsapp_template_id=whatsapp_template_id,
        status=MessageStatus.SCHEDULED,
        # See _FOLLOWUP_DISPATCH_GUARD: keeps the beat dispatcher off this row
        # for the moment it takes to send it here. Not a delay.
        scheduled_at=now + _FOLLOWUP_DISPATCH_GUARD,
    )
    session.add(message)
    session.commit()

    result = send_message_impl(session, message.id, now=now,
                               outcome_source="auto_followup")
    logger.info("auto follow-up (%s) for enrollment %s step %s: %s",
                mode, enrollment_id, step_no, result)
    return result


@celery_app.task(name="leadpilot.outreach.check_followup_due")
def check_followup_due() -> int:
    session = SessionLocal()
    try:
        return len(check_followup_due_impl(session))
    finally:
        session.close()


@celery_app.task(name="leadpilot.outreach.send_followup", bind=True, max_retries=3)
def send_followup_task(self, enrollment_id: str, step_no: int) -> str:
    session = SessionLocal()
    try:
        return send_followup_impl(session, uuid.UUID(enrollment_id), int(step_no))
    except Exception as exc:
        session.rollback()
        logger.exception("auto follow-up failed for enrollment %s step %s — "
                         "retrying", enrollment_id, step_no)
        raise self.retry(exc=exc, countdown=300)
    finally:
        session.close()

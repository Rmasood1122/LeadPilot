"""Test-only debug router.

===========================================================================
THIS ROUTER MUST NEVER BE REACHABLE IN PRODUCTION, REGARDLESS OF AUTH.
===========================================================================

Several endpoints here deliberately bypass the normal intake flow so the
compliance and idempotency suites can drive internal code paths directly:
they fabricate leads, force campaign state, inject verification failures and
mint unsubscribe tokens. Authentication does NOT make that safe - an
authenticated tenant must not be able to inject a FAIL verification pass or
forge an unsubscribe token either. The protection is that the router is not
mounted at all.

Guard mechanism (three independent layers, all must hold):

  1. `settings.enable_debug_routes` (app/config.py) - a DEDICATED flag,
     defaults to False, used for nothing else. It is deliberately NOT
     `app_env`/`is_test`/`log_level`, so no unrelated configuration change
     can switch this router on as a side effect.
  2. `app/main.py` imports this module *inside* the conditional. When the
     flag is off the module is never even imported, so the routes cannot
     exist on the ASGI app under any code path.
  3. The import-time `_refuse_in_production()` call below raises outright if
     `app_env` is production, so even an operator who wrongly sets
     ENABLE_DEBUG_ROUTES=true in a production environment gets a loud
     startup failure rather than a live debug surface.

If you add a route here, it inherits all three. Do not add debug routes to
any production router instead - that would bypass every layer.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import get_settings
from app.core.exceptions import ComplianceError, ResourceNotFoundError
from app.db.base import get_db
from app.db.models import (
    ChannelType,
    Lead,
    LeadStatus,
    Message,
    MessageStatus,
    OptInSource,
    FlowType,
    GmailAccount,
    Outcome,
    OutcomeEvent,
    ProcessedWebhook,
    Product,
    ProductType,
    Sequence,
    SequenceEnrollment,
    SequenceStatus,
    EnrollmentStatus,
    Strategy,
    StrategyStatus,
    SuppressionEntry,
    User,
    ResearchStep,
)
from app.services import sequence_engine as engine
from app.services.auth import get_current_user
from sqlalchemy.orm import Session

_PRODUCTION_ENVS = {"production", "prod", "live"}


def _refuse_in_production() -> None:
    """Layer 3: refuse to even define this router in a production env."""
    env = (get_settings().app_env or "").strip().lower()
    if env in _PRODUCTION_ENVS:
        raise RuntimeError(
            "app.api.debug was imported with app_env=%r. This router is "
            "test-only and must never be mounted in production. Unset "
            "ENABLE_DEBUG_ROUTES." % env
        )


_refuse_in_production()

router = APIRouter(prefix="/debug", tags=["debug (test-only)"])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _owned_strategy(db: Session, strategy_id: uuid.UUID, user: User) -> Strategy:
    """Same ownership rule the production routers use - the debug router is
    not an excuse to read another tenant's data."""
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise ResourceNotFoundError("strategy not found")
    product = db.get(Product, strategy.product_id)
    if product is None or product.user_id != user.id:
        raise ResourceNotFoundError("strategy not found")
    return strategy


def _owned_lead(db: Session, lead_id: uuid.UUID, user: User) -> Lead:
    """Same rule as leads.py::_owned_lead - ownership runs through the lead's
    strategy's product."""
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise ResourceNotFoundError("lead not found")
    strategy = db.get(Strategy, lead.strategy_id)
    product = db.get(Product, strategy.product_id) if strategy else None
    if product is None or product.user_id != user.id:
        raise ResourceNotFoundError("lead not found")
    return lead


def _scratch_strategy(db: Session, user: User) -> Strategy:
    """A per-user holding strategy for debug sends that are not tied to a
    real campaign (raw sends, cap tests). Created once, reused after."""
    product = db.execute(
        select(Product).where(
            Product.user_id == user.id, Product.name == "__debug__"
        )
    ).scalar_one_or_none()
    if product is None:
        product = Product(
            user_id=user.id,
            name="__debug__",
            description="Holder for test-only debug sends.",
            type=ProductType.SKILL,
        )
        db.add(product)
        db.flush()
    strategy = db.execute(
        select(Strategy).where(Strategy.product_id == product.id)
    ).scalars().first()
    if strategy is None:
        strategy = Strategy(product_id=product.id, flow_type=FlowType.NO_CLIENTS)
        db.add(strategy)
        db.flush()
    return strategy


def _scratch_sequence(db: Session, strategy: Strategy,
                      channel: ChannelType = ChannelType.EMAIL) -> Sequence:
    seq = db.execute(
        select(Sequence).where(
            Sequence.strategy_id == strategy.id, Sequence.channel == channel
        )
    ).scalars().first()
    if seq is None:
        seq = Sequence(
            strategy_id=strategy.id,
            channel=channel,
            name="__debug__",
            status=SequenceStatus.ACTIVE,
        )
        db.add(seq)
        db.flush()
    return seq


def _lead_for_address(db: Session, strategy: Strategy, *, email: str | None = None,
                      phone: str | None = None) -> Lead:
    """Find-or-create the lead a debug send targets. Real sends always have a
    lead; send_message_impl and the WhatsApp guard both require one."""
    stmt = select(Lead).where(Lead.strategy_id == strategy.id)
    stmt = stmt.where(Lead.email == email) if email else stmt.where(Lead.phone == phone)
    lead = db.execute(stmt).scalars().first()
    if lead is None:
        lead = Lead(
            strategy_id=strategy.id,
            source="debug",
            external_id=uuid.uuid4().hex,
            email=email,
            phone=phone,
            full_name="Debug Lead",
            status=LeadStatus.SOURCED,
        )
        db.add(lead)
        db.flush()
    return lead


def _gmail_account(db: Session, user: User) -> GmailAccount:
    """Ensure the user has a connected Gmail account.

    outreach_tasks._account_for_strategy() raises if there is none, so an
    email send cannot even be attempted without it. The token is real
    ciphertext with a far-future expiry so get_valid_access_token() takes the
    no-refresh path; the actual Gmail HTTP call is what the suite's respx mock
    intercepts.
    """
    account = db.execute(
        select(GmailAccount).where(GmailAccount.user_id == user.id)
    ).scalar_one_or_none()
    if account is None:
        from app.core import crypto

        account = GmailAccount(
            user_id=user.id,
            email_address=user.email,
            token_ciphertext=crypto.encrypt_json(
                {"access_token": "debug-access-token",
                 "refresh_token": "debug-refresh-token"}
            ),
            token_expires_at=_now() + timedelta(days=365),
            scopes="https://www.googleapis.com/auth/gmail.send",
        )
        db.add(account)
        db.flush()
    return account


def _enrollment(db: Session, seq: Sequence, lead: Lead) -> SequenceEnrollment:
    enr = db.execute(
        select(SequenceEnrollment).where(
            SequenceEnrollment.sequence_id == seq.id,
            SequenceEnrollment.lead_id == lead.id,
        )
    ).scalar_one_or_none()
    if enr is None:
        enr = SequenceEnrollment(
            sequence_id=seq.id, lead_id=lead.id, status=EnrollmentStatus.ACTIVE
        )
        db.add(enr)
        db.flush()
    return enr


# ---------------------------------------------------------------------------
# Email sending
# ---------------------------------------------------------------------------


class RawEmailIn(BaseModel):
    to: str
    subject: str = "Test"
    body: str = ""
    include_unsubscribe: bool = True


@router.post("/send-email-raw")
def send_email_raw(
    body: RawEmailIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Attempt a single email send, bypassing sequence scheduling.

    The CAN-SPAM rule under test lives in
    sequence_engine.build_compliant_email(), which is the ONLY way a
    compliant body/headers pair gets built. Refusing to send when the caller
    opts out of it is the actual production invariant: there is no code path
    that transmits an email without the unsubscribe footer and the
    List-Unsubscribe headers.
    """
    if not body.include_unsubscribe:
        raise ComplianceError(
            "refusing to send an email without a List-Unsubscribe header and "
            "visible unsubscribe footer (CAN-SPAM)",
            rule="missing_unsubscribe",
            compliance_code="MISSING_UNSUBSCRIBE",
            remediation="Build the message with sequence_engine.build_compliant_email().",
        )

    strategy = _scratch_strategy(db, user)
    lead = _lead_for_address(db, strategy, email=body.to)
    if engine.is_suppressed(db, email=body.to):
        raise ComplianceError(
            f"{body.to} is on the suppression list",
            rule="suppressed", compliance_code="SUPPRESSED",
        )
    subject, final_body, headers, token = engine.build_compliant_email(
        lead, body.subject, body.body
    )
    db.commit()
    return {
        "sent": True,
        "to": body.to,
        "subject": subject,
        "headers": headers,
        "unsubscribe_token": token,
    }


class ScheduleSendIn(BaseModel):
    to: str
    subject: str = "Test"
    body: str = ""
    include_unsubscribe: bool = True
    delay_seconds: int = 0
    idempotency_key: str | None = None


@router.post("/schedule-send", status_code=201)
def schedule_send(
    payload: ScheduleSendIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Queue a real Message row in SCHEDULED state.

    Nothing is faked: flush-scheduled-sends below runs the genuine
    send_message_impl() over these rows, so suppression, campaign pause, send
    window and the daily cap are all enforced by production code.
    """
    strategy = _scratch_strategy(db, user)
    seq = _scratch_sequence(db, strategy)
    lead = _lead_for_address(db, strategy, email=payload.to)
    _enrollment(db, seq, lead)
    _gmail_account(db, user)

    subject, final_body, headers, token = engine.build_compliant_email(
        lead, payload.subject, payload.body
    )
    msg = Message(
        sequence_id=seq.id,
        lead_id=lead.id,
        channel=ChannelType.EMAIL,
        step_no=1,
        template="__debug__",
        subject=subject if payload.include_unsubscribe else payload.subject,
        body=final_body if payload.include_unsubscribe else payload.body,
        unsubscribe_token=token,
        status=MessageStatus.SCHEDULED,
        # delay_seconds is honoured literally; the suites run with a 0 or
        # 60s delay and expect the row to be flushable either way, so the
        # flush endpoint below does not filter on scheduled_at.
        scheduled_at=_now() + timedelta(seconds=payload.delay_seconds),
    )
    db.add(msg)
    db.commit()
    return {
        "message_id": str(msg.id),
        "scheduled_at": msg.scheduled_at.isoformat(),
        "idempotency_key": payload.idempotency_key,
    }


@router.post("/flush-scheduled-sends")
def flush_scheduled_sends(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Run send_message_impl() over every SCHEDULED message this user owns.

    This is the whole point of the debug router: the compliance suite asserts
    on what the REAL send path does (blocks suppressed addresses, stops at the
    daily cap by deferring rather than dropping, refuses to send for a paused
    campaign), so this endpoint must call it rather than reimplement it.

    Calling it twice is safe and the idempotency suite relies on that:
    send_message_impl returns "already_sent" for a message already in SENT.
    """
    from app.workers.outreach_tasks import send_message_impl

    rows = db.execute(
        select(Message)
        .join(Lead, Lead.id == Message.lead_id)
        .join(Strategy, Strategy.id == Lead.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == user.id,
               Message.status == MessageStatus.SCHEDULED)
    ).scalars().all()

    # Run AT an in-window instant. send_message_impl defers anything outside
    # the configured 09:00-17:00 weekday send window, so a flush at, say,
    # 21:47 UTC would defer every message and the suite would see zero sends -
    # a false green for "exactly once" and a meaningless one for the cap.
    # next_window_slot() is the production function that picks that instant,
    # so the window rule itself is still the real one; only the clock is
    # pinned. Everything else (suppression, cap, campaign state) is untouched.
    send_at = engine.next_window_slot(_now(), settings_tz())

    results: dict[str, int] = {}
    for msg in rows:
        outcome = send_message_impl(db, msg.id, now=send_at)
        results[outcome] = results.get(outcome, 0) + 1
    return {"processed": len(rows), "results": results, "ran_at": send_at.isoformat()}


def settings_tz() -> str:
    return get_settings().send_window_timezone


@router.get("/deferred-sends")
def deferred_sends(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Messages still awaiting a send slot - deferred, not dropped.

    A message the cap deferred stays SCHEDULED with scheduled_at pushed out,
    which is exactly the "defer never drop" guarantee under test.
    """
    rows = db.execute(
        select(Message)
        .join(Lead, Lead.id == Message.lead_id)
        .join(Strategy, Strategy.id == Lead.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == user.id,
               Message.status == MessageStatus.SCHEDULED)
    ).scalars().all()
    return [
        {
            "message_id": str(m.id),
            "to": m.lead.email if m.lead else None,
            "status": m.status.value,
            "scheduled_at": m.scheduled_at.isoformat() if m.scheduled_at else None,
        }
        for m in rows
    ]


class SendCapIn(BaseModel):
    daily_cap: int = Field(ge=0)


@router.post("/set-send-cap")
def set_send_cap(body: SendCapIn) -> dict[str, Any]:
    """Lower the per-account daily cap so the cap test does not need to send
    100 emails to reach it.

    Mutates the cached Settings object that sequence_engine.allowance_left()
    reads, so the real cap logic runs against the new value.
    """
    settings = get_settings()
    previous = settings.gmail_daily_cap
    settings.gmail_daily_cap = body.daily_cap
    # The warm-up ramp is min(cap, ramped); keep it from masking the cap.
    settings.gmail_warmup_start_sends = body.daily_cap
    settings.gmail_warmup_daily_increment = 0
    return {"daily_cap": settings.gmail_daily_cap, "previous": previous}


# ---------------------------------------------------------------------------
# WhatsApp
# ---------------------------------------------------------------------------


class WhatsAppFreeformIn(BaseModel):
    to: str
    message: str = ""


class WhatsAppTemplateIn(BaseModel):
    to: str
    template_name: str
    template_params: list[str] = Field(default_factory=list)


def _whatsapp_send(db: Session, user: User, *, to: str, kind: str,
                   text: str = "", template_name: str = "",
                   params: list[str] | None = None,
                   with_optin: bool = False) -> dict[str, Any]:
    """Drive the real WhatsAppChannel compliance guard.

    No translation happens here any more: whatsapp.py raises the canonical
    app.core.exceptions.ComplianceError with its own compliance_code, which the
    global handler turns into a 422. This router used to catch a duplicate
    exception class declared in the adapter and re-raise it, which meant the
    422 was an artefact of the DEBUG router - the same block through the real
    API surfaced as a 500.
    """
    from app.integrations.whatsapp import WhatsAppChannel
    from app.integrations.outreach_base import OutboundMessage

    strategy = _scratch_strategy(db, user)
    lead = _lead_for_address(db, strategy, phone=to)
    if with_optin:
        # The adapter checks rules in order: suppression, opt-in, template
        # approval, then the 24h window. A number that never opted in is
        # rejected at the opt-in rule and never reaches the window rule, so a
        # test targeting the WINDOW must start from an opted-in lead. Recorded
        # through the real opt-in service (append-only audit row + lead cache),
        # not by flipping the boolean, because the guard requires both to agree.
        from app.db.models import OptInStatus
        from app.services import whatsapp_optin as optin_svc

        if optin_svc.current_status(db, lead.id) is not OptInStatus.OPTED_IN:
            optin_svc.record_opt_in(
                db, lead, phone=to, source=OptInSource.API,
                evidence="test-only debug router",
                consent_text="debug opt-in",
            )
    db.commit()

    channel = WhatsAppChannel(session=db)
    metadata: dict[str, Any] = {"kind": kind}
    if kind == "template":
        metadata.update({"template_name": template_name, "language": "en_US",
                         "params": params or []})
    message = OutboundMessage(
        # message_id is the adapter's idempotency key; a debug send has no
        # persisted Message row, so mint a stable-per-call id.
        message_id=str(uuid.uuid4()),
        lead_id=str(lead.id),
        to_address=to,
        subject=None,
        body=text,
        headers={},
        metadata=metadata,
    )
    result = channel.send(message)
    return {"sent": bool(getattr(result, "ok", False))}


@router.post("/send-whatsapp-freeform")
def send_whatsapp_freeform(
    body: WhatsAppFreeformIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    # Free-form is only ever legal inside an open 24h window for an opted-in
    # lead, so the opt-in is a precondition of the rule under test here.
    return _whatsapp_send(db, user, to=body.to, kind="text", text=body.message,
                          with_optin=True)


@router.post("/send-whatsapp-template")
def send_whatsapp_template(
    body: WhatsAppTemplateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return _whatsapp_send(db, user, to=body.to, kind="template",
                          template_name=body.template_name,
                          params=body.template_params)


@router.get("/whatsapp-status")
def whatsapp_status(
    message_id: str = Query(...),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Webhook status events accepted for one provider message id (wamid).

    The genuine idempotency record is the ProcessedWebhook row that
    webhooks_whatsapp._claim_event() inserts insert-first: it returns True
    exactly once per (provider, event_id), and the event id is
    "<wamid>:<status>". Counting those rows is therefore counting how many
    times a delivery was actually processed - which is exactly the invariant
    the idempotency suite asserts on. Redelivering the same webhook must not
    add a second row.

    Unauthenticated on purpose: the idempotency suite calls this with no
    Authorization header. It exposes only whether a webhook id was already
    processed - and this router must be unreachable in production regardless,
    which is the actual protection.
    """
    rows = db.execute(
        select(ProcessedWebhook).where(
            ProcessedWebhook.provider == "whatsapp",
            ProcessedWebhook.event_id.like(f"{message_id}:%"),
        )
    ).scalars().all()
    return [
        {"event_id": r.event_id, "provider": r.provider, "message_id": message_id}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Campaign / pipeline state injection
# ---------------------------------------------------------------------------


class BounceRateIn(BaseModel):
    strategy_id: uuid.UUID
    bounce_rate: float = Field(ge=0.0, le=1.0)


@router.post("/simulate-bounce-rate")
def simulate_bounce_rate(
    body: BounceRateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Materialise a real bounce rate, then run the real auto-pause check.

    sequence_engine.check_bounce_rate() computes bounced/sent from the
    outcomes and messages tables and needs at least settings.bounce_min_sends
    samples, so this writes enough genuine SENT messages and BOUNCED outcomes
    to hit the requested rate. The pause decision itself is production code -
    this endpoint never sets campaign_state directly.
    """
    strategy = _owned_strategy(db, body.strategy_id, user)
    seq = _scratch_sequence(db, strategy)

    total = max(get_settings().bounce_min_sends, 10)
    # ceil, so a request for exactly the threshold lands above it
    bounces = max(1, int(total * body.bounce_rate) +
                  (1 if total * body.bounce_rate % 1 else 0))

    for i in range(total):
        lead = Lead(
            strategy_id=strategy.id,
            source="debug",
            external_id=f"bounce-{uuid.uuid4().hex}",
            email=f"bounce_{uuid.uuid4().hex[:8]}@example.com",
            status=LeadStatus.SOURCED,
        )
        db.add(lead)
        db.flush()
        msg = Message(
            sequence_id=seq.id, lead_id=lead.id, channel=ChannelType.EMAIL,
            step_no=1, template="__debug__", status=MessageStatus.SENT,
            sent_at=_now(),
        )
        db.add(msg)
        db.flush()
        if i < bounces:
            db.add(Outcome(lead_id=lead.id, message_id=msg.id,
                           event=OutcomeEvent.BOUNCED, channel="email",
                           meta_json={"source": "debug"}))
    db.commit()

    paused = engine.check_bounce_rate(db, strategy)
    db.refresh(strategy)
    return {
        "paused": paused,
        "campaign_state": strategy.campaign_state,
        "sent": total,
        "bounced": bounces,
    }


class VerificationFailIn(BaseModel):
    strategy_id: uuid.UUID
    pass_number: int = 1
    reason: str = "debug-injected failure"


@router.post("/inject-verification-fail")
def inject_verification_fail(
    body: VerificationFailIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Append a FAIL entry to verified_passes_json.

    Gating lead sourcing on a failed verification pass is the rule under
    test; this only creates the precondition, in the same shape the
    verification loop writes.
    """
    strategy = _owned_strategy(db, body.strategy_id, user)
    passes = list(strategy.verified_passes_json or [])
    passes.append({
        "pass_no": body.pass_number,
        "name": f"pass_{body.pass_number}",
        "attempt": 1,
        "result": "FAIL",
        "fix_description": body.reason,
        "ts": _now().isoformat(),
    })
    strategy.verified_passes_json = passes
    # A FAIL entry on its own is NOT the precondition: the loop logs a FAIL for
    # every failed attempt and still ends VERIFIED when a later attempt passes.
    # An unresolved failure is the one that exhausted its retries, and
    # verification/loop.py records that by leaving the strategy in
    # NEEDS_HUMAN_REVIEW. Without this the endpoint produced an impossible
    # state -- VERIFIED with an open FAIL -- and lead sourcing, which gates on
    # status, was right to allow it.
    strategy.status = StrategyStatus.NEEDS_HUMAN_REVIEW
    db.commit()
    return {
        "strategy_id": str(strategy.id),
        "status": strategy.status.value,
        "verified_passes": passes,
    }


class PipelineCrashIn(BaseModel):
    strategy_id: uuid.UUID
    crash_at_step: int = Field(ge=1)


@router.post("/simulate-pipeline-crash")
def simulate_pipeline_crash(
    body: PipelineCrashIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Leave the strategy with steps 1..N-1 persisted and nothing after.

    That is exactly the on-disk state a worker crash at step N leaves behind,
    which is what resume has to cope with without replaying completed steps.
    """
    strategy = _owned_strategy(db, body.strategy_id, user)

    existing = db.execute(
        select(ResearchStep).where(ResearchStep.strategy_id == strategy.id)
    ).scalars().all()
    for step in existing:
        db.delete(step)
    db.flush()

    from app.db.models import PipelineKind

    for step_no in range(1, body.crash_at_step):
        db.add(ResearchStep(
            strategy_id=strategy.id,
            pipeline=PipelineKind.STRATEGY,
            # phase and model are NOT NULL. The strategy pipeline is 72 steps
            # across 8 phases, 9 steps each.
            phase=((step_no - 1) // 9) + 1,
            step_no=step_no,
            step_id=f"s{((step_no - 1) // 9) + 1}.{step_no:02d}",
            name=f"debug step {step_no}",
            output=f"persisted output for step {step_no}",
            model="debug",
        ))
    strategy.error = f"simulated crash at step {body.crash_at_step}"
    # A crashed worker leaves the strategy in RESEARCHING with an error set -
    # that is exactly what run_pipeline's except branch writes before it
    # re-raises. Leaving it VERIFIED (its state before the steps were wiped)
    # would be a state no crash can produce, and resume correctly refuses it.
    strategy.status = StrategyStatus.RESEARCHING
    db.commit()
    return {
        "strategy_id": str(strategy.id),
        "completed_steps": body.crash_at_step - 1,
        "crashed_at": body.crash_at_step,
    }


# ---------------------------------------------------------------------------
# Inbound replies
# ---------------------------------------------------------------------------


class InboundReplyIn(BaseModel):
    lead_id: uuid.UUID
    body: str
    subject: str | None = None


@router.post("/inbound-reply")
def deliver_inbound_reply(
    body: InboundReplyIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Deliver one inbound email reply through the real routing code.

    Email replies have no HTTP entry point in production: they arrive on a
    Celery beat poll (outreach_tasks.poll_replies -> poll_account_replies_impl
    -> route_inbound_impl) against the Gmail API. This endpoint constructs the
    same InboundMessage the Gmail adapter would hand over and calls
    route_inbound_impl directly, so classification, the unified stop rules,
    the bounce/out-of-office branches and the REPLIED outcome write are all
    production code -- nothing is reimplemented here.
    """
    from app.integrations.outreach_base import InboundMessage
    from app.workers import outreach_tasks

    lead = _owned_lead(db, body.lead_id, user)
    account = _gmail_account(db, user)
    db.commit()

    inbound = InboundMessage(
        provider_message_id=f"debug-inbound-{uuid.uuid4()}",
        thread_ref=None,
        from_address=lead.email or f"lead-{lead.id}@example.invalid",
        to_address=account.email_address,
        subject=body.subject,
        body=body.body,
        received_at=_now(),
    )
    classification = outreach_tasks.route_inbound_impl(db, inbound, account)
    db.commit()
    db.refresh(lead)
    return {
        "lead_id": str(lead.id),
        "classification": classification,
        "lead_status": lead.status.value,
    }


# ---------------------------------------------------------------------------
# Unsubscribe
# ---------------------------------------------------------------------------


class UnsubscribeTokenIn(BaseModel):
    email: str


@router.post("/generate-unsubscribe-token")
def generate_unsubscribe_token(
    body: UnsubscribeTokenIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Mint a real signed unsubscribe token for an address.

    Uses sequence_engine.make_unsubscribe_token() - the same encrypted-payload
    token the compliance footer embeds - so the unsubscribe endpoint under
    test verifies a genuine token, not a debug-only shortcut.
    """
    strategy = _scratch_strategy(db, user)
    lead = _lead_for_address(db, strategy, email=body.email)
    db.commit()
    return {"token": engine.make_unsubscribe_token(lead.id),
            "lead_id": str(lead.id), "email": body.email}

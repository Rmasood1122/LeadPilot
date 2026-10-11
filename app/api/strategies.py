"""Strategies — creation (enqueues the pipeline), status/progress, and
password-confirmed deletion."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.metering import refuse_if_daily_limit_reached
from app.core.plans import PlanLimitExceeded, check_plan_limit, plan_limit_response
from app.core.rate_limiting import AUTH_WINDOW_SECONDS, enforce_rate_limit
from app.api.schemas import (
    PhaseProgress,
    PipelineProgress,
    StrategyCreate,
    StrategyOut,
    StrategyResumeIn,
    StrategyPassOverrideIn,
    StrategyReverifyIn,
    StrategyStatusOut,
)
from app.db.base import get_db
from datetime import datetime, timezone

from app.config import settings
from app.db.models import (
    FlowType, GmailAccount, Lead, LeadStatus, Message, MessageStatus,
    Outcome, OutcomeEvent, PastClient, Product, ResearchStep, Strategy,
    StrategyStatus, User,
)
from app.api import spend_guard as spend_guard_api
from app.pipeline import budget_plan
from app.services import auth as auth_svc
from app.services import security_audit, usage_meter, verification_override
from app.services import sequence_engine as engine
from app.pipeline.engine import pipelines_for_flow
from app.pipeline.registry import phase_title
from app.workers import tasks as worker_tasks

logger = logging.getLogger(__name__)

router = APIRouter(tags=["strategies"])

# The exact detail a wrong confirmation password carries. The frontend matches
# on it (a contract, like EMAIL_NOT_VERIFIED). 403, never 401: a 401 would send
# the client into refresh-then-retry and, failing that, sign the user out for
# mistyping a password.
INVALID_PASSWORD = "INVALID_PASSWORD"


class StrategyDeleteIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


MIN_BUDGET_USD = 0.50


def _budget_micros(usd: float) -> int:
    """Validate a requested budget against the server's bounds; return micros."""
    ceiling = settings.pipeline_max_usd_ceiling
    if usd < MIN_BUDGET_USD or usd > ceiling:
        raise HTTPException(
            status_code=422,
            detail=f"max_budget_usd must be between ${MIN_BUDGET_USD:.2f} and "
                   f"${ceiling:.2f} (server ceiling)",
        )
    return int(round(usd * 1_000_000))


def _planned_steps(strategy: Strategy) -> int:
    per_pipeline = len(budget_plan.planned_step_nos(strategy.steps_per_phase))
    return per_pipeline * len(pipelines_for_flow(strategy.flow_type))


def _strategy_out(db: Session, strategy: Strategy) -> StrategyOut:
    out = StrategyOut.model_validate(strategy)
    out.steps_per_phase = strategy.steps_per_phase
    out.planned_steps = _planned_steps(strategy)
    out.budget_usd = (strategy.budget_micros / 1_000_000
                      if strategy.budget_micros is not None else None)
    out.spent_usd = usage_meter.spent_micros(db, strategy.id) / 1_000_000
    return out


def _owned_strategy(db: Session, strategy_id: uuid.UUID, current_user: User) -> Strategy:
    """Fetch a strategy and verify it belongs to current_user, else 404.

    Mirrors leads.py::_owned_strategy. 404 rather than 403 in both branches so
    a strategy id belonging to another account cannot be confirmed to exist.
    """
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    product = db.get(Product, strategy.product_id)
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="strategy not found")
    return strategy


def _refuse_if_daily_ai_limit_reached(db: Session, user: User) -> None:
    """P0-5: don't enqueue a pipeline the account cannot pay for today.

    The worker enforces the cap before every model call anyway
    (usage_meter.check_budget); this answers early with a clear 429 instead of
    queueing a run that would stop at its first call. Uses the caller's own
    account id only.
    """
    refuse_if_daily_limit_reached(db, user.id)


# Rate limited: the most expensive operation in the system (a 72/144-step
# pipeline plus 10 verification passes, ~150 Claude calls). See
# app/core/config.py::RATE_LIMIT_STRATEGIES for why the limit is 2/hour.
@router.post("/products/{product_id}/strategies", response_model=StrategyOut,
             status_code=202)
def create_strategy(
    product_id: uuid.UUID,
    body: StrategyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StrategyOut:
    """Create a strategy and enqueue its research pipeline.

    flow_type is inferred from whether the product has past clients when
    not given explicitly. Explicit with_clients on a product without past
    clients is rejected — Flow 1 is anchored on real patterns."""
    # Rate limit AFTER validation, not as a route dependency: a route-level
    # dependency runs before FastAPI validates `body`, so a malformed payload
    # burned a slot without creating anything. See
    # app/core/rate_limiting.py::enforce_rate_limit.
    enforce_rate_limit(str(current_user.id), "strategies", "RATE_LIMIT_STRATEGIES")

    product = db.get(Product, product_id)
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="product not found")

    # After the ownership check, so a foreign product id is 404 whatever the
    # count.
    check_new_strategy_allowed(db, current_user)

    has_clients = (
        db.execute(
            select(func.count(PastClient.id)).where(PastClient.product_id == product_id)
        ).scalar_one()
        > 0
    )

    flow_type = body.flow_type
    if flow_type is None:
        flow_type = FlowType.WITH_CLIENTS if has_clients else FlowType.NO_CLIENTS
    elif flow_type is FlowType.WITH_CLIENTS and not has_clients:
        raise HTTPException(
            status_code=422,
            detail="flow_type=with_clients requires at least one past client "
                   "(POST /products/{id}/past-clients first)",
        )

    budget_micros, steps_per_phase = plan_budget(db, flow_type, body.max_budget_usd)
    # F07: forecast first; refused (429) before anything is created.
    forecast = spend_guard_api.guard_new_strategy(db, current_user, flow_type, steps_per_phase)
    strategy = Strategy(product_id=product.id, flow_type=flow_type,
                        budget_micros=budget_micros, steps_per_phase=steps_per_phase)
    db.add(strategy)
    db.commit()
    db.refresh(strategy)
    spend_guard_api.link(db, forecast, strategy_id=strategy.id)  # F07

    worker_tasks.run_pipeline.delay(str(strategy.id))
    return _strategy_out(db, strategy)


def check_new_strategy_allowed(db: Session, current_user: User) -> None:
    """The account-level checks every new strategy passes: the plan's
    max_strategies (402) and today's AI cap (429).

    Shared by create_strategy and F06 Quickstart (app/api/quickstart.py), which
    creates a strategy too and must not be a way around either limit.
    """
    # F-AI-01: the plan's max_strategies. Counted over the caller's OWN
    # strategies, across all their products -- never another account's.
    owned_strategies = db.execute(
        select(func.count(Strategy.id))
        .join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == current_user.id)
    ).scalar_one()
    try:
        check_plan_limit(current_user, "max_strategies", owned_strategies)
    except PlanLimitExceeded as exc:
        raise HTTPException(status_code=402, detail=plan_limit_response(exc))
    _refuse_if_daily_ai_limit_reached(db, current_user)


def plan_budget(db: Session, flow_type: FlowType,
                max_budget_usd: float | None) -> tuple[int, int | None]:
    """(budget_micros, steps_per_phase) for a new strategy, or 422.

    Shared by create_strategy and F06 Quickstart."""
    budget_micros = _budget_micros(
        max_budget_usd if max_budget_usd is not None
        else settings.pipeline_max_usd_default
    )
    # F-AI-01b: fit the run to the budget -- fewer steps per phase for a small
    # one -- rather than letting it stop short. None = the full pipeline.
    try:
        steps_per_phase = budget_plan.plan_steps_per_phase(
            budget_micros, flow_type, usage_meter.price_table(db))
    except budget_plan.BudgetTooSmall as exc:
        raise HTTPException(
            status_code=422,
            detail=f"A budget of ${exc.budget_micros / 1_000_000:.2f} cannot run a "
                   f"complete pipeline; this flow needs at least "
                   f"${exc.minimum_micros / 1_000_000:.2f}.",
        )
    return budget_micros, steps_per_phase


@router.get("/strategies/{strategy_id}", response_model=StrategyStatusOut)
def get_strategy(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StrategyStatusOut:
    """Overall status + per-phase progress for every pipeline in the flow."""
    strategy = _owned_strategy(db, strategy_id, current_user)

    k = strategy.steps_per_phase or 9
    planned = budget_plan.planned_step_nos(strategy.steps_per_phase)
    progress: list[PipelineProgress] = []
    for pipeline in pipelines_for_flow(strategy.flow_type):
        counts = dict(
            db.execute(
                select(ResearchStep.phase, func.count(ResearchStep.id))
                .where(
                    ResearchStep.strategy_id == strategy.id,
                    ResearchStep.pipeline == pipeline,
                )
                .group_by(ResearchStep.phase)
            ).all()
        )
        phases = [
            PhaseProgress(
                phase=p,
                title=phase_title(pipeline, p),
                done=counts.get(p, 0),
                total=k,
            )
            for p in range(1, 9)
        ]
        progress.append(
            PipelineProgress(
                pipeline=pipeline.value,
                done=sum(counts.values()),
                total=len(planned),
                phases=phases,
            )
        )

    return StrategyStatusOut(
        id=strategy.id,
        flow_type=strategy.flow_type,
        status=strategy.status,
        progress=progress,
        verification=strategy.verified_passes_json or [],
        strategy_document_ready=bool(strategy.strategy_document),
        gtm_document_ready=bool(strategy.gtm_document),
        error=strategy.error,
        budget_usd=(strategy.budget_micros / 1_000_000
                    if strategy.budget_micros is not None else None),
        spent_usd=usage_meter.spent_micros(db, strategy.id) / 1_000_000,
        steps_per_phase=strategy.steps_per_phase,
        planned_steps=_planned_steps(strategy),
    )


@router.post("/strategies/{strategy_id}/resume", response_model=StrategyOut, status_code=202)
def resume_strategy(
    strategy_id: uuid.UUID,
    body: StrategyResumeIn | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StrategyOut:
    """Re-enqueue the research pipeline for a strategy that stopped early.

    `run_pipeline` is resumable by construction: the engine asks for the first
    step with no persisted row, so a re-enqueue continues from the crash point
    and never replays a completed step (the unique constraint on the
    research_steps row enforces that regardless of timing).

    Nothing could trigger that resume from outside the worker. Celery's own
    retry gives up after max_retries, and monitoring.detect_stale_pipeline_steps
    is deliberately detection-only -- "strategies are flagged and logged, never
    mutated", because the M1 engine owns status transitions. A strategy whose
    worker died therefore stayed stuck in `researching` forever with no way for
    the owner or an operator to restart it.
    """
    strategy = _owned_strategy(db, strategy_id, current_user)

    # Terminal states: run_pipeline itself refuses these, but answer with a
    # clear 409 rather than a 202 that quietly does nothing.
    if strategy.status in (StrategyStatus.VERIFIED, StrategyStatus.NEEDS_HUMAN_REVIEW):
        raise HTTPException(
            status_code=409,
            detail=f"strategy status is '{strategy.status.value}' - the pipeline "
                   "has already finished; there is nothing to resume",
        )
    # EXECUTING means outreach is live off a finished strategy. Re-running the
    # pipeline would reset status to 'researching' underneath a running
    # campaign, so refuse instead.
    if strategy.status is StrategyStatus.EXECUTING:
        raise HTTPException(
            status_code=409,
            detail="strategy is executing - pause the campaign before resuming "
                   "the pipeline",
        )

    # F-AI-01: a run that stopped on its budget resumes with a larger one.
    if body is not None and body.max_budget_usd is not None:
        new_micros = _budget_micros(body.max_budget_usd)
        spent = usage_meter.spent_micros(db, strategy.id)
        if new_micros <= spent:
            raise HTTPException(
                status_code=422,
                detail=f"max_budget_usd must exceed the ${spent / 1_000_000:.2f} "
                       "already spent on this strategy",
            )
        strategy.budget_micros = new_micros
    _refuse_if_daily_ai_limit_reached(db, current_user)
    # F07: forecast the rest of the run; a refusal (429) leaves nothing changed.
    spend_guard_api.guard_strategy_resume(db, current_user, strategy)
    if strategy.status is StrategyStatus.BUDGET_EXHAUSTED:
        strategy.status = StrategyStatus.PENDING
        strategy.error = None
    db.commit()
    db.refresh(strategy)

    worker_tasks.run_pipeline.delay(str(strategy.id))
    return _strategy_out(db, strategy)


@router.post("/strategies/{strategy_id}/reverify", response_model=StrategyOut,
             status_code=202)
def reverify_strategy(
    strategy_id: uuid.UUID,
    body: StrategyReverifyIn | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StrategyOut:
    """Run the 10 verification passes again on a strategy that ended in
    `needs_human_review`, reusing its finished research.

    Before this, that state was a dead end: /resume refuses it and nothing else
    starts verification, so the only way forward was a brand-new strategy and a
    second payment for research that already existed. This does NOT mark
    anything verified -- every pass is judged again from scratch and the status
    becomes `verified` only if all ten come back PASS.

    Only `needs_human_review` is accepted: the research is complete there by
    construction (verification only starts after the last step).
    """
    strategy = _owned_strategy(db, strategy_id, current_user)
    if strategy.status is not StrategyStatus.NEEDS_HUMAN_REVIEW:
        raise HTTPException(
            status_code=409,
            detail=f"strategy status is '{strategy.status.value}' - only a "
                   "strategy waiting for human review can be re-verified",
        )

    if body is not None and body.max_budget_usd is not None:
        new_micros = _budget_micros(body.max_budget_usd)
        spent = usage_meter.spent_micros(db, strategy.id)
        if new_micros <= spent:
            raise HTTPException(
                status_code=422,
                detail=f"max_budget_usd must exceed the ${spent / 1_000_000:.2f} "
                       "already spent on this strategy",
            )
        strategy.budget_micros = new_micros

    # F07: forecast the verification run; a refusal (429) leaves nothing changed.
    spend_guard_api.guard_strategy_reverify(db, current_user, strategy)
    strategy.status = StrategyStatus.VERIFYING
    strategy.error = None
    db.commit()
    db.refresh(strategy)

    worker_tasks.run_verification.delay(
        str(strategy.id), body.max_attempts if body is not None else None)
    return _strategy_out(db, strategy)


@router.post("/strategies/{strategy_id}/override-passes", response_model=StrategyOut)
def override_failed_passes(
    strategy_id: uuid.UUID,
    body: StrategyPassOverrideIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StrategyOut:
    """Human sign-off on 1-3 failed verification passes of the latest COMPLETE
    verification run; moves the strategy to `verified`. Allowed from
    `needs_human_review`, `budget_exhausted`, or a `verifying` run that has gone
    quiet (killed worker).

    Recorded as a human decision (who, when, why) in the pass log and the
    security audit trail; the judge's original FAIL rows are kept. The Legal &
    compliance pass can never be overridden. See
    app/services/verification_override.py for the rules.
    """
    strategy = _owned_strategy(db, strategy_id, current_user)
    if not body.acknowledge:
        raise HTTPException(
            status_code=422,
            detail="acknowledge must be true: you are passing these checks "
                   "yourself, not the automated judge",
        )
    try:
        overridden = verification_override.apply_override(
            strategy, pass_nos=body.pass_nos, reason=body.reason,
            user_id=current_user.id, user_email=current_user.email)
    except verification_override.OverrideRefused as exc:
        db.rollback()
        security_audit.record(
            db, action=security_audit.STRATEGY_PASSES_OVERRIDE_DENIED, request=request,
            user_id=current_user.id, target_type="strategy", target_id=strategy.id,
            details={"reason": exc.detail})
        db.commit()
        raise HTTPException(status_code=exc.status, detail=exc.detail)

    strategy.status = StrategyStatus.VERIFIED
    strategy.error = None
    security_audit.record(
        db, action=security_audit.STRATEGY_PASSES_OVERRIDDEN, request=request,
        user_id=current_user.id, target_type="strategy", target_id=strategy.id,
        details={"passes": overridden, "reason": body.reason.strip()})
    db.commit()
    db.refresh(strategy)
    return _strategy_out(db, strategy)


@router.delete("/strategies/{strategy_id}")
def delete_strategy(
    strategy_id: uuid.UUID,
    body: StrategyDeleteIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Permanently delete a strategy, after re-checking the account password.

    WHOSE PASSWORD. The person who is signed in (request.state.actor). In a
    workspace, current_user is the OWNER whose data this is, and a manager
    must confirm with their own password, not know the owner's. SDRs and
    viewers never get here: app/services/rbac.py refuses DELETE for both.

    ORDER. Rate limit (well-formed requests only), then ownership (404 -- an id
    from another account is not confirmed to exist, and no password is tested
    against it), then the live-campaign guard, then the password. The limit
    shares RATE_LIMIT_AUTH and its window with login but has its OWN bucket, so
    mistyping here cannot lock anyone out of signing in, while a stolen access
    token still cannot be used to brute-force the password.

    WHAT GOES. Everything that hangs off the strategy -- research steps, leads,
    batches, sequences, messages, analytics -- through the database's ON DELETE
    CASCADE / SET NULL rules. Deleted with a Core DELETE rather than
    session.delete(): the ORM relationships have no passive_deletes, so the ORM
    would first try to NULL every child's NOT NULL strategy_id. The
    tamper-evident activity trail keeps its rows (opaque refs, no FK) by design.

    AUDIT. The deletion and its security_audit_events row commit together; a
    refused attempt is recorded and committed on its own.
    """
    actor: User = getattr(request.state, "actor", None) or current_user
    enforce_rate_limit(f"acct:{actor.id}", "password_confirm", "RATE_LIMIT_AUTH",
                       AUTH_WINDOW_SECONDS)

    strategy = _owned_strategy(db, strategy_id, current_user)

    if strategy.status is StrategyStatus.EXECUTING and strategy.campaign_state == "active":
        raise HTTPException(
            status_code=409,
            detail="This strategy's campaign is still sending. Pause the campaign "
                   "before deleting the strategy.",
        )

    if not auth_svc.verify_password(body.password, actor.password_hash):
        security_audit.record(
            db, action=security_audit.STRATEGY_DELETE_DENIED, request=request,
            user_id=actor.id, owner_user_id=current_user.id,
            target_type="strategy", target_id=strategy.id,
            details={"reason": "invalid_password"})
        db.commit()
        raise HTTPException(status_code=403, detail=INVALID_PASSWORD)

    deleted_at = datetime.now(timezone.utc)
    security_audit.record(
        db, action=security_audit.STRATEGY_DELETED, request=request,
        user_id=actor.id, owner_user_id=current_user.id,
        target_type="strategy", target_id=strategy.id,
        details={"product_id": str(strategy.product_id),
                 "status": strategy.status.value,
                 "flow_type": strategy.flow_type.value,
                 "deleted_at": deleted_at.isoformat()})
    db.flush()
    db.expunge(strategy)
    db.execute(delete(Strategy).where(Strategy.id == strategy_id)
               .execution_options(synchronize_session=False))
    db.commit()
    logger.info("strategy %s deleted by user %s (owner %s)", strategy_id, actor.id,
                current_user.id)
    return {"deleted": True, "id": str(strategy_id), "deleted_at": deleted_at.isoformat()}


@router.get("/strategies/{strategy_id}/campaign")
def campaign_overview(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Campaign overview: leads by status, sends today vs cap, reply rate,
    meetings booked, bounce rate, paused/active state (M3 Chunk 5).

    Owner-scoped like every other /strategies route. This endpoint had NO
    auth dependency at all until now: anyone who knew or guessed a strategy
    UUID could read that account's lead counts, send volume against its
    daily cap, reply/bounce/booking rates and per-channel breakdown, with no
    credentials. It survived the Phase A audit because
    test_campaign_cross_tenant_isolation requested "/campaigns" (plural),
    which matches no route -- the 404 it asserted came from the router, so
    the test was green without ever reaching this handler.
    """
    strategy = _owned_strategy(db, strategy_id, current_user)
    owner = db.get(Product, strategy.product_id)

    lead_counts = dict(db.execute(
        select(Lead.status, func.count(Lead.id))
        .where(Lead.strategy_id == strategy_id).group_by(Lead.status)
    ).all())
    leads_by_status = {s.value: lead_counts.get(s, 0) for s in LeadStatus}

    sent = db.execute(
        select(func.count(Message.id)).join(Lead, Lead.id == Message.lead_id)
        .where(Lead.strategy_id == strategy_id,
               Message.status.in_([MessageStatus.SENT, MessageStatus.BOUNCED]))
    ).scalar_one()

    def _outcome_count(event: OutcomeEvent) -> int:
        return db.execute(
            select(func.count(Outcome.id)).join(Lead, Lead.id == Outcome.lead_id)
            .where(Lead.strategy_id == strategy_id, Outcome.event == event)
        ).scalar_one()

    replied = _outcome_count(OutcomeEvent.REPLIED)
    bounced = _outcome_count(OutcomeEvent.BOUNCED)
    booked = _outcome_count(OutcomeEvent.BOOKED)
    unsubscribed = _outcome_count(OutcomeEvent.UNSUBSCRIBED)

    now = datetime.now(timezone.utc)
    sends_today = cap_today = None
    product = owner
    account = db.execute(
        select(GmailAccount).where(GmailAccount.user_id == product.user_id)
    ).scalar_one_or_none()
    if account is not None:
        sends_today = engine.sends_today(db, str(account.id), now)
        # F03: the same cap the send path enforces (stepped ramp when the
        # Deliverability Autopilot is on; unchanged when it is off).
        from app.services import deliverability_autopilot  # noqa: PLC0415

        cap_today = engine.ramp_allowance(db, account, now.date(),
                                          autopilot=deliverability_autopilot.enabled(db))

    # ---- per-channel stats (M4 Chunk 3) ---------------------------------
    from app.db.models import ChannelType, InboundReply, WhatsAppTemplate
    from app.services.whatsapp_window import window_state_for_lead

    def _channel_block(channel: ChannelType) -> dict:
        sent_c = db.execute(
            select(func.count(Message.id)).join(Lead, Lead.id == Message.lead_id)
            .where(Lead.strategy_id == strategy_id,
                   Message.channel == channel,
                   Message.status.in_([MessageStatus.SENT, MessageStatus.BOUNCED]))
        ).scalar_one()
        failed_c = db.execute(
            select(func.count(Message.id)).join(Lead, Lead.id == Message.lead_id)
            .where(Lead.strategy_id == strategy_id,
                   Message.channel == channel,
                   Message.status.in_([MessageStatus.FAILED, MessageStatus.BOUNCED]))
        ).scalar_one()
        replied_c = db.execute(
            select(func.count(Outcome.id)).join(Lead, Lead.id == Outcome.lead_id)
            .where(Lead.strategy_id == strategy_id,
                   Outcome.event == OutcomeEvent.REPLIED,
                   Outcome.channel == channel.value)
        ).scalar_one()
        return {
            "sent_total": sent_c,
            "delivery_rate": round((sent_c - failed_c) / sent_c, 4) if sent_c else None,
            "reply_rate": round(replied_c / sent_c, 4) if sent_c else None,
        }

    email_stats = _channel_block(ChannelType.EMAIL)
    email_stats["sends_today"] = sends_today
    email_stats["daily_cap_today"] = cap_today

    wa_stats = _channel_block(ChannelType.WHATSAPP)
    wa_stats["sends_today"] = engine.whatsapp_sends_today(db, now)
    wa_stats["daily_cap_today"] = engine.whatsapp_daily_allowance(db, now.date())
    wa_stats["window_open_count"] = sum(
        1 for lead_row in db.execute(
            select(Lead).where(Lead.strategy_id == strategy_id,
                               Lead.whatsapp_last_inbound_at.isnot(None))
        ).scalars()
        if window_state_for_lead(lead_row, now).open
    )
    template_ids = db.execute(
        select(Message.whatsapp_template_id)
        .join(Lead, Lead.id == Message.lead_id)
        .where(Lead.strategy_id == strategy_id,
               Message.whatsapp_template_id.isnot(None))
        .distinct()
    ).scalars().all()
    wa_stats["templates_in_use"] = [
        {"id": str(t.id), "name": t.name, "language": t.language,
         "status": t.status.value}
        for t in (db.get(WhatsAppTemplate, tid) for tid in template_ids)
        if t is not None
    ]
    needs_attention = db.execute(
        select(func.count(Message.id)).join(Lead, Lead.id == Message.lead_id)
        .where(Lead.strategy_id == strategy_id,
               Message.status == MessageStatus.NEEDS_TEMPLATE)
    ).scalar_one()
    wa_stats["needs_template_count"] = needs_attention

    return {
        "strategy_id": str(strategy.id),
        "campaign_state": strategy.campaign_state,
        "campaign_pause_reason": strategy.campaign_pause_reason,
        "leads_by_status": leads_by_status,
        "sent_total": sent,
        "sends_today": sends_today,
        "daily_cap_today": cap_today,
        "channels": {"email": email_stats, "whatsapp": wa_stats},
        "reply_rate": round(replied / sent, 4) if sent else 0.0,
        "bounce_rate": round(bounced / sent, 4) if sent else 0.0,
        "bounce_pause_threshold": settings.bounce_rate_pause_threshold,
        "meetings_booked": booked,
        "unsubscribed": unsubscribed,
    }


# NOTE: a GET /strategies list route used to live here (added for the M6
# CLI's `clienthunter status` command). It was removed because
# app/api/ui_support.py registers the SAME path earlier in app/main.py's
# include_router() order, so this one was silently unreachable -- by the
# frontend AND by the CLI. ui_support.py's version is what's actually
# served; it now has the owner-check this one had. CLI compatibility
# (its response shape is lighter than StrategyStatusOut -- no per-phase
# progress/verification) is a follow-up: either point the CLI at a
# lighter shape intentionally, or give this route a distinct path like
# /strategies/full and update the CLI to use it.
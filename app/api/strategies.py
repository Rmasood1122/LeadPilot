"""Strategies — creation (enqueues the pipeline) and status/progress."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limiting import enforce_rate_limit
from app.api.schemas import (
    PhaseProgress,
    PipelineProgress,
    StrategyCreate,
    StrategyOut,
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
from app.services import sequence_engine as engine
from app.pipeline.engine import pipelines_for_flow
from app.pipeline.registry import phase_title
from app.workers import tasks as worker_tasks

router = APIRouter(tags=["strategies"])


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
) -> Strategy:
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

    strategy = Strategy(product_id=product.id, flow_type=flow_type)
    db.add(strategy)
    db.commit()
    db.refresh(strategy)

    worker_tasks.run_pipeline.delay(str(strategy.id))
    return strategy


@router.get("/strategies/{strategy_id}", response_model=StrategyStatusOut)
def get_strategy(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StrategyStatusOut:
    """Overall status + per-phase progress for every pipeline in the flow."""
    strategy = _owned_strategy(db, strategy_id, current_user)

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
                total=9,
            )
            for p in range(1, 9)
        ]
        progress.append(
            PipelineProgress(
                pipeline=pipeline.value,
                done=sum(counts.values()),
                total=72,
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
    )


@router.post("/strategies/{strategy_id}/resume", response_model=StrategyOut, status_code=202)
def resume_strategy(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Strategy:
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

    worker_tasks.run_pipeline.delay(str(strategy.id))
    return strategy


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
        cap_today = engine.daily_allowance(account, now.date())

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
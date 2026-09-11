"""Feature Group 1 API — consensus zones, market signals, strategy versions,
lead rescoring.

Everything is owner-scoped through the same helpers the leads router uses
(404 for another account's strategy or lead, never 403), and anything that
spends a model call or a paid API call is limited by RATE_LIMIT_AI_ACTION.
"""

# NOTE: deliberately NO `from __future__ import annotations` (FastAPI).

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.leads import _owned_lead, _owned_strategy
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import (
    PipelineKind,
    Strategy,
    StrategyModelOutput,
    StrategyVersion,
    User,
)
from app.services import consensus, lead_scoring, strategy_mutation
from app.workers import intelligence_tasks

router = APIRouter(tags=["ai-intelligence"])

_AI_LIMIT = "RATE_LIMIT_AI_ACTION"


class ZoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pipeline: PipelineKind
    phase: int
    step_no: int
    section_title: str
    topic: str
    claude_position: str
    gpt_position: str
    severity: str
    similarity: float | None


class VersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_no: int
    parent_version_id: uuid.UUID | None
    change_summary: str | None
    changes_json: dict | None
    outcome_snapshot_json: dict | None
    trigger: str
    status: str
    applied_at: datetime | None
    created_at: datetime


class VersionOut(VersionSummary):
    document: str


class IntelligenceOut(BaseModel):
    consensus_status: str | None
    zones: list[ZoneOut]
    market_signals: dict | None
    market_signals_fetched_at: datetime | None
    versions: list[VersionSummary]


class ModelOutputOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    model: str
    output: str | None
    error: str | None
    latency_ms: int | None


class LeadScoreOut(BaseModel):
    lead_id: uuid.UUID
    ai_booking_likelihood: int | None
    ai_score_reason: str | None
    ai_score_factors: dict | None
    ai_scored_at: datetime | None


def _versions(db: Session, strategy_id) -> list[StrategyVersion]:
    return list(db.execute(
        select(StrategyVersion).where(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version_no.desc())
    ).scalars().all())


def _owned_version(db: Session, strategy: Strategy, version_id: uuid.UUID) -> StrategyVersion:
    version = db.get(StrategyVersion, version_id)
    if version is None or version.strategy_id != strategy.id:
        raise HTTPException(status_code=404, detail="version not found")
    return version


# ---------------------------------------------------------------------------
# Consensus + market signals
# ---------------------------------------------------------------------------


@router.get("/strategies/{strategy_id}/intelligence", response_model=IntelligenceOut)
def strategy_intelligence(strategy_id: uuid.UUID, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)) -> IntelligenceOut:
    """Everything the strategy document page shows next to the document:
    uncertain zones, the market signals the research used, and versions."""
    strategy = _owned_strategy(db, strategy_id, current_user)
    return IntelligenceOut(
        consensus_status=strategy.consensus_status,
        zones=[ZoneOut.model_validate(z) for z in consensus.zones_for(db, strategy.id)],
        market_signals=strategy.market_signals_json,
        market_signals_fetched_at=strategy.market_signals_fetched_at,
        versions=[VersionSummary.model_validate(v) for v in _versions(db, strategy.id)],
    )


@router.get("/strategies/{strategy_id}/model-outputs", response_model=list[ModelOutputOut])
def strategy_model_outputs(strategy_id: uuid.UUID, step_no: int = Query(ge=1, le=72),
                           pipeline: PipelineKind = PipelineKind.STRATEGY,
                           db: Session = Depends(get_db),
                           current_user: User = Depends(get_current_user)) -> list:
    """Both models' raw answers for one section -- the "compare" view."""
    strategy = _owned_strategy(db, strategy_id, current_user)
    return list(db.execute(
        select(StrategyModelOutput).where(
            StrategyModelOutput.strategy_id == strategy.id,
            StrategyModelOutput.pipeline == pipeline,
            StrategyModelOutput.step_no == step_no,
        ).order_by(StrategyModelOutput.provider)
    ).scalars().all())


@router.post("/strategies/{strategy_id}/market-signals/refresh", status_code=202)
def refresh_market_signals(strategy_id: uuid.UUID, db: Session = Depends(get_db),
                           current_user: User = Depends(get_current_user)) -> dict:
    """Re-fetch live signals. They are used by the NEXT pipeline run; an
    existing document is not re-researched."""
    enforce_rate_limit(str(current_user.id), "ai_action", _AI_LIMIT)
    strategy = _owned_strategy(db, strategy_id, current_user)
    queued = intelligence_tasks.enqueue(intelligence_tasks.refresh_market_signals,
                                        str(strategy.id))
    return {"queued": queued}


# ---------------------------------------------------------------------------
# Strategy versions (mutation)
# ---------------------------------------------------------------------------


@router.get("/strategies/{strategy_id}/versions", response_model=list[VersionSummary])
def list_versions(strategy_id: uuid.UUID, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> list:
    strategy = _owned_strategy(db, strategy_id, current_user)
    return _versions(db, strategy.id)


@router.get("/strategies/{strategy_id}/versions/{version_id}", response_model=VersionOut)
def get_version(strategy_id: uuid.UUID, version_id: uuid.UUID,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)) -> StrategyVersion:
    strategy = _owned_strategy(db, strategy_id, current_user)
    return _owned_version(db, strategy, version_id)


@router.post("/strategies/{strategy_id}/mutate", response_model=VersionOut, status_code=201)
def mutate_strategy(strategy_id: uuid.UUID, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)) -> StrategyVersion:
    """Propose a mutation now, whatever the idle state -- the user asked."""
    enforce_rate_limit(str(current_user.id), "ai_action", _AI_LIMIT)
    strategy = _owned_strategy(db, strategy_id, current_user)
    if not strategy.strategy_document:
        raise HTTPException(status_code=409, detail="this strategy has no document yet")
    try:
        return strategy_mutation.mutate(db, strategy, trigger="manual",
                                        actor_user_id=current_user.id)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=502,
                            detail=f"the mutation could not be generated: {exc}") from exc


@router.post("/strategies/{strategy_id}/versions/{version_id}/apply",
             response_model=VersionOut)
def apply_version(strategy_id: uuid.UUID, version_id: uuid.UUID,
                  db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> StrategyVersion:
    strategy = _owned_strategy(db, strategy_id, current_user)
    version = _owned_version(db, strategy, version_id)
    if version.status == "applied":
        raise HTTPException(status_code=409, detail="this version is already applied")
    return strategy_mutation.apply_version(db, strategy, version)


@router.post("/strategies/{strategy_id}/versions/{version_id}/dismiss",
             response_model=VersionOut)
def dismiss_version(strategy_id: uuid.UUID, version_id: uuid.UUID,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)) -> StrategyVersion:
    strategy = _owned_strategy(db, strategy_id, current_user)
    version = _owned_version(db, strategy, version_id)
    if version.status != "proposed":
        raise HTTPException(status_code=409, detail="only a proposed version can be dismissed")
    version.status = "dismissed"
    db.commit()
    return version


# ---------------------------------------------------------------------------
# Lead scoring
# ---------------------------------------------------------------------------


@router.post("/strategies/{strategy_id}/leads/rescore", status_code=202)
def rescore_strategy_leads(strategy_id: uuid.UUID, db: Session = Depends(get_db),
                           current_user: User = Depends(get_current_user)) -> dict:
    enforce_rate_limit(str(current_user.id), "ai_action", _AI_LIMIT)
    strategy = _owned_strategy(db, strategy_id, current_user)
    queued = intelligence_tasks.enqueue(intelligence_tasks.rescore_strategy,
                                        str(strategy.id))
    return {"queued": queued}


@router.post("/leads/{lead_id}/rescore", response_model=LeadScoreOut)
def rescore_lead(lead_id: uuid.UUID, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)) -> LeadScoreOut:
    enforce_rate_limit(str(current_user.id), "ai_action", _AI_LIMIT)
    lead = _owned_lead(db, lead_id, current_user)
    strategy = db.get(Strategy, lead.strategy_id)
    lead_scoring.score_leads(db, strategy, [lead])
    return LeadScoreOut(lead_id=lead.id, ai_booking_likelihood=lead.ai_booking_likelihood,
                        ai_score_reason=lead.ai_score_reason,
                        ai_score_factors=lead.ai_score_factors,
                        ai_scored_at=lead.ai_scored_at)

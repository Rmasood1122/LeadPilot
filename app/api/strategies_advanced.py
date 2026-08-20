"""
Strategies API — adds C4 endpoints to the M3 base.

New endpoints:
  GET /strategies/{id}/mv-results           — multi-variate test results
  GET /strategies/{id}/personalization-stats — personalization health
  GET /plans                                 — public plan matrix (C5)
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.plans import PLANS, check_feature, PlanLimitExceeded, plan_limit_response

logger = get_logger("api.strategies")
router = APIRouter(prefix="/strategies", tags=["strategies"])


# ---------------------------------------------------------------------------
# Multi-variate results (C4)
# ---------------------------------------------------------------------------

@router.get("/{strategy_id}/mv-results")
async def get_mv_results(
    strategy_id: str,
    metric: str = Query("meeting_rate"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """
    Multi-variate test results for all steps with >2 variants.
    Requires ab_testing feature (starter plan+).
    """
    try:
        check_feature(current_user, "ab_testing")
    except PlanLimitExceeded as e:
        raise HTTPException(status_code=402, detail=plan_limit_response(e))

    # Verify ownership
    _check_strategy_ownership(db, strategy_id, str(current_user.id))

    from sqlalchemy import text
    # Get all variants for this strategy
    rows = db.execute(text("""
        SELECT DISTINCT variant FROM outcomes
        WHERE strategy_id = :sid AND variant IS NOT NULL
        ORDER BY variant
    """), {"sid": strategy_id}).scalars().all()

    variants = list(rows)
    if len(variants) < 2:
        return {
            "strategy_id": strategy_id,
            "variants": variants,
            "message": "Need at least 2 variants to compare.",
        }

    from app.services.multi_variate import compare_multi_variants
    from dataclasses import asdict

    result = compare_multi_variants(
        strategy_id=strategy_id,
        variants=variants,
        metric=metric,
        db_session=db,
    )

    return {
        "strategy_id": result.strategy_id,
        "variants": result.variants,
        "metric": result.metric,
        "per_variant_stats": {
            v: {
                "variant": s.variant,
                "rate": s.rate,
                "sample_size": s.sample_size,
                "event_count": s.event_count,
                "rank": s.rank,
            }
            for v, s in result.per_variant_stats.items()
        },
        "overall_significant": result.overall_significant,
        "overall_p_value": result.overall_p_value,
        "pairwise_results": [
            {
                "variant_a": pr.variant_a,
                "variant_b": pr.variant_b,
                "p_value": pr.p_value,
                "corrected_threshold": pr.corrected_threshold,
                "significant": pr.significant,
            }
            for pr in result.pairwise_results
        ],
        "winner": result.winner,
        "runner_up": result.runner_up,
        "harm_flags": result.harm_flags,
        "recommendation": result.recommendation,
    }


# ---------------------------------------------------------------------------
# Personalization stats (C4)
# ---------------------------------------------------------------------------

@router.get("/{strategy_id}/personalization-stats")
async def get_personalization_stats(
    strategy_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """
    Per-strategy personalization scores and correlation with reply rate.
    Used by the Campaign page "Personalization health" indicator.
    """
    _check_strategy_ownership(db, strategy_id, str(current_user.id))

    from app.services.personalization_scorer import score_strategy_messages
    stats = score_strategy_messages(strategy_id, db)

    # Determine health indicator
    corr = stats.get("correlation")
    avg_score = stats.get("avg_score")

    if corr is None or stats.get("sample_size", 0) < 10:
        indicator = "grey"
        indicator_label = "Insufficient data"
    elif corr > 0.3 and (avg_score or 0) > 0.5:
        indicator = "green"
        indicator_label = "Strong personalization-reply correlation"
    elif (avg_score or 0) < 0.3:
        indicator = "yellow"
        indicator_label = "Messages are not well-personalized"
    else:
        indicator = "grey"
        indicator_label = "Moderate personalization"

    return {
        "strategy_id": strategy_id,
        **stats,
        "health_indicator": indicator,
        "health_label": indicator_label,
    }


# ---------------------------------------------------------------------------
# Public plans endpoint (C5)
# ---------------------------------------------------------------------------

plans_router = APIRouter(tags=["plans"])

@plans_router.get("/plans")
async def get_plans() -> dict:
    """Public, no auth. Returns the full plan matrix for the pricing/upgrade UI."""
    return {"plans": PLANS}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_strategy_ownership(db, strategy_id: str, user_id: str) -> None:
    from sqlalchemy import text
    row = db.execute(text("""
        SELECT s.id FROM strategies s
        JOIN products p ON p.id = s.product_id
        WHERE s.id = :sid AND p.user_id = :uid
    """), {"sid": strategy_id, "uid": user_id}).first()
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found")

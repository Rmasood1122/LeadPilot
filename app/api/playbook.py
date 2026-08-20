"""
Playbook API — M8-C1+C2 base + C4 additions.

New endpoints (C4):
  GET /playbook/send-times       — send-time recommendation for channel+ICP
  GET /playbook/subject-patterns — top subject line patterns by channel
  GET /playbook/scores           — playbook scores (with decay metadata)
  GET /playbook/similar-strategies — TF-IDF similarity
  POST /playbook/aggregate       — trigger nightly aggregation (admin)
  POST /playbook/promote-winners — trigger A/B promotion sweep (admin)
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.plans import check_feature, plan_limit_response, PlanLimitExceeded

logger = get_logger("api.playbook")
router = APIRouter(prefix="/playbook", tags=["playbook"])


# ---------------------------------------------------------------------------
# Send-time optimizer (C4)
# ---------------------------------------------------------------------------

@router.get("/send-times")
async def get_send_times(
    channel: str = Query("gmail"),
    icp_industry: Optional[str] = Query(None),
    icp_company_size: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
) -> dict:
    """
    Recommended send-time slots for a channel+ICP combination.
    Returns up to 5 slots sorted by expected_reply_rate.
    """
    try:
        check_feature(current_user, "playbook_access")
    except PlanLimitExceeded as e:
        raise HTTPException(status_code=402, detail=plan_limit_response(e))

    from app.services.send_time_optimizer import get_send_time_recommendation
    from dataclasses import asdict

    rec = get_send_time_recommendation(channel, icp_industry, icp_company_size)
    return {
        "channel": rec.channel,
        "icp_industry": rec.icp_industry,
        "icp_company_size": rec.icp_company_size,
        "confidence": rec.confidence,
        "fallback_used": rec.fallback_used,
        "recommended_slots": rec.recommended_slots,
    }


# ---------------------------------------------------------------------------
# Subject line patterns (C4)
# ---------------------------------------------------------------------------

@router.get("/subject-patterns")
async def get_subject_patterns(
    channel: str = Query("gmail"),
    top_n: int = Query(5, ge=1, le=10),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[dict]:
    """
    Top subject line patterns by meeting rate for a channel.
    Only returns patterns with is_reliable=True.
    """
    try:
        check_feature(current_user, "playbook_access")
    except PlanLimitExceeded as e:
        raise HTTPException(status_code=402, detail=plan_limit_response(e))

    from app.services.subject_intelligence import get_top_patterns
    from dataclasses import asdict

    patterns = get_top_patterns(db, channel=channel, top_n=top_n)
    return [
        {
            "pattern_type": p.pattern_type,
            "example": p.example,
            "avg_reply_rate": p.avg_reply_rate,
            "avg_meeting_rate": p.avg_meeting_rate,
            "sample_size": p.sample_size,
            "is_reliable": p.is_reliable,
            "channel": p.channel,
        }
        for p in patterns
    ]


# ---------------------------------------------------------------------------
# Playbook scores (with decay metadata)
# ---------------------------------------------------------------------------

@router.get("/scores")
async def get_playbook_scores(
    strategy_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[dict]:
    """User's playbook scores. Includes decay metadata (effective_n, trend)."""
    try:
        check_feature(current_user, "playbook_access")
    except PlanLimitExceeded as e:
        raise HTTPException(status_code=402, detail=plan_limit_response(e))

    from sqlalchemy import text
    params: dict = {"user_id": str(current_user.id)}
    where_extra = ""
    if strategy_id:
        where_extra = "AND s.id = :sid"
        params["sid"] = strategy_id

    try:
        rows = db.execute(text(f"""
            SELECT DISTINCT ps.pattern_key, ps.variant, ps.reply_rate, ps.booking_rate,
                   ps.sample_size, ps.effective_sample_size, ps.is_reliable,
                   ps.decay_half_life_days, ps.trend, ps.last_aggregated_at,
                   s.id AS strategy_id
            FROM playbook_scores ps
            JOIN strategies s ON s.pattern_key = ps.pattern_key
            JOIN products p ON p.id = s.product_id
            WHERE p.user_id = :user_id
              {where_extra}
            ORDER BY ps.reply_rate DESC NULLS LAST
            LIMIT 200
        """), params).mappings().all()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error("playbook.scores_failed", error=str(e))
        return []


# ---------------------------------------------------------------------------
# Strategy similarity (C2 — unchanged)
# ---------------------------------------------------------------------------

@router.get("/similar-strategies")
async def similar_strategies(
    query: str = Query(..., min_length=5),
    top_n: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[dict]:
    from app.services.similarity import StrategySimilarityIndex
    results = StrategySimilarityIndex.find_similar(query, db, user_id=str(current_user.id), top_n=top_n)
    return results


# ---------------------------------------------------------------------------
# Admin actions (aggregate + promote)
# ---------------------------------------------------------------------------

@router.post("/aggregate")
async def trigger_aggregate(admin=Depends(require_admin)) -> dict:
    from app.workers.learning_tasks import run_strategy_aggregation
    run_strategy_aggregation.delay()
    return {"status": "triggered"}


@router.post("/promote-winners")
async def trigger_promote(admin=Depends(require_admin)) -> dict:
    from app.workers.learning_tasks import auto_promote_winners
    auto_promote_winners.delay()
    return {"status": "triggered"}

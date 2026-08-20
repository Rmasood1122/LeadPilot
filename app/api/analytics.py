"""Analytics aggregates + manual campaign controls (M5 additions).

GET  /strategies/{id}/analytics?granularity=day
    Time series of outcome counts grouped by (bucket, channel, event) plus
    a per-variant aggregate (sent/replied/booked by A/B variant) — the
    groundwork the M8 learning loop and the Analytics page both read.
POST /strategies/{id}/campaign/pause   — manual pause (state + reason)
POST /strategies/{id}/campaign/resume  — clears a manual OR bounce pause
    (resuming after a bounce pause is a deliberate human decision; the 3%
    monitor will simply pause again if bounces continue).
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import Lead, Message, Outcome, OutcomeEvent, Product, Strategy, User
from app.services import sequence_engine as engine

router = APIRouter(tags=["analytics"])

_BUCKETS = {"day": "%Y-%m-%d", "week": "%Y-%W", "month": "%Y-%m"}


def _owned_strategy(strategy_id: uuid.UUID, db: Session, current_user: User) -> Strategy:
    """Fetch a strategy and verify it belongs to current_user, else 404.

    Guards both read (analytics) and write (pause/resume) endpoints below —
    without this, any authenticated user could view another account's
    outcome data or sabotage their campaign by pausing/resuming it.
    """
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    product = db.get(Product, strategy.product_id)
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="strategy not found")
    return strategy


@router.get("/strategies/{strategy_id}/analytics")
def analytics(
    strategy_id: uuid.UUID,
    granularity: str = Query(default="day"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _owned_strategy(strategy_id, db, current_user)
    fmt = _BUCKETS.get(granularity)
    if fmt is None:
        raise HTTPException(status_code=422,
                            detail=f"granularity must be one of {sorted(_BUCKETS)}")

    # NOTE: strftime works on SQLite (tests); PostgreSQL uses to_char via
    # func.to_char — pick per dialect so both run the same query shape.
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        pg_fmt = {"day": "YYYY-MM-DD", "week": "IYYY-IW", "month": "YYYY-MM"}[granularity]
        bucket = func.to_char(Outcome.ts, pg_fmt)
    else:
        bucket = func.strftime(fmt, Outcome.ts)

    series_rows = db.execute(
        select(bucket.label("bucket"), Outcome.channel, Outcome.event,
               func.count(Outcome.id))
        .join(Lead, Lead.id == Outcome.lead_id)
        .where(Lead.strategy_id == strategy_id)
        .group_by("bucket", Outcome.channel, Outcome.event)
        .order_by("bucket")
    ).all()

    variant_rows = db.execute(
        select(Message.variant, Outcome.event, func.count(Outcome.id))
        .join(Message, Message.id == Outcome.message_id)
        .join(Lead, Lead.id == Outcome.lead_id)
        .where(Lead.strategy_id == strategy_id)
        .group_by(Message.variant, Outcome.event)
    ).all()

    variants: dict[str, dict[str, int]] = {}
    for variant, event, count in variant_rows:
        variants.setdefault(variant, {})[event.value] = count

    return {
        "strategy_id": str(strategy_id),
        "granularity": granularity,
        "series": [
            {"bucket": b, "channel": ch, "event": ev.value, "count": n}
            for b, ch, ev, n in series_rows
        ],
        "variants": variants,
        # M8 fills this with playbook scores; the UI renders the container.
        "learning_insights": None,
    }


@router.post("/strategies/{strategy_id}/campaign/pause")
def pause_campaign(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    strategy = _owned_strategy(strategy_id, db, current_user)
    strategy.campaign_state = "paused_manual"
    strategy.campaign_pause_reason = "paused by user"
    db.commit()
    return {"campaign_state": strategy.campaign_state,
            "campaign_pause_reason": strategy.campaign_pause_reason}


@router.post("/strategies/{strategy_id}/campaign/resume")
def resume_campaign(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    strategy = _owned_strategy(strategy_id, db, current_user)
    strategy.campaign_state = engine.CAMPAIGN_ACTIVE
    strategy.campaign_pause_reason = None
    db.commit()
    return {"campaign_state": strategy.campaign_state,
            "campaign_pause_reason": None}
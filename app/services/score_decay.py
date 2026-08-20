"""
Score decay engine — exponential time-decay for playbook scores.

Old high-sample scores crowd out recent signal.
Decay model:

  effective_score = Σ (outcome_value × w_i) / Σ w_i
  where w_i = e^(-λ × days_since_outcome)
  and   λ   = ln(2) / PLAYBOOK_SCORE_HALF_LIFE_DAYS

At t = half_life: weight = 0.5  (half as influential)
At t = 0:         weight = 1.0  (full influence)

Effective sample size:
  effective_n = Σ w_i   (NOT raw count — a pattern with 100 old outcomes
                          may have effective_n < PLAYBOOK_MIN_SAMPLE)

Configuration:
  PLAYBOOK_SCORE_HALF_LIFE_DAYS  (default: 90)
"""
from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from typing import Optional

from app.core.logging import get_logger

logger = get_logger("services.score_decay")

DEFAULT_HALF_LIFE_DAYS = 90


def _lambda(half_life_days: int) -> float:
    """Decay constant λ = ln(2) / half_life."""
    return math.log(2) / max(half_life_days, 1)


def _weight(days_since: float, lam: float) -> float:
    """Exponential weight for an outcome that is `days_since` days old."""
    return math.exp(-lam * days_since)


def compute_decayed_score(
    outcomes: list[dict],
    metric_key: str = "is_reply",
    half_life_days: int = DEFAULT_HALF_LIFE_DAYS,
    reference_dt: Optional[datetime.datetime] = None,
) -> tuple[float, float]:
    """
    Compute a decay-weighted score for a list of outcome dicts.

    Each dict must have:
        "ts": datetime.datetime    — when the outcome occurred
        metric_key: int | float    — 1 for event (e.g., replied), 0 for non-event

    Returns: (decayed_rate: float, effective_n: float)
      decayed_rate is in [0, 1]; effective_n is the sum of weights.
    """
    if not outcomes:
        return 0.0, 0.0

    # REPAIR: outcomes.ts is timezone-aware (DateTime(timezone=True)) —
    # the reference must be aware too or the subtraction raises TypeError.
    ref = reference_dt or datetime.datetime.now(datetime.timezone.utc)
    lam = _lambda(half_life_days)

    weighted_sum = 0.0
    weight_total = 0.0

    for o in outcomes:
        ts = o.get("ts")
        if ts is None:
            continue
        if isinstance(ts, str):
            ts = datetime.datetime.fromisoformat(ts)
        if ts.tzinfo is None:  # REPAIR: naive rows (test DBs) → assume UTC
            ts = ts.replace(tzinfo=datetime.timezone.utc)

        days_since = max(0.0, (ref - ts).total_seconds() / 86400.0)
        w = _weight(days_since, lam)
        value = float(o.get(metric_key, 0))

        weighted_sum += value * w
        weight_total += w

    if weight_total == 0.0:
        return 0.0, 0.0

    return weighted_sum / weight_total, weight_total


def determine_trend(
    current_decayed_score: float,
    previous_decayed_score: Optional[float],
    threshold: float = 0.005,
) -> str:
    """
    Compare this run's decayed score vs last run's.

    Returns: "rising" | "falling" | "stable" | "new"

    A "rising" trend means recent outcomes are outperforming historical ones
    — more meaningful than comparing raw scores (decay amplifies the recency signal).
    """
    if previous_decayed_score is None:
        return "new"
    delta = current_decayed_score - previous_decayed_score
    if delta > threshold:
        return "rising"
    if delta < -threshold:
        return "falling"
    return "stable"


def compute_scores_with_decay(db_session, half_life_days: Optional[int] = None) -> dict[str, dict]:
    """
    Full decayed aggregation over the outcomes table.

    Replaces the simple mean in the nightly aggregation job.
    Returns: {pattern_key: {reply_rate, meeting_rate, effective_n, oldest_outcome_ts, trend}}

    Called from learning_tasks.run_strategy_aggregation().
    """
    from app.core.config import settings
    from sqlalchemy import text

    hl = half_life_days or settings.PLAYBOOK_SCORE_HALF_LIFE_DAYS

    # Pull raw outcomes with timestamps
    sql = text("""
        SELECT
            s.pattern_key,
            o.event,
            o.ts,
            o.variant,
            o.lead_id
        FROM outcomes o
        JOIN strategies s ON s.id = o.strategy_id
        WHERE o.event IN ('sent', 'replied', 'booked', 'won')
          AND s.pattern_key IS NOT NULL
        ORDER BY s.pattern_key, o.ts
    """)

    try:
        rows = db_session.execute(sql).mappings().all()
    except Exception as e:
        logger.error("score_decay.query_failed", error=str(e))
        return {}

    from collections import defaultdict
    # group by (pattern_key, variant)
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        k = (row["pattern_key"], row["variant"] or "control")
        buckets[k].append({"ts": row["ts"], "event": row["event"],
                           "lead_id": row["lead_id"]})

    results: dict[str, dict] = {}
    now = datetime.datetime.now(datetime.timezone.utc)  # REPAIR: tz-aware (see above)
    min_sample = settings.PLAYBOOK_MIN_SAMPLE

    for (pattern_key, variant), raw_outcomes in buckets.items():
        sends = [o for o in raw_outcomes if o["event"] == "sent"]
        replies = [o for o in raw_outcomes if o["event"] == "replied"]
        bookings = [o for o in raw_outcomes if o["event"] == "booked"]

        if not sends:
            continue

        # Decayed reply rate
        # For each send, check if there's a corresponding reply (simplified: count weighted replies / weighted sends)
        _, eff_n = compute_decayed_score(sends, metric_key="noop", half_life_days=hl, reference_dt=now)

        # Attribute a reply/booking to the send that earned it BY LEAD.
        #
        # This used to ask "is there any reply within 10 days of this send?",
        # which is not attribution at all: one reply inside the window marked
        # EVERY send in that window as replied, so a campaign of 50 sends with
        # 8 replies scored reply_rate 1.0 instead of 0.16. Every variant then
        # scored ~1.0, so A/B promotion could never separate a winner from a
        # loser and auto_promote_winners never fired. outcomes.lead_id +
        # ix_outcomes_lead_event exist precisely to make this a set lookup.
        replied_leads = {o["lead_id"] for o in replies if o["lead_id"] is not None}
        booked_leads = {o["lead_id"] for o in bookings if o["lead_id"] is not None}

        reply_outcomes = [
            {**s, "is_reply": 1 if s["lead_id"] in replied_leads else 0}
            for s in sends
        ]

        decayed_reply, _ = compute_decayed_score(reply_outcomes, "is_reply", hl, now)

        booking_outcomes = [
            {**s, "is_booked": 1 if s["lead_id"] in booked_leads else 0}
            for s in sends
        ]

        decayed_booking, _ = compute_decayed_score(booking_outcomes, "is_booked", hl, now)

        oldest_ts = min(o["ts"] for o in raw_outcomes) if raw_outcomes else None

        composite_key = f"{pattern_key}::{variant}"
        results[composite_key] = {
            "pattern_key": pattern_key,
            "variant": variant,
            "reply_rate": round(decayed_reply, 4),
            "booking_rate": round(decayed_booking, 4),
            "effective_n": round(eff_n, 2),
            "raw_n": len(sends),
            "is_reliable": eff_n >= min_sample,
            "oldest_outcome_ts": oldest_ts,
            "half_life_days": hl,
        }

    logger.info("score_decay.computed", pattern_count=len(results), half_life_days=hl)
    return results

"""Feature 1 — pipeline health score.

ONE number, 0-100, that answers "is my outbound pipeline healthy right now?"
so the founder does not have to read the analytics, funnel, CRM and reply
screens and synthesise the answer themselves.

THE FORMULA (each component is 0-100 before weighting)

    reply_rate        replies / sends                       weight 0.35
    completion        completed enrollments / enrollments    weight 0.25
    freshness         decay on days since the last lead      weight 0.20
    conversations     open replies x 10, capped at 100       weight 0.20

Weights sum to 1.0, so the weighted sum is already on a 0-100 scale.

WHY THESE FOUR. A pipeline dies in exactly four ways and each component
catches one: nobody answers (reply_rate), sequences stall before they finish
(completion), no new names are going in (freshness), or replies are arriving
and nobody is working them (conversations). Three of the four can look fine
while the fourth is what is actually killing the pipeline, which is why this
is a weighted blend and not a single ratio.

Everything is read from live rows -- outcomes, enrollments, leads. The
`strategies.pipeline_health_score` / `health_band` / `health_message` /
`health_updated_at` columns are a CACHE of the last computation (written by
the six-hourly sweep in app/workers/health_tasks.py and by the API when it
recomputes), never the source of truth.
"""

import logging
import uuid as uuid_module
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    EnrollmentStatus,
    Lead,
    LeadStatus,
    Outcome,
    OutcomeEvent,
    Sequence,
    SequenceEnrollment,
    Strategy,
)

logger = logging.getLogger(__name__)

# Component weights. These must sum to 1.0 -- asserted below, because a
# weights table that silently stops summing to one turns every score in the
# product into a number on a different scale, with no error anywhere.
WEIGHTS = {
    "reply_rate": 0.35,
    "completion": 0.25,
    "freshness": 0.20,
    "conversations": 0.20,
}
if abs(sum(WEIGHTS.values()) - 1.0) > 1e-9:  # not an assert: `python -O` strips those
    raise RuntimeError(
        f"pipeline health weights must sum to 1.0, got {sum(WEIGHTS.values())}")

# Lead freshness decay: full marks up to FRESH_DAYS, nothing from STALE_DAYS,
# straight-line in between.
FRESH_DAYS = 3
STALE_DAYS = 30

# An open reply is worth ten points, so ten unanswered conversations max out
# the component. Beyond ten, more unanswered replies are not a healthier
# pipeline anyway.
CONVERSATION_POINTS = 10

# (inclusive upper bound, band, message). Ordered lowest first; the first
# bound a score falls at or under wins.
BANDS = (
    (40, "critical", "Pipeline empty. Add leads immediately."),
    (60, "low", "Pipeline thinning. Add 10 leads this week."),
    (80, "moderate", "Pipeline healthy. Maintain your cadence."),
    (100, "strong", "Pipeline strong. Focus on open replies."),
)

# What a strategy scores when it cannot be scored at all -- see
# compute_health_score's contract.
_FAILED_COMPONENTS = {"reply_rate": 0.0, "completion": 0.0,
                      "freshness": 0.0, "conversations": 0.0}


def band_for(score: int) -> tuple[str, str]:
    """(band, message) for a 0-100 score.

    Returns the band name and the sentence the UI shows under the number.
    Never raises: a score outside 0-100 falls through to the top band rather
    than erroring.
    """
    for upper, band, message in BANDS:
        if score <= upper:
            return band, message
    return BANDS[-1][1], BANDS[-1][2]


def _pct(numerator: float, denominator: float) -> float:
    """numerator/denominator as a 0-100 percentage, clamped.

    A zero denominator returns 0.0 -- an empty pipeline scores zero, it does
    not divide by zero. Never raises.
    """
    if not denominator:
        return 0.0
    return max(0.0, min(100.0, (numerator / denominator) * 100.0))


def _freshness(last_lead_at, now: datetime) -> float:
    """100 up to FRESH_DAYS old, 0 from STALE_DAYS, linear between.

    `last_lead_at` of None (no leads at all) is 0.0. Naive timestamps are
    read as UTC, because SQLite stores them without a tzinfo. Never raises.
    """
    if last_lead_at is None:
        return 0.0
    if getattr(last_lead_at, "tzinfo", None) is None:
        last_lead_at = last_lead_at.replace(tzinfo=timezone.utc)
    days = (now - last_lead_at).total_seconds() / 86400.0
    if days <= FRESH_DAYS:
        return 100.0
    if days >= STALE_DAYS:
        return 0.0
    return 100.0 * (STALE_DAYS - days) / (STALE_DAYS - FRESH_DAYS)


def compute_health_score(db: Session, strategy_id, now: datetime | None = None) -> dict:
    """Score one strategy's outbound pipeline from live rows.

    WHAT IT DOES. Reads sends/replies (outcomes), enrollment completion, the
    age of the newest lead and the number of open reply conversations for
    `strategy_id`, scales each to 0-100, and blends them with WEIGHTS.

    WHAT IT RETURNS. {"score": int 0-100, "band": str, "message": str,
    "components": {"reply_rate", "completion", "freshness", "conversations"}
    each a float 0-100, "inputs": {...} the raw counts the components were
    derived from}. On failure the same shape with score=0, band="critical"
    and an extra "error" key.

    WHAT IT NEVER RAISES. Anything. A health score is decoration on top of a
    working product -- a bad query, an unknown strategy id or a database blip
    must never take down the analytics page or abort the six-hourly sweep
    part-way through the other strategies. Every failure degrades to score=0 /
    band="critical", logged at WARNING, and carries the "error" key so a
    caller that cares can tell a genuinely empty pipeline from a failed
    measurement.
    """
    now = now or datetime.now(timezone.utc)
    try:
        if not isinstance(strategy_id, uuid_module.UUID):
            strategy_id = uuid_module.UUID(str(strategy_id))

        # --- reply rate ----------------------------------------------------
        def _outcome_count(event: OutcomeEvent) -> int:
            return db.execute(
                select(func.count(Outcome.id))
                .join(Lead, Lead.id == Outcome.lead_id)
                .where(Lead.strategy_id == strategy_id, Outcome.event == event)
            ).scalar_one() or 0

        sends = _outcome_count(OutcomeEvent.SENT)
        replies = _outcome_count(OutcomeEvent.REPLIED)

        # --- sequence completion -------------------------------------------
        enrolled = db.execute(
            select(func.count(SequenceEnrollment.id))
            .join(Sequence, Sequence.id == SequenceEnrollment.sequence_id)
            .where(Sequence.strategy_id == strategy_id)
        ).scalar_one() or 0
        completed = db.execute(
            select(func.count(SequenceEnrollment.id))
            .join(Sequence, Sequence.id == SequenceEnrollment.sequence_id)
            .where(Sequence.strategy_id == strategy_id,
                   SequenceEnrollment.status == EnrollmentStatus.COMPLETED)
        ).scalar_one() or 0

        # --- lead freshness -------------------------------------------------
        last_lead_at = db.execute(
            select(func.max(Lead.created_at)).where(Lead.strategy_id == strategy_id)
        ).scalar_one_or_none()

        # --- active conversations -------------------------------------------
        # A lead sitting at REPLIED is a conversation somebody still owes an
        # answer to: it has not advanced to meeting_booked and it has not been
        # closed out. That is exactly what "open reply" means on this screen.
        open_replies = db.execute(
            select(func.count(Lead.id))
            .where(Lead.strategy_id == strategy_id, Lead.status == LeadStatus.REPLIED)
        ).scalar_one() or 0

        components = {
            "reply_rate": round(_pct(replies, sends), 2),
            "completion": round(_pct(completed, enrolled), 2),
            "freshness": round(_freshness(last_lead_at, now), 2),
            "conversations": float(min(open_replies * CONVERSATION_POINTS, 100)),
        }
        score = int(round(sum(components[key] * weight
                              for key, weight in WEIGHTS.items())))
        score = max(0, min(100, score))
        band, message = band_for(score)
        return {
            "score": score,
            "band": band,
            "message": message,
            "components": components,
            "inputs": {
                "sends": sends,
                "replies": replies,
                "enrolled": enrolled,
                "completed": completed,
                "open_replies": open_replies,
                "last_lead_at": last_lead_at.isoformat() if last_lead_at else None,
            },
        }
    except Exception as exc:  # noqa: BLE001 -- see the docstring
        logger.warning("pipeline health for strategy %s failed: %s: %s",
                       strategy_id, type(exc).__name__, exc)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001 -- rollback on an already-dead session
            pass
        band, message = band_for(0)
        return {"score": 0, "band": band, "message": message,
                "components": dict(_FAILED_COMPONENTS),
                "inputs": {},
                "error": f"{type(exc).__name__}: {exc}"[:200]}


def persist(db: Session, strategy: Strategy, result: dict,
            now: datetime | None = None) -> Strategy:
    """Write `result` onto the strategy's health cache columns and commit.

    WHAT IT DOES. Copies score/band/message onto the Strategy row and stamps
    health_updated_at. A result carrying an "error" key is NOT written: a
    failed measurement must never overwrite the last good score with a zero
    and tell the founder their pipeline collapsed.

    WHAT IT RETURNS. The same Strategy instance.

    WHAT IT NEVER RAISES. Anything. A commit failure is rolled back and
    logged -- the caller already holds the computed score, and failing to
    cache it is not a reason to fail their request or abort the sweep.
    """
    if result.get("error"):
        return strategy
    try:
        strategy.pipeline_health_score = int(result["score"])
        strategy.health_band = str(result["band"])[:20]
        strategy.health_message = str(result["message"])[:200]
        strategy.health_updated_at = now or datetime.now(timezone.utc)
        db.commit()
    except Exception:  # noqa: BLE001 -- see the docstring
        logger.exception("could not persist pipeline health for strategy %s",
                         getattr(strategy, "id", None))
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
    return strategy

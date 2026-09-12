"""Feature 1 background work: the six-hourly pipeline health refresh.

  refresh_all_pipeline_health   every strategy that has a pipeline to score,
                                recomputed and cached on the strategy row

On the `learning` queue: this is aggregation over outcomes, enrollments and
leads, exactly like the nightly learning-loop jobs, and nothing about it is
time-critical to the minute. GET /strategies/{id}/health recomputes on demand
anyway, so a founder who opens the page between sweeps sees live numbers -- the
sweep exists so lists and dashboards can render a score without running four
aggregates per row.

IDEMPOTENT BY CONSTRUCTION. Each strategy's score is a pure function of rows
that exist when it runs, and the write is a full overwrite of four cache
columns. Running it twice, or retrying it after a crash half-way through,
produces the same end state as running it once.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.db.models import Strategy, StrategyStatus
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# A strategy only has a pipeline worth scoring once it has passed verification
# and may execute. PENDING / RESEARCHING / VERIFYING strategies have no leads,
# no sequences and no outcomes, so scoring them would write "critical" on every
# campaign that is still being built. FAILED and NEEDS_HUMAN_REVIEW are not
# running, and their last real score (if any) is left untouched.
SCORABLE_STATUSES = (StrategyStatus.VERIFIED, StrategyStatus.EXECUTING)


def refresh_all_pipeline_health_impl(session: Session) -> dict:
    """Recompute and cache the health score of every scorable strategy.

    WHAT IT RETURNS. {"scored": n, "failed": n, "total": n} -- "failed" counts
    strategies whose score could not be computed (compute_health_score
    reported an error) and whose cached score was therefore left alone.

    WHAT IT NEVER RAISES. Per-strategy failures. compute_health_score and
    persist both swallow their own errors, and the loop additionally guards
    each iteration so one poisoned row cannot abort the sweep for every
    strategy after it. A failure to even list the strategies does propagate --
    that is a broken database, not a broken strategy, and Celery should see it.
    """
    from app.services import pipeline_health  # noqa: PLC0415

    strategies = session.execute(
        select(Strategy).where(Strategy.status.in_(SCORABLE_STATUSES))
    ).scalars().all()

    scored = failed = 0
    for strategy in strategies:
        try:
            result = pipeline_health.compute_health_score(session, strategy.id)
            if result.get("error"):
                failed += 1
                continue
            pipeline_health.persist(session, strategy, result)
            scored += 1
        except Exception:  # noqa: BLE001 -- one bad row must not end the sweep
            failed += 1
            logger.exception("pipeline health sweep failed for strategy %s", strategy.id)
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
    logger.info("pipeline health sweep: scored=%s failed=%s total=%s",
                scored, failed, len(strategies))
    return {"scored": scored, "failed": failed, "total": len(strategies)}


@celery_app.task(name="app.workers.health_tasks.refresh_all_pipeline_health")
def refresh_all_pipeline_health() -> dict:
    """Celery entry point for the six-hourly sweep. Safe to retry."""
    session = SessionLocal()
    try:
        return refresh_all_pipeline_health_impl(session)
    finally:
        session.close()

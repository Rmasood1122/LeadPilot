"""Feature 5 background work: the nightly ROI snapshot.

  refresh_all_roi_snapshots   01:00 UTC, every campaign that can have results

On the `learning` queue with the other nightly aggregations.

IDEMPOTENT BY CONSTRUCTION. UNIQUE (strategy_id, snapshot_date) means a day
has exactly one row, and upsert_daily_snapshot updates it rather than
appending. A retried or double-scheduled run recomputes the same day from the
same rows and lands on the same numbers -- a day can never be double-counted.

WHY 01:00 UTC. Late enough that the previous day is closed everywhere the
product sells (US -> NZ), early enough to be finished before the 02:00
learning-loop aggregation starts competing for the same worker.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def refresh_all_roi_snapshots_impl(session: Session, snapshot_date=None) -> dict:
    """Snapshot every scorable strategy for one day.

    WHAT IT RETURNS. {"date": iso str, "written": n, "failed": n, "total": n}
    -- "failed" counts strategies whose metrics could not be computed, whose
    existing row for the day was therefore left alone.

    WHAT IT NEVER RAISES. Per-strategy failures; upsert_daily_snapshot
    swallows its own and returns None, and the loop guards each iteration on
    top of that so one poisoned campaign cannot cost every campaign after it
    its snapshot.
    """
    from app.services import roi_calculator  # noqa: PLC0415

    snapshot_date = snapshot_date or datetime.now(timezone.utc).date()
    strategy_ids = roi_calculator.scorable_strategy_ids(session)

    written = failed = 0
    for strategy_id in strategy_ids:
        try:
            snapshot = roi_calculator.upsert_daily_snapshot(session, strategy_id,
                                                            snapshot_date)
            written += 1 if snapshot is not None else 0
            failed += 0 if snapshot is not None else 1
        except Exception:  # noqa: BLE001 -- one bad row must not end the sweep
            failed += 1
            logger.exception("ROI snapshot sweep failed for strategy %s", strategy_id)
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
    logger.info("ROI snapshot sweep %s: written=%s failed=%s total=%s",
                snapshot_date, written, failed, len(strategy_ids))
    return {"date": snapshot_date.isoformat(), "written": written,
            "failed": failed, "total": len(strategy_ids)}


@celery_app.task(name="app.workers.roi_tasks.refresh_all_roi_snapshots")
def refresh_all_roi_snapshots() -> dict:
    """Celery entry point for the 01:00 UTC sweep. Safe to retry."""
    session = SessionLocal()
    try:
        return refresh_all_roi_snapshots_impl(session)
    finally:
        session.close()

"""Feature 4 background work: the twelve-hourly displacement sweep.

  scan_strategy_for_displacement(strategy_id)   one campaign, on demand
  scan_all_strategies                           every executable campaign, 12h

On the `pipeline` queue with the other batched external-API-plus-model work
(intelligence_tasks' lead rescoring and market-signal refresh). A sweep across
every strategy's watch list is exactly that shape of job, and it must not sit
in front of time-sensitive outreach sends or user-facing notifications.

IDEMPOTENT BY CONSTRUCTION. The 14-day per-lead dedup window inside
run_displacement_scan is what makes a retry safe: a sweep that crashed
half-way and is redelivered re-scans the leads it already alerted on and
creates nothing for them. Running it twice in an hour produces the same alerts
as running it once.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.db.models import Strategy, StrategyStatus
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Only campaigns that can actually act on an alert. A strategy still being
# researched has no leads to watch, and a failed one has nobody minding it.
SCANNABLE_STATUSES = (StrategyStatus.VERIFIED, StrategyStatus.EXECUTING)


def scan_strategy_impl(session: Session, strategy_id) -> dict:
    """Scan one strategy's watch list.

    WHAT IT RETURNS. {"strategy_id": str, "alerts_created": int}.

    WHAT IT NEVER RAISES. Anything -- run_displacement_scan swallows its own
    per-lead and per-strategy failures and returns 0.
    """
    from app.services import displacement_monitor  # noqa: PLC0415

    created = displacement_monitor.run_displacement_scan(session, strategy_id)
    return {"strategy_id": str(strategy_id), "alerts_created": created}


def scan_all_strategies_impl(session: Session) -> dict:
    """Scan every scannable strategy.

    WHAT IT RETURNS. {"strategies": n, "alerts_created": n, "failed": n}.

    WHAT IT NEVER RAISES. Per-strategy failures. A failure to LIST the
    strategies propagates -- that is a broken database, not a broken campaign,
    and Celery should record it.
    """
    strategy_ids = session.execute(
        select(Strategy.id).where(Strategy.status.in_(SCANNABLE_STATUSES))
    ).scalars().all()

    created = failed = 0
    for strategy_id in strategy_ids:
        try:
            created += scan_strategy_impl(session, strategy_id)["alerts_created"]
        except Exception:  # noqa: BLE001 -- one bad campaign must not end the sweep
            failed += 1
            logger.exception("displacement sweep failed for strategy %s", strategy_id)
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
    logger.info("displacement sweep: strategies=%s alerts=%s failed=%s",
                len(strategy_ids), created, failed)
    return {"strategies": len(strategy_ids), "alerts_created": created,
            "failed": failed}


@celery_app.task(name="app.workers.displacement_tasks.scan_strategy_for_displacement")
def scan_strategy_for_displacement(strategy_id: str) -> dict:
    """Celery entry point for one campaign. Safe to retry."""
    session = SessionLocal()
    try:
        return scan_strategy_impl(session, strategy_id)
    finally:
        session.close()


@celery_app.task(name="app.workers.displacement_tasks.scan_all_strategies")
def scan_all_strategies() -> dict:
    """Celery entry point for the twelve-hourly sweep. Safe to retry."""
    session = SessionLocal()
    try:
        return scan_all_strategies_impl(session)
    finally:
        session.close()


def enqueue_strategy_scan(strategy_id) -> bool:
    """Publish a one-campaign scan. Never raises; False when the broker refused."""
    try:
        scan_strategy_for_displacement.apply_async(args=[str(strategy_id)], retry=False)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("displacement: could not enqueue strategy %s", strategy_id)
        return False

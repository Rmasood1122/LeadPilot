"""Feature Group 1 Celery tasks.

  check_idle_campaigns   daily Beat sweep: mutate campaigns with N idle days
                         and zero replies (learning queue -- it is the
                         learning loop reacting to outcomes)
  rescore_strategy       re-run lead scoring for a whole strategy on request
                         (pipeline queue -- batched model calls over many
                         leads, the same shape of work as sourcing)
  refresh_market_signals re-fetch live signals on request (pipeline queue)
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import Lead, Strategy
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.intelligence_tasks.check_idle_campaigns")
def check_idle_campaigns() -> dict:
    from app.services import strategy_mutation  # noqa: PLC0415

    session = SessionLocal()
    try:
        return strategy_mutation.run_idle_sweep(session)
    finally:
        session.close()


def rescore_strategy_impl(session, strategy_id: uuid.UUID) -> int:
    from app.services import lead_scoring  # noqa: PLC0415

    strategy = session.get(Strategy, strategy_id)
    if strategy is None:
        return 0
    leads = session.execute(
        select(Lead).where(Lead.strategy_id == strategy_id,
                           Lead.status.in_(lead_scoring.SCORABLE))
    ).scalars().all()
    return lead_scoring.score_leads(session, strategy, list(leads))


@celery_app.task(name="app.workers.intelligence_tasks.rescore_strategy",
                 bind=True, max_retries=2)
def rescore_strategy(self, strategy_id: str) -> int:
    session = SessionLocal()
    try:
        return rescore_strategy_impl(session, uuid.UUID(strategy_id))
    except Exception as exc:
        session.rollback()
        raise self.retry(exc=exc, countdown=60)
    finally:
        session.close()


@celery_app.task(name="app.workers.intelligence_tasks.refresh_market_signals")
def refresh_market_signals(strategy_id: str) -> int:
    from app.services import market_intel  # noqa: PLC0415

    session = SessionLocal()
    try:
        strategy = session.get(Strategy, uuid.UUID(strategy_id))
        if strategy is None:
            return 0
        payload = market_intel.ensure_signals(session, strategy, force=True) or {}
        return len(payload.get("signals") or [])
    finally:
        session.close()


def enqueue(task, *args) -> bool:
    """Publish, never raise. Tests monkeypatch this."""
    try:
        task.apply_async(args=list(args), retry=False)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not queue %s: %s", task.name, exc)
        return False

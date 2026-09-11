"""Feature Group 3 background work: send-time windows and reply sentiment.

All on the `learning` queue -- both are the learning loop reacting to
outcomes, and neither is time-critical to the minute.

  compute_send_windows(strategy_id)  one campaign, the moment it crosses the
                                     open threshold (open_tracking.py)
  refresh_send_windows               nightly: every campaign past the
                                     threshold, so windows follow the data
  aggregate_reply_sentiment          weekly (Monday): the last complete
                                     week's classifications + spike alerts
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.db.models import Lead, Outcome, OutcomeEvent, Strategy
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def compute_send_windows_impl(session: Session, strategy_id) -> dict:
    from app.services import send_windows  # noqa: PLC0415

    strategy = session.get(Strategy, uuid.UUID(str(strategy_id)))
    if strategy is None:
        return {"status": "not_found"}
    result = send_windows.compute(session, strategy)
    if result.get("windows") and strategy.smart_send_time:
        result["rescheduled"] = send_windows.reslot_scheduled(session, strategy)
    return result


def refresh_send_windows_impl(session: Session) -> dict:
    from app.services import system_settings  # noqa: PLC0415

    needed = system_settings.get(session, "send_time_min_opens")
    ids = session.execute(
        select(Lead.strategy_id)
        .join(Outcome, Outcome.lead_id == Lead.id)
        .where(Outcome.event == OutcomeEvent.OPENED)
        .group_by(Lead.strategy_id)
        .having(func.count(Outcome.id) >= needed)
    ).scalars().all()
    done = failed = 0
    for strategy_id in ids:
        try:
            compute_send_windows_impl(session, strategy_id)
            done += 1
        except Exception:
            session.rollback()
            failed += 1
            logger.exception("send windows: refresh failed for strategy %s", strategy_id)
    return {"computed": done, "failed": failed}


@celery_app.task(name="app.workers.analytics_tasks.compute_send_windows")
def compute_send_windows(strategy_id: str) -> dict:
    session = SessionLocal()
    try:
        return compute_send_windows_impl(session, strategy_id)
    finally:
        session.close()


@celery_app.task(name="app.workers.analytics_tasks.refresh_send_windows")
def refresh_send_windows() -> dict:
    session = SessionLocal()
    try:
        return refresh_send_windows_impl(session)
    finally:
        session.close()


@celery_app.task(name="app.workers.analytics_tasks.aggregate_reply_sentiment")
def aggregate_reply_sentiment() -> dict:
    from app.services import reply_sentiment  # noqa: PLC0415

    session = SessionLocal()
    try:
        return reply_sentiment.aggregate_and_alert(session, datetime.now(timezone.utc))
    finally:
        session.close()


def enqueue_send_windows(strategy_id) -> bool:
    """Publish point tests patch (tests/conftest.py::queued_jobs)."""
    try:
        compute_send_windows.apply_async(args=[str(strategy_id)], retry=False)
        return True
    except Exception:
        logger.exception("send windows: could not enqueue strategy %s", strategy_id)
        return False

"""F07 Spend Guard: the 15-minute alert sweep.

Alerts also fire after every refused run and every lead-batch stage; the sweep
catches spend that arrives any other way (a pipeline step, a send, a meeting
brief). Idempotent by construction: a threshold that already fired this month
cannot fire again (UNIQUE user_id, period, threshold). A no-op while the flag
is off. Routed to `default`: it reads a few sums per capped account and sends
at most one transactional email per newly crossed threshold.
"""

from __future__ import annotations

import logging

from app.db.base import SessionLocal
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.spend_guard_tasks.sweep_spend_alerts")
def sweep_spend_alerts() -> int:
    from app.services import spend_guard  # noqa: PLC0415

    session = SessionLocal()
    try:
        fired = spend_guard.sweep_alerts(session)
        if fired:
            logger.info("spend guard: %d alert(s) fired", fired)
        return fired
    finally:
        session.close()

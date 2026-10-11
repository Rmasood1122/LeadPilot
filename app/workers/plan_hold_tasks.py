"""Plan-hold release sweep (Celery beat, every 15 minutes).

A message held at send time because the owner's plan no longer covered it
(app/services/plan_holds.py, error prefix 'plan_limit: ') goes back to
SCHEDULED as soon as the owner's CURRENT plan covers it again -- so an upgrade
unfreezes the campaign without any hook in billing code.

QUEUE `default`: short database work, and a held campaign is waiting on it.

NOTHING HERE SENDS. A release returns messages to SCHEDULED and the ordinary
dispatcher sends them through every gate, the plan check included.
"""

from __future__ import annotations

import logging

from app.db.base import SessionLocal
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="leadpilot.plan_holds.release")
def release_plan_holds() -> dict:
    from app.services import plan_holds  # noqa: PLC0415

    session = SessionLocal()
    try:
        return plan_holds.release_sweep(session)
    finally:
        session.close()

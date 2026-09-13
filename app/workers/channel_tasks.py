"""Feature A4 background work: the hourly channel-stagnation step.

  detect_channel_stagnation   hourly at :25

On `outreach`: with auto-switch on, it changes which channel a scheduled send
goes out on, so it runs beside the dispatcher and send tasks it affects.
"""

import logging

from app.db.base import SessionLocal
from app.pipeline import channel_orchestrator
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.channel_tasks.detect_channel_stagnation")
def detect_channel_stagnation() -> dict:
    session = SessionLocal()
    try:
        ranking = None
        try:  # Feature A5's outcome-based channel ranking, when present.
            from app.services import send_time_optimizer  # noqa: PLC0415

            ranking = getattr(send_time_optimizer, "channel_ranking_for_lead", None)
        except Exception:  # noqa: BLE001
            ranking = None
        return channel_orchestrator.detect_stagnation(session, ranking_for=ranking)
    finally:
        session.close()

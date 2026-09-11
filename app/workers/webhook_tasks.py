"""Celery task for outbound webhook delivery (Feature Group 4 rebuild).

The delivery logic -- signing, the SSRF check, retries, 410 handling -- lives
in app/services/webhook_delivery.py::deliver, which is what the tests drive.
This module is only the queue boundary. Retries re-enqueue with a countdown
(max_retries=0 on the task: Celery's own retry would double-count attempts).

The previous version queried with raw SQL against columns that do not exist
and imported NotificationService / task_error from paths that do not exist;
see the webhook_delivery module docstring.
"""

from __future__ import annotations

import logging
import uuid

from app.db.base import SessionLocal
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.webhook_tasks.deliver_webhook", bind=True,
                 max_retries=0, acks_late=True)
def deliver_webhook(self, delivery_id: str) -> dict:
    from app.services import webhook_delivery  # noqa: PLC0415

    session = SessionLocal()
    try:
        return {"status": webhook_delivery.deliver(session, uuid.UUID(delivery_id))}
    finally:
        session.close()


def enqueue_delivery(delivery_id, countdown: int = 0) -> bool:
    """Publish point tests patch (tests/conftest.py::queued_jobs)."""
    try:
        deliver_webhook.apply_async(args=[str(delivery_id)], countdown=countdown, retry=False)
        return True
    except Exception:
        logger.exception("webhook: could not enqueue delivery %s", delivery_id)
        return False

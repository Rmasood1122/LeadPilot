"""Section E background work: charge pay-per-meeting usage; auto-renewal
notices.

  charge_due_meetings    every 30 minutes
  send_renewal_notices   daily at 15:10 UTC (docs/features/annual-billing.md):
                         annual acknowledgment, trial-ending and 30-day
                         renewal notices to the account owner, each claimed
                         against UNIQUE (subscription, kind, period) before
                         it is sent, so re-runs never send twice

On the `default` queue: one outbound Stripe call per due meeting, integration
I/O like CRM sync and webhook delivery, never time-critical to the minute.

Importing app.services.billing here is also what registers the booked-meeting
metering listener inside the WORKER process -- the native calendar's booking
task writes BOOKED outcomes there, not in the API.

SAFE TO RETRY. A meeting leaves `pending` in the same commit that records its
charge, and every Stripe call carries an idempotency key derived from the
meeting id, so a crashed or double-scheduled sweep cannot invoice twice.
"""

import logging

from app.db.base import SessionLocal
from app.services import billing
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

billing.install()


@celery_app.task(name="app.workers.billing_tasks.charge_due_meetings")
def charge_due_meetings() -> dict:
    session = SessionLocal()
    try:
        result = billing.charge_due_meetings(session)
        logger.info("pay-per-meeting sweep: %s", result)
        return result
    finally:
        session.close()


@celery_app.task(name="app.workers.billing_tasks.send_renewal_notices")
def send_renewal_notices() -> dict:
    session = SessionLocal()
    try:
        result = billing.send_renewal_notices(session)
        logger.info("renewal notices sweep: %s", result)
        return result
    finally:
        session.close()

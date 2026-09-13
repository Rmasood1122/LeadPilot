"""Feature A2 background work: seal the activity audit trail.

  seal_audit_trails   every 5 minutes

Recording happens inside the business transaction; sealing (assigning each
record its place in the account's hash chain) happens here, serialised per
account, so a send never waits on -- or races for -- a sequence number.
Exports and verification also seal on demand, so a report is never stale by
more than the moment it was requested.

Importing app.services.audit_trail here registers the recording listener
inside the WORKER process, where most Outcomes (sends, replies, bookings) are
written.

On `default`: short database work, never time-critical to the minute.
"""

import logging

from app.db.base import SessionLocal
from app.services import audit_trail
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

audit_trail.install()


@celery_app.task(name="app.workers.audit_tasks.seal_audit_trails")
def seal_audit_trails() -> dict:
    session = SessionLocal()
    try:
        return audit_trail.seal_all(session)
    finally:
        session.close()

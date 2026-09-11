"""Feature Group 9: the daily sending-domain health + blacklist sweep.

On the `default` queue -- outbound DNS/API lookups for one user at a time,
like the other integration checks. Beat runs it once a day; the check is also
available on demand (POST /deliverability/check).
"""

from __future__ import annotations

from app.db.base import SessionLocal
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.deliverability_tasks.run_daily_checks")
def run_daily_checks() -> dict:
    from app.services import deliverability  # noqa: PLC0415

    session = SessionLocal()
    try:
        return deliverability.run_all(session)
    finally:
        session.close()

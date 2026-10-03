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


@celery_app.task(name="app.workers.deliverability_tasks.refresh_mailbox_health")
def refresh_mailbox_health() -> dict:
    """Part 1 Feature 4: the per-mailbox health sweep.

    Runs every few hours rather than daily, because the two signals it exists
    to catch -- a complaint spike and a volume spike -- do their damage inside
    a day. The DOMAIN sweep above stays daily: DNS records and blocklist
    entries do not change between breakfast and lunch.
    """
    from app.services import mailbox_health  # noqa: PLC0415

    session = SessionLocal()
    try:
        return mailbox_health.refresh_all(session)
    finally:
        session.close()

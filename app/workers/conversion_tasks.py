"""Feature A5 background work: rescore live leads' conversion probability.

  rescore_conversion_probability   hourly at :40

The send task already gates every send on a fresh estimate; this sweep
catches the leads whose NEXT send is days away, so a lead that went cold on
Monday is tagged "cooling" in the CRM on Monday rather than on the morning of
its next scheduled touch. On `learning`: aggregation over outcomes, like the
other scoring sweeps.
"""

import logging

from app.db.base import SessionLocal
from app.services import conversion_probability
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.conversion_tasks.rescore_conversion_probability")
def rescore_conversion_probability() -> dict:
    session = SessionLocal()
    try:
        return conversion_probability.rescore_active_leads(session)
    finally:
        session.close()

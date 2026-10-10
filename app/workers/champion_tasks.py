"""F10 Champion Tracker sweeps (Celery beat).

  reverify_held  every 15 minutes: leads whose messages the staleness hold
                 parked get their role re-verified (or are released when no
                 longer stale; with the flag off every hold is released).
  refresh        daily: past positive repliers and customers whose role data
                 is stale are re-verified, oldest first, budget-capped.

QUEUE `default`, not `pipeline`: a held message waits on the first sweep, and
`pipeline` runs 144-step strategy builds at concurrency 2.

NOTHING HERE SENDS. A release returns messages to SCHEDULED and the ordinary
dispatcher sends them through every gate. See app/services/champion_tracker.py.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.db.base import SessionLocal
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_source():
    """The configured LeadSource (Apollo). Tests monkeypatch this."""
    import app.integrations.apollo  # noqa: F401,PLC0415 -- registers the adapter
    from app.integrations.base import get_lead_source  # noqa: PLC0415

    return get_lead_source(settings.lead_source_provider)


def _get_verifier():
    """The configured EmailVerifier (Hunter). Tests monkeypatch this."""
    import app.integrations.hunter  # noqa: F401,PLC0415 -- registers the adapter
    from app.integrations.base import get_email_verifier  # noqa: PLC0415

    return get_email_verifier(settings.email_verifier_provider)


@celery_app.task(name="leadpilot.champion.reverify_held")
def reverify_held() -> dict:
    from app.services import champion_tracker  # noqa: PLC0415

    session = SessionLocal()
    try:
        counts = champion_tracker.run_held(session, _get_source(), _get_verifier())
        logger.info("champion tracker held sweep: %s", counts)
        return counts
    finally:
        session.close()


@celery_app.task(name="leadpilot.champion.refresh")
def refresh() -> dict:
    from app.services import champion_tracker  # noqa: PLC0415

    session = SessionLocal()
    try:
        counts = champion_tracker.run_refresh(session, _get_source(), _get_verifier())
        logger.info("champion tracker refresh: %s", counts)
        return counts
    finally:
        session.close()

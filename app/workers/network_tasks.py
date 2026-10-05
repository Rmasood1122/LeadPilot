"""Weekly refresh of the private LinkedIn network scores (Growth plan and up).

Re-scores connections that are ALREADY stored against each account's own
products. It calls no model and no external service. It cannot fetch new
connections: LinkedIn has no API for that, so new people only arrive when the
member uploads a fresh export.
"""

from __future__ import annotations

import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

__all__ = ["weekly_refresh"]


@celery_app.task(name="leadpilot.network.weekly_refresh")
def weekly_refresh() -> dict:
    from app.db.base import SessionLocal
    from app.services import linkedin_network

    with SessionLocal() as session:
        result = linkedin_network.refresh_all(session)
    logger.info("linkedin network weekly refresh: %s", result)
    return result

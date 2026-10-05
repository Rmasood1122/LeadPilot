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

__all__ = ["weekly_refresh", "send_queued"]


@celery_app.task(name="leadpilot.network.weekly_refresh")
def weekly_refresh() -> dict:
    from app.db.base import SessionLocal
    from app.services import linkedin_network

    with SessionLocal() as session:
        result = linkedin_network.refresh_all(session)
    logger.info("linkedin network weekly refresh: %s", result)
    return result


@celery_app.task(name="leadpilot.network.send_queued")
def send_queued(message_id: str) -> dict:
    """Send one queued network message. Every rule is re-checked here, not
    trusted from when the user clicked: the plan, the saved text, suppression,
    the daily cap and the 1st-degree check all run again."""
    import uuid  # noqa: PLC0415

    from app.db.base import SessionLocal  # noqa: PLC0415
    from app.db.models import LinkedInNetworkMessage, User  # noqa: PLC0415
    from app.services import network_messages as nm  # noqa: PLC0415

    with SessionLocal() as session:
        msg = session.get(LinkedInNetworkMessage, uuid.UUID(str(message_id)))
        if msg is None or msg.status != "queued":
            return {"status": "skipped"}
        user = session.get(User, msg.user_id)
        try:
            nm.deliver(session, user, msg, "bulk")
        except nm.MessageError as exc:
            session.refresh(msg)
            if exc.status == 429:               # cap hit: hand it back, not lost
                msg.status, msg.error = "approved", exc.detail
            elif msg.status == "queued":
                msg.status, msg.error = "failed", exc.detail[:300]
            session.commit()
            return {"status": msg.status, "error": exc.detail}
        return {"status": msg.status}

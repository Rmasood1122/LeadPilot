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

__all__ = ["weekly_refresh", "send_queued", "enqueue_send"]


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
        # Daily send approval (SAFETY GUARD): a bulk send is AUTOMATIC LinkedIn
        # sending through the customer's account, so it waits for today's
        # LinkedIn approval (with its restriction-risk acknowledgement). Held
        # = stays "queued", tagged; approving LinkedIn queues it again. A
        # lookup error fails CLOSED: held, and re-checked in an hour.
        held = _approval_hold(session, msg)
        if held is not None:
            return held
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


def _approval_hold(session, msg) -> dict | None:
    """None = send now. Otherwise the message is left queued and tagged."""
    from datetime import datetime, timezone  # noqa: PLC0415

    from app.db.models import LinkedInNetworkMessage  # noqa: PLC0415
    from app.services import daily_send_approval as dsa  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    message_id = msg.id
    try:
        hold = dsa.network_hold(session, msg.user_id, now)
        if hold is not None:
            msg.error = hold.error[:300]
            session.flush()
            if not dsa.confirm_hold(session, hold, "linkedin", now):
                session.rollback()       # approved meanwhile: drop the tag, send
                return None
    except Exception:  # noqa: BLE001 -- fails closed
        logger.exception("daily send approval check failed for network message %s -- held",
                         message_id)
        session.rollback()
        row = session.get(LinkedInNetworkMessage, message_id)
        row.error = f"{dsa.ERROR_PREFIX}approval could not be checked -- held (fails closed)"
        session.commit()
        enqueue_send(message_id, countdown=int(dsa.UNAVAILABLE_RETRY.total_seconds()))
        return {"status": "held", "result": dsa.SEND_RESULT_UNAVAILABLE}
    if hold is None:
        return None
    session.commit()
    dsa.notify_if_needed(session, hold, now)
    return {"status": "held", "result": hold.result}


def enqueue_send(message_id, countdown: int = 0) -> bool:
    """Publish send_queued. Never raises: False when the broker refused (the
    caller keeps the message tagged so a later approval queues it again)."""
    try:
        send_queued.apply_async(args=[str(message_id)], countdown=countdown, retry=False)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not queue network message %s: %s", message_id, exc)
        return False

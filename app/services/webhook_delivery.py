"""
Reliable outbound webhook delivery.

Enterprise users can register target URLs to receive events from ClientHunter
(strategy_complete, meeting_booked, lead_replied, campaign_paused, variant_promoted).
This is the "connect ClientHunter to your CRM" integration path.

Delivery model:
  - Enqueue on event fire → Celery task deliver_webhook(delivery_id)
  - HTTP POST with HMAC-SHA256 signature header and delivery_id in payload
  - Exponential backoff: [30s, 2m, 10m, 30m, 2h] (5 attempts)
  - On exhaustion: task_errors write + admin FCM notification
  - Idempotent: delivery_id in payload for receiver-side dedup

Secrets: target.secret encrypted via TokenStore (Fernet); never logged.
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import uuid
from typing import Optional

from app.core.logging import get_logger

logger = get_logger("services.webhook_delivery")

EVENT_TYPES = frozenset({
    "strategy_complete",
    "meeting_booked",
    "lead_replied",
    "campaign_paused",
    "variant_promoted",
})

RETRY_DELAYS_SECONDS = [30, 120, 600, 1800, 7200]


def _sign_payload(secret: str, payload_bytes: bytes) -> str:
    """HMAC-SHA256 signature: X-ClientHunter-Signature: sha256=<hex>"""
    sig = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def create_delivery(
    db_session,
    target_id: str,
    event_type: str,
    payload: dict,
) -> Optional[str]:
    """
    Create a WebhookDelivery row and enqueue the delivery task.
    Returns the delivery_id or None on failure.
    """
    if event_type not in EVENT_TYPES:
        logger.warning("webhook_delivery.unknown_event_type", event_type=event_type)
        return None

    delivery_id = str(uuid.uuid4())
    now = datetime.datetime.utcnow()

    try:
        from sqlalchemy import text
        db_session.execute(text("""
            INSERT INTO webhook_deliveries
                (id, target_id, event_type, payload_json, status,
                 max_retries, attempts, created_at, next_attempt_at)
            VALUES
                (:id, :target_id, :event_type, :payload, 'pending',
                 5, 0, :now, :now)
        """), {
            "id": delivery_id,
            "target_id": target_id,
            "event_type": event_type,
            "payload": json.dumps({**payload, "delivery_id": delivery_id}),
            "now": now,
        })
        db_session.commit()
    except Exception as e:
        logger.error("webhook_delivery.create_failed", error=str(e))
        return None

    # Enqueue Celery task
    try:
        from app.workers.webhook_tasks import deliver_webhook
        deliver_webhook.delay(delivery_id)
    except Exception as e:
        logger.error("webhook_delivery.enqueue_failed", delivery_id=delivery_id, error=str(e))

    return delivery_id


def fire_event(
    db_session,
    user_id: str,
    event_type: str,
    payload: dict,
) -> list[str]:
    """
    Fire an event to all matching registered webhook targets for user_id.
    Returns list of delivery_ids created.
    """
    from sqlalchemy import text
    try:
        targets = db_session.execute(text("""
            SELECT id, url, secret_encrypted, event_types
            FROM webhook_targets
            WHERE user_id = :uid
              AND :event = ANY(event_types)
              AND active = true
        """), {"uid": user_id, "event": event_type}).mappings().all()
    except Exception as e:
        logger.error("webhook_delivery.targets_query_failed", error=str(e))
        return []

    delivery_ids = []
    for target in targets:
        did = create_delivery(db_session, str(target["id"]), event_type, payload)
        if did:
            delivery_ids.append(did)

    if delivery_ids:
        logger.info(
            "webhook_delivery.fired",
            event_type=event_type,
            user_id=user_id,
            deliveries=len(delivery_ids),
        )
    return delivery_ids


def mark_delivered(db_session, delivery_id: str, response_code: int) -> None:
    from sqlalchemy import text
    db_session.execute(text("""
        UPDATE webhook_deliveries
        SET status = 'delivered',
            last_attempt_at = NOW(),
            last_response_code = :code,
            attempts = attempts + 1
        WHERE id = :id
    """), {"code": response_code, "id": delivery_id})
    db_session.commit()


def mark_failed_attempt(
    db_session,
    delivery_id: str,
    response_code: Optional[int],
    error: str,
    attempt: int,
) -> bool:
    """
    Record a failed attempt and schedule the next retry.
    Returns True if more retries remain, False if exhausted.
    """
    from sqlalchemy import text
    import datetime

    # `attempt` is the number of attempts ALREADY made when this one was
    # dispatched (webhook_tasks reads it straight from webhook_deliveries
    # .attempts), so this failure is attempt number `attempt + 1`. With five
    # delays the budget is five attempts, and `attempt >= len(...)` spent a
    # sixth: at attempt=4 it returned "retries remain", scheduled another run
    # reusing the last 2h delay, and only marked the row exhausted on the way
    # back. Both this module's docstring and webhook_tasks' say 5 attempts.
    exhausted = attempt + 1 >= len(RETRY_DELAYS_SECONDS)
    next_delay = RETRY_DELAYS_SECONDS[min(attempt, len(RETRY_DELAYS_SECONDS) - 1)]
    next_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=next_delay)
    new_status = "exhausted" if exhausted else "pending"

    db_session.execute(text("""
        UPDATE webhook_deliveries
        SET status = :status,
            attempts = :attempts,
            last_attempt_at = NOW(),
            next_attempt_at = :next_at,
            last_response_code = :code,
            last_error = :error
        WHERE id = :id
    """), {
        "status": new_status,
        "attempts": attempt + 1,
        "next_at": next_at if not exhausted else None,
        "code": response_code,
        "error": error[:1000],
        "id": delivery_id,
    })
    db_session.commit()
    return not exhausted


def get_deliveries(
    db_session,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    from sqlalchemy import text
    where = "WHERE status = :status" if status else ""
    params = {"limit": limit}
    if status:
        params["status"] = status

    try:
        rows = db_session.execute(text(f"""
            SELECT wd.id, wd.event_type, wd.status, wd.attempts,
                   wd.last_response_code, wd.last_error,
                   wd.created_at, wd.last_attempt_at, wd.next_attempt_at,
                   wt.url AS target_url
            FROM webhook_deliveries wd
            JOIN webhook_targets wt ON wt.id = wd.target_id
            {where}
            ORDER BY wd.created_at DESC
            LIMIT :limit
        """), params).mappings().all()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error("webhook_delivery.list_failed", error=str(e))
        return []

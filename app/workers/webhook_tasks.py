"""
Celery tasks for reliable outbound webhook delivery.

Task: deliver_webhook(delivery_id)
  - Reads delivery row + decrypts target secret
  - HTTP POST to target_url (timeout=10s)
  - On success: mark delivered
  - On failure: record attempt, schedule retry via apply_async(countdown=N)
  - On exhaustion (5 attempts): write task_error, send admin FCM
"""
from __future__ import annotations

import json

from app.workers.celery_app import celery_app
from app.core.logging import get_logger, bind_celery_task_context

logger = get_logger("workers.webhook_tasks")

SEND_TIMEOUT_SECONDS = 10


@celery_app.task(
    name="app.workers.webhook_tasks.deliver_webhook",
    bind=True,
    max_retries=0,   # we manage retries manually via apply_async
    acks_late=True,
)
def deliver_webhook(self, delivery_id: str) -> dict:
    """
    Attempt to deliver a single webhook. Schedules its own retry on failure.
    """
    bind_celery_task_context(
        task_id=self.request.id,
        task_name="deliver_webhook",
    )

    from app.core.database import SessionLocal
    from app.services.webhook_delivery import (
        mark_delivered,
        mark_failed_attempt,
        RETRY_DELAYS_SECONDS,
    )
    from app.integrations.token_store import TokenStore

    db = SessionLocal()
    try:
        from sqlalchemy import text
        row = db.execute(text("""
            SELECT wd.id, wd.target_id, wd.payload_json, wd.attempts,
                   wt.url AS target_url, wt.secret_encrypted, wt.user_id
            FROM webhook_deliveries wd
            JOIN webhook_targets wt ON wt.id = wd.target_id
            WHERE wd.id = :id AND wd.status IN ('pending')
        """), {"id": delivery_id}).mappings().first()

        if not row:
            logger.info("webhook_task.delivery_not_found_or_done", delivery_id=delivery_id)
            return {"status": "skipped"}

        target_url = row["target_url"]
        payload_json = row["payload_json"]
        attempt = row["attempts"]

        # Decrypt the webhook secret for signing
        secret = ""
        try:
            from app.core.crypto import decrypt
            secret = decrypt(row["secret_encrypted"]) if row["secret_encrypted"] else ""
        except Exception:
            pass  # send without signature if secret unreadable; log only

        # Build signed payload
        payload_bytes = payload_json.encode() if isinstance(payload_json, str) else json.dumps(payload_json).encode()

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ClientHunter-Enterprise/1.0",
        }
        if secret:
            from services.webhook_delivery import _sign_payload
            headers["X-ClientHunter-Signature"] = _sign_payload(secret, payload_bytes)

        # HTTP delivery
        import httpx
        try:
            response = httpx.post(
                target_url,
                content=payload_bytes,
                headers=headers,
                timeout=SEND_TIMEOUT_SECONDS,
                follow_redirects=True,
            )
            response.raise_for_status()

            mark_delivered(db, delivery_id, response.status_code)
            logger.info(
                "webhook_task.delivered",
                delivery_id=delivery_id,
                target_url=target_url,
                status_code=response.status_code,
            )
            return {"status": "delivered", "code": response.status_code}

        except httpx.HTTPStatusError as e:
            return _handle_failure(
                db, delivery_id, attempt, target_url,
                error=str(e), response_code=e.response.status_code,
            )
        except Exception as e:
            return _handle_failure(
                db, delivery_id, attempt, target_url,
                error=str(e), response_code=None,
            )

    finally:
        db.close()


def _handle_failure(
    db,
    delivery_id: str,
    attempt: int,
    target_url: str,
    error: str,
    response_code,
) -> dict:
    """Record failure, schedule retry or notify on exhaustion."""
    from app.services.webhook_delivery import mark_failed_attempt, RETRY_DELAYS_SECONDS

    has_more_retries = mark_failed_attempt(db, delivery_id, response_code, error, attempt)

    if has_more_retries:
        delay = RETRY_DELAYS_SECONDS[min(attempt, len(RETRY_DELAYS_SECONDS) - 1)]
        deliver_webhook.apply_async(args=[delivery_id], countdown=delay)
        logger.warning(
            "webhook_task.retry_scheduled",
            delivery_id=delivery_id,
            attempt=attempt + 1,
            retry_in_seconds=delay,
            error=error,
        )
        return {"status": "retry_scheduled", "next_attempt_in": delay}
    else:
        # All retries exhausted
        logger.error(
            "webhook_task.exhausted",
            delivery_id=delivery_id,
            target_url=target_url,
            attempts=attempt + 1,
            error=error,
        )
        _notify_exhaustion(delivery_id, target_url, error)
        return {"status": "exhausted"}


def _notify_exhaustion(delivery_id: str, target_url: str, error: str) -> None:
    """Write to task_errors and send admin FCM — best effort."""
    import threading
    import datetime

    def _run():
        try:
            from app.core.database import SessionLocal
            from app.models.task_error import TaskError
            db = SessionLocal()
            try:
                db.add(TaskError(
                    task_name="deliver_webhook",
                    task_id=delivery_id,
                    args_summary=f"target_url={target_url[:100]}",
                    error_type="WebhookExhausted",
                    error_message=error[:2000],
                    traceback="",
                    ts=datetime.datetime.utcnow(),
                ))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning("webhook_task.error_write_failed", error=str(e))

        try:
            import asyncio
            from app.services.notification_service import NotificationService
            asyncio.run(NotificationService.send_to_admins(
                title="Webhook Delivery Failed",
                body=f"Delivery {delivery_id[:8]}… to {target_url[:50]} exhausted all retries.",
                data={"event": "webhook_exhausted", "delivery_id": delivery_id},
            ))
        except Exception as e:
            logger.warning("webhook_task.fcm_notify_failed", error=str(e))

    threading.Thread(target=_run, daemon=True).start()

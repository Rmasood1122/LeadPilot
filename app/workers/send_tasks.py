"""
Send task scheduler — M3 base extended with M8-C4 improvements.

Changes from M3:
  1. Before scheduling a sequence step, call get_send_time_recommendation().
     If confidence is high/medium and a recommended slot is available within
     48 hours, prefer that slot over flat "next business hour" scheduling.
     If confidence is low/no_data → fall through to existing M3 logic.
     NEVER delay a send more than 48 hours.

  2. After sending, call score_message() and write personalization_score
     to messages.personalization_score.

M3 compliance rules (suppression check, send cap, bounce-rate pause) are
unchanged and still enforced before every send.
"""
from __future__ import annotations

import datetime
import json
from typing import Optional

from app.workers.celery_app import celery_app
from app.core.logging import get_logger, bind_celery_task_context

logger = get_logger("workers.send_tasks")


@celery_app.task(
    name="app.workers.send_tasks.send_sequence_step",
    bind=True,
    max_retries=3,
    acks_late=True,
    default_retry_delay=60,
)
def send_sequence_step(self, message_id: int) -> dict:
    """
    Send a single sequence step message.
    Called by the scheduler; should NOT be called directly for new sends —
    use schedule_sequence_step() which handles send-time optimization.
    """
    bind_celery_task_context(task_id=self.request.id, task_name="send_sequence_step")

    from app.core.database import SessionLocal
    from app.core.exceptions import ComplianceError
    from sqlalchemy import text

    db = SessionLocal()
    try:
        msg = db.execute(text("""
            SELECT m.*, l.email, l.phone, l.enrichment_json,
                   l.status AS lead_status,
                   seq.strategy_id, seq.channel
            FROM messages m
            JOIN sequences seq ON seq.id = m.sequence_id
            JOIN leads l ON l.id = seq.lead_id
            WHERE m.id = :mid AND m.sent_at IS NULL
        """), {"mid": message_id}).mappings().first()

        if not msg:
            logger.info("send_task.message_not_found_or_sent", message_id=message_id)
            return {"status": "skipped"}

        # M3 Compliance: suppression check at send time
        from app.services.suppression_service import is_suppressed
        if is_suppressed(db, email=msg["email"], phone=msg.get("phone")):
            logger.warning("send_task.suppressed_at_send", message_id=message_id)
            _mark_suppressed(db, message_id)
            return {"status": "suppressed"}

        # Render body
        body = msg["body"] or ""
        subject = msg.get("subject") or ""

        # Personalization score (lightweight — before send)
        try:
            from app.services.personalization_scorer import score_message, write_personalization_score
            enrichment = msg.get("enrichment_json")
            if isinstance(enrichment, str):
                enrichment = json.loads(enrichment)
            ps = score_message(body, enrichment, message_id=message_id)
            write_personalization_score(message_id, ps.raw_score, db)
        except Exception as e:
            logger.warning("send_task.personalization_score_failed", message_id=message_id, error=str(e))

        # Channel dispatch
        channel = msg.get("channel") or "gmail"
        try:
            if channel == "gmail":
                _send_gmail(db, msg, subject, body)
            elif channel == "whatsapp":
                _send_whatsapp(db, msg, body)
            else:
                logger.warning("send_task.unknown_channel", channel=channel)
                return {"status": "skipped"}
        except ComplianceError as ce:
            logger.warning("send_task.compliance_error", error=str(ce), message_id=message_id)
            _mark_compliance_blocked(db, message_id, str(ce))
            return {"status": "compliance_blocked"}

        # Mark sent
        db.execute(text("""
            UPDATE messages SET sent_at = NOW() WHERE id = :mid
        """), {"mid": message_id})
        db.execute(text("""
            INSERT INTO outcomes (lead_id, strategy_id, message_id, event, variant, ts)
            SELECT seq.lead_id, seq.strategy_id, :mid, 'sent', m.variant, NOW()
            FROM messages m JOIN sequences seq ON seq.id = m.sequence_id
            WHERE m.id = :mid
            ON CONFLICT DO NOTHING
        """), {"mid": message_id})
        db.commit()

        return {"status": "sent", "message_id": message_id}

    except Exception as e:
        logger.error("send_task.error", message_id=message_id, error=str(e))
        self.retry(exc=e)
    finally:
        db.close()


def schedule_sequence_step(
    db_session,
    message_id: int,
    lead: dict,
    strategy: dict,
    from_datetime: Optional[datetime.datetime] = None,
) -> datetime.datetime:
    """
    Determine the optimal send time for a message and enqueue the task.

    Integration point for M8-C4 send-time optimizer:
      1. Get recommendation for lead's ICP
      2. If high/medium confidence, prefer the recommended slot (within 48h)
      3. Otherwise use M3 "next available business hour" logic

    Returns the scheduled datetime (UTC).
    """
    from app.services.send_time_optimizer import (
        get_send_time_recommendation,
        pick_next_send_datetime,
    )

    channel = strategy.get("primary_channel", "gmail")
    icp_industry = strategy.get("icp_industry")
    icp_size = strategy.get("icp_company_size_bucket")

    now = from_datetime or datetime.datetime.utcnow()

    # Try optimized slot
    recommendation = get_send_time_recommendation(channel, icp_industry, icp_size)
    optimized_dt = pick_next_send_datetime(recommendation, now)

    if optimized_dt:
        scheduled_dt = optimized_dt
        logger.info(
            "scheduler.send_time_optimized",
            message_id=message_id,
            scheduled_for=scheduled_dt.isoformat(),
            confidence=recommendation.confidence,
        )
    else:
        # M3 fallback: next business hour
        scheduled_dt = _next_business_hour(now)

    # Enqueue with countdown
    delay_seconds = max(0, int((scheduled_dt - now).total_seconds()))
    send_sequence_step.apply_async(args=[message_id], countdown=delay_seconds)

    return scheduled_dt


def _next_business_hour(from_dt: datetime.datetime) -> datetime.datetime:
    """M3-compatible: next 09:00 UTC Mon-Fri."""
    dt = from_dt.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
    for _ in range(168):  # max 1 week ahead
        if dt.weekday() < 5 and 9 <= dt.hour < 18:
            return dt
        dt += datetime.timedelta(hours=1)
    return from_dt + datetime.timedelta(hours=1)  # fallback


def _send_gmail(db, msg, subject, body):
    from app.integrations.gmail import GmailChannel
    channel_impl = GmailChannel(user_id=msg.get("user_id"), db=db)
    channel_impl.send(
        to=msg["email"],
        subject=subject,
        body=body,
        thread_id=msg.get("gmail_thread_id"),
    )


def _send_whatsapp(db, msg, body):
    from app.integrations.whatsapp import WhatsAppChannel
    channel_impl = WhatsAppChannel(user_id=msg.get("user_id"), db=db)
    channel_impl.send(
        to=msg["phone"],
        template_name=msg.get("wa_template_name"),
        params=json.loads(msg.get("wa_template_params") or "[]"),
    )


def _mark_suppressed(db, message_id: int) -> None:
    from sqlalchemy import text
    db.execute(text("""
        UPDATE messages SET sent_at = NULL, suppressed_at = NOW() WHERE id = :mid
    """), {"mid": message_id})
    db.commit()


def _mark_compliance_blocked(db, message_id: int, reason: str) -> None:
    from sqlalchemy import text
    db.execute(text("""
        UPDATE messages SET compliance_block_reason = :reason WHERE id = :mid
    """), {"reason": reason[:500], "mid": message_id})
    db.commit()

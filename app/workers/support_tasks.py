"""Support-chat retention (Feature 3).

Chat history is kept for SUPPORT_CHAT_RETENTION_DAYS (30) and then deleted.
That is a commitment made to the user in the UI, and a commitment nothing
enforces is just a sentence — so it runs nightly from beat, not "whenever
someone remembers".

KEYED ON last_message_at, NOT created_at
----------------------------------------
A conversation started six weeks ago but used yesterday is not stale. Purging
on created_at would delete a live thread out from under someone mid-sentence.
Sessions that never received a message fall back to created_at so an abandoned
empty session still ages out.

TICKETS ARE NOT PURGED
----------------------
support_tickets.chat_session_id is ON DELETE SET NULL, so a ticket raised from
a purged conversation survives with a null reference. Losing the conversation
is acceptable; losing an open support ticket is not.

Messages are removed by the ON DELETE CASCADE on chat_messages.session_id —
deleting the session is enough, and doing it in one statement per batch beats
loading every message into Python to delete it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

__all__ = ["purge_expired_chat_sessions", "purge_old_chats"]


def purge_expired_chat_sessions(retention_days: int | None = None) -> int:
    """Delete chat sessions older than the retention window. Returns the count.

    Plain function, separate from the Celery task, so it can be tested and run
    from a shell without a broker.
    """
    from app.config import settings
    from app.db.base import SessionLocal
    from app.db.models import ChatSession

    days = retention_days if retention_days is not None else settings.support_chat_retention_days
    if days <= 0:
        logger.info("chat purge skipped: retention_days=%s (disabled)", days)
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    db = SessionLocal()
    try:
        stale = db.execute(
            select(ChatSession).where(
                func.coalesce(ChatSession.last_message_at,
                              ChatSession.created_at) < cutoff
            )
        ).scalars().all()

        for session in stale:
            # ORM delete rather than a bulk DELETE: the cascade to
            # chat_messages is declared at the database level AND in the
            # relationship, and going through the ORM keeps both honest on
            # SQLite, which does not enforce FK cascades unless pragma
            # foreign_keys is on — as it is not, in the unit-test harness.
            db.delete(session)

        db.commit()
        if stale:
            logger.info("chat purge: deleted %d session(s) older than %d days",
                        len(stale), days)
        return len(stale)
    finally:
        db.close()


@celery_app.task(name="app.workers.support_tasks.purge_old_chats")
def purge_old_chats() -> dict:
    """Nightly beat task. Never raises — a failed purge must not kill the beat.

    Returns a dict rather than None so the result backend carries something
    readable when someone asks whether it ran.
    """
    try:
        deleted = purge_expired_chat_sessions()
        return {"status": "ok", "sessions_deleted": deleted}
    except Exception as exc:  # pragma: no cover — defensive
        logger.exception("chat purge FAILED")
        return {"status": "error", "error": str(exc)}

"""NotificationService — class-style facade over the M7 FCM helpers.

M8 code (circuit breaker, task-failure monitoring, webhook delivery) calls:

    asyncio.run(NotificationService.send_to_admins(title=..., body=..., data=...))
    asyncio.run(NotificationService.send_to_user(user_id, title=..., body=...))

The canonical low-level sender is app.services.notifications.send_to_device
(M7). Device-token lookups here use the SYNC SessionLocal because every M8
caller runs inside a Celery task / daemon thread (sync context) and wraps the
coroutine with asyncio.run().

All methods are best-effort: push notification failure must never break the
business operation that triggered it.
"""
from __future__ import annotations

import logging

from app.services.notifications import send_to_device

log = logging.getLogger(__name__)


class NotificationService:
    """Static facade — no instance state."""

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _tokens_for_user_ids(user_ids: list) -> list[str]:
        """Fetch valid FCM tokens for the given users (sync session).

        Delegates to notifications.valid_tokens_for_users - this used to be a
        second, independent copy of that query, which is how the two
        notification layers drifted apart in the first place.
        """
        if not user_ids:
            return []
        try:
            from app.db.base import SessionLocal
            from app.services.notifications import valid_tokens_for_users

            db = SessionLocal()
            try:
                return valid_tokens_for_users(db, user_ids)
            finally:
                db.close()
        except Exception as exc:  # pragma: no cover — defensive
            log.warning("device token lookup failed: %s", exc)
            return []

    @staticmethod
    def _admin_user_ids() -> list:
        try:
            from app.db.base import SessionLocal
            from app.db.models import User

            db = SessionLocal()
            try:
                rows = (
                    db.query(User.id)
                    .filter(User.is_admin == True)  # noqa: E712
                    .all()
                )
                return [r[0] for r in rows]
            finally:
                db.close()
        except Exception as exc:  # pragma: no cover — defensive
            log.warning("admin lookup failed: %s", exc)
            return []

    # ------------------------------------------------------------------ #
    # public API (all awaitable — callers use asyncio.run)
    # ------------------------------------------------------------------ #

    @staticmethod
    async def send_to_user(
        user_id,
        title: str,
        body: str,
        data: dict[str, str] | None = None,
    ) -> int:
        """Push to all of one user's valid devices. Returns devices notified."""
        sent = 0
        for token in NotificationService._tokens_for_user_ids([user_id]):
            try:
                if await send_to_device(token, title, body, data, db=None):
                    sent += 1
            except Exception as exc:  # never propagate
                log.warning("push to user %s failed: %s", user_id, exc)
        return sent

    @staticmethod
    async def send_to_admins(
        title: str,
        body: str,
        data: dict[str, str] | None = None,
    ) -> int:
        """Push to every admin's valid devices. Returns devices notified."""
        admin_ids = NotificationService._admin_user_ids()
        sent = 0
        for token in NotificationService._tokens_for_user_ids(admin_ids):
            try:
                if await send_to_device(token, title, body, data, db=None):
                    sent += 1
            except Exception as exc:  # never propagate
                log.warning("admin push failed: %s", exc)
        return sent

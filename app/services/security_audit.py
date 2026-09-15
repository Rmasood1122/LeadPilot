"""Security audit log -- who did what to an account, and when.

record() ADDS a row and never commits: the caller commits it in the same
transaction as the action it describes, so a deletion and the record of it land
together or not at all. For a REFUSED action (wrong password) the caller commits
the record on its own before raising, because there is no action to share a
transaction with and the attempt is exactly what must not be lost.

The same event is also written to the application log, so it is greppable even
where nobody queries the table.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.rate_limiting import client_ip
from app.db.models import SecurityAuditEvent

logger = logging.getLogger(__name__)

STRATEGY_DELETED = "strategy.deleted"
STRATEGY_DELETE_DENIED = "strategy.delete_denied"
AUTH_LOGOUT = "auth.logout"
AUTH_REFRESH_REUSE = "auth.refresh_reuse_detected"


def record(db: Session, *, action: str, request: Request | None = None,
           user_id: uuid.UUID | None = None, owner_user_id: uuid.UUID | None = None,
           target_type: str | None = None, target_id=None,
           details: dict | None = None) -> SecurityAuditEvent:
    ip = (client_ip(request) or "")[:64] or None if request is not None else None
    agent = (request.headers.get("user-agent") or "")[:300] or None if request is not None else None
    event = SecurityAuditEvent(
        id=uuid.uuid4(), user_id=user_id, owner_user_id=owner_user_id or user_id,
        action=action, target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        ip=ip, user_agent=agent, details_json=details or None,
    )
    db.add(event)
    logger.info("SECURITY AUDIT action=%s user=%s owner=%s target=%s:%s ip=%s",
                action, user_id, event.owner_user_id, target_type, event.target_id, ip)
    return event

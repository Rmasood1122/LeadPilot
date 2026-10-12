"""Security audit log -- who did what to an account, and when.

record() ADDS a row and never commits: the caller commits it in the same
transaction as the action it describes, so a deletion and the record of it land
together or not at all. For a REFUSED action (wrong password) the caller commits
the record on its own before raising, because there is no action to share a
transaction with and the attempt is exactly what must not be lost.

The same event is also written to the application log, so it is greppable even
where nobody queries the table -- without the IP address, which stays in the
table only (docs/features/gdpr-erasure.md).
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
STRATEGY_PASSES_OVERRIDDEN = "strategy.passes_overridden"
STRATEGY_PASSES_OVERRIDE_DENIED = "strategy.passes_override_denied"
# Autopilot launch (docs/features/autopilot-launch.md): the per-strategy opt-in
# and its lawful-basis confirmation, and turning it off.
AUTOPILOT_OPT_IN = "autopilot.opt_in"
AUTOPILOT_OPT_OUT = "autopilot.opt_out"
LINKEDIN_NETWORK_IMPORTED = "linkedin_network.imported"
LINKEDIN_NETWORK_ERASED = "linkedin_network.erased"
AUTH_LOGOUT = "auth.logout"
AUTH_PASSWORD_CHANGED = "auth.password_changed"
AUTH_PASSWORD_RESET_REQUESTED = "auth.password_reset_requested"
AUTH_PASSWORD_RESET = "auth.password_reset"
AUTH_PASSWORD_RESET_REFUSED = "auth.password_reset_refused"
AUTH_REFRESH_REUSE = "auth.refresh_reuse_detected"
ACCOUNT_EXPORTED = "account.data_exported"
ACCOUNT_EXPORT_DENIED = "account.data_export_denied"
# GDPR Art. 17: the account erased itself (app/services/account_erasure.py).
# The ACCOUNT_DELETED row carries no IP, user agent or email -- see there.
ACCOUNT_DELETED = "account.deleted"
ACCOUNT_DELETE_DENIED = "account.delete_denied"


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
    # No IP in the application log: the table row holds it (and an account
    # erasure scrubs it there), but a log line cannot be erased afterwards.
    logger.info("SECURITY AUDIT action=%s user=%s owner=%s target=%s:%s",
                action, user_id, event.owner_user_id, target_type, event.target_id)
    return event

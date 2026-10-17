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
# Local business mode (docs/features/local-business-mode.md).
PRODUCT_BUSINESS_TYPE_CHANGED = "product.business_type_changed"
CUSTOMERS_IMPORTED = "customers.imported"
STRATEGY_DELETE_DENIED = "strategy.delete_denied"
STRATEGY_PASSES_OVERRIDDEN = "strategy.passes_overridden"
STRATEGY_PASSES_OVERRIDE_DENIED = "strategy.passes_override_denied"
# Autopilot launch (docs/features/autopilot-launch.md): the per-strategy opt-in
# and its lawful-basis confirmation, and turning it off.
AUTOPILOT_OPT_IN = "autopilot.opt_in"
AUTOPILOT_OPT_OUT = "autopilot.opt_out"
# Voice twin (docs/features/voice-twin.md): the owner's biometric consent,
# its revocation, the account switches, the pause after a disclosure incident
# and a live takeover.
VOICE_CLONE_CONSENTED = "voice_clone.consented"
VOICE_CLONE_REVOKED = "voice_clone.revoked"
VOICE_TWIN_SETTINGS_CHANGED = "voice_twin.settings_changed"
VOICE_TWIN_PAUSED = "voice_twin.paused"
VOICE_TWIN_RESUMED = "voice_twin.resumed"
VOICE_TWIN_TAKEOVER = "voice_twin.takeover"
# Review fix M3: a provider voice whose delete failed after an account
# erasure (operator alert) and its eventual deletion.
VOICE_CLONE_DELETE_PENDING = "voice_clone.delete_pending"
VOICE_CLONE_PROVIDER_DELETED = "voice_clone.provider_deleted"
VOICE_TWIN_NUMBER_ASSIGNED = "voice_twin.number_assigned"
LINKEDIN_NETWORK_IMPORTED = "linkedin_network.imported"
LINKEDIN_NETWORK_ERASED = "linkedin_network.erased"
# Email network: counts only (never names, addresses, subjects or bodies).
EMAIL_NETWORK_IMPORTED = "email_network.imported"
EMAIL_NETWORK_SCAN_STARTED = "email_network.gmail_scan_started"
EMAIL_NETWORK_ERASED = "email_network.erased"
EMAIL_NETWORK_ADDED_TO_CAMPAIGN = "email_network.added_to_campaign"
AUTH_LOGOUT = "auth.logout"
AUTH_PASSWORD_CHANGED = "auth.password_changed"
AUTH_PASSWORD_RESET_REQUESTED = "auth.password_reset_requested"
AUTH_PASSWORD_RESET = "auth.password_reset"
AUTH_PASSWORD_RESET_REFUSED = "auth.password_reset_refused"
AUTH_REFRESH_REUSE = "auth.refresh_reuse_detected"
# Claude / ChatGPT connector (docs/features/mcp-connector.md): consent given or
# refused on the consent page, a connection revoked, and each write tool call
# (action "mcp.<tool>", details: actor_channel="mcp", oauth_client_id).
OAUTH_CONSENT_GRANTED = "oauth.consent_granted"
OAUTH_CONSENT_DENIED = "oauth.consent_denied"
OAUTH_CODE_REUSE = "oauth.code_reuse_detected"
OAUTH_TOKEN_REVOKED = "oauth.token_revoked"
MCP_TOOL_PREFIX = "mcp."
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

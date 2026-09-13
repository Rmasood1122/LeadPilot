"""VPN / proxy / Tor / datacenter blocking at signup and login (Section D).

`enforce_clean_network(db, request, action)` is called INSIDE the two auth
handlers, after their rate limits (so a flood from a blocked address still
spends its quota and cannot turn the provider lookup into the thing being
flooded) and before any credential or account work.

Skipped entirely when:
  * blocking is not active (VPN_BLOCK_ENABLED, default on only in production);
  * the caller's address is not a public IP (localhost, a private network,
    the TestClient) -- no provider can classify those;
  * the address is on VPN_ALLOWLIST_IPS.

When the provider cannot answer, VPN_DETECTION_FAIL_CLOSED decides: open by
default (logged), because failing closed turns a third-party outage into
"nobody can sign in".

Every refusal writes an account_security_events row, committed on its own:
the request is about to fail, and the audit of WHY must survive that.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.core.rate_limiting import client_ip
from app.integrations import geolocation, ip_intelligence
from app.services import identity

logger = logging.getLogger(__name__)

VPN_BLOCKED_MESSAGE = (
    "It looks like you're connecting through a VPN, proxy or hosting network. "
    "Please disable your VPN or proxy and try again from your normal network."
)
CHECK_UNAVAILABLE_MESSAGE = (
    "We couldn't verify your network just now. Please try again in a minute."
)
# Machine-readable reason, sent as a header so the detail stays a plain
# sentence the frontend can show as-is (client.ts only renders string details).
BLOCK_HEADER = "X-Block-Reason"
VPN_BLOCKED = "VPN_BLOCKED"


def _allowlisted(ip: str) -> bool:
    allowed = {part.strip() for part in (settings.vpn_allowlist_ips or "").split(",")}
    return ip in allowed


def enforce_clean_network(db: Session, request: Request, action: str,
                          email: str | None = None) -> None:
    if not settings.vpn_blocking_active:
        return
    ip = client_ip(request)
    if not geolocation.is_public_ip(ip) or _allowlisted(ip):
        return

    try:
        risk = ip_intelligence.assess(ip)
    except ip_intelligence.IpIntelligenceError as exc:
        logger.warning("VPN check for %s (%s) unavailable: %s", action, ip, exc)
        if not settings.vpn_detection_fail_closed:
            return
        _audit(db, f"{action}_vpn_check_failed", email, ip, {"error": str(exc)[:300]})
        raise HTTPException(status_code=503, detail=CHECK_UNAVAILABLE_MESSAGE)

    if not risk.blocked:
        return
    _audit(db, f"{action}_blocked_vpn", email, ip,
           {"reasons": risk.reasons, "provider": risk.provider})
    logger.info("%s refused for %s: %s", action, ip, ",".join(risk.reasons))
    raise HTTPException(status_code=403, detail=VPN_BLOCKED_MESSAGE,
                        headers={BLOCK_HEADER: VPN_BLOCKED})


def _audit(db: Session, event: str, email: str | None, ip: str, details: dict) -> None:
    try:
        identity.record_event(db, event=event, email=(email or "").lower().strip() or None,
                              ip=ip, details=details)
        db.commit()
    except Exception:  # noqa: BLE001 -- the refusal must still happen
        logger.exception("could not record %s for %s", event, ip)
        db.rollback()

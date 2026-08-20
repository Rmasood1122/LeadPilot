"""Calendly adapter — booking links + webhook handling (M3 Chunk 5).

Auth: personal access token from CALENDLY_API_TOKEN.
# TODO: verify current Calendly auth options (PAT vs OAuth) against docs.

Webhook signature: Calendly sends a `Calendly-Webhook-Signature` header of
the form "t=<timestamp>,v1=<hex hmac-sha256 of '<t>.<raw body>' with the
signing key>". # TODO: verify exact header name/scheme against current docs.
"""

import hashlib
import hmac
import logging

from app.config import settings
from app.integrations.plumbing import BaseHttpAdapter

logger = logging.getLogger(__name__)

CALENDLY_API_BASE = "https://api.calendly.com"  # TODO: verify against current Calendly docs
SIGNATURE_HEADER = "Calendly-Webhook-Signature"  # TODO: verify against current Calendly docs


class CalendlyAdapter(BaseHttpAdapter):
    provider = "calendly"
    base_url = CALENDLY_API_BASE

    def __init__(self, api_token: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.api_token = api_token if api_token is not None else settings.calendly_api_token

    def _auth(self) -> dict:
        return {"headers": {"Authorization": f"Bearer {self.api_token}"}}

    def current_user(self) -> dict:
        # TODO: verify against current Calendly docs (GET /users/me)
        return self.call("GET", "/users/me").get("resource", {})

    def event_types(self) -> list[dict]:
        """The user's bookable event types (name + scheduling_url)."""
        user_uri = self.current_user().get("uri")
        if not user_uri:
            return []
        data = self.call("GET", "/event_types", params={"user": user_uri})
        # TODO: verify against current Calendly docs (collection shape)
        return [
            {
                "name": item.get("name"),
                "scheduling_url": item.get("scheduling_url"),
                "uri": item.get("uri"),
                "active": item.get("active"),
            }
            for item in data.get("collection", [])
        ]

    def health_check(self) -> bool:
        if self.breaker.is_open():
            return False
        try:
            self.call("GET", "/users/me")
            return True
        except Exception:
            return False


def verify_webhook_signature(raw_body: bytes, signature_header: str | None,
                             signing_key: str | None = None) -> bool:
    """Constant-time verification of Calendly's t=...,v1=... signature."""
    signing_key = signing_key if signing_key is not None else settings.calendly_webhook_signing_key
    if not signing_key or not signature_header:
        return False
    try:
        parts = dict(p.split("=", 1) for p in signature_header.split(","))
        timestamp, given = parts["t"], parts["v1"]
    except (ValueError, KeyError):
        return False
    expected = hmac.new(
        signing_key.encode(),
        f"{timestamp}.{raw_body.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, given)


def extract_event_id(payload: dict, raw_body: bytes) -> str:
    """Stable id for webhook dedupe: Calendly retries deliveries."""
    for candidate in (
        payload.get("event_id"),
        (payload.get("payload") or {}).get("uri"),
        payload.get("created_at"),
    ):
        if candidate:
            return str(candidate)[:200]
    return hashlib.sha256(raw_body).hexdigest()


# --------------------------------------------------------------------------
# Tenant tagging — which account does an inbound booking belong to?
# --------------------------------------------------------------------------
#
# A Calendly delivery carries no account identity of its own: one deployment
# has ONE webhook subscription and ONE signing key, and the payload describes
# the invitee, not which of our users owns the campaign. The handler used to
# resolve the lead with `select(Lead).where(Lead.email == email)` over the
# whole table and take the first row - so when two customers prospected the
# same person (routine in B2B) a booking could land on the wrong tenant's
# lead, flip its status and stop their sequences. Same bug class as the
# inbound-reply matching fixed in session update 4.
#
# The fix is to put the identity INTO the link we hand the lead, and read it
# back off the webhook. Calendly forwards the standard UTM query parameters on
# a booking link into `payload.tracking` on invitee.created / invitee.canceled,
# so the tenant id makes the round trip with no Calendly plan requirement (a
# per-tenant webhook subscription needs Enterprise) and no reliance on email.
#
# FIELD CHOICE: utm_content. `booking_url` is a URL the USER pastes in when
# they create a sequence and may already carry their own utm_source /
# utm_campaign for their own attribution; utm_content is the least likely of
# the set to be already in use, and overwriting a customer's utm_source to
# smuggle an internal id would silently corrupt their reporting. Anything
# already on their URL is preserved.

TENANT_TRACKING_PARAM = "utm_content"


def tag_booking_url(booking_url: str | None, user_id) -> str | None:
    """Return `booking_url` with the owning tenant's id attached.

    Idempotent, and never raises: a malformed URL is returned untouched
    rather than costing the lead their scheduling link.
    """
    if not booking_url or user_id is None:
        return booking_url
    try:
        from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

        parts = urlparse(booking_url)
        params = dict(parse_qsl(parts.query, keep_blank_values=True))
        params[TENANT_TRACKING_PARAM] = str(user_id)
        return urlunparse(parts._replace(query=urlencode(params)))
    except Exception:  # noqa: BLE001 - a link is better than no link
        logger.warning("could not tag booking url %r - sending it untagged",
                       booking_url)
        return booking_url


def tenant_id_from_payload(payload: dict):
    """The tenant id a booking came back with, or None.

    Returns None for every "we cannot tell" case - missing tracking block,
    absent parameter, or a value that is not a UUID (an organic visitor who
    found the link elsewhere, or a link generated before tagging existed).
    The caller must treat None as "do not match", never as "match anything".
    """
    import uuid as _uuid

    tracking = ((payload or {}).get("payload") or {}).get("tracking") or {}
    raw = (tracking.get(TENANT_TRACKING_PARAM) or "").strip()
    if not raw:
        return None
    try:
        return _uuid.UUID(raw)
    except (ValueError, AttributeError, TypeError):
        logger.info("calendly booking carried an unparseable tenant id %r", raw[:80])
        return None

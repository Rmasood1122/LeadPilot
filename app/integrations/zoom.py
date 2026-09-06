"""Zoom adapter — creates a meeting and returns its join_url.

AUTH: SERVER-TO-SERVER OAUTH, NOT THE USER-CONSENT FLOW
Zoom offers both. This uses server-to-server (grant_type=account_credentials,
Basic-authenticated with the app's client id/secret plus the account id),
because the alternative would put a second per-user OAuth dance in front of
booking a call — a consent screen, a callback route, a refresh token per user
and a re-consent every time Zoom rotates scopes. Server-to-server means the
LeadPilot operator authorises once, in the Zoom marketplace app, and every
meeting is created under that account.

The trade-off is stated rather than hidden: meetings are hosted by the
configured Zoom account, not by each individual LeadPilot user. For a product
whose users are solo founders and boutique agency owners that is the same
person; for a future team plan it is not, and this is the module that would
change.

THE TOKEN IS CACHED IN REDIS
Zoom's account tokens last an hour. Minting one per meeting would mean two
round trips for every booking and a rate limit that bites during a batch. The
cache key is per client id, so rotating credentials invalidates it on its own
rather than serving a token minted with the old secret until it expires.
"""

from __future__ import annotations

import base64
import logging
from datetime import timezone

import httpx

from app.config import settings
from app.core.exceptions import ClientHunterError
from app.integrations.plumbing import BaseHttpAdapter

logger = logging.getLogger(__name__)

# TODO: verify against current Zoom API docs (v2 base + OAuth token endpoint).
ZOOM_API_BASE = "https://api.zoom.us/v2"
ZOOM_TOKEN_ENDPOINT = "https://zoom.us/oauth/token"

# Zoom meeting types. 2 = scheduled meeting.
# TODO: verify against current Zoom API docs.
_SCHEDULED = 2

# One hour tokens; expire the cache entry early so a token never dies
# mid-request.
_TOKEN_CACHE_SECONDS = 3000


class ZoomNotConfigured(ClientHunterError):
    """The deployment has no Zoom credentials.

    Raised instead of letting the call 401: "ZOOM_OAUTH_CLIENT_ID is empty" is
    something an operator can fix in a dashboard, and "Zoom said 401" is not.
    """


class ZoomAdapter(BaseHttpAdapter):
    provider = "zoom"
    base_url = ZOOM_API_BASE

    def __init__(self, token_http: httpx.Client | None = None, **kwargs):
        super().__init__(**kwargs)
        # Separate client from self.http: the token endpoint is on a different
        # host than the API base, and BaseHttpAdapter's client is pinned to
        # base_url.
        self._token_http = token_http or httpx.Client(timeout=30.0)

    # -- credentials -------------------------------------------------------
    @staticmethod
    def configured() -> bool:
        return bool(settings.zoom_oauth_client_id
                    and settings.zoom_oauth_client_secret
                    and settings.zoom_account_id)

    def _cache_key(self) -> str:
        return f"zoom:token:{settings.zoom_oauth_client_id}"

    def _access_token(self) -> str:
        if not self.configured():
            raise ZoomNotConfigured(
                "Zoom is not configured. Set ZOOM_OAUTH_CLIENT_ID, "
                "ZOOM_OAUTH_CLIENT_SECRET and ZOOM_ACCOUNT_ID, or create the "
                "meeting with a custom link instead."
            )
        try:
            cached = self.redis.get(self._cache_key())
            if cached:
                return cached
        except Exception as exc:  # noqa: BLE001 — Redis down must not block a call
            logger.warning("zoom token cache read failed: %s", exc)

        basic = base64.b64encode(
            f"{settings.zoom_oauth_client_id}:"
            f"{settings.zoom_oauth_client_secret}".encode()
        ).decode()
        resp = self._token_http.post(
            ZOOM_TOKEN_ENDPOINT,
            headers={"Authorization": f"Basic {basic}"},
            data={"grant_type": "account_credentials",
                  "account_id": settings.zoom_account_id},
        )
        if resp.status_code >= 400:
            raise ZoomNotConfigured(
                f"Zoom rejected the credentials: HTTP {resp.status_code} "
                f"{resp.text[:200]}"
            )
        token = resp.json().get("access_token") or ""
        if not token:
            raise ZoomNotConfigured("Zoom returned no access_token")
        try:
            self.redis.setex(self._cache_key(), _TOKEN_CACHE_SECONDS, token)
        except Exception as exc:  # noqa: BLE001
            logger.warning("zoom token cache write failed: %s", exc)
        return token

    def _auth(self) -> dict:
        return {"headers": {"Authorization": f"Bearer {self._access_token()}"}}

    # -- API ---------------------------------------------------------------
    def create_meeting(self, *, topic: str, start_at, duration_minutes: int,
                       agenda: str | None = None) -> dict:
        """Schedule a meeting on the configured account. Returns the resource.

        `start_time` is sent as UTC with an explicit Z, which is the form Zoom
        documents for a UTC schedule; sending a local time without a timezone
        field is how a meeting lands in the wrong hour.
        """
        body = {
            "topic": topic[:200],
            "type": _SCHEDULED,
            "start_time": start_at.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
            "duration": max(1, int(duration_minutes)),
            "timezone": "UTC",
            "agenda": (agenda or "")[:2000] or None,
            "settings": {
                # Neither party should be blocked on the host arriving first —
                # a prospect who joins to a "waiting for host" screen while the
                # host is on the LeadPilot meeting page is a lost call.
                "join_before_host": True,
                "waiting_room": False,
            },
        }
        return self.call("POST", "/users/me/meetings", json_body=body)

    def health_check(self) -> bool:
        if self.breaker.is_open() or not self.configured():
            return False
        try:
            self.call("GET", "/users/me")
            return True
        except Exception:  # noqa: BLE001
            return False


def create_zoom_meeting(*, topic: str, start_at, duration_minutes: int,
                        agenda: str | None = None) -> dict:
    """{"join_url", "external_event_id"} for a new Zoom meeting."""
    data = ZoomAdapter().create_meeting(
        topic=topic, start_at=start_at, duration_minutes=duration_minutes,
        agenda=agenda,
    )
    return {
        "join_url": data.get("join_url") or "",
        "external_event_id": str(data.get("id") or "")[:200],
    }

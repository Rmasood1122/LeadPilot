"""PostIQ — Google Apps Script Web App client.

Verified against PostIQ apps-script/Code.js and core-logic.js:

  GET  <webapp_url>   health check (unauthenticated):
                      {"ok": true, "service": "postiq", "phase": 4, "ts": ...}
  POST <webapp_url>   one entry point, serving the Chrome extension's LinkedIn
                      post CAPTURE and Meta's WhatsApp webhook. Nothing else:
                      there is no action to list or fetch generated drafts,
                      and none to trigger generation or delivery — PostIQ runs
                      those on its own triggers and delivers drafts to
                      Telegram / WhatsApp itself.

  Auth: Apps Script's doPost cannot read request headers, so the token travels
  in the BODY at auth.client_token (PostIQCore.extractEnvelope).
  Responses: always HTTP 200 (Apps Script cannot set a status); the outcome is
  {"ok": bool, "error_code": str, "message": str}.

Every request follows redirects — Apps Script always answers with a 302 to
script.googleusercontent.com.

The Web App URL is supplied by an ordinary (non-admin) user, so it is pinned
to https://script.google.com/macros/... by `validate_webapp_url` — otherwise
the server would request any URL a user names.

No retries here: PostIQ runs on the free Apps Script tier behind a script
lock and a daily request quota.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

WEBAPP_HOST = "script.google.com"
CLIENT_NAME = "leadpilot"
CLIENT_VERSION = "1.0"

# PostIQCore.ERROR_CODES values this client branches on.
UNAUTHORIZED = "UNAUTHORIZED"
SERVER_NOT_CONFIGURED = "SERVER_NOT_CONFIGURED"
VALIDATION_FAILED = "VALIDATION_FAILED"
RATE_LIMITED = "RATE_LIMITED"


class PostIQError(Exception):
    def __init__(self, message: str, error_code: str | None = None):
        super().__init__(message)
        self.error_code = error_code


def validate_webapp_url(webapp_url: str) -> str:
    """Return the URL if it is an Apps Script Web App URL, else raise ValueError."""
    parsed = urlparse(webapp_url.strip())
    if (parsed.scheme != "https" or parsed.hostname != WEBAPP_HOST
            or parsed.port not in (None, 443) or parsed.username or parsed.password
            or not parsed.path.startswith("/macros/")):
        raise ValueError(
            "webapp_url must be a Google Apps Script Web App URL "
            "(https://script.google.com/macros/s/<id>/exec)"
        )
    return webapp_url.strip()


def _client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(timeout=timeout, follow_redirects=True)


def _json(r: httpx.Response) -> dict:
    try:
        data = r.json()
    except ValueError as exc:
        # Usually a Google sign-in page: the Web App is not deployed with
        # access "Anyone".
        raise PostIQError("PostIQ returned a non-JSON response — check that the Web App is "
                          "deployed with access 'Anyone'") from exc
    if not isinstance(data, dict):
        raise PostIQError("PostIQ returned an unexpected response shape")
    return data


def health_check(*, webapp_url: str) -> bool:
    """True if the Web App answers its health check. Says nothing about the token."""
    try:
        with _client(timeout=10.0) as client:
            r = client.get(validate_webapp_url(webapp_url))
        data = _json(r)
        return r.status_code == 200 and data.get("ok") is True and data.get("service") == "postiq"
    except Exception:
        return False


def verify_token(*, webapp_url: str, token: str) -> None:
    """Prove the token is accepted, without saving anything in PostIQ.

    doPost authenticates BEFORE it validates the capture. An envelope with the
    token and no capture therefore comes back VALIDATION_FAILED when the token
    is right and UNAUTHORIZED when it is wrong; nothing is written to the
    sheet either way. It does consume one request of PostIQ's rate limit.

    Raises PostIQError (with error_code) unless the token is accepted.
    """
    try:
        with _client() as client:
            r = client.post(validate_webapp_url(webapp_url), json={
                "auth": {"client_token": token},
                "client": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
            })
    except httpx.RequestError as exc:
        raise PostIQError(f"Network error reaching PostIQ: {exc}") from exc

    data = _json(r)
    code = data.get("error_code")
    if code == VALIDATION_FAILED:
        return  # authenticated; only the (deliberately absent) capture was rejected
    if code == UNAUTHORIZED:
        raise PostIQError("PostIQ rejected the token.", error_code=code)
    if code == SERVER_NOT_CONFIGURED:
        raise PostIQError("PostIQ has no POSTIQ_CLIENT_TOKEN script property set.",
                          error_code=code)
    if code == RATE_LIMITED:
        raise PostIQError("PostIQ rate limit reached — try again later.", error_code=code)
    raise PostIQError(f"Unexpected PostIQ response: {code or data.get('message') or 'unknown'}",
                      error_code=code)

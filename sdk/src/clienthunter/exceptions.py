"""Typed exceptions for the ClientHunter SDK.

Mapping from backend HTTP responses:
    401, 403        → AuthError
    404             → NotFoundError
    422 compliance  → ComplianceError   (detail contains "compliance" key OR
                                         the detail string starts with a known
                                         compliance marker — see client._raise_for)
    422 other       → ValidationError
    429             → RateLimitError
    5xx             → APIError (after exhausting retries)
    network errors  → APIError wrapping the original exception

Every exception stores the raw ``detail`` from the backend so callers can
inspect it without parsing the message string.  Secrets are never included.
"""

from __future__ import annotations


class ClientHunterError(Exception):
    """Base class for all SDK exceptions."""


class AuthError(ClientHunterError):
    """Authentication or authorisation failed (HTTP 401 / 403).

    Common causes:
    - Expired access token (the client retries once with a refresh automatically).
    - Invalid or revoked API key.
    - Accessing a resource owned by a different user.
    """

    def __init__(self, detail: str = "authentication failed") -> None:
        self.detail = detail
        super().__init__(detail)


class NotFoundError(ClientHunterError):
    """The requested resource does not exist (HTTP 404)."""

    def __init__(self, resource: str = "resource", detail: str | None = None) -> None:
        self.resource = resource
        self.detail = detail or f"{resource} not found"
        super().__init__(self.detail)


class ValidationError(ClientHunterError):
    """The request payload was rejected by the backend (HTTP 422).

    ``detail`` is the raw FastAPI validation error structure (list of dicts
    with ``loc``, ``msg``, ``type``) or a plain string for custom errors.
    """

    def __init__(self, detail: object) -> None:
        self.detail = detail
        # Produce a human-readable summary without leaking the full structure
        if isinstance(detail, list):
            parts = [f"{'.'.join(str(p) for p in e.get('loc', []))}: {e.get('msg', '')}"
                     for e in detail if isinstance(e, dict)]
            msg = "; ".join(parts) if parts else str(detail)
        else:
            msg = str(detail)
        super().__init__(msg)


class ComplianceError(ClientHunterError):
    """A request was blocked by a compliance rule.

    The backend refuses operations that would violate outreach law or platform
    policy (CAN-SPAM, GDPR, WhatsApp template requirements, etc.).  This is
    NOT a bug — it is the system working correctly.

    Attributes:
        rule: Short identifier for the rule that fired (e.g. ``"gdpr"``,
              ``"whatsapp_cold_freeform"``, ``"suppression_list"``).
        detail: Full explanation from the backend.
        remediation: Optional human-readable next step (populated by the SDK
                     when it can infer one from the rule identifier).
    """

    _REMEDIATIONS: dict[str, str] = {
        "gdpr": (
            "EU targets require a documented lawful basis. Add a lawful-basis "
            "note to your strategy or exclude the affected contacts."
        ),
        "whatsapp_cold_freeform": (
            "Cold WhatsApp contacts must receive Meta-approved template messages "
            "only. Create and submit a template via `ch.whatsapp.templates.create()` "
            "or `clienthunter run` — do not send free-form messages to cold leads."
        ),
        "suppression_list": (
            "This contact is on the suppression list and must never be messaged "
            "again. Remove them from your lead set."
        ),
        "can_spam": (
            "Every email must include a working unsubscribe link and your identity. "
            "Update your sequence template to include the required footer."
        ),
        "bounce_rate": (
            "The campaign bounce rate exceeded the 3% safety threshold and was "
            "paused automatically. Review your lead list quality before resuming "
            "via `ch.campaigns.resume(strategy_id)`."
        ),
    }

    def __init__(self, rule: str, detail: str) -> None:
        self.rule = rule
        self.detail = detail
        self.remediation: str | None = self._REMEDIATIONS.get(rule)
        msg = f"[{rule}] {detail}"
        if self.remediation:
            msg = f"{msg}\n\nRemediation: {self.remediation}"
        super().__init__(msg)


class RateLimitError(ClientHunterError):
    """The backend rate-limited this request (HTTP 429).

    ``retry_after`` is the number of seconds to wait, if the backend provided
    a ``Retry-After`` header.  The SDK's internal retry loop already honours
    this — you will only see this exception if all retry attempts are exhausted.
    """

    def __init__(self, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        if retry_after is not None:
            msg = f"rate limited; retry after {retry_after:.0f}s"
        else:
            msg = "rate limited; back off and try again"
        super().__init__(msg)


class APIError(ClientHunterError):
    """Unexpected HTTP error or network failure.

    Attributes:
        status_code: HTTP status code, or ``None`` for network errors.
        detail: Error body text from the server (never contains secrets).
    """

    def __init__(self, detail: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        self.detail = detail
        prefix = f"HTTP {status_code}: " if status_code else "network error: "
        super().__init__(f"{prefix}{detail}")

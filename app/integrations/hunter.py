"""Hunter.io adapter — email finding + verification.

Every email in LeadPilot MUST pass through `verify()` before any later
milestone may use it. Status mapping (project knowledge):
    deliverable -> verified | risky -> flagged | undeliverable -> dropped

Auth via HUNTER_API_KEY (env). Shares all plumbing (retry, cache,
breaker, logging). Unverified API details are marked
`# TODO: verify against current Hunter docs`.
"""

import logging

from app.config import settings
from app.integrations.base import (
    EmailVerificationStatus,
    EmailVerifier,
    VerificationResult,
    register_email_verifier,
)
from app.integrations.plumbing import BaseHttpAdapter

logger = logging.getLogger(__name__)

# Hunter's email-verifier "result" field values.
# TODO: verify against current Hunter docs
_RESULT_MAP = {
    "deliverable": EmailVerificationStatus.DELIVERABLE,
    "risky": EmailVerificationStatus.RISKY,
    "undeliverable": EmailVerificationStatus.UNDELIVERABLE,
}


@register_email_verifier
class HunterAdapter(BaseHttpAdapter, EmailVerifier):
    provider = "hunter"
    base_url = "https://api.hunter.io/v2"  # TODO: verify against current Hunter docs

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key if api_key is not None else settings.hunter_api_key
        if not self.api_key:
            logger.warning("HUNTER_API_KEY is not set — Hunter calls will fail auth")

    def _auth(self) -> dict:
        # Query-param key auth.  # TODO: verify against current Hunter docs
        return {"params": {"api_key": self.api_key}}

    # ------------------------------------------------------------------
    # EmailVerifier interface
    # ------------------------------------------------------------------

    def find_email(self, full_name: str, domain: str) -> str | None:
        """Email finder for leads the source returned without an email.
        Cached — the same person+domain lookup is never paid for twice."""
        if not full_name or not domain:
            return None
        data = self.call(
            "GET",
            "/email-finder",  # TODO: verify against current Hunter docs
            params={"domain": domain, "full_name": full_name},
            cache_ttl=settings.cache_ttl_enrichment_seconds,
        )
        return (data.get("data") or {}).get("email")

    def verify(self, email: str) -> VerificationResult:
        """Deliverability verification — the mandatory gate."""
        data = self.call(
            "GET",
            "/email-verifier",  # TODO: verify against current Hunter docs
            params={"email": email},
            cache_ttl=settings.cache_ttl_enrichment_seconds,
        )
        payload = data.get("data") or {}
        result = str(payload.get("result") or "").lower()
        status = _RESULT_MAP.get(result, EmailVerificationStatus.UNKNOWN)
        score = payload.get("score")
        return VerificationResult(
            email=email,
            status=status,
            score=int(score) if score is not None else None,
            raw=payload,
        )

    def health_check(self) -> bool:
        if self.breaker.is_open():
            return False
        try:
            self.call("GET", "/account")  # TODO: verify against current Hunter docs
            return True
        except Exception:
            return False

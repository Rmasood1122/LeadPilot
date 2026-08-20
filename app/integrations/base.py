"""Adapter foundation — interfaces, shared data types, plug-in registry.

Every lead-sourcing or email-verification provider (Apollo, Hunter, and
later LinkedIn/HubSpot/...) implements one of the abstract interfaces
below and registers itself. Core logic (Celery lead tasks, API endpoints)
only ever talks to these interfaces — adding a provider never touches
core code (project knowledge, section E: adapter pattern).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar

from app.db.models import LeadStatus

# --------------------------------------------------------------------------
# Shared data types (provider-agnostic)
# --------------------------------------------------------------------------


@dataclass
class RawLead:
    """A person as returned by a lead source's search, pre-enrichment."""

    source: str                       # provider key, e.g. "apollo"
    external_id: str | None = None    # provider's person id (dedupe key)
    full_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    title: str | None = None
    company: str | None = None
    company_domain: str | None = None
    email: str | None = None
    phone: str | None = None
    raw: dict = field(default_factory=dict)  # full provider payload


@dataclass
class EnrichedLead(RawLead):
    """A RawLead plus the provider's enrichment payload."""

    enrichment: dict = field(default_factory=dict)

    @classmethod
    def from_raw(cls, lead: RawLead, enrichment: dict) -> "EnrichedLead":
        return cls(
            source=lead.source,
            external_id=lead.external_id,
            full_name=lead.full_name,
            first_name=lead.first_name,
            last_name=lead.last_name,
            title=lead.title,
            company=lead.company,
            company_domain=lead.company_domain,
            email=lead.email,
            phone=lead.phone,
            raw=lead.raw,
            enrichment=enrichment,
        )


class EmailVerificationStatus(str, Enum):
    DELIVERABLE = "deliverable"
    RISKY = "risky"
    UNDELIVERABLE = "undeliverable"
    UNKNOWN = "unknown"


# Project-knowledge mapping: deliverable -> verified, risky -> flagged,
# undeliverable -> dropped. UNKNOWN stays flagged for a human decision.
VERIFICATION_TO_LEAD_STATUS: dict[EmailVerificationStatus, LeadStatus] = {
    EmailVerificationStatus.DELIVERABLE: LeadStatus.VERIFIED,
    EmailVerificationStatus.RISKY: LeadStatus.FLAGGED,
    EmailVerificationStatus.UNDELIVERABLE: LeadStatus.DROPPED,
    EmailVerificationStatus.UNKNOWN: LeadStatus.FLAGGED,
}


@dataclass
class VerificationResult:
    email: str
    status: EmailVerificationStatus
    score: int | None = None          # provider confidence 0-100 when given
    raw: dict = field(default_factory=dict)

    @property
    def lead_status(self) -> LeadStatus:
        return VERIFICATION_TO_LEAD_STATUS[self.status]


# --------------------------------------------------------------------------
# Interfaces
# --------------------------------------------------------------------------


class LeadSource(ABC):
    """A provider that can find and enrich people matching an ICP."""

    provider: ClassVar[str]  # unique registry key, e.g. "apollo"

    @abstractmethod
    def search(self, icp_criteria: dict, max_leads: int) -> list[RawLead]:
        """Find people matching the ICP criteria. Must respect max_leads."""

    @abstractmethod
    def enrich(self, lead: RawLead) -> EnrichedLead:
        """Enrich one lead. Implementations MUST cache so the same
        person/company is never paid for twice."""

    @abstractmethod
    def health_check(self) -> bool:
        """Cheap call proving auth + connectivity."""


class EmailVerifier(ABC):
    """A provider that finds and verifies email addresses."""

    provider: ClassVar[str]

    @abstractmethod
    def find_email(self, full_name: str, domain: str) -> str | None:
        """Best-guess email for a person at a domain, or None."""

    @abstractmethod
    def verify(self, email: str) -> VerificationResult:
        """Verify deliverability. Every email must pass through this
        before any later milestone may use it."""

    @abstractmethod
    def health_check(self) -> bool:
        ...


# --------------------------------------------------------------------------
# Registry — new providers plug in without touching core logic
# --------------------------------------------------------------------------

_LEAD_SOURCES: dict[str, type[LeadSource]] = {}
_EMAIL_VERIFIERS: dict[str, type[EmailVerifier]] = {}


def register_lead_source(cls: type[LeadSource]) -> type[LeadSource]:
    """Class decorator: @register_lead_source above a LeadSource subclass."""
    key = getattr(cls, "provider", None)
    if not key:
        raise ValueError(f"{cls.__name__} must define a `provider` key")
    if key in _LEAD_SOURCES:
        raise ValueError(f"lead source '{key}' registered twice")
    _LEAD_SOURCES[key] = cls
    return cls


def register_email_verifier(cls: type[EmailVerifier]) -> type[EmailVerifier]:
    key = getattr(cls, "provider", None)
    if not key:
        raise ValueError(f"{cls.__name__} must define a `provider` key")
    if key in _EMAIL_VERIFIERS:
        raise ValueError(f"email verifier '{key}' registered twice")
    _EMAIL_VERIFIERS[key] = cls
    return cls


def get_lead_source(provider: str, **kwargs) -> LeadSource:
    try:
        return _LEAD_SOURCES[provider](**kwargs)
    except KeyError:
        raise KeyError(
            f"unknown lead source '{provider}' — registered: {sorted(_LEAD_SOURCES)}"
        ) from None


def get_email_verifier(provider: str, **kwargs) -> EmailVerifier:
    try:
        return _EMAIL_VERIFIERS[provider](**kwargs)
    except KeyError:
        raise KeyError(
            f"unknown email verifier '{provider}' — registered: {sorted(_EMAIL_VERIFIERS)}"
        ) from None


def registered_lead_sources() -> list[str]:
    return sorted(_LEAD_SOURCES)


def registered_email_verifiers() -> list[str]:
    return sorted(_EMAIL_VERIFIERS)

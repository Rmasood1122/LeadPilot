"""Apollo.io adapter — lead sourcing & enrichment.

Auth via APOLLO_API_KEY (env). All calls inherit the shared plumbing:
retry/backoff, Redis caching, structured logging, circuit breaker.

Honesty rule from the project spec: any endpoint/parameter not verified
against current Apollo documentation is marked with
`# TODO: verify against current Apollo docs` rather than invented.
"""

import logging

from app.config import settings
from app.integrations.base import EnrichedLead, LeadSource, RawLead, register_lead_source
from app.integrations.plumbing import BaseHttpAdapter

logger = logging.getLogger(__name__)

# Apollo returns a placeholder instead of null for emails you haven't paid
# to unlock; treat those as "no email" so Hunter can find one instead.
_LOCKED_EMAIL_MARKERS = ("email_not_unlocked", "not_unlocked")


def icp_to_apollo_params(icp_criteria: dict) -> dict:
    """Translate LeadPilot's structured ICP criteria into Apollo people
    search parameters.

    Our ICP criteria schema (produced by app/services/icp_extraction.py or
    supplied explicitly by the API caller):
        titles: list[str]                e.g. ["Owner", "Operations Manager"]
        industries: list[str]            e.g. ["fire protection services"]
        locations: list[str]             e.g. ["Texas, US", "Georgia, US"]
        company_size_ranges: list[str]   e.g. ["11,50", "51,200"]
        keywords: list[str]              free-text qualifiers
    """
    params: dict = {}
    if icp_criteria.get("titles"):
        params["person_titles"] = list(icp_criteria["titles"])
    if icp_criteria.get("locations"):
        params["person_locations"] = list(icp_criteria["locations"])
    if icp_criteria.get("company_size_ranges"):
        # Apollo expects "min,max" strings.  # TODO: verify against current Apollo docs
        params["organization_num_employees_ranges"] = list(icp_criteria["company_size_ranges"])
    if icp_criteria.get("industries"):
        # Industry filtering parameter name.  # TODO: verify against current Apollo docs
        params["q_organization_keyword_tags"] = list(icp_criteria["industries"])
    if icp_criteria.get("keywords"):
        params["q_keywords"] = " ".join(icp_criteria["keywords"])
    return params


@register_lead_source
class ApolloAdapter(BaseHttpAdapter, LeadSource):
    provider = "apollo"
    base_url = "https://api.apollo.io/api/v1"  # TODO: verify against current Apollo docs

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key if api_key is not None else settings.apollo_api_key
        if not self.api_key:
            logger.warning("APOLLO_API_KEY is not set — Apollo calls will fail auth")

    def _auth(self) -> dict:
        # Header-based key auth.  # TODO: verify against current Apollo docs
        return {"headers": {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
        }}

    # ------------------------------------------------------------------
    # LeadSource interface
    # ------------------------------------------------------------------

    def search(self, icp_criteria: dict, max_leads: int) -> list[RawLead]:
        """Paginated people search, hard-capped at max_leads."""
        max_leads = min(max_leads, settings.leads_max_per_run)
        base_params = icp_to_apollo_params(icp_criteria)
        leads: list[RawLead] = []
        page = 1

        while len(leads) < max_leads:
            body = {
                **base_params,
                "page": page,
                "per_page": min(settings.apollo_page_size, max_leads - len(leads)),
            }
            data = self.call(
                "POST",
                "/mixed_people/search",  # TODO: verify against current Apollo docs
                json_body=body,
                cache_ttl=settings.cache_ttl_search_seconds,
                cost_units=body["per_page"],
            )
            people = data.get("people") or data.get("contacts") or []
            if not people:
                break
            leads.extend(self._to_raw_lead(p) for p in people)

            pagination = data.get("pagination") or {}
            total_pages = int(pagination.get("total_pages") or page)
            if page >= total_pages:
                break
            page += 1

        return leads[:max_leads]

    def enrich(self, lead: RawLead) -> EnrichedLead:
        """Enrich one person. Cached in Redis for
        CACHE_TTL_ENRICHMENT_SECONDS — the same person is never paid for
        twice (cache key is derived from the request payload)."""
        if lead.external_id:
            body = {"id": lead.external_id}  # TODO: verify against current Apollo docs
        elif lead.email:
            body = {"email": lead.email}
        else:
            body = {
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "organization_name": lead.company,
            }
        data = self.call(
            "POST",
            "/people/match",  # TODO: verify against current Apollo docs
            json_body=body,
            cache_ttl=settings.cache_ttl_enrichment_seconds,
        )
        person = data.get("person") or {}
        merged = self._to_raw_lead(person) if person else lead
        # Never lose information we already had.
        merged.source = "apollo"
        merged.external_id = merged.external_id or lead.external_id
        merged.email = merged.email or lead.email
        merged.phone = merged.phone or lead.phone
        merged.full_name = merged.full_name or lead.full_name
        merged.title = merged.title or lead.title
        merged.company = merged.company or lead.company
        merged.company_domain = merged.company_domain or lead.company_domain
        return EnrichedLead.from_raw(merged, enrichment=data)

    def health_check(self) -> bool:
        if self.breaker.is_open():
            return False
        try:
            self.call("GET", "/auth/health")  # TODO: verify against current Apollo docs
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Response mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_raw_lead(person: dict) -> RawLead:
        org = person.get("organization") or {}
        email = person.get("email")
        if email and any(marker in email for marker in _LOCKED_EMAIL_MARKERS):
            email = None
        phone = None
        numbers = person.get("phone_numbers") or []
        if numbers and isinstance(numbers[0], dict):
            phone = numbers[0].get("sanitized_number") or numbers[0].get("raw_number")
        return RawLead(
            source="apollo",
            external_id=str(person["id"]) if person.get("id") is not None else None,
            full_name=person.get("name"),
            first_name=person.get("first_name"),
            last_name=person.get("last_name"),
            title=person.get("title"),
            company=org.get("name"),
            company_domain=org.get("primary_domain") or org.get("website_url"),
            email=email,
            phone=phone,
            raw=person,
        )

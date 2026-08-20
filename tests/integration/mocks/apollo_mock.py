"""
Apollo.io API transport mock.

Returns stable, realistic search and enrichment responses.
Person IDs are fixed so dedupe tests can assert no duplicate rows.
Captures the ICP params used in the search call for assertion.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import respx
from httpx import Request, Response

# Must match ApolloAdapter.base_url exactly (app/integrations/apollo.py).
# This was "/v1" while the adapter calls "/api/v1", so every sourcing run
# raised RESPX AllMockedAssertionError and the Celery task retried instead
# of returning leads.
APOLLO_BASE = "https://api.apollo.io/api/v1"

# Fixed personas matching the ICP produced by Phase 2 (see anthropic_mock.py)
PEOPLE: list[dict[str, Any]] = [
    {
        "id": "apollo_person_001",
        "first_name": "Alice",
        "last_name": "Chen",
        "email": "alice.chen@saasco.io",
        "title": "VP Sales",
        "organization_name": "SaaSCo",
        "organization": {
            "id": "apollo_org_001",
            "name": "SaaSCo",
            "num_employees": 45,
            "industry": "SaaS",
            "annual_revenue": 8_000_000,
        },
        "phone_numbers": [{"raw_number": "+14155550101", "type": "work"}],
    },
    {
        "id": "apollo_person_002",
        "first_name": "Ben",
        "last_name": "Torres",
        "email": "ben@growthagency.com",
        "title": "Founder",
        "organization_name": "GrowthAgency",
        "organization": {
            "id": "apollo_org_002",
            "name": "GrowthAgency",
            "num_employees": 12,
            "industry": "professional services",
            "annual_revenue": 1_500_000,
        },
        "phone_numbers": [],
    },
    {
        "id": "apollo_person_003",
        "first_name": "Carol",
        "last_name": "Singh",
        "email": "carol@psvc.net",
        "title": "VP Sales",
        "organization_name": "PSvc",
        "organization": {
            "id": "apollo_org_003",
            "name": "PSvc",
            "num_employees": 60,
            "industry": "professional services",
            "annual_revenue": 5_000_000,
        },
        "phone_numbers": [{"raw_number": "+14155550303", "type": "work"}],
    },
]


@dataclass
class ApolloCallCapture:
    """Records every Apollo search call so tests can assert ICP params were used."""
    search_calls: list[dict[str, Any]] = field(default_factory=list)
    enrich_calls: list[str] = field(default_factory=list)  # email addresses


_capture = ApolloCallCapture()


def get_capture() -> ApolloCallCapture:
    return _capture


def reset_capture() -> None:
    _capture.search_calls.clear()
    _capture.enrich_calls.clear()


def _people_search_handler(request: Request) -> Response:
    try:
        body = json.loads(request.content)
    except Exception:
        body = {}
    _capture.search_calls.append(body)
    return Response(200, json={
        "people": PEOPLE,
        "pagination": {"page": 1, "per_page": 25, "total_entries": len(PEOPLE), "total_pages": 1},
    })


def _enrich_handler(request: Request) -> Response:
    try:
        body = json.loads(request.content)
    except Exception:
        body = {}
    email = body.get("email", "")
    _capture.enrich_calls.append(email)
    person = next((p for p in PEOPLE if p["email"] == email), PEOPLE[0])
    return Response(200, json={"person": person})


def register(router: respx.MockRouter) -> None:
    """Register Apollo routes on the given respx router."""
    router.post(f"{APOLLO_BASE}/mixed_people/search").mock(side_effect=_people_search_handler)
    router.post(f"{APOLLO_BASE}/people/match").mock(side_effect=_enrich_handler)
    # Bulk enrichment endpoint
    router.post(f"{APOLLO_BASE}/people/bulk_match").mock(side_effect=_enrich_handler)

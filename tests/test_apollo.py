"""Apollo adapter — ICP translation, capped pagination, mapping, caching."""

import json

import httpx

from app.integrations.apollo import ApolloAdapter, icp_to_apollo_params

ICP = {
    "titles": ["Owner", "Operations Manager"],
    "industries": ["fire protection services"],
    "locations": ["Texas, US"],
    "company_size_ranges": ["11,50"],
    "keywords": ["fire inspection", "NFPA"],
}


def make_apollo(fake_redis, handler) -> ApolloAdapter:
    return ApolloAdapter(
        api_key="test-apollo-key",
        redis=fake_redis,
        http=httpx.Client(base_url="https://api.apollo.io/api/v1",
                          transport=httpx.MockTransport(handler)),
        sleep=lambda s: None,
    )


def person(i: int, email: str | None = None) -> dict:
    return {
        "id": f"ap_{i}",
        "name": f"Person {i}",
        "first_name": "Person",
        "last_name": str(i),
        "title": "Owner",
        "email": email,
        "organization": {"name": f"Acme {i}", "primary_domain": f"acme{i}.com"},
        "phone_numbers": [{"sanitized_number": f"+1555000{i:04d}"}],
    }


class TestIcpTranslation:
    def test_full_mapping(self):
        params = icp_to_apollo_params(ICP)
        assert params["person_titles"] == ["Owner", "Operations Manager"]
        assert params["person_locations"] == ["Texas, US"]
        assert params["organization_num_employees_ranges"] == ["11,50"]
        assert params["q_organization_keyword_tags"] == ["fire protection services"]
        assert params["q_keywords"] == "fire inspection NFPA"

    def test_missing_keys_are_omitted_not_invented(self):
        assert icp_to_apollo_params({}) == {}
        assert icp_to_apollo_params({"titles": ["CEO"]}) == {"person_titles": ["CEO"]}


class TestSearch:
    def test_pagination_respects_max_leads_cap(self, fake_redis):
        pages_served = []

        served = {"n": 0}

        def handler(request):
            body = json.loads(request.content)
            pages_served.append((body["page"], body["per_page"]))
            start = served["n"]
            served["n"] += body["per_page"]
            return httpx.Response(200, json={
                "people": [person(start + i) for i in range(body["per_page"])],
                "pagination": {"total_pages": 99},
            })

        adapter = make_apollo(fake_redis, handler)
        leads = adapter.search(ICP, max_leads=60)  # page size settings default 25

        assert len(leads) == 60
        assert pages_served == [(1, 25), (2, 25), (3, 10)], \
            "last page requests only the remainder — never over-fetches paid results"
        assert len({l.external_id for l in leads}) == 60

    def test_stops_when_provider_runs_out(self, fake_redis):
        def handler(request):
            body = json.loads(request.content)
            people = [person(i) for i in range(7)] if body["page"] == 1 else []
            return httpx.Response(200, json={"people": people,
                                             "pagination": {"total_pages": 1}})

        adapter = make_apollo(fake_redis, handler)
        assert len(adapter.search(ICP, max_leads=50)) == 7

    def test_auth_header_sent(self, fake_redis):
        seen = {}

        def handler(request):
            seen["key"] = request.headers.get("X-Api-Key")
            return httpx.Response(200, json={"people": [], "pagination": {"total_pages": 1}})

        make_apollo(fake_redis, handler).search(ICP, max_leads=5)
        assert seen["key"] == "test-apollo-key"


class TestMapping:
    def test_locked_email_placeholder_becomes_none(self, fake_redis):
        def handler(request):
            return httpx.Response(200, json={
                "people": [person(1, email="email_not_unlocked@domain.com"),
                           person(2, email="real@acme2.com")],
                "pagination": {"total_pages": 1},
            })

        leads = make_apollo(fake_redis, handler).search(ICP, max_leads=5)
        assert leads[0].email is None, "locked placeholder must not be treated as an email"
        assert leads[1].email == "real@acme2.com"
        assert leads[0].company_domain == "acme1.com"
        assert leads[0].phone == "+15550000001"


class TestEnrichment:
    def test_enrichment_cached_never_pay_twice(self, fake_redis):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, json={"person": person(1, email="p1@acme1.com")})

        adapter = make_apollo(fake_redis, handler)
        raw = adapter._to_raw_lead(person(1))

        first = adapter.enrich(raw)
        second = adapter.enrich(raw)
        assert calls["n"] == 1, "second enrichment must be a cache hit"
        assert first.email == second.email == "p1@acme1.com"
        assert first.enrichment  # full raw response stored

    def test_enrich_never_loses_known_fields(self, fake_redis):
        def handler(request):
            return httpx.Response(200, json={"person": {}})  # provider knows nothing

        adapter = make_apollo(fake_redis, handler)
        raw = adapter._to_raw_lead(person(3, email="keep@acme3.com"))
        enriched = adapter.enrich(raw)
        assert enriched.email == "keep@acme3.com"
        assert enriched.external_id == "ap_3"
        assert enriched.company == "Acme 3"

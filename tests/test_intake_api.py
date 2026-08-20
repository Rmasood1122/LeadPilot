"""Intake flow API — happy paths, validation errors, flow inference."""

import uuid

PRODUCT = {
    "user_email": "rehan@leadpilot.dev",
    "name": "SEO System X",
    "description": "Local SEO audits for fire protection companies",
    "type": "skill",
}

CLIENTS = {
    "clients": [
        {
            "details": "Texas fire ITM company, 30 staff, $4M revenue",
            "acquisition_story": "Referral from an inspector after a failed audit",
        },
        {
            "details": "Georgia sprinkler contractor, 12 staff",
            "acquisition_story": "Cold email citing their expired certification",
        },
    ]
}


def _create_product(client) -> str:
    r = client.post("/products", json=PRODUCT)
    assert r.status_code == 201, r.text
    return r.json()["id"]


class TestProducts:
    def test_create_product_happy_path(self, client):
        r = client.post("/products", json=PRODUCT)
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == "SEO System X"
        assert body["type"] == "skill"
        assert uuid.UUID(body["id"])

    def test_create_product_validation_errors(self, client):
        assert client.post("/products", json={}).status_code == 422
        assert client.post("/products", json={**PRODUCT, "type": "banana"}).status_code == 422
        assert client.post("/products", json={**PRODUCT, "user_email": "not-an-email"}).status_code == 422
        assert client.post("/products", json={**PRODUCT, "name": ""}).status_code == 422

    def test_get_product_404(self, client):
        assert client.get(f"/products/{uuid.uuid4()}").status_code == 404


class TestPastClients:
    def test_add_past_clients_extracts_patterns(self, client, fake_claude):
        pid = _create_product(client)
        r = client.post(f"/products/{pid}/past-clients", json=CLIENTS)
        assert r.status_code == 201
        body = r.json()
        assert len(body) == 2
        for c in body:
            patterns = c["extracted_patterns_json"]
            assert patterns["industry"] == "fire protection"
            assert patterns["acquisition_channel"] == "referral"

    def test_empty_client_list_rejected(self, client):
        pid = _create_product(client)
        assert client.post(f"/products/{pid}/past-clients", json={"clients": []}).status_code == 422

    def test_unknown_product_404(self, client):
        assert client.post(f"/products/{uuid.uuid4()}/past-clients", json=CLIENTS).status_code == 404


class TestStrategies:
    def test_flow_inferred_no_clients(self, client, enqueued):
        pid = _create_product(client)
        r = client.post(f"/products/{pid}/strategies", json={})
        assert r.status_code == 202
        body = r.json()
        assert body["flow_type"] == "no_clients"
        assert body["status"] == "pending"
        assert enqueued == [body["id"]], "pipeline enqueued exactly once"

    def test_flow_inferred_with_clients(self, client, enqueued):
        pid = _create_product(client)
        client.post(f"/products/{pid}/past-clients", json=CLIENTS)
        r = client.post(f"/products/{pid}/strategies", json={})
        assert r.status_code == 202
        assert r.json()["flow_type"] == "with_clients"
        assert len(enqueued) == 1

    def test_explicit_with_clients_without_clients_rejected(self, client, enqueued):
        pid = _create_product(client)
        r = client.post(f"/products/{pid}/strategies", json={"flow_type": "with_clients"})
        assert r.status_code == 422
        assert enqueued == []

    def test_unknown_product_404(self, client):
        assert client.post(f"/products/{uuid.uuid4()}/strategies", json={}).status_code == 404


class TestStrategyStatus:
    def test_status_shape_flow1(self, client):
        pid = _create_product(client)
        client.post(f"/products/{pid}/past-clients", json=CLIENTS)
        sid = client.post(f"/products/{pid}/strategies", json={}).json()["id"]

        r = client.get(f"/strategies/{sid}")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "pending"
        assert len(body["progress"]) == 1  # strategy pipeline only
        strat = body["progress"][0]
        assert strat["total"] == 72 and strat["done"] == 0
        assert len(strat["phases"]) == 8
        assert all(p["total"] == 9 for p in strat["phases"])
        assert body["strategy_document_ready"] is False

    def test_status_shape_flow2_has_two_pipelines(self, client):
        pid = _create_product(client)
        sid = client.post(f"/products/{pid}/strategies", json={}).json()["id"]
        body = client.get(f"/strategies/{sid}").json()
        assert [p["pipeline"] for p in body["progress"]] == ["strategy", "gtm"]

    def test_unknown_strategy_404(self, client):
        assert client.get(f"/strategies/{uuid.uuid4()}").status_code == 404

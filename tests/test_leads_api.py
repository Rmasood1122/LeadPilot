"""Lead API — sourcing gate, listing, detail, GDPR delete semantics."""

import uuid

from sqlalchemy import select

from app.db import models as m
from app.workers.lead_tasks import source_leads_impl
from tests.conftest import FakeLeadSource, make_raw


def seed_leads(db, strategy, n=5, status=m.LeadStatus.VERIFIED):
    leads = []
    for i in range(n):
        lead = m.Lead(
            strategy_id=strategy.id, source="apollo", external_id=f"seed{i}",
            full_name=f"Seed {i}", title="Owner", company=f"Co {i}",
            email=f"seed{i}@co{i}.com", phone=f"+1555{i:07d}",
            enrichment_json={"k": i}, status=status,
        )
        db.add(lead)
        leads.append(lead)
    db.commit()
    return leads


class TestSourceEndpoint:
    def test_rejects_unverified_strategy(self, leads_client, db_session,
                                         product_with_strategy, chain_calls):
        _, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)  # status: pending
        r = leads_client.post(f"/strategies/{strategy.id}/leads/source", json={})
        assert r.status_code == 409
        assert "verification passes" in r.json()["detail"]
        assert chain_calls == [], "chain must not be enqueued for unverified strategies"

    def test_verified_strategy_creates_batch_and_enqueues_chain(
        self, leads_client, db_session, verified_strategy, chain_calls
    ):
        r = leads_client.post(f"/strategies/{verified_strategy.id}/leads/source",
                              json={"max_leads": 40})
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["stage"] == "sourcing"
        assert body["requested_leads"] == 40
        # No explicit criteria -> extracted from research (FakeClaude)
        assert body["icp_criteria_json"]["titles"] == ["Owner", "Operations Manager"]
        assert chain_calls == [body["id"]]

    def test_explicit_criteria_used_verbatim(self, leads_client, verified_strategy):
        criteria = {"titles": ["CTO"], "industries": [], "locations": ["Berlin, DE"],
                    "company_size_ranges": [], "keywords": []}
        r = leads_client.post(f"/strategies/{verified_strategy.id}/leads/source",
                              json={"icp_criteria": criteria})
        assert r.json()["icp_criteria_json"] == criteria

    def test_max_leads_capped_by_settings(self, leads_client, verified_strategy):
        r = leads_client.post(f"/strategies/{verified_strategy.id}/leads/source",
                              json={"max_leads": 1000})
        assert r.json()["requested_leads"] == 200  # LEADS_MAX_PER_RUN default

    def test_unknown_strategy_404(self, leads_client):
        assert leads_client.post(f"/strategies/{uuid.uuid4()}/leads/source",
                                 json={}).status_code == 404


class TestListAndDetail:
    def test_list_pagination_and_total(self, leads_client, db_session, verified_strategy):
        seed_leads(db_session, verified_strategy, n=7)
        r = leads_client.get(f"/strategies/{verified_strategy.id}/leads?limit=3&offset=3")
        body = r.json()
        assert body["total"] == 7
        assert len(body["items"]) == 3
        assert body["items"][0]["full_name"] == "Seed 3"

    def test_list_filters_by_status(self, leads_client, db_session, verified_strategy):
        seed_leads(db_session, verified_strategy, n=2, status=m.LeadStatus.VERIFIED)
        seed_leads_dropped = m.Lead(strategy_id=verified_strategy.id, source="apollo",
                                    external_id="dropped1", email="d@d.com",
                                    status=m.LeadStatus.DROPPED)
        db_session.add(seed_leads_dropped)
        db_session.commit()
        r = leads_client.get(f"/strategies/{verified_strategy.id}/leads?status=verified")
        body = r.json()
        assert body["total"] == 2
        assert all(item["status"] == "verified" for item in body["items"])

    def test_detail_includes_enrichment(self, leads_client, db_session, verified_strategy):
        lead = seed_leads(db_session, verified_strategy, n=1)[0]
        body = leads_client.get(f"/leads/{lead.id}").json()
        assert body["enrichment_json"] == {"k": 0}
        assert body["external_id"] == "seed0"
        assert body["strategy_id"] == str(verified_strategy.id)

    def test_404s(self, leads_client):
        assert leads_client.get(f"/strategies/{uuid.uuid4()}/leads").status_code == 404
        assert leads_client.get(f"/leads/{uuid.uuid4()}").status_code == 404


class TestGdprDelete:
    def test_delete_erases_personal_data_and_writes_tombstones(
        self, leads_client, db_session, verified_strategy
    ):
        lead = seed_leads(db_session, verified_strategy, n=1)[0]
        email, phone = lead.email, lead.phone

        assert leads_client.delete(f"/leads/{lead.id}").status_code == 204

        db_session.refresh(lead)
        assert lead.full_name is None and lead.title is None
        assert lead.email is None and lead.phone is None and lead.company is None
        assert lead.enrichment_json == {"gdpr_deleted": True}
        assert lead.status is m.LeadStatus.DROPPED
        assert lead.external_id == "seed0", "non-personal tombstone remains"

        suppressed = db_session.execute(select(m.SuppressionEntry)).scalars().all()
        assert {(s.email, s.phone, s.reason) for s in suppressed} == {
            (email, None, "gdpr_delete"), (None, phone, "gdpr_delete"),
        }

    def test_deleted_lead_is_never_resourced(self, leads_client, db_session, verified_strategy):
        lead = seed_leads(db_session, verified_strategy, n=1)[0]
        email = lead.email
        leads_client.delete(f"/leads/{lead.id}")

        batch = m.LeadBatch(strategy_id=verified_strategy.id, requested_leads=10,
                            source_provider="fakesource", verifier_provider="fakeverifier")
        db_session.add(batch)
        db_session.commit()

        source = FakeLeadSource(feed=[make_raw(99, email=email)])
        counts = source_leads_impl(db_session, batch.id, source=source)
        assert counts == {"added": 0, "duplicates": 0, "suppressed": 1}, \
            "the suppression tombstone blocks re-sourcing, no exceptions"

    def test_delete_unknown_lead_404(self, leads_client):
        assert leads_client.delete(f"/leads/{uuid.uuid4()}").status_code == 404

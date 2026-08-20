"""Lead-sourcing chain — dedupe, suppression, resumability, status flow."""

import pytest
from sqlalchemy import select

from app.db import models as m
from app.integrations.base import EmailVerificationStatus
from app.workers.lead_tasks import (
    enrich_leads_impl,
    finalize_lead_batch_impl,
    find_missing_emails_impl,
    is_suppressed,
    source_leads_impl,
    verify_emails_impl,
)
from tests.conftest import FakeLeadSource, make_raw


def batch_leads(db, batch):
    return db.execute(select(m.Lead).where(m.Lead.batch_id == batch.id)
                      .order_by(m.Lead.external_id)).scalars().all()


class TestSourcing:
    def test_happy_path_inserts_sourced_leads(self, db_session, lead_batch, fake_source):
        fake_source.feed = [make_raw(1, email="p1@acme1.com"),
                            make_raw(2, domain="acme2.com"),
                            make_raw(3)]
        counts = source_leads_impl(db_session, lead_batch.id, source=fake_source)
        assert counts == {"added": 3, "duplicates": 0, "suppressed": 0}
        leads = batch_leads(db_session, lead_batch)
        assert [l.status for l in leads] == [m.LeadStatus.SOURCED] * 3
        assert leads[1].enrichment_json["company_domain"] == "acme2.com"
        assert lead_batch.stage is m.BatchStage.SOURCING

    def test_dedupe_same_lead_sourced_twice_is_one_row(self, db_session, lead_batch, fake_source):
        fake_source.feed = [make_raw(1, email="p1@acme1.com"), make_raw(2)]
        first = source_leads_impl(db_session, lead_batch.id, source=fake_source)
        second = source_leads_impl(db_session, lead_batch.id, source=fake_source)
        assert first["added"] == 2
        assert second == {"added": 0, "duplicates": 2, "suppressed": 0}
        assert len(batch_leads(db_session, lead_batch)) == 2

    def test_dedupe_by_email_across_different_external_ids(self, db_session, lead_batch, fake_source):
        fake_source.feed = [make_raw(1, email="same@acme.com"),
                            make_raw(2, email="same@acme.com")]
        counts = source_leads_impl(db_session, lead_batch.id, source=fake_source)
        assert counts["added"] == 1 and counts["duplicates"] == 1

    def test_suppressed_leads_excluded_at_sourcing_time(self, db_session, lead_batch, fake_source):
        db_session.add(m.SuppressionEntry(email="optout@acme1.com", reason="unsubscribed"))
        db_session.add(m.SuppressionEntry(phone="+15550009999", reason="unsubscribed"))
        db_session.commit()
        fake_source.feed = [make_raw(1, email="optout@acme1.com"),
                            make_raw(2, phone="+15550009999"),
                            make_raw(3, email="fine@acme3.com")]
        counts = source_leads_impl(db_session, lead_batch.id, source=fake_source)
        assert counts == {"added": 1, "duplicates": 0, "suppressed": 2}
        leads = batch_leads(db_session, lead_batch)
        assert len(leads) == 1 and leads[0].email == "fine@acme3.com"

    def test_is_suppressed_normalizes_email_case(self, db_session):
        db_session.add(m.SuppressionEntry(email="x@y.com", reason="gdpr_delete"))
        db_session.commit()
        assert is_suppressed(db_session, email="X@Y.COM ".strip() if True else None) or \
               is_suppressed(db_session, email="X@Y.com")


class TestEnrichment:
    def test_enrich_advances_status_and_stores_payload(self, db_session, lead_batch, fake_source):
        fake_source.feed = [make_raw(1, email="p1@acme1.com"), make_raw(2)]
        source_leads_impl(db_session, lead_batch.id, source=fake_source)
        processed = enrich_leads_impl(db_session, lead_batch.id, source=fake_source)
        assert processed == 2
        for lead in batch_leads(db_session, lead_batch):
            assert lead.status is m.LeadStatus.ENRICHED
            assert lead.enrichment_json["company_domain"]
            assert lead.enrichment_json["enrichment"] == {"provider": "fakesource"}

    def test_resume_crash_mid_enrichment_no_duplicate_work(self, db_session, lead_batch, fake_source):
        fake_source.feed = [make_raw(i) for i in range(6)]
        source_leads_impl(db_session, lead_batch.id, source=fake_source)

        fake_source.enrich_fail_after = 3  # crash on the 4th enrich call
        with pytest.raises(RuntimeError):
            enrich_leads_impl(db_session, lead_batch.id, source=fake_source)
        db_session.rollback()

        done = [l for l in batch_leads(db_session, lead_batch) if l.status is m.LeadStatus.ENRICHED]
        assert len(done) == 3, "the 3 committed leads survive the crash"

        fake_source.enrich_fail_after = None
        enrich_leads_impl(db_session, lead_batch.id, source=fake_source)
        assert all(l.status is m.LeadStatus.ENRICHED for l in batch_leads(db_session, lead_batch))
        assert fake_source.enrich_calls == 6, "already-enriched leads are never re-paid for"

    def test_enrichment_discovering_suppressed_email_drops_lead(
        self, db_session, lead_batch, fake_source, monkeypatch
    ):
        db_session.add(m.SuppressionEntry(email="hidden@acme1.com", reason="unsubscribed"))
        db_session.commit()
        fake_source.feed = [make_raw(1)]
        source_leads_impl(db_session, lead_batch.id, source=fake_source)

        original = fake_source.enrich
        def enrich_with_email(lead):
            e = original(lead)
            e.email = "hidden@acme1.com"
            return e
        monkeypatch.setattr(fake_source, "enrich", enrich_with_email)

        enrich_leads_impl(db_session, lead_batch.id, source=fake_source)
        lead = batch_leads(db_session, lead_batch)[0]
        assert lead.status is m.LeadStatus.DROPPED
        assert lead.enrichment_json["dropped_reason"] == "suppressed"


class TestEmailFindingAndVerification:
    def _through_enrichment(self, db, batch, source):
        source_leads_impl(db, batch.id, source=source)
        enrich_leads_impl(db, batch.id, source=source)

    def test_missing_emails_found_or_dropped(self, db_session, lead_batch, fake_source, fake_verifier):
        fake_source.feed = [make_raw(1, email="has@acme1.com"), make_raw(2), make_raw(3)]
        fake_verifier.findable[("Person 3", "acme3.com")] = None  # finder strikes out
        self._through_enrichment(db_session, lead_batch, fake_source)

        counts = find_missing_emails_impl(db_session, lead_batch.id, verifier=fake_verifier)
        assert counts == {"found": 1, "already_had": 1, "dropped": 1}
        leads = {l.external_id: l for l in batch_leads(db_session, lead_batch)}
        assert leads["p1"].status is m.LeadStatus.EMAIL_FOUND
        assert leads["p2"].status is m.LeadStatus.EMAIL_FOUND
        assert leads["p2"].email == "person.2@acme2.com"
        assert leads["p3"].status is m.LeadStatus.DROPPED
        assert leads["p3"].enrichment_json["dropped_reason"] == "no_email_found"

    def test_verification_maps_statuses(self, db_session, lead_batch, fake_source, fake_verifier):
        fake_source.feed = [make_raw(1, email="good@a1.com"),
                            make_raw(2, email="maybe@a2.com"),
                            make_raw(3, email="dead@a3.com")]
        fake_verifier.verdicts = {
            "maybe@a2.com": EmailVerificationStatus.RISKY,
            "dead@a3.com": EmailVerificationStatus.UNDELIVERABLE,
        }
        self._through_enrichment(db_session, lead_batch, fake_source)
        find_missing_emails_impl(db_session, lead_batch.id, verifier=fake_verifier)

        counts = verify_emails_impl(db_session, lead_batch.id, verifier=fake_verifier)
        assert counts == {"verified": 1, "flagged": 1, "dropped": 1}
        leads = {l.email or l.external_id: l for l in batch_leads(db_session, lead_batch)}
        assert leads["good@a1.com"].status is m.LeadStatus.VERIFIED
        assert leads["maybe@a2.com"].status is m.LeadStatus.FLAGGED
        assert leads["dead@a3.com"].status is m.LeadStatus.DROPPED
        assert leads["good@a1.com"].enrichment_json["verification"]["status"] == "deliverable"

    def test_verify_is_resumable_by_status(self, db_session, lead_batch, fake_source, fake_verifier):
        fake_source.feed = [make_raw(1, email="a@a1.com"), make_raw(2, email="b@a2.com")]
        self._through_enrichment(db_session, lead_batch, fake_source)
        find_missing_emails_impl(db_session, lead_batch.id, verifier=fake_verifier)
        verify_emails_impl(db_session, lead_batch.id, verifier=fake_verifier)
        again = verify_emails_impl(db_session, lead_batch.id, verifier=fake_verifier)
        assert again == {"verified": 0, "flagged": 0, "dropped": 0}
        assert fake_verifier.verify_calls == 2, "verified leads are never re-verified"


class TestFinalize:
    def test_full_chain_and_summary(self, db_session, lead_batch, fake_source, fake_verifier):
        fake_source.feed = [make_raw(1, email="a@a1.com"), make_raw(2), make_raw(3)]
        fake_verifier.findable[("Person 3", "acme3.com")] = None

        source_leads_impl(db_session, lead_batch.id, source=fake_source)
        enrich_leads_impl(db_session, lead_batch.id, source=fake_source)
        find_missing_emails_impl(db_session, lead_batch.id, verifier=fake_verifier)
        verify_emails_impl(db_session, lead_batch.id, verifier=fake_verifier)
        summary = finalize_lead_batch_impl(db_session, lead_batch.id)

        assert lead_batch.stage is m.BatchStage.FINALIZED
        assert summary["total"] == 3
        assert summary["counts"]["verified"] == 2
        assert summary["counts"]["dropped"] == 1

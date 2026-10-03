"""Part 1 Feature 10 — data provenance tags.

The properties that matter:
  * the confidence belongs to the SOURCE and is a documented constant, not
    model output,
  * age is reported SEPARATELY from source quality, because they need
    different fixes,
  * "never recorded" and "unknown source" are different answers,
  * the sourcing pipeline tags what it actually filled, and nothing else.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.services import provenance
from tests.conftest import auth_headers, make_raw

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def lead(db_session, verified_strategy):
    row = m.Lead(strategy_id=verified_strategy.id, source="apollo", external_id="PV1",
                 full_name="Sara Khan", title="Owner", company="Blaze Safety",
                 email="sara@blaze.test", status=m.LeadStatus.VERIFIED,
                 enrichment_json={"company_domain": "blaze.test",
                                  "person": {"organization": {
                                      "industry": "fire protection services",
                                      "estimated_num_employees": 30,
                                      "city": "Austin"}}})
    db_session.add(row)
    db_session.commit()
    return row


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------


class TestSources:
    def test_every_source_has_a_confidence_and_a_justification(self):
        for source, (confidence, note) in provenance.SOURCES.items():
            assert 0.0 <= confidence <= 1.0, source
            assert note.endswith("."), source

    def test_every_source_has_a_human_label(self):
        assert set(provenance.SOURCE_LABELS) == set(provenance.SOURCES)

    def test_a_typed_value_outranks_a_guessed_one(self):
        """The whole point: these are not all the same claim."""
        assert (provenance.source_confidence(provenance.MANUAL)
                > provenance.source_confidence(provenance.APOLLO)
                > provenance.source_confidence(provenance.HUNTER_PATTERN)
                > provenance.source_confidence(provenance.INFERRED))

    def test_a_verified_email_outranks_a_risky_one(self):
        assert (provenance.source_confidence(provenance.HUNTER_VERIFIED)
                > provenance.source_confidence(provenance.HUNTER_RISKY))

    def test_an_unknown_source_is_treated_as_inferred_not_as_certain(self):
        """The safe direction when something wrote a field without saying
        what it was."""
        assert (provenance.source_confidence("mystery")
                == provenance.source_confidence(provenance.INFERRED))

    def test_an_unknown_source_still_renders_a_label(self):
        assert provenance.source_label("some_new_provider") == "Some New Provider"


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


class TestRecord:
    def test_a_tag_carries_the_source_default(self, db_session, lead):
        entry = provenance.record(db_session, lead, "title", provenance.APOLLO)
        assert entry["source"] == provenance.APOLLO
        assert entry["confidence"] == provenance.source_confidence(provenance.APOLLO)

    def test_an_explicit_confidence_wins_when_the_caller_knows_better(
            self, db_session, lead):
        entry = provenance.record(db_session, lead, "email",
                                  provenance.HUNTER_VERIFIED, confidence=0.99)
        assert entry["confidence"] == 0.99

    def test_an_out_of_range_confidence_is_clamped_not_stored(self, db_session, lead):
        """A confidence above 1 is a bug that would otherwise render as
        '140% sure'."""
        assert provenance.record(db_session, lead, "title", provenance.APOLLO,
                                 confidence=1.4)["confidence"] == 1.0
        assert provenance.record(db_session, lead, "title", provenance.APOLLO,
                                 confidence=-2)["confidence"] == 0.0

    def test_the_value_is_snapshotted(self, db_session, lead):
        """So 'this title came from Apollo' can be checked against a title
        someone has since edited by hand."""
        entry = provenance.record(db_session, lead, "title", provenance.APOLLO,
                                  value="Operations Manager")
        assert entry["value"] == "Operations Manager"

    def test_re_tagging_replaces_rather_than_appends(self, db_session, lead):
        provenance.record(db_session, lead, "email", provenance.HUNTER_PATTERN)
        provenance.record(db_session, lead, "email", provenance.HUNTER_VERIFIED)
        assert lead.provenance_json["email"]["source"] == provenance.HUNTER_VERIFIED
        assert len(lead.provenance_json) == 1

    def test_record_many_takes_one_write_for_many_fields(self, db_session, lead):
        provenance.record_many(db_session, lead, {
            "title": provenance.APOLLO,
            "email": {"source": provenance.HUNTER_VERIFIED, "value": "a@b.test"},
        })
        assert set(lead.provenance_json) == {"title", "email"}
        assert lead.provenance_json["email"]["value"] == "a@b.test"

    def test_the_updated_at_marker_moves(self, db_session, lead):
        provenance.record(db_session, lead, "title", provenance.APOLLO, observed_at=NOW)
        assert lead.provenance_updated_at is not None


class TestRecordEnrichment:
    def test_it_tags_what_the_stage_actually_filled_and_nothing_else(
            self, db_session, lead):
        provenance.record_enrichment(db_session, lead, provenance.APOLLO)
        tagged = set(lead.provenance_json)
        assert {"full_name", "title", "company", "company_size", "industry",
                "company_domain", "location"} <= tagged
        # No phone and no LinkedIn URL on this lead, so neither is claimed.
        assert "phone" not in tagged
        assert "linkedin_url" not in tagged

    def test_it_never_raises_into_the_sourcing_chain(self, db_session, lead,
                                                     monkeypatch):
        monkeypatch.setattr(provenance, "record_many",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        assert provenance.record_enrichment(db_session, lead, provenance.APOLLO) == {}

    @pytest.mark.parametrize("status,source", [
        ("valid", provenance.HUNTER_VERIFIED),
        ("deliverable", provenance.HUNTER_VERIFIED),
        ("risky", provenance.HUNTER_RISKY),
        ("accept_all", provenance.HUNTER_RISKY),
        ("unknown", provenance.HUNTER_PATTERN),
    ])
    def test_each_verifier_verdict_is_its_own_source(self, db_session, lead,
                                                     status, source):
        """Three verdicts, three claims: checked, warned about, never checked."""
        entry = provenance.record_email_verification(db_session, lead, status)
        assert entry["source"] == source


# --------------------------------------------------------------------------
# Age
# --------------------------------------------------------------------------


class TestStaleness:
    def test_age_is_reported_separately_from_source_quality(self, db_session, lead):
        """Multiplying them into one number hides which is the problem, and
        they need different fixes: a weak source needs a better source, an old
        fact needs a refresh."""
        provenance.record(db_session, lead, "company_size", provenance.APOLLO,
                          observed_at=NOW - timedelta(days=400))
        item = provenance.for_lead(lead, now=NOW)["items"][0]
        assert item["confidence"] == provenance.source_confidence(provenance.APOLLO)
        assert item["staleness"]["band"] == "very_stale"

    @pytest.mark.parametrize("days,band", [
        (0, "fresh"), (89, "fresh"), (90, "stale"), (364, "stale"),
        (365, "very_stale"),
    ])
    def test_bands(self, days, band):
        assert provenance.staleness(NOW - timedelta(days=days), NOW)["band"] == band

    def test_an_unknown_date_is_unknown_not_fresh(self):
        assert provenance.staleness(None, NOW) == {"days": None, "band": "unknown"}


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


class TestForLead:
    def test_never_recorded_is_distinguishable_from_unknown_source(
            self, db_session, lead):
        out = provenance.for_lead(lead, now=NOW)
        assert out["tracked"] is False
        assert out["items"] == []
        assert out["weakest"] is None

    def test_the_weakest_field_comes_first(self, db_session, lead):
        """The list exists to answer 'what here should I not rely on?', and
        alphabetical order buries that under Company and Email."""
        provenance.record_many(db_session, lead, {
            "title": provenance.MANUAL,
            "company_size": provenance.INFERRED,
            "email": provenance.APOLLO,
        }, observed_at=NOW)
        out = provenance.for_lead(lead, now=NOW)
        assert out["items"][0]["field"] == "company_size"
        assert out["weakest"]["field"] == "company_size"

    def test_stale_fields_are_counted(self, db_session, lead):
        provenance.record(db_session, lead, "title", provenance.APOLLO,
                          observed_at=NOW - timedelta(days=200))
        provenance.record(db_session, lead, "email", provenance.APOLLO,
                          observed_at=NOW)
        assert provenance.for_lead(lead, now=NOW)["stale_count"] == 1

    def test_every_item_carries_the_reason_to_trust_it_or_not(self, db_session, lead):
        provenance.record(db_session, lead, "title", provenance.HUNTER_PATTERN)
        item = provenance.for_lead(lead, now=NOW)["items"][0]
        assert item["source_label"] == "Guessed pattern"
        assert "never verified" in item["source_note"]

    def test_a_corrupt_entry_is_skipped_rather_than_crashing_the_page(
            self, db_session, lead):
        lead.provenance_json = {"title": "not a dict", "email": {"source": "apollo"}}
        db_session.commit()
        out = provenance.for_lead(lead, now=NOW)
        assert [i["field"] for i in out["items"]] == ["email"]

    def test_field_out_is_none_for_an_untracked_field(self, db_session, lead):
        assert provenance.field_out(lead, "title", now=NOW) is None


# --------------------------------------------------------------------------
# The pipeline
# --------------------------------------------------------------------------


class TestPipeline:
    def test_enrichment_tags_the_fields_it_fills(self, db_session, lead_batch,
                                                 fake_source, monkeypatch):
        from app.workers import lead_tasks

        monkeypatch.setattr(lead_tasks, "_get_source", lambda batch: fake_source)
        fake_source.feed = [make_raw(1, email="p1@acme1.com"), make_raw(2)]
        lead_tasks.source_leads_impl(db_session, lead_batch.id, fake_source)
        lead_tasks.enrich_leads_impl(db_session, lead_batch.id, fake_source)
        leads = db_session.query(m.Lead).filter_by(batch_id=lead_batch.id).all()
        assert leads
        assert all(row.provenance_json for row in leads)
        # The tag names the provider that actually filled it -- whatever that
        # provider is called -- rather than a hardcoded "apollo".
        assert all(row.provenance_json["full_name"]["source"] == row.source
                   for row in leads)
        # An unrecognised provider is scored as INFERRED, the safe direction.
        assert all(row.provenance_json["title"]["confidence"]
                   == provenance.source_confidence(provenance.INFERRED)
                   for row in leads)

    def test_verification_upgrades_the_email_tag(self, db_session, lead_batch,
                                                 fake_source, fake_verifier,
                                                 monkeypatch):
        from app.workers import lead_tasks

        monkeypatch.setattr(lead_tasks, "_get_source", lambda batch: fake_source)
        monkeypatch.setattr(lead_tasks, "_get_verifier", lambda batch: fake_verifier)
        fake_source.feed = [make_raw(1, email="p1@acme1.com"), make_raw(2)]
        lead_tasks.source_leads_impl(db_session, lead_batch.id, fake_source)
        lead_tasks.enrich_leads_impl(db_session, lead_batch.id, fake_source)
        lead_tasks.find_missing_emails_impl(db_session, lead_batch.id, fake_verifier)
        lead_tasks.verify_emails_impl(db_session, lead_batch.id, fake_verifier)
        verified = db_session.query(m.Lead).filter_by(
            batch_id=lead_batch.id, status=m.LeadStatus.VERIFIED).all()
        assert verified
        assert all(row.provenance_json["email"]["source"]
                   in (provenance.HUNTER_VERIFIED, provenance.HUNTER_RISKY)
                   for row in verified)


class TestApi:
    def test_the_endpoint_returns_the_tags(self, client, db_session, lead, test_user):
        provenance.record(db_session, lead, "title", provenance.APOLLO,
                          value="Owner", observed_at=NOW)
        response = client.get(f"/leads/{lead.id}/provenance",
                              headers=auth_headers(test_user))
        assert response.status_code == 200
        body = response.json()
        assert body["tracked"] is True
        assert body["items"][0]["source_label"] == "Apollo"

    def test_an_untracked_prospect_says_so(self, client, db_session, lead, test_user):
        body = client.get(f"/leads/{lead.id}/provenance",
                          headers=auth_headers(test_user)).json()
        assert body["tracked"] is False
        assert body["items"] == []

    def test_another_account_cannot_read_it(self, client, db_session, lead):
        other = m.User(email="nosy-prov@test.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        assert client.get(f"/leads/{lead.id}/provenance",
                          headers=auth_headers(other)).status_code == 404

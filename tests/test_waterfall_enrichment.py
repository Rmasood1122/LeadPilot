"""F01 -- the email waterfall in the lead pipeline.

The properties that matter:
  * the first address the independent verifier confirms wins, and nothing
    after it is called (no paying for a second opinion we do not need),
  * a bad source address falls through to the next provider instead of
    dropping a reachable person,
  * a suppressed address drops the PERSON -- we never go looking for another
    way to reach someone who opted out,
  * every attempt is in the ledger with its cost (0 for a cache hit), and the
    ledger never holds an address,
  * flag off = the legacy stages, byte for byte.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import fakeredis
import pytest
from sqlalchemy import literal_column, select

from app.db import models as m
from app.integrations.base import EmailVerificationStatus, VerificationResult
from app.services import system_settings
from app.services import waterfall_enrichment as wf
from app.workers.lead_tasks import (
    enrich_leads_impl,
    find_missing_emails_impl,
    source_leads_impl,
    verify_emails_impl,
)
from tests.conftest import FakeVerifier, make_raw

D = EmailVerificationStatus.DELIVERABLE
R = EmailVerificationStatus.RISKY
U = EmailVerificationStatus.UNDELIVERABLE


class ScriptedVerifier(FakeVerifier):
    """FakeVerifier plus a scripted raw payload per address and a scriptable
    cache answer (what plumbing reports as last_call)."""

    provider = "hunter"

    def __init__(self):
        super().__init__()
        self.raw: dict[str, dict] = {}
        self.cached: set[str] = set()
        self.last_call = None
        self.verified: list[str] = []
        self.api_key = "test-key"
        self.raise_on_verify: Exception | None = None

    def find_email(self, full_name, domain):
        email = super().find_email(full_name, domain)
        self.last_call = {"cached": False, "cost_units": 1}
        return email

    def verify(self, email):
        if self.raise_on_verify is not None:
            raise self.raise_on_verify
        result = super().verify(email)
        self.verified.append(email)
        result.raw = {**(result.raw or {}), **self.raw.get(email, {})}
        self.last_call = ({"cached": True, "cost_units": 0} if email in self.cached
                          else {"cached": False, "cost_units": 1})
        return result


@pytest.fixture()
def verifier():
    return ScriptedVerifier()


@pytest.fixture()
def waterfall_on(db_session):
    system_settings.set(db_session, "waterfall_enrichment_enabled", True)


def leads_of(db, batch):
    return {l.external_id: l for l in db.execute(
        select(m.Lead).where(m.Lead.batch_id == batch.id)).scalars()}


def attempts(db, lead=None):
    # SQLite rowid = insertion order (created_at has one-second resolution).
    q = select(m.EnrichmentAttempt).order_by(literal_column("rowid"))
    if lead is not None:
        q = q.where(m.EnrichmentAttempt.lead_id == lead.id)
    return db.execute(q).scalars().all()


def run_chain(db, batch, source, verifier):
    source_leads_impl(db, batch.id, source=source)
    enrich_leads_impl(db, batch.id, source=source)
    found = find_missing_emails_impl(db, batch.id, verifier=verifier)
    verified = verify_emails_impl(db, batch.id, verifier=verifier)
    return found, verified


# --------------------------------------------------------------------------
# Flag off: nothing changes
# --------------------------------------------------------------------------


class TestFlagOff:
    def test_defaults_are_off(self, db_session):
        assert system_settings.get(db_session, "waterfall_enrichment_enabled") is False
        assert system_settings.get(db_session, "bounce_shield_enabled") is False
        assert system_settings.get(db_session, "bounce_shield_catch_all_policy") == "block"
        assert system_settings.get(db_session, "waterfall_provider_order") == "apollo,hunter"

    def test_legacy_stages_unchanged_and_no_ledger(self, db_session, lead_batch, fake_source,
                                                   fake_verifier):
        """Same inputs and assertions as the legacy stage tests: a bad source
        address is DROPPED without trying the finder, and nothing is ledgered."""
        fake_source.feed = [make_raw(1, email="bad@acme1.com"), make_raw(2)]
        fake_verifier.verdicts["bad@acme1.com"] = U
        found, verified = run_chain(db_session, lead_batch, fake_source, fake_verifier)
        assert found == {"found": 1, "already_had": 1, "dropped": 0}
        assert verified == {"verified": 1, "flagged": 0, "dropped": 1}
        assert fake_verifier.find_calls == 1          # only for the lead with no email
        leads = leads_of(db_session, lead_batch)
        assert leads["p1"].status is m.LeadStatus.DROPPED
        assert leads["p1"].email == "bad@acme1.com"
        assert "email_verdict" not in leads["p2"].enrichment_json
        assert attempts(db_session) == []


# --------------------------------------------------------------------------
# The chain
# --------------------------------------------------------------------------


@pytest.mark.usefixtures("waterfall_on")
class TestChain:
    def test_first_verified_result_wins_and_nothing_after_is_called(
            self, db_session, lead_batch, fake_source, verifier):
        fake_source.feed = [make_raw(1, email="good@acme1.com")]
        found, verified = run_chain(db_session, lead_batch, fake_source, verifier)

        assert found == {"found": 0, "already_had": 1, "dropped": 0}
        assert verified == {"verified": 1, "flagged": 0, "dropped": 0}
        assert verifier.find_calls == 0, "Hunter's finder is never paid for"
        assert verifier.verified == ["good@acme1.com"]
        lead = leads_of(db_session, lead_batch)["p1"]
        assert lead.status is m.LeadStatus.VERIFIED
        record = lead.enrichment_json["email_verdict"]
        assert record["verdict"] == "valid" and record["provider"] == "fakesource"
        assert record["email_sha256"] == wf.email_hash("good@acme1.com")
        assert lead.enrichment_json["verification"] == {"status": "deliverable", "score": 90}

        rows = attempts(db_session, lead)
        assert [(r.step, r.operation, r.outcome, r.cost_units) for r in rows] == [
            ("apollo", "find_email", "candidate", 0),
            ("apollo", "verify", "valid", 1),
        ]

    def test_bad_source_address_falls_through_to_the_next_provider(
            self, db_session, lead_batch, fake_source, verifier):
        fake_source.feed = [make_raw(1, email="old@acme1.com")]
        verifier.verdicts["old@acme1.com"] = U
        found, verified = run_chain(db_session, lead_batch, fake_source, verifier)

        lead = leads_of(db_session, lead_batch)["p1"]
        assert lead.email == "person.1@acme1.com", "Hunter's address replaced the dead one"
        assert lead.status is m.LeadStatus.VERIFIED
        assert found == {"found": 1, "already_had": 0, "dropped": 0}
        assert verified["verified"] == 1
        assert verifier.verified == ["old@acme1.com", "person.1@acme1.com"]
        assert lead.enrichment_json["email_verdict"]["provider"] == "hunter"
        assert [(r.step, r.operation, r.outcome) for r in attempts(db_session, lead)] == [
            ("apollo", "find_email", "candidate"),
            ("apollo", "verify", "invalid"),
            ("hunter", "find_email", "candidate"),
            ("hunter", "verify", "valid"),
        ]

    def test_catch_all_is_kept_as_the_best_fallback(self, db_session, lead_batch,
                                                    fake_source, verifier):
        fake_source.feed = [make_raw(1, email="maybe@acme1.com")]
        verifier.verdicts["maybe@acme1.com"] = R
        verifier.raw["maybe@acme1.com"] = {"accept_all": True}
        verifier.verdicts["person.1@acme1.com"] = U
        run_chain(db_session, lead_batch, fake_source, verifier)

        lead = leads_of(db_session, lead_batch)["p1"]
        assert lead.email == "maybe@acme1.com"
        assert lead.status is m.LeadStatus.FLAGGED
        assert lead.enrichment_json["email_verdict"]["verdict"] == "catch_all"

    def test_every_candidate_invalid_drops_the_lead_at_verification(
            self, db_session, lead_batch, fake_source, verifier):
        fake_source.feed = [make_raw(1, email="a@acme1.com")]
        verifier.verdicts["a@acme1.com"] = U
        verifier.verdicts["person.1@acme1.com"] = U
        found, verified = run_chain(db_session, lead_batch, fake_source, verifier)
        assert verified == {"verified": 0, "flagged": 0, "dropped": 1}
        lead = leads_of(db_session, lead_batch)["p1"]
        assert lead.status is m.LeadStatus.DROPPED
        assert lead.enrichment_json["email_verdict"]["verdict"] == "invalid"

    def test_no_candidate_at_all_is_dropped_as_before(self, db_session, lead_batch,
                                                      fake_source, verifier):
        fake_source.feed = [make_raw(1)]
        verifier.findable[("Person 1", "acme1.com")] = None
        found, _ = run_chain(db_session, lead_batch, fake_source, verifier)
        assert found == {"found": 0, "already_had": 0, "dropped": 1}
        lead = leads_of(db_session, lead_batch)["p1"]
        assert lead.status is m.LeadStatus.DROPPED
        assert lead.enrichment_json["dropped_reason"] == "no_email_found"
        assert verifier.verified == []
        assert [(r.step, r.outcome, r.cost_units) for r in attempts(db_session, lead)] == [
            ("hunter", "not_found", 1)]

    def test_a_suppressed_alternative_drops_the_person_and_is_never_verified(
            self, db_session, lead_batch, fake_source, verifier):
        db_session.add(m.SuppressionEntry(email="person.1@acme1.com", reason="unsubscribed"))
        db_session.commit()
        fake_source.feed = [make_raw(1, email="old@acme1.com")]
        verifier.verdicts["old@acme1.com"] = U
        found, _ = run_chain(db_session, lead_batch, fake_source, verifier)

        lead = leads_of(db_session, lead_batch)["p1"]
        assert lead.status is m.LeadStatus.DROPPED
        assert lead.enrichment_json["dropped_reason"] == "suppressed"
        assert lead.email == "old@acme1.com", "the opted-out address is never adopted"
        assert "person.1@acme1.com" not in verifier.verified
        assert found["dropped"] == 1
        assert attempts(db_session, lead)[-1].outcome == "suppressed"

    def test_the_same_address_is_never_verified_twice(self, db_session, lead_batch,
                                                      fake_source, verifier):
        fake_source.feed = [make_raw(1, email="Person.1@acme1.com")]
        verifier.verdicts["Person.1@acme1.com"] = R
        run_chain(db_session, lead_batch, fake_source, verifier)
        assert verifier.verified == ["Person.1@acme1.com"]
        lead = leads_of(db_session, lead_batch)["p1"]
        outcomes = [(r.step, r.operation, r.outcome) for r in attempts(db_session, lead)]
        assert ("hunter", "find_email", "duplicate") in outcomes
        assert lead.status is m.LeadStatus.FLAGGED

    def test_source_label_is_recorded_but_never_trusted(self, db_session, lead_batch,
                                                        fake_source, verifier):
        raw = make_raw(1, email="claimed@acme1.com")
        raw.raw = {"id": "p1", "email_status": "verified"}
        fake_source.feed = [raw]
        verifier.verdicts["claimed@acme1.com"] = U
        verifier.verdicts["person.1@acme1.com"] = U
        run_chain(db_session, lead_batch, fake_source, verifier)
        lead = leads_of(db_session, lead_batch)["p1"]
        assert lead.status is m.LeadStatus.DROPPED, "Apollo's 'verified' is not a verdict"
        first = attempts(db_session, lead)[0]
        assert first.claimed_status == "verified"

    def test_verify_stage_never_pays_again_for_what_find_stage_checked(
            self, db_session, lead_batch, fake_source, verifier):
        fake_source.feed = [make_raw(i, email=f"p{i}@acme{i}.com") for i in range(1, 4)]
        source_leads_impl(db_session, lead_batch.id, source=fake_source)
        enrich_leads_impl(db_session, lead_batch.id, source=fake_source)
        find_missing_emails_impl(db_session, lead_batch.id, verifier=verifier)
        calls = len(verifier.verified)
        verify_emails_impl(db_session, lead_batch.id, verifier=verifier)
        assert len(verifier.verified) == calls == 3

    def test_flag_switched_on_mid_batch_verifies_once(self, db_session, lead_batch,
                                                      fake_source, verifier):
        system_settings.set(db_session, "waterfall_enrichment_enabled", False)
        fake_source.feed = [make_raw(1, email="mid@acme1.com")]
        source_leads_impl(db_session, lead_batch.id, source=fake_source)
        enrich_leads_impl(db_session, lead_batch.id, source=fake_source)
        find_missing_emails_impl(db_session, lead_batch.id, verifier=verifier)
        system_settings.set(db_session, "waterfall_enrichment_enabled", True)
        counts = verify_emails_impl(db_session, lead_batch.id, verifier=verifier)
        assert counts == {"verified": 1, "flagged": 0, "dropped": 0}
        assert verifier.verified == ["mid@acme1.com"]
        lead = leads_of(db_session, lead_batch)["p1"]
        assert [(r.step, r.outcome) for r in attempts(db_session, lead)] == [("verify", "valid")]

    def test_a_provider_error_is_ledgered_and_the_stage_retries(
            self, db_session, lead_batch, fake_source, verifier):
        fake_source.feed = [make_raw(1, email="x@acme1.com")]
        source_leads_impl(db_session, lead_batch.id, source=fake_source)
        enrich_leads_impl(db_session, lead_batch.id, source=fake_source)
        verifier.raise_on_verify = RuntimeError("Hunter 503")
        with pytest.raises(RuntimeError):
            find_missing_emails_impl(db_session, lead_batch.id, verifier=verifier)
        db_session.rollback()
        lead = leads_of(db_session, lead_batch)["p1"]
        assert lead.status is m.LeadStatus.ENRICHED, "left for the retry"
        assert [r.outcome for r in attempts(db_session, lead)] == ["candidate", "error"]

        verifier.raise_on_verify = None
        find_missing_emails_impl(db_session, lead_batch.id, verifier=verifier)
        assert leads_of(db_session, lead_batch)["p1"].status is m.LeadStatus.EMAIL_FOUND


# --------------------------------------------------------------------------
# Ledger
# --------------------------------------------------------------------------


@pytest.mark.usefixtures("waterfall_on")
class TestLedger:
    def test_cache_hits_cost_nothing(self, db_session, lead_batch, fake_source, verifier):
        fake_source.feed = [make_raw(1, email="cached@acme1.com")]
        verifier.cached.add("cached@acme1.com")
        run_chain(db_session, lead_batch, fake_source, verifier)
        row = [r for r in attempts(db_session) if r.operation == "verify"][0]
        assert row.cached is True and row.cost_units == 0

    def test_rows_hold_no_address_and_belong_to_the_strategy_owner(
            self, db_session, lead_batch, fake_source, verifier, verified_strategy):
        fake_source.feed = [make_raw(1, email="old@acme1.com")]
        verifier.verdicts["old@acme1.com"] = U
        run_chain(db_session, lead_batch, fake_source, verifier)
        product = db_session.get(m.Product, verified_strategy.product_id)
        rows = attempts(db_session)
        assert rows
        for row in rows:
            assert row.user_id == product.user_id
            assert row.strategy_id == verified_strategy.id
            assert row.batch_id == lead_batch.id
            for column in m.EnrichmentAttempt.__table__.columns:
                value = getattr(row, column.key)
                assert not (isinstance(value, str) and "@" in value), column.key
            assert row.email_domain in (None, "acme1.com")

    def test_a_fresh_verdict_on_the_lead_is_reused_without_a_call(
            self, db_session, verified_strategy, verifier):
        lead = m.Lead(strategy_id=verified_strategy.id, source="apollo", external_id="R1",
                      full_name="Re Use", email="reuse@co.com", status=m.LeadStatus.ENRICHED,
                      enrichment_json={"company_domain": "co.com"})
        db_session.add(lead)
        db_session.commit()
        wf.store_verdict(lead, verdict="valid", email="reuse@co.com", provider="apollo",
                         verifier="hunter", score=95, legacy_status="deliverable",
                         checked_at=datetime.now(timezone.utc) - timedelta(days=3))
        db_session.commit()
        ctx = wf.context_for_lead(db_session, lead)
        steps, _ = wf.configured_steps(db_session, verifier)
        result = wf.run_for_lead(db_session, lead, verifier, ctx, steps)
        assert result.verdict == "valid" and result.verified.reused
        assert verifier.verified == []

    def test_the_real_adapter_reports_paid_then_cached(self, db_session, verified_strategy):
        """Through the real HunterAdapter and plumbing (fake HTTP, fakeredis):
        the second verification of an address is a cache hit, cost 0."""
        from app.integrations.hunter import HunterAdapter

        class Http:
            calls = 0

            def request(self, method, endpoint, params=None, json=None, headers=None):
                Http.calls += 1

                class Resp:
                    status_code = 200
                    headers: dict = {}
                    text = ""

                    @staticmethod
                    def json():
                        return {"data": {"status": "valid", "result": "deliverable",
                                         "score": 97, "accept_all": False}}
                return Resp()

        adapter = HunterAdapter(api_key="k", redis=fakeredis.FakeRedis(decode_responses=True),
                                http=Http())
        lead = m.Lead(strategy_id=verified_strategy.id, source="apollo", external_id="H1",
                      full_name="Real Adapter", email="real@co.com",
                      status=m.LeadStatus.EMAIL_FOUND)
        db_session.add(lead)
        db_session.commit()
        ctx = wf.context_for_lead(db_session, lead)
        first = wf.verify_address(db_session, lead, "real@co.com", adapter, ctx,
                                  step="verify", reuse=False)
        second = wf.verify_address(db_session, lead, "real@co.com", adapter, ctx,
                                   step="verify", reuse=False)
        assert first.verdict == second.verdict == "valid"
        assert Http.calls == 1
        assert [(r.cached, r.cost_units) for r in attempts(db_session, lead)] == [
            (False, 1), (True, 0)]


# --------------------------------------------------------------------------
# Provider chain configuration
# --------------------------------------------------------------------------


class TestProviders:
    def test_unknown_and_credential_less_providers_are_disabled(self, db_session, verifier):
        system_settings.set(db_session, "waterfall_provider_order",
                            "apollo, dropcontact ,hunter")
        verifier.api_key = ""
        steps, disabled = wf.configured_steps(db_session, verifier)
        assert [s.key for s in steps] == ["apollo"]
        assert disabled == [{"key": "dropcontact", "reason": "unknown provider (no adapter)"},
                            {"key": "hunter", "reason": "no credentials"}]

    def test_the_real_hunter_adapter_without_a_key_is_disabled(self, db_session):
        from app.integrations.hunter import HunterAdapter

        adapter = HunterAdapter(api_key="", redis=fakeredis.FakeRedis(), http=object())
        steps, disabled = wf.configured_steps(db_session, adapter)
        assert [s.key for s in steps] == ["apollo"]
        assert disabled[0]["key"] == "hunter"

    def test_order_is_respected(self, db_session, verifier):
        system_settings.set(db_session, "waterfall_provider_order", "hunter,apollo")
        steps, _ = wf.configured_steps(db_session, verifier)
        assert [s.key for s in steps] == ["hunter", "apollo"]


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status,raw,expected", [
    (D, {"status": "valid"}, "valid"),
    (D, {}, "valid"),
    (D, {"status": "valid", "accept_all": True}, "catch_all"),
    (R, {"status": "accept_all"}, "catch_all"),
    (R, {"accept_all": True}, "catch_all"),
    (D, {"accept_all": True}, "catch_all"),
    (U, {}, "invalid"),
    (D, {"status": "invalid"}, "invalid"),
    (D, {"status": "disposable"}, "invalid"),
    (R, {}, "unknown"),
    (EmailVerificationStatus.UNKNOWN, {}, "unknown"),
    (D, {"status": "unknown"}, "unknown"),
    (R, {"status": "webmail"}, "unknown"),
])
def test_classification(status, raw, expected):
    assert wf.classify(VerificationResult(email="a@b.com", status=status, raw=raw)) == expected

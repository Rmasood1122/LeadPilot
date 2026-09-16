"""Part 1 Feature 2 — Fit / Problem / Timing / Access scoring.

The things that matter about a four-part score:
  * each dimension is computed from its OWN evidence (a great fit must not
    lend confidence to timing),
  * nothing is invented when there is no evidence,
  * the model can shade a score but never rewrite it,
  * a model outage degrades to the deterministic baseline instead of blocking
    an enrollment.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.services import fpta_scoring
from tests.conftest import auth_headers

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)

ICP = {
    "industries": ["fire protection services"],
    "keywords": ["fire inspection", "ITM", "NFPA"],
    "company_size_ranges": ["11,50"],
}


def _lead(db_session, strategy, **kwargs) -> m.Lead:
    defaults = dict(
        strategy_id=strategy.id, source="apollo", external_id=kwargs.pop("ext", "F1"),
        full_name="Sara Khan", title="Owner", company="Blaze Safety",
        email="sara@blaze.test", status=m.LeadStatus.VERIFIED,
        enrichment_json={"person": {"organization": {
            "industry": "fire protection services",
            "estimated_num_employees": 30,
        }}},
    )
    defaults.update(kwargs)
    lead = m.Lead(**defaults)
    db_session.add(lead)
    db_session.commit()
    return lead


@pytest.fixture()
def scored_strategy(db_session, verified_strategy):
    verified_strategy.pattern_inputs_json = ICP
    db_session.commit()
    return verified_strategy


# --------------------------------------------------------------------------
# The deterministic baselines
# --------------------------------------------------------------------------


class TestFit:
    def test_an_ideal_prospect_scores_high(self, db_session, scored_strategy):
        score, signals = fpta_scoring.fit_signals(_lead(db_session, scored_strategy), ICP)
        assert score > 0.9
        assert "Industry matches the ICP exactly" in signals
        assert any("Headcount 30 is inside" in s for s in signals)

    def test_the_wrong_industry_is_named_not_just_scored_down(
            self, db_session, scored_strategy):
        lead = _lead(db_session, scored_strategy, enrichment_json={"person": {
            "organization": {"industry": "pet grooming", "estimated_num_employees": 900}}})
        score, signals = fpta_scoring.fit_signals(lead, ICP)
        assert score < 0.5
        assert "Industry is outside the ICP" in signals
        assert any("outside the ICP range" in s for s in signals)

    def test_a_missing_title_is_reported_rather_than_guessed(
            self, db_session, scored_strategy):
        lead = _lead(db_session, scored_strategy, title=None)
        _score, signals = fpta_scoring.fit_signals(lead, ICP)
        assert "No title on file" in signals

    def test_an_empty_icp_does_not_crash_or_punish(self, db_session, verified_strategy):
        score, _ = fpta_scoring.fit_signals(_lead(db_session, verified_strategy), {})
        assert 0.0 <= score <= 1.0


class TestProblem:
    def test_the_prospects_own_words_are_the_evidence(self, db_session, scored_strategy):
        lead = _lead(db_session, scored_strategy, linkedin_posts_json=[
            {"text": "We are drowning in fire inspection paperwork this quarter."}])
        score, signals = fpta_scoring.problem_signals(lead, ICP)
        assert score > 0.4
        assert any("drowning" in s for s in signals)
        assert any(s.startswith("Said:") for s in signals)

    def test_an_icp_keyword_counts_as_evidence(self, db_session, scored_strategy):
        lead = _lead(db_session, scored_strategy, company_news_json=[
            {"headline": "Blaze Safety adopts NFPA reporting", "summary": ""}])
        _score, signals = fpta_scoring.problem_signals(lead, ICP)
        assert any("mentions nfpa" in s.lower() for s in signals)

    def test_no_evidence_says_so_and_scores_low(self, db_session, scored_strategy):
        score, signals = fpta_scoring.problem_signals(_lead(db_session, scored_strategy), ICP)
        assert signals == ["No visible problem signal"]
        assert score == 0.25

    def test_a_perfect_fit_does_not_lend_confidence_to_problem(
            self, db_session, scored_strategy):
        """The dimensions are independent on purpose."""
        lead = _lead(db_session, scored_strategy)
        fit, _ = fpta_scoring.fit_signals(lead, ICP)
        problem, _ = fpta_scoring.problem_signals(lead, ICP)
        assert fit > 0.9
        assert problem == 0.25


class TestTiming:
    def test_recent_funding_is_a_timing_signal(self, db_session, scored_strategy):
        lead = _lead(db_session, scored_strategy, enrichment_json={"person": {"organization": {
            "industry": "fire protection services",
            "latest_funding_round_date": (NOW - timedelta(days=60)).isoformat()}}})
        score, signals = fpta_scoring.timing_signals(lead, ICP, NOW)
        assert score > fpta_scoring.NEUTRAL
        assert any("Raised funding" in s for s in signals)

    def test_old_funding_is_not(self, db_session, scored_strategy):
        lead = _lead(db_session, scored_strategy, enrichment_json={"person": {"organization": {
            "latest_funding_round_date": (NOW - timedelta(days=1200)).isoformat()}}})
        _score, signals = fpta_scoring.timing_signals(lead, ICP, NOW)
        assert not any("Raised funding" in s for s in signals)

    def test_recent_news_counts(self, db_session, scored_strategy):
        lead = _lead(db_session, scored_strategy, company_news_json=[
            {"headline": "Blaze Safety opens a second depot",
             "published_at": (NOW - timedelta(days=5)).isoformat()}])
        score, signals = fpta_scoring.timing_signals(lead, ICP, NOW)
        assert score > fpta_scoring.NEUTRAL
        assert any("In the news" in s for s in signals)

    def test_silence_is_reported_honestly(self, db_session, scored_strategy):
        score, signals = fpta_scoring.timing_signals(_lead(db_session, scored_strategy),
                                                     ICP, NOW)
        assert signals == ["No recent activity on file"]
        assert score == 0.30

    def test_an_unparseable_date_is_ignored_not_fatal(self, db_session, scored_strategy):
        lead = _lead(db_session, scored_strategy, enrichment_json={"person": {"organization": {
            "latest_funding_round_date": "last spring"}}})
        score, _ = fpta_scoring.timing_signals(lead, ICP, NOW)
        assert 0.0 <= score <= 1.0


class TestAccess:
    def test_a_verified_email_and_a_connection_score_high(self, db_session, scored_strategy):
        lead = _lead(db_session, scored_strategy, linkedin_url="https://li/sara",
                     linkedin_connection_status="connected")
        score, signals = fpta_scoring.access_signals(lead)
        assert score >= 0.75
        assert "Verified email address" in signals
        assert "Connected on LinkedIn" in signals

    def test_no_route_at_all_scores_zero(self, db_session, scored_strategy):
        lead = _lead(db_session, scored_strategy, email=None, status=m.LeadStatus.SOURCED)
        score, signals = fpta_scoring.access_signals(lead)
        assert score == 0.0
        assert "No email address" in signals

    def test_a_phone_without_consent_is_worth_less_than_one_with(
            self, db_session, scored_strategy):
        without = _lead(db_session, scored_strategy, ext="P1", email=None,
                        status=m.LeadStatus.SOURCED, phone="+15550001")
        with_consent = _lead(db_session, scored_strategy, ext="P2", email=None,
                             status=m.LeadStatus.SOURCED, phone="+15550002",
                             phone_consent_at=NOW)
        assert (fpta_scoring.access_signals(without)[0]
                < fpta_scoring.access_signals(with_consent)[0])

    def test_access_is_computed_from_facts_only(self, db_session, scored_strategy):
        """Nothing in access depends on the ICP or on any model."""
        lead = _lead(db_session, scored_strategy)
        assert fpta_scoring.access_signals(lead) == fpta_scoring.access_signals(lead)


class TestOverall:
    def test_the_overall_is_the_documented_weighted_mean(self):
        scores = {"fit": 100, "problem": 0, "timing": 50, "access": 50}
        assert fpta_scoring.overall(scores) == round(
            100 * 0.30 + 0 * 0.30 + 50 * 0.20 + 50 * 0.20)

    def test_the_weights_sum_to_one(self):
        assert round(sum(fpta_scoring.WEIGHTS.values()), 6) == 1.0

    @pytest.mark.parametrize("score,expected", [
        (None, "unscored"), (0, "weak"), (44, "weak"), (45, "workable"),
        (69, "workable"), (70, "strong"), (100, "strong"),
    ])
    def test_bands(self, score, expected):
        assert fpta_scoring.band(score) == expected


# --------------------------------------------------------------------------
# The model pass
# --------------------------------------------------------------------------


class TestScoring:
    def test_scoring_writes_every_column(self, db_session, fake_claude, scored_strategy):
        lead = _lead(db_session, scored_strategy)
        assert fpta_scoring.score_leads(db_session, scored_strategy, [lead], now=NOW) == 1
        db_session.refresh(lead)
        assert lead.fpta_overall is not None
        assert lead.fpta_method == "model"
        assert set(lead.fpta_reasons_json) == set(fpta_scoring.DIMENSIONS)
        assert lead.fpta_reasons_json["fit"]["signals"]
        assert lead.fpta_scored_at.replace(tzinfo=timezone.utc) == NOW

    def test_the_model_cannot_move_a_score_more_than_the_clamp(
            self, db_session, fake_claude, scored_strategy):
        lead = _lead(db_session, scored_strategy)
        base = fpta_scoring.baselines(lead, ICP, NOW)["problem"]["baseline"]
        fake_claude.fpta_response = {"prospects": [{
            "lead_id": str(lead.id),
            "problem": {"score": 100, "reason": "they are desperate"},
        }]}
        fpta_scoring.score_leads(db_session, scored_strategy, [lead], now=NOW)
        db_session.refresh(lead)
        assert lead.fpta_problem == base + fpta_scoring.MAX_ADJUSTMENT

    def test_a_model_outage_falls_back_to_the_baseline(
            self, db_session, fake_claude, scored_strategy):
        lead = _lead(db_session, scored_strategy)
        expected = fpta_scoring.baselines(lead, ICP, NOW)
        fake_claude.fpta_response = RuntimeError("anthropic down")
        fpta_scoring.score_leads(db_session, scored_strategy, [lead], now=NOW)
        db_session.refresh(lead)
        assert lead.fpta_method == "heuristic"
        assert lead.fpta_fit == expected["fit"]["baseline"]
        assert lead.fpta_reasons_json["fit"]["reason"].startswith("Fit:")

    def test_a_dimension_the_model_skipped_keeps_its_baseline(
            self, db_session, fake_claude, scored_strategy):
        lead = _lead(db_session, scored_strategy)
        expected = fpta_scoring.baselines(lead, ICP, NOW)
        fake_claude.fpta_response = {"prospects": [{
            "lead_id": str(lead.id), "fit": {"score": 50, "reason": "a reason"}}]}
        fpta_scoring.score_leads(db_session, scored_strategy, [lead], now=NOW)
        db_session.refresh(lead)
        assert lead.fpta_timing == expected["timing"]["baseline"]
        assert lead.fpta_method == "mixed"

    def test_an_empty_reason_falls_back_rather_than_showing_a_blank(
            self, db_session, fake_claude, scored_strategy):
        lead = _lead(db_session, scored_strategy)
        fake_claude.fpta_response = {"prospects": [{
            "lead_id": str(lead.id),
            **{d: {"score": 60, "reason": "  "} for d in fpta_scoring.DIMENSIONS}}]}
        fpta_scoring.score_leads(db_session, scored_strategy, [lead], now=NOW)
        db_session.refresh(lead)
        assert lead.fpta_method == "heuristic"
        assert lead.fpta_reasons_json["access"]["reason"]

    def test_scoring_batches_rather_than_one_call_per_lead(
            self, db_session, fake_claude, scored_strategy):
        leads = [_lead(db_session, scored_strategy, ext=f"B{i}", email=f"b{i}@c.test")
                 for i in range(fpta_scoring.BATCH_SIZE + 2)]
        fpta_scoring.score_leads(db_session, scored_strategy, leads, now=NOW)
        assert len(fake_claude.fpta_prompts) == 2


class TestEnrollmentHook:
    def test_enrolling_scores_the_prospects(self, db_session, fake_claude, scored_strategy,
                                            verified_leads, email_sequence, gmail_account):
        from app.services.sequence_engine import enroll_leads

        assert enroll_leads(db_session, email_sequence, now=NOW) == 3
        for lead in verified_leads:
            db_session.refresh(lead)
            assert lead.fpta_overall is not None

    def test_re_enrolling_never_overwrites_a_score_someone_has_read(
            self, db_session, fake_claude, scored_strategy, verified_leads):
        lead = verified_leads[0]
        lead.fpta_overall = 11
        lead.fpta_scored_at = NOW - timedelta(days=5)
        db_session.commit()
        fpta_scoring.score_for_enrollment(db_session, [lead.id], now=NOW)
        db_session.refresh(lead)
        assert lead.fpta_overall == 11

    def test_a_scoring_failure_never_breaks_an_enrollment(
            self, db_session, fake_claude, scored_strategy, verified_leads,
            email_sequence, gmail_account, monkeypatch):
        from app.services import sequence_engine

        monkeypatch.setattr(fpta_scoring, "score_leads",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        assert sequence_engine.enroll_leads(db_session, email_sequence, now=NOW) == 3

    def test_an_empty_id_list_is_a_no_op(self, db_session, fake_claude):
        assert fpta_scoring.score_for_enrollment(db_session, []) == 0


# --------------------------------------------------------------------------
# Output + API
# --------------------------------------------------------------------------


class TestOutput:
    def test_an_unscored_prospect_reads_as_unscored_not_zero(
            self, db_session, scored_strategy):
        out = fpta_scoring.detail(_lead(db_session, scored_strategy))
        assert out["band"] == "unscored"
        assert out["overall"] is None
        assert [d["score"] for d in out["dimensions"]] == [None] * 4

    def test_detail_carries_every_dimension_with_its_weight(
            self, db_session, fake_claude, scored_strategy):
        lead = _lead(db_session, scored_strategy)
        fpta_scoring.score_leads(db_session, scored_strategy, [lead], now=NOW)
        out = fpta_scoring.detail(lead)
        assert [d["key"] for d in out["dimensions"]] == list(fpta_scoring.DIMENSIONS)
        assert all(d["weight"] == fpta_scoring.WEIGHTS[d["key"]] for d in out["dimensions"])
        assert all(d["reason"] for d in out["dimensions"])

    def test_the_engagement_note_is_none_before_anything_is_sent(
            self, db_session, scored_strategy):
        assert fpta_scoring.engagement_note(db_session,
                                            _lead(db_session, scored_strategy)) is None

    def test_the_engagement_note_counts_sends_and_opens(
            self, db_session, scored_strategy, email_sequence):
        lead = _lead(db_session, scored_strategy)
        db_session.add(m.Message(sequence_id=email_sequence.id, lead_id=lead.id,
                                 channel=m.ChannelType.EMAIL, step_no=1, template="t",
                                 status=m.MessageStatus.SENT, sent_at=NOW,
                                 opened_at=NOW))
        db_session.commit()
        note = fpta_scoring.engagement_note(db_session, lead)
        assert "1 message sent" in note and "1 opened" in note


class TestApi:
    def test_the_lead_detail_endpoint_returns_the_scores(
            self, client, db_session, fake_claude, scored_strategy, test_user):
        lead = _lead(db_session, scored_strategy)
        fpta_scoring.score_leads(db_session, scored_strategy, [lead], now=NOW)
        response = client.get(f"/leads/{lead.id}/fpta", headers=auth_headers(test_user))
        assert response.status_code == 200
        body = response.json()
        assert body["band"] in ("strong", "workable", "weak")
        assert len(body["dimensions"]) == 4

    def test_rescore_scores_an_unscored_prospect(
            self, client, db_session, fake_claude, scored_strategy, test_user):
        lead = _lead(db_session, scored_strategy)
        response = client.post(f"/leads/{lead.id}/fpta/rescore",
                               headers=auth_headers(test_user))
        assert response.status_code == 200
        assert response.json()["overall"] is not None

    def test_the_lead_list_carries_the_sub_scores(
            self, client, db_session, fake_claude, scored_strategy, test_user):
        lead = _lead(db_session, scored_strategy)
        fpta_scoring.score_leads(db_session, scored_strategy, [lead], now=NOW)
        response = client.get(f"/strategies/{scored_strategy.id}/leads",
                              headers=auth_headers(test_user))
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["fpta_overall"] is not None
        assert item["fpta_fit"] is not None

    def test_sorting_by_fpta_puts_unscored_last(
            self, client, db_session, fake_claude, scored_strategy, test_user):
        weak = _lead(db_session, scored_strategy, ext="W", email="w@c.test")
        weak.fpta_overall = 10
        weak.fpta_scored_at = NOW
        _lead(db_session, scored_strategy, ext="U", email="u@c.test")
        db_session.commit()
        response = client.get(f"/strategies/{scored_strategy.id}/leads?sort=fpta",
                              headers=auth_headers(test_user))
        items = response.json()["items"]
        assert items[0]["fpta_overall"] == 10
        assert items[-1]["fpta_overall"] is None

    def test_a_strategy_backfill_only_touches_unscored_prospects_by_default(
            self, client, db_session, fake_claude, scored_strategy, test_user):
        already = _lead(db_session, scored_strategy, ext="A", email="a@c.test")
        already.fpta_overall = 5
        already.fpta_scored_at = NOW
        _lead(db_session, scored_strategy, ext="N", email="n@c.test")
        db_session.commit()
        response = client.post(
            f"/strategies/{scored_strategy.id}/leads/fpta/rescore",
            headers=auth_headers(test_user))
        assert response.status_code == 200
        assert response.json()["scored"] == 1
        db_session.refresh(already)
        assert already.fpta_overall == 5

    def test_another_account_cannot_read_a_score(
            self, client, db_session, fake_claude, scored_strategy):
        other = m.User(email="stranger@test.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        lead = _lead(db_session, scored_strategy)
        response = client.get(f"/leads/{lead.id}/fpta", headers=auth_headers(other))
        assert response.status_code == 404

"""The ROI calculator against REAL PostgreSQL.

WHY THIS FILE EXISTS. tests/test_roi_dashboard.py covers the metrics on
SQLite and passes completely — and the endpoint still returned 503 on the
first live deploy. `compute_roi_snapshot` counted booked meetings with a
JOIN + SELECT DISTINCT over whole `leads` rows. SQLite compares anything;
PostgreSQL cannot compare its `json` type at all and raises

    psycopg2.errors.UndefinedFunction:
    could not identify an equality operator for type json

`leads` has six JSON columns, so that query could never have worked in
production. compute_roi_snapshot swallows every exception by design, so it
degraded to score-zero-plus-error and the API turned that into a 503 with
nothing in the test suite to show for it.

These tests run the same code against the dialect that actually ships.
Anything here that touches a query returning whole entity rows belongs
under this harness, not only under SQLite.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.db import models as m
from app.services import roi_calculator

TODAY = datetime.now(timezone.utc).date()
MONTH_AGO = TODAY - timedelta(days=29)


@pytest.fixture()
def campaign(db_session):
    """A user -> product -> strategy -> sequence chain on real PostgreSQL."""
    user = m.User(email=f"roi-pg-{uuid.uuid4().hex[:8]}@example.test",
                  plan=m.PlanTier.PRO)
    db_session.add(user)
    db_session.flush()
    product = m.Product(user_id=user.id, name="ROI PG", description="x",
                        type=m.ProductType.SKILL)
    db_session.add(product)
    db_session.flush()
    strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.WITH_CLIENTS,
                          status=m.StrategyStatus.EXECUTING)
    db_session.add(strategy)
    db_session.flush()
    sequence = m.Sequence(strategy_id=strategy.id, channel=m.ChannelType.EMAIL,
                          name="cold", status=m.SequenceStatus.ACTIVE)
    db_session.add(sequence)
    db_session.commit()
    return strategy, sequence


def _booked_lead(db_session, strategy, sequence, *, steps, value=None):
    """A meeting_booked lead carrying real JSON payloads.

    The JSON columns are populated on purpose: they are what makes
    SELECT DISTINCT over this row unrepresentable in PostgreSQL, so a test
    that left them NULL would not reproduce the failure.
    """
    lead = m.Lead(strategy_id=strategy.id, source="manual",
                  external_id=str(uuid.uuid4()),
                  email=f"{uuid.uuid4().hex[:10]}@example.test",
                  full_name="Sara Khan", company="Acme",
                  status=m.LeadStatus.MEETING_BOOKED,
                  estimated_deal_value=value,
                  enrichment_json={"company_domain": "acme.test"},
                  linkedin_posts_json=[{"text": "hello", "url": None}],
                  company_news_json=[{"headline": "Acme wins"}],
                  ai_score_factors={"seniority": 1})
    db_session.add(lead)
    db_session.flush()
    for step in steps:
        db_session.add(m.SequenceEnrollment(sequence_id=sequence.id, lead_id=lead.id,
                                            current_step=step))
    db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.BOOKED,
                             channel="email", ts=datetime.now(timezone.utc)))
    db_session.commit()
    return lead


class TestRoiOnPostgres:
    def test_compute_does_not_error_on_postgres(self, db_session, campaign):
        """The regression itself: this returned an `error` key, and the
        endpoint a 503, because of SELECT DISTINCT over json columns."""
        strategy, sequence = campaign
        _booked_lead(db_session, strategy, sequence, steps=[3])

        metrics = roi_calculator.compute_roi_snapshot(db_session, strategy.id,
                                                      MONTH_AGO, TODAY)

        assert "error" not in metrics, metrics.get("error")
        assert metrics["meetings_booked"] == 1

    def test_a_lead_with_two_qualifying_enrollments_counts_once(self, db_session,
                                                                campaign):
        """What the DISTINCT was there for. The IN-subquery form must keep it."""
        strategy, sequence = campaign
        second = m.Sequence(strategy_id=strategy.id, channel=m.ChannelType.LINKEDIN,
                            name="li", status=m.SequenceStatus.ACTIVE)
        db_session.add(second)
        db_session.commit()

        lead = _booked_lead(db_session, strategy, sequence, steps=[3])
        db_session.add(m.SequenceEnrollment(sequence_id=second.id, lead_id=lead.id,
                                            current_step=4))
        db_session.commit()

        metrics = roi_calculator.compute_roi_snapshot(db_session, strategy.id,
                                                      MONTH_AGO, TODAY)

        assert "error" not in metrics
        assert metrics["meetings_booked"] == 1

    def test_step_threshold_still_applies(self, db_session, campaign):
        strategy, sequence = campaign
        _booked_lead(db_session, strategy, sequence, steps=[2])

        metrics = roi_calculator.compute_roi_snapshot(db_session, strategy.id,
                                                      MONTH_AGO, TODAY)

        assert "error" not in metrics
        assert metrics["meetings_booked"] == 0

    def test_money_is_decimal_on_postgres_numeric(self, db_session, campaign):
        strategy, sequence = campaign
        _booked_lead(db_session, strategy, sequence, steps=[3],
                     value=Decimal("2500.50"))

        metrics = roi_calculator.compute_roi_snapshot(db_session, strategy.id,
                                                      MONTH_AGO, TODAY)

        assert "error" not in metrics
        assert isinstance(metrics["pipeline_value"], Decimal)
        assert metrics["pipeline_value"] == Decimal("2500.50")

    def test_daily_snapshot_upserts_on_postgres(self, db_session, campaign):
        """Exercises the real UNIQUE (strategy_id, snapshot_date)."""
        strategy, sequence = campaign
        _booked_lead(db_session, strategy, sequence, steps=[3])

        first = roi_calculator.upsert_daily_snapshot(db_session, strategy.id, TODAY)
        second = roi_calculator.upsert_daily_snapshot(db_session, strategy.id, TODAY)

        assert first is not None and second is not None
        assert first.id == second.id
        assert db_session.query(m.ROISnapshot).filter(
            m.ROISnapshot.strategy_id == strategy.id).count() == 1


class TestOtherFeaturesOnPostgres:
    """The other four features' read paths, against the real dialect."""

    def test_pipeline_health_computes(self, db_session, campaign):
        from app.services import pipeline_health

        strategy, sequence = campaign
        _booked_lead(db_session, strategy, sequence, steps=[3])

        result = pipeline_health.compute_health_score(db_session, strategy.id)

        assert "error" not in result, result.get("error")
        assert 0 <= result["score"] <= 100

    def test_displacement_scan_runs(self, db_session, campaign, monkeypatch):
        from app.services import displacement_monitor

        strategy, sequence = campaign
        lead = _booked_lead(db_session, strategy, sequence, steps=[3])
        lead.linkedin_url = "https://www.linkedin.com/in/sara-khan/"
        lead.linkedin_posts_json = [{"text": "We left Apollo last month.",
                                     "url": "https://li/p/1"}]
        db_session.commit()
        monkeypatch.setattr(
            "app.services.personalization_context.ensure_fresh",
            lambda session, lead, **kwargs: {"posts": "stubbed"})
        monkeypatch.setattr(displacement_monitor, "generate_displacement_dm",
                            lambda *a, **k: "Saw your note about Apollo. What broke?")

        created = displacement_monitor.run_displacement_scan(db_session, strategy.id)

        assert created == 1
        alert = db_session.query(m.DisplacementAlert).one()
        assert alert.matched_keywords == ["Apollo"]

    def test_voice_profile_round_trips(self, db_session, campaign):
        from app.services import voice_profiler

        strategy, _sequence = campaign
        profile = m.VoiceProfile(product_id=strategy.product_id,
                                 raw_posts_json=["a post"],
                                 style_dimensions_json={"opens_with": "question"},
                                 sample_phrases=["here is the thing"],
                                 post_count=1)
        db_session.add(profile)
        db_session.commit()

        loaded = voice_profiler.get_profile(db_session, strategy.product_id)

        assert loaded is not None
        assert loaded.style_dimensions_json["opens_with"] == "question"

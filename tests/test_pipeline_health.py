"""Feature 1 — pipeline health score.

Pins the formula (each component and the weighting), the band boundaries, the
"never raises" contract, the six-hourly sweep's idempotency, and the endpoint's
owner-scoping.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.services import pipeline_health
from app.workers import health_tasks

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def scored(db_session, product_with_strategy):
    """A strategy with one sequence, its steps and a handful of leads."""
    _product, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
    strategy.status = m.StrategyStatus.VERIFIED
    sequence = m.Sequence(strategy_id=strategy.id, channel=m.ChannelType.EMAIL,
                          name="cold", status=m.SequenceStatus.ACTIVE)
    db_session.add(sequence)
    db_session.commit()
    return strategy, sequence


def _lead(db_session, strategy, *, status=m.LeadStatus.CONTACTED, created_at=None):
    lead = m.Lead(strategy_id=strategy.id, source="manual",
                  external_id=str(uuid.uuid4()),
                  email=f"{uuid.uuid4().hex[:10]}@example.com", status=status)
    db_session.add(lead)
    db_session.commit()
    if created_at is not None:
        lead.created_at = created_at
        db_session.commit()
    return lead


class TestComponents:
    def test_empty_pipeline_scores_zero_and_is_critical(self, db_session, scored):
        strategy, _sequence = scored
        result = pipeline_health.compute_health_score(db_session, strategy.id, now=NOW)
        assert result["score"] == 0
        assert result["band"] == "critical"
        assert result["message"] == "Pipeline empty. Add leads immediately."
        assert result["components"] == {"reply_rate": 0.0, "completion": 0.0,
                                        "freshness": 0.0, "conversations": 0.0}

    def test_reply_rate_is_replies_over_sends(self, db_session, scored):
        strategy, _sequence = scored
        lead = _lead(db_session, strategy, created_at=NOW)
        for _ in range(4):
            db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.SENT,
                                     channel="email"))
        db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.REPLIED,
                                 channel="email"))
        db_session.commit()

        result = pipeline_health.compute_health_score(db_session, strategy.id, now=NOW)
        assert result["components"]["reply_rate"] == 25.0
        assert result["inputs"]["sends"] == 4
        assert result["inputs"]["replies"] == 1

    def test_reply_rate_cannot_exceed_100(self, db_session, scored):
        """More replies than sends (a thread that answered twice) is capped,
        not allowed to push the blended score above its own weight."""
        strategy, _sequence = scored
        lead = _lead(db_session, strategy, created_at=NOW)
        db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.SENT,
                                 channel="email"))
        for _ in range(3):
            db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.REPLIED,
                                     channel="email"))
        db_session.commit()
        result = pipeline_health.compute_health_score(db_session, strategy.id, now=NOW)
        assert result["components"]["reply_rate"] == 100.0

    def test_completion_is_completed_over_enrolled(self, db_session, scored):
        strategy, sequence = scored
        for status in (m.EnrollmentStatus.COMPLETED, m.EnrollmentStatus.COMPLETED,
                       m.EnrollmentStatus.ACTIVE, m.EnrollmentStatus.STOPPED):
            lead = _lead(db_session, strategy, created_at=NOW)
            db_session.add(m.SequenceEnrollment(sequence_id=sequence.id,
                                                lead_id=lead.id, status=status))
        db_session.commit()
        result = pipeline_health.compute_health_score(db_session, strategy.id, now=NOW)
        assert result["components"]["completion"] == 50.0

    @pytest.mark.parametrize("age_days,expected", [
        (0, 100.0), (3, 100.0), (30, 0.0), (45, 0.0),
        # Straight line between 3 and 30 days: 16.5 days is the midpoint.
        (16.5, 50.0),
    ])
    def test_freshness_decay(self, db_session, scored, age_days, expected):
        strategy, _sequence = scored
        _lead(db_session, strategy, created_at=NOW - timedelta(days=age_days))
        result = pipeline_health.compute_health_score(db_session, strategy.id, now=NOW)
        assert result["components"]["freshness"] == pytest.approx(expected, abs=0.01)

    def test_conversations_is_open_replies_times_ten_capped(self, db_session, scored):
        strategy, _sequence = scored
        for _ in range(12):
            _lead(db_session, strategy, status=m.LeadStatus.REPLIED, created_at=NOW)
        result = pipeline_health.compute_health_score(db_session, strategy.id, now=NOW)
        assert result["components"]["conversations"] == 100.0

    def test_score_is_the_weighted_blend(self, db_session, scored):
        strategy, sequence = scored
        # freshness 100, conversations 30 (3 open replies), completion 100,
        # reply_rate 100  ->  35 + 25 + 20 + 6 = 86
        for _ in range(3):
            lead = _lead(db_session, strategy, status=m.LeadStatus.REPLIED,
                         created_at=NOW)
            db_session.add(m.SequenceEnrollment(sequence_id=sequence.id, lead_id=lead.id,
                                                status=m.EnrollmentStatus.COMPLETED))
            db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.SENT,
                                     channel="email"))
            db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.REPLIED,
                                     channel="email"))
        db_session.commit()
        result = pipeline_health.compute_health_score(db_session, strategy.id, now=NOW)
        assert result["components"] == {"reply_rate": 100.0, "completion": 100.0,
                                        "freshness": 100.0, "conversations": 30.0}
        assert result["score"] == 86
        assert result["band"] == "strong"


class TestBands:
    @pytest.mark.parametrize("score,band", [
        (0, "critical"), (40, "critical"), (41, "low"), (60, "low"),
        (61, "moderate"), (80, "moderate"), (81, "strong"), (100, "strong"),
    ])
    def test_boundaries(self, score, band):
        assert pipeline_health.band_for(score)[0] == band

    def test_every_band_has_its_own_message(self):
        messages = {message for _upper, _band, message in pipeline_health.BANDS}
        assert len(messages) == len(pipeline_health.BANDS)

    def test_weights_sum_to_one(self):
        assert sum(pipeline_health.WEIGHTS.values()) == pytest.approx(1.0)


class TestNeverRaises:
    def test_unknown_strategy_id_degrades_to_critical(self, db_session):
        result = pipeline_health.compute_health_score(db_session, uuid.uuid4(), now=NOW)
        assert result["score"] == 0 and result["band"] == "critical"

    def test_garbage_strategy_id_degrades_instead_of_raising(self, db_session):
        result = pipeline_health.compute_health_score(db_session, "not-a-uuid", now=NOW)
        assert result["score"] == 0
        assert "error" in result

    def test_a_failed_measurement_never_overwrites_the_last_good_score(
            self, db_session, scored):
        """The bug this guards: a database blip during the sweep writing 0 on
        every campaign and telling the founder their pipeline collapsed."""
        strategy, _sequence = scored
        strategy.pipeline_health_score = 77
        strategy.health_band = "moderate"
        db_session.commit()

        failed = pipeline_health.compute_health_score(db_session, "not-a-uuid", now=NOW)
        pipeline_health.persist(db_session, strategy, failed)

        assert strategy.pipeline_health_score == 77
        assert strategy.health_band == "moderate"


class TestSweep:
    def test_scores_only_scorable_statuses(self, db_session, product_with_strategy):
        pending = product_with_strategy(m.FlowType.WITH_CLIENTS)[1]
        executing = product_with_strategy(m.FlowType.WITH_CLIENTS)[1]
        executing.status = m.StrategyStatus.EXECUTING
        db_session.commit()

        result = health_tasks.refresh_all_pipeline_health_impl(db_session)

        assert result["total"] == 1
        assert executing.pipeline_health_score is not None
        assert pending.pipeline_health_score is None

    def test_is_idempotent(self, db_session, scored):
        strategy, _sequence = scored
        _lead(db_session, strategy, created_at=datetime.now(timezone.utc))

        first = health_tasks.refresh_all_pipeline_health_impl(db_session)
        score_after_first = strategy.pipeline_health_score
        second = health_tasks.refresh_all_pipeline_health_impl(db_session)

        assert first == second
        assert strategy.pipeline_health_score == score_after_first


class TestEndpoint:
    def test_returns_score_band_message_and_components(self, client, db_session,
                                                       product_with_strategy):
        _product, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
        _lead(db_session, strategy, created_at=datetime.now(timezone.utc))

        response = client.get(f"/strategies/{strategy.id}/health")

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"score", "band", "message", "components", "updated_at"}
        assert set(body["components"]) == {"reply_rate", "completion",
                                           "freshness", "conversations"}
        assert body["components"]["freshness"] == 100.0
        assert body["updated_at"] is not None

    def test_caches_the_score_on_the_strategy(self, client, db_session,
                                              product_with_strategy):
        _product, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
        assert strategy.pipeline_health_score is None

        client.get(f"/strategies/{strategy.id}/health")

        db_session.refresh(strategy)
        assert strategy.pipeline_health_score == 0
        assert strategy.health_band == "critical"

    def test_another_users_strategy_is_404_not_403(self, client, db_session):
        other = m.User(email="stranger@example.com", plan=m.PlanTier.PRO)
        db_session.add(other)
        db_session.flush()
        product = m.Product(user_id=other.id, name="theirs", description="x",
                            type=m.ProductType.SKILL)
        db_session.add(product)
        db_session.flush()
        strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.WITH_CLIENTS)
        db_session.add(strategy)
        db_session.commit()

        response = client.get(f"/strategies/{strategy.id}/health")

        assert response.status_code == 404

    def test_unknown_strategy_is_404(self, client):
        assert client.get(f"/strategies/{uuid.uuid4()}/health").status_code == 404

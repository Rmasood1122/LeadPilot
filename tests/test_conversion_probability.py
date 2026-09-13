"""Feature A5 — live conversion probability, kill signals and outcome-based
channel/slot optimisation.

Pins: the estimate moves the right way for every kind of evidence and explains
itself; kill signals end a lead regardless of probability; the send task holds
a cold lead instead of sending (pausing or stopping its sequence and tagging it
in the CRM); probability never judges a lead before its minimum sends; a person
can reactivate; and channel/slot ranking weights bookings over replies.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import conversion_probability as cp
from app.services import score_decay, send_time_optimizer, system_settings
from tests.conftest import NOW, auth_headers


def _outcome(db_session, lead, event, days_ago, channel="email", now=None):
    now = now or datetime.now(timezone.utc)
    db_session.add(m.Outcome(lead_id=lead.id, event=event, channel=channel,
                             ts=now - timedelta(days=days_ago)))
    db_session.commit()


def _lead(db_session, strategy, n, *, score=None):
    lead = m.Lead(strategy_id=strategy.id, source="apollo", external_id=f"CP{n}",
                  full_name=f"CP {n}", email=f"cp{n}@acme.io", status=m.LeadStatus.CONTACTED,
                  ai_booking_likelihood=score)
    db_session.add(lead)
    db_session.commit()
    return lead


class TestEstimate:
    def test_a_fresh_lead_starts_at_its_prior(self, db_session, verified_strategy):
        default = cp.compute(db_session, _lead(db_session, verified_strategy, 1))
        assert default.probability == pytest.approx(0.10, abs=0.001)
        assert default.factors[0]["factor"] == "default_prior"
        scored = cp.compute(db_session, _lead(db_session, verified_strategy, 2, score=60))
        assert scored.probability == pytest.approx(0.60, abs=0.001) and scored.band == "hot"

    def test_every_unanswered_send_lowers_it(self, db_session, verified_strategy):
        lead = _lead(db_session, verified_strategy, 3)
        previous = cp.compute(db_session, lead).probability
        for days in (6, 5, 4):
            _outcome(db_session, lead, m.OutcomeEvent.SENT, days)
            current = cp.compute(db_session, lead).probability
            assert current < previous
            previous = current
        assert cp.compute(db_session, lead).unanswered_sends == 3

    def test_opens_and_clicks_raise_it_and_fade_with_age(self, db_session, verified_strategy):
        base = _lead(db_session, verified_strategy, 4)
        _outcome(db_session, base, m.OutcomeEvent.SENT, 3)
        without = cp.compute(db_session, base).probability

        fresh = _lead(db_session, verified_strategy, 5)
        _outcome(db_session, fresh, m.OutcomeEvent.SENT, 3)
        _outcome(db_session, fresh, m.OutcomeEvent.OPENED, 1)
        _outcome(db_session, fresh, m.OutcomeEvent.CLICKED, 1)
        stale = _lead(db_session, verified_strategy, 6)
        _outcome(db_session, stale, m.OutcomeEvent.SENT, 3)
        _outcome(db_session, stale, m.OutcomeEvent.OPENED, 2.9)
        stale_click = datetime.now(timezone.utc) - timedelta(days=2.9)
        db_session.add(m.Outcome(lead_id=stale.id, event=m.OutcomeEvent.CLICKED, channel="email",
                                 ts=stale_click - timedelta(days=40)))
        db_session.commit()
        assert cp.compute(db_session, fresh).probability > cp.compute(db_session, stale).probability \
            > without

    def test_a_genuine_interested_reply_resets_the_count_and_jumps(self, db_session,
                                                                   verified_strategy):
        lead = _lead(db_session, verified_strategy, 7)
        for days in (9, 8, 7):
            _outcome(db_session, lead, m.OutcomeEvent.SENT, days)
        before = cp.compute(db_session, lead).probability
        db_session.add(m.InboundReply(lead_id=lead.id, channel="email", from_address=lead.email,
                                      body="Interested", classification="interested",
                                      received_at=datetime.now(timezone.utc) - timedelta(days=1),
                                      authenticity_kind="genuine"))
        db_session.commit()
        after = cp.compute(db_session, lead)
        assert after.probability > before * 3 and after.unanswered_sends == 0

    def test_automated_replies_count_for_nothing(self, db_session, verified_strategy):
        lead = _lead(db_session, verified_strategy, 8)
        _outcome(db_session, lead, m.OutcomeEvent.SENT, 3)
        before = cp.compute(db_session, lead).probability
        db_session.add(m.InboundReply(lead_id=lead.id, channel="email", from_address=lead.email,
                                      body="I am away", classification="out_of_office",
                                      authenticity_kind="out_of_office"))
        db_session.commit()
        assert cp.compute(db_session, lead).probability == before

    def test_inactivity_decays_but_never_to_zero(self, db_session, verified_strategy):
        recent = _lead(db_session, verified_strategy, 9)
        _outcome(db_session, recent, m.OutcomeEvent.SENT, 2)
        old = _lead(db_session, verified_strategy, 10)
        _outcome(db_session, old, m.OutcomeEvent.SENT, 400)
        assert cp.compute(db_session, old).probability < cp.compute(db_session, recent).probability
        assert cp.compute(db_session, old).probability > 0.03, "time alone at most halves the odds"

    @pytest.mark.parametrize("event,signal", [(m.OutcomeEvent.BOUNCED, "bounced"),
                                              (m.OutcomeEvent.UNSUBSCRIBED, "unsubscribed"),
                                              (m.OutcomeEvent.OPTED_OUT, "unsubscribed")])
    def test_kill_signals(self, db_session, verified_strategy, event, signal):
        lead = _lead(db_session, verified_strategy, 11, score=90)
        _outcome(db_session, lead, event, 1)
        estimate = cp.compute(db_session, lead)
        assert estimate.kill_signal == signal and estimate.probability == 0.0

    def test_not_interested_is_a_kill_signal(self, db_session, verified_strategy):
        lead = _lead(db_session, verified_strategy, 12, score=90)
        db_session.add(m.InboundReply(lead_id=lead.id, channel="email", from_address=lead.email,
                                      body="No thanks", classification="not_interested",
                                      authenticity_kind="genuine"))
        db_session.commit()
        assert cp.compute(db_session, lead).kill_signal == "not_interested"

    def test_a_booking_is_won(self, db_session, verified_strategy):
        lead = _lead(db_session, verified_strategy, 13)
        _outcome(db_session, lead, m.OutcomeEvent.BOOKED, 1)
        assert cp.compute(db_session, lead).band == "won"

    def test_engagement_weight_is_the_playbook_curve(self):
        assert score_decay.engagement_weight(0, 14) == pytest.approx(1.0)
        assert score_decay.engagement_weight(14, 14) == pytest.approx(0.5)


def _history(db_session, sequence, lead, sends: int, *, first_days_ago: float = 40):
    """`sends` SENT messages + outcomes on the fixture clock (NOW)."""
    for i in range(sends):
        when = NOW - timedelta(days=first_days_ago - i * 5)
        db_session.add(m.Message(sequence_id=sequence.id, lead_id=lead.id,
                                 channel=m.ChannelType.EMAIL, step_no=1, template="t",
                                 body="b", status=m.MessageStatus.SENT, sent_at=when))
        db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.SENT, channel="email",
                                 ts=when))
    db_session.commit()


def _scheduled(db_session, sequence, lead):
    return db_session.execute(select(m.Message).where(
        m.Message.sequence_id == sequence.id, m.Message.lead_id == lead.id,
        m.Message.status == m.MessageStatus.SCHEDULED)).scalars().first()


class TestSendGate:
    def test_a_cold_lead_is_held_and_its_sequence_paused(self, db_session, enrolled,
                                                         verified_leads, fake_channel, test_user):
        from app.workers import outreach_tasks

        lead = verified_leads[0]
        lead.ai_booking_likelihood = 5
        _history(db_session, enrolled, lead, 5)
        message = _scheduled(db_session, enrolled, lead)
        result = outreach_tasks.send_message_impl(db_session, message.id, channel=fake_channel,
                                                  now=NOW)
        assert result == "held_cooling"
        assert fake_channel.sent == []
        db_session.refresh(lead)
        assert lead.engagement_state == "cooling" and lead.conversion_probability < 0.05
        enrollment = db_session.execute(select(m.SequenceEnrollment).where(
            m.SequenceEnrollment.lead_id == lead.id)).scalar_one()
        assert enrollment.status is m.EnrollmentStatus.PAUSED
        tag = db_session.execute(select(m.CrmTag).where(m.CrmTag.user_id == test_user.id,
                                                        m.CrmTag.name == "cooling")).scalar_one()
        assert db_session.execute(select(m.CrmLeadTag).where(
            m.CrmLeadTag.lead_id == lead.id, m.CrmLeadTag.tag_id == tag.id)).first()

    def test_a_kill_signal_stops_the_sequence(self, db_session, enrolled, verified_leads,
                                              fake_channel):
        from app.workers import outreach_tasks

        lead = verified_leads[1]
        db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.BOUNCED, channel="email",
                                 ts=NOW - timedelta(days=1)))
        db_session.commit()
        message = _scheduled(db_session, enrolled, lead)
        assert outreach_tasks.send_message_impl(db_session, message.id, channel=fake_channel,
                                                now=NOW) == "held_archived"
        enrollment = db_session.execute(select(m.SequenceEnrollment).where(
            m.SequenceEnrollment.lead_id == lead.id)).scalar_one()
        assert enrollment.status is m.EnrollmentStatus.STOPPED
        assert enrollment.stop_reason == "kill_signal:bounced"

    def test_probability_never_judges_a_lead_before_its_minimum_sends(
            self, db_session, enrolled, verified_leads, fake_channel):
        from app.workers import outreach_tasks

        lead = verified_leads[2]
        lead.ai_booking_likelihood = 1      # prior below the archive threshold
        db_session.commit()
        message = _scheduled(db_session, enrolled, lead)
        assert outreach_tasks.send_message_impl(db_session, message.id, channel=fake_channel,
                                                now=NOW) == "sent"

    def test_the_gate_can_be_switched_off(self, db_session, enrolled, verified_leads,
                                          fake_channel):
        from app.workers import outreach_tasks

        system_settings.set(db_session, "conversion_gate_enabled", False)
        lead = verified_leads[0]
        lead.ai_booking_likelihood = 5
        _history(db_session, enrolled, lead, 6)
        message = _scheduled(db_session, enrolled, lead)
        assert outreach_tasks.send_message_impl(db_session, message.id, channel=fake_channel,
                                                now=NOW) == "sent"


class TestSweepAndOverride:
    def test_the_sweep_archives_a_dead_lead(self, db_session, enrolled, verified_leads):
        lead = verified_leads[0]
        db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.UNSUBSCRIBED,
                                 channel="email", ts=NOW))
        db_session.commit()
        result = cp.rescore_active_leads(db_session, now=NOW)
        assert result["scored"] == 3 and result["changed"] == 1
        db_session.refresh(lead)
        assert (lead.engagement_state, lead.kill_signal) == ("archived", "unsubscribed")

    def test_hysteresis_keeps_a_cooling_lead_cooling_on_a_small_rise(self, db_session,
                                                                    verified_strategy):
        lead = _lead(db_session, verified_strategy, 20)
        lead.engagement_state = "cooling"
        db_session.commit()
        estimate = cp.Estimate(0.06, "cold", None, 5, [])
        assert cp.reclassify(db_session, lead, estimate) == "cooling"
        assert cp.reclassify(db_session, lead, cp.Estimate(0.2, "warm", None, 5, [])) == "active"

    def test_reactivate_resumes_and_clears_tags(self, client, db_session, enrolled,
                                                verified_leads, fake_channel):
        from app.workers import outreach_tasks

        lead = verified_leads[0]
        lead.ai_booking_likelihood = 5
        _history(db_session, enrolled, lead, 5)
        message = _scheduled(db_session, enrolled, lead)
        outreach_tasks.send_message_impl(db_session, message.id, channel=fake_channel, now=NOW)

        at_risk = client.get("/conversion/at-risk").json()
        assert [r["lead_id"] for r in at_risk] == [str(lead.id)]
        resp = client.post(f"/leads/{lead.id}/conversion/reactivate")
        assert resp.status_code == 200 and resp.json()["resumed_enrollments"] == 1
        db_session.refresh(lead)
        assert lead.engagement_state == "active"
        assert db_session.execute(select(m.CrmLeadTag).where(
            m.CrmLeadTag.lead_id == lead.id)).first() is None
        assert client.post(f"/leads/{lead.id}/conversion/reactivate").status_code == 409

    def test_live_endpoint_and_scoping(self, client, db_session, verified_leads):
        body = client.get(f"/leads/{verified_leads[0].id}/conversion").json()
        assert 0 < body["live"]["probability"] < 1 and body["stored"]["engagement_state"] == "active"
        stranger = m.User(email="conv-stranger@example.com", email_verified=True)
        db_session.add(stranger)
        db_session.commit()
        assert client.get(f"/leads/{verified_leads[0].id}/conversion",
                          headers=auth_headers(stranger)).status_code == 404


class TestOutcomeBasedOptimisation:
    def test_channels_rank_by_meetings_not_just_replies(self, db_session, verified_strategy):
        now = datetime.now(timezone.utc)
        leads = [_lead(db_session, verified_strategy, 30 + i) for i in range(6)]
        for lead in leads[:3]:        # email: 3 sends, 2 replies, no bookings
            _outcome(db_session, lead, m.OutcomeEvent.SENT, 5, "email", now)
        for lead in leads[:2]:
            _outcome(db_session, lead, m.OutcomeEvent.REPLIED, 4, "email", now)
        for lead in leads[3:]:        # linkedin: 3 sends, 1 reply that booked
            _outcome(db_session, lead, m.OutcomeEvent.SENT, 5, "linkedin", now)
        _outcome(db_session, leads[3], m.OutcomeEvent.REPLIED, 4, "linkedin", now)
        _outcome(db_session, leads[3], m.OutcomeEvent.BOOKED, 3, "calendly", now)

        rates = send_time_optimizer.channel_conversion_rates(db_session, verified_strategy.id)
        assert rates["linkedin"]["bookings"] == 1, "the booking is credited to the send that earned it"
        assert "calendly" not in rates
        ranking = send_time_optimizer.channel_ranking_for_lead(db_session, leads[0])
        assert ranking[0] == "linkedin" and ranking.index("email") < ranking.index("phone")

    def test_slots_weight_bookings(self, db_session, verified_strategy):
        base = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)   # a Monday
        a, b = _lead(db_session, verified_strategy, 40), _lead(db_session, verified_strategy, 41)
        db_session.add_all([
            m.Outcome(lead_id=a.id, event=m.OutcomeEvent.SENT, channel="email", ts=base),
            m.Outcome(lead_id=a.id, event=m.OutcomeEvent.BOOKED, channel="calendly",
                      ts=base + timedelta(days=1)),
            m.Outcome(lead_id=b.id, event=m.OutcomeEvent.SENT, channel="email",
                      ts=base + timedelta(hours=5)),
            m.Outcome(lead_id=b.id, event=m.OutcomeEvent.REPLIED, channel="email",
                      ts=base + timedelta(days=1)),
        ])
        db_session.commit()
        slots = send_time_optimizer.outcome_weighted_slots(db_session, verified_strategy.id)
        assert (slots[0]["day_of_week"], slots[0]["hour_utc"]) == (1, 9)

    def test_channel_performance_endpoint_is_owner_scoped(self, client, db_session,
                                                          verified_strategy):
        assert client.get(f"/strategies/{verified_strategy.id}/channel-performance").status_code == 200
        stranger = m.User(email="perf-stranger@example.com", email_verified=True)
        db_session.add(stranger)
        db_session.commit()
        assert client.get(f"/strategies/{verified_strategy.id}/channel-performance",
                          headers=auth_headers(stranger)).status_code == 404


def test_the_sweep_is_scheduled_on_learning():
    from app.workers import conversion_tasks  # noqa: F401
    from app.workers.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["rescore-conversion-probability"]
    assert entry["task"] == "app.workers.conversion_tasks.rescore_conversion_probability"
    assert celery_app.amqp.router.route({}, entry["task"])["queue"].name == "learning"

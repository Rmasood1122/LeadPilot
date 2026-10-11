"""Best time to send (docs/features/autopilot-launch.md section 3.2).

Pinned here, offline and deterministic:
  * the production defaults (flag ON, 30-send learning threshold);
  * priors per channel and per industry, intersected with sending hours;
  * placement in the PROSPECT's local time: New York, Singapore, weekends,
    both DST changes, the horizon fallback, the per-lead spread;
  * learning: below the threshold the prior decides; above it the account's own
    reply rates move the slot (Bayesian smoothing); another account's sends
    never count;
  * the person's override is a hard window and re-places scheduled messages;
  * the send-time plan: a good model answer is used, a bad one / an error keeps
    the priors, it is bought once and metered as `send_time`;
  * the engine: enrollment and later steps use it; flag off = the old schedule;
    the send path's outside-hours deferral lands on the best slot.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.db import models as m
from app.services import send_time, system_settings, usage_meter
from app.services import sequence_engine as engine

#: Captured at import, before conftest's autouse `best_time_scheduling_off`.
_REAL_ENABLED = send_time.enabled

TUE_10 = datetime(2026, 8, 11, 10, 0, tzinfo=timezone.utc)   # Tuesday
TUE_13 = datetime(2026, 8, 11, 13, 0, tzinfo=timezone.utc)
MON_09 = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)    # Monday
NY = "America/New_York"


@pytest.fixture(autouse=True)
def best_time_on(monkeypatch):
    monkeypatch.setattr(send_time, "enabled", _REAL_ENABLED)


def _lead(tz: str | None = None) -> m.Lead:
    lead = m.Lead(id=uuid.uuid4(), source="t", external_id=uuid.uuid4().hex,
                  enrichment_json={"timezone": tz} if tz else {})
    return lead


def _slot(db, lead, earliest, channel="email", strategy=None, **kw):
    scorer, hard, _ = send_time.scorer_for(db, strategy, channel)
    return send_time.best_slot(db, scorer, hard, earliest, engine.lead_timezone(lead), **kw)


# --------------------------------------------------------------------------
# Defaults and priors
# --------------------------------------------------------------------------


class TestDefaults:
    def test_flags_default_on_and_threshold_is_30(self, db_session):
        assert system_settings.DEFAULTS[send_time.FLAG][0] is True
        assert system_settings.DEFAULTS[send_time.MIN_SENDS_SETTING][0] == 30
        assert system_settings.DEFAULTS["autopilot_launch_enabled"][0] is True
        assert send_time.enabled(db_session) is True

    def test_the_suite_default_fixture_turns_it_off_elsewhere(self):
        # conftest's best_time_scheduling_off replaces `enabled`; this module
        # restores the real one, so the production default is what is tested.
        assert send_time.enabled is _REAL_ENABLED


class TestPriors:
    def test_b2b_email_is_tue_to_thu_mid_morning(self):
        entry = send_time.plan_for(None, "email")
        assert entry["basis"] == "prior"
        assert send_time.describe_window(entry["windows"][0]) == "Tue–Thu 09:00–11:00"

    def test_linkedin_mornings_and_lunch(self):
        windows = send_time.plan_for(None, "linkedin")["windows"]
        assert [send_time.describe_window(w) for w in windows] == [
            "Tue–Thu 08:00–10:00", "Tue–Thu 12:00–13:00"]

    @pytest.mark.parametrize("industry, label, first", [
        ("Restaurants & cafés", "restaurants", "Mon–Fri 14:30–16:30"),
        ("Dental clinics", "healthcare", "Mon–Fri 09:00–11:00"),
        ("Independent retail", "retail", "Mon–Fri 09:00–09:30"),
        ("Residential real estate", "real estate", "Mon–Fri 09:00–10:30"),
    ])
    def test_industry_priors_apply_to_every_channel(self, industry, label, first):
        plan = send_time.prior_plan([industry])
        for channel in ("email", "linkedin", "whatsapp"):
            assert plan[channel]["basis"] == f"industry:{label}"
            assert send_time.describe_window(plan[channel]["windows"][0]) == first

    def test_keywords_match_words_not_fragments(self):
        assert send_time.industry_prior(["Barbershops"]) is None
        assert send_time.industry_prior(["Drugstore chains"]) is None
        assert send_time.industry_prior(["fire protection"]) is None

    def test_strategy_icp_drives_the_prior(self, verified_strategy):
        verified_strategy.pattern_inputs_json = {"icp": {"industries": ["Restaurants"]}}
        assert send_time.plan_for(verified_strategy, "whatsapp")["basis"] == "industry:restaurants"


# --------------------------------------------------------------------------
# Placement
# --------------------------------------------------------------------------


class TestPlacement:
    def test_new_york_monday_goes_to_ten_local(self, db_session):
        earliest = datetime(2026, 8, 10, 13, 0, tzinfo=timezone.utc)   # Mon 09:00 EDT
        got = _slot(db_session, _lead(NY), earliest)
        assert got == datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)  # Mon 10:00 EDT

    def test_singapore_afternoon_moves_to_next_morning(self, db_session):
        earliest = datetime(2026, 8, 11, 6, 0, tzinfo=timezone.utc)    # Tue 14:00 SGT
        got = _slot(db_session, _lead("Asia/Singapore"), earliest)
        assert got == datetime(2026, 8, 12, 1, 0, tzinfo=timezone.utc)  # Wed 09:00 SGT

    def test_weekends_are_skipped(self, db_session):
        earliest = datetime(2026, 8, 14, 16, 0, tzinfo=timezone.utc)   # Fri 16:00 UTC
        got = _slot(db_session, _lead(), earliest)
        assert got == datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)  # Mon 10:00

    def test_spring_forward_keeps_ten_local(self, db_session):
        earliest = datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc)    # Sat before DST
        got = _slot(db_session, _lead(NY), earliest)
        assert got == datetime(2026, 3, 9, 14, 0, tzinfo=timezone.utc)   # Mon 10:00 EDT
        assert got.astimezone(ZoneInfo(NY)).hour == 10

    def test_fall_back_keeps_ten_local(self, db_session):
        earliest = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)  # Sat before DST ends
        got = _slot(db_session, _lead(NY), earliest)
        assert got == datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)  # Mon 10:00 EST
        assert got.astimezone(ZoneInfo(NY)).hour == 10

    def test_already_in_the_best_window_stays(self, db_session):
        assert _slot(db_session, _lead(), TUE_10) == TUE_10

    def test_never_earlier_than_earliest(self, db_session):
        earliest = datetime(2026, 8, 11, 10, 7, tzinfo=timezone.utc)
        got = _slot(db_session, _lead(), earliest)
        assert got >= earliest and got == datetime(2026, 8, 11, 10, 15, tzinfo=timezone.utc)

    def test_no_permitted_slot_in_the_horizon_returns_earliest(self, db_session):
        earliest = datetime(2026, 8, 14, 17, 30, tzinfo=timezone.utc)  # Fri after hours
        got = _slot(db_session, _lead(), earliest, horizon=timedelta(hours=1))
        assert got == earliest

    def test_the_compliance_window_is_respected(self, db_session):
        # A rule allowing only 13:00-16:00: the prior 9-11 cannot be used, so the
        # earliest permitted slot (all equal) wins.
        got = _slot(db_session, _lead(), TUE_10, window=(13, 16, True))
        assert got == TUE_13

    def test_spread_is_deterministic_and_stays_in_the_window(self, db_session):
        lead = _lead()
        a = _slot(db_session, lead, MON_09, spread_key=lead.id)
        b = _slot(db_session, lead, MON_09, spread_key=lead.id)
        assert a == b
        assert datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc) <= a \
            < datetime(2026, 8, 10, 10, 30, tzinfo=timezone.utc)

    def test_flag_off_returns_earliest(self, db_session, monkeypatch):
        system_settings.set(db_session, send_time.FLAG, False)
        assert send_time.place(db_session, None, _lead(), "email", TUE_13) == TUE_13


# --------------------------------------------------------------------------
# Learning
# --------------------------------------------------------------------------


def _sends(db, strategy, sequence, when: datetime, n: int, replies: int, prefix: str):
    for i in range(n):
        lead = m.Lead(strategy_id=strategy.id, source="t", external_id=f"{prefix}{i}",
                      email=f"{prefix}{i}@x.com", status=m.LeadStatus.CONTACTED)
        db.add(lead)
        db.flush()
        db.add(m.Message(sequence_id=sequence.id, lead_id=lead.id, channel=m.ChannelType.EMAIL,
                         step_no=1, template="t", status=m.MessageStatus.SENT, sent_at=when,
                         scheduled_at=when))
        if i < replies:
            db.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.REPLIED, channel="email",
                             ts=when + timedelta(hours=2), meta_json={}))
    db.commit()


class TestLearning:
    MON_15 = datetime(2026, 8, 3, 15, 0, tzinfo=timezone.utc)   # Mon, outside the prior
    TUE_09 = datetime(2026, 8, 4, 9, 0, tzinfo=timezone.utc)    # Tue, inside the prior

    def test_below_the_threshold_the_prior_decides(self, db_session, verified_strategy,
                                                   email_sequence, test_user):
        _sends(db_session, verified_strategy, email_sequence, self.MON_15, 29, 20, "a")
        assert send_time.learned_rates(db_session, test_user.id, "email", TUE_10) is None
        got = _slot(db_session, _lead(), MON_09, strategy=verified_strategy)
        assert got == datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)

    def test_the_accounts_own_replies_move_the_slot(self, db_session, verified_strategy,
                                                    email_sequence, test_user):
        _sends(db_session, verified_strategy, email_sequence, self.MON_15, 40, 20, "a")
        _sends(db_session, verified_strategy, email_sequence, self.TUE_09, 40, 0, "b")
        learned = send_time.learned_rates(db_session, test_user.id, "email", TUE_10)
        assert learned.sends == 80 and learned.replies == 20
        assert learned.slots[(0, 15)] == [40, 20] and learned.slots[(1, 9)] == [40, 0]
        scorer = send_time.Scorer(send_time.plan_for(None, "email")["windows"], learned)
        # Smoothed toward the prior: (20 + 20*m) / (40 + 20), m = p0 * 0.85.
        p0 = 21 / 82
        assert scorer.score(datetime(2026, 8, 10, 15, 0)) == pytest.approx(
            (20 + 20 * p0 * 0.85) / 60)
        # The send path reads learned rates from Redis only; the periodic
        # refresh (send_time.refresh_learning) writes them.
        assert _slot(db_session, _lead(), MON_09, strategy=verified_strategy) == datetime(
            2026, 8, 10, 10, 0, tzinfo=timezone.utc)
        send_time.refresh_learning(db_session, now=TUE_10)
        got = _slot(db_session, _lead(), MON_09, strategy=verified_strategy)
        assert got == datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)
        assert send_time.explain(db_session, verified_strategy, "email")["basis"] == "learned"

    def test_a_reply_is_credited_to_the_send_before_it(self, db_session, verified_strategy,
                                                       email_sequence, test_user):
        _sends(db_session, verified_strategy, email_sequence, self.TUE_09, 30, 0, "c")
        lead = db_session.query(m.Lead).filter_by(external_id="c0").one()
        db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.REPLIED, channel="email",
                                 ts=self.TUE_09 - timedelta(days=1), meta_json={}))
        db_session.commit()
        assert send_time.learned_rates(db_session, test_user.id, "email", TUE_10).replies == 0

    def test_another_accounts_sends_never_count(self, db_session, verified_strategy,
                                               email_sequence, test_user):
        other = m.User(email="other@leadpilot.dev", email_verified=True)
        db_session.add(other)
        db_session.flush()
        product = m.Product(user=other, name="X", description="x", type=m.ProductType.SKILL)
        db_session.add(product)
        db_session.flush()
        strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.NO_CLIENTS)
        db_session.add(strategy)
        db_session.flush()
        seq = m.Sequence(strategy_id=strategy.id, channel=m.ChannelType.EMAIL, name="o")
        db_session.add(seq)
        db_session.commit()
        _sends(db_session, strategy, seq, self.MON_15, 60, 30, "o")
        assert send_time.learned_rates(db_session, test_user.id, "email", TUE_10) is None
        assert send_time.learned_rates(db_session, other.id, "email", TUE_10).sends == 60


# --------------------------------------------------------------------------
# Override
# --------------------------------------------------------------------------


class TestOverride:
    @pytest.mark.parametrize("raw", [
        {"days": [], "start": "09:00", "end": "10:00"},
        {"days": ["Tue"], "start": "9am", "end": "10:00"},
        {"days": ["Tue"], "start": "09:10", "end": "10:00"},
        {"days": ["Tue"], "start": "10:00", "end": "10:15"},
        {"days": ["Funday"], "start": "09:00", "end": "10:00"},
    ])
    def test_bad_windows_are_refused(self, raw):
        with pytest.raises(ValueError):
            send_time.validate_override(raw)

    def test_a_window_outside_sending_hours_is_refused(self):
        with pytest.raises(ValueError, match="outside the permitted sending hours"):
            send_time.validate_override({"days": ["Tue"], "start": "18:00", "end": "20:00"})
        with pytest.raises(ValueError):
            send_time.validate_override({"days": ["Sat", "Sun"], "start": "10:00",
                                         "end": "12:00"})

    def test_override_is_a_hard_window(self, db_session, verified_strategy):
        verified_strategy.send_time_override_json = send_time.validate_override(
            {"days": ["Wed"], "start": "13:00", "end": "14:00"})
        db_session.commit()
        got = _slot(db_session, _lead(), MON_09, strategy=verified_strategy)
        assert got == datetime(2026, 8, 12, 13, 0, tzinfo=timezone.utc)
        # Further than the 72 h horizon is still found (hard window, 8 days).
        got = _slot(db_session, _lead(), datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
                    strategy=verified_strategy)
        assert got == datetime(2026, 8, 19, 13, 0, tzinfo=timezone.utc)

    def test_reslot_moves_future_messages_into_the_window(self, db_session, enrolled,
                                                          verified_strategy):
        msgs = db_session.query(m.Message).filter_by(status=m.MessageStatus.SCHEDULED).all()
        msgs[0].scheduled_at = TUE_10 + timedelta(minutes=2)    # due within 5 min: kept
        for msg in msgs[1:]:
            msg.scheduled_at = TUE_10 + timedelta(hours=1)
        db_session.commit()
        verified_strategy.send_time_override_json = {"days": [3], "start": "14:00",
                                                     "end": "15:00"}
        db_session.commit()
        moved = send_time.reslot(db_session, verified_strategy, now=TUE_10)
        assert moved == 2
        for msg in msgs[1:]:
            db_session.refresh(msg)
            local = msg.scheduled_at.replace(tzinfo=timezone.utc)
            assert local.weekday() == 3 and local.hour == 14
        db_session.refresh(msgs[0])
        assert msgs[0].scheduled_at.replace(tzinfo=timezone.utc) == TUE_10 + timedelta(minutes=2)


# --------------------------------------------------------------------------
# The send-time plan
# --------------------------------------------------------------------------


class _Model:
    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    def complete_json(self, system, prompt, **kw):
        self.calls += 1
        assert "send-time planner" in system
        usage_meter.note("anthropic", "fake-model", 1000, 200)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


class TestPlan:
    GOOD = {"channels": {"email": {"windows": [{"days": ["Mon", "Tue"], "start": "08:30",
                                                "end": "10:00"}],
                                   "reason": "Owners read email before the shop opens."},
                         "linkedin": {"windows": [{"days": ["Sat"], "start": "20:00",
                                                   "end": "21:00"}], "reason": "nope"}}}

    def _run(self, db, strategy, answer, monkeypatch):
        model = _Model(answer)
        monkeypatch.setattr("app.services.anthropic_client.get_client", lambda: model)
        return send_time.ensure_plan(db, strategy, now=TUE_10), model

    def test_a_valid_answer_is_used_per_channel(self, db_session, verified_strategy,
                                                 monkeypatch, test_user):
        plan, model = self._run(db_session, verified_strategy, self.GOOD, monkeypatch)
        assert plan["source"] == "model"
        assert plan["channels"]["email"]["windows"] == [
            {"days": [0, 1], "start": "08:30", "end": "10:00"}]
        assert plan["channels"]["email"]["basis"] == "model"
        # LinkedIn's answer is outside sending hours: the prior stays.
        assert plan["channels"]["linkedin"]["basis"] == "prior"
        db_session.refresh(verified_strategy)
        assert verified_strategy.send_time_plan_json == plan
        rows = db_session.query(m.ApiUsage).filter_by(user_id=test_user.id,
                                                      purpose="send_time").all()
        assert rows, "the model call is metered to the owner as send_time"

    def test_bought_once(self, db_session, verified_strategy, monkeypatch):
        self._run(db_session, verified_strategy, self.GOOD, monkeypatch)
        _, model = self._run(db_session, verified_strategy, self.GOOD, monkeypatch)
        assert model.calls == 0

    @pytest.mark.parametrize("answer", [{}, {"channels": "x"}, RuntimeError("down"),
                                        {"channels": {"email": {"windows": [
                                            {"days": ["Tue"], "start": "09:07",
                                             "end": "10:00"}]}}}])
    def test_bad_answers_keep_the_priors(self, db_session, verified_strategy, monkeypatch,
                                         answer):
        plan, _ = self._run(db_session, verified_strategy, answer, monkeypatch)
        assert plan["source"] == "priors"
        assert plan["channels"]["email"]["basis"] == "prior"

    def test_the_plan_is_what_placement_uses(self, db_session, verified_strategy, monkeypatch):
        self._run(db_session, verified_strategy, self.GOOD, monkeypatch)
        got = _slot(db_session, _lead(), datetime(2026, 8, 10, 7, 0, tzinfo=timezone.utc),
                    strategy=verified_strategy)
        # 08:30 is before the 09:00 sending start: the window's permitted part.
        assert got == datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# The engine and the send path
# --------------------------------------------------------------------------


class TestEngine:
    def test_flag_off_is_the_old_schedule(self, db_session, fake_claude, email_sequence,
                                          verified_leads, gmail_account):
        system_settings.set(db_session, send_time.FLAG, False)
        assert engine.enroll_leads(db_session, email_sequence, now=TUE_13) == 3
        for msg in db_session.query(m.Message).all():
            assert msg.scheduled_at.replace(tzinfo=timezone.utc) == TUE_13

    def test_enrollment_places_step_one_at_the_best_slot(self, db_session, fake_claude,
                                                         email_sequence, verified_leads,
                                                         gmail_account):
        assert engine.enroll_leads(db_session, email_sequence, now=TUE_13) == 3
        for msg in db_session.query(m.Message).all():
            when = msg.scheduled_at.replace(tzinfo=timezone.utc)
            assert when.date().isoformat() == "2026-08-12" and 9 <= when.hour < 11

    def test_lead_ids_narrow_enrollment(self, db_session, fake_claude, email_sequence,
                                        verified_leads, gmail_account):
        assert engine.enroll_leads(db_session, email_sequence, now=TUE_13,
                                   lead_ids=[verified_leads[1].id]) == 1
        assert engine.enroll_leads(db_session, email_sequence, now=TUE_13, lead_ids=[]) == 0

    def test_later_steps_respect_delay_then_best_slot(self, db_session, enrolled):
        msg = db_session.query(m.Message).filter_by(step_no=1).first()
        msg.status = m.MessageStatus.SENT
        msg.sent_at = TUE_13
        db_session.commit()
        nxt = engine.schedule_next_step(db_session, msg, now=TUE_13)   # step 2: +3 days
        when = nxt.scheduled_at.replace(tzinfo=timezone.utc)
        assert when >= TUE_13 + timedelta(days=3)
        assert when.weekday() == 0 and when.hour == 10      # Fri 13:00 -> Mon 10:xx

    def test_send_path_deferral_lands_on_the_best_slot(self, db_session, enrolled,
                                                       monkeypatch, fake_channel):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        msg = db_session.query(m.Message).first()
        night = datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc)
        msg.scheduled_at = night
        db_session.commit()
        assert outreach_tasks.send_message_impl(db_session, msg.id, now=night) == \
            "deferred_window"
        db_session.refresh(msg)
        when = msg.scheduled_at.replace(tzinfo=timezone.utc)
        assert when.date().isoformat() == "2026-08-12" and 9 <= when.hour < 11
        assert fake_channel.sent == []

    def test_send_path_deferral_flag_off_is_window_start(self, db_session, enrolled,
                                                         monkeypatch, fake_channel):
        from app.workers import outreach_tasks

        system_settings.set(db_session, send_time.FLAG, False)
        msg = db_session.query(m.Message).first()
        night = datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc)
        msg.scheduled_at = night
        db_session.commit()
        outreach_tasks.send_message_impl(db_session, msg.id, now=night)
        db_session.refresh(msg)
        assert msg.scheduled_at.replace(tzinfo=timezone.utc) == datetime(
            2026, 8, 12, 9, 0, tzinfo=timezone.utc)


class TestApi:
    def test_send_time_view_and_override(self, client, db_session, verified_strategy, enrolled):
        out = client.get(f"/strategies/{verified_strategy.id}/best-time").json()
        email = out["channels"][0]
        assert email["channel"] == "email" and email["basis"] == "prior"
        assert email["summary"].startswith("Messages go out Tue–Thu 09:00–11:00")
        assert out["timezones"]["leads"] == 3 and out["timezones"]["with_timezone"] == 0
        assert out["timezones"]["fallback"] == {"zone": "UTC", "source": "deployment_default"}

        bad = client.put(f"/strategies/{verified_strategy.id}/best-time",
                         json={"days": ["Tue"], "start": "19:00", "end": "20:00"})
        assert bad.status_code == 422
        ok = client.put(f"/strategies/{verified_strategy.id}/best-time",
                        json={"days": ["Wed", "Thu"], "start": "14:00", "end": "15:30"})
        assert ok.status_code == 202, ok.text      # re-placement runs in the background
        assert ok.json()["override"] == {"days": [2, 3], "start": "14:00", "end": "15:30"}
        assert ok.json()["channels"][0]["basis"] == "override"
        cleared = client.put(f"/strategies/{verified_strategy.id}/best-time",
                             json={"clear": True})
        assert cleared.json()["override"] is None

    def test_another_accounts_strategy_is_404(self, client, db_session):
        other = m.User(email="x@leadpilot.dev", email_verified=True)
        db_session.add(other)
        db_session.flush()
        product = m.Product(user=other, name="X", description="x", type=m.ProductType.SKILL)
        db_session.add(product)
        db_session.flush()
        strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.NO_CLIENTS)
        db_session.add(strategy)
        db_session.commit()
        for path in ("best-time", "send-diagnostics", "autopilot"):
            assert client.get(f"/strategies/{strategy.id}/{path}").status_code == 404
        assert client.put(f"/strategies/{strategy.id}/best-time",
                          json={"clear": True}).status_code == 404

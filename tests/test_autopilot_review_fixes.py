"""Autopilot launch -- fixes for the independent review of d1f3b5c.

The reviewer's probes (scratchpad/review-ap/test_ap_probes.py P1-P8)
demonstrated each defect by asserting the BROKEN behaviour; they are ported
here inverted, asserting the fixed one, together with the other findings:

  M1  a lead enrollment would skip leaves the pool; "launched" only with an
      enrollment; the launch gate is not re-run for nothing      (P2)
  M2  the spend check runs before the ICP model call; the ICP is cached; a
      refusal backs off until the next UTC day and notifies once  (P1)
  M3  a failed / stalled chain publish is retried, then given up with a
      notification -- never stuck in SOURCING                     (P3)
  M5  Autopilot only under daily send approval: opt-in 409, sweep pauses,
      the send path holds an Autopilot message                    (P7)
  M7  learned rates come from Redis (periodic refresh), and a warm send-path
      deferral runs at most one SQL statement for best time       (P5)
  Low override is hard under a narrower rule window and refused when it
      cannot overlap (P4); API keys and SDRs cannot change it; 202 + a
      background reslot; claim heartbeat; ensure_plan only when used; the
      chosen WhatsApp template; the chain's queue; API keys refused (P6).
M4 (diagnostics vs compliance rules, P8) is in tests/test_send_diagnostics.py
with the other pinned reasons; M6 (only Autopilot's own leads) is
TestEndToEnd.test_only_its_own_batch_is_ever_enrolled in
tests/test_autopilot_launch.py; M8b is tests/test_best_time_window_guard.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from app.db import models as m
from app.services import autopilot, send_time, system_settings
from app.services import daily_send_approval as dsa
from tests.conftest import auth_headers

_REAL_SEND_TIME = send_time.enabled
_REAL_DSA = dsa.enabled
NOW = datetime(2026, 8, 11, 13, 0, tzinfo=timezone.utc)          # Tuesday
DOC = "# Strategy\n## Phase 8\nCold email first."


@pytest.fixture(autouse=True)
def best_time_on(monkeypatch):
    monkeypatch.setattr(send_time, "enabled", _REAL_SEND_TIME)


@pytest.fixture(autouse=True)
def approval_on(monkeypatch):
    monkeypatch.setattr(dsa, "enabled", _REAL_DSA)


@pytest.fixture()
def strategy(db_session, product_with_strategy, fake_claude):
    _, s = product_with_strategy(m.FlowType.WITH_CLIENTS)
    s.strategy_document = DOC
    s.status = m.StrategyStatus.VERIFIED
    db_session.commit()
    return s


def _opt_in(db, s, user):
    return autopilot.set_opt_in(db, s, enabled=True, confirmed=True,
                                text_version=autopilot.LAWFUL_BASIS_VERSION,
                                actor_id=user.id, owner_id=user.id, now=NOW)


def _own_batch(db, s, user, emails):
    row = _opt_in(db, s, user)
    batch = m.LeadBatch(strategy_id=s.id, requested_leads=len(emails), icp_criteria_json={},
                        source_provider="t", verifier_provider="t",
                        stage=m.BatchStage.FINALIZED)
    db.add(batch)
    db.flush()
    for i, email in enumerate(emails):
        db.add(m.Lead(strategy_id=s.id, batch_id=batch.id, source="t", external_id=f"o{i}",
                      email=email, status=m.LeadStatus.VERIFIED))
    row.batch_id = batch.id
    row.batch_ids_json = [str(batch.id)]
    row.chain_published_at = NOW
    db.commit()
    return row


def _events(jobs, needle):
    return [e for e in jobs["events"] if e[1] == autopilot.EVENT and needle in e[2]["title"]]


def _model_calls(fake, monkeypatch):
    calls = []
    orig = fake.complete_json

    def wrapped(*a, **kw):
        calls.append(kw.get("system", "")[:40])
        return orig(*a, **kw)

    monkeypatch.setattr(fake, "complete_json", wrapped)
    return calls


# --------------------------------------------------------------------------
# M1 -- skipped leads leave the pool; no false "launched"; no gate re-runs
# --------------------------------------------------------------------------


class TestM1Unreachable:
    def test_suppressed_only_lead_is_not_reported_launched_and_no_gate_reruns(
            self, db_session, test_user, strategy, gmail_account, monkeypatch, queued_jobs):
        from app.api import sequences as sequences_api

        gates = []
        real = sequences_api._launch_checks
        monkeypatch.setattr(sequences_api, "_launch_checks",
                            lambda db, seq: (gates.append(1), real(db, seq))[1])
        _own_batch(db_session, strategy, test_user, ["gone@x.com"])
        db_session.add(m.SuppressionEntry(email="gone@x.com", reason="unsubscribed"))
        db_session.commit()
        states = [autopilot.advance(db_session, strategy.id,
                                    now=NOW + timedelta(minutes=15 * i),
                                    start_chain=lambda b, s: None) for i in range(3)]
        row = autopilot.row_for(db_session, strategy.id)
        assert db_session.query(m.SequenceEnrollment).count() == 0
        assert states == [autopilot.BLOCKED] * 3
        assert row.channels_json["email"]["state"] != "launched"
        assert "1 lead(s) cannot be contacted (suppressed)" in row.state_reason
        assert list(row.unreachable_json.values()) == ["suppressed"]
        assert gates == []

    def test_launched_counts_real_enrollments(self, db_session, test_user, strategy,
                                              gmail_account):
        _own_batch(db_session, strategy, test_user, ["ok@x.com", "gone@x.com"])
        db_session.add(m.SuppressionEntry(email="gone@x.com", reason="unsubscribed"))
        db_session.commit()
        assert autopilot.advance(db_session, strategy.id, now=NOW,
                                 start_chain=lambda b, s: None) == autopilot.LAUNCHED
        row = autopilot.row_for(db_session, strategy.id)
        assert row.channels_json["email"]["enrolled"] == 1
        assert db_session.query(m.SequenceEnrollment).count() == 1
        assert "cannot be contacted (suppressed)" in row.state_reason


# --------------------------------------------------------------------------
# M2 -- spend check before the ICP model call; ICP cached; back-off
# --------------------------------------------------------------------------


class TestM2SpendRefusal:
    def test_refused_spend_buys_no_model_call_and_backs_off(
            self, db_session, test_user, strategy, fake_claude, monkeypatch, queued_jobs):
        from fastapi import HTTPException

        from app.api import spend_guard

        refusals = []

        def refuse(*a, **kw):
            refusals.append(1)
            raise HTTPException(status_code=402, detail="Enrichment spend limit reached")

        monkeypatch.setattr(spend_guard, "guard_enrichment_run", refuse)
        calls = _model_calls(fake_claude, monkeypatch)
        _opt_in(db_session, strategy, test_user)
        started = []
        for i in range(4):
            st = autopilot.advance(db_session, strategy.id,
                                   now=NOW + timedelta(minutes=15 * i),
                                   start_chain=lambda b, s: started.append(b))
            assert st == autopilot.BLOCKED
        assert calls == [] and started == []
        assert refusals == [1], "backed off until the next UTC day after one refusal"
        row = autopilot.row_for(db_session, strategy.id)
        assert row.retry_after.replace(tzinfo=timezone.utc) == datetime(
            2026, 8, 12, tzinfo=timezone.utc)
        assert len(_events(queued_jobs, "cannot find leads")) == 1
        # Next day: tried again (still refused, still no model call).
        autopilot.advance(db_session, strategy.id, now=datetime(2026, 8, 12, 0, 5,
                                                                tzinfo=timezone.utc),
                          start_chain=lambda b, s: started.append(b))
        assert refusals == [1, 1] and calls == []

    def test_the_icp_is_extracted_once_and_cached(self, db_session, test_user, strategy,
                                                  fake_claude, monkeypatch):
        from app.services import icp_extraction

        extractions = []
        real = icp_extraction.extract_icp_criteria
        monkeypatch.setattr(icp_extraction, "extract_icp_criteria",
                            lambda db, s: (extractions.append(1), real(db, s))[1])
        _opt_in(db_session, strategy, test_user)
        publish = []

        def broken(b, s):
            publish.append(b)
            raise ConnectionError("broker down")

        autopilot.advance(db_session, strategy.id, now=NOW, start_chain=broken)
        row = autopilot.row_for(db_session, strategy.id)
        assert extractions == [1] and row.icp_json["titles"] == ["Owner", "Operations Manager"]


# --------------------------------------------------------------------------
# M3 -- chain publish failure / stall
# --------------------------------------------------------------------------


class TestM3ChainPublish:
    def test_a_failed_publish_is_retried_then_given_up_with_a_notice(
            self, db_session, test_user, strategy, fake_claude, queued_jobs):
        _opt_in(db_session, strategy, test_user)

        def broken(b, s):
            raise ConnectionError("redis down")

        st = autopilot.advance(db_session, strategy.id, now=NOW, start_chain=broken)
        assert st == autopilot.SOURCING          # does not raise
        row = autopilot.row_for(db_session, strategy.id)
        assert "Could not start the lead search" in row.state_reason
        published = []
        st = autopilot.advance(db_session, strategy.id, now=NOW + timedelta(minutes=15),
                               start_chain=lambda b, s: published.append(b))
        batch = db_session.query(m.LeadBatch).one()
        assert published == [str(batch.id)], "re-published, same batch"
        assert st == autopilot.SOURCING
        # Published but no progress for over an hour: published again, then given up.
        for i, hours in enumerate((2, 4)):
            autopilot.advance(db_session, strategy.id, now=NOW + timedelta(hours=hours),
                              start_chain=lambda b, s: published.append(b))
        assert len(published) == 2       # attempts 2 and 3; the 4th check gives up
        st = autopilot.advance(db_session, strategy.id, now=NOW + timedelta(hours=6),
                               start_chain=lambda b, s: published.append(b))
        assert st == autopilot.BLOCKED
        db_session.refresh(batch)
        assert batch.stage is m.BatchStage.FAILED and batch.error == autopilot.CHAIN_GAVE_UP
        assert len(_events(queued_jobs, "could not start")) == 1
        assert db_session.query(m.LeadBatch).count() == 1

    def test_a_progressing_chain_is_left_alone(self, db_session, test_user, strategy,
                                               fake_claude):
        _opt_in(db_session, strategy, test_user)
        published = []
        autopilot.advance(db_session, strategy.id, now=NOW,
                          start_chain=lambda b, s: published.append(b))
        batch = db_session.query(m.LeadBatch).one()
        db_session.add(m.Lead(strategy_id=strategy.id, batch_id=batch.id, source="t",
                              external_id="p", email="p@x.com", status=m.LeadStatus.SOURCED))
        db_session.commit()
        autopilot.advance(db_session, strategy.id, now=NOW + timedelta(hours=3),
                          start_chain=lambda b, s: published.append(b))
        assert len(published) == 1


# --------------------------------------------------------------------------
# M5 -- only under daily approval
# --------------------------------------------------------------------------


class TestM5DailyApproval:
    def _put(self, client, s):
        return client.put(f"/strategies/{s.id}/autopilot", json={
            "enabled": True, "lawful_basis_confirmed": True,
            "lawful_basis_text_version": autopilot.LAWFUL_BASIS_VERSION})

    def test_opt_in_refused_when_approval_is_off(self, client, db_session, strategy):
        system_settings.set(db_session, "daily_send_approval_enabled", False)
        r = self._put(client, strategy)
        assert r.status_code == 409 and "daily send approval" in r.json()["detail"]
        assert autopilot.row_for(db_session, strategy.id) is None

    def test_opt_in_refused_when_a_channel_is_not_gated(self, client, db_session, strategy):
        system_settings.set(db_session, "daily_send_approval_channels", "email,linkedin")
        r = self._put(client, strategy)
        assert r.status_code == 409 and "whatsapp" in r.json()["detail"]

    def test_the_text_says_exactly_what_happens(self):
        text = autopilot.LAWFUL_BASIS_TEXT
        assert "never contacts leads added or verified by hand" in text
        assert "job-change tracking" in text
        assert "only runs while daily send approval is on" in text

    def test_sweep_pauses_and_the_send_path_holds_when_approval_goes_off(
            self, db_session, test_user, strategy, gmail_account, fake_channel, monkeypatch,
            queued_jobs):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        _own_batch(db_session, strategy, test_user, ["a@x.com"])
        assert autopilot.advance(db_session, strategy.id, now=NOW,
                                 start_chain=lambda b, s: None) == autopilot.LAUNCHED
        msg = db_session.query(m.Message).one()
        system_settings.set(db_session, "daily_send_approval_enabled", False)
        for i in range(2):
            assert autopilot.advance(db_session, strategy.id,
                                     now=NOW + timedelta(minutes=15 * (i + 1)),
                                     start_chain=lambda b, s: None) == autopilot.PAUSED
        assert len(_events(queued_jobs, "paused")) == 1
        due = msg.scheduled_at.replace(tzinfo=timezone.utc)
        result = outreach_tasks.send_message_impl(db_session, msg.id, now=due)
        assert result == "deferred_autopilot_needs_daily_approval"
        db_session.refresh(msg)
        assert msg.status is m.MessageStatus.SCHEDULED
        assert msg.error.startswith(autopilot.HOLD_PREFIX) and fake_channel.sent == []
        # Approval back on: the sweep resumes and the message goes through the
        # ordinary approval gate again.
        system_settings.set(db_session, "daily_send_approval_enabled", True)
        assert autopilot.advance(db_session, strategy.id, now=NOW + timedelta(hours=1),
                                 start_chain=lambda b, s: None) == autopilot.LAUNCHED
        dsa.approve(db_session, test_user.id, actor_id=test_user.id, channels=["email"],
                    now=due + timedelta(hours=1))
        assert outreach_tasks.send_message_impl(
            db_session, msg.id, now=due + timedelta(hours=1, minutes=1)) == "sent"

    def test_a_non_autopilot_message_is_not_held(self, db_session, enrolled, fake_channel,
                                                 monkeypatch):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        system_settings.set(db_session, "daily_send_approval_enabled", False)
        msg = db_session.query(m.Message).first()
        now = datetime(2026, 8, 11, 10, 0, tzinfo=timezone.utc)
        assert outreach_tasks.send_message_impl(db_session, msg.id, now=now) == "sent"

    def test_an_old_confirmation_text_pauses(self, db_session, test_user, strategy,
                                             queued_jobs):
        row = _opt_in(db_session, strategy, test_user)
        row.text_version = "autopilot-lawful-basis-2026-10-11"
        db_session.commit()
        assert autopilot.advance(db_session, strategy.id, now=NOW,
                                 start_chain=lambda b, s: None) == autopilot.PAUSED
        assert db_session.query(m.LeadBatch).count() == 0


# --------------------------------------------------------------------------
# M7 -- learned rates from Redis; the send path's deferral is cheap
# --------------------------------------------------------------------------


def _count_statements(db, fn):
    stmts = []
    bind = db.get_bind()

    def before(conn, cursor, statement, params, context, executemany):
        stmts.append(statement.split()[0].upper())

    event.listen(bind, "before_cursor_execute", before)
    try:
        fn()
    finally:
        event.remove(bind, "before_cursor_execute", before)
    return stmts


class TestM7Learning:
    def _sends(self, db, s, n):
        seq = m.Sequence(strategy_id=s.id, name="s", channel=m.ChannelType.EMAIL,
                         status=m.SequenceStatus.ACTIVE)
        db.add(seq)
        db.flush()
        for i in range(n):
            lead = m.Lead(strategy_id=s.id, source="t", external_id=f"L{i}",
                          email=f"l{i}@x.com", status=m.LeadStatus.CONTACTED)
            db.add(lead)
            db.flush()
            db.add(m.Message(sequence_id=seq.id, lead_id=lead.id,
                             channel=m.ChannelType.EMAIL, step_no=1, template="t",
                             status=m.MessageStatus.SENT,
                             sent_at=NOW - timedelta(days=1, minutes=i)))
        db.commit()

    def test_place_never_computes_learning_and_a_warm_call_is_one_statement(
            self, db_session, test_user, strategy):
        self._sends(db_session, strategy, 60)
        lead = db_session.query(m.Lead).filter_by(external_id="L0").one()
        send_time.clear_cache(db_session)
        cold = _count_statements(db_session, lambda: send_time.place(
            db_session, strategy, lead, "email", NOW))
        assert not any("messages" in s.lower() for s in cold)
        warm = _count_statements(db_session, lambda: send_time.place(
            db_session, strategy, lead, "email", NOW))
        assert len(warm) <= 1, warm
        assert send_time.cached_learned(test_user.id, "email") is None   # no refresh yet

    def test_the_periodic_refresh_fills_redis(self, db_session, test_user, strategy):
        self._sends(db_session, strategy, 60)
        out = send_time.refresh_learning(db_session, now=NOW)
        assert out["owners"] == 1
        learned = send_time.cached_learned(test_user.id, "email")
        assert learned is not None and learned.sends == 60
        assert send_time.cached_learned(test_user.id, "linkedin") is None   # below 30
        assert send_time.explain(db_session, strategy, "email")["basis"] == "learned"

    def test_send_path_deferral_runs_at_most_one_statement_for_best_time(
            self, db_session, enrolled, monkeypatch, fake_channel):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        counts = []
        real = send_time.place

        def counting(*a, **kw):
            out = []
            stmts = _count_statements(db_session, lambda: out.append(real(*a, **kw)))
            counts.append(len(stmts))
            return out[0]

        monkeypatch.setattr(send_time, "place", counting)
        night = datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc)
        for msg in db_session.query(m.Message).all():
            assert outreach_tasks.send_message_impl(db_session, msg.id,
                                                    now=night) == "deferred_window"
        assert counts[1:] and max(counts[1:]) <= 1, counts

    def test_the_refresh_task_is_scheduled_every_six_hours(self):
        from app.workers.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["send-time-learning-refresh"]
        assert entry["task"] == "leadpilot.autopilot.refresh_learning"
        assert entry["schedule"].hour == {0, 6, 12, 18}


# --------------------------------------------------------------------------
# Low findings
# --------------------------------------------------------------------------


class TestOverrideIsHard:
    def test_no_fallback_to_earliest_under_a_narrower_rule_window(self, db_session, strategy):
        strategy.send_time_override_json = send_time.validate_override(
            {"days": ["Tue", "Wed", "Thu"], "start": "09:00", "end": "10:00"})
        db_session.commit()
        lead = m.Lead(strategy_id=strategy.id, source="t", external_id="o", email="o@x.com",
                      status=m.LeadStatus.VERIFIED)
        db_session.add(lead)
        db_session.commit()
        earliest = datetime(2026, 8, 11, 11, 0, tzinfo=timezone.utc)
        when = send_time.place(db_session, strategy, lead, "email", earliest,
                               window=(11, 13, True))
        assert when != earliest
        assert when >= earliest + send_time.OVERRIDE_HORIZON

    def test_put_refuses_a_window_a_rule_never_overlaps(self, client, db_session, strategy):
        from app.services import compliance_rules as rules

        db_session.add(m.Lead(strategy_id=strategy.id, source="t", external_id="r",
                              email="r@x.com", status=m.LeadStatus.VERIFIED))
        db_session.add(m.ComplianceRule(scope=rules.GLOBAL, region="*", channel="*",
                                        send_start_hour=11, send_end_hour=13))
        db_session.commit()
        r = client.put(f"/strategies/{strategy.id}/best-time",
                       json={"days": ["Tue"], "start": "09:00", "end": "10:00"})
        assert r.status_code == 422 and "never overlaps" in r.json()["detail"]
        ok = client.put(f"/strategies/{strategy.id}/best-time",
                        json={"days": ["Tue"], "start": "11:00", "end": "12:00"})
        assert ok.status_code == 202, ok.text

    @staticmethod
    def _due_message(db, enrolled):
        msg = db.query(m.Message).order_by(m.Message.created_at, m.Message.id).first()
        lead = db.get(m.Lead, msg.lead_id)
        lead.enrichment_json = {**(lead.enrichment_json or {}), "timezone": "UTC"}
        strategy = db.get(m.Sequence, msg.sequence_id).strategy
        strategy.send_time_override_json = send_time.validate_override(
            {"days": ["Tue", "Wed", "Thu"], "start": "09:00", "end": "10:00"})
        system_settings.set(db, "daily_send_approval_enabled", False)
        db.commit()
        return msg

    def test_the_send_path_never_sends_outside_the_override(self, db_session, enrolled,
                                                            fake_channel, monkeypatch):
        """Inside the permitted 09-17 window but outside the person's own
        09-10 window (a message scheduled before the window was saved, or
        parked at the horizon): deferred into the override, never sent."""
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        msg = self._due_message(db_session, enrolled)
        due = datetime(2026, 8, 11, 11, 0, tzinfo=timezone.utc)            # Tue 11:00
        msg.scheduled_at = due
        db_session.commit()
        assert outreach_tasks.send_message_impl(db_session, msg.id, now=due) == \
            "deferred_override_window"
        db_session.refresh(msg)
        placed = msg.scheduled_at.replace(tzinfo=timezone.utc)
        assert msg.status is m.MessageStatus.SCHEDULED and fake_channel.sent == []
        assert datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc) <= placed \
            < datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)              # Wed 09:xx
        assert outreach_tasks.send_message_impl(db_session, msg.id, now=placed) == "sent"

    def test_inside_the_override_it_sends(self, db_session, enrolled, fake_channel,
                                          monkeypatch):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        msg = self._due_message(db_session, enrolled)
        due = datetime(2026, 8, 11, 9, 15, tzinfo=timezone.utc)            # Tue 09:15
        msg.scheduled_at = due
        db_session.commit()
        assert outreach_tasks.send_message_impl(db_session, msg.id, now=due) == "sent"


class TestBestTimePut:
    def test_202_and_a_background_reslot(self, client, db_session, enrolled, verified_strategy,
                                         queued_jobs):
        future = datetime.now(timezone.utc) + timedelta(days=2)
        for msg in db_session.query(m.Message):
            msg.scheduled_at = future
        db_session.commit()
        r = client.put(f"/strategies/{verified_strategy.id}/best-time",
                       json={"days": ["Wed"], "start": "14:00", "end": "15:00"})
        assert r.status_code == 202 and r.json()["rescheduling"] == 3
        assert queued_jobs["reslot"] == [(str(verified_strategy.id),)]
        assert client.put(f"/strategies/{verified_strategy.id}/best-time",
                          json={"clear": True}).status_code == 200

    def test_an_sdr_and_an_api_key_cannot_change_it(self, client, db_session, test_user,
                                                    verified_strategy):
        from app.services import api_keys, workspaces

        ws = workspaces.personal_workspace(db_session, test_user)
        sdr = m.User(email="sdr@bt.dev", email_verified=True)
        db_session.add(sdr)
        db_session.flush()
        db_session.add(m.WorkspaceMember(workspace_id=ws.id, user_id=sdr.id, role="sdr"))
        db_session.commit()
        body = {"days": ["Wed"], "start": "14:00", "end": "15:00"}
        r = client.put(f"/strategies/{verified_strategy.id}/best-time", json=body,
                       headers={**auth_headers(sdr), "X-Workspace-Id": str(ws.id)})
        assert r.status_code == 403
        _, raw = api_keys.create(db_session, test_user.id, "zapier")
        r = client.put(f"/strategies/{verified_strategy.id}/best-time", json=body,
                       headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 403
        db_session.refresh(verified_strategy)
        assert verified_strategy.send_time_override_json is None


class TestApiKeyOptIn:
    def test_an_api_key_cannot_turn_autopilot_on(self, client, db_session, test_user, strategy,
                                                 product_with_strategy):
        from app.services import api_keys

        _, raw = api_keys.create(db_session, test_user.id, "zapier")
        h = {"Authorization": f"Bearer {raw}"}
        body = {"enabled": True, "lawful_basis_confirmed": True,
                "lawful_basis_text_version": autopilot.LAWFUL_BASIS_VERSION}
        assert client.put(f"/strategies/{strategy.id}/autopilot", json=body,
                          headers=h).status_code == 403
        product, _ = product_with_strategy(m.FlowType.WITH_CLIENTS)
        assert client.post(f"/products/{product.id}/strategies", json={"autopilot": body},
                           headers=h).status_code == 403
        assert autopilot.row_for(db_session, strategy.id) is None


class TestClaimHeartbeat:
    def test_a_worker_that_lost_its_claim_does_not_source(self, db_session, test_user, strategy,
                                                          fake_claude, monkeypatch):
        from sqlalchemy import update

        real = autopilot.start_sourcing

        def slow(db, row, s, owner, now):
            # Another worker takes the row over while this one is mid-phase.
            db.execute(update(m.AutopilotLaunch).where(m.AutopilotLaunch.id == row.id)
                       .values(claim_token="other-worker"))
            return real(db, row, s, owner, now)

        monkeypatch.setattr(autopilot, "start_sourcing", slow)
        _opt_in(db_session, strategy, test_user)
        started = []
        assert autopilot.advance(db_session, strategy.id, now=NOW,
                                 start_chain=lambda b, s: started.append(b)) == "busy"
        assert started == [] and db_session.query(m.LeadBatch).count() == 0


class TestPlanOnlyWhenUsed:
    def test_no_model_call_without_autopilot_or_an_active_sequence(
            self, db_session, test_user, strategy, fake_claude, monkeypatch):
        assert send_time.plan_wanted(db_session, strategy) is False
        _opt_in(db_session, strategy, test_user)
        assert send_time.plan_wanted(db_session, strategy) is True
        monkeypatch.setattr(send_time, "enabled", lambda db: False)
        assert send_time.plan_wanted(db_session, strategy) is False

    def test_an_active_sequence_counts(self, db_session, enrolled, verified_strategy):
        assert send_time.plan_wanted(db_session, verified_strategy) is True

    def test_run_pipeline_skips_the_call(self, db_session, strategy, fake_claude, monkeypatch):
        from app.workers import tasks as worker_tasks

        planned = []
        monkeypatch.setattr(send_time, "ensure_plan", lambda *a, **k: planned.append(1))
        monkeypatch.setattr(worker_tasks.run_verification, "delay", lambda *a, **k: None)

        class _NoClose:
            def __init__(self, s):
                self._s = s

            def close(self):
                pass

            def __getattr__(self, n):
                return getattr(self._s, n)

        monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: _NoClose(db_session))
        strategy.status = m.StrategyStatus.PENDING
        strategy.steps_per_phase = 2
        db_session.commit()
        worker_tasks.run_pipeline.run(str(strategy.id))
        assert planned == []


class TestWhatsAppTemplate:
    def _template(self, db, name, body, status=m.WhatsAppTemplateStatus.APPROVED):
        t = m.WhatsAppTemplate(name=name, language="en_US", body=body, status=status)
        db.add(t)
        db.commit()
        return t

    def test_waits_until_a_template_is_chosen_and_uses_only_that_one(
            self, client, db_session, test_user, strategy, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "whatsapp_access_token", "t")
        monkeypatch.setattr(settings, "whatsapp_phone_number_id", "1")
        user = db_session.get(m.User, test_user.id)
        user.plan = "growth"
        db_session.commit()
        self._template(db_session, "aaa_first", "Hi {{1}}. Reply STOP to opt out.")
        mine = self._template(db_session, "zzz_mine", "Hello {{1}}. Reply STOP to opt out.")
        _own_batch(db_session, strategy, test_user, ["a@x.com"])
        autopilot.advance(db_session, strategy.id, now=NOW, start_chain=lambda b, s: None)
        row = autopilot.row_for(db_session, strategy.id)
        assert row.channels_json["whatsapp"]["state"] == "waiting"
        assert "Choose the approved WhatsApp template" in row.channels_json["whatsapp"]["reason"]
        assert "whatsapp" not in (row.sequences_json or {})

        unapproved = self._template(db_session, "draft", "Hi. Reply STOP to opt out.",
                                    status=m.WhatsAppTemplateStatus.DRAFT)
        bad = client.put(f"/strategies/{strategy.id}/autopilot/whatsapp-template",
                         json={"whatsapp_template_id": str(unapproved.id)})
        assert bad.status_code == 422
        ok = client.put(f"/strategies/{strategy.id}/autopilot/whatsapp-template",
                        json={"whatsapp_template_id": str(mine.id)})
        assert ok.status_code == 200 and ok.json()["whatsapp_template_id"] == str(mine.id)
        lead = db_session.query(m.Lead).filter_by(external_id="o0").one()
        lead.email, lead.phone = None, "+15550100"
        db_session.add(m.WhatsAppOptIn(lead_id=lead.id, phone="+15550100",
                                       status=m.OptInStatus.OPTED_IN,
                                       source=list(m.OptInSource)[0]))
        db_session.commit()
        autopilot.advance(db_session, strategy.id, now=NOW + timedelta(minutes=15),
                          start_chain=lambda b, s: None)
        row = autopilot.row_for(db_session, strategy.id)
        seq = db_session.get(m.Sequence, uuid.UUID(row.sequences_json["whatsapp"]))
        assert [s.whatsapp_template_id for s in seq.steps] == [mine.id]


class TestChainQueue:
    def test_the_paid_chain_uses_the_manual_find_leads_routing(self):
        from app.workers import autopilot_tasks
        from app.workers.celery_app import celery_app

        sig = autopilot_tasks.lead_chain("b1", "s1")
        for task in sig.tasks[:-1]:
            assert "queue" not in (task.options or {}), task.task
        manual = celery_app.amqp.router.route({}, "leadpilot.leads.source")["queue"].name
        assert manual == celery_app.amqp.router.route({}, sig.tasks[0].task)["queue"].name

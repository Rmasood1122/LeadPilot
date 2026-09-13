"""Feature 5 — opt-in post-sequence re-engagement.

What must hold:
  * OFF unless the campaign turned it on AND the deployment allows it;
  * only NEUTRAL completed enrollments qualify: lead still `contacted`, no
    reply/booking/decision since the sequence started, never unsubscribed,
    opted out or bounced, not suppressed, not archived, last touch on email,
    and the delay (never shorter than the admin minimum) has passed;
  * the sweep never enqueues past the campaign's daily or weekly allowance;
  * at most ONE re-engagement per enrollment, enforced by the database;
  * every send goes through send_message_impl: suppression still wins, and
    this feature's own switch and cap are re-checked at send time (off =
    cancelled, cap = deferred, never dropped);
  * candidates are found per campaign -- another account's enrollments never
    appear in this campaign's list;
  * only owners and managers change the settings, within the admin ceilings.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.services import message_personalization as personalization
from app.services import reengagement, system_settings, workspaces
from app.workers import outreach_tasks as tasks

from .conftest import auth_headers

UTC = timezone.utc


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture()
def sequence(db_session, verified_strategy):
    seq = m.Sequence(strategy_id=verified_strategy.id, channel=m.ChannelType.EMAIL,
                     name="Outbound", status=m.SequenceStatus.ACTIVE)
    db_session.add(seq)
    db_session.flush()
    db_session.add(m.SequenceStep(sequence_id=seq.id, step_no=1, template="Open on X",
                                  delay_days=0))
    db_session.commit()
    return seq


@pytest.fixture()
def campaign(db_session, verified_strategy):
    verified_strategy.reengagement_enabled = True
    verified_strategy.reengagement_delay_days = 30
    db_session.commit()
    return verified_strategy


def _lead(db, strategy, n, status=m.LeadStatus.CONTACTED):
    row = m.Lead(strategy_id=strategy.id, source="manual", external_id=f"re{n}",
                 full_name=f"Lead {n}", company="Acme Fire",
                 email=f"lead{n}@acme.test", status=status)
    db.add(row)
    db.commit()
    return row


def _completed(db, sequence, lead, *, days_ago=40, channel=m.ChannelType.EMAIL,
               status=m.EnrollmentStatus.COMPLETED):
    enrollment = m.SequenceEnrollment(sequence_id=sequence.id, lead_id=lead.id,
                                      status=status, current_step=1)
    when = datetime.now(UTC) - timedelta(days=days_ago)
    db.add_all([enrollment, m.Message(
        sequence_id=sequence.id, lead_id=lead.id, channel=channel, step_no=1,
        template="Open on X", status=m.MessageStatus.SENT, sent_at=when,
        scheduled_at=when, body="hello", subject="hi")])
    db.commit()
    return enrollment


@pytest.fixture()
def lead(db_session, verified_strategy):
    return _lead(db_session, verified_strategy, 1)


@pytest.fixture()
def enrollment(db_session, sequence, lead):
    return _completed(db_session, sequence, lead)


def _sweep(db, now=None):
    found: list[str] = []
    tasks.check_reengagement_due_impl(db, now=now or datetime.now(UTC), enqueue=found.append)
    return found


def _other_account(db, email="other@elsewhere.test"):
    user = m.User(email=email, email_verified=True)
    db.add(user)
    db.flush()
    product = m.Product(user_id=user.id, name="Other", description="Other",
                        type=m.ProductType.PRODUCT)
    db.add(product)
    db.flush()
    strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.NO_CLIENTS,
                          status=m.StrategyStatus.VERIFIED, reengagement_enabled=True)
    db.add(strategy)
    db.commit()
    return user, strategy


# --------------------------------------------------------------------------
# Eligibility and the sweep
# --------------------------------------------------------------------------


class TestEligibility:
    def test_off_by_default(self, db_session, enrollment):
        assert _sweep(db_session) == []

    def test_an_enabled_campaign_picks_up_a_neutral_completed_lead(self, db_session,
                                                                   campaign, enrollment):
        assert _sweep(db_session) == [str(enrollment.id)]

    def test_the_deployment_kill_switch_wins(self, db_session, campaign, enrollment):
        system_settings.set(db_session, "reengagement_allowed", False)
        assert _sweep(db_session) == []

    def test_inside_the_delay_nothing_fires(self, db_session, campaign, sequence, lead):
        _completed(db_session, sequence, lead, days_ago=10)
        assert _sweep(db_session) == []

    def test_the_admin_minimum_delay_overrides_a_shorter_campaign_setting(
            self, db_session, campaign, sequence, lead):
        campaign.reengagement_delay_days = 1          # below the 14-day minimum
        db_session.commit()
        _completed(db_session, sequence, lead, days_ago=10)
        assert _sweep(db_session) == []

    def test_an_active_enrollment_belongs_to_the_sequence_engine(self, db_session, campaign,
                                                                sequence, lead):
        _completed(db_session, sequence, lead, status=m.EnrollmentStatus.ACTIVE)
        assert _sweep(db_session) == []

    def test_a_reply_during_the_sequence_is_not_neutral(self, db_session, campaign,
                                                        enrollment, lead):
        db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.REPLIED,
                                 channel="email", ts=datetime.now(UTC) - timedelta(days=35)))
        db_session.commit()
        assert _sweep(db_session) == []

    def test_a_reply_from_before_this_sequence_does_not_count(self, db_session, campaign,
                                                              enrollment, lead):
        db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.REPLIED,
                                 channel="email", ts=datetime.now(UTC) - timedelta(days=200)))
        db_session.commit()
        assert _sweep(db_session) == [str(enrollment.id)]

    @pytest.mark.parametrize("event", [m.OutcomeEvent.UNSUBSCRIBED, m.OutcomeEvent.OPTED_OUT,
                                       m.OutcomeEvent.BOUNCED])
    def test_an_exit_ever_disqualifies(self, db_session, campaign, enrollment, lead, event):
        db_session.add(m.Outcome(lead_id=lead.id, event=event, channel="email",
                                 ts=datetime.now(UTC) - timedelta(days=400)))
        db_session.commit()
        assert _sweep(db_session) == []

    @pytest.mark.parametrize("status", [m.LeadStatus.REPLIED, m.LeadStatus.MEETING_BOOKED,
                                        m.LeadStatus.DROPPED, m.LeadStatus.DISQUALIFIED])
    def test_the_lead_must_still_be_contacted(self, db_session, campaign, enrollment, lead,
                                              status):
        lead.status = status
        db_session.commit()
        assert _sweep(db_session) == []

    def test_a_suppressed_lead_is_skipped(self, db_session, campaign, enrollment, lead):
        db_session.add(m.SuppressionEntry(email=lead.email, reason="unsubscribed"))
        db_session.commit()
        assert _sweep(db_session) == []

    def test_a_lead_the_conversion_gate_archived_is_skipped(self, db_session, campaign,
                                                            enrollment, lead):
        lead.engagement_state = "archived"
        db_session.commit()
        assert _sweep(db_session) == []

    def test_a_whatsapp_last_touch_is_out_of_scope(self, db_session, campaign, sequence, lead):
        _completed(db_session, sequence, lead, channel=m.ChannelType.WHATSAPP)
        assert _sweep(db_session) == []

    def test_a_paused_campaign_sends_nothing(self, db_session, campaign, enrollment):
        campaign.campaign_state = "paused_manual"
        db_session.commit()
        assert _sweep(db_session) == []

    def test_the_sweep_stops_at_the_daily_cap(self, db_session, campaign, sequence):
        campaign.reengagement_daily_cap = 2
        db_session.commit()
        for n in range(4):
            _completed(db_session, sequence, _lead(db_session, campaign, 10 + n))
        assert len(_sweep(db_session)) == 2

    def test_the_weekly_cap_counts_what_already_went_out(self, db_session, campaign, sequence):
        campaign.reengagement_daily_cap = 3
        campaign.reengagement_weekly_cap = 3
        db_session.commit()
        three_days_ago = datetime.now(UTC) - timedelta(days=3)
        for n in range(2):
            done = _lead(db_session, campaign, 20 + n)
            db_session.add(m.Message(sequence_id=sequence.id, lead_id=done.id,
                                     channel=m.ChannelType.EMAIL, step_no=2, template="x",
                                     status=m.MessageStatus.SENT, sent_at=three_days_ago,
                                     origin=reengagement.ORIGIN))
        for n in range(3):
            _completed(db_session, sequence, _lead(db_session, campaign, 30 + n))
        db_session.commit()
        assert len(_sweep(db_session)) == 1

    def test_a_sequence_and_lead_from_different_campaigns_are_refused(self, db_session,
                                                                      campaign, lead):
        _, other_strategy = _other_account(db_session)
        foreign_seq = m.Sequence(strategy_id=other_strategy.id, channel=m.ChannelType.EMAIL,
                                 name="Theirs", status=m.SequenceStatus.ACTIVE)
        db_session.add(foreign_seq)
        db_session.commit()
        mixed = _completed(db_session, foreign_seq, lead)
        assert reengagement.ineligibility(db_session, mixed) == "tenant_mismatch"

    def test_candidates_never_include_another_accounts_enrollments(self, db_session, campaign,
                                                                   enrollment):
        _, other_strategy = _other_account(db_session)
        their_seq = m.Sequence(strategy_id=other_strategy.id, channel=m.ChannelType.EMAIL,
                               name="Theirs", status=m.SequenceStatus.ACTIVE)
        db_session.add(their_seq)
        db_session.commit()
        # Same email address on both accounts: routine in B2B.
        theirs = m.Lead(strategy_id=other_strategy.id, source="manual", external_id="t1",
                        email="lead1@acme.test", status=m.LeadStatus.CONTACTED)
        db_session.add(theirs)
        db_session.commit()
        their_enrollment = _completed(db_session, their_seq, theirs)

        mine = reengagement.candidates(db_session, campaign, datetime.now(UTC), 10)
        assert [e.id for e in mine] == [enrollment.id]
        assert their_enrollment.id not in {e.id for e in mine}


# --------------------------------------------------------------------------
# Sending
# --------------------------------------------------------------------------


class TestSend:
    @pytest.fixture(autouse=True)
    def channel(self, monkeypatch):
        from app.integrations.outreach_base import SendResult

        sent: list = []

        class FakeChannel:
            def send(self, outbound):
                sent.append(outbound)
                return SendResult(ok=True, provider_message_id="p1", thread_ref="t1")

        monkeypatch.setattr(tasks, "_get_channel", lambda session, account: FakeChannel())
        return sent

    @pytest.fixture(autouse=True)
    def gmail_account(self, db_session, test_user):
        from app.services import crypto

        row = m.GmailAccount(
            user_id=test_user.id, email_address="me@leadpilot.dev",
            token_ciphertext=crypto.encrypt_json({"access_token": "a", "refresh_token": "r"}),
            token_expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db_session.add(row)
        db_session.commit()
        return row

    @pytest.fixture(autouse=True)
    def in_window(self, monkeypatch):
        """The send window is re-checked at send time and not bypassed; the
        tests move the clock inside it instead."""
        from app.services import sequence_engine as engine

        # `window` is the resolved compliance rule's window (Feature 8).
        monkeypatch.setattr(engine, "in_send_window", lambda dt, tz, window=None: True)

    def _scheduled(self, db, sequence, lead, origin=reengagement.ORIGIN):
        msg = m.Message(sequence_id=sequence.id, lead_id=lead.id,
                        channel=m.ChannelType.EMAIL, step_no=2, template="One last note",
                        status=m.MessageStatus.SCHEDULED, scheduled_at=datetime.now(UTC),
                        origin=origin)
        db.add(msg)
        db.commit()
        return msg

    def test_it_sends_once_and_tags_every_record(self, db_session, campaign, enrollment,
                                                 channel, fake_claude):
        assert tasks.send_reengagement_impl(db_session, enrollment.id) == "sent"

        sent = db_session.query(m.Message).filter_by(origin=reengagement.ORIGIN).all()
        assert len(sent) == 1 and sent[0].status is m.MessageStatus.SENT
        assert sent[0].step_no == 2 and sent[0].template
        outcome = db_session.query(m.Outcome).filter_by(message_id=sent[0].id,
                                                        event=m.OutcomeEvent.SENT).one()
        assert outcome.meta_json["source"] == "reengagement"
        attempt = db_session.query(m.ReengagementAttempt).one()
        assert attempt.status == "sent" and attempt.message_id == sent[0].id

        # A retry, a duplicate task, a second sweep: nothing more.
        assert tasks.send_reengagement_impl(db_session, enrollment.id) == \
            "skipped_already_attempted"
        assert db_session.query(m.Message).filter_by(origin=reengagement.ORIGIN).count() == 1
        assert len(channel) == 1
        db_session.refresh(enrollment)
        assert enrollment.status is m.EnrollmentStatus.COMPLETED

    def test_the_claim_is_unique_in_the_database(self, db_session, campaign, enrollment, lead):
        assert reengagement.claim(db_session, enrollment, lead, campaign) is not None
        assert reengagement.claim(db_session, enrollment, lead, campaign) is None
        assert db_session.query(m.ReengagementAttempt).count() == 1

    def test_turning_it_off_cancels_a_scheduled_message(self, db_session, campaign, sequence,
                                                        lead, enrollment, channel):
        msg = self._scheduled(db_session, sequence, lead)
        campaign.reengagement_enabled = False
        db_session.commit()
        assert tasks.send_message_impl(db_session, msg.id) == "cancelled_reengagement_off"
        db_session.refresh(msg)
        assert msg.status is m.MessageStatus.CANCELLED and channel == []

    def test_an_exhausted_cap_defers_and_never_drops(self, db_session, campaign, sequence,
                                                     lead, enrollment, channel):
        campaign.reengagement_daily_cap = 1
        db_session.commit()
        other = _lead(db_session, campaign, 50)
        now = datetime.now(UTC)
        db_session.add(m.Message(sequence_id=sequence.id, lead_id=other.id,
                                 channel=m.ChannelType.EMAIL, step_no=2, template="x",
                                 status=m.MessageStatus.SENT, sent_at=now,
                                 origin=reengagement.ORIGIN))
        db_session.commit()
        msg = self._scheduled(db_session, sequence, lead)
        assert tasks.send_message_impl(db_session, msg.id, now=now) == \
            "deferred_reengagement_cap"
        db_session.refresh(msg)
        assert msg.status is m.MessageStatus.SCHEDULED
        assert msg.scheduled_at.replace(tzinfo=msg.scheduled_at.tzinfo or UTC) > now
        assert channel == []

    def test_suppression_still_wins_at_send_time(self, db_session, campaign, sequence, lead,
                                                 enrollment, channel):
        msg = self._scheduled(db_session, sequence, lead)
        db_session.add(m.SuppressionEntry(email=lead.email, reason="unsubscribed"))
        db_session.commit()
        assert tasks.send_message_impl(db_session, msg.id) == "cancelled_suppressed"
        assert channel == []

    def test_a_lead_who_engaged_after_scheduling_is_not_sent_to(self, db_session, campaign,
                                                                sequence, lead, enrollment,
                                                                channel):
        msg = self._scheduled(db_session, sequence, lead)
        lead.status = m.LeadStatus.REPLIED
        db_session.commit()
        assert tasks.send_message_impl(db_session, msg.id) == "cancelled_lead_engaged"
        assert channel == []

    def test_an_ordinary_message_is_unaffected_by_the_toggle(self, db_session, sequence, lead,
                                                             enrollment, channel, fake_claude):
        msg = self._scheduled(db_session, sequence, lead, origin=None)
        assert tasks.send_message_impl(db_session, msg.id) == "sent"


class TestBrief:
    def test_the_prompt_carries_the_no_invention_rule(self, db_session, campaign, lead,
                                                      monkeypatch):
        systems: list[str] = []

        class Capture:
            def complete_json(self, system, prompt, max_tokens=None):
                systems.append(system)
                return {"brief": "Ask whether inspection scheduling is still worth a look."}

        monkeypatch.setattr(personalization, "get_client", lambda: Capture())
        brief = personalization.build_reengagement_brief(db_session, campaign, lead)
        assert brief == "Ask whether inspection scheduling is still worth a look."
        assert "Never invent" in systems[0] and "not now" in systems[0]

    def test_a_failed_model_call_falls_back(self, db_session, campaign, lead, monkeypatch):
        class Down:
            def complete_json(self, system, prompt, max_tokens=None):
                raise RuntimeError("anthropic unavailable")

        monkeypatch.setattr(personalization, "get_client", lambda: Down())
        assert personalization.build_reengagement_brief(db_session, campaign, lead) == \
            personalization.FALLBACK_REENGAGEMENT_BRIEF


# --------------------------------------------------------------------------
# Settings API
# --------------------------------------------------------------------------


def _as(user, ws=None):
    headers = auth_headers(user)
    if ws is not None:
        headers["X-Workspace-Id"] = str(ws.id)
    return headers


class TestApi:
    def test_defaults_are_off_and_preview_the_eligible_count(self, client, verified_strategy,
                                                            enrollment):
        body = client.get(f"/strategies/{verified_strategy.id}/reengagement").json()
        assert body["enabled"] is False
        assert (body["daily_cap"], body["weekly_cap"], body["delay_days"]) == (10, 25, 30)
        assert body["eligible_now"] == 1
        assert body["channels"] == ["email"]

    def test_the_owner_turns_it_on(self, client, db_session, verified_strategy):
        r = client.put(f"/strategies/{verified_strategy.id}/reengagement",
                       json={"enabled": True, "daily_cap": 5, "weekly_cap": 20,
                             "delay_days": 45})
        assert r.status_code == 200, r.text
        db_session.refresh(verified_strategy)
        assert verified_strategy.reengagement_enabled is True
        assert verified_strategy.reengagement_delay_days == 45

    def test_sdrs_and_viewers_cannot_change_it(self, client, db_session, test_user,
                                               verified_strategy):
        ws = workspaces.personal_workspace(db_session, test_user)
        for role in ("sdr", "viewer"):
            user = m.User(email=f"{role}@re.dev", email_verified=True)
            db_session.add(user)
            db_session.flush()
            db_session.add(m.WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=role))
            db_session.commit()
            r = client.put(f"/strategies/{verified_strategy.id}/reengagement",
                           json={"enabled": True}, headers=_as(user, ws))
            assert r.status_code == 403
        db_session.refresh(verified_strategy)
        assert verified_strategy.reengagement_enabled is False

    @pytest.mark.parametrize("body", [
        {"daily_cap": 26}, {"weekly_cap": 101}, {"delay_days": 13},
        {"daily_cap": 10, "weekly_cap": 5},
    ])
    def test_values_outside_the_ceilings_are_refused(self, client, verified_strategy, body):
        r = client.put(f"/strategies/{verified_strategy.id}/reengagement", json=body)
        assert r.status_code == 422

    def test_the_kill_switch_refuses_enabling(self, client, db_session, verified_strategy):
        system_settings.set(db_session, "reengagement_allowed", False)
        r = client.put(f"/strategies/{verified_strategy.id}/reengagement",
                       json={"enabled": True})
        assert r.status_code == 409

    def test_another_accounts_campaign_is_404(self, client, db_session):
        _, theirs = _other_account(db_session)
        assert client.get(f"/strategies/{theirs.id}/reengagement").status_code == 404
        assert client.put(f"/strategies/{theirs.id}/reengagement",
                          json={"enabled": False}).status_code == 404


def test_beat_runs_the_sweep_on_the_outreach_queue():
    from app.workers.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["check-reengagement-due"]
    assert entry["task"] == "leadpilot.outreach.check_reengagement_due"
    assert celery_app.amqp.router.route({}, entry["task"])["queue"].name == "outreach"

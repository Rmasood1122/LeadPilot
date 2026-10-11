"""Scheduled sends after a plan downgrade (app/services/plan_holds.py).

Before this, plans were checked only when a sequence was created or launched
(app/api/sequences.py _enforce_plan). Messages already scheduled kept sending
after a downgrade: a Free account kept sending WhatsApp steps and steps past
its 5-step limit. Now the send chokepoint re-checks the owner's CURRENT plan
and HOLDS what it no longer covers (FAILED + 'plan_limit: ', kept, visible,
never transmitted, enrollment not stopped).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import plan_holds, send_holds
from app.workers import outreach_tasks
from app.workers.outreach_tasks import check_followup_due_impl, send_message_impl
from tests.conftest import NOW, auth_headers, entitle_owner

# The shipped grandfather instant, captured before any test moves it.
REAL_EFFECTIVE_AT = plan_holds.PLAN_HOLD_EFFECTIVE_AT


@pytest.fixture(autouse=True)
def _check_every_enrollment(monkeypatch):
    """Enrollments in these tests are created at wall-clock time, which may be
    before PLAN_HOLD_EFFECTIVE_AT. Most tests are about the check itself, so
    the grandfather line is moved to the distant past here; TestGrandfather
    restores the real one and sets created_at explicitly."""
    monkeypatch.setattr(plan_holds, "PLAN_HOLD_EFFECTIVE_AT",
                        datetime(2000, 1, 1, tzinfo=timezone.utc))


def _owner(db, strategy) -> m.User:
    return db.get(m.User, db.get(m.Product, strategy.product_id).user_id)


def _first_scheduled(db, sequence, lead=None):
    q = select(m.Message).where(m.Message.sequence_id == sequence.id,
                                m.Message.status == m.MessageStatus.SCHEDULED)
    if lead is not None:
        q = q.where(m.Message.lead_id == lead.id)
    return db.execute(q.order_by(m.Message.created_at)).scalars().first()


def _email_message_at_step(db, sequence, lead, step_no):
    """An email message for `step_no` of a sequence that has that step."""
    for n in range(1, step_no + 1):
        if not db.execute(select(m.SequenceStep).where(
                m.SequenceStep.sequence_id == sequence.id,
                m.SequenceStep.step_no == n)).scalar_one_or_none():
            db.add(m.SequenceStep(sequence_id=sequence.id, step_no=n,
                                  template=f"Step {n} brief", delay_days=0))
    msg = m.Message(sequence_id=sequence.id, lead_id=lead.id, channel=m.ChannelType.EMAIL,
                    step_no=step_no, template=f"Step {step_no} brief",
                    status=m.MessageStatus.SCHEDULED, scheduled_at=NOW)
    db.add(msg)
    db.commit()
    return msg


@pytest.fixture()
def wa_message(db_session, multichannel_sequence, wa_lead):
    """A WhatsApp template step scheduled for a lead with a real opt-in,
    launched while the owner was on Starter (multichannel_sequence)."""
    db_session.add(m.SequenceEnrollment(sequence_id=multichannel_sequence.id,
                                        lead_id=wa_lead.id,
                                        status=m.EnrollmentStatus.ACTIVE, current_step=1))
    step = db_session.execute(select(m.SequenceStep).where(
        m.SequenceStep.sequence_id == multichannel_sequence.id,
        m.SequenceStep.step_no == 2)).scalar_one()
    msg = m.Message(sequence_id=multichannel_sequence.id, lead_id=wa_lead.id,
                    channel=m.ChannelType.WHATSAPP, step_no=2, template=step.template,
                    whatsapp_kind=m.WhatsAppStepKind.TEMPLATE,
                    whatsapp_template_id=step.whatsapp_template_id,
                    status=m.MessageStatus.SCHEDULED, scheduled_at=NOW)
    db_session.add(msg)
    db_session.commit()
    return msg


# --------------------------------------------------------------------------
# The rule (pure)
# --------------------------------------------------------------------------


class TestSendBlock:
    @pytest.mark.parametrize("plan,channel,blocked", [
        (m.PlanTier.FREE, m.ChannelType.EMAIL, False),
        (m.PlanTier.FREE, m.ChannelType.WHATSAPP, True),
        (m.PlanTier.STARTER, m.ChannelType.WHATSAPP, False),
        (m.PlanTier.STARTER, m.ChannelType.LINKEDIN, True),
        (m.PlanTier.GROWTH, m.ChannelType.LINKEDIN, False),
        (m.PlanTier.GROWTH, m.ChannelType.PHONE, True),
        (m.PlanTier.SCALE, m.ChannelType.PHONE, False),
    ])
    def test_channel(self, plan, channel, blocked):
        owner = m.User(email="o@x.io", plan=plan)
        msg = m.Message(channel=channel, step_no=1)
        assert (plan_holds.send_block(owner, msg) is not None) is blocked

    @pytest.mark.parametrize("plan,step,blocked", [
        (m.PlanTier.FREE, 5, False), (m.PlanTier.FREE, 6, True),
        (m.PlanTier.STARTER, 10, False), (m.PlanTier.STARTER, 11, True),
        # Scale's steps are capped at SEQUENCE_STEP_CAP (20) since the plan
        # advertising fix (product defect #18); the API never creates more.
        (m.PlanTier.SCALE, 20, False), (m.PlanTier.SCALE, 21, True),
    ])
    def test_step_limit_for_sequence_messages(self, plan, step, blocked):
        owner = m.User(email="o@x.io", plan=plan)
        msg = m.Message(channel=m.ChannelType.EMAIL, step_no=step, origin=None)
        assert (plan_holds.send_block(owner, msg) is not None) is blocked

    @pytest.mark.parametrize("origin", ["reengagement", "reply_copilot", "notnow_memory"])
    def test_non_sequence_origins_are_not_numbered_steps(self, origin):
        owner = m.User(email="o@x.io", plan=m.PlanTier.FREE)
        msg = m.Message(channel=m.ChannelType.EMAIL, step_no=9, origin=origin)
        assert plan_holds.send_block(owner, msg) is None

    def test_non_sequence_origins_still_need_the_channel(self):
        owner = m.User(email="o@x.io", plan=m.PlanTier.FREE)
        msg = m.Message(channel=m.ChannelType.WHATSAPP, step_no=1, origin="reply_copilot")
        assert "whatsapp" in plan_holds.send_block(owner, msg)

    def test_the_hold_prefix_is_a_registered_send_hold(self):
        assert plan_holds.ERROR_PREFIX in send_holds.HOLD_PREFIXES


# --------------------------------------------------------------------------
# The send chokepoint
# --------------------------------------------------------------------------


class TestAtSendTime:
    def test_downgraded_channel_is_held_not_sent(self, db_session, fake_claude, wa_message,
                                                 verified_strategy, fake_channel):
        entitle_owner(db_session, verified_strategy, m.PlanTier.FREE)  # the downgrade
        out = send_message_impl(db_session, wa_message.id, channel=fake_channel, now=NOW)
        assert out == "held_plan_limit"
        db_session.refresh(wa_message)
        assert wa_message.status is m.MessageStatus.FAILED
        assert wa_message.error.startswith("plan_limit: ")
        assert "whatsapp" in wa_message.error
        assert fake_channel.sent == []
        enrollment = db_session.execute(select(m.SequenceEnrollment).where(
            m.SequenceEnrollment.lead_id == wa_message.lead_id)).scalar_one()
        assert enrollment.status is m.EnrollmentStatus.ACTIVE  # not stopped

    def test_hold_is_audited(self, db_session, fake_claude, wa_message, verified_strategy,
                             fake_channel):
        entitle_owner(db_session, verified_strategy, m.PlanTier.FREE)
        send_message_impl(db_session, wa_message.id, channel=fake_channel, now=NOW)
        row = db_session.execute(select(m.ComplianceAuditLog).where(
            m.ComplianceAuditLog.message_id == wa_message.id)).scalar_one()
        assert row.decision == "held_plan_limit"
        assert row.checks_json["plan"] == "free"

    def test_entitled_channel_still_sends(self, db_session, fake_claude, wa_message,
                                          fake_channel):
        assert send_message_impl(db_session, wa_message.id, channel=fake_channel,
                                 now=NOW) == "sent"
        assert len(fake_channel.sent) == 1

    def test_step_past_the_plan_limit_is_held(self, db_session, fake_claude, enrolled,
                                              verified_leads, fake_channel):
        lead = verified_leads[0]
        msg = _email_message_at_step(db_session, enrolled, lead, 6)
        out = send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert out == "held_plan_limit"
        db_session.refresh(msg)
        assert msg.error == ("plan_limit: Free plan allows 5 sequence steps; "
                             "this is step 6.")
        assert fake_channel.sent == []

    def test_steps_inside_the_limit_keep_sending(self, db_session, fake_claude, enrolled,
                                                 verified_leads, fake_channel):
        msg = _first_scheduled(db_session, enrolled, verified_leads[0])
        assert msg.step_no == 1
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"

    def test_an_upgrade_lifts_the_step_limit(self, db_session, fake_claude, enrolled,
                                             verified_leads, verified_strategy, fake_channel):
        entitle_owner(db_session, verified_strategy, m.PlanTier.GROWTH)
        msg = _email_message_at_step(db_session, enrolled, verified_leads[0], 6)
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"

    def test_a_held_message_is_never_redispatched(self, db_session, fake_claude, wa_message,
                                                  verified_strategy, fake_channel):
        entitle_owner(db_session, verified_strategy, m.PlanTier.FREE)
        send_message_impl(db_session, wa_message.id, channel=fake_channel, now=NOW)
        enqueued = outreach_tasks.dispatch_due_messages_impl(
            db_session, now=NOW, enqueue=lambda mid: None)
        assert str(wa_message.id) not in enqueued
        # and a retry of the task is a no-op
        assert send_message_impl(db_session, wa_message.id, channel=fake_channel,
                                 now=NOW) == "skipped_failed"
        assert fake_channel.sent == []

    def test_follow_up_sweep_does_not_copy_a_held_step(self, db_session, fake_claude,
                                                       enrolled, verified_leads,
                                                       fake_channel):
        """The held message is the pending message for its step; without
        that the 30-minute sweep would recreate step 6 forever."""
        from datetime import timedelta

        lead = verified_leads[0]
        first = _first_scheduled(db_session, enrolled, lead)
        assert send_message_impl(db_session, first.id, channel=fake_channel, now=NOW) == "sent"
        # The engine scheduled step 2; pretend it is step 6 on a 5-step plan.
        nxt = _first_scheduled(db_session, enrolled, lead)
        nxt.step_no = 6
        db_session.commit()
        assert send_message_impl(db_session, nxt.id, channel=fake_channel,
                                 now=NOW) == "held_plan_limit"
        later = NOW + timedelta(days=30)
        due = check_followup_due_impl(db_session, now=later, enqueue=lambda *_a: None)
        enrollment = db_session.execute(select(m.SequenceEnrollment).where(
            m.SequenceEnrollment.lead_id == lead.id)).scalar_one()
        assert (str(enrollment.id), 7) not in due and all(
            eid != str(enrollment.id) for eid, _ in due)

    def test_plan_check_failure_fails_closed(self, db_session, fake_claude, wa_message,
                                             fake_channel, monkeypatch):
        def boom(*_a, **_kw):
            raise RuntimeError("plans unavailable")

        monkeypatch.setattr(plan_holds, "send_block", boom)
        out = send_message_impl(db_session, wa_message.id, channel=fake_channel, now=NOW)
        assert out == "deferred_plan_check_unavailable"
        db_session.refresh(wa_message)
        assert wa_message.status is m.MessageStatus.SCHEDULED
        assert fake_channel.sent == []

    def test_suppression_still_cancels_before_the_plan_holds(
            self, db_session, fake_claude, wa_message, wa_lead, verified_strategy,
            fake_channel):
        """A message that must never go out is cancelled, not merely held."""
        entitle_owner(db_session, verified_strategy, m.PlanTier.FREE)
        db_session.add(m.SuppressionEntry(email=wa_lead.email, reason="unsubscribed"))
        db_session.commit()
        out = send_message_impl(db_session, wa_message.id, channel=fake_channel, now=NOW)
        assert out == "cancelled_suppressed"


# --------------------------------------------------------------------------
# Review fixes: grandfathering, exemptions, release sweep, stats, beat
# --------------------------------------------------------------------------


def _enrollment_of(db, message):
    return db.execute(select(m.SequenceEnrollment).where(
        m.SequenceEnrollment.sequence_id == message.sequence_id,
        m.SequenceEnrollment.lead_id == message.lead_id)).scalar_one()


def _downgrade(db, strategy):
    entitle_owner(db, strategy, m.PlanTier.FREE)


class TestGrandfather:
    @pytest.fixture(autouse=True)
    def _real_line(self, monkeypatch):
        monkeypatch.setattr(plan_holds, "PLAN_HOLD_EFFECTIVE_AT", REAL_EFFECTIVE_AT)

    def test_the_line_is_2026_10_12_utc(self):
        assert REAL_EFFECTIVE_AT == datetime(2026, 10, 12, tzinfo=timezone.utc)

    def test_enrollment_from_before_the_line_keeps_sending(
            self, db_session, fake_claude, wa_message, verified_strategy, fake_channel):
        _enrollment_of(db_session, wa_message).created_at = REAL_EFFECTIVE_AT - timedelta(seconds=1)
        _downgrade(db_session, verified_strategy)
        assert send_message_impl(db_session, wa_message.id, channel=fake_channel,
                                 now=NOW) == "sent"

    def test_enrollment_from_the_line_on_is_checked(
            self, db_session, fake_claude, wa_message, verified_strategy, fake_channel):
        _enrollment_of(db_session, wa_message).created_at = REAL_EFFECTIVE_AT
        _downgrade(db_session, verified_strategy)
        assert send_message_impl(db_session, wa_message.id, channel=fake_channel,
                                 now=NOW) == "held_plan_limit"


class TestExemptions:
    def test_admin_owner_is_never_held(self, db_session, fake_claude, wa_message,
                                       verified_strategy, fake_channel):
        _downgrade(db_session, verified_strategy)
        _owner(db_session, verified_strategy).is_admin = True
        db_session.commit()
        assert send_message_impl(db_session, wa_message.id, channel=fake_channel,
                                 now=NOW) == "sent"

    def _copilot(self, db, message, owner, *, auto_sent):
        message.origin = "reply_copilot"
        db.add(m.ReplyDraft(user_id=owner.id, reply_id=uuid.uuid4(), lead_id=message.lead_id,
                            channel="email", intent="positive", status="approved",
                            draft_body="b", message_id=message.id, auto_sent=auto_sent))
        db.commit()

    def test_person_approved_copilot_answer_is_exempt(self, db_session, verified_strategy):
        owner = _owner(db_session, verified_strategy)
        owner.plan = m.PlanTier.FREE
        msg = m.Message(channel=m.ChannelType.WHATSAPP, step_no=1, id=uuid.uuid4(),
                        lead_id=uuid.uuid4())
        self._copilot(db_session, msg, owner, auto_sent=False)
        assert plan_holds.check(db_session, owner, msg, None) is None

    def test_auto_sent_copilot_answer_is_checked(self, db_session, verified_strategy):
        owner = _owner(db_session, verified_strategy)
        owner.plan = m.PlanTier.FREE
        msg = m.Message(channel=m.ChannelType.WHATSAPP, step_no=1, id=uuid.uuid4(),
                        lead_id=uuid.uuid4())
        self._copilot(db_session, msg, owner, auto_sent=True)
        assert plan_holds.check(db_session, owner, msg, None) is not None

    def test_copilot_origin_without_a_draft_is_checked(self, db_session, verified_strategy):
        owner = _owner(db_session, verified_strategy)
        owner.plan = m.PlanTier.FREE
        msg = m.Message(channel=m.ChannelType.WHATSAPP, step_no=1, id=uuid.uuid4(),
                        origin="reply_copilot")
        assert plan_holds.check(db_session, owner, msg, None) is not None


class TestReleaseSweep:
    def _hold(self, db, wa_message, strategy, fake_channel):
        _downgrade(db, strategy)
        assert send_message_impl(db, wa_message.id, channel=fake_channel,
                                 now=NOW) == "held_plan_limit"

    def test_upgrade_releases_the_hold_and_it_then_sends(
            self, db_session, fake_claude, wa_message, verified_strategy, fake_channel):
        self._hold(db_session, wa_message, verified_strategy, fake_channel)
        entitle_owner(db_session, verified_strategy, m.PlanTier.STARTER)  # upgrade
        counts = plan_holds.release_sweep(db_session, now=NOW)
        assert counts == {"held_leads": 1, "released_leads": 1, "released_messages": 1}
        db_session.refresh(wa_message)
        assert wa_message.status is m.MessageStatus.SCHEDULED and wa_message.error is None
        assert send_message_impl(db_session, wa_message.id, channel=fake_channel,
                                 now=NOW) == "sent"

    def test_without_an_upgrade_nothing_is_released(
            self, db_session, fake_claude, wa_message, verified_strategy, fake_channel):
        self._hold(db_session, wa_message, verified_strategy, fake_channel)
        assert plan_holds.release_sweep(db_session, now=NOW)["released_leads"] == 0
        db_session.refresh(wa_message)
        assert wa_message.status is m.MessageStatus.FAILED

    def test_other_guards_holds_are_not_released(self, db_session, fake_claude, wa_message):
        wa_message.status = m.MessageStatus.FAILED
        wa_message.error = "bounce_shield: unverified address"
        db_session.commit()
        assert plan_holds.release_sweep(db_session, now=NOW)["held_leads"] == 0
        db_session.refresh(wa_message)
        assert wa_message.error.startswith("bounce_shield: ")

    def test_beat_runs_it_every_15_minutes_on_default(self):
        import importlib

        from app.workers.celery_app import celery_app

        importlib.import_module("app.workers.plan_hold_tasks")
        entry = celery_app.conf.beat_schedule["plan-hold-release"]
        assert entry["task"] == "leadpilot.plan_holds.release"
        assert sorted(entry["schedule"].minute) == [11, 26, 41, 56]
        assert "leadpilot.plan_holds.release" in celery_app.tasks
        assert celery_app.amqp.router.route({}, entry["task"])["queue"].name == "default"


class TestCampaignStats:
    def test_holds_are_not_delivery_failures_and_are_reported(
            self, db_session, fake_claude, client, enrolled, verified_leads,
            verified_strategy, fake_channel):
        leads = verified_leads
        first = _first_scheduled(db_session, enrolled, leads[0])
        assert send_message_impl(db_session, first.id, channel=fake_channel, now=NOW) == "sent"
        held = _email_message_at_step(db_session, enrolled, leads[1], 6)
        assert send_message_impl(db_session, held.id, channel=fake_channel,
                                 now=NOW) == "held_plan_limit"
        body = client.get(f"/strategies/{verified_strategy.id}/campaign",
                          headers=auth_headers(_owner(db_session, verified_strategy))).json()
        assert body["channels"]["email"]["delivery_rate"] == 1.0
        assert body["plan_holds"] == {
            "count": 1, "reasons": ["Free plan allows 5 sequence steps; this is step 6."]}

    def test_a_real_failure_still_counts(self, db_session, fake_claude, client, enrolled,
                                         verified_leads, verified_strategy, fake_channel):
        first = _first_scheduled(db_session, enrolled, verified_leads[0])
        send_message_impl(db_session, first.id, channel=fake_channel, now=NOW)
        second = _first_scheduled(db_session, enrolled, verified_leads[1])
        second.status = m.MessageStatus.FAILED
        second.error = None
        db_session.commit()
        body = client.get(f"/strategies/{verified_strategy.id}/campaign").json()
        assert body["channels"]["email"]["delivery_rate"] == 0.0

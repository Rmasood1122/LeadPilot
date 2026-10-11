"""Send-path gap fixes (docs/program/fixes/send-path-gaps.md) -- the
behaviour fixes. The legal/safety GUARD fixes (1, 3, 4, 7) are in
tests/test_send_path_guards.py, kept apart so they can be sealed on their own.

Every test FAILS on the code before the fix unless it is marked as a control
(it pins behaviour that must not change). Offline and deterministic.

  2  review-held step counted as pending; rejected step never re-created
  5  "not now" re-engagement touch is not cancelled by its own reply's stop
  6  WhatsApp/phone-first sequences enroll phone-only leads; honest stop reason
  8  every emitted event is registered; alert events are subscribable
  9  webhook retries reach the documented 2-hour retry
  10 per-HOST double-booking guard across booking pages
"""

from __future__ import annotations

import ast
import pathlib
from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import sequence_engine as engine
from app.services import system_settings
from app.workers import outreach_tasks as tasks
from tests.conftest import NOW

REPO = pathlib.Path(__file__).resolve().parents[1]


def _enrollment(db, sequence, lead):
    return db.execute(select(m.SequenceEnrollment).where(
        m.SequenceEnrollment.sequence_id == sequence.id,
        m.SequenceEnrollment.lead_id == lead.id)).scalar_one()


# ===========================================================================
# 2. Review queue vs the follow-up sweep
# ===========================================================================


@pytest.fixture()
def sweep_lead(db_session, verified_strategy):
    lead = m.Lead(strategy_id=verified_strategy.id, source="manual", full_name="Omar Ali",
                  company="Beta", email="omar@beta.test", status=m.LeadStatus.CONTACTED)
    db_session.add(lead)
    db_session.commit()
    return lead


def _msg(db, sequence, lead, step_no, status, *, hours_ago=100, error=None, now=None):
    when = (now or datetime.now(UTC)) - timedelta(hours=hours_ago)
    row = m.Message(sequence_id=sequence.id, lead_id=lead.id, channel=m.ChannelType.EMAIL,
                    step_no=step_no, template=f"Step {step_no} brief", status=status,
                    sent_at=when if status is m.MessageStatus.SENT else None,
                    scheduled_at=when, body="hello", subject="hi", error=error)
    db.add(row)
    db.commit()
    return row


def _active(db, sequence, lead, current_step=1):
    row = m.SequenceEnrollment(sequence_id=sequence.id, lead_id=lead.id,
                               status=m.EnrollmentStatus.ACTIVE, current_step=current_step,
                               planned_steps=3, steps_sent=current_step)
    db.add(row)
    db.commit()
    return row


class TestReviewHeldStepsAndTheSweep:
    def test_a_step_waiting_in_review_is_pending(self, db_session, email_sequence,
                                                 sweep_lead):
        enrollment = _active(db_session, email_sequence, sweep_lead)
        _msg(db_session, email_sequence, sweep_lead, 1, m.MessageStatus.SENT)
        _msg(db_session, email_sequence, sweep_lead, 2, m.MessageStatus.AWAITING_REVIEW,
             hours_ago=1)
        queued = []
        tasks.check_followup_due_impl(db_session, enqueue=lambda e, s: queued.append((e, s)))
        assert queued == []
        assert tasks.send_followup_impl(db_session, enrollment.id, 2) == \
            "skipped_already_pending"
        assert db_session.query(m.Message).count() == 2

    def test_rejecting_a_step_advances_the_sequence(self, db_session, email_sequence,
                                                    sweep_lead, test_user):
        from app.services import send_review

        enrollment = _active(db_session, email_sequence, sweep_lead)
        _msg(db_session, email_sequence, sweep_lead, 1, m.MessageStatus.SENT)
        held = _msg(db_session, email_sequence, sweep_lead, 2,
                    m.MessageStatus.AWAITING_REVIEW, hours_ago=1)
        review = m.SendReview(message_id=held.id, lead_id=sweep_lead.id,
                              user_id=test_user.id, status=send_review.PENDING,
                              triggers_json=[])
        db_session.add(review)
        db_session.commit()

        send_review.reject(db_session, review, note="Wrong moment for this one", now=NOW)

        db_session.refresh(held)
        db_session.refresh(enrollment)
        assert held.status is m.MessageStatus.CANCELLED
        assert held.error.startswith("rejected in review: ")
        nxt = db_session.execute(select(m.Message).where(
            m.Message.lead_id == sweep_lead.id, m.Message.step_no == 3)).scalar_one()
        assert nxt.status is m.MessageStatus.SCHEDULED
        assert enrollment.status is m.EnrollmentStatus.ACTIVE
        assert enrollment.current_step == 2
        assert enrollment.steps_sent == 1, "a rejected step was never received"

    def test_rejecting_the_last_step_completes_the_enrollment(
            self, db_session, email_sequence, sweep_lead, test_user):
        from app.services import send_review

        enrollment = _active(db_session, email_sequence, sweep_lead, current_step=2)
        held = _msg(db_session, email_sequence, sweep_lead, 3,
                    m.MessageStatus.AWAITING_REVIEW, hours_ago=1)
        review = m.SendReview(message_id=held.id, lead_id=sweep_lead.id,
                              user_id=test_user.id, status=send_review.PENDING,
                              triggers_json=[])
        db_session.add(review)
        db_session.commit()
        send_review.reject(db_session, review, note="Not this one, thanks", now=NOW)
        db_session.refresh(enrollment)
        assert enrollment.status is m.EnrollmentStatus.COMPLETED

    def test_the_sweep_never_recreates_a_rejected_step(self, db_session, email_sequence,
                                                       sweep_lead):
        """An enrollment rejected before the fix: nothing pending, step 2
        rejected. The sweep moves on to step 3, never back to step 2."""
        enrollment = _active(db_session, email_sequence, sweep_lead)
        _msg(db_session, email_sequence, sweep_lead, 1, m.MessageStatus.SENT)
        _msg(db_session, email_sequence, sweep_lead, 2, m.MessageStatus.CANCELLED,
             hours_ago=50, error="rejected in review: Wrong moment")
        queued = []
        tasks.check_followup_due_impl(db_session, enqueue=lambda e, s: queued.append((e, s)))
        assert queued == [(str(enrollment.id), 3)]
        assert tasks.send_followup_impl(db_session, enrollment.id, 2) == \
            "skipped_rejected_in_review"

    def test_rejecting_a_step_the_sequence_already_passed_does_not_advance_again(
            self, db_session, email_sequence, sweep_lead, test_user):
        """Review finding 2 (ported probe): a pre-fix sweep copy of the held
        step 2 was SENT and the engine scheduled step 3; rejecting the stale
        review must not schedule step 3 a second time or rewind current_step."""
        from app.services import send_review

        enrollment = _active(db_session, email_sequence, sweep_lead, current_step=2)
        _msg(db_session, email_sequence, sweep_lead, 1, m.MessageStatus.SENT, hours_ago=300)
        held = _msg(db_session, email_sequence, sweep_lead, 2,
                    m.MessageStatus.AWAITING_REVIEW, hours_ago=200)
        _msg(db_session, email_sequence, sweep_lead, 2, m.MessageStatus.SENT, hours_ago=100)
        _msg(db_session, email_sequence, sweep_lead, 3, m.MessageStatus.SCHEDULED,
             hours_ago=-24)
        review = m.SendReview(message_id=held.id, lead_id=sweep_lead.id,
                              user_id=test_user.id, status=send_review.PENDING,
                              triggers_json=[])
        db_session.add(review)
        db_session.commit()
        send_review.reject(db_session, review, note="old", now=NOW)
        db_session.refresh(enrollment)
        step3 = db_session.execute(select(m.Message).where(
            m.Message.lead_id == sweep_lead.id, m.Message.step_no == 3,
            m.Message.status == m.MessageStatus.SCHEDULED)).scalars().all()
        assert len(step3) == 1
        assert enrollment.current_step == 2

    def test_rejecting_does_not_advance_when_a_later_step_is_already_queued(
            self, db_session, email_sequence, sweep_lead, test_user):
        from app.services import send_review

        enrollment = _active(db_session, email_sequence, sweep_lead, current_step=1)
        held = _msg(db_session, email_sequence, sweep_lead, 2,
                    m.MessageStatus.AWAITING_REVIEW, hours_ago=1)
        _msg(db_session, email_sequence, sweep_lead, 3, m.MessageStatus.AWAITING_REVIEW,
             hours_ago=-24)
        review = m.SendReview(message_id=held.id, lead_id=sweep_lead.id,
                              user_id=test_user.id, status=send_review.PENDING,
                              triggers_json=[])
        db_session.add(review)
        db_session.commit()
        send_review.reject(db_session, review, note="not this one", now=NOW)
        db_session.refresh(enrollment)
        assert db_session.query(m.Message).filter(m.Message.step_no == 3).count() == 1
        assert enrollment.current_step == 1

    def test_no_generated_follow_up_replaces_a_rejected_last_step(
            self, db_session, email_sequence, sweep_lead):
        _active(db_session, email_sequence, sweep_lead, current_step=2)
        _msg(db_session, email_sequence, sweep_lead, 1, m.MessageStatus.SENT, hours_ago=200)
        _msg(db_session, email_sequence, sweep_lead, 2, m.MessageStatus.SENT)
        _msg(db_session, email_sequence, sweep_lead, 3, m.MessageStatus.CANCELLED,
             hours_ago=50, error="rejected in review: no")
        queued = []
        tasks.check_followup_due_impl(db_session, enqueue=lambda e, s: queued.append((e, s)))
        assert queued == []


# ===========================================================================
# 5. "Not now" re-engagement touch
# ===========================================================================


@pytest.fixture()
def not_now(db_session, email_sequence, gmail_account, verified_strategy, test_user):
    """A prospect who replied "not now" to step 1: sequence stopped by that
    reply, a due plan, auto-send on."""
    from app.services import reengagement_memory as memory

    system_settings.set(db_session, "reengagement_memory_auto_send", True)
    lead = m.Lead(strategy_id=verified_strategy.id, source="apollo", external_id="NN1",
                  full_name="Nadia Iqbal", title="Operations Manager", company="Gamma",
                  email="nadia@gamma.test", status=m.LeadStatus.REPLIED)
    db_session.add(lead)
    db_session.flush()
    replied_at = NOW - timedelta(days=95)
    db_session.add(m.Message(sequence_id=email_sequence.id, lead_id=lead.id,
                             channel=m.ChannelType.EMAIL, step_no=1, template="Step 1 brief",
                             status=m.MessageStatus.SENT, sent_at=replied_at - timedelta(days=1),
                             body="hello", subject="hi", thread_ref="thread-1"))
    reply = m.InboundReply(lead_id=lead.id, channel="email", from_address=lead.email,
                           subject="Re: hi", body="Locked in until November, try then.",
                           classification="not_interested", intent_label="not_now",
                           received_at=replied_at, created_at=replied_at)
    db_session.add(reply)
    db_session.flush()
    enrollment = m.SequenceEnrollment(sequence_id=email_sequence.id, lead_id=lead.id,
                                      status=m.EnrollmentStatus.ACTIVE, current_step=1)
    db_session.add(enrollment)
    db_session.commit()
    engine.stop_enrollment(db_session, enrollment, reason="replied_not_interested",
                           now=replied_at + timedelta(minutes=1))
    plan = m.ReengagementPlan(lead_id=lead.id, user_id=test_user.id,
                              strategy_id=lead.strategy_id, source_reply_id=reply.id,
                              reason_kind=memory.CONTRACT,
                              reason_text="Locked in until November",
                              due_at=NOW - timedelta(hours=1), status=memory.SCHEDULED)
    db_session.add(plan)
    db_session.commit()
    memory.run_due(db_session, now=NOW)
    db_session.refresh(plan)
    assert plan.message_id is not None, "the touch must have been scheduled"
    return {"lead": lead, "reply": reply, "plan": plan, "enrollment": enrollment,
            "message": db_session.get(m.Message, plan.message_id)}


class TestNotNowTouch:
    def test_the_touch_is_sent_on_the_day_it_is_due(self, db_session, not_now,
                                                     fake_channel, fake_claude):
        out = tasks.send_message_impl(db_session, not_now["message"].id,
                                      channel=fake_channel, now=NOW)
        assert out == "sent"
        assert len(fake_channel.sent) == 1
        enrollment = not_now["enrollment"]
        db_session.refresh(enrollment)
        assert enrollment.status is m.EnrollmentStatus.STOPPED, "the touch does not restart it"
        assert db_session.query(m.Message).filter(
            m.Message.status == m.MessageStatus.SCHEDULED).count() == 0

    def test_a_stop_for_any_other_reason_still_cancels_it(self, db_session, not_now,
                                                          fake_channel, fake_claude):
        not_now["enrollment"].stop_reason = "kill_signal_cold"
        db_session.commit()
        out = tasks.send_message_impl(db_session, not_now["message"].id,
                                      channel=fake_channel, now=NOW)
        assert out == "cancelled_stopped"
        assert fake_channel.sent == []

    def test_a_newer_reply_cancels_it(self, db_session, not_now, fake_channel, fake_claude):
        later = NOW - timedelta(days=10)
        db_session.add(m.InboundReply(lead_id=not_now["lead"].id, channel="email",
                                      from_address="nadia@gamma.test", body="Actually...",
                                      classification="question", received_at=later,
                                      created_at=later))
        db_session.commit()
        out = tasks.send_message_impl(db_session, not_now["message"].id,
                                      channel=fake_channel, now=NOW)
        assert out == "cancelled_prospect_wrote_again"
        assert fake_channel.sent == []

    def test_switching_auto_send_off_cancels_a_scheduled_touch(
            self, db_session, not_now, fake_channel, fake_claude):
        system_settings.set(db_session, "reengagement_memory_auto_send", False)
        out = tasks.send_message_impl(db_session, not_now["message"].id,
                                      channel=fake_channel, now=NOW)
        assert out == "cancelled_reengagement_off"
        assert fake_channel.sent == []

    def test_suppression_still_applies(self, db_session, not_now, fake_channel, fake_claude):
        db_session.add(m.SuppressionEntry(email="nadia@gamma.test", reason="unsubscribed"))
        db_session.commit()
        out = tasks.send_message_impl(db_session, not_now["message"].id,
                                      channel=fake_channel, now=NOW)
        assert out.startswith("cancelled_")
        assert fake_channel.sent == []

    def test_a_scheduled_touch_can_still_be_cancelled(self, client, db_session, not_now):
        """Review finding 3: once the sweep scheduled the touch (plan `sent`),
        cancelling the plan used to 409, leaving no way to stop it."""
        plan = not_now["plan"]
        listed = client.get(f"/leads/{not_now['lead'].id}/reengagement-plans").json()
        assert listed[0]["touch_pending"] is True
        resp = client.post(f"/reengagement/plans/{plan.id}/cancel",
                           json={"reason": "spoke to them by phone"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "cancelled"
        message = not_now["message"]
        db_session.refresh(message)
        assert message.status is m.MessageStatus.CANCELLED

    def test_a_touch_that_already_went_out_cannot_be_cancelled(
            self, client, db_session, not_now, fake_channel, fake_claude):
        assert tasks.send_message_impl(db_session, not_now["message"].id,
                                       channel=fake_channel, now=NOW) == "sent"
        resp = client.post(f"/reengagement/plans/{not_now['plan'].id}/cancel",
                           json={"reason": "too late now"})
        assert resp.status_code == 409
        assert "gone out" in resp.json()["detail"]

    def test_auto_send_defaults_off(self):
        assert system_settings.DEFAULTS["reengagement_memory_auto_send"][0] is False


# ===========================================================================
# 6. WhatsApp-first sequences and the honest no-address stop
# ===========================================================================


@pytest.fixture()
def whatsapp_first(db_session, verified_strategy, approved_template):
    seq = m.Sequence(strategy_id=verified_strategy.id, channel=m.ChannelType.WHATSAPP,
                     name="WA first", status=m.SequenceStatus.ACTIVE)
    db_session.add(seq)
    db_session.flush()
    db_session.add(m.SequenceStep(
        sequence_id=seq.id, step_no=1, template="wa intro", delay_days=0,
        channel=m.ChannelType.WHATSAPP, whatsapp_kind=m.WhatsAppStepKind.TEMPLATE,
        whatsapp_template_id=approved_template.id,
        variable_mapping_json={"1": "lead.first_name", "2": "brief: their pain"}))
    db_session.commit()
    return seq


class TestChannelAddress:
    def test_a_phone_only_lead_is_enrolled_in_a_whatsapp_first_sequence(
            self, db_session, whatsapp_first, verified_strategy, fake_claude):
        phone_only = m.Lead(strategy_id=verified_strategy.id, source="manual",
                            full_name="Phone Only", phone="+923001112233",
                            status=m.LeadStatus.VERIFIED)
        email_only = m.Lead(strategy_id=verified_strategy.id, source="manual",
                            full_name="Email Only", email="only@email.test",
                            status=m.LeadStatus.VERIFIED)
        db_session.add_all([phone_only, email_only])
        db_session.commit()
        assert engine.enroll_leads(db_session, whatsapp_first, now=NOW) == 1
        enrolled_ids = {e.lead_id for e in db_session.query(m.SequenceEnrollment)}
        assert enrolled_ids == {phone_only.id}

    def test_a_missing_address_stops_with_an_honest_reason(
            self, db_session, multichannel_sequence, verified_strategy, fake_channel):
        lead = m.Lead(strategy_id=verified_strategy.id, source="manual",
                      full_name="No Phone", email="nophone@x.test",
                      status=m.LeadStatus.CONTACTED)
        db_session.add(lead)
        db_session.flush()
        enrollment = m.SequenceEnrollment(sequence_id=multichannel_sequence.id,
                                          lead_id=lead.id, status=m.EnrollmentStatus.ACTIVE,
                                          current_step=1)
        msg = m.Message(sequence_id=multichannel_sequence.id, lead_id=lead.id,
                        channel=m.ChannelType.WHATSAPP, step_no=2, template="wa follow",
                        status=m.MessageStatus.SCHEDULED, scheduled_at=NOW)
        db_session.add_all([enrollment, msg])
        db_session.commit()
        out = tasks.send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert out == "cancelled_no_address"
        db_session.refresh(enrollment)
        assert enrollment.stop_reason == engine.STOP_NO_ADDRESS
        assert enrollment.stop_category == "no_address"
        from app.services import sequence_completion
        assert not sequence_completion.is_authorised(enrollment.stop_category), \
            "a data gap is not a compliance decision"


# ===========================================================================
# 8. Events: registered, deliverable, subscribable
# ===========================================================================


def _emitted_events() -> dict[str, bool]:
    """Every literal event name passed to enqueue_event / emit in app/, and
    whether any call site builds a webhook payload for it."""
    found: dict[str, bool] = {}
    for path in (REPO / "app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name not in ("enqueue_event", "emit"):
                continue
            literals = [a.value for a in node.args
                        if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            if not literals:
                continue
            payload = any(k.arg == "webhook_payload"
                          and not (isinstance(k.value, ast.Constant) and k.value.value is None)
                          for k in node.keywords)
            found[literals[0]] = found.get(literals[0], False) or payload
    return found


class TestEvents:
    def test_every_emitted_event_is_registered(self):
        from app.services import event_bus

        emitted = _emitted_events()
        assert {"send_needs_review", "mailbox_paused", "reengagement_due",
                "reply_draft_approved"} <= set(emitted)
        assert sorted(set(emitted) - set(event_bus.EVENTS)) == []

    def test_every_event_that_builds_a_payload_can_be_subscribed_to(self):
        from app.services import webhook_delivery as wd

        with_payload = {e for e, payload in _emitted_events().items() if payload}
        assert sorted(with_payload - set(wd.EVENT_DESCRIPTIONS)) == []
        assert wd.normalize_events(["domain_blacklisted", "deliverability_warning",
                                    "mailbox_paused", "send_needs_review",
                                    "reengagement_due", "reply_draft_approved"])

    def test_every_subscribable_event_has_a_sample_and_is_a_hub_event(self):
        from app.services import event_bus
        from app.services import webhook_delivery as wd

        assert set(wd.EVENT_DESCRIPTIONS) <= set(wd.SAMPLES)
        assert set(wd.EVENT_DESCRIPTIONS) <= set(event_bus.EVENTS)

    def _deliver(self, db_session, test_user, queued_jobs, monkeypatch, event):
        """Emit what the call site queued, to a target subscribed to it."""
        from app.services import event_bus
        from app.services import webhook_delivery as wd

        monkeypatch.setattr(event_bus, "_push", lambda *a, **k: 0)
        monkeypatch.setattr(event_bus, "_slack", lambda *a, **k: False)
        monkeypatch.setattr(wd, "public_destination", lambda url: True)
        from app.core.crypto import encrypt

        db_session.add(m.WebhookTarget(user_id=test_user.id, url="https://hooks.example.com/x",
                                       event_types=[event], active=True,
                                       secret_encrypted=encrypt("s")))
        db_session.commit()
        (user_id, name, kwargs), = [e for e in queued_jobs["events"] if e[1] == event]
        result = event_bus.emit(db_session, user_id, name, **kwargs)
        assert result["webhooks"] == 1
        assert set(kwargs["webhook_payload"]) == set(wd.SAMPLES[event]), \
            "the documented sample must have the shape the code sends"

    def test_mailbox_paused_reaches_a_subscriber(self, db_session, test_user, queued_jobs,
                                                 monkeypatch):
        from app.services import mailbox_health
        from app.workers import notification_tasks

        row = m.MailboxHealth(user_id=test_user.id, mailbox_ref="mbx-1",
                              address="me@x.test", score=30, reasons_json=["bounces"])
        mailbox_health._notify_paused(notification_tasks, test_user.id, row)
        self._deliver(db_session, test_user, queued_jobs, monkeypatch, "mailbox_paused")

    def test_send_needs_review_reaches_a_subscriber(self, db_session, test_user, queued_jobs,
                                                    monkeypatch, sweep_lead):
        from app.services import send_review

        review = m.SendReview(message_id=None, lead_id=sweep_lead.id, user_id=test_user.id,
                              status=send_review.PENDING,
                              triggers_json=[{"code": "vip_title", "label": "VIP"}])
        send_review._notify(db_session, review, sweep_lead)
        self._deliver(db_session, test_user, queued_jobs, monkeypatch, "send_needs_review")

    def test_reengagement_due_reaches_a_subscriber(self, db_session, test_user, queued_jobs,
                                                   monkeypatch, sweep_lead):
        from app.services import reengagement_memory as memory

        plan = m.ReengagementPlan(lead_id=sweep_lead.id, user_id=test_user.id,
                                  due_at=NOW, status=memory.DUE, reason_kind=memory.BUDGET)
        db_session.add(plan)
        db_session.commit()
        memory._notify_due(db_session, plan)
        self._deliver(db_session, test_user, queued_jobs, monkeypatch, "reengagement_due")


# ===========================================================================
# 9. Webhook retries reach the 2-hour retry
# ===========================================================================


class TestWebhookRetries:
    def test_the_fifth_failure_schedules_the_two_hour_retry(self, db_session, test_user,
                                                           queued_jobs, monkeypatch):
        from app.core.crypto import encrypt
        from app.services import webhook_delivery as wd

        class _Http:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def post(self, url, content=None, headers=None):
                return type("R", (), {"status_code": 500})()

        monkeypatch.setattr(wd, "_http", _Http)
        monkeypatch.setattr(wd, "public_destination", lambda url: True)
        monkeypatch.setattr(wd, "_record_exhaustion", lambda *a: None)
        target = m.WebhookTarget(user_id=test_user.id, url="https://hooks.example.com/x",
                                 event_types=["reply_received"], active=True,
                                 secret_encrypted=encrypt("s"))
        db_session.add(target)
        db_session.commit()
        delivery = wd.create_delivery(db_session, target, "reply_received", {}, enqueue=False)
        for _ in range(5):
            assert wd.deliver(db_session, delivery.id) == "retry"
        assert queued_jobs["webhooks"][-1][1] == "7200"
        assert wd.deliver(db_session, delivery.id) == "exhausted"
        db_session.refresh(delivery)
        assert delivery.attempts == wd.MAX_ATTEMPTS == 6


# ===========================================================================
# 10. Per-host double booking
# ===========================================================================


@pytest.fixture()
def no_calendar_broker(monkeypatch):
    from app.workers import calendar_tasks

    monkeypatch.setattr(calendar_tasks.on_booking_created, "delay", lambda *a, **k: None,
                        raising=False)
    monkeypatch.setattr(calendar_tasks.on_booking_cancelled, "delay", lambda *a, **k: None,
                        raising=False)


@pytest.fixture()
def two_pages(db_session, test_user, no_calendar_broker):
    db_session.add_all([
        m.CalendarAvailability(user_id=test_user.id, day_of_week=day, start_time=time(9, 0),
                               end_time=time(17, 0), timezone="UTC", is_active=True)
        for day in range(5)])
    intro = m.CalendarBookingPage(user_id=test_user.id, slug="intro-30", title="Intro",
                                  duration_minutes=30, is_active=True)
    deep = m.CalendarBookingPage(user_id=test_user.id, slug="deep-60", title="Deep dive",
                                 duration_minutes=60, is_active=True)
    db_session.add_all([intro, deep])
    db_session.commit()
    return intro, deep


def _live(page, start, minutes, status=m.BookingStatus.CONFIRMED):
    from app.services import calendar_service as cal

    live = status in (m.BookingStatus.CONFIRMED, m.BookingStatus.PENDING)
    return m.CalendarBooking(booking_page_id=page.id, invitee_name="Someone",
                             invitee_email="someone@x.test", start_at=start,
                             end_at=start + timedelta(minutes=minutes), status=status,
                             slot_key=cal.slot_key_for(start) if live else None)


class TestHostDoubleBooking:
    def test_a_concurrent_booking_on_another_page_is_seen_after_the_lock(
            self, anon_client, db_session, two_pages, monkeypatch):
        """Simulates the race: the other request (60-min page, overlapping)
        commits while this one waits for the host lock. The slot check runs
        AFTER the lock, so it sees that booking and refuses."""
        from app.services import calendar_service as cal

        _intro, deep = two_pages
        slot = anon_client.get("/calendar/booking-pages/intro-30/slots?days=14").json()[1]
        start = datetime.fromisoformat(slot["start_at"])
        original = cal.lock_host_calendar

        def lock_then_competitor_commits(db, host):
            db.add(_live(deep, start - timedelta(minutes=30), 60))
            db.commit()
            return original(db, host)

        monkeypatch.setattr(cal, "lock_host_calendar", lock_then_competitor_commits)
        resp = anon_client.post("/calendar/booking-pages/intro-30/book", json={
            "start_at": slot["start_at"], "invitee_name": "Second",
            "invitee_email": "second@x.test"})
        assert resp.status_code == 409, resp.text
        assert db_session.query(m.CalendarBooking).count() == 1

    def test_the_lock_is_a_row_lock_on_postgresql(self, db_session, test_user):
        from sqlalchemy.dialects import postgresql

        from app.services import calendar_service as cal

        seen = []
        real = db_session.execute

        def spy(stmt, *a, **k):
            seen.append(stmt)
            return real(stmt, *a, **k)

        db_session.execute = spy
        try:
            cal.lock_host_calendar(db_session, test_user.id)
        finally:
            del db_session.execute
        sql = str(seen[0].compile(dialect=postgresql.dialect()))
        # FOR NO KEY UPDATE (key_share): serialises booking writes for one
        # host without blocking foreign-key inserts that reference the user.
        assert "FOR NO KEY UPDATE" in sql and "users" in sql

    def test_reactivating_a_cancelled_booking_into_an_overlap_is_refused(
            self, client, db_session, two_pages):
        intro, deep = two_pages
        start = (datetime.now(UTC) + timedelta(days=7)).replace(hour=10, minute=0, second=0,
                                                                microsecond=0)
        db_session.add(_live(deep, start, 60))
        cancelled = _live(intro, start + timedelta(minutes=30), 30,
                          status=m.BookingStatus.CANCELLED)
        db_session.add(cancelled)
        db_session.commit()
        resp = client.patch(f"/calendar/bookings/{cancelled.id}", json={"status": "confirmed"})
        assert resp.status_code == 409, resp.text
        db_session.refresh(cancelled)
        assert cancelled.status is m.BookingStatus.CANCELLED

    def test_reactivating_into_a_free_time_still_works(self, client, db_session, two_pages):
        intro = two_pages[0]
        start = (datetime.now(UTC) + timedelta(days=7)).replace(hour=14, minute=0, second=0,
                                                                microsecond=0)
        cancelled = _live(intro, start, 30, status=m.BookingStatus.CANCELLED)
        db_session.add(cancelled)
        db_session.commit()
        resp = client.patch(f"/calendar/bookings/{cancelled.id}", json={"status": "confirmed"})
        assert resp.status_code == 200, resp.text

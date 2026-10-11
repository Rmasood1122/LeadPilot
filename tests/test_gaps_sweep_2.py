"""gaps-sweep-2 (docs/program/fixes/gaps-sweep-2.md) -- behaviour fixes.

Every test here FAILS on the base (master be2f9e0) unless it is marked as a
control (it pins behaviour that must not change). Offline and deterministic.

  1  every subscribable webhook event is emitted with a payload somewhere
  2  stopping an enrollment cancels review-held and guard-held messages and
     closes their reviews
  3  closed / disqualified / dropped statuses stop sequences, whichever writer
     set them; the send path refuses a sequence step to a closed lead
  4  meeting_outcome_* is a recognised stop category
  5  re-engagement still_appropriate checks phone and LinkedIn suppression
  6  Reply Copilot answers carry In-Reply-To / References
  7  LinkedIn and WhatsApp inbound: classification is set before the reply
     intelligence job is published
  8  held messages carry a hold reason in the conversation thread
  9  mv-results ownership and data on SQLite (dialect-neutral)
  11 bounce-shield report uses the compliance-lowered threshold
  12 env examples and docs name settings that exist
  17 no raw exception text from the API handlers fixed here
  18 auto_promote_winners runs (and promotes) on SQLite
"""

from __future__ import annotations

import ast
import pathlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import sequence_engine as engine
from tests.conftest import NOW, auth_headers

REPO = pathlib.Path(__file__).resolve().parents[1]


def _lead(db, strategy, *, status=m.LeadStatus.CONTACTED, email="omar@beta.test",
          phone=None, linkedin=None, ext="GS2"):
    lead = m.Lead(strategy_id=strategy.id, source="manual", external_id=ext,
                  full_name="Omar Ali", company="Beta", email=email, phone=phone,
                  linkedin_url=linkedin, status=status)
    db.add(lead)
    db.commit()
    return lead


def _enroll(db, sequence, lead, *, step=1):
    enrollment = m.SequenceEnrollment(sequence_id=sequence.id, lead_id=lead.id,
                                      status=m.EnrollmentStatus.ACTIVE, current_step=step)
    db.add(enrollment)
    db.commit()
    return enrollment


def _msg(db, sequence, lead, step_no, status, *, error=None, origin=None):
    row = m.Message(sequence_id=sequence.id, lead_id=lead.id, channel=m.ChannelType.EMAIL,
                    step_no=step_no, template=f"Step {step_no} brief", status=status,
                    scheduled_at=datetime.now(UTC) - timedelta(minutes=5),
                    body="hello", subject="hi", error=error, origin=origin)
    db.add(row)
    db.commit()
    return row


# ===========================================================================
# 1. Every subscribable event can actually be delivered
# ===========================================================================


class TestSubscribableEventsAreDelivered:
    def test_every_subscribable_event_is_emitted_with_a_webhook_payload(self):
        """A subscribable event emitted only without `webhook_payload` can never
        reach a webhook target: emit() skips webhooks when the payload is None.
        call_completed was the one."""
        from app.services import webhook_delivery as wd
        from tests.test_send_path_gaps import _emitted_events

        emitted = _emitted_events()
        never = sorted(e for e in wd.EVENT_DESCRIPTIONS if not emitted.get(e))
        assert never == []


# ===========================================================================
# 2. A stop closes the review queue and guard holds too
# ===========================================================================


class TestStopClosesHeldMessages:
    def test_a_review_held_message_is_cancelled_and_its_review_closed(
            self, db_session, email_sequence, verified_strategy, test_user):
        from app.services import send_review

        lead = _lead(db_session, verified_strategy)
        enrollment = _enroll(db_session, email_sequence, lead)
        held = _msg(db_session, email_sequence, lead, 1, m.MessageStatus.AWAITING_REVIEW)
        review = m.SendReview(message_id=held.id, lead_id=lead.id, user_id=test_user.id,
                              status=send_review.PENDING,
                              triggers_json=[{"code": "vip_title", "label": "VIP"}])
        db_session.add(review)
        db_session.commit()

        engine.stop_enrollment(db_session, enrollment, reason="unsubscribed")

        db_session.refresh(held)
        db_session.refresh(review)
        assert held.status is m.MessageStatus.CANCELLED
        assert held.error == "enrollment stopped: unsubscribed"
        assert review.status == send_review.REJECTED
        assert review.decided_by_user_id is None
        assert review.decision_note == "closed by system: enrollment stopped: unsubscribed"
        assert send_review.pending_count(db_session, test_user.id) == 0
        # History tells it apart from a person's rejection (review L6).
        out = send_review.review_out(db_session, review)
        assert out["closed_by_system"] is True

    def test_a_guard_held_message_is_cancelled(self, db_session, email_sequence,
                                               verified_strategy):
        from app.services import send_holds

        lead = _lead(db_session, verified_strategy)
        enrollment = _enroll(db_session, email_sequence, lead)
        held = _msg(db_session, email_sequence, lead, 1, m.MessageStatus.FAILED,
                    error=f"{send_holds.BOUNCE_SHIELD_PREFIX}address unverified")
        engine.stop_enrollment(db_session, enrollment, reason="bounced")
        db_session.refresh(held)
        assert held.status is m.MessageStatus.CANCELLED

    def test_control_sent_and_plain_failed_messages_are_untouched(
            self, db_session, email_sequence, verified_strategy):
        lead = _lead(db_session, verified_strategy)
        enrollment = _enroll(db_session, email_sequence, lead)
        sent = _msg(db_session, email_sequence, lead, 1, m.MessageStatus.SENT)
        failed = _msg(db_session, email_sequence, lead, 2, m.MessageStatus.FAILED,
                      error="smtp 550")
        engine.stop_enrollment(db_session, enrollment, reason="replied_interested")
        db_session.refresh(sent)
        db_session.refresh(failed)
        assert sent.status is m.MessageStatus.SENT
        assert failed.status is m.MessageStatus.FAILED and failed.error == "smtp 550"


# ===========================================================================
# 4. Logging a meeting outcome is a recognised, authorised stop
# ===========================================================================


class TestMeetingOutcomeStopCategory:
    @pytest.mark.parametrize("kind", ["closed_won", "closed_lost", "needs_follow_up",
                                      "not_a_fit", "interested"])
    def test_meeting_outcome_reasons_are_categorised(self, kind):
        from app.services import sequence_completion as completion

        category = completion.categorize(f"meeting_outcome_{kind}")
        assert category == completion.MEETING_OUTCOME
        assert completion.is_authorised(category)
        assert completion.LABELS[category] == "Meeting outcome logged"

    def test_log_outcome_stops_with_the_meeting_outcome_category(
            self, db_session, email_sequence, verified_strategy, test_user):
        from app.services import meeting_followup

        lead = _lead(db_session, verified_strategy, status=m.LeadStatus.MEETING_BOOKED)
        enrollment = _enroll(db_session, email_sequence, lead)
        meeting_followup.log_outcome(db_session, user=test_user, lead=lead,
                                     outcome=m.MeetingOutcomeKind.CLOSED_LOST)
        db_session.refresh(enrollment)
        assert enrollment.status is m.EnrollmentStatus.STOPPED
        assert enrollment.stop_reason == "meeting_outcome_closed_lost"
        assert enrollment.stop_category == "meeting_outcome"

    def test_the_frontend_knows_the_category(self):
        text = (REPO / "frontend" / "src" / "lib" / "sequenceCompletion.ts").read_text()
        assert '"meeting_outcome"' in text


# ===========================================================================
# 5. A "not now" plan respects phone and LinkedIn suppression too
# ===========================================================================


class TestReengagementSuppression:
    def _plan(self, db, lead, user):
        from app.services import reengagement_memory as memory

        plan = m.ReengagementPlan(lead_id=lead.id, user_id=user.id,
                                  due_at=datetime.now(UTC) - timedelta(hours=1),
                                  status=memory.SCHEDULED, reason_kind=memory.BUDGET)
        db.add(plan)
        db.commit()
        return plan

    def test_a_suppressed_phone_cancels_the_plan(self, db_session, verified_strategy,
                                                 test_user):
        from app.services import reengagement_memory as memory
        from app.workers.lead_tasks import suppression_phone

        lead = _lead(db_session, verified_strategy, phone="+1 (555) 010-7000")
        db_session.add(m.SuppressionEntry(phone=suppression_phone("+15550107000"),
                                          reason="whatsapp_stop"))
        db_session.commit()
        plan = self._plan(db_session, lead, test_user)
        assert memory.still_appropriate(db_session, plan) == "suppressed (phone number)"
        memory.run_due(db_session)
        db_session.refresh(plan)
        assert plan.status == memory.CANCELLED

    def test_a_suppressed_linkedin_profile_cancels_the_plan(self, db_session,
                                                            verified_strategy, test_user):
        from app.services import reengagement_memory as memory
        from app.services.linkedin_outreach import normalize_profile

        url = "https://www.linkedin.com/in/omar-ali-gs2"
        lead = _lead(db_session, verified_strategy, linkedin=url)
        db_session.add(m.LinkedInSuppression(profile=normalize_profile(url),
                                             reason="linkedin_reply"))
        db_session.commit()
        plan = self._plan(db_session, lead, test_user)
        assert memory.still_appropriate(db_session, plan) == "suppressed (LinkedIn profile)"

    def test_control_email_suppression_keeps_its_reason(self, db_session, verified_strategy,
                                                        test_user):
        from app.services import reengagement_memory as memory

        lead = _lead(db_session, verified_strategy, email="Omar@Beta.test")
        db_session.add(m.SuppressionEntry(email="omar@beta.test", reason="unsubscribed_email"))
        db_session.commit()
        plan = self._plan(db_session, lead, test_user)
        assert memory.still_appropriate(db_session, plan) == "suppressed (unsubscribed_email)"

    def test_control_an_unsuppressed_lead_is_still_appropriate(
            self, db_session, verified_strategy, test_user):
        from app.services import reengagement_memory as memory

        lead = _lead(db_session, verified_strategy, phone="+15550107001",
                     linkedin="https://www.linkedin.com/in/someone-else")
        plan = self._plan(db_session, lead, test_user)
        assert memory.still_appropriate(db_session, plan) is None


# ===========================================================================
# 6. Reply threading headers: captured, stored, sanitised, erased
# ===========================================================================


class TestEmailThreading:
    def test_reply_headers_follow_rfc_5322(self):
        from app.services import email_threading as et

        assert et.reply_headers("<b@x>", "<a@x>") == {
            "In-Reply-To": "<b@x>", "References": "<a@x> <b@x>"}
        assert et.reply_headers("<b@x>", None) == {"In-Reply-To": "<b@x>",
                                                    "References": "<b@x>"}
        assert et.reply_headers(None, "<a@x>") == {}

    def test_header_injection_is_dropped(self):
        from app.services import email_threading as et

        assert et.clean_message_id("<ok@x>\r\nBcc: victim@evil.test") == "<ok@x>"
        assert et.clean_message_id("no brackets@x") is None
        assert et.reply_headers("<a b@x>", None) == {}
        headers = et.reply_headers("<p@x>", "<a@x>\r\nBcc: v@evil.test <c@x>")
        assert "\r" not in headers["References"] and "\n" not in headers["References"]
        assert headers["References"] == "<a@x> <c@x> <p@x>"

    def test_the_chain_is_bounded(self):
        from app.services import email_threading as et

        refs = " ".join(f"<r{i}@x>" for i in range(50))
        chain = et.reply_headers("<p@x>", refs)["References"].split()
        assert len(chain) == et.MAX_REFERENCES
        assert chain[0] == "<r0@x>" and chain[-1] == "<p@x>"

    def test_gmail_captures_message_id_and_references(self):
        from app.integrations.gmail import GmailChannel

        inbound = GmailChannel._parse_inbound({"id": "g1", "threadId": "t1", "payload": {
            "mimeType": "text/plain", "headers": [
                {"name": "From", "value": "Sara <sara@acme.test>"},
                {"name": "Message-ID", "value": "<CAB1@mail.gmail.com>"},
                {"name": "In-Reply-To", "value": "<s2@leadpilot.dev>"},
                {"name": "References", "value": "<s1@leadpilot.dev> <s2@leadpilot.dev>"}],
            "body": {"data": ""}}})
        assert inbound.rfc_message_id == "<CAB1@mail.gmail.com>"
        assert inbound.rfc_references == "<s1@leadpilot.dev> <s2@leadpilot.dev>"

    def test_gmail_falls_back_to_in_reply_to(self):
        from app.integrations.gmail import GmailChannel

        inbound = GmailChannel._parse_inbound({"id": "g2", "payload": {"headers": [
            {"name": "Message-Id", "value": "<m@x>"},
            {"name": "In-Reply-To", "value": "<parent@x>"}]}})
        assert inbound.rfc_references == "<parent@x>"

    def test_the_reply_row_stores_them(self, db_session, verified_strategy, gmail_account):
        from app.integrations.outreach_base import InboundMessage
        from app.workers import outreach_tasks as tasks

        _lead(db_session, verified_strategy, email="sara@acme.test")
        tasks.route_inbound_impl(db_session, InboundMessage(
            provider_message_id="g1", thread_ref=None, from_address="sara@acme.test",
            to_address=None, body="How much is it?", subject="Re: hi",
            rfc_message_id="<CAB1@mail.gmail.com>", rfc_references="<s1@x>"), gmail_account)
        reply = db_session.execute(select(m.InboundReply)).scalars().one()
        assert reply.rfc_message_id == "<CAB1@mail.gmail.com>"
        assert reply.rfc_references == "<s1@x>"

    def test_a_lead_erasure_clears_them(self, db_session, verified_strategy):
        from app.services import account_erasure

        lead = _lead(db_session, verified_strategy)
        db_session.add(m.InboundReply(lead_id=lead.id, channel="email", from_address="o@b.t",
                                      body="hi", rfc_message_id="<a@b>",
                                      rfc_references="<z@b>"))
        db_session.commit()
        account_erasure.erase_lead_correspondence(db_session, lead.id)
        db_session.commit()
        reply = db_session.execute(select(m.InboundReply)).scalars().one()
        db_session.refresh(reply)
        assert reply.rfc_message_id is None and reply.rfc_references is None


class TestThreadingMigration:
    def _load(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "m0086", REPO / "alembic" / "versions" / "0086_inbound_reply_threading.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_revision_chain(self):
        module = self._load()
        assert module.revision == "0086_inbound_reply_threading"
        assert module.down_revision == "0085_webhook_foreign_keys"
        assert len(module.revision) <= 32   # alembic_version.version_num is VARCHAR(32)

    def test_upgrade_matches_the_model_and_downgrade_round_trips(self, tmp_path):
        import sqlalchemy as sa
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        from app.db.base import Base

        engine = sa.create_engine(f"sqlite:///{tmp_path / 'm.db'}")
        meta = sa.MetaData()
        table = Base.metadata.tables["inbound_replies"]
        legacy = sa.Table("inbound_replies", meta,
                          *[sa.Column(c.name, c.type, nullable=True,
                                      primary_key=c.primary_key)
                            for c in table.columns
                            if c.name not in ("rfc_message_id", "rfc_references")])
        meta.create_all(engine, tables=[legacy])
        with engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO inbound_replies (id, channel, from_address, body) "
                                 "VALUES ('r1', 'email', 'a@b.c', 'kept')"))
        module = self._load()

        def run(step):
            with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
                step()

        run(module.upgrade)
        cols = {c["name"]: c for c in sa.inspect(engine).get_columns("inbound_replies")}
        assert cols["rfc_message_id"]["nullable"] and cols["rfc_references"]["nullable"]
        assert cols["rfc_message_id"]["type"].length == \
            table.columns["rfc_message_id"].type.length
        run(module.downgrade)
        cols = {c["name"] for c in sa.inspect(engine).get_columns("inbound_replies")}
        assert "rfc_message_id" not in cols and "rfc_references" not in cols
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT body FROM inbound_replies")).scalar() == "kept"
        engine.dispose()

    def test_no_postgres_only_types(self):
        text = (REPO / "alembic" / "versions" / "0086_inbound_reply_threading.py").read_text()
        assert "postgresql." not in text and "JSONB" not in text


# ===========================================================================
# 7. Inbound: classification is set before the reply job is published
# ===========================================================================


class TestWhatsAppInboundOrdering:
    def _msg(self, text, wamid="wamid.GS2"):
        return {"id": wamid, "from": "15550107100", "timestamp": "1754900000",
                "type": "text", "text": {"body": text}}

    def test_the_reply_job_sees_the_classification(self, db_session, verified_strategy,
                                                   fake_claude, monkeypatch):
        from app.api import webhooks_whatsapp as wa
        from app.workers import reply_tasks

        _lead(db_session, verified_strategy, phone="+15550107100")
        seen = []
        monkeypatch.setattr(reply_tasks, "enqueue", lambda reply_id: seen.append(
            db_session.get(m.InboundReply, reply_id).classification) or True)
        wa._handle_inbound(db_session, self._msg("Sounds good, tell me more"), "5550001")
        assert seen and seen[0] is not None
        reply = db_session.execute(select(m.InboundReply)).scalars().one()
        assert seen == [reply.classification]

    def test_a_stop_is_classified_before_the_job(self, db_session, verified_strategy,
                                                 fake_claude, monkeypatch):
        from app.api import webhooks_whatsapp as wa
        from app.workers import reply_tasks

        _lead(db_session, verified_strategy, phone="+15550107100")
        seen = []
        monkeypatch.setattr(reply_tasks, "enqueue", lambda reply_id: seen.append(
            db_session.get(m.InboundReply, reply_id).classification) or True)
        wa._handle_inbound(db_session, self._msg("STOP", "wamid.GS2b"), "5550001")
        assert seen == ["unsubscribe_request"]


# ===========================================================================
# 8. A held message is shown as held, not as a failure
# ===========================================================================


class TestHoldBadge:
    def test_every_hold_kind_is_recognised(self):
        from app.services import (bounce_shield, champion_tracker, daily_send_approval,
                                  plan_holds, send_holds)

        assert send_holds.DAILY_APPROVAL_PREFIX == daily_send_approval.ERROR_PREFIX
        for prefix, kind in ((bounce_shield.ERROR_PREFIX, "bounce_shield"),
                             (champion_tracker.ERROR_PREFIX, "champion_tracker"),
                             (plan_holds.ERROR_PREFIX, "plan_limit")):
            hold = send_holds.hold_of(m.MessageStatus.FAILED, f"{prefix}the reason")
            assert hold["kind"] == kind and hold["reason"] == "the reason"
        hold = send_holds.hold_of(m.MessageStatus.SCHEDULED,
                                  f"{daily_send_approval.ERROR_PREFIX}waiting for today")
        assert hold["kind"] == "daily_send_approval"
        assert send_holds.hold_of(m.MessageStatus.AWAITING_REVIEW, None)["kind"] == "send_review"

    def test_control_real_failures_are_not_holds(self):
        from app.services import send_holds

        assert send_holds.hold_of(m.MessageStatus.FAILED, "smtp 550 mailbox unknown") is None
        assert send_holds.hold_of(m.MessageStatus.FAILED, None) is None
        assert send_holds.hold_of(m.MessageStatus.SENT, "bounce_shield: x") is None
        assert send_holds.hold_of(m.MessageStatus.SCHEDULED, None) is None

    def test_the_conversation_thread_carries_the_hold(self, client, db_session,
                                                      email_sequence, verified_strategy):
        from app.services import send_holds

        lead = _lead(db_session, verified_strategy)
        _enroll(db_session, email_sequence, lead)
        _msg(db_session, email_sequence, lead, 1, m.MessageStatus.FAILED,
             error=f"{send_holds.PLAN_LIMIT_PREFIX}your plan no longer includes email")
        _msg(db_session, email_sequence, lead, 2, m.MessageStatus.FAILED, error="smtp 550")
        resp = client.get(f"/leads/{lead.id}/conversation")
        assert resp.status_code == 200, resp.text
        by_step = {i["step_no"]: i for i in resp.json()["items"] if i["kind"] == "message"}
        assert by_step[1]["hold"] == {"kind": "plan_limit", "label": "Plan limit",
                                      "reason": "your plan no longer includes email"}
        assert by_step[2]["hold"] is None


# ===========================================================================
# 9 / 18. Multi-variate results and the promotion sweep run on SQLite
# ===========================================================================


def _seed_variant(db, strategy, variant, sends, replies, bookings):
    rows = ([m.Outcome(strategy_id=strategy.id, variant=variant, event=m.OutcomeEvent.SENT)
             for _ in range(sends)]
            + [m.Outcome(strategy_id=strategy.id, variant=variant,
                         event=m.OutcomeEvent.REPLIED) for _ in range(replies)]
            + [m.Outcome(strategy_id=strategy.id, variant=variant,
                         event=m.OutcomeEvent.BOOKED) for _ in range(bookings)])
    db.add_all(rows)
    db.commit()


class TestMultiVariateResults:
    def test_the_owner_gets_results(self, client, db_session, verified_strategy, test_user):
        test_user.plan = "growth"
        db_session.commit()
        for name, booked in (("A", 2), ("B", 30), ("C", 5)):
            _seed_variant(db_session, verified_strategy, name, 200, 20, booked)
        resp = client.get(f"/strategies/{verified_strategy.id}/mv-results")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["variants"] == ["A", "B", "C"]
        stats = body["per_variant_stats"]
        assert stats["B"]["sample_size"] == 200 and stats["B"]["event_count"] == 30
        assert stats["B"]["rank"] == 1

    def test_another_account_gets_404(self, client, db_session, verified_strategy, test_user):
        test_user.plan = "growth"
        other = m.User(email="mv-other@x.test", email_verified=True, plan="growth")
        db_session.add(other)
        db_session.commit()
        resp = client.get(f"/strategies/{verified_strategy.id}/mv-results",
                          headers=auth_headers(other))
        assert resp.status_code == 404

    def test_control_the_plan_gate_still_applies(self, client, db_session, verified_strategy,
                                                 test_user):
        test_user.plan = "starter"
        db_session.commit()
        resp = client.get(f"/strategies/{verified_strategy.id}/mv-results")
        assert resp.status_code == 402

    def test_no_raw_sql_left_in_the_promotion_paths(self):
        for rel in ("app/services/multi_variate.py", "app/services/ab_testing.py",
                    "app/api/strategies_advanced.py"):
            text = (REPO / rel).read_text()
            for pg_only in ("FILTER (WHERE", "= ANY(", "gen_random_uuid", "array_agg"):
                assert pg_only not in text, (rel, pg_only)
        source = (REPO / "app" / "workers" / "learning_tasks.py").read_text()
        body = source[source.index("def promote_winners"):source.index("def auto_promote_winners")]
        assert "text(" not in body


class TestPromotionSweep:
    def test_a_clear_winner_is_promoted_once(self, db_session, verified_strategy):
        from app.workers import learning_tasks

        _seed_variant(db_session, verified_strategy, "variant_a", 200, 20, 4)
        _seed_variant(db_session, verified_strategy, "variant_b", 200, 90, 30)
        assert learning_tasks.promote_winners(db_session, min_sample=30) == 1
        db_session.refresh(verified_strategy)
        assert verified_strategy.default_variant == "variant_b"
        markers = db_session.execute(select(m.Outcome).where(
            m.Outcome.strategy_id == verified_strategy.id,
            m.Outcome.event == m.OutcomeEvent.AB_PROMOTED)).scalars().all()
        assert [row.variant for row in markers] == ["variant_b"]
        # Idempotent: the marker is permanent.
        assert learning_tasks.promote_winners(db_session, min_sample=30) == 0

    def test_the_task_runs_end_to_end_when_enabled(self, db_session, verified_strategy,
                                                   monkeypatch):
        from app.services import system_settings
        from app.workers import learning_tasks

        _seed_variant(db_session, verified_strategy, "variant_a", 200, 20, 4)
        _seed_variant(db_session, verified_strategy, "variant_b", 200, 90, 30)
        system_settings.set(db_session, "ab_auto_promotion_enabled", True)
        monkeypatch.setattr("app.core.database.SessionLocal", lambda: _NoClose(db_session))
        assert learning_tasks.auto_promote_winners.run() == {"promoted": 1}

    def test_control_no_significant_difference_promotes_nothing(self, db_session,
                                                                verified_strategy):
        from app.workers import learning_tasks

        _seed_variant(db_session, verified_strategy, "variant_a", 50, 5, 2)
        _seed_variant(db_session, verified_strategy, "variant_b", 50, 6, 3)
        assert learning_tasks.promote_winners(db_session, min_sample=30) == 0
        db_session.refresh(verified_strategy)
        assert verified_strategy.default_variant is None


class _NoClose:
    """The test session, handed to the task without letting it close it."""

    def __init__(self, session):
        self._s = session

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._s, name)


# ===========================================================================
# 11. The Bounce Shield report shows the threshold the pause really uses
# ===========================================================================


class TestBounceReportThreshold:
    def test_the_report_uses_the_compliance_lowered_threshold(
            self, client, db_session, test_user, verified_strategy):
        from app.services import bounce_shield, compliance_rules, workspaces

        ws = workspaces.personal_workspace(db_session, test_user)
        assert bounce_shield.metrics(db_session, test_user.id)["campaign_pause_threshold"] \
            == pytest.approx(0.03)
        db_session.add(m.ComplianceRule(scope=str(ws.id), workspace_id=ws.id, region="*",
                                        channel="*", bounce_pause_threshold=0.015))
        db_session.commit()
        report = bounce_shield.metrics(db_session, test_user.id)
        assert report["campaign_pause_threshold"] == pytest.approx(0.015)
        # The same number the campaign page and the CRM dashboard report.
        assert compliance_rules.bounce_threshold(db_session, verified_strategy) == \
            pytest.approx(0.015)
        assert client.get("/crm/dashboard/campaigns").json()["bounce"]["pause_threshold"] \
            == pytest.approx(0.015)

    def test_control_another_workspaces_rule_does_not_apply(self, db_session, test_user):
        from app.services import bounce_shield, workspaces

        other = m.User(email="bs-other@x.test", email_verified=True)
        db_session.add(other)
        db_session.commit()
        ws = workspaces.personal_workspace(db_session, other)
        db_session.add(m.ComplianceRule(scope=str(ws.id), workspace_id=ws.id, region="*",
                                        channel="*", bounce_pause_threshold=0.01))
        db_session.commit()
        assert bounce_shield.metrics(db_session, test_user.id)["campaign_pause_threshold"] \
            == pytest.approx(0.03)


# ===========================================================================
# 12. Sending-limit variables in the env examples are real settings
# ===========================================================================


class TestSendingLimitEnvNames:
    DEAD = ("GMAIL_DAILY_SEND_CAP", "GMAIL_BOUNCE_PAUSE_THRESHOLD", "GMAIL_WARMUP_START_DAILY")

    def _keys(self, name):
        keys = []
        for line in (REPO / name).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                keys.append(line.split("=", 1)[0].strip())
        return keys

    def _fields(self):
        from app.config import Settings as AppSettings
        from app.core.config import Settings as CoreSettings

        return ({f.upper() for f in AppSettings.model_fields}
                | {f.upper() for f in CoreSettings.model_fields})

    @pytest.mark.parametrize("name", [".env.example", ".env.production.example"])
    def test_every_sending_limit_key_is_read(self, name):
        fields = self._fields()
        keys = [k for k in self._keys(name) if k.startswith(("GMAIL_", "BOUNCE_"))]
        assert {"GMAIL_DAILY_CAP", "BOUNCE_RATE_PAUSE_THRESHOLD",
                "GMAIL_WARMUP_START_SENDS"} <= set(keys)
        assert sorted(k for k in keys if k not in fields) == []

    def test_the_dead_names_are_gone(self):
        from app.core.config import Settings as CoreSettings

        for dead in self.DEAD:
            assert dead not in CoreSettings.model_fields
            for name in (".env.example", ".env.production.example"):
                assert dead not in self._keys(name)
        doc = (REPO / "docs" / "setup" / "environment-variables.md").read_text()
        assert "`GMAIL_DAILY_CAP`" in doc
        assert "`GMAIL_DAILY_SEND_CAP`, `SEND_WINDOW_*`" not in doc


# ===========================================================================
# 17. No raw exception text in API responses
# ===========================================================================

SECRET = "Error 111 connecting to redis-internal.example:6379; api_key=sk-live-abc"

_BROAD = {"Exception", "BaseException"}


def _leaky_handlers() -> list[str]:
    """`except Exception as e:` (or bare / BaseException) handlers in app/api
    whose response -- an HTTPException detail or a returned value -- is built
    from the exception's text."""
    found = []
    for path in sorted((REPO / "app" / "api").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.ExceptHandler) or not node.name:
                continue
            caught = ast.unparse(node.type) if node.type else "Exception"
            if not any(b in caught.split(".")[-1] for b in _BROAD):
                continue
            for stmt in node.body:
                for sub in ast.walk(stmt):
                    target = None
                    if isinstance(sub, ast.Raise) and sub.exc is not None:
                        target = sub.exc
                    elif isinstance(sub, ast.Return) and sub.value is not None:
                        target = sub.value
                    if target is None:
                        continue
                    text = ast.unparse(target)
                    if (f"str({node.name})" in text or f"{{{node.name}}}" in text
                            or f"{{{node.name}!" in text or f"repr({node.name})" in text):
                        found.append(f"{path.relative_to(REPO)}:{node.lineno}")
    return found


class TestNoRawExceptionText:
    def test_no_broad_handler_returns_exception_text(self):
        assert _leaky_handlers() == []

    def test_learning_loop_hides_the_stored_worker_error(self, db_session, test_user):
        from fastapi.testclient import TestClient

        from app.api import deps
        from app.core.redis_client import get_redis
        from app.db.base import get_db
        from app.main import app

        class _Redis:
            async def get(self, key):
                return {"learning_loop:last_run": "1760000000",
                        "learning_loop:last_error": SECRET}.get(key)

        test_user.is_admin = True
        db_session.commit()
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[get_redis] = lambda: _Redis()
        app.dependency_overrides[deps.require_admin] = lambda: test_user
        try:
            r = TestClient(app).get("/health/learning-loop")
        finally:
            app.dependency_overrides.clear()
        assert r.status_code == 200
        assert r.json()["status"] == "error"
        assert r.json()["last_error"] == "the last run failed"
        assert "redis-internal" not in r.text and "sk-live" not in r.text

    def test_style_analysis_failure_hides_the_provider_text(self, client, monkeypatch):
        from app.services import style_profile

        def boom(*a, **k):
            raise RuntimeError(SECRET)

        monkeypatch.setattr(style_profile, "extract", boom)
        r = client.put("/me/style-profile", json={"samples": ["Hi there, a sample email."]})
        assert r.status_code == 502
        assert "redis-internal" not in r.text and "sk-live" not in r.text
        assert "the style analysis failed" in r.text

    def test_meeting_link_failure_hides_the_provider_text(self, client, monkeypatch,
                                                           db_session, test_user):
        import app.integrations.google_meet as gm

        def boom(*a, **k):
            raise RuntimeError(SECRET)

        monkeypatch.setattr(gm, "create_meet_event", boom)
        booking = _booking(db_session, test_user)
        r = client.post("/meetings", json={"booking_id": str(booking.id),
                                           "platform": "google_meet"})
        assert r.status_code == 201, r.text
        assert r.json()["platform_error"] == "the meeting provider did not create a link"
        assert "sk-live" not in r.text

    def test_control_our_own_error_text_is_kept(self, client, monkeypatch, db_session,
                                                test_user):
        import app.integrations.google_meet as gm

        def refused(*a, **k):
            raise gm.GoogleCalendarNotAuthorized("scope not granted")

        monkeypatch.setattr(gm, "create_meet_event", refused)
        booking = _booking(db_session, test_user)
        r = client.post("/meetings", json={"booking_id": str(booking.id),
                                           "platform": "google_meet"})
        assert r.json()["platform_error"] == "scope not granted"


def _booking(db, user):
    from app.services import calendar_service as cal

    page = m.CalendarBookingPage(user_id=user.id, slug=f"gs2-{uuid.uuid4().hex[:6]}",
                                 title="Intro call", duration_minutes=30)
    db.add(page)
    db.flush()
    start = datetime.now(UTC) + timedelta(days=1)
    row = m.CalendarBooking(booking_page_id=page.id, invitee_name="Sara Khan",
                            invitee_email="sara@acme.test", start_at=start,
                            end_at=start + timedelta(minutes=30),
                            status=m.BookingStatus.CONFIRMED, slot_key=cal.slot_key_for(start))
    db.add(row)
    db.commit()
    return row


# ===========================================================================
# Review round (d5da447): M2, L4-L8 and the ported reviewer probes
# ===========================================================================


class TestCompletedEnrollmentsKeepTheirStatus:
    """Review M2: a lead-status stop overwrote COMPLETED enrollments as
    STOPPED, moving them from "completed" to "stopped early"."""

    def _completed(self, db, sequence, lead, *, pending=False):
        enrollment = _enroll(db, sequence, lead, step=3)
        enrollment.status = m.EnrollmentStatus.COMPLETED
        db.commit()
        _msg(db, sequence, lead, 3, m.MessageStatus.SENT)
        held = (_msg(db, sequence, lead, 3, m.MessageStatus.SCHEDULED, origin="reply_copilot")
                if pending else None)
        return enrollment, held

    def test_the_helper_leaves_completed_alone_but_cancels_what_is_pending(
            self, db_session, email_sequence, verified_strategy):
        lead = _lead(db_session, verified_strategy, status=m.LeadStatus.CLOSED_WON)
        enrollment, held = self._completed(db_session, email_sequence, lead, pending=True)
        assert engine.stop_for_status(db_session, lead) == 0
        db_session.refresh(enrollment)
        db_session.refresh(held)
        assert enrollment.status is m.EnrollmentStatus.COMPLETED
        assert enrollment.stop_reason is None and enrollment.stop_category is None
        assert held.status is m.MessageStatus.CANCELLED
        assert held.error == "lead status: crm_closed_won"

    def test_a_crm_close_keeps_a_completed_enrollment(self, client, db_session, enrolled,
                                                       verified_leads):
        """Reviewer probe 1, ported."""
        lead = verified_leads[0]
        enrollment = db_session.execute(select(m.SequenceEnrollment).where(
            m.SequenceEnrollment.lead_id == lead.id)).scalar_one()
        enrollment.status = m.EnrollmentStatus.COMPLETED
        lead.status = m.LeadStatus.OPPORTUNITY
        for msg in db_session.execute(select(m.Message).where(
                m.Message.lead_id == lead.id)).scalars():
            msg.status = m.MessageStatus.SENT
        db_session.commit()
        r = client.patch(f"/crm/leads/{lead.id}", json={"status": "closed_won"})
        assert r.status_code == 200, r.text
        db_session.refresh(enrollment)
        assert enrollment.status is m.EnrollmentStatus.COMPLETED
        assert enrollment.stop_reason is None

    def test_meeting_outcome_keeps_a_completed_enrollment(self, db_session, email_sequence,
                                                          verified_strategy, test_user):
        from app.services import meeting_followup

        lead = _lead(db_session, verified_strategy, status=m.LeadStatus.MEETING_BOOKED)
        enrollment, _ = self._completed(db_session, email_sequence, lead)
        meeting_followup.log_outcome(db_session, user=test_user, lead=lead,
                                     outcome=m.MeetingOutcomeKind.CLOSED_WON)
        db_session.refresh(enrollment)
        assert enrollment.status is m.EnrollmentStatus.COMPLETED

    def test_crm_sync_close_keeps_a_completed_enrollment(self, db_session, email_sequence,
                                                         verified_strategy):
        from app.services import crm_sync

        lead = _lead(db_session, verified_strategy, status=m.LeadStatus.OPPORTUNITY)
        enrollment, _ = self._completed(db_session, email_sequence, lead)
        assert crm_sync.apply_lead_status(db_session, lead, "closed_lost", source="hubspot")
        db_session.refresh(enrollment)
        assert enrollment.status is m.EnrollmentStatus.COMPLETED

    def test_control_active_and_paused_are_stopped(self, db_session, email_sequence,
                                                   verified_strategy):
        lead = _lead(db_session, verified_strategy, status=m.LeadStatus.DISQUALIFIED)
        active = _enroll(db_session, email_sequence, lead)
        other = m.Sequence(strategy_id=verified_strategy.id, channel=m.ChannelType.EMAIL,
                           name="second", status=m.SequenceStatus.ACTIVE)
        db_session.add(other)
        db_session.commit()
        paused = _enroll(db_session, other, lead)
        paused.status = m.EnrollmentStatus.PAUSED
        db_session.commit()
        assert engine.stop_for_status(db_session, lead) == 2
        for row in (active, paused):
            db_session.refresh(row)
            assert row.status is m.EnrollmentStatus.STOPPED


class TestBulkCloseIsAtomic:
    """Review L4: statuses were committed, then each lead's sequences stopped
    one commit at a time; a failure part way left closed leads with live
    sequences."""

    def test_a_failure_part_way_changes_nothing(self, client, db_session, enrolled,
                                                verified_leads, monkeypatch):
        first, second = verified_leads[0], verified_leads[1]
        for lead in (first, second):
            lead.status = m.LeadStatus.OPPORTUNITY
        db_session.commit()
        ids = (first.id, second.id)
        real = engine.stop_for_status
        calls = []

        def flaky(db, lead, **kw):
            calls.append(lead.id)
            if len(calls) == 2:
                raise RuntimeError("database went away")
            return real(db, lead, **kw)

        monkeypatch.setattr(engine, "stop_for_status", flaky)
        with pytest.raises(RuntimeError):
            client.post("/crm/leads/bulk", json={"lead_ids": [str(i) for i in ids],
                                                 "status": "closed_lost"})
        db_session.rollback()
        for lead_id in ids:
            lead = db_session.get(m.Lead, lead_id)
            db_session.refresh(lead)
            assert lead.status is m.LeadStatus.OPPORTUNITY
            enrollment = db_session.execute(select(m.SequenceEnrollment).where(
                m.SequenceEnrollment.lead_id == lead_id)).scalar_one()
            assert enrollment.status is m.EnrollmentStatus.ACTIVE


class TestGdprEraseStopsSequences:
    """Review L5: the GDPR lead delete set DROPPED but left enrollments ACTIVE."""

    def test_erasing_a_lead_stops_its_enrollments(self, client, db_session, enrolled,
                                                  verified_leads):
        lead = verified_leads[0]
        r = client.delete(f"/leads/{lead.id}")
        assert r.status_code == 204, r.text
        enrollment = db_session.execute(select(m.SequenceEnrollment).where(
            m.SequenceEnrollment.lead_id == lead.id)).scalar_one()
        db_session.refresh(enrollment)
        assert enrollment.status is m.EnrollmentStatus.STOPPED
        assert enrollment.stop_reason == engine.STOP_LEAD_REMOVED
        other = db_session.execute(select(m.SequenceEnrollment).where(
            m.SequenceEnrollment.lead_id == verified_leads[1].id)).scalar_one()
        assert other.status is m.EnrollmentStatus.ACTIVE


class TestStopLeavesOthersAlone:
    """Review L8."""

    def test_a_held_message_on_another_sequence_is_untouched(
            self, db_session, email_sequence, verified_strategy):
        from app.services import send_holds

        lead = _lead(db_session, verified_strategy)
        enrollment = _enroll(db_session, email_sequence, lead)
        other = m.Sequence(strategy_id=verified_strategy.id, channel=m.ChannelType.EMAIL,
                           name="other", status=m.SequenceStatus.ACTIVE)
        db_session.add(other)
        db_session.commit()
        _enroll(db_session, other, lead)
        held = _msg(db_session, other, lead, 1, m.MessageStatus.FAILED,
                    error=f"{send_holds.BOUNCE_SHIELD_PREFIX}unverified")
        engine.stop_enrollment(db_session, enrollment, reason="crm_hubspot")
        db_session.refresh(held)
        assert held.status is m.MessageStatus.FAILED

    def test_an_approved_review_is_untouched(self, db_session, email_sequence,
                                             verified_strategy, test_user):
        from app.services import send_review

        lead = _lead(db_session, verified_strategy)
        enrollment = _enroll(db_session, email_sequence, lead)
        msg = _msg(db_session, email_sequence, lead, 1, m.MessageStatus.SCHEDULED)
        review = m.SendReview(message_id=msg.id, lead_id=lead.id, user_id=test_user.id,
                              status=send_review.APPROVED, decided_by_user_id=test_user.id,
                              decision_note="looks good")
        db_session.add(review)
        db_session.commit()
        engine.stop_enrollment(db_session, enrollment, reason="unsubscribed")
        db_session.refresh(review)
        db_session.refresh(msg)
        assert msg.status is m.MessageStatus.CANCELLED      # the message still stops
        assert review.status == send_review.APPROVED         # the human decision stays
        assert review.decision_note == "looks good"
        assert send_review.review_out(db_session, review)["closed_by_system"] is False

    def test_whatsapp_routing_failure_still_publishes_the_job(
            self, db_session, verified_strategy, fake_claude, monkeypatch):
        from app.api import webhooks_whatsapp as wa
        from app.workers import outreach_tasks, reply_tasks

        _lead(db_session, verified_strategy, phone="+15550107100")
        seen = []
        monkeypatch.setattr(reply_tasks, "enqueue", lambda reply_id: seen.append(reply_id))

        def boom(*a, **k):
            raise RuntimeError("router down")

        monkeypatch.setattr(outreach_tasks, "route_whatsapp_inbound_impl", boom)
        with pytest.raises(RuntimeError):
            wa._handle_inbound(db_session, {"id": "wamid.GS2f", "from": "15550107100",
                                            "timestamp": "1754900000", "type": "text",
                                            "text": {"body": "hello"}}, "5550001")
        assert len(seen) == 1


class TestSequenceMappingErrors:
    """Review L7: Python's own exception text must not reach the 422."""

    def _post(self, client, strategy, template, mapping=None):
        step = {"step_no": 1, "template": "Intro", "channel": "whatsapp",
                "whatsapp_kind": "template", "whatsapp_template_id": str(template.id)}
        if mapping is not None:
            step["variable_mapping"] = mapping
        return client.post(f"/strategies/{strategy.id}/sequences",
                           json={"name": "WA", "channel": "whatsapp", "steps": [step]})

    def test_a_malformed_stored_template_gets_a_generic_422(
            self, client, db_session, verified_strategy, approved_template):
        approved_template.variable_descriptions_json = {"first": "first name"}
        db_session.commit()
        r = self._post(client, verified_strategy, approved_template)
        assert r.status_code == 422, r.text
        assert "invalid literal" not in r.text
        assert "variable_mapping must cover" in r.text

    def test_control_the_validators_own_sentence_is_kept(
            self, client, verified_strategy, approved_template):
        r = self._post(client, verified_strategy, approved_template,
                       mapping={"1": "lead.first_name"})
        assert r.status_code == 422, r.text
        assert "variable_mapping must cover" in r.text and "—" in r.json()["detail"]


class TestPromotionConflictPath:
    def test_a_concurrent_marker_does_not_double_promote(self, db_session,
                                                         verified_strategy, monkeypatch):
        """Reviewer probe 3, ported: a concurrent sweep commits its marker
        between the check and the insert; the SAVEPOINT swallows the unique
        violation and exactly one marker exists."""
        import sqlalchemy as sa

        from app.services import ab_testing
        from app.workers import learning_tasks

        db_session.execute(sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS gs2_ab_once ON outcomes (strategy_id) "
            "WHERE event = 'AB_PROMOTED' OR event = 'ab_promoted'"))
        db_session.commit()
        _seed_variant(db_session, verified_strategy, "variant_a", 200, 20, 4)
        _seed_variant(db_session, verified_strategy, "variant_b", 200, 90, 30)
        real = ab_testing.compare_variants

        def racing(*a, **k):
            res = real(*a, **k)
            db_session.add(m.Outcome(strategy_id=verified_strategy.id,
                                     event=m.OutcomeEvent.AB_PROMOTED, variant="variant_b"))
            db_session.commit()
            return res

        monkeypatch.setattr(ab_testing, "compare_variants", racing)
        learning_tasks.promote_winners(db_session, min_sample=30)
        db_session.refresh(verified_strategy)
        markers = db_session.execute(select(m.Outcome).where(
            m.Outcome.event == m.OutcomeEvent.AB_PROMOTED)).scalars().all()
        assert len(markers) == 1
        assert verified_strategy.default_variant == "variant_b"


class TestProviderTextNeverPassesThrough:
    """Review L2/L3: ClientHunterError subclasses that wrap a provider's text
    are not user-safe; integrations log provider bodies instead of putting
    them in messages that reach users."""

    def test_public_detail_refuses_provider_wrapping_errors(self):
        from app.core.errors import public_detail
        from app.integrations.sms import SmsSendError
        from app.integrations.stripe_billing import StripeError
        from app.services.email_sender import EmailSendError

        for cls in (StripeError, EmailSendError, SmsSendError):
            assert public_detail(cls(SECRET), "generic", event="t") == "generic"

    def test_zoom_does_not_put_its_response_body_in_the_message(self, monkeypatch):
        from app.integrations import zoom

        class _Resp:
            status_code = 401
            text = '{"reason":"Invalid client_id","secret":"sk-live-abc"}'

        adapter = zoom.ZoomAdapter.__new__(zoom.ZoomAdapter)
        adapter.creds = {"client_id": "c", "client_secret": "s", "account_id": "a"}

        class _Http:
            def post(self, *a, **k):
                return _Resp()

        adapter._token_http = _Http()

        class _Redis:
            def get(self, key):
                return None

        adapter.redis = _Redis()
        monkeypatch.setattr(adapter, "_cache_key", lambda: "k", raising=False)
        with pytest.raises(zoom.ZoomNotConfigured) as exc:
            adapter._access_token()
        assert "sk-live" not in str(exc.value) and "Invalid client_id" not in str(exc.value)
        assert "HTTP 401" in str(exc.value)

    def test_meeting_followup_send_failure_hides_gmail_text(self, db_session, test_user,
                                                            verified_strategy, monkeypatch):
        from app.integrations import gmail
        from app.services import meeting_followup

        db_session.add(m.GmailAccount(user_id=test_user.id, email_address="me@x.test",
                                      token_ciphertext="x"))
        lead = _lead(db_session, verified_strategy, status=m.LeadStatus.MEETING_BOOKED)
        row = meeting_followup.log_outcome(db_session, user=test_user, lead=lead,
                                           outcome=m.MeetingOutcomeKind.INTERESTED)
        row.gmail_draft_id = "d1"
        row.draft_status = "draft_saved"
        db_session.commit()

        def boom(*a, **k):
            raise RuntimeError(SECRET)

        monkeypatch.setattr(gmail, "send_draft", boom)
        monkeypatch.setattr(meeting_followup, "_recipient_block", lambda db, lead: None,
                            raising=False)
        with pytest.raises(meeting_followup.FollowupNotSendable) as exc:
            meeting_followup.send_followup(db_session, row, user=test_user)
        assert "sk-live" not in str(exc.value) and "redis-internal" not in str(exc.value)

    def test_no_service_raises_an_error_built_from_exception_text(self):
        """AST scan of app/services and app/integrations: `raise X(f"...{exc}")`
        inside an except handler. Allowed, with the reason:
          email_sender / sms / stripe_billing -- user_safe = False errors;
            every caller maps them to fixed text (auth.py, phone_verification,
            billing) and public_detail refuses them.
          notifications.py -- a start-up configuration RuntimeError, never in
            a response.
          ip_intelligence.py -- IpIntelligenceError is only logged / written
            to the admin security audit by network_guard.
          meeting_followup.py str(exc) of GmailScopeMissing -- our own text.
        """
        allowed = {"app/services/email_sender.py", "app/integrations/sms.py",
                   "app/integrations/stripe_billing.py", "app/services/notifications.py",
                   "app/integrations/ip_intelligence.py"}
        found = []
        for root in ("app/services", "app/integrations"):
            for path in sorted((REPO / root).rglob("*.py")):
                rel = str(path.relative_to(REPO))
                if rel in allowed:
                    continue
                for handler in ast.walk(ast.parse(path.read_text())):
                    if not isinstance(handler, ast.ExceptHandler) or not handler.name:
                        continue
                    caught = ast.unparse(handler.type) if handler.type else ""
                    if rel == "app/services/meeting_followup.py" and "GmailScopeMissing" in caught:
                        continue
                    for stmt in handler.body:
                        for sub in ast.walk(stmt):
                            if isinstance(sub, ast.Raise) and sub.exc is not None:
                                text = ast.unparse(sub.exc)
                                n = handler.name
                                if (f"{{{n}" in text or f"str({n})" in text
                                        or f"repr({n})" in text):
                                    found.append(f"{rel}:{sub.lineno}")
        assert found == []

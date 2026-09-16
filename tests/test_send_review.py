"""Part 1 Feature 5 — the human review queue for high-risk sends.

The properties that matter:
  * each of the four triggers fires on its own evidence, and nothing else does,
  * a held message is QUEUED, never lost,
  * what the reviewer approved is exactly what transmits, even when the next
    render produces different words (rendering is a model call),
  * a reviewer can fix the copy, not only veto it,
  * a broken review system fails OPEN: it must not silently stop outreach.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.services import send_review
from tests.conftest import auth_headers

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def review_on(monkeypatch):
    """Undo conftest's `send_review_off`. This is the one module that tests
    the gate, so it is the one module that has it on."""
    from app.services import send_review as service

    monkeypatch.setattr(service, "enabled", lambda db, code=None: True)


@pytest.fixture()
def lead(db_session, verified_strategy):
    row = m.Lead(strategy_id=verified_strategy.id, source="apollo", external_id="SR1",
                 full_name="Sara Khan", title="Operations Manager",
                 company="Blaze Safety", email="sara@blaze.test",
                 status=m.LeadStatus.VERIFIED)
    db_session.add(row)
    db_session.commit()
    return row


def _message(db_session, sequence, lead, **kwargs) -> m.Message:
    message = m.Message(sequence_id=sequence.id, lead_id=lead.id,
                        channel=m.ChannelType.EMAIL, step_no=1, template="t",
                        subject="Quick question", body="Hi Sara — who owns inspections?",
                        status=m.MessageStatus.SCHEDULED, **kwargs)
    db_session.add(message)
    db_session.commit()
    return message


# --------------------------------------------------------------------------
# The triggers
# --------------------------------------------------------------------------


class TestPriorObjection:
    def test_an_objection_on_the_last_reply_holds_the_next_send(self, db_session, lead):
        db_session.add(m.InboundReply(lead_id=lead.id, channel="email",
                                      from_address=lead.email,
                                      body="Too expensive for where we are.",
                                      reply_category="OBJECTION"))
        db_session.commit()
        found = send_review.prior_objection(db_session, lead)
        assert found["code"] == send_review.PRIOR_OBJECTION
        assert "Too expensive" in found["detail"]

    def test_the_part_one_intent_label_also_counts(self, db_session, lead):
        """Two classifiers exist for different questions; either one alone
        would miss cases."""
        db_session.add(m.InboundReply(lead_id=lead.id, channel="email",
                                      from_address=lead.email, body="We use a vendor.",
                                      intent_label="objection"))
        db_session.commit()
        assert send_review.prior_objection(db_session, lead) is not None

    def test_only_the_LATEST_reply_decides(self, db_session, lead):
        db_session.add(m.InboundReply(lead_id=lead.id, channel="email",
                                      from_address=lead.email, body="old",
                                      reply_category="OBJECTION",
                                      created_at=NOW - timedelta(days=5)))
        db_session.commit()
        db_session.add(m.InboundReply(lead_id=lead.id, channel="email",
                                      from_address=lead.email, body="new",
                                      reply_category="BUYING_SIGNAL",
                                      created_at=NOW))
        db_session.commit()
        assert send_review.prior_objection(db_session, lead) is None

    def test_no_replies_is_not_an_objection(self, db_session, lead):
        assert send_review.prior_objection(db_session, lead) is None


class TestDealStalled:
    def test_an_open_deal_past_its_close_date_is_stalled(self, db_session, lead, test_user):
        db_session.add(m.Deal(user_id=test_user.id, lead_id=lead.id, name="Blaze pilot",
                              stage=m.DealStage.OPEN, close_date=date(2026, 8, 1)))
        db_session.commit()
        found = send_review.deal_stalled(db_session, lead, NOW)
        assert found["code"] == send_review.DEAL_STALLED
        assert "Blaze pilot" in found["detail"]

    def test_a_deal_still_in_the_future_is_not_stalled(self, db_session, lead, test_user):
        db_session.add(m.Deal(user_id=test_user.id, lead_id=lead.id, name="Later",
                              stage=m.DealStage.OPEN, close_date=date(2026, 12, 1)))
        db_session.commit()
        assert send_review.deal_stalled(db_session, lead, NOW) is None

    def test_a_closed_deal_is_not_stalled_however_old(self, db_session, lead, test_user):
        db_session.add(m.Deal(user_id=test_user.id, lead_id=lead.id, name="Won",
                              stage=m.DealStage.WON, close_date=date(2026, 1, 1)))
        db_session.commit()
        assert send_review.deal_stalled(db_session, lead, NOW) is None

    def test_a_cooling_prospect_is_the_same_signal_from_the_other_side(
            self, db_session, lead):
        lead.engagement_state = "cooling"
        db_session.commit()
        assert send_review.deal_stalled(db_session, lead, NOW) is not None


class TestVipTitle:
    @pytest.mark.parametrize("title", [
        "Founder", "Co-Founder", "CEO", "Chief Revenue Officer", "President",
        "Managing Director", "VP of Sales", "Vice President, Operations",
        "Head of Marketing", "Partner", "Board Member",
    ])
    def test_executive_titles_are_held(self, db_session, lead, title):
        lead.title = title
        assert send_review.vip_title(lead) is not None

    @pytest.mark.parametrize("title", [
        "Operations Manager", "Senior Engineer", "Inspector", "Office Administrator", "",
    ])
    def test_ordinary_titles_are_not(self, db_session, lead, title):
        """Widening this to every 'manager' would put the whole campaign in
        the queue, and a queue nobody can finish is a queue nobody reads."""
        lead.title = title
        assert send_review.vip_title(lead) is None

    def test_a_missing_title_is_not_a_vip(self, db_session, lead):
        lead.title = None
        assert send_review.vip_title(lead) is None

    def test_the_detail_names_the_person_and_the_title(self, db_session, lead):
        lead.title = "CEO"
        assert "Sara Khan is CEO at Blaze Safety." == send_review.vip_title(lead)["detail"]


class TestToneFlag:
    def test_spam_copy_is_flagged(self):
        found = send_review.tone_flags("Act now", "This is risk-free and guaranteed.",
                                       "email")
        assert found["code"] == send_review.TONE_FLAG

    def test_shouting_is_flagged(self):
        assert send_review.tone_flags(
            None, "THIS IS URGENT PLEASE REPLY IMMEDIATELY NOW", "email") is not None

    def test_ordinary_copy_is_not_flagged(self):
        assert send_review.tone_flags(
            "Quick question", "Hi Sara — who owns inspection scheduling today?",
            "email") is None

    def test_the_shared_rules_are_reused_not_reimplemented(self):
        """The pre-launch gate and this one must never disagree about what
        reads badly."""
        from app.services import adversarial_review

        assert adversarial_review._text_findings("guaranteed", None, channel="email")
        assert send_review.tone_flags(None, "guaranteed", "email") is not None


class TestEvaluate:
    def test_a_clean_message_to_an_ordinary_prospect_has_no_triggers(
            self, db_session, lead):
        assert send_review.evaluate(db_session, lead, "Quick question",
                                    "Who owns inspections?", "email", NOW) == []

    def test_triggers_accumulate(self, db_session, lead):
        lead.title = "CEO"
        db_session.add(m.InboundReply(lead_id=lead.id, channel="email",
                                      from_address=lead.email, body="no",
                                      reply_category="OBJECTION"))
        db_session.commit()
        codes = {t["code"] for t in send_review.evaluate(
            db_session, lead, "Act now", "guaranteed results", "email", NOW)}
        assert codes == {send_review.PRIOR_OBJECTION, send_review.VIP_TITLE,
                         send_review.TONE_FLAG}

    def test_a_broken_check_never_blocks_a_send(self, db_session, lead, monkeypatch):
        """Fails OPEN on purpose: holding every message because a query broke
        would stop the product dead."""
        monkeypatch.setattr(send_review, "vip_title",
                            lambda lead: (_ for _ in ()).throw(RuntimeError("boom")))
        lead.title = "CEO"
        assert send_review.evaluate(db_session, lead, "s", "b", "email", NOW) == []

    def test_every_trigger_has_a_human_label(self):
        assert set(send_review.LABELS) == set(send_review.TRIGGERS)


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


class TestGate:
    def test_a_clean_message_passes_straight_through(
            self, db_session, lead, email_sequence):
        message = _message(db_session, email_sequence, lead)
        decision = send_review.gate(db_session, lead, message, "Quick question",
                                    "Who owns inspections?", now=NOW)
        assert decision["action"] == "send"
        assert send_review.review_for(db_session, message.id) is None

    def test_a_vip_message_is_held_with_its_copy_snapshotted(
            self, db_session, lead, email_sequence, product_with_strategy):
        lead.title = "CEO"
        db_session.commit()
        message = _message(db_session, email_sequence, lead)
        decision = send_review.gate(db_session, lead, message, "Quick question",
                                    "Who owns inspections?", now=NOW)
        assert decision["action"] == "hold"
        review = decision["review"]
        assert review.status == send_review.PENDING
        assert review.body_snapshot == "Who owns inspections?"
        assert review.content_hash

    def test_a_second_pass_does_not_create_a_second_review(
            self, db_session, lead, email_sequence):
        lead.title = "CEO"
        db_session.commit()
        message = _message(db_session, email_sequence, lead)
        send_review.gate(db_session, lead, message, "s", "b", now=NOW)
        send_review.gate(db_session, lead, message, "s", "b", now=NOW)
        assert db_session.query(m.SendReview).count() == 1

    def test_an_approved_message_is_let_through(self, db_session, lead, email_sequence):
        lead.title = "CEO"
        db_session.commit()
        message = _message(db_session, email_sequence, lead)
        review = send_review.gate(db_session, lead, message, "s", "b", now=NOW)["review"]
        send_review.approve(db_session, review, now=NOW)
        assert send_review.gate(db_session, lead, message, "s", "b",
                                now=NOW)["action"] == "send"

    def test_an_approved_review_sends_the_approved_words_not_a_fresh_render(
            self, db_session, lead, email_sequence):
        """Rendering is a model call and never repeats itself. If the gate
        compared a fresh render against the approval, the message would
        re-queue on every attempt and never go out."""
        lead.title = "CEO"
        db_session.commit()
        message = _message(db_session, email_sequence, lead)
        review = send_review.gate(db_session, lead, message, "s", "approved words",
                                  now=NOW)["review"]
        send_review.approve(db_session, review, now=NOW)
        decision = send_review.gate(db_session, lead, message, "s", "a DIFFERENT render",
                                    now=NOW)
        assert decision["action"] == "send"
        assert decision["body"] == "approved words"

    def test_an_edited_approval_sends_the_reviewers_words(
            self, db_session, lead, email_sequence):
        lead.title = "CEO"
        db_session.commit()
        message = _message(db_session, email_sequence, lead)
        review = send_review.gate(db_session, lead, message, "s", "b", now=NOW)["review"]
        send_review.approve(db_session, review, body="A better line.", now=NOW)
        decision = send_review.gate(db_session, lead, message, "s", "b", now=NOW)
        assert decision["action"] == "send"
        assert decision["body"] == "A better line."

    def test_a_rejected_message_is_cancelled_not_silently_sent(
            self, db_session, lead, email_sequence):
        lead.title = "CEO"
        db_session.commit()
        message = _message(db_session, email_sequence, lead)
        review = send_review.gate(db_session, lead, message, "s", "b", now=NOW)["review"]
        send_review.reject(db_session, review, note="Wrong moment for this account",
                           now=NOW)
        decision = send_review.gate(db_session, lead, message, "s", "b", now=NOW)
        assert decision["action"] == "cancel"
        assert "Wrong moment" in decision["reason"]

    def test_the_gate_fails_open_when_it_breaks(self, db_session, lead, email_sequence,
                                                monkeypatch):
        monkeypatch.setattr(send_review, "review_for",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db gone")))
        message = _message(db_session, email_sequence, lead)
        assert send_review.gate(db_session, lead, message, "s", "b",
                                now=NOW)["action"] == "send"


class TestDecisions:
    def _held(self, db_session, lead, email_sequence):
        lead.title = "CEO"
        db_session.commit()
        message = _message(db_session, email_sequence, lead)
        review = send_review.gate(db_session, lead, message, "s", "b", now=NOW)["review"]
        message.status = m.MessageStatus.AWAITING_REVIEW
        db_session.commit()
        return message, review

    def test_approving_returns_the_message_to_the_send_queue(
            self, db_session, lead, email_sequence):
        message, review = self._held(db_session, lead, email_sequence)
        send_review.approve(db_session, review, now=NOW)
        db_session.refresh(message)
        assert message.status is m.MessageStatus.SCHEDULED
        assert message.error is None

    def test_rejecting_cancels_the_message_but_leaves_the_relationship_running(
            self, db_session, lead, email_sequence):
        message, review = self._held(db_session, lead, email_sequence)
        enrollment = m.SequenceEnrollment(sequence_id=email_sequence.id, lead_id=lead.id)
        db_session.add(enrollment)
        db_session.commit()
        send_review.reject(db_session, review, note="Not now for this one", now=NOW)
        db_session.refresh(message)
        db_session.refresh(enrollment)
        assert message.status is m.MessageStatus.CANCELLED
        assert enrollment.status is m.EnrollmentStatus.ACTIVE

    def test_the_decision_records_who_and_when(self, db_session, lead, email_sequence,
                                               test_user):
        _message_, review = self._held(db_session, lead, email_sequence)
        send_review.approve(db_session, review, actor_user_id=test_user.id, now=NOW)
        assert review.decided_by_user_id == test_user.id
        assert review.decided_at == NOW


class TestSendPath:
    def test_a_high_risk_send_is_held_rather_than_transmitted(
            self, db_session, fake_claude, enrolled, verified_leads, gmail_account,
            fake_channel, monkeypatch):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        for row in verified_leads:
            row.title = "CEO"
        db_session.commit()
        message = db_session.query(m.Message).filter_by(
            status=m.MessageStatus.SCHEDULED).first()
        result = outreach_tasks.send_message_impl(db_session, message.id, now=NOW)
        db_session.refresh(message)
        assert result == "held_for_review"
        assert message.status is m.MessageStatus.AWAITING_REVIEW
        assert fake_channel.sent == []
        assert message.body        # rendered and kept, not thrown away

    def test_approving_then_dispatching_actually_sends(
            self, db_session, fake_claude, enrolled, verified_leads, gmail_account,
            fake_channel, monkeypatch):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        for row in verified_leads:
            row.title = "CEO"
        db_session.commit()
        message = db_session.query(m.Message).filter_by(
            status=m.MessageStatus.SCHEDULED).first()
        outreach_tasks.send_message_impl(db_session, message.id, now=NOW)
        review = send_review.review_for(db_session, message.id)
        send_review.approve(db_session, review, now=NOW)
        assert outreach_tasks.send_message_impl(db_session, message.id, now=NOW) == "sent"
        assert len(fake_channel.sent) == 1

    def test_an_ordinary_send_is_unaffected(
            self, db_session, fake_claude, enrolled, verified_leads, gmail_account,
            fake_channel, monkeypatch):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        # The shared fixture's leads are all "Owner", which IS a VIP title.
        # This test is about the ordinary path, so give them an ordinary one.
        for row in verified_leads:
            row.title = "Operations Manager"
        db_session.commit()
        message = db_session.query(m.Message).filter_by(
            status=m.MessageStatus.SCHEDULED).first()
        assert outreach_tasks.send_message_impl(db_session, message.id, now=NOW) == "sent"
        assert db_session.query(m.SendReview).count() == 0


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


class TestApi:
    @pytest.fixture()
    def held(self, db_session, lead, email_sequence, test_user, product_with_strategy):
        lead.title = "CEO"
        db_session.commit()
        message = _message(db_session, email_sequence, lead)
        review = send_review.gate(db_session, lead, message, "Quick question",
                                  "Who owns inspections?", now=NOW)["review"]
        message.status = m.MessageStatus.AWAITING_REVIEW
        db_session.commit()
        return review

    def test_the_queue_lists_pending_reviews_with_their_triggers(
            self, client, db_session, held, test_user):
        response = client.get("/send-reviews", headers=auth_headers(test_user))
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["triggers"][0]["code"] == send_review.VIP_TITLE
        assert item["lead"]["full_name"] == "Sara Khan"

    def test_the_count_endpoint_feeds_the_nav_badge(self, client, db_session, held,
                                                    test_user):
        assert client.get("/send-reviews/count",
                          headers=auth_headers(test_user)).json()["pending"] == 1

    def test_approving_with_an_edit(self, client, db_session, held, test_user):
        response = client.post(f"/send-reviews/{held.id}/approve",
                               json={"body": "A better line.", "note": "Softened it"},
                               headers=auth_headers(test_user))
        assert response.status_code == 200
        assert response.json()["body"] == "A better line."
        assert response.json()["edited"] is True

    def test_rejecting_requires_a_real_reason(self, client, db_session, held, test_user):
        assert client.post(f"/send-reviews/{held.id}/reject", json={"note": "no"},
                           headers=auth_headers(test_user)).status_code == 422

    def test_rejecting(self, client, db_session, held, test_user):
        response = client.post(f"/send-reviews/{held.id}/reject",
                               json={"note": "Wrong moment for this account"},
                               headers=auth_headers(test_user))
        assert response.status_code == 200
        assert response.json()["status"] == send_review.REJECTED

    def test_deciding_twice_is_a_conflict_not_a_silent_overwrite(
            self, client, db_session, held, test_user):
        client.post(f"/send-reviews/{held.id}/approve", json={},
                    headers=auth_headers(test_user))
        response = client.post(f"/send-reviews/{held.id}/reject",
                               json={"note": "changed my mind"},
                               headers=auth_headers(test_user))
        assert response.status_code == 409

    def test_another_account_cannot_see_or_decide_a_review(
            self, client, db_session, held):
        other = m.User(email="nosy-review@test.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        assert client.get(f"/send-reviews/{held.id}",
                          headers=auth_headers(other)).status_code == 404
        assert client.post(f"/send-reviews/{held.id}/approve", json={},
                           headers=auth_headers(other)).status_code == 404

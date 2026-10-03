"""Part 1 Feature 1 — positive reply classification.

Covers the three things that can go wrong with a headline metric:
  * a label invented when the model failed (it must stay NULL instead),
  * machine mail counted as a human reply,
  * a rate divided by zero and charted as 0%.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.services import reply_intent
from tests.conftest import auth_headers

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture()
def lead(db_session, verified_strategy):
    row = m.Lead(strategy_id=verified_strategy.id, source="apollo", external_id="RI1",
                 full_name="Sara Khan", title="Owner", company="Blaze Safety",
                 email="sara@blaze.test", status=m.LeadStatus.VERIFIED)
    db_session.add(row)
    db_session.commit()
    return row


def _reply(db_session, lead, **kwargs) -> m.InboundReply:
    reply = m.InboundReply(
        lead_id=lead.id, channel=kwargs.pop("channel", "email"),
        from_address=kwargs.pop("from_address", lead.email),
        subject=kwargs.pop("subject", "Re: quick question"),
        body=kwargs.pop("body", "Sounds good — can we talk Thursday?"),
        received_at=kwargs.pop("received_at", NOW), **kwargs)
    db_session.add(reply)
    db_session.commit()
    return reply


def _sent_message(db_session, lead, sequence, step_no=1) -> m.Message:
    message = m.Message(sequence_id=sequence.id, lead_id=lead.id,
                        channel=m.ChannelType.EMAIL, step_no=step_no,
                        template=f"Step {step_no}", subject="Quick question",
                        body="Hi Sara — who owns inspections today?",
                        status=m.MessageStatus.SENT, sent_at=NOW - timedelta(days=1))
    db_session.add(message)
    db_session.commit()
    return message


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------


class TestClassify:
    def test_a_human_reply_is_labelled_by_the_model(self, db_session, fake_claude, lead):
        reply = _reply(db_session, lead)
        result = reply_intent.classify(db_session, reply.id)
        assert result["label"] == "interested"
        assert result["confidence"] == 0.9
        assert result["source"] == "model"
        assert "Thursday" in result["reason"]

    def test_the_original_message_is_given_to_the_model(
            self, db_session, fake_claude, lead, email_sequence):
        message = _sent_message(db_session, lead, email_sequence, step_no=2)
        reply = _reply(db_session, lead, message_id=message.id)
        reply_intent.classify(db_session, reply.id)
        prompt = fake_claude.reply_intent_prompts[-1]
        assert "who owns inspections today?" in prompt
        assert "step 2" in prompt

    def test_the_latest_sent_message_is_used_when_the_reply_is_unmatched(
            self, db_session, fake_claude, lead, email_sequence):
        _sent_message(db_session, lead, email_sequence, step_no=1)
        reply = _reply(db_session, lead)
        reply_intent.classify(db_session, reply.id)
        assert "step 1" in fake_claude.reply_intent_prompts[-1]

    @pytest.mark.parametrize("label", list(reply_intent.LABELS))
    def test_every_documented_label_is_accepted(self, db_session, fake_claude, lead, label):
        fake_claude.reply_intent_response = {"label": label, "confidence": 0.5,
                                             "reason": "because"}
        reply = _reply(db_session, lead)
        assert reply_intent.classify(db_session, reply.id)["label"] == label

    def test_a_label_the_taxonomy_does_not_have_leaves_the_reply_unclassified(
            self, db_session, fake_claude, lead):
        """Never guess. A guessed label silently moves a headline metric."""
        fake_claude.reply_intent_response = {"label": "maybe", "confidence": 0.9}
        reply = _reply(db_session, lead)
        result = reply_intent.classify(db_session, reply.id)
        assert result["label"] is None
        assert "error" in result

    def test_a_model_outage_leaves_the_reply_unclassified_and_never_raises(
            self, db_session, fake_claude, lead):
        fake_claude.reply_intent_response = RuntimeError("anthropic down")
        reply = _reply(db_session, lead)
        result = reply_intent.classify(db_session, reply.id)
        assert result["label"] is None
        assert result["error"].startswith("RuntimeError")

    def test_a_missing_reply_is_an_error_not_an_exception(self, db_session, fake_claude):
        result = reply_intent.classify(db_session, uuid.uuid4())
        assert result["label"] is None
        assert "LookupError" in result["error"]

    def test_confidence_is_clamped_into_zero_to_one(self, db_session, fake_claude, lead):
        fake_claude.reply_intent_response = {"label": "objection", "confidence": 7,
                                             "reason": "r"}
        reply = _reply(db_session, lead)
        assert reply_intent.classify(db_session, reply.id)["confidence"] == 1.0


class TestRules:
    def test_an_unsubscribe_never_costs_a_model_call(self, db_session, fake_claude, lead):
        reply = _reply(db_session, lead, classification="unsubscribe_request",
                       body="take me off your list")
        result = reply_intent.classify(db_session, reply.id)
        assert result == {"label": "unsubscribe", "confidence": 1.0,
                          "source": "rules", "reason": result["reason"],
                          "at": result["at"]}
        assert fake_claude.reply_intent_prompts == []

    @pytest.mark.parametrize("routing", reply_intent.MACHINE_CLASSES)
    def test_machine_mail_is_neutral_without_a_model_call(
            self, db_session, fake_claude, lead, routing):
        reply = _reply(db_session, lead, classification=routing)
        result = reply_intent.classify(db_session, reply.id)
        assert result["label"] == "neutral"
        assert result["source"] == "rules"
        assert fake_claude.reply_intent_prompts == []

    def test_machine_reply_also_reads_the_authenticity_verdict(self, db_session, lead):
        reply = _reply(db_session, lead, authenticity_kind="auto_responder")
        assert reply_intent.machine_reply(reply) is True

    def test_a_plain_reply_is_not_a_machine_reply(self, db_session, lead):
        assert reply_intent.machine_reply(_reply(db_session, lead)) is False


class TestApply:
    def test_a_result_is_written_to_the_row(self, db_session, fake_claude, lead):
        reply = _reply(db_session, lead)
        reply_intent.apply(db_session, reply, reply_intent.classify(db_session, reply.id))
        db_session.refresh(reply)
        assert reply.intent_label == "interested"
        assert reply.intent_source == "model"
        assert reply.intent_at is not None

    def test_a_failed_result_never_blanks_an_earlier_good_one(
            self, db_session, fake_claude, lead):
        reply = _reply(db_session, lead)
        reply_intent.apply(db_session, reply, reply_intent.classify(db_session, reply.id))
        reply_intent.apply(db_session, reply, {"label": None, "error": "boom"})
        db_session.refresh(reply)
        assert reply.intent_label == "interested"

    def test_classify_and_apply_is_idempotent(self, db_session, fake_claude, lead):
        reply = _reply(db_session, lead)
        assert reply_intent.classify_and_apply(db_session, reply)["status"] == "classified"
        calls = len(fake_claude.reply_intent_prompts)
        assert reply_intent.classify_and_apply(db_session, reply)["status"] == "skipped"
        assert len(fake_claude.reply_intent_prompts) == calls

    def test_force_reclassifies(self, db_session, fake_claude, lead):
        reply = _reply(db_session, lead)
        reply_intent.classify_and_apply(db_session, reply)
        fake_claude.reply_intent_response = {"label": "objection", "confidence": 0.7,
                                             "reason": "already have a vendor"}
        reply_intent.classify_and_apply(db_session, reply, force=True)
        db_session.refresh(reply)
        assert reply.intent_label == "objection"

    def test_intent_out_always_has_every_key(self, db_session, lead):
        out = reply_intent.intent_out(_reply(db_session, lead))
        assert set(out) == {"label", "confidence", "reason", "source", "at", "is_positive"}
        assert out["label"] is None and out["is_positive"] is False


# --------------------------------------------------------------------------
# The metric
# --------------------------------------------------------------------------


class TestMetrics:
    def _campaign(self, db_session, verified_strategy, email_sequence, labels):
        """One sent message and one reply per entry in `labels`."""
        for index, (label, routing) in enumerate(labels):
            lead = m.Lead(strategy_id=verified_strategy.id, source="apollo",
                          external_id=f"M{index}", full_name=f"Lead {index}",
                          email=f"m{index}@co.test", status=m.LeadStatus.VERIFIED)
            db_session.add(lead)
            db_session.flush()
            db_session.add(m.Message(sequence_id=email_sequence.id, lead_id=lead.id,
                                     channel=m.ChannelType.EMAIL, step_no=1,
                                     template="t", status=m.MessageStatus.SENT,
                                     sent_at=NOW))
            db_session.add(m.InboundReply(lead_id=lead.id, channel="email",
                                          from_address=lead.email, body="b",
                                          classification=routing, intent_label=label,
                                          intent_at=NOW if label else None))
        db_session.commit()

    def test_an_empty_campaign_has_no_rate_rather_than_zero(
            self, db_session, verified_strategy):
        metrics = reply_intent.strategy_metrics(db_session, verified_strategy.id)
        assert metrics["reply_rate"] is None
        assert metrics["positive_reply_rate"] is None
        assert metrics["positive_share"] is None

    def test_the_positive_rate_counts_only_interested(
            self, db_session, verified_strategy, email_sequence):
        self._campaign(db_session, verified_strategy, email_sequence, [
            ("interested", None), ("interested", None), ("objection", None),
            ("not_now", None),
        ])
        metrics = reply_intent.strategy_metrics(db_session, verified_strategy.id)
        assert metrics["sent"] == 4
        assert metrics["reply_rate"] == 1.0
        assert metrics["positive_reply_rate"] == 0.5
        assert metrics["breakdown"] == {"interested": 2, "neutral": 0, "objection": 1,
                                        "not_now": 1, "unsubscribe": 0}

    def test_machine_mail_is_excluded_from_the_human_denominator(
            self, db_session, verified_strategy, email_sequence):
        self._campaign(db_session, verified_strategy, email_sequence, [
            ("interested", None), ("neutral", "bounce"), ("neutral", "out_of_office"),
        ])
        metrics = reply_intent.strategy_metrics(db_session, verified_strategy.id)
        assert metrics["replies"] == 3          # raw reply count keeps them
        assert metrics["human_replies"] == 1    # the metric does not
        assert metrics["positive_share"] == 1.0

    def test_unclassified_replies_are_reported_separately(
            self, db_session, verified_strategy, email_sequence):
        """A low positive rate must be distinguishable from 'not classified yet'."""
        self._campaign(db_session, verified_strategy, email_sequence, [
            ("interested", None), (None, None), (None, None),
        ])
        metrics = reply_intent.strategy_metrics(db_session, verified_strategy.id)
        assert metrics["classified"] == 1
        assert metrics["unclassified"] == 2

    def test_the_raw_reply_rate_is_unchanged_by_this_feature(
            self, db_session, verified_strategy, email_sequence):
        self._campaign(db_session, verified_strategy, email_sequence,
                       [("unsubscribe", None), (None, None)])
        metrics = reply_intent.strategy_metrics(db_session, verified_strategy.id)
        assert metrics["reply_rate"] == 1.0
        assert metrics["positive_reply_rate"] == 0.0


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------


class TestReplyTask:
    def test_the_reply_task_classifies_intent_as_well_as_category(
            self, db_session, fake_claude, lead):
        from app.workers.reply_tasks import process_inbound_reply_impl

        reply = _reply(db_session, lead)
        result = process_inbound_reply_impl(db_session, reply.id)
        db_session.refresh(reply)
        assert result["intent"] == "interested"
        assert reply.intent_label == "interested"
        assert reply.reply_category is not None      # the FG1 fields still run

    def test_an_already_classified_reply_still_gets_a_missing_intent_label(
            self, db_session, fake_claude, lead):
        """Replies stored before this feature must pick up a label on the next pass."""
        from app.workers.reply_tasks import process_inbound_reply_impl

        reply = _reply(db_session, lead, reply_category="BUYING_SIGNAL",
                       classified_at=NOW)
        result = process_inbound_reply_impl(db_session, reply.id)
        db_session.refresh(reply)
        assert result["status"] == "skipped"
        assert reply.intent_label == "interested"


class TestApi:
    def test_the_replies_list_carries_the_intent_block(
            self, client, db_session, fake_claude, lead, test_user):
        _reply(db_session, lead, intent_label="interested", intent_confidence=0.9,
               intent_source="model", intent_at=NOW)
        response = client.get("/crm/replies", headers=auth_headers(test_user))
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["intent"]["label"] == "interested"
        assert item["intent"]["is_positive"] is True

    def test_reclassify_reruns_the_classifier(
            self, client, db_session, fake_claude, lead, test_user):
        reply = _reply(db_session, lead, intent_label="neutral", intent_at=NOW)
        response = client.post(f"/crm/replies/{reply.id}/intent/reclassify",
                               headers=auth_headers(test_user))
        assert response.status_code == 200
        assert response.json()["label"] == "interested"

    def test_reclassify_reports_an_outage_rather_than_a_silent_no_op(
            self, client, db_session, fake_claude, lead, test_user):
        fake_claude.reply_intent_response = RuntimeError("down")
        reply = _reply(db_session, lead)
        response = client.post(f"/crm/replies/{reply.id}/intent/reclassify",
                               headers=auth_headers(test_user))
        assert response.status_code == 503

    def test_another_account_cannot_read_an_intent(
            self, client, db_session, fake_claude, lead):
        other = m.User(email="other@test.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        reply = _reply(db_session, lead)
        response = client.get(f"/crm/replies/{reply.id}/intent",
                              headers=auth_headers(other))
        assert response.status_code == 404

    def test_strategy_analytics_carries_reply_quality(
            self, client, db_session, fake_claude, lead, verified_strategy,
            test_user):
        _reply(db_session, lead, intent_label="interested", intent_at=NOW)
        response = client.get(f"/strategies/{verified_strategy.id}/analytics",
                              headers=auth_headers(test_user))
        assert response.status_code == 200
        quality = response.json()["reply_quality"]
        assert quality["breakdown"]["interested"] == 1

    def test_the_dedicated_reply_quality_endpoint(
            self, client, db_session, fake_claude, lead, verified_strategy,
            test_user):
        response = client.get(f"/strategies/{verified_strategy.id}/reply-quality",
                              headers=auth_headers(test_user))
        assert response.status_code == 200
        assert response.json()["strategy_id"] == str(verified_strategy.id)

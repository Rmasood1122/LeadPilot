"""Part 1 Feature 8 — the transparent attribution ledger.

The properties that matter:
  * a linked reply is a FACT and is labelled as one,
  * last-touch is a GUESS and is labelled as one, with confidence that decays
    as the gap widens,
  * "nothing was sent" is an answer, not a blank,
  * the sweep is idempotent, so it can run forever and back-fill history,
  * a bad reply never lands in a ledger of positive outcomes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.services import attribution
from tests.conftest import auth_headers

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def lead(db_session, verified_strategy):
    row = m.Lead(strategy_id=verified_strategy.id, source="apollo", external_id="AT1",
                 full_name="Sara Khan", company="Blaze Safety",
                 email="sara@blaze.test", status=m.LeadStatus.CONTACTED)
    db_session.add(row)
    db_session.commit()
    return row


def _sent(db_session, sequence, lead, step_no, when, **kwargs) -> m.Message:
    message = m.Message(sequence_id=sequence.id, lead_id=lead.id,
                        channel=kwargs.pop("channel", m.ChannelType.EMAIL),
                        step_no=step_no, template="t",
                        subject=kwargs.pop("subject", f"Step {step_no}"),
                        body=kwargs.pop("body", f"Body {step_no}"),
                        status=m.MessageStatus.SENT, sent_at=when, **kwargs)
    db_session.add(message)
    db_session.commit()
    return message


def _reply(db_session, lead, when, **kwargs) -> m.InboundReply:
    reply = m.InboundReply(lead_id=lead.id, channel="email",
                           from_address=lead.email, body="yes please",
                           received_at=when, **kwargs)
    db_session.add(reply)
    db_session.commit()
    return reply


# --------------------------------------------------------------------------
# Finding the touch
# --------------------------------------------------------------------------


class TestCredit:
    def test_a_linked_reply_is_a_fact_not_an_attribution(
            self, db_session, lead, email_sequence):
        step1 = _sent(db_session, email_sequence, lead, 1, NOW - timedelta(days=5))
        _sent(db_session, email_sequence, lead, 2, NOW - timedelta(days=1))
        _reply(db_session, lead, NOW - timedelta(days=4), message_id=step1.id)
        found = attribution.credit(db_session, lead.id, NOW)
        assert found["method"] == attribution.DIRECT_REPLY
        assert found["confidence"] == 1.0
        assert found["message"].id == step1.id      # NOT the most recent send

    def test_a_thread_match_is_evidence_one_link_weaker(
            self, db_session, lead, email_sequence):
        step1 = _sent(db_session, email_sequence, lead, 1, NOW - timedelta(days=5),
                      thread_ref="thread-a")
        _sent(db_session, email_sequence, lead, 2, NOW - timedelta(days=1))
        _reply(db_session, lead, NOW - timedelta(days=4), thread_ref="thread-a")
        found = attribution.credit(db_session, lead.id, NOW)
        assert found["method"] == attribution.THREAD_MATCH
        assert found["confidence"] == 0.85
        assert found["message"].id == step1.id

    def test_without_a_reply_the_last_send_is_credited_and_labelled_a_guess(
            self, db_session, lead, email_sequence):
        _sent(db_session, email_sequence, lead, 1, NOW - timedelta(days=5))
        step2 = _sent(db_session, email_sequence, lead, 2, NOW - timedelta(hours=3))
        found = attribution.credit(db_session, lead.id, NOW)
        assert found["method"] == attribution.LAST_TOUCH
        assert found["message"].id == step2.id
        assert found["confidence"] < 1.0
        assert any("any of them may have done the work" in e for e in found["evidence"])

    def test_a_message_sent_AFTER_the_outcome_is_never_credited(
            self, db_session, lead, email_sequence):
        step1 = _sent(db_session, email_sequence, lead, 1, NOW - timedelta(days=2))
        _sent(db_session, email_sequence, lead, 2, NOW + timedelta(days=1))
        assert attribution.credit(db_session, lead.id, NOW)["message"].id == step1.id

    def test_nothing_sent_is_an_answer_not_a_blank(self, db_session, lead):
        found = attribution.credit(db_session, lead.id, NOW)
        assert found["method"] == attribution.NONE
        assert found["message"] is None
        assert found["evidence"]

    def test_a_scheduled_message_is_not_a_touch(self, db_session, lead, email_sequence):
        db_session.add(m.Message(sequence_id=email_sequence.id, lead_id=lead.id,
                                 channel=m.ChannelType.EMAIL, step_no=1, template="t",
                                 status=m.MessageStatus.SCHEDULED,
                                 scheduled_at=NOW - timedelta(days=1)))
        db_session.commit()
        assert attribution.credit(db_session, lead.id, NOW)["method"] == attribution.NONE

    def test_every_answer_carries_its_evidence(self, db_session, lead, email_sequence):
        _sent(db_session, email_sequence, lead, 1, NOW - timedelta(hours=2))
        assert attribution.credit(db_session, lead.id, NOW)["evidence"]


class TestConfidence:
    @pytest.mark.parametrize("hours,expected", [
        (1, 0.7), (24, 0.7), (25, 0.55), (72, 0.55), (100, 0.4), (168, 0.4),
        (200, 0.25), (720, 0.25), (1000, attribution.LAST_TOUCH_FLOOR),
    ])
    def test_a_guess_decays_as_the_gap_widens(self, hours, expected):
        """A booking two hours after a send is far more likely to be that
        send's doing than one three weeks later."""
        assert attribution.last_touch_confidence(hours) == expected

    def test_an_unknown_gap_is_the_floor(self):
        assert attribution.last_touch_confidence(None) == attribution.LAST_TOUCH_FLOOR


# --------------------------------------------------------------------------
# Recording
# --------------------------------------------------------------------------


class TestRecord:
    def test_the_entry_snapshots_the_copy_that_earned_it(
            self, db_session, lead, email_sequence, product_with_strategy):
        _sent(db_session, email_sequence, lead, 2, NOW - timedelta(hours=4),
              subject="Your inspection backlog", body="Who owns scheduling?")
        entry = attribution.record(db_session, lead=lead,
                                   outcome_kind=attribution.MEETING_BOOKED,
                                   outcome_id=lead.id, outcome_at=NOW)
        assert entry.subject_snapshot == "Your inspection backlog"
        assert entry.body_snapshot == "Who owns scheduling?"
        assert entry.step_no == 2
        assert entry.channel == "email"
        assert entry.hours_to_outcome == 4.0

    def test_recording_twice_credits_once(self, db_session, lead, email_sequence,
                                          product_with_strategy):
        _sent(db_session, email_sequence, lead, 1, NOW - timedelta(hours=1))
        first = attribution.record(db_session, lead=lead,
                                   outcome_kind=attribution.MEETING_BOOKED,
                                   outcome_id=lead.id, outcome_at=NOW)
        second = attribution.record(db_session, lead=lead,
                                    outcome_kind=attribution.MEETING_BOOKED,
                                    outcome_id=lead.id, outcome_at=NOW)
        assert first.id == second.id
        assert db_session.query(m.AttributionEntry).count() == 1

    def test_an_outcome_with_no_prospect_is_not_credited(self, db_session):
        assert attribution.record(db_session, lead=None,
                                  outcome_kind=attribution.WON,
                                  outcome_id=None, outcome_at=NOW) is None


class TestSweep:
    def _booked(self, db_session, lead, strategy, when=NOW):
        outcome = m.Outcome(lead_id=lead.id, strategy_id=strategy.id,
                            event=m.OutcomeEvent.BOOKED, channel="email", ts=when)
        db_session.add(outcome)
        db_session.commit()
        return outcome

    def test_the_sweep_credits_a_booking(self, db_session, lead, verified_strategy,
                                         email_sequence, product_with_strategy):
        _sent(db_session, email_sequence, lead, 2, NOW - timedelta(hours=6))
        self._booked(db_session, lead, verified_strategy)
        counts = attribution.run_sweep(db_session, now=NOW)
        assert counts["recorded"] == 1
        entry = db_session.query(m.AttributionEntry).one()
        assert entry.outcome_kind == attribution.MEETING_BOOKED
        assert entry.step_no == 2

    def test_the_sweep_is_safe_to_run_forever(self, db_session, lead, verified_strategy,
                                              email_sequence, product_with_strategy):
        _sent(db_session, email_sequence, lead, 1, NOW - timedelta(hours=1))
        self._booked(db_session, lead, verified_strategy)
        attribution.run_sweep(db_session, now=NOW)
        second = attribution.run_sweep(db_session, now=NOW)
        assert second["recorded"] == 0
        assert second["skipped"] == 1
        assert db_session.query(m.AttributionEntry).count() == 1

    def test_the_sweep_backfills_history(self, db_session, lead, verified_strategy,
                                         email_sequence, product_with_strategy):
        """A booking from before this feature shipped is credited too."""
        _sent(db_session, email_sequence, lead, 1, NOW - timedelta(days=200))
        self._booked(db_session, lead, verified_strategy, when=NOW - timedelta(days=199))
        assert attribution.run_sweep(db_session, now=NOW)["recorded"] == 1

    def test_only_a_POSITIVE_reply_earns_a_ledger_entry(
            self, db_session, lead, verified_strategy, email_sequence,
            product_with_strategy):
        """Crediting every reply would put 'stop emailing me' in the same
        ledger as a booking."""
        _sent(db_session, email_sequence, lead, 1, NOW - timedelta(hours=2))
        _reply(db_session, lead, NOW - timedelta(hours=1), intent_label="unsubscribe")
        db_session.add(m.Outcome(lead_id=lead.id, strategy_id=verified_strategy.id,
                                 event=m.OutcomeEvent.REPLIED, channel="email", ts=NOW))
        db_session.commit()
        assert attribution.run_sweep(db_session, now=NOW)["recorded"] == 0

    def test_an_interested_reply_does_earn_one(
            self, db_session, lead, verified_strategy, email_sequence,
            product_with_strategy):
        _sent(db_session, email_sequence, lead, 1, NOW - timedelta(hours=2))
        _reply(db_session, lead, NOW - timedelta(hours=1), intent_label="interested")
        db_session.add(m.Outcome(lead_id=lead.id, strategy_id=verified_strategy.id,
                                 event=m.OutcomeEvent.REPLIED, channel="email", ts=NOW))
        db_session.commit()
        assert attribution.run_sweep(db_session, now=NOW)["recorded"] == 1

    def test_uninteresting_events_are_ignored(self, db_session, lead, verified_strategy,
                                              product_with_strategy):
        for event in (m.OutcomeEvent.SENT, m.OutcomeEvent.OPENED,
                      m.OutcomeEvent.BOUNCED, m.OutcomeEvent.UNSUBSCRIBED):
            db_session.add(m.Outcome(lead_id=lead.id, strategy_id=verified_strategy.id,
                                     event=event, channel="email", ts=NOW))
        db_session.commit()
        assert attribution.run_sweep(db_session, now=NOW)["checked"] == 0

    def test_one_bad_outcome_never_stops_the_sweep(
            self, db_session, lead, verified_strategy, product_with_strategy,
            monkeypatch):
        self._booked(db_session, lead, verified_strategy)
        monkeypatch.setattr(attribution, "record",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        assert attribution.run_sweep(db_session, now=NOW)["failed"] == 1


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


class TestOutput:
    def test_the_entry_says_whether_it_is_a_fact_or_a_guess(
            self, db_session, lead, email_sequence, product_with_strategy):
        step1 = _sent(db_session, email_sequence, lead, 1, NOW - timedelta(days=1))
        _reply(db_session, lead, NOW - timedelta(hours=12), message_id=step1.id)
        certain = attribution.record(db_session, lead=lead,
                                     outcome_kind=attribution.MEETING_BOOKED,
                                     outcome_id=lead.id, outcome_at=NOW)
        out = attribution.entry_out(db_session, certain)
        assert out["is_certain"] is True
        assert out["method_label"] == "They replied to this message"

    def test_every_method_has_a_label(self):
        assert set(attribution.METHOD_LABELS) == set(attribution.METHODS)

    def test_the_summary_reports_how_much_of_it_is_guesswork(
            self, db_session, verified_strategy, email_sequence, test_user,
            product_with_strategy):
        for index in range(3):
            row = m.Lead(strategy_id=verified_strategy.id, source="apollo",
                         external_id=f"S{index}", email=f"s{index}@co.test",
                         status=m.LeadStatus.CONTACTED)
            db_session.add(row)
            db_session.flush()
            message = _sent(db_session, email_sequence, row, 2,
                            NOW - timedelta(hours=2))
            if index == 0:
                _reply(db_session, row, NOW - timedelta(hours=1),
                       message_id=message.id)
            attribution.record(db_session, lead=row,
                               outcome_kind=attribution.MEETING_BOOKED,
                               outcome_id=row.id, outcome_at=NOW)
        summary = attribution.summary(db_session, test_user.id)
        assert summary["total"] == 3
        assert summary["certain"] == 1
        assert summary["by_step"][0] == {"step_no": 2, "count": 3, "certain": 1}
        assert summary["by_channel"][0]["channel"] == "email"

    def test_an_empty_summary_does_not_invent_numbers(self, db_session, test_user):
        summary = attribution.summary(db_session, test_user.id)
        assert summary["total"] == 0
        assert summary["by_step"] == []
        assert summary["median_hours_to_outcome"] is None


class TestApi:
    @pytest.fixture()
    def credited(self, db_session, lead, email_sequence, test_user,
                 product_with_strategy):
        _sent(db_session, email_sequence, lead, 2, NOW - timedelta(hours=5))
        return attribution.record(db_session, lead=lead,
                                  outcome_kind=attribution.MEETING_BOOKED,
                                  outcome_id=lead.id, outcome_at=NOW)

    def test_the_ledger_endpoint(self, client, db_session, credited, test_user):
        response = client.get("/attribution", headers=auth_headers(test_user))
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["step_no"] == 2
        assert item["method"] == attribution.LAST_TOUCH
        assert item["confidence"] is not None

    def test_filtering_by_outcome_kind(self, client, db_session, credited, test_user):
        assert client.get("/attribution?outcome_kind=won",
                          headers=auth_headers(test_user)).json()["total"] == 0
        assert client.get("/attribution?outcome_kind=meeting_booked",
                          headers=auth_headers(test_user)).json()["total"] == 1

    def test_an_unknown_outcome_kind_is_rejected(self, client, db_session, test_user):
        assert client.get("/attribution?outcome_kind=vibes",
                          headers=auth_headers(test_user)).status_code == 422

    def test_the_summary_endpoint(self, client, db_session, credited, test_user):
        response = client.get("/attribution/summary", headers=auth_headers(test_user))
        assert response.status_code == 200
        assert response.json()["total"] == 1

    def test_the_per_lead_endpoint_returns_the_copy_itself(
            self, client, db_session, credited, lead, test_user):
        response = client.get(f"/leads/{lead.id}/attribution",
                              headers=auth_headers(test_user))
        assert response.status_code == 200
        assert response.json()[0]["body"] == "Body 2"

    def test_recompute_is_safe_to_press_repeatedly(self, client, db_session, lead,
                                                   verified_strategy, email_sequence,
                                                   test_user, product_with_strategy):
        _sent(db_session, email_sequence, lead, 1, NOW - timedelta(hours=1))
        db_session.add(m.Outcome(lead_id=lead.id, strategy_id=verified_strategy.id,
                                 event=m.OutcomeEvent.BOOKED, channel="email", ts=NOW))
        db_session.commit()
        first = client.post("/attribution/recompute", headers=auth_headers(test_user))
        second = client.post("/attribution/recompute", headers=auth_headers(test_user))
        assert first.json()["recorded"] == 1
        assert second.json()["recorded"] == 0

    def test_another_account_sees_nothing(self, client, db_session, credited):
        other = m.User(email="nosy-attr@test.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        assert client.get("/attribution",
                          headers=auth_headers(other)).json()["total"] == 0

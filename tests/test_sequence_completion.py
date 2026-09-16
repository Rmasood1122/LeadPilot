"""Part 1 Feature 3 — sequence completion guarantee and its metric.

The guarantee is about what CANNOT happen quietly, so most of these tests are
about the categorisation of a stop rather than about arithmetic:
  * every documented stop reason maps onto the fixed vocabulary,
  * a reason nobody anticipated lands in `other` and is LOGGED,
  * an automated stop is never counted as a human decision,
  * a skipped step never counts as a received one,
  * editing a sequence does not retroactively un-complete finished enrollments.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.services import sequence_completion as completion
from app.services import sequence_engine as engine
from tests.conftest import auth_headers

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


def _enrollment(db_session, sequence, lead, **kwargs) -> m.SequenceEnrollment:
    row = m.SequenceEnrollment(sequence_id=sequence.id, lead_id=lead.id, **kwargs)
    db_session.add(row)
    db_session.commit()
    return row


# --------------------------------------------------------------------------
# The vocabulary
# --------------------------------------------------------------------------


class TestCategorize:
    @pytest.mark.parametrize("reason,expected", [
        # Every reason the codebase actually passes to stop_enrollment today.
        ("replied_interested", completion.REPLIED),
        ("replied_question", completion.REPLIED),
        ("replied_objection", completion.REPLIED),
        ("replied_unsubscribe_request", completion.UNSUBSCRIBED),
        ("replied_bounce", completion.BOUNCED),
        ("unsubscribed", completion.UNSUBSCRIBED),
        ("bounced", completion.BOUNCED),
        ("meeting_booked", completion.MEETING_BOOKED),
        ("suppressed", completion.SUPPRESSED),
        ("whatsapp_optout", completion.OPTED_OUT),
        ("crm_hubspot", completion.CRM_CLOSED),
        ("crm_salesforce", completion.CRM_CLOSED),
        ("call_not_interested", completion.CALL_OUTCOME),
        ("kill_signal:bounced", completion.SYSTEM_KILL),
        ("completed_all_skipped_needs_attention", completion.ALL_STEPS_SKIPPED),
    ])
    def test_every_reason_in_the_codebase_is_recognised(self, reason, expected):
        assert completion.categorize(reason) == expected

    def test_an_unsubscribe_arriving_as_a_reply_is_not_counted_as_a_reply(self):
        """The longest prefix wins, so the more specific reading survives."""
        assert completion.categorize("replied_unsubscribe_request") == completion.UNSUBSCRIBED

    def test_an_unrecognised_reason_is_other_and_is_logged(self, caplog):
        with caplog.at_level(logging.WARNING):
            assert completion.categorize("because_i_said_so") == completion.OTHER
        assert "unrecognised sequence stop reason" in caplog.text

    def test_no_reason_at_all_is_other_and_is_logged(self, caplog):
        with caplog.at_level(logging.WARNING):
            assert completion.categorize(None) == completion.OTHER
        assert "no reason at all" in caplog.text

    def test_categorisation_is_case_insensitive(self):
        assert completion.categorize("REPLIED_INTERESTED") == completion.REPLIED

    def test_an_automated_kill_is_never_an_authorised_stop(self):
        """'The system decided' is not 'a person decided'."""
        assert completion.is_authorised(completion.SYSTEM_KILL) is False
        assert completion.is_authorised(completion.ALL_STEPS_SKIPPED) is False
        assert completion.is_authorised(completion.OTHER) is False

    def test_the_documented_decisions_are_authorised(self):
        for category in (completion.REPLIED, completion.UNSUBSCRIBED, completion.BOUNCED,
                         completion.MEETING_BOOKED, completion.SUPPRESSED,
                         completion.OPTED_OUT, completion.CRM_CLOSED,
                         completion.CALL_OUTCOME):
            assert completion.is_authorised(category) is True

    def test_every_category_has_a_human_label(self):
        assert set(completion.LABELS) == set(completion.CATEGORIES)


# --------------------------------------------------------------------------
# The engine keeps the columns true
# --------------------------------------------------------------------------


class TestEngineWiring:
    def test_enrollment_freezes_the_planned_step_count(
            self, db_session, fake_claude, email_sequence, verified_leads, gmail_account):
        engine.enroll_leads(db_session, email_sequence, now=NOW)
        rows = db_session.query(m.SequenceEnrollment).all()
        assert all(r.planned_steps == 3 for r in rows)
        assert all(r.steps_sent == 0 for r in rows)

    def test_adding_a_step_later_does_not_un_complete_a_finished_enrollment(
            self, db_session, fake_claude, email_sequence, verified_leads, gmail_account):
        """The snapshot is the whole point of planned_steps."""
        engine.enroll_leads(db_session, email_sequence, now=NOW)
        row = db_session.query(m.SequenceEnrollment).first()
        row.steps_sent = 3
        db_session.commit()
        assert completion.completed_every_step(row) is True

        db_session.add(m.SequenceStep(sequence_id=email_sequence.id, step_no=4,
                                      template="Step 4", delay_days=5))
        db_session.commit()
        db_session.refresh(row)
        assert completion.completed_every_step(row) is True

    def test_stopping_records_when_and_what_kind(
            self, db_session, fake_claude, email_sequence, verified_leads, gmail_account):
        engine.enroll_leads(db_session, email_sequence, now=NOW)
        row = db_session.query(m.SequenceEnrollment).first()
        engine.stop_enrollment(db_session, row, reason="replied_interested", now=NOW)
        db_session.refresh(row)
        assert row.status is m.EnrollmentStatus.STOPPED
        assert row.stop_category == completion.REPLIED
        assert row.stopped_at is not None

    def test_an_invented_reason_is_recorded_as_unauthorised(
            self, db_session, fake_claude, email_sequence, verified_leads, gmail_account):
        engine.enroll_leads(db_session, email_sequence, now=NOW)
        row = db_session.query(m.SequenceEnrollment).first()
        engine.stop_enrollment(db_session, row, reason="some_new_thing", now=NOW)
        db_session.refresh(row)
        assert row.stop_category == completion.OTHER
        assert completion.is_authorised(row.stop_category) is False

    def test_a_sent_step_counts_and_a_re_send_does_not(
            self, db_session, fake_claude, email_sequence, verified_leads, gmail_account):
        engine.enroll_leads(db_session, email_sequence, now=NOW)
        lead = verified_leads[0]
        row = db_session.query(m.SequenceEnrollment).filter_by(lead_id=lead.id).one()
        message = db_session.query(m.Message).filter_by(lead_id=lead.id).one()
        engine.schedule_next_step(db_session, message, now=NOW)
        db_session.refresh(row)
        assert row.steps_sent == 1
        # The same step arriving again (a transient failure that finally sent)
        # must not be counted twice.
        engine.schedule_next_step(db_session, message, now=NOW)
        db_session.refresh(row)
        assert row.steps_sent == 1

    def test_a_skipped_step_advances_the_sequence_but_is_not_received(
            self, db_session, fake_claude, email_sequence, verified_leads, gmail_account):
        engine.enroll_leads(db_session, email_sequence, now=NOW)
        lead = verified_leads[0]
        row = db_session.query(m.SequenceEnrollment).filter_by(lead_id=lead.id).one()
        message = db_session.query(m.Message).filter_by(lead_id=lead.id).one()
        engine.skip_message(db_session, message, reason="skipped_no_optin", now=NOW)
        db_session.refresh(row)
        assert row.current_step == 1
        assert row.steps_sent == 0

    def test_finishing_the_last_step_stamps_completed_at(
            self, db_session, fake_claude, email_sequence, verified_leads, gmail_account):
        engine.enroll_leads(db_session, email_sequence, now=NOW)
        lead = verified_leads[0]
        row = db_session.query(m.SequenceEnrollment).filter_by(lead_id=lead.id).one()
        message = db_session.query(m.Message).filter_by(lead_id=lead.id).one()
        for step_no in (1, 2, 3):
            message.step_no = step_no
            engine.schedule_next_step(db_session, message, now=NOW)
        db_session.refresh(row)
        assert row.status is m.EnrollmentStatus.COMPLETED
        assert row.completed_at is not None
        assert row.steps_sent == 3

    def test_a_meeting_pause_is_not_a_stop(
            self, db_session, fake_claude, email_sequence, verified_leads, gmail_account):
        """pause_for_meeting writes stop_reason but leaves the enrollment
        running — it must never appear in the dropped breakdown."""
        engine.enroll_leads(db_session, email_sequence, now=NOW)
        engine.pause_for_meeting(db_session, verified_leads[0], now=NOW)
        row = db_session.query(m.SequenceEnrollment).filter_by(
            lead_id=verified_leads[0].id).one()
        assert row.stop_category is None
        assert completion.outcome_of(row) == "running"


# --------------------------------------------------------------------------
# Per-enrollment reading
# --------------------------------------------------------------------------


class TestOutcome:
    def test_a_running_enrollment_is_neither_completed_nor_dropped(
            self, db_session, email_sequence, verified_leads):
        row = _enrollment(db_session, email_sequence, verified_leads[0],
                          planned_steps=3, steps_sent=1)
        assert completion.outcome_of(row) == "running"

    def test_a_paused_enrollment_is_still_running(
            self, db_session, email_sequence, verified_leads):
        row = _enrollment(db_session, email_sequence, verified_leads[0],
                          planned_steps=3, steps_sent=1,
                          status=m.EnrollmentStatus.PAUSED)
        assert completion.outcome_of(row) == "running"

    def test_every_step_received_is_completed(self, db_session, email_sequence,
                                              verified_leads):
        row = _enrollment(db_session, email_sequence, verified_leads[0],
                          planned_steps=3, steps_sent=3,
                          status=m.EnrollmentStatus.COMPLETED)
        assert completion.outcome_of(row) == "completed"

    def test_stopping_halfway_is_dropped(self, db_session, email_sequence, verified_leads):
        row = _enrollment(db_session, email_sequence, verified_leads[0],
                          planned_steps=3, steps_sent=1,
                          status=m.EnrollmentStatus.STOPPED,
                          stop_category=completion.REPLIED)
        assert completion.outcome_of(row) == "dropped"

    def test_an_enrollment_from_before_this_feature_is_unknown_not_failed(
            self, db_session, email_sequence, verified_leads):
        """No planned_steps snapshot means the question cannot be answered.
        Answering 'False' would invent a failure out of missing data."""
        row = _enrollment(db_session, email_sequence, verified_leads[0],
                          status=m.EnrollmentStatus.COMPLETED)
        assert completion.completed_every_step(row) is None
        assert completion.outcome_of(row) == "unknown"

    def test_enrollment_out_carries_the_label_and_the_authorisation(
            self, db_session, email_sequence, verified_leads):
        row = _enrollment(db_session, email_sequence, verified_leads[0],
                          planned_steps=3, steps_sent=1,
                          status=m.EnrollmentStatus.STOPPED,
                          stop_reason="kill_signal:bounced",
                          stop_category=completion.SYSTEM_KILL)
        out = completion.enrollment_out(row)
        assert out["stop_label"] == "Stopped by an automated kill signal"
        assert out["authorised"] is False


# --------------------------------------------------------------------------
# The metric
# --------------------------------------------------------------------------


class TestMetrics:
    def _spread(self, db_session, sequence, strategy):
        """One enrollment of each interesting kind."""
        rows = [
            dict(planned_steps=3, steps_sent=3, status=m.EnrollmentStatus.COMPLETED),
            dict(planned_steps=3, steps_sent=3, status=m.EnrollmentStatus.COMPLETED),
            dict(planned_steps=3, steps_sent=1, status=m.EnrollmentStatus.STOPPED,
                 stop_reason="replied_interested", stop_category=completion.REPLIED),
            dict(planned_steps=3, steps_sent=1, status=m.EnrollmentStatus.STOPPED,
                 stop_reason="kill_signal:bounced", stop_category=completion.SYSTEM_KILL),
            dict(planned_steps=3, steps_sent=2, status=m.EnrollmentStatus.ACTIVE),
        ]
        for index, kwargs in enumerate(rows):
            lead = m.Lead(strategy_id=strategy.id, source="apollo",
                          external_id=f"C{index}", full_name=f"Lead {index}",
                          email=f"c{index}@co.test", status=m.LeadStatus.VERIFIED)
            db_session.add(lead)
            db_session.flush()
            db_session.add(m.SequenceEnrollment(sequence_id=sequence.id,
                                                lead_id=lead.id, **kwargs))
        db_session.commit()

    def test_an_empty_campaign_has_no_rate_rather_than_zero(
            self, db_session, verified_strategy):
        metrics = completion.strategy_metrics(db_session, verified_strategy.id)
        assert metrics["completion_rate"] is None
        assert metrics["enrolled"] == 0

    def test_running_enrollments_are_in_neither_half_of_the_rate(
            self, db_session, email_sequence, verified_strategy):
        self._spread(db_session, email_sequence, verified_strategy)
        metrics = completion.strategy_metrics(db_session, verified_strategy.id)
        assert metrics["enrolled"] == 5
        assert metrics["running"] == 1
        assert metrics["finished"] == 4
        assert metrics["completion_rate"] == 0.5

    def test_the_unauthorised_drop_count_is_reported_on_its_own(
            self, db_session, email_sequence, verified_strategy):
        self._spread(db_session, email_sequence, verified_strategy)
        metrics = completion.strategy_metrics(db_session, verified_strategy.id)
        assert metrics["dropped"] == 2
        assert metrics["dropped_unauthorised"] == 1

    def test_the_breakdown_names_each_reason_and_says_if_it_was_a_decision(
            self, db_session, email_sequence, verified_strategy):
        self._spread(db_session, email_sequence, verified_strategy)
        reasons = {r["category"]: r for r in
                   completion.strategy_metrics(db_session, verified_strategy.id)["reasons"]}
        assert reasons[completion.REPLIED]["authorised"] is True
        assert reasons[completion.SYSTEM_KILL]["authorised"] is False
        assert all(r["label"] for r in reasons.values())

    def test_empty_categories_are_omitted_rather_than_listed_as_zero(
            self, db_session, email_sequence, verified_strategy):
        self._spread(db_session, email_sequence, verified_strategy)
        categories = {r["category"] for r in
                      completion.strategy_metrics(db_session, verified_strategy.id)["reasons"]}
        assert completion.BOUNCED not in categories

    def test_a_single_bad_sequence_is_visible_rather_than_averaged_away(
            self, db_session, email_sequence, verified_strategy):
        self._spread(db_session, email_sequence, verified_strategy)
        metrics = completion.strategy_metrics(db_session, verified_strategy.id)
        assert len(metrics["by_sequence"]) == 1
        assert metrics["by_sequence"][0]["completion_rate"] == 0.5
        assert metrics["by_sequence"][0]["name"] == email_sequence.name

    def test_pre_feature_enrollments_are_unknown_not_failures(
            self, db_session, email_sequence, verified_strategy, verified_leads):
        _enrollment(db_session, email_sequence, verified_leads[0],
                    status=m.EnrollmentStatus.COMPLETED)
        metrics = completion.strategy_metrics(db_session, verified_strategy.id)
        assert metrics["unknown"] == 1
        assert metrics["dropped"] == 0
        assert metrics["completion_rate"] is None

    def test_the_dropped_work_list_can_be_narrowed_to_the_actionable_ones(
            self, db_session, email_sequence, verified_strategy):
        self._spread(db_session, email_sequence, verified_strategy)
        everything = completion.dropped_enrollments(db_session, verified_strategy.id)
        actionable = completion.dropped_enrollments(db_session, verified_strategy.id,
                                                    unauthorised_only=True)
        assert len(everything) == 2
        assert len(actionable) == 1
        assert actionable[0]["stop_category"] == completion.SYSTEM_KILL
        assert actionable[0]["lead"]["email"]


class TestApi:
    def test_the_completion_endpoint(self, client, db_session, verified_strategy,
                                     test_user):
        response = client.get(f"/strategies/{verified_strategy.id}/completion",
                              headers=auth_headers(test_user))
        assert response.status_code == 200
        assert response.json()["strategy_id"] == str(verified_strategy.id)

    def test_completion_rides_along_on_the_analytics_response(
            self, client, db_session, verified_strategy, test_user):
        response = client.get(f"/strategies/{verified_strategy.id}/analytics",
                              headers=auth_headers(test_user))
        assert response.status_code == 200
        assert "completion" in response.json()

    def test_the_dropped_list_endpoint(self, client, db_session, email_sequence,
                                       verified_strategy, verified_leads, test_user):
        _enrollment(db_session, email_sequence, verified_leads[0], planned_steps=3,
                    steps_sent=1, status=m.EnrollmentStatus.STOPPED,
                    stop_reason="kill_signal:bounced",
                    stop_category=completion.SYSTEM_KILL, stopped_at=NOW)
        response = client.get(
            f"/strategies/{verified_strategy.id}/completion/dropped?unauthorised_only=true",
            headers=auth_headers(test_user))
        assert response.status_code == 200
        assert response.json()["total"] == 1

    def test_the_per_sequence_endpoint(self, client, db_session, email_sequence,
                                       test_user):
        response = client.get(f"/sequences/{email_sequence.id}/completion",
                              headers=auth_headers(test_user))
        assert response.status_code == 200
        assert response.json()["sequence_id"] == str(email_sequence.id)

    def test_another_account_cannot_read_completion(self, client, db_session,
                                                    verified_strategy):
        other = m.User(email="nosy@test.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        response = client.get(f"/strategies/{verified_strategy.id}/completion",
                              headers=auth_headers(other))
        assert response.status_code == 404

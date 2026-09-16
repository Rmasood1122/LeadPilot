"""Part 1 Feature 4 — per-mailbox deliverability health and auto-throttle.

The properties that matter:
  * a score is computed per MAILBOX, not per domain,
  * a throttle slows sending and never silently becomes a pause,
  * a pause DEFERS messages, never drops them,
  * a pause is only lifted by a person,
  * an unscored mailbox sends normally (absence of a check is not a block).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.services import mailbox_health
from tests.conftest import auth_headers

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
GOOD_AUTH = {"spf": True, "dkim": True, "dmarc": True, "dmarc_policy": "reject"}
NO_VOLUME = {"today": 0, "week": 0, "daily_baseline": 0.0, "spike": False}


@pytest.fixture(autouse=True)
def no_dns(monkeypatch):
    """No test may make a real DNS query."""
    monkeypatch.setattr("app.services.deliverability.dns_auth", lambda domain: dict(GOOD_AUTH))


def _sent(db_session, sequence, lead, ref, when, status=m.MessageStatus.SENT):
    message = m.Message(sequence_id=sequence.id, lead_id=lead.id,
                        channel=m.ChannelType.EMAIL, step_no=1, template="t",
                        status=status, sent_at=when, sender_ref=ref)
    db_session.add(message)
    db_session.commit()
    return message


# --------------------------------------------------------------------------
# The score
# --------------------------------------------------------------------------


class TestScore:
    def test_a_clean_mailbox_scores_full_marks(self):
        score, reasons = mailbox_health.score_for(GOOD_AUTH, 0.0, 0.0, NO_VOLUME)
        assert score == 100
        assert reasons == []

    def test_missing_auth_is_named_not_just_deducted(self):
        score, reasons = mailbox_health.score_for(
            {"spf": False, "dkim": False, "dmarc": False, "dmarc_policy": None},
            None, None, NO_VOLUME)
        # 100 - 25 (SPF) - 20 (DMARC) - 10 (DKIM). Deliberately above
        # PAUSE_BELOW: missing DNS records are fixable in an afternoon.
        assert score == 45
        assert any("SPF" in r for r in reasons)
        assert any("DMARC" in r for r in reasons)

    def test_a_monitoring_only_dmarc_costs_less_than_none_at_all(self):
        monitoring, _ = mailbox_health.score_for(
            {**GOOD_AUTH, "dmarc_policy": "none"}, None, None, NO_VOLUME)
        missing, _ = mailbox_health.score_for(
            {**GOOD_AUTH, "dmarc": False}, None, None, NO_VOLUME)
        assert missing < monitoring < 100

    def test_complaints_past_the_danger_line_cost_most(self):
        warn, _ = mailbox_health.score_for(GOOD_AUTH, 0.0015, None, NO_VOLUME)
        bad, _ = mailbox_health.score_for(GOOD_AUTH, 0.004, None, NO_VOLUME)
        assert bad < warn < 100

    def test_bounces_past_the_danger_line_cost_most(self):
        warn, _ = mailbox_health.score_for(GOOD_AUTH, None, 0.03, NO_VOLUME)
        bad, _ = mailbox_health.score_for(GOOD_AUTH, None, 0.08, NO_VOLUME)
        assert bad < warn < 100

    def test_a_volume_spike_is_a_deduction_with_the_numbers_in_it(self):
        score, reasons = mailbox_health.score_for(
            GOOD_AUTH, None, None,
            {"today": 90, "week": 120, "daily_baseline": 4.3, "spike": True})
        assert score == 90
        assert "90 today" in reasons[0]

    def test_unknown_rates_are_not_punished(self):
        """A brand new mailbox has no rates. That is not evidence of harm."""
        score, _ = mailbox_health.score_for(GOOD_AUTH, None, None, NO_VOLUME)
        assert score == 100

    def test_the_score_never_leaves_zero_to_one_hundred(self):
        score, _ = mailbox_health.score_for(
            {"spf": False, "dkim": False, "dmarc": False, "dmarc_policy": None},
            0.5, 0.5, {"today": 99, "week": 100, "daily_baseline": 0.1, "spike": True})
        assert 0 <= score <= 100


class TestBands:
    @pytest.mark.parametrize("score,state", [
        (100, mailbox_health.HEALTHY), (70, mailbox_health.HEALTHY),
        (69, mailbox_health.THROTTLED), (40, mailbox_health.THROTTLED),
        (39, mailbox_health.PAUSED), (0, mailbox_health.PAUSED),
    ])
    def test_state_thresholds(self, score, state):
        assert mailbox_health.state_for(score) == state

    def test_unauthenticated_but_quiet_is_throttled_rather_than_paused(self):
        """Missing DNS records are fixable in an afternoon. Stopping outreach
        outright would cost more than slowing it."""
        score, _ = mailbox_health.score_for(
            {"spf": False, "dkim": False, "dmarc": False, "dmarc_policy": None},
            None, None, NO_VOLUME)
        assert mailbox_health.state_for(score) == mailbox_health.THROTTLED

    def test_a_throttle_never_becomes_a_silent_pause(self):
        assert mailbox_health.throttled_cap(1) >= mailbox_health.MIN_THROTTLE_CAP
        assert mailbox_health.throttled_cap(0) >= mailbox_health.MIN_THROTTLE_CAP

    def test_a_throttle_is_a_real_reduction(self):
        assert mailbox_health.throttled_cap(100) == 25

    @pytest.mark.parametrize("score,expected", [
        (None, "unchecked"), (90, "good"), (70, "good"), (50, "at_risk"), (10, "bad"),
    ])
    def test_band_names(self, score, expected):
        assert mailbox_health.band(score) == expected


# --------------------------------------------------------------------------
# The inputs, per mailbox
# --------------------------------------------------------------------------


class TestInputs:
    def test_bounces_are_counted_for_this_mailbox_only(
            self, db_session, email_sequence, verified_leads, gmail_account):
        lead = verified_leads[0]
        mine = _sent(db_session, email_sequence, lead, "box-a", NOW - timedelta(days=1))
        _sent(db_session, email_sequence, verified_leads[1], "box-b", NOW - timedelta(days=1))
        db_session.add(m.Outcome(lead_id=lead.id, message_id=mine.id,
                                 event=m.OutcomeEvent.BOUNCED, channel="email",
                                 ts=NOW - timedelta(days=1)))
        db_session.commit()
        assert mailbox_health.bounce_rate(db_session, "box-a", NOW) == 1.0
        assert mailbox_health.bounce_rate(db_session, "box-b", NOW) == 0.0

    def test_a_mailbox_that_has_sent_nothing_has_no_rate(self, db_session):
        assert mailbox_health.bounce_rate(db_session, "quiet", NOW) is None

    def test_the_complaint_rate_counts_unsubscribes_and_stop_replies(
            self, db_session, email_sequence, verified_leads, test_user,
            product_with_strategy):
        lead = verified_leads[0]
        message = _sent(db_session, email_sequence, lead, "box-a", NOW - timedelta(days=1))
        db_session.add(m.Outcome(lead_id=lead.id, message_id=message.id,
                                 event=m.OutcomeEvent.UNSUBSCRIBED, channel="email",
                                 ts=NOW - timedelta(days=1)))
        db_session.commit()
        rate, source = mailbox_health.complaint_rate(db_session, test_user.id, "box-a", NOW)
        assert rate == 1.0
        assert source == "proxy"

    def test_the_complaint_source_is_always_labelled_a_proxy(
            self, db_session, test_user):
        """There is no feedback loop connected. The payload must say so."""
        _rate, source = mailbox_health.complaint_rate(db_session, test_user.id, "x", NOW)
        assert source == "proxy"

    def test_a_volume_spike_compares_today_against_the_days_before_it(
            self, db_session, email_sequence, verified_leads, gmail_account):
        lead = verified_leads[0]
        for _ in range(7):
            _sent(db_session, email_sequence, lead, "box-a", NOW - timedelta(days=3))
        for _ in range(30):
            _sent(db_session, email_sequence, lead, "box-a", NOW)
        vol = mailbox_health.volume(db_session, "box-a", NOW)
        assert vol["today"] == 30
        assert vol["spike"] is True

    def test_a_steady_mailbox_is_not_a_spike(
            self, db_session, email_sequence, verified_leads, gmail_account):
        lead = verified_leads[0]
        for day in range(7):
            for _ in range(25):
                _sent(db_session, email_sequence, lead, "box-a", NOW - timedelta(days=day))
        assert mailbox_health.volume(db_session, "box-a", NOW)["spike"] is False

    def test_a_small_day_is_never_a_spike_however_the_ratio_looks(
            self, db_session, email_sequence, verified_leads, gmail_account):
        lead = verified_leads[0]
        _sent(db_session, email_sequence, lead, "box-a", NOW - timedelta(days=3))
        for _ in range(5):
            _sent(db_session, email_sequence, lead, "box-a", NOW)
        assert mailbox_health.volume(db_session, "box-a", NOW)["spike"] is False


# --------------------------------------------------------------------------
# Refresh
# --------------------------------------------------------------------------


class TestRefresh:
    def test_a_row_is_created_per_mailbox(self, db_session, test_user, gmail_account):
        rows = mailbox_health.refresh(db_session, test_user.id, now=NOW)
        assert len(rows) == 1
        assert rows[0]["mailbox_ref"] == str(gmail_account.id)
        assert rows[0]["state"] == mailbox_health.HEALTHY
        assert rows[0]["complaint_source"] == "proxy"

    def test_refresh_is_an_upsert_not_an_append(self, db_session, test_user, gmail_account):
        mailbox_health.refresh(db_session, test_user.id, now=NOW)
        mailbox_health.refresh(db_session, test_user.id, now=NOW + timedelta(hours=4))
        assert db_session.query(m.MailboxHealth).count() == 1

    def test_a_consumer_mailbox_is_not_scored_on_dns_it_does_not_own(
            self, db_session, test_user, gmail_account):
        """A gmail.com sender's reputation is Google's. Deducting for its
        missing SPF would throttle a perfectly fine mailbox."""
        gmail_account.email_address = "founder@gmail.com"
        db_session.commit()
        row = mailbox_health.refresh(db_session, test_user.id, now=NOW)[0]
        assert row["auth"]["spf"] is None
        assert row["score"] == 100

    def test_a_bad_mailbox_is_paused_and_the_reason_is_recorded(
            self, db_session, test_user, gmail_account, email_sequence, verified_leads,
            monkeypatch):
        monkeypatch.setattr("app.services.deliverability.dns_auth",
                            lambda domain: {"spf": False, "dkim": False, "dmarc": False,
                                            "dmarc_policy": None})
        lead = verified_leads[0]
        message = _sent(db_session, email_sequence, lead, str(gmail_account.id),
                        NOW - timedelta(days=1))
        db_session.add(m.Outcome(lead_id=lead.id, message_id=message.id,
                                 event=m.OutcomeEvent.BOUNCED, channel="email",
                                 ts=NOW - timedelta(days=1)))
        db_session.commit()
        row = mailbox_health.refresh(db_session, test_user.id, now=NOW)[0]
        assert row["state"] == mailbox_health.PAUSED
        assert row["reason"]
        assert row["paused_at"]

    def test_a_dns_failure_keeps_the_last_known_auth_rather_than_blanking_it(
            self, db_session, test_user, gmail_account, monkeypatch):
        mailbox_health.refresh(db_session, test_user.id, now=NOW)
        monkeypatch.setattr("app.services.deliverability.dns_auth",
                            lambda domain: (_ for _ in ()).throw(RuntimeError("no DNS")))
        row = mailbox_health.refresh(db_session, test_user.id, now=NOW)[0]
        assert row["auth"]["spf"] is True

    def test_a_refresh_never_resumes_a_paused_mailbox(
            self, db_session, test_user, gmail_account):
        mailbox_health.refresh(db_session, test_user.id, now=NOW)
        row = db_session.query(m.MailboxHealth).one()
        row.state = mailbox_health.PAUSED
        db_session.commit()
        after = mailbox_health.refresh(db_session, test_user.id, now=NOW)[0]
        assert after["state"] == mailbox_health.PAUSED
        assert after["score"] == 100      # healthy again, still paused

    def test_refresh_all_survives_one_user_failing(
            self, db_session, test_user, gmail_account, monkeypatch):
        monkeypatch.setattr(mailbox_health, "refresh",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        result = mailbox_health.refresh_all(db_session, now=NOW)
        assert result["failed"] == 1
        assert result["users"] == 1


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


class TestGate:
    def test_an_unscored_mailbox_sends_normally(self, db_session, test_user):
        """Absence of a check is not a reason to block sending."""
        assert mailbox_health.gate(db_session, test_user.id, "never-checked") == {
            "state": mailbox_health.HEALTHY, "cap": None, "reason": None}

    def test_a_throttled_mailbox_reports_a_cap(self, db_session, test_user, gmail_account):
        db_session.add(m.MailboxHealth(user_id=test_user.id,
                                       mailbox_ref=str(gmail_account.id), channel="email",
                                       score=50, state=mailbox_health.THROTTLED,
                                       throttle_cap=5, reason="Bounce rate 3.0%"))
        db_session.commit()
        gate = mailbox_health.gate(db_session, test_user.id, str(gmail_account.id))
        assert gate["cap"] == 5
        assert gate["reason"]

    def test_a_paused_mailbox_reports_paused(self, db_session, test_user, gmail_account):
        db_session.add(m.MailboxHealth(user_id=test_user.id,
                                       mailbox_ref=str(gmail_account.id), channel="email",
                                       score=10, state=mailbox_health.PAUSED,
                                       reason="Complaint rate 0.90%"))
        db_session.commit()
        assert mailbox_health.gate(db_session, test_user.id,
                                   str(gmail_account.id))["state"] == mailbox_health.PAUSED

    def test_resuming_is_recorded_as_a_human_decision(
            self, db_session, test_user, gmail_account):
        db_session.add(m.MailboxHealth(user_id=test_user.id,
                                       mailbox_ref=str(gmail_account.id), channel="email",
                                       score=85, state=mailbox_health.PAUSED,
                                       daily_cap=40))
        db_session.commit()
        row = mailbox_health.resume(db_session, test_user.id, str(gmail_account.id),
                                    actor_user_id=test_user.id, now=NOW)
        assert row.state == mailbox_health.HEALTHY
        assert row.resumed_by_user_id == test_user.id
        assert row.resumed_at == NOW

    def test_resuming_a_still_unhealthy_mailbox_throttles_rather_than_frees_it(
            self, db_session, test_user, gmail_account):
        db_session.add(m.MailboxHealth(user_id=test_user.id,
                                       mailbox_ref=str(gmail_account.id), channel="email",
                                       score=50, state=mailbox_health.PAUSED,
                                       daily_cap=40))
        db_session.commit()
        row = mailbox_health.resume(db_session, test_user.id, str(gmail_account.id))
        assert row.state == mailbox_health.THROTTLED
        assert row.throttle_cap == 10

    def test_resuming_an_unknown_mailbox_raises_lookup_error(self, db_session, test_user):
        with pytest.raises(LookupError):
            mailbox_health.resume(db_session, test_user.id, "nope")


class TestSendGate:
    def test_a_paused_mailbox_defers_the_message_instead_of_dropping_it(
            self, db_session, fake_claude, enrolled, verified_leads, gmail_account,
            test_user, fake_channel, monkeypatch):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        db_session.add(m.MailboxHealth(user_id=test_user.id,
                                       mailbox_ref=str(gmail_account.id), channel="email",
                                       score=10, state=mailbox_health.PAUSED,
                                       reason="Complaint rate 0.90%"))
        db_session.commit()
        message = db_session.query(m.Message).filter_by(
            status=m.MessageStatus.SCHEDULED).first()
        result = outreach_tasks.send_message_impl(db_session, message.id, now=NOW)
        db_session.refresh(message)
        assert result == "deferred_mailbox_paused"
        assert message.status is m.MessageStatus.SCHEDULED    # not cancelled
        assert message.scheduled_at.replace(tzinfo=timezone.utc) > NOW
        assert "mailbox paused" in (message.error or "")
        assert fake_channel.sent == []

    def test_a_healthy_mailbox_sends_exactly_as_before(
            self, db_session, fake_claude, enrolled, gmail_account, fake_channel,
            monkeypatch):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        message = db_session.query(m.Message).filter_by(
            status=m.MessageStatus.SCHEDULED).first()
        assert outreach_tasks.send_message_impl(db_session, message.id, now=NOW) == "sent"


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


class TestApi:
    def test_an_unchecked_mailbox_is_listed_rather_than_omitted(
            self, client, db_session, gmail_account, test_user):
        response = client.get("/deliverability/mailboxes", headers=auth_headers(test_user))
        assert response.status_code == 200
        body = response.json()
        assert body["mailboxes"][0]["band"] == "unchecked"
        assert "proxy" in body["complaint_note"]

    def test_the_thresholds_are_published_so_a_score_can_be_read(
            self, client, db_session, gmail_account, test_user):
        body = client.get("/deliverability/mailboxes",
                          headers=auth_headers(test_user)).json()
        assert body["thresholds"]["pause_below"] == mailbox_health.PAUSE_BELOW
        assert body["thresholds"]["throttle_below"] == mailbox_health.THROTTLE_BELOW

    def test_refresh_scores_the_mailboxes(self, client, db_session, gmail_account,
                                          test_user):
        response = client.post("/deliverability/mailboxes/refresh",
                               headers=auth_headers(test_user))
        assert response.status_code == 200
        assert response.json()["mailboxes"][0]["score"] == 100

    def test_resume_un_pauses(self, client, db_session, gmail_account, test_user):
        db_session.add(m.MailboxHealth(user_id=test_user.id,
                                       mailbox_ref=str(gmail_account.id), channel="email",
                                       score=90, state=mailbox_health.PAUSED))
        db_session.commit()
        response = client.post(
            f"/deliverability/mailboxes/{gmail_account.id}/resume",
            headers=auth_headers(test_user))
        assert response.status_code == 200
        assert response.json()["mailboxes"][0]["state"] == mailbox_health.HEALTHY

    def test_resuming_an_unknown_mailbox_is_a_404(self, client, db_session,
                                                  gmail_account, test_user):
        response = client.post("/deliverability/mailboxes/not-a-mailbox/resume",
                               headers=auth_headers(test_user))
        assert response.status_code == 404

    def test_another_account_sees_only_its_own_mailboxes(
            self, client, db_session, gmail_account):
        other = m.User(email="other-mb@test.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        response = client.get("/deliverability/mailboxes", headers=auth_headers(other))
        assert response.status_code == 200
        assert response.json()["mailboxes"] == []

"""Daily send approval -- LEGAL/SAFETY GUARD (docs/features/daily-send-approval.md).

Founder decision 2026-10-11: no AUTOMATIC send goes out on a day nobody
approved automatic sending for that channel; LinkedIn needs an explicit
acknowledgement that LinkedIn may restrict accounts that use automation.

The properties that matter:
  * the production default is ON; off = exactly the previous behaviour,
  * without today's approval an automatic message is DEFERRED -- still
    SCHEDULED, never failed, never dropped, never sent,
  * approval is per channel and expires at the account's local midnight,
  * LinkedIn approval without the acknowledgement is refused (422),
  * the owner is notified once per day, by transactional email (never the
    outreach channel) and push, and only the owner,
  * messages a person approved one by one are not gated,
  * a lookup error fails CLOSED (deferred),
  * one account's approval never touches another account's messages.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import pytest

from app.db import models as m
from app.services import daily_send_approval as dsa
from app.services import system_settings
from tests.conftest import auth_headers

NOW = datetime(2026, 8, 11, 10, 0, tzinfo=timezone.utc)   # Tuesday 10:00 UTC (in window)
NEXT_UTC_MIDNIGHT = datetime(2026, 8, 12, 0, 0, tzinfo=timezone.utc)

#: Captured at import, before conftest's autouse `daily_send_approval_off`
#: replaces it for the test run.
_REAL_ENABLED = dsa.enabled


@pytest.fixture(autouse=True)
def approval_on(monkeypatch):
    """Undo conftest's `daily_send_approval_off`: this module tests the gate,
    reading the REAL flag (whose default is the founder's True)."""
    monkeypatch.setattr(dsa, "enabled", _REAL_ENABLED)


@pytest.fixture()
def wired(monkeypatch, fake_channel):
    from app.workers import outreach_tasks

    monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
    return outreach_tasks


def _scheduled(db_session):
    return (db_session.query(m.Message).filter_by(status=m.MessageStatus.SCHEDULED)
            .order_by(m.Message.created_at, m.Message.id).all())


def _ordinary_titles(db_session, leads):
    for row in leads:
        row.title = "Operations Manager"
    db_session.commit()


def _as_linkedin(db_session, message):
    lead = db_session.get(m.Lead, message.lead_id)
    lead.linkedin_url = f"https://www.linkedin.com/in/{lead.external_id.lower()}"
    message.channel = m.ChannelType.LINKEDIN
    db_session.commit()
    return message


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------


class TestSettings:
    def test_the_founder_default_is_on_and_covers_every_automatic_channel(self, db_session):
        assert system_settings.DEFAULTS[dsa.FLAG][0] is True
        assert dsa.enabled(db_session) is True
        assert dsa.gated_channels(db_session) == ("email", "linkedin", "whatsapp", "phone")

    def test_a_channel_setting_with_no_valid_name_gates_everything(self, db_session):
        system_settings.set(db_session, dsa.CHANNELS_SETTING, "carrier-pigeon")
        assert dsa.gated_channels(db_session) == dsa.ALL_CHANNELS

    def test_unknown_names_are_ignored(self, db_session):
        system_settings.set(db_session, dsa.CHANNELS_SETTING, "linkedin, fax")
        assert dsa.gated_channels(db_session) == ("linkedin",)


# --------------------------------------------------------------------------
# The send path
# --------------------------------------------------------------------------


class TestSendPath:
    def test_flag_off_is_the_previous_behaviour(self, db_session, enrolled, verified_leads,
                                                wired, fake_channel):
        system_settings.set(db_session, dsa.FLAG, False)
        message = _scheduled(db_session)[0]
        assert wired.send_message_impl(db_session, message.id, now=NOW) == "sent"
        assert len(fake_channel.sent) == 1
        assert db_session.query(m.DailySendApproval).count() == 0

    def test_no_approval_defers_never_sends_never_fails(self, db_session, enrolled,
                                                        verified_leads, wired, fake_channel):
        message = _scheduled(db_session)[0]
        result = wired.send_message_impl(db_session, message.id, now=NOW)
        db_session.refresh(message)
        assert result == dsa.SEND_RESULT_AWAITING
        assert message.status is m.MessageStatus.SCHEDULED
        assert message.error.startswith(dsa.ERROR_PREFIX)
        assert message.scheduled_at.replace(tzinfo=timezone.utc) == NEXT_UTC_MIDNIGHT
        assert message.body is None           # nothing rendered, no model call spent
        assert fake_channel.sent == []
        assert db_session.query(m.Outcome).filter_by(event=m.OutcomeEvent.SENT).count() == 0

    def test_approval_releases_the_deferred_message_and_it_sends(
            self, db_session, enrolled, verified_leads, wired, fake_channel, test_user):
        message = _scheduled(db_session)[0]
        wired.send_message_impl(db_session, message.id, now=NOW)
        out = dsa.approve(db_session, test_user.id, actor_id=test_user.id,
                          channels=["email"], now=NOW + timedelta(minutes=5))
        assert out["released"] == 1
        db_session.refresh(message)
        assert message.error is None
        assert message.scheduled_at.replace(tzinfo=timezone.utc) == NOW + timedelta(minutes=5)
        assert wired.send_message_impl(db_session, message.id,
                                       now=NOW + timedelta(minutes=6)) == "sent"
        assert len(fake_channel.sent) == 1

    def test_email_only_approval_keeps_linkedin_deferred(
            self, db_session, enrolled, verified_leads, wired, fake_channel, test_user):
        message = _as_linkedin(db_session, _scheduled(db_session)[0])
        dsa.approve(db_session, test_user.id, actor_id=test_user.id, channels=["email"],
                    now=NOW)
        result = wired.send_message_impl(db_session, message.id, now=NOW)
        db_session.refresh(message)
        assert result == dsa.SEND_RESULT_CHANNEL
        assert message.status is m.MessageStatus.SCHEDULED
        assert "LinkedIn was not approved" in message.error
        assert fake_channel.sent == []

    def test_a_later_linkedin_approval_releases_only_linkedin(
            self, db_session, enrolled, verified_leads, test_user, wired):
        li = _as_linkedin(db_session, _scheduled(db_session)[0])
        email = _scheduled(db_session)[1]
        wired.send_message_impl(db_session, li.id, now=NOW)
        wired.send_message_impl(db_session, email.id, now=NOW)
        out = dsa.approve(db_session, test_user.id, actor_id=test_user.id,
                          channels=["linkedin"], linkedin_risk_acknowledged=True,
                          linkedin_warning_version=dsa.LINKEDIN_WARNING_VERSION, now=NOW)
        assert out["released"] == 1
        db_session.refresh(li)
        db_session.refresh(email)
        assert li.error is None
        assert email.error.startswith(dsa.ERROR_PREFIX)

    def test_approval_expires_at_local_midnight(self, db_session, enrolled, verified_leads,
                                                wired, test_user):
        dsa.approve(db_session, test_user.id, actor_id=test_user.id, channels=["email"],
                    now=NOW)
        message = _scheduled(db_session)[0]
        strategy = db_session.get(m.Strategy, db_session.get(m.Lead, message.lead_id).strategy_id)
        just_before = NEXT_UTC_MIDNIGHT - timedelta(seconds=1)
        assert dsa.send_hold(db_session, message, strategy, just_before) is None
        hold = dsa.send_hold(db_session, message, strategy, NEXT_UTC_MIDNIGHT)
        assert hold is not None and hold.result == dsa.SEND_RESULT_AWAITING
        assert hold.local_date.isoformat() == "2026-08-12"

    def test_the_day_follows_the_owners_calendar_timezone(self, db_session, enrolled,
                                                          verified_leads, test_user):
        db_session.add(m.CalendarAvailability(user_id=test_user.id, day_of_week=1,
                                              start_time=time(9), end_time=time(17),
                                              timezone="America/New_York"))
        db_session.commit()
        assert dsa.account_timezone(db_session, test_user.id) == (
            "America/New_York", dsa.TZ_SOURCE_CALENDAR)
        dsa.approve(db_session, test_user.id, actor_id=test_user.id, channels=["email"],
                    now=NOW)   # 06:00 in New York, Aug 11
        message = _scheduled(db_session)[0]
        strategy = db_session.get(m.Strategy, db_session.get(m.Lead, message.lead_id).strategy_id)
        ny_midnight = datetime(2026, 8, 12, 4, 0, tzinfo=timezone.utc)
        # 00:30 UTC is still Aug 11 in New York: the approval holds.
        assert dsa.send_hold(db_session, message, strategy,
                             NEXT_UTC_MIDNIGHT + timedelta(minutes=30)) is None
        hold = dsa.send_hold(db_session, message, strategy, ny_midnight)
        assert hold is not None
        assert hold.until == datetime(2026, 8, 13, 4, 0, tzinfo=timezone.utc)
        state = dsa.state(db_session, test_user.id, NOW)
        assert state["valid_until"] == ny_midnight.isoformat()

    def test_without_a_calendar_the_day_is_utc_and_says_so(self, db_session, test_user):
        assert dsa.account_timezone(db_session, test_user.id) == ("UTC", dsa.TZ_SOURCE_UTC)
        assert dsa.state(db_session, test_user.id, NOW)["timezone_source"] == "utc_fallback"

    def test_a_lookup_error_fails_closed(self, db_session, enrolled, verified_leads, wired,
                                         fake_channel, monkeypatch):
        def broken(*_a, **_k):
            raise RuntimeError("database hiccup")

        monkeypatch.setattr(dsa, "account_timezone", broken)
        message = _scheduled(db_session)[0]
        result = wired.send_message_impl(db_session, message.id, now=NOW)
        db_session.refresh(message)
        assert result == dsa.SEND_RESULT_UNAVAILABLE
        assert message.status is m.MessageStatus.SCHEDULED
        assert message.scheduled_at.replace(tzinfo=timezone.utc) == NOW + timedelta(hours=1)
        assert "fails closed" in message.error
        assert fake_channel.sent == []

    def test_decline_holds_then_a_later_approval_same_day_sends(
            self, db_session, enrolled, verified_leads, wired, fake_channel, test_user,
            mailbox, queued_jobs):
        dsa.decline(db_session, test_user.id, actor_id=test_user.id, note="not today", now=NOW)
        message = _scheduled(db_session)[0]
        assert wired.send_message_impl(db_session, message.id, now=NOW) == \
            dsa.SEND_RESULT_DECLINED
        assert mailbox == []                    # a decision was made: no nagging
        assert fake_channel.sent == []
        dsa.approve(db_session, test_user.id, actor_id=test_user.id, channels=["email"],
                    now=NOW + timedelta(hours=1))
        assert wired.send_message_impl(db_session, message.id,
                                       now=NOW + timedelta(hours=1)) == "sent"

    def test_an_ungated_channel_is_not_held(self, db_session, enrolled, verified_leads,
                                            wired):
        system_settings.set(db_session, dsa.CHANNELS_SETTING, "linkedin")
        message = _scheduled(db_session)[0]
        assert wired.send_message_impl(db_session, message.id, now=NOW) == "sent"

    def test_suppression_still_wins_over_a_hold(self, db_session, enrolled, verified_leads,
                                                wired):
        """The gate sits AFTER the cancel gates: a suppressed lead is cancelled,
        not parked waiting for an approval that would never be right."""
        message = _scheduled(db_session)[0]
        lead = db_session.get(m.Lead, message.lead_id)
        db_session.add(m.SuppressionEntry(email=lead.email, reason="unsubscribed"))
        db_session.commit()
        assert wired.send_message_impl(db_session, message.id, now=NOW) == "cancelled_suppressed"


# --------------------------------------------------------------------------
# Automatic vs human
# --------------------------------------------------------------------------


class TestAutomaticVsHuman:
    def test_a_send_review_approval_is_a_human_decision(
            self, db_session, enrolled, verified_leads, wired, fake_channel, test_user):
        _ordinary_titles(db_session, verified_leads)
        message = _scheduled(db_session)[0]
        db_session.add(m.SendReview(message_id=message.id, lead_id=message.lead_id,
                                    user_id=test_user.id, status="approved",
                                    triggers_json=[], subject_snapshot="Hello",
                                    body_snapshot="Approved words", content_hash="x"))
        db_session.commit()
        assert wired.send_message_impl(db_session, message.id, now=NOW) == "sent"
        assert fake_channel.sent[0].body.startswith("Approved words")

    @pytest.mark.parametrize("auto_sent,expected", [(False, False), (True, True)])
    def test_reply_copilot_person_approved_vs_auto_sent(self, db_session, enrolled,
                                                        verified_leads, test_user,
                                                        auto_sent, expected):
        message = _scheduled(db_session)[0]
        message.origin = "reply_copilot"
        reply = m.InboundReply(lead_id=message.lead_id, channel="email",
                               from_address="lead0@co0.com", body="Send me a time")
        db_session.add(reply)
        db_session.flush()
        db_session.add(m.ReplyDraft(user_id=test_user.id, reply_id=reply.id,
                                    lead_id=message.lead_id, channel="email",
                                    intent="positive", draft_body="Tuesday works",
                                    status="approved", message_id=message.id,
                                    auto_sent=auto_sent))
        db_session.commit()
        assert dsa.is_automatic(db_session, message) is expected

    def test_reply_copilot_without_a_draft_fails_closed(self, db_session, enrolled):
        message = _scheduled(db_session)[0]
        message.origin = "reply_copilot"
        db_session.commit()
        assert dsa.is_automatic(db_session, message) is True

    @pytest.mark.parametrize("origin", [None, "reengagement", "notnow_memory"])
    def test_sequence_followup_and_reengagement_sends_are_automatic(
            self, db_session, enrolled, origin):
        message = _scheduled(db_session)[0]
        message.origin = origin
        db_session.commit()
        assert dsa.is_automatic(db_session, message) is True

    def test_queued_counts_skip_human_approved_messages(self, db_session, enrolled,
                                                        verified_leads, test_user):
        rows = _scheduled(db_session)
        db_session.add(m.SendReview(message_id=rows[0].id, lead_id=rows[0].lead_id,
                                    user_id=test_user.id, status="approved",
                                    triggers_json=[], content_hash="x"))
        db_session.commit()
        assert dsa.queued_counts(db_session, test_user.id, NOW)["email"] == 2


# --------------------------------------------------------------------------
# Notification
# --------------------------------------------------------------------------


class TestNotification:
    def test_first_due_send_notifies_the_owner_once_per_day(
            self, db_session, enrolled, verified_leads, wired, fake_channel, test_user,
            mailbox, queued_jobs):
        first, second = _scheduled(db_session)[:2]
        wired.send_message_impl(db_session, first.id, now=NOW)
        wired.send_message_impl(db_session, second.id, now=NOW + timedelta(minutes=1))
        # Email: once, to the owner only, through the transactional gateway.
        assert len(mailbox) == 1
        assert mailbox[0]["to"] == test_user.email
        assert "/send-approval" in mailbox[0]["text"]
        assert "Email: 3" in mailbox[0]["text"]
        assert dsa.LINKEDIN_QUESTION in mailbox[0]["text"]
        # Never through the outreach channel.
        assert fake_channel.sent == []
        # Push: once, through the notification hub.
        events = [e for e in queued_jobs["events"] if e[1] == dsa.EVENT]
        assert len(events) == 1
        assert events[0][0] == str(test_user.id)
        assert events[0][2]["deep_link"] == "/send-approval"
        assert "Email: 3" in events[0][2]["body"]
        row = db_session.query(m.DailySendApproval).one()
        assert row.notified_at is not None
        assert row.notify_result_json["email"] == "sent"

    def test_the_next_day_notifies_again(self, db_session, enrolled, verified_leads, wired,
                                         mailbox):
        message = _scheduled(db_session)[0]
        wired.send_message_impl(db_session, message.id, now=NOW)
        wired.send_message_impl(db_session, message.id, now=NOW + timedelta(days=1))
        assert len(mailbox) == 2
        assert db_session.query(m.DailySendApproval).count() == 2

    def test_an_email_failure_does_not_undo_the_deferral(self, db_session, enrolled,
                                                         verified_leads, wired, monkeypatch):
        from app.services import email_sender

        def down(**_k):
            raise email_sender.EmailSendError("relay down")

        monkeypatch.setattr(email_sender, "send_email", down)
        message = _scheduled(db_session)[0]
        assert wired.send_message_impl(db_session, message.id, now=NOW) == \
            dsa.SEND_RESULT_AWAITING
        row = db_session.query(m.DailySendApproval).one()
        assert row.notify_result_json["email"] == "failed"

    def test_email_content_states_the_linkedin_risk(self):
        content = dsa.email_content({"email": 2, "linkedin": 4},
                                    NOW.date(), "UTC", linkedin_gated=True)
        assert "LinkedIn: 4" in content["text"]
        assert "restrict or suspend" in content["text"]
        assert dsa.LINKEDIN_QUESTION in content["text"]
        assert "<script" not in content["html"]


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------


class TestAudit:
    def test_an_approval_writes_the_full_record(self, db_session, enrolled, test_user):
        dsa.approve(db_session, test_user.id, actor_id=test_user.id,
                    channels=["email", "linkedin"], linkedin_risk_acknowledged=True,
                    linkedin_warning_version=dsa.LINKEDIN_WARNING_VERSION, now=NOW)
        row = db_session.query(m.ComplianceAuditLog).filter_by(
            decision=dsa.AUDIT_APPROVED).one()
        checks = row.checks_json
        assert row.user_id == test_user.id
        assert checks["approver_user_id"] == str(test_user.id)
        assert checks["channels_approved"] == ["email", "linkedin"]
        assert checks["linkedin_risk_acknowledged"] is True
        assert checks["linkedin_warning_version"] == dsa.LINKEDIN_WARNING_VERSION
        assert checks["linkedin_warning_text"] == dsa.LINKEDIN_WARNING_TEXT
        assert checks["queued_counts"]["email"] == 3
        assert checks["local_date"] == "2026-08-11"
        assert checks["decided_at"] == NOW.isoformat()

    def test_a_decline_is_audited(self, db_session, test_user):
        dsa.decline(db_session, test_user.id, actor_id=test_user.id, note="busy", now=NOW)
        row = db_session.query(m.ComplianceAuditLog).filter_by(
            decision=dsa.AUDIT_DECLINED).one()
        assert row.checks_json["note"] == "busy"


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


class TestApi:
    def test_today_shows_counts_and_the_linkedin_warning(self, client, enrolled, test_user):
        body = client.get("/send-approval/today", headers=auth_headers(test_user)).json()
        assert body["enabled"] is True
        assert body["status"] == "pending"
        assert body["queued"]["email"] == 3
        assert body["queued"]["linkedin"] == 0
        assert body["approved_channels"] == []
        assert body["linkedin_warning"]["version"] == dsa.LINKEDIN_WARNING_VERSION
        assert dsa.LINKEDIN_QUESTION in body["linkedin_warning"]["text"]
        assert body["can_decide"] is True

    def test_approve_email(self, client, db_session, enrolled, test_user):
        r = client.post("/send-approval/approve", json={"channels": ["email"]},
                        headers=auth_headers(test_user))
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"
        assert r.json()["approved_channels"] == ["email"]

    def test_linkedin_without_acknowledgement_is_422(self, client, db_session, test_user):
        r = client.post("/send-approval/approve", json={"channels": ["email", "linkedin"]},
                        headers=auth_headers(test_user))
        assert r.status_code == 422
        r = client.post("/send-approval/approve",
                        json={"channels": ["linkedin"], "linkedin_risk_acknowledged": True},
                        headers=auth_headers(test_user))
        assert r.status_code == 422          # the warning version shown is required too
        assert db_session.query(m.DailySendApproval).count() == 0
        assert db_session.query(m.ComplianceAuditLog).count() == 0

    def test_a_stale_warning_version_is_409(self, client, test_user):
        r = client.post("/send-approval/approve",
                        json={"channels": ["linkedin"], "linkedin_risk_acknowledged": True,
                              "linkedin_warning_version": "li-automation-old"},
                        headers=auth_headers(test_user))
        assert r.status_code == 409

    def test_linkedin_with_acknowledgement(self, client, test_user):
        r = client.post("/send-approval/approve",
                        json={"channels": ["linkedin"], "linkedin_risk_acknowledged": True,
                              "linkedin_warning_version": dsa.LINKEDIN_WARNING_VERSION},
                        headers=auth_headers(test_user))
        assert r.status_code == 200
        assert r.json()["approved_channels"] == ["linkedin"]
        assert r.json()["linkedin_risk_acknowledged"] is True

    @pytest.mark.parametrize("channels", [[], ["fax"]])
    def test_bad_channel_lists_are_422(self, client, test_user, channels):
        assert client.post("/send-approval/approve", json={"channels": channels},
                           headers=auth_headers(test_user)).status_code == 422

    def test_decline(self, client, test_user):
        r = client.post("/send-approval/decline", json={"note": "Not today"},
                        headers=auth_headers(test_user))
        assert r.status_code == 200
        assert r.json()["status"] == "declined"

    def test_an_sdr_can_read_but_not_decide(self, client, db_session, test_user):
        from app.services import workspaces

        ws = workspaces.personal_workspace(db_session, test_user)
        sdr = m.User(email="sdr@approval.dev", email_verified=True)
        db_session.add(sdr)
        db_session.flush()
        db_session.add(m.WorkspaceMember(workspace_id=ws.id, user_id=sdr.id, role="sdr"))
        db_session.commit()
        headers = {**auth_headers(sdr), "X-Workspace-Id": str(ws.id)}
        body = client.get("/send-approval/today", headers=headers).json()
        assert body["can_decide"] is False
        assert client.post("/send-approval/approve", json={"channels": ["email"]},
                           headers=headers).status_code == 403
        assert client.post("/send-approval/decline", json={},
                           headers=headers).status_code == 403
        assert db_session.query(m.DailySendApproval).count() == 0

    def test_a_manager_decides_and_is_recorded_as_the_approver(self, client, db_session,
                                                               test_user):
        from app.services import workspaces

        ws = workspaces.personal_workspace(db_session, test_user)
        manager = m.User(email="mgr@approval.dev", email_verified=True)
        db_session.add(manager)
        db_session.flush()
        db_session.add(m.WorkspaceMember(workspace_id=ws.id, user_id=manager.id,
                                         role="manager"))
        db_session.commit()
        headers = {**auth_headers(manager), "X-Workspace-Id": str(ws.id)}
        r = client.post("/send-approval/approve", json={"channels": ["email"]},
                        headers=headers)
        assert r.status_code == 200, r.text
        row = db_session.query(m.DailySendApproval).one()
        assert row.user_id == test_user.id               # the ACCOUNT's day
        assert row.decided_by_user_id == manager.id      # the PERSON who decided


# --------------------------------------------------------------------------
# Tenancy
# --------------------------------------------------------------------------


class TestTenancy:
    def test_another_accounts_approval_never_releases_or_counts_these_messages(
            self, client, db_session, enrolled, verified_leads, wired, fake_channel,
            test_user):
        other = m.User(email="other-approval@test.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        message = _scheduled(db_session)[0]
        wired.send_message_impl(db_session, message.id, now=NOW)

        body = client.get("/send-approval/today", headers=auth_headers(other)).json()
        assert body["queued"]["email"] == 0
        r = client.post("/send-approval/approve", json={"channels": ["email"]},
                        headers=auth_headers(other))
        assert r.status_code == 200
        assert r.json()["released"] == 0
        db_session.refresh(message)
        assert message.error.startswith(dsa.ERROR_PREFIX)
        # The other account approving the SAME day does not let this one's out.
        dsa.approve(db_session, other.id, actor_id=other.id, channels=["email"], now=NOW)
        assert wired.send_message_impl(db_session, message.id, now=NOW) == \
            dsa.SEND_RESULT_AWAITING
        assert fake_channel.sent == []
        # The owner sees only their own row.
        mine = client.get("/send-approval/today", headers=auth_headers(test_user)).json()
        assert mine["status"] == "pending"


# --------------------------------------------------------------------------
# Review fixes (2b94fdc review)
# --------------------------------------------------------------------------


class TestApiKeysCannotDecide:
    """A PERSON decides every day; a personal API key is not a person."""

    def test_an_api_key_cannot_approve_or_decline(self, client, db_session, test_user):
        from app.services import api_keys

        _row, key = api_keys.create(db_session, test_user.id, "zap")
        headers = {"Authorization": f"Bearer {key}"}
        r = client.post("/send-approval/approve",
                        json={"channels": ["email", "linkedin"],
                              "linkedin_risk_acknowledged": True,
                              "linkedin_warning_version": dsa.LINKEDIN_WARNING_VERSION},
                        headers=headers)
        assert r.status_code == 403
        assert client.post("/send-approval/decline", json={},
                           headers=headers).status_code == 403
        assert client.get("/send-approval/today", headers=headers).json()["can_decide"] is False
        assert db_session.query(m.DailySendApproval).count() == 0
        assert db_session.query(m.ComplianceAuditLog).count() == 0


class TestRace:
    def test_an_approval_landing_mid_hold_does_not_strand_the_message(
            self, db_session, enrolled, verified_leads, wired, fake_channel, test_user,
            monkeypatch):
        """The worker computes a hold; the owner approves (its release cannot
        see the not-yet-committed tag); the worker must then NOT park the
        message until midnight."""
        real = dsa.send_hold

        def racing(db, message, strategy, now=None):
            hold = real(db, message, strategy, now)
            dsa.approve(db, test_user.id, actor_id=test_user.id, channels=["email"], now=NOW)
            return hold

        monkeypatch.setattr(dsa, "send_hold", racing)
        message = _scheduled(db_session)[0]
        assert wired.send_message_impl(db_session, message.id, now=NOW) == "sent"
        db_session.refresh(message)
        assert message.status is m.MessageStatus.SENT
        assert len(fake_channel.sent) == 1


class TestValidUntil:
    def test_a_timezone_change_cannot_stretch_an_approval(self, db_session, enrolled,
                                                          verified_leads, test_user):
        db_session.add(m.CalendarAvailability(user_id=test_user.id, day_of_week=1,
                                              start_time=time(9), end_time=time(17),
                                              timezone="Pacific/Kiritimati"))
        db_session.commit()
        at = datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc)   # 23:00 Aug 11, UTC+14
        out = dsa.approve(db_session, test_user.id, actor_id=test_user.id,
                          channels=["email"], now=at)
        assert out["valid_until"] == datetime(2026, 8, 11, 10, 0, tzinfo=timezone.utc).isoformat()
        row = db_session.query(m.CalendarAvailability).one()
        row.timezone = "Etc/GMT+12"                              # now UTC-12: still Aug 11
        db_session.commit()
        message = _scheduled(db_session)[0]
        strategy = db_session.get(m.Strategy,
                                  db_session.get(m.Lead, message.lead_id).strategy_id)
        later = datetime(2026, 8, 12, 11, 0, tzinfo=timezone.utc)
        hold = dsa.send_hold(db_session, message, strategy, later)
        assert hold is not None and hold.result == dsa.SEND_RESULT_AWAITING
        assert dsa.state(db_session, test_user.id, later)["status"] == "pending"

    def test_the_earliest_availability_row_wins_ties_by_id(self, db_session, test_user):
        """Deterministic: created_at, then id (this ordering pre-dates the
        review; the test pins it)."""
        import uuid as uuid_mod

        same = datetime(2026, 1, 1, tzinfo=timezone.utc)
        low, high = uuid_mod.UUID(int=1), uuid_mod.UUID(int=2)
        for rid, tz in ((high, "Asia/Karachi"), (low, "Europe/Rome")):
            db_session.add(m.CalendarAvailability(id=rid, user_id=test_user.id, day_of_week=1,
                                                  start_time=time(9), end_time=time(17),
                                                  timezone=tz, created_at=same))
        db_session.commit()
        assert dsa.account_timezone(db_session, test_user.id)[0] == "Europe/Rome"


class TestConcurrentApprovals:
    def test_a_parallel_approval_for_another_channel_is_not_lost(
            self, db_session, test_user, monkeypatch):
        """Approval B (LinkedIn) commits between approval A (email) reading
        today's row and writing it. A must re-read under the lock and keep B."""
        from sqlalchemy import update as sa_update

        dsa.decline(db_session, test_user.id, actor_id=test_user.id, now=NOW)   # row exists
        real = dsa._get_or_create

        def with_parallel_approval(db, user_id, local_date, tz_name):
            row = real(db, user_id, local_date, tz_name)
            db.execute(sa_update(m.DailySendApproval)
                       .where(m.DailySendApproval.id == row.id)
                       .values(status="approved", channels_json=["linkedin"],
                               linkedin_risk_acknowledged=True,
                               linkedin_warning_version=dsa.LINKEDIN_WARNING_VERSION,
                               decided_at=NOW, valid_until=NEXT_UTC_MIDNIGHT)
                       .execution_options(synchronize_session=False))
            return row

        monkeypatch.setattr(dsa, "_get_or_create", with_parallel_approval)
        out = dsa.approve(db_session, test_user.id, actor_id=test_user.id,
                          channels=["email"], now=NOW + timedelta(seconds=1))
        assert out["approved_channels"] == ["email", "linkedin"]


class TestAcknowledgementPerDecision:
    def test_a_decline_clears_it_and_a_later_email_only_approval_does_not_claim_it(
            self, db_session, test_user):
        dsa.approve(db_session, test_user.id, actor_id=test_user.id,
                    channels=["email", "linkedin"], linkedin_risk_acknowledged=True,
                    linkedin_warning_version=dsa.LINKEDIN_WARNING_VERSION, now=NOW)
        dsa.decline(db_session, test_user.id, actor_id=test_user.id,
                    now=NOW + timedelta(minutes=1))
        out = dsa.approve(db_session, test_user.id, actor_id=test_user.id,
                          channels=["email"], now=NOW + timedelta(minutes=2))
        assert out["approved_channels"] == ["email"]
        assert out["linkedin_risk_acknowledged"] is False
        row = db_session.query(m.DailySendApproval).one()
        assert row.linkedin_risk_acknowledged is False
        assert row.linkedin_warning_version is None
        audits = (db_session.query(m.ComplianceAuditLog)
                  .filter_by(decision=dsa.AUDIT_APPROVED)
                  .order_by(m.ComplianceAuditLog.ts, m.ComplianceAuditLog.id).all())
        last = max(audits, key=lambda a: a.checks_json["decided_at"]).checks_json
        assert last["linkedin_risk_acknowledged"] is False
        assert last["linkedin_approved"] is False
        assert last["linkedin_warning_version"] is None
        assert last["linkedin_warning_text"] is None

    def test_an_email_approval_after_a_linkedin_one_does_not_reacknowledge(
            self, db_session, test_user):
        dsa.approve(db_session, test_user.id, actor_id=test_user.id, channels=["linkedin"],
                    linkedin_risk_acknowledged=True,
                    linkedin_warning_version=dsa.LINKEDIN_WARNING_VERSION, now=NOW)
        out = dsa.approve(db_session, test_user.id, actor_id=test_user.id,
                          channels=["email"], now=NOW + timedelta(minutes=1))
        assert out["approved_channels"] == ["email", "linkedin"]
        assert out["linkedin_risk_acknowledged"] is True          # still approved today
        audits = db_session.query(m.ComplianceAuditLog).filter_by(
            decision=dsa.AUDIT_APPROVED).all()
        last = max(audits, key=lambda a: a.checks_json["decided_at"]).checks_json
        assert last["linkedin_risk_acknowledged"] is False         # not THIS decision
        assert last["linkedin_acknowledged_earlier_today"] is True


class TestCountsMatchTheSendPath:
    def test_paused_campaigns_and_paused_or_stopped_enrollments_are_not_counted(
            self, db_session, enrolled, verified_leads, verified_strategy, test_user):
        assert dsa.queued_counts(db_session, test_user.id, NOW)["email"] == 3
        enrollments = (db_session.query(m.SequenceEnrollment)
                       .order_by(m.SequenceEnrollment.id).all())
        enrollments[0].status = m.EnrollmentStatus.PAUSED
        enrollments[1].status = m.EnrollmentStatus.STOPPED
        db_session.commit()
        assert dsa.queued_counts(db_session, test_user.id, NOW)["email"] == 1
        verified_strategy.campaign_state = "paused_manual"
        db_session.commit()
        assert dsa.queued_counts(db_session, test_user.id, NOW)["email"] == 0

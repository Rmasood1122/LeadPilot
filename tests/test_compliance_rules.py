"""Feature 8 — configurable compliance rules.

THE ASSERTIONS THIS FILE EXISTS FOR are the fail-closed ones: an empty rules
table is exactly the old hardcoded behaviour, and a misconfigured, unreadable
or self-contradicting rule set never silently disables a check -- it can only
ever make a send MORE restricted. Everything else (precedence, per-region and
per-channel scoping, the admin API) follows from that.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.db import models as m
from app.services import compliance_rules as rules
from app.services import crypto, workspaces
from app.services import sequence_engine as engine
from app.workers import outreach_tasks as tasks

UTC = timezone.utc
TUESDAY_10 = datetime(2026, 9, 15, 10, 0, tzinfo=UTC)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture()
def ws(db_session, test_user):
    return workspaces.personal_workspace(db_session, test_user)


@pytest.fixture()
def sequence(db_session, verified_strategy):
    seq = m.Sequence(strategy_id=verified_strategy.id, channel=m.ChannelType.EMAIL,
                     name="Outbound", status=m.SequenceStatus.ACTIVE)
    db_session.add(seq)
    db_session.flush()
    db_session.add_all([
        m.SequenceStep(sequence_id=seq.id, step_no=1, template="Open on X", delay_days=0),
        m.SequenceStep(sequence_id=seq.id, step_no=2, template="Nudge", delay_days=3),
    ])
    db_session.commit()
    return seq


def _lead(db, strategy, n, country):
    row = m.Lead(strategy_id=strategy.id, source="manual", external_id=f"cr{n}",
                 full_name=f"Lead {n}", company="Acme", email=f"cr{n}@acme.test",
                 status=m.LeadStatus.VERIFIED, enrichment_json={"country": country})
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def us_lead(db_session, verified_strategy):
    return _lead(db_session, verified_strategy, 1, "United States")


@pytest.fixture()
def eu_lead(db_session, verified_strategy):
    return _lead(db_session, verified_strategy, 2, "Germany")


@pytest.fixture()
def channel(monkeypatch):
    from app.integrations.outreach_base import SendResult

    sent: list = []

    class FakeChannel:
        def send(self, outbound):
            sent.append(outbound)
            return SendResult(ok=True, provider_message_id="p1", thread_ref="t1")

    monkeypatch.setattr(tasks, "_get_channel", lambda session, account: FakeChannel())
    return sent


@pytest.fixture()
def gmail(db_session, test_user):
    row = m.GmailAccount(
        user_id=test_user.id, email_address="me@leadpilot.dev",
        token_ciphertext=crypto.encrypt_json({"access_token": "a", "refresh_token": "r"}),
        token_expires_at=TUESDAY_10 + timedelta(days=30),
        created_at=TUESDAY_10 - timedelta(days=365),
    )
    db_session.add(row)
    db_session.commit()
    return row


def _scheduled(db, sequence, lead, channel=m.ChannelType.EMAIL):
    db.add(m.SequenceEnrollment(sequence_id=sequence.id, lead_id=lead.id,
                                status=m.EnrollmentStatus.ACTIVE, current_step=0))
    msg = m.Message(sequence_id=sequence.id, lead_id=lead.id, channel=channel, step_no=1,
                    template="Open on X", status=m.MessageStatus.SCHEDULED,
                    scheduled_at=TUESDAY_10)
    db.add(msg)
    db.commit()
    return msg


def _rule(db, *, ws=None, region="*", channel="*", **fields):
    row = m.ComplianceRule(scope=str(ws.id) if ws else rules.GLOBAL,
                           workspace_id=ws.id if ws else None,
                           region=region, channel=channel, **fields)
    db.add(row)
    db.commit()
    return row


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# --------------------------------------------------------------------------
# Fail closed -- the load-bearing tests
# --------------------------------------------------------------------------


class TestFailsClosed:
    @pytest.mark.parametrize("channel", ["email", "whatsapp", "linkedin", "phone"])
    def test_an_empty_table_is_exactly_the_old_hardcoded_behaviour(self, db_session, ws,
                                                                   channel):
        eff = rules.resolve_for(db_session, ws.id, "eu", channel)
        assert eff.window == (settings.send_window_start_hour, settings.send_window_end_hour,
                              settings.send_window_skip_weekends)
        assert eff.daily_cap == rules.baseline_cap(channel)
        assert eff.bounce_pause_threshold == settings.bounce_rate_pause_threshold
        assert eff.consent_required is False and eff.failed_closed is False

    def test_an_empty_table_still_enforces_the_send_window(self, db_session, sequence,
                                                           us_lead, gmail, channel,
                                                           fake_claude):
        msg = _scheduled(db_session, sequence, us_lead)
        early = TUESDAY_10.replace(hour=6)
        assert tasks.send_message_impl(db_session, msg.id, now=early) == "deferred_window"
        assert _aware(msg.scheduled_at) == TUESDAY_10.replace(hour=settings.send_window_start_hour)
        assert channel == []

    def test_an_unreadable_rules_table_applies_the_baseline(self, db_session, ws, monkeypatch):
        def boom(session, workspace_id):
            raise OperationalError("SELECT", {}, Exception("no such table"))

        monkeypatch.setattr(rules, "_load", boom)
        eff = rules.resolve_for(db_session, ws.id, "us", "email")
        assert eff.failed_closed is True
        assert eff.window == rules.baseline("email").window
        assert eff.daily_cap == settings.gmail_daily_cap

    def test_an_invalid_row_cannot_widen_the_window(self, db_session, ws):
        # A valid global rule widens to 07-20; a corrupt workspace row (end
        # before start, written by hand) also matches. Result: the INTERSECTION
        # with the baseline -- 09-17 -- not the valid rule's 07-20.
        _rule(db_session, send_start_hour=7, send_end_hour=20)
        _rule(db_session, ws=ws, send_start_hour=20, send_end_hour=8)
        eff = rules.resolve_for(db_session, ws.id, "us", "email")
        assert eff.failed_closed is True
        assert (eff.send_start_hour, eff.send_end_hour) == (
            settings.send_window_start_hour, settings.send_window_end_hour)

    def test_hours_outside_the_hard_band_are_invalid_and_closed(self, db_session, ws,
                                                                sequence, us_lead, gmail,
                                                                channel):
        _rule(db_session, ws=ws, send_start_hour=5, send_end_hour=23)
        msg = _scheduled(db_session, sequence, us_lead)
        assert tasks.send_message_impl(db_session, msg.id,
                                       now=TUESDAY_10.replace(hour=6)) == "deferred_window"
        assert channel == []

    def test_a_cap_above_the_deployment_cap_is_invalid_not_a_raise(self, db_session, ws):
        _rule(db_session, ws=ws, channel="email", daily_cap=settings.gmail_daily_cap * 10)
        eff = rules.resolve_for(db_session, ws.id, "us", "email")
        assert eff.failed_closed is True
        assert eff.daily_cap == settings.gmail_daily_cap

    def test_an_invalid_row_keeps_every_stricter_valid_setting(self, db_session, ws):
        _rule(db_session, ws=ws, channel="email", consent_required=True, daily_cap=5)
        _rule(db_session, region="us", bounce_pause_threshold=5.0)   # invalid
        eff = rules.resolve_for(db_session, ws.id, "us", "email")
        assert eff.failed_closed is True
        assert eff.consent_required is True and eff.daily_cap == 5

    def test_rules_that_leave_no_hours_send_nothing(self, db_session, ws, sequence, us_lead,
                                                    gmail, channel):
        _rule(db_session, ws=ws, send_start_hour=18)          # baseline end is 17
        msg = _scheduled(db_session, sequence, us_lead)
        assert tasks.send_message_impl(db_session, msg.id, now=TUESDAY_10) == \
            "deferred_no_send_window"
        assert msg.status is m.MessageStatus.SCHEDULED and channel == []

    def test_a_valid_rule_can_never_raise_the_bounce_threshold(self, db_session, ws):
        row = _rule(db_session, ws=ws, daily_cap=None, bounce_pause_threshold=0.02)
        row.bounce_pause_threshold = settings.bounce_rate_pause_threshold * 2  # by hand
        db_session.commit()
        assert rules.resolve_for(db_session, ws.id, "*", "*").bounce_pause_threshold \
            <= settings.bounce_rate_pause_threshold


# --------------------------------------------------------------------------
# Precedence and scoping
# --------------------------------------------------------------------------


class TestResolution:
    def test_workspace_beats_global_and_region_beats_any(self, db_session, ws):
        _rule(db_session, send_start_hour=8)
        _rule(db_session, ws=ws, send_start_hour=10)
        _rule(db_session, ws=ws, region="eu", send_start_hour=11)
        assert rules.resolve_for(db_session, ws.id, "us", "email").send_start_hour == 10
        assert rules.resolve_for(db_session, ws.id, "eu", "email").send_start_hour == 11
        assert rules.resolve_for(db_session, None, "eu", "email").send_start_hour == 8

    def test_another_workspaces_rules_do_not_apply(self, db_session, ws):
        other_owner = m.User(email="other@rules.test", email_verified=True)
        db_session.add(other_owner)
        db_session.commit()
        other = workspaces.personal_workspace(db_session, other_owner)
        _rule(db_session, ws=other, consent_required=True)
        assert rules.resolve_for(db_session, ws.id, "us", "email").consent_required is False

    def test_fields_inherit_independently(self, db_session, ws):
        _rule(db_session, send_end_hour=16)
        _rule(db_session, ws=ws, channel="email", daily_cap=20)
        eff = rules.resolve_for(db_session, ws.id, "us", "email")
        assert (eff.send_end_hour, eff.daily_cap) == (16, 20)


# --------------------------------------------------------------------------
# The send path
# --------------------------------------------------------------------------


class TestSendPath:
    def test_a_workspace_window_moves_the_send(self, db_session, ws, sequence, us_lead,
                                               gmail, channel):
        _rule(db_session, ws=ws, send_start_hour=11, send_end_hour=15)
        msg = _scheduled(db_session, sequence, us_lead)
        assert tasks.send_message_impl(db_session, msg.id, now=TUESDAY_10) == "deferred_window"
        assert _aware(msg.scheduled_at) == TUESDAY_10.replace(hour=11)

    def test_a_consent_rule_skips_only_the_region_it_names(self, db_session, ws, sequence,
                                                           us_lead, eu_lead, gmail, channel,
                                                           fake_claude):
        _rule(db_session, ws=ws, region="eu", channel="email", consent_required=True)
        eu_msg = _scheduled(db_session, sequence, eu_lead)
        assert tasks.send_message_impl(db_session, eu_msg.id, now=TUESDAY_10) == \
            "skipped_consent_required"
        us_msg = _scheduled(db_session, sequence, us_lead)
        assert tasks.send_message_impl(db_session, us_msg.id, now=TUESDAY_10) == "sent"
        assert len(channel) == 1

    def test_a_cap_rule_defers_and_never_drops(self, db_session, ws, sequence, us_lead, gmail,
                                               channel):
        _rule(db_session, ws=ws, channel="email", daily_cap=0)
        msg = _scheduled(db_session, sequence, us_lead)
        assert tasks.send_message_impl(db_session, msg.id, now=TUESDAY_10) == "deferred_cap"
        assert msg.status is m.MessageStatus.SCHEDULED and channel == []

    def test_a_lower_bounce_threshold_pauses_earlier(self, db_session, ws, sequence, us_lead,
                                                     eu_lead, verified_strategy, gmail):
        for _ in range(50):
            db_session.add(m.Message(sequence_id=sequence.id, lead_id=us_lead.id,
                                     channel=m.ChannelType.EMAIL, step_no=1, template="x",
                                     status=m.MessageStatus.SENT, sent_at=TUESDAY_10))
        db_session.commit()
        _rule(db_session, ws=ws, bounce_pause_threshold=0.01)
        engine.record_bounce(db_session, eu_lead)                  # 1/50 = 2%
        assert verified_strategy.campaign_state == engine.CAMPAIGN_PAUSED_BOUNCE

    def test_without_the_rule_two_percent_does_not_pause(self, db_session, sequence, us_lead,
                                                         eu_lead, verified_strategy, gmail):
        for _ in range(50):
            db_session.add(m.Message(sequence_id=sequence.id, lead_id=us_lead.id,
                                     channel=m.ChannelType.EMAIL, step_no=1, template="x",
                                     status=m.MessageStatus.SENT, sent_at=TUESDAY_10))
        db_session.commit()
        engine.record_bounce(db_session, eu_lead)
        assert verified_strategy.campaign_state == engine.CAMPAIGN_ACTIVE


# --------------------------------------------------------------------------
# Admin API
# --------------------------------------------------------------------------


class TestAdminApi:
    @pytest.fixture()
    def admin(self, db_session, test_user):
        test_user.is_admin = True
        db_session.commit()
        return test_user

    def test_non_admins_are_refused(self, client):
        assert client.get("/admin/compliance-rules").status_code == 403

    def test_upsert_list_preview_delete(self, client, admin, ws):
        body = {"workspace_id": str(ws.id), "region": "eu", "channel": "email",
                "send_start_hour": 10, "send_end_hour": 16, "consent_required": True}
        first = client.put("/admin/compliance-rules", json=body)
        assert first.status_code == 200, first.text
        again = client.put("/admin/compliance-rules", json={**body, "send_end_hour": 15})
        assert again.json()["id"] == first.json()["id"]            # upsert, not a duplicate

        listed = client.get(f"/admin/compliance-rules?workspace_id={ws.id}").json()
        assert [r["send_end_hour"] for r in listed["rules"]] == [15]
        assert listed["baseline"]["send_start_hour"] == settings.send_window_start_hour

        eff = client.get(f"/admin/compliance-rules/effective?workspace_id={ws.id}"
                         "&region=eu&channel=email").json()
        assert (eff["send_start_hour"], eff["consent_required"]) == (10, True)

        assert client.delete(f"/admin/compliance-rules/{first.json()['id']}").status_code == 204
        assert client.get(f"/admin/compliance-rules?workspace_id={ws.id}").json()["rules"] == []

    @pytest.mark.parametrize("body", [
        {"send_start_hour": 16, "send_end_hour": 10},
        {"send_start_hour": 5},
        {"send_end_hour": 22},
        {"bounce_pause_threshold": 0.5},
        {"daily_cap": -1},
        {"channel": "email", "daily_cap": 10_000_000},
        {"region": "mars", "consent_required": True},
        {"channel": "fax", "consent_required": True},
        {},
    ])
    def test_invalid_rules_are_refused(self, client, admin, body):
        assert client.put("/admin/compliance-rules", json=body).status_code == 422

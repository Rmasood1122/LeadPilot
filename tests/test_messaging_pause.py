"""Feature 4 -- reply kill switch: pause one contact, pause all messaging.

The property that matters is NEGATIVE: while a pause is in force NO adapter is
called, on ANY send path. Every enforcement test therefore asserts on the fake
channel / fake client, not just on a return string.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.services import messaging_pause as mp
from app.services import system_settings
from tests.conftest import NOW


@pytest.fixture()
def scheduled(db_session, enrolled):
    return db_session.query(m.Message).filter_by(
        status=m.MessageStatus.SCHEDULED).first()


@pytest.fixture()
def channel(fake_channel, monkeypatch):
    from app.workers import outreach_tasks

    monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
    return fake_channel


def _lead_of(db, message):
    return db.get(m.Lead, message.lead_id)


def _send(db, message):
    from app.workers import outreach_tasks

    return outreach_tasks.send_message_impl(db, message.id, now=NOW)


# --------------------------------------------------------------------------
# Service
# --------------------------------------------------------------------------


class TestBlockedReason:
    def test_nothing_paused_means_not_blocked(self, db_session, scheduled, test_user):
        lead = _lead_of(db_session, scheduled)
        assert mp.blocked_reason(db_session, lead=lead) is None
        assert mp.blocked_reason(db_session, user=test_user) is None

    def test_contact_pause(self, db_session, scheduled):
        lead = _lead_of(db_session, scheduled)
        mp.pause_contact(db_session, lead, reason="manual")
        assert mp.blocked_reason(db_session, lead=lead) == "contact_paused"

    def test_account_pause_blocks_every_lead_of_the_owner(self, db_session, scheduled,
                                                          test_user):
        mp.pause_account(db_session, test_user, reason="spam")
        assert mp.blocked_reason(db_session, lead=_lead_of(db_session, scheduled)) \
            == "account_paused"

    def test_platform_pause_wins_over_everything(self, db_session, scheduled, test_user):
        system_settings.set(db_session, "messaging_global_pause", True)
        assert mp.blocked_reason(db_session, lead=_lead_of(db_session, scheduled)) \
            == "platform_paused"
        assert mp.blocked_reason(db_session, user=test_user) == "platform_paused"

    def test_resume_clears_it(self, db_session, scheduled, test_user):
        lead = _lead_of(db_session, scheduled)
        mp.pause_contact(db_session, lead, reason="bounce")
        mp.pause_account(db_session, test_user, reason="manual")
        mp.resume_contact(db_session, lead)
        mp.resume_account(db_session, test_user)
        assert mp.blocked_reason(db_session, lead=lead) is None
        assert lead.messaging_paused_reason is None

    def test_an_unknown_reason_is_refused_not_stored(self, db_session, scheduled):
        with pytest.raises(mp.PauseError):
            mp.pause_contact(db_session, _lead_of(db_session, scheduled), reason="vibes")

    def test_pausing_twice_keeps_the_first_timestamp(self, db_session, scheduled):
        lead = _lead_of(db_session, scheduled)
        mp.pause_contact(db_session, lead, reason="manual")
        first = lead.messaging_paused_at
        mp.pause_contact(db_session, lead, reason="spam")
        assert lead.messaging_paused_at == first


# --------------------------------------------------------------------------
# Enforcement: the main send path
# --------------------------------------------------------------------------


class TestSendPath:
    def test_baseline_it_sends_when_nothing_is_paused(self, db_session, scheduled, channel):
        assert _send(db_session, scheduled) == "sent"
        assert len(channel.sent) == 1

    def test_a_paused_contact_is_not_sent_to(self, db_session, scheduled, channel):
        mp.pause_contact(db_session, _lead_of(db_session, scheduled), reason="manual")
        assert _send(db_session, scheduled) == "paused_contact"
        assert channel.sent == []

    def test_the_message_stays_scheduled_so_resume_picks_it_up(self, db_session, scheduled,
                                                                channel):
        lead = _lead_of(db_session, scheduled)
        mp.pause_contact(db_session, lead, reason="manual")
        _send(db_session, scheduled)
        db_session.refresh(scheduled)
        assert scheduled.status is m.MessageStatus.SCHEDULED
        mp.resume_contact(db_session, lead)
        assert _send(db_session, scheduled) == "sent"

    def test_a_paused_account_sends_nothing(self, db_session, scheduled, channel, test_user):
        mp.pause_account(db_session, test_user, reason="spam")
        assert _send(db_session, scheduled) == "paused_account"
        assert channel.sent == []

    def test_the_platform_switch_sends_nothing(self, db_session, scheduled, channel):
        system_settings.set(db_session, "messaging_global_pause", True)
        assert _send(db_session, scheduled) == "paused_platform"
        assert channel.sent == []

    def test_pausing_one_contact_does_not_stop_the_others(self, db_session, enrolled,
                                                          channel):
        msgs = db_session.query(m.Message).filter_by(status=m.MessageStatus.SCHEDULED).all()
        assert len(msgs) == 3
        mp.pause_contact(db_session, db_session.get(m.Lead, msgs[0].lead_id), reason="manual")
        results = [_send(db_session, x) for x in msgs]
        assert results.count("paused_contact") == 1
        assert results.count("sent") == 2
        assert len(channel.sent) == 2


# --------------------------------------------------------------------------
# Enforcement: the other send paths
# --------------------------------------------------------------------------


class TestOtherPaths:
    def test_a_meeting_followup_is_refused_and_nothing_is_sent(
            self, db_session, scheduled, test_user, monkeypatch):
        from app.integrations import gmail
        from app.services import meeting_followup as mf

        calls: list = []
        monkeypatch.setattr(gmail, "send_draft", lambda *a, **k: calls.append(a) or {})
        lead = _lead_of(db_session, scheduled)
        row = m.MeetingOutcome(lead_id=lead.id, user_id=test_user.id,
                               outcome=m.MeetingOutcomeKind.NEEDS_FOLLOW_UP,
                               draft_status="draft_saved", gmail_draft_id="d1")
        db_session.add(row)
        db_session.commit()
        mp.pause_contact(db_session, lead, reason="manual")
        with pytest.raises(mf.FollowupNotSendable):
            mf.send_followup(db_session, row, user=test_user)
        assert calls == []

    def test_an_ai_call_is_refused(self, client, db_session, scheduled, monkeypatch):
        lead = _lead_of(db_session, scheduled)
        lead.phone = "+14155550123"
        db_session.commit()
        system_settings.set(db_session, "phone_calling_enabled", True)
        mp.pause_contact(db_session, lead, reason="manual")
        r = client.post(f"/leads/{lead.id}/call", json={})
        assert r.status_code == 409
        assert "paused" in r.json()["detail"].lower()

    def test_a_network_message_is_refused_when_the_account_is_paused(
            self, db_session, test_user, monkeypatch):
        from app.services import network_messages as nm

        mp.pause_account(db_session, test_user, reason="manual")
        msg = m.LinkedInNetworkMessage(user_id=test_user.id, connection_id=uuid.uuid4(),
                                       status="approved", text="hi")
        with pytest.raises(nm.MessageError) as exc:
            nm.deliver(db_session, test_user, msg, "linkedin")
        assert exc.value.status == 409
        assert "paused" in str(exc.value).lower()


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


class TestApi:
    def test_status_defaults_to_not_paused(self, client):
        r = client.get("/messaging/status")
        assert r.status_code == 200
        body = r.json()
        assert body["account_paused"] is False
        assert body["platform_paused"] is False
        assert body["paused_contacts"] == 0

    def test_pause_and_resume_a_contact(self, client, db_session, scheduled):
        lead = _lead_of(db_session, scheduled)
        r = client.post(f"/messaging/leads/{lead.id}/pause", json={"reason": "manual"})
        assert r.status_code == 200 and r.json()["paused"] is True
        assert client.get("/messaging/status").json()["paused_contacts"] == 1
        r = client.post(f"/messaging/leads/{lead.id}/resume")
        assert r.status_code == 200 and r.json()["paused"] is False
        assert client.get("/messaging/status").json()["paused_contacts"] == 0

    def test_a_contact_pause_leaves_a_crm_timeline_row(self, client, db_session, scheduled):
        lead = _lead_of(db_session, scheduled)
        client.post(f"/messaging/leads/{lead.id}/pause", json={"reason": "spam"})
        rows = db_session.query(m.CrmActivity).filter_by(
            lead_id=lead.id, kind=m.CrmActivityKind.FIELD_CHANGED).all()
        assert rows

    def test_pause_all_and_resume_all(self, client):
        assert client.post("/messaging/pause-all", json={"reason": "manual"}).status_code == 200
        assert client.get("/messaging/status").json()["account_paused"] is True
        assert client.post("/messaging/resume-all").status_code == 200
        assert client.get("/messaging/status").json()["account_paused"] is False

    def test_bad_reason_is_422(self, client, db_session, scheduled):
        lead = _lead_of(db_session, scheduled)
        r = client.post(f"/messaging/leads/{lead.id}/pause", json={"reason": "vibes"})
        assert r.status_code == 422

    def test_another_accounts_lead_is_404_for_pause_and_resume(self, client, db_session):
        other = m.User(email="o@x.dev", email_verified=True)
        db_session.add(other)
        db_session.flush()
        product = m.Product(user_id=other.id, name="P", description="d",
                            type=m.ProductType.SKILL)
        db_session.add(product)
        db_session.flush()
        strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.WITH_CLIENTS)
        db_session.add(strategy)
        db_session.flush()
        lead = m.Lead(strategy_id=strategy.id, source="apollo", external_id="X",
                      email="x@y.com", status=m.LeadStatus.VERIFIED)
        db_session.add(lead)
        db_session.commit()
        assert client.post(f"/messaging/leads/{lead.id}/pause",
                           json={"reason": "manual"}).status_code == 404
        assert client.post(f"/messaging/leads/{lead.id}/resume").status_code == 404
        db_session.refresh(lead)
        assert lead.messaging_paused_at is None

    def test_pause_all_only_touches_my_account(self, client, db_session):
        other = m.User(email="o2@x.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        client.post("/messaging/pause-all", json={"reason": "manual"})
        db_session.refresh(other)
        assert other.messaging_paused_at is None

    def test_audit_records_counts_only(self, client, db_session, scheduled):
        lead = _lead_of(db_session, scheduled)
        client.post(f"/messaging/leads/{lead.id}/pause", json={"reason": "manual"})
        client.post("/messaging/pause-all", json={"reason": "manual"})
        events = db_session.query(m.SecurityAuditEvent).filter(
            m.SecurityAuditEvent.action.like("messaging.%")).all()
        assert len(events) == 2
        for e in events:
            blob = str(e.details_json)
            assert "@" not in blob and "lead0" not in blob

    def test_the_platform_switch_is_visible_in_status(self, client, db_session):
        system_settings.set(db_session, "messaging_global_pause", True)
        assert client.get("/messaging/status").json()["platform_paused"] is True

    def test_the_platform_switch_is_a_registered_admin_setting(self):
        assert system_settings.DEFAULTS["messaging_global_pause"][0] is False

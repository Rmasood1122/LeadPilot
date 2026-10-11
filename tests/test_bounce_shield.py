"""F01 -- Bounce Shield, the send-time SAFETY GUARD, and its API.

The properties that matter:
  * with the flag off the send path is exactly what it was (meta included),
  * with it on, an email goes only to a fresh verified-valid address, a
    catch-all one under an explicit 'allow' policy, or one a manager overrode,
  * a block keeps the message (FAILED, releasable), audits it, and does not
    stop the sequence; nothing is rendered or transmitted,
  * an override can never reach an undeliverable or suppressed address,
  * releasing a blocked message sends it back through every gate,
  * no bounce threshold moves.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import settings
from app.db import models as m
from app.services import bounce_shield, system_settings
from app.services import sequence_engine as engine
from app.services import waterfall_enrichment as wf
from app.workers.outreach_tasks import send_message_impl
from tests.conftest import NOW, auth_headers
from tests.test_waterfall_enrichment import ScriptedVerifier


@pytest.fixture()
def shield_on(db_session):
    system_settings.set(db_session, "bounce_shield_enabled", True)


def message_for(db, lead):
    return db.execute(select(m.Message).where(m.Message.lead_id == lead.id)
                      .order_by(m.Message.created_at)).scalars().first()


def verdict(db, lead, value, *, age_days=1, email=None):
    wf.store_verdict(lead, verdict=value, email=email or lead.email, provider="apollo",
                     verifier="hunter", score=90, legacy_status="deliverable",
                     checked_at=NOW - timedelta(days=age_days))
    db.commit()


def sent_meta(db, message):
    return db.execute(select(m.Outcome.meta_json).where(
        m.Outcome.message_id == message.id,
        m.Outcome.event == m.OutcomeEvent.SENT)).scalar_one()


def audit_decisions(db, lead):
    return [r.decision for r in db.execute(select(m.ComplianceAuditLog).where(
        m.ComplianceAuditLog.lead_id == lead.id)).scalars()]


def enrollment_of(db, lead):
    return db.execute(select(m.SequenceEnrollment).where(
        m.SequenceEnrollment.lead_id == lead.id)).scalar_one()


# --------------------------------------------------------------------------
# The guard in the send chokepoint
# --------------------------------------------------------------------------


class TestFlagOff:
    def test_unverified_lead_sends_exactly_as_before(self, db_session, enrolled,
                                                     verified_leads, fake_channel):
        lead = verified_leads[0]
        msg = message_for(db_session, lead)
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"
        assert len(fake_channel.sent) == 1
        assert "email_verdict" not in sent_meta(db_session, msg), "meta byte-identical"


@pytest.mark.usefixtures("shield_on")
class TestShield:
    def test_verified_valid_sends_and_is_tagged(self, db_session, enrolled, verified_leads,
                                                fake_channel):
        lead = verified_leads[0]
        verdict(db_session, lead, "valid")
        msg = message_for(db_session, lead)
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"
        assert sent_meta(db_session, msg)["email_verdict"] == "valid"

    def test_no_verdict_is_blocked_kept_audited_and_the_sequence_lives(
            self, db_session, enrolled, verified_leads, fake_channel):
        lead = verified_leads[0]
        msg = message_for(db_session, lead)
        out = send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert out == "blocked_unverified_email"
        assert fake_channel.sent == []
        assert msg.status is m.MessageStatus.FAILED
        assert msg.error.startswith(bounce_shield.ERROR_PREFIX)
        assert "no verification on record" in msg.error
        assert msg.body is None or msg.body == "", "nothing was rendered"
        assert enrollment_of(db_session, lead).status is m.EnrollmentStatus.ACTIVE
        assert "blocked_unverified_email" in audit_decisions(db_session, lead)
        assert db_session.execute(select(m.Outcome).where(
            m.Outcome.message_id == msg.id)).first() is None

    def test_an_edited_address_is_not_verified(self, db_session, enrolled, verified_leads,
                                               fake_channel):
        lead = verified_leads[0]
        verdict(db_session, lead, "valid", email="someone.else@co0.com")
        msg = message_for(db_session, lead)
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == "blocked_unverified_email"
        assert "address changed" in msg.error

    def test_a_stale_verdict_is_not_verified(self, db_session, enrolled, verified_leads,
                                             fake_channel):
        lead = verified_leads[0]
        verdict(db_session, lead, "valid", age_days=91)
        msg = message_for(db_session, lead)
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == "blocked_unverified_email"
        assert "older than 90 days" in msg.error

    @pytest.mark.parametrize("policy,expected", [
        ("block", "blocked_unverified_email"),
        ("allow", "sent"),
        ("maybe", "blocked_unverified_email"),   # garbage fails closed
    ])
    def test_catch_all_follows_the_policy(self, db_session, enrolled, verified_leads,
                                          fake_channel, policy, expected):
        system_settings.set(db_session, "bounce_shield_catch_all_policy", policy)
        lead = verified_leads[0]
        verdict(db_session, lead, "catch_all")
        msg = message_for(db_session, lead)
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == expected
        if expected == "sent":
            assert sent_meta(db_session, msg)["email_verdict"] == "catch_all"

    def test_unknown_is_blocked_until_overridden(self, db_session, enrolled, verified_leads,
                                                 fake_channel):
        lead = verified_leads[0]
        verdict(db_session, lead, "unknown")
        msg = message_for(db_session, lead)
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == "blocked_unverified_email"
        bounce_shield.set_override(db_session, lead, actor_id=None, owner_id=None,
                                   reason="spoke to them on the phone", now=NOW)
        assert bounce_shield.requeue_blocked(db_session, lead, now=NOW) == 1
        db_session.refresh(msg)
        assert msg.status is m.MessageStatus.SCHEDULED and msg.error is None
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"
        assert sent_meta(db_session, msg)["email_verdict"] == "override"

    def test_an_override_never_reaches_an_undeliverable_address(
            self, db_session, enrolled, verified_leads, fake_channel):
        lead = verified_leads[0]
        verdict(db_session, lead, "invalid")
        with pytest.raises(bounce_shield.OverrideRefused):
            bounce_shield.set_override(db_session, lead, actor_id=None, owner_id=None,
                                       reason="send it anyway")
        # Even an override written behind the service's back does not open it.
        lead.enrichment_json = {**lead.enrichment_json, bounce_shield.OVERRIDE_KEY: {
            "email_sha256": wf.email_hash(lead.email), "reason": "x"}}
        db_session.commit()
        msg = message_for(db_session, lead)
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == "blocked_unverified_email"
        assert "undeliverable" in msg.error

    def test_an_override_for_an_old_address_does_not_carry_over(
            self, db_session, enrolled, verified_leads, fake_channel):
        lead = verified_leads[0]
        bounce_shield.set_override(db_session, lead, actor_id=None, owner_id=None,
                                   reason="known contact")
        lead.email = "new.address@co0.com"
        db_session.commit()
        msg = message_for(db_session, lead)
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == "blocked_unverified_email"

    def test_suppression_still_runs_first(self, db_session, enrolled, verified_leads,
                                          fake_channel):
        lead = verified_leads[0]
        db_session.add(m.SuppressionEntry(email=lead.email, reason="unsubscribed"))
        db_session.commit()
        msg = message_for(db_session, lead)
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == "cancelled_suppressed"

    def test_non_email_channels_are_untouched(self, db_session, verified_strategy,
                                              wa_lead_no_optin, fake_channel):
        seq = m.Sequence(strategy_id=verified_strategy.id, channel=m.ChannelType.WHATSAPP,
                         name="wa", status=m.SequenceStatus.ACTIVE)
        db_session.add(seq)
        db_session.flush()
        db_session.add(m.SequenceEnrollment(sequence_id=seq.id, lead_id=wa_lead_no_optin.id,
                                            status=m.EnrollmentStatus.ACTIVE))
        msg = m.Message(sequence_id=seq.id, lead_id=wa_lead_no_optin.id,
                        channel=m.ChannelType.WHATSAPP, step_no=1, template="t",
                        whatsapp_kind=m.WhatsAppStepKind.TEMPLATE,
                        status=m.MessageStatus.SCHEDULED, scheduled_at=NOW)
        db_session.add(msg)
        db_session.commit()
        out = send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert out == "skipped_no_optin", "the WhatsApp rules decided, not the shield"


class TestThresholdsUnchanged:
    def test_pause_threshold_is_still_three_percent(self):
        assert settings.bounce_rate_pause_threshold == 0.03

    def test_auto_pause_behaves_identically_with_both_flags_on(
            self, db_session, enrolled, verified_leads, verified_strategy, gmail_account):
        system_settings.set(db_session, "bounce_shield_enabled", True)
        system_settings.set(db_session, "waterfall_enrichment_enabled", True)
        for _ in range(20):
            db_session.add(m.Message(sequence_id=enrolled.id, lead_id=verified_leads[0].id,
                                     channel=m.ChannelType.EMAIL, step_no=1, template="x",
                                     status=m.MessageStatus.SENT, sent_at=NOW,
                                     sender_ref=str(gmail_account.id)))
        db_session.commit()
        engine.record_bounce(db_session, verified_leads[1])   # 1/20 = 5% > 3%
        assert verified_strategy.campaign_state == engine.CAMPAIGN_PAUSED_BOUNCE
        assert "3.0%" in verified_strategy.campaign_pause_reason


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


@pytest.fixture()
def scripted(monkeypatch):
    v = ScriptedVerifier()
    monkeypatch.setattr("app.api.bounce_shield._get_verifier", lambda: v)
    return v


def _other_account_lead(db):
    user = m.User(email="other@tenant.dev", email_verified=True)
    db.add(user)
    db.flush()
    product = m.Product(user_id=user.id, name="Other", description="d",
                        type=m.ProductType.SKILL)
    db.add(product)
    db.flush()
    strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.WITH_CLIENTS)
    db.add(strategy)
    db.flush()
    lead = m.Lead(strategy_id=strategy.id, source="apollo", external_id="X1",
                  full_name="Not Yours", email="notyours@other.com",
                  status=m.LeadStatus.VERIFIED)
    db.add(lead)
    db.commit()
    return user, strategy, lead


def _member(db, owner, role):
    from app.services import workspaces

    ws = workspaces.personal_workspace(db, owner)
    user = m.User(email=f"{role}@shield.dev", email_verified=True)
    db.add(user)
    db.flush()
    db.add(m.WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=role))
    db.commit()
    headers = auth_headers(user)
    headers["X-Workspace-Id"] = str(ws.id)
    return headers


class TestApi:
    def test_get_verdict_shape(self, client, db_session, verified_leads):
        lead = verified_leads[0]
        verdict(db_session, lead, "valid")
        body = client.get(f"/leads/{lead.id}/email-verdict").json()
        assert body["verdict"]["verdict"] == "valid"
        assert "email_sha256" not in body["verdict"]
        assert body["send_decision"]["shield_enabled"] is False
        assert body["send_decision"]["allowed"] is True
        assert body["settings"]["catch_all_policy"] == "block"

    def test_another_accounts_lead_is_404_everywhere(self, client, db_session, scripted):
        system_settings.set(db_session, "bounce_shield_enabled", True)
        _, _, lead = _other_account_lead(db_session)
        assert client.get(f"/leads/{lead.id}/email-verdict").status_code == 404
        assert client.post(f"/leads/{lead.id}/email-override",
                           json={"reason": "known contact"}).status_code == 404
        assert client.post(f"/leads/{lead.id}/email-verdict/refresh").status_code == 404
        assert client.delete(f"/leads/{lead.id}/email-override").status_code == 404
        assert scripted.verified == []

    def test_override_releases_the_blocked_message(self, client, db_session, enrolled,
                                                   verified_leads, fake_channel):
        system_settings.set(db_session, "bounce_shield_enabled", True)
        lead = verified_leads[0]
        msg = message_for(db_session, lead)
        send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert msg.status is m.MessageStatus.FAILED

        r = client.post(f"/leads/{lead.id}/email-override",
                        json={"reason": "Met at the trade show"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["released_messages"] == 1
        assert body["override"]["reason"] == "Met at the trade show"
        assert body["send_decision"]["allowed"] is True
        assert "bounce_shield_override" in audit_decisions(db_session, lead)
        db_session.refresh(msg)
        assert msg.status is m.MessageStatus.SCHEDULED

        r = client.delete(f"/leads/{lead.id}/email-override")
        assert r.status_code == 200 and r.json()["removed"] is True
        assert "bounce_shield_override_revoked" in audit_decisions(db_session, lead)

    @pytest.mark.parametrize("case", ["off", "invalid", "suppressed", "short"])
    def test_override_refusals(self, client, db_session, verified_leads, case):
        lead = verified_leads[0]
        if case != "off":
            system_settings.set(db_session, "bounce_shield_enabled", True)
        if case == "invalid":
            verdict(db_session, lead, "invalid")
        if case == "suppressed":
            db_session.add(m.SuppressionEntry(email=lead.email, reason="unsubscribed"))
            db_session.commit()
        reason = "ok" if case == "short" else "a real reason"
        r = client.post(f"/leads/{lead.id}/email-override", json={"reason": reason})
        assert r.status_code == (422 if case == "short" else 409), r.text
        db_session.refresh(lead)
        assert bounce_shield.OVERRIDE_KEY not in (lead.enrichment_json or {})

    def test_sdrs_cannot_override(self, client, db_session, test_user, verified_leads):
        system_settings.set(db_session, "bounce_shield_enabled", True)
        lead = verified_leads[0]
        headers = _member(db_session, test_user, "sdr")
        r = client.post(f"/leads/{lead.id}/email-override",
                        json={"reason": "known contact"}, headers=headers)
        assert r.status_code == 403
        assert client.delete(f"/leads/{lead.id}/email-override",
                             headers=headers).status_code == 403
        manager = _member(db_session, test_user, "manager")
        assert client.post(f"/leads/{lead.id}/email-override",
                           json={"reason": "known contact"},
                           headers=manager).status_code == 200

    def test_refresh_reverifies_ledgers_and_releases(self, client, db_session, enrolled,
                                                     verified_leads, fake_channel, scripted):
        system_settings.set(db_session, "bounce_shield_enabled", True)
        lead = verified_leads[0]
        msg = message_for(db_session, lead)
        send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert msg.status is m.MessageStatus.FAILED

        r = client.post(f"/leads/{lead.id}/email-verdict/refresh")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["verdict"]["verdict"] == "valid"
        assert body["released_messages"] == 1
        assert scripted.verified == [lead.email]
        assert [(a["step"], a["outcome"], a["cost_units"]) for a in body["attempts"]] == [
            ("reverify", "valid", 1)]
        db_session.refresh(lead)
        assert lead.status is m.LeadStatus.VERIFIED, "status is never changed by a refresh"

    def test_refresh_finding_undeliverable_removes_the_override(
            self, client, db_session, verified_leads, scripted):
        system_settings.set(db_session, "bounce_shield_enabled", True)
        lead = verified_leads[0]
        assert client.post(f"/leads/{lead.id}/email-override",
                           json={"reason": "known contact"}).status_code == 200
        scripted.verdicts[lead.email] = wf.EmailVerificationStatus.UNDELIVERABLE
        body = client.post(f"/leads/{lead.id}/email-verdict/refresh").json()
        assert body["verdict"]["verdict"] == "invalid"
        assert body["override"] is None
        assert body["send_decision"]["would_allow"] is False

    def test_refresh_needs_a_flag(self, client, verified_leads, scripted):
        r = client.post(f"/leads/{verified_leads[0].id}/email-verdict/refresh")
        assert r.status_code == 409
        assert scripted.verified == []


class TestMetrics:
    def _send(self, db, sequence, lead, tag, bounced=False):
        msg = m.Message(sequence_id=sequence.id, lead_id=lead.id, channel=m.ChannelType.EMAIL,
                        step_no=1, template="x", status=m.MessageStatus.SENT, sent_at=NOW)
        db.add(msg)
        db.flush()
        meta = {"step_no": 1, "variant": None}
        if tag:
            meta["email_verdict"] = tag
        db.add(m.Outcome(lead_id=lead.id, message_id=msg.id, event=m.OutcomeEvent.SENT,
                         channel="email", meta_json=meta))
        if bounced:
            db.add(m.Outcome(lead_id=lead.id, message_id=msg.id,
                             event=m.OutcomeEvent.BOUNCED, channel="email"))
        db.commit()

    def test_rate_on_verified_sends_split_by_tag_and_owner_scoped(
            self, client, db_session, email_sequence, verified_leads, scripted):
        lead = verified_leads[0]
        for i in range(50):
            self._send(db_session, email_sequence, lead, "valid", bounced=(i == 0))
        self._send(db_session, email_sequence, lead, "override", bounced=True)
        self._send(db_session, email_sequence, lead, None)
        # Another account's bounces must not leak into this account's number.
        _, other_strategy, other_lead = _other_account_lead(db_session)
        other_seq = m.Sequence(strategy_id=other_strategy.id, channel=m.ChannelType.EMAIL,
                               name="o", status=m.SequenceStatus.ACTIVE)
        db_session.add(other_seq)
        db_session.commit()
        for _ in range(5):
            self._send(db_session, other_seq, other_lead, "valid", bounced=True)

        # The endpoint's window is relative to the real clock (NOW-dated sends
        # may fall outside it), so the numbers are asserted through the
        # service with an explicit `now`, and the endpoint for shape + 200.
        r = client.get("/bounce-shield/metrics", params={"days": 30})
        assert r.status_code == 200, r.text
        body = r.json()
        owner = db_session.get(m.Product, db_session.get(m.Strategy, lead.strategy_id)
                               .product_id).user_id
        svc = bounce_shield.metrics(db_session, owner, days=30, now=NOW + timedelta(days=1))
        assert svc["sends"]["valid"] == {"sent": 50, "bounced": 1, "rate": 0.02}
        assert svc["sends"]["override"] == {"sent": 1, "bounced": 1, "rate": 1.0}
        assert svc["sends"]["untagged"]["sent"] == 1
        assert svc["verified_send_bounce_rate"] == 0.02
        assert svc["verified_sends"] == 50 and svc["sample_ok"] is False
        assert svc["target_verified_bounce_rate"] == 0.02
        assert svc["campaign_pause_threshold"] == 0.03
        assert set(body) >= {"sends", "ledger", "providers", "settings"}

    def test_window_excludes_old_sends(self, db_session, email_sequence, verified_leads):
        lead = verified_leads[0]
        self._send(db_session, email_sequence, lead, "valid", bounced=True)
        owner = db_session.get(m.Product, db_session.get(m.Strategy, lead.strategy_id)
                               .product_id).user_id
        svc = bounce_shield.metrics(db_session, owner, days=7, now=NOW + timedelta(days=30))
        assert svc["verified_sends"] == 0 and svc["verified_send_bounce_rate"] is None


# --------------------------------------------------------------------------
# A held message is still the message for its step (review fix)
# --------------------------------------------------------------------------


def _msgs(db, lead):
    return db.execute(select(m.Message).where(m.Message.lead_id == lead.id)
                      .order_by(m.Message.step_no, m.Message.created_at)).scalars().all()


def _step2_after_step1_sent(db, lead, fake_channel):
    first = message_for(db, lead)
    assert send_message_impl(db, first.id, channel=fake_channel, now=NOW) == "sent"
    return [x for x in _msgs(db, lead) if x.step_no == 2][0]


def _held_copy(db, lead, sequence, step_no):
    msg = m.Message(sequence_id=sequence.id, lead_id=lead.id, channel=m.ChannelType.EMAIL,
                    step_no=step_no, template="t", status=m.MessageStatus.FAILED,
                    error=f"{bounce_shield.ERROR_PREFIX}held", scheduled_at=NOW)
    db.add(msg)
    db.commit()
    return msg


class TestHoldsAreNotDuplicated:
    def test_the_prefix_is_in_the_shared_hold_list(self):
        from app.services import send_holds

        assert bounce_shield.ERROR_PREFIX in send_holds.HOLD_PREFIXES

    def test_a_shield_hold_is_pending_for_the_followup_sweep(
            self, db_session, enrolled, verified_leads, fake_channel):
        from app.workers import outreach_tasks as ot

        lead = verified_leads[0]
        step2 = _step2_after_step1_sent(db_session, lead, fake_channel)
        system_settings.set(db_session, "bounce_shield_enabled", True)
        later = NOW + timedelta(days=3)
        step2.scheduled_at = later
        db_session.commit()
        assert send_message_impl(db_session, step2.id, channel=fake_channel,
                                 now=later) == bounce_shield.SEND_RESULT
        enrollment = enrollment_of(db_session, lead)
        much_later = NOW + timedelta(days=10)
        due = ot.check_followup_due_impl(db_session, now=much_later, enqueue=lambda *a: None)
        assert str(enrollment.id) not in {eid for eid, _ in due}
        assert ot.send_followup_impl(db_session, enrollment.id, 2,
                                     now=much_later) == "skipped_already_pending"

    def test_release_puts_back_one_message_per_step_and_cancels_copies(
            self, db_session, enrolled, verified_leads):
        lead = verified_leads[0]
        first = message_for(db_session, lead)
        first.status = m.MessageStatus.FAILED
        first.error = f"{bounce_shield.ERROR_PREFIX}held"
        db_session.commit()
        copies = [_held_copy(db_session, lead, enrolled, 2) for _ in range(3)]
        assert bounce_shield.requeue_blocked(db_session, lead, NOW) == 2
        for msg in copies + [first]:
            db_session.refresh(msg)
        statuses = [c.status for c in copies]
        assert statuses.count(m.MessageStatus.SCHEDULED) == 1
        assert statuses.count(m.MessageStatus.CANCELLED) == 2
        assert first.status is m.MessageStatus.SCHEDULED

    def test_a_held_copy_of_a_step_that_already_went_out_is_cancelled(
            self, db_session, enrolled, verified_leads, fake_channel):
        lead = verified_leads[0]
        first = message_for(db_session, lead)
        assert send_message_impl(db_session, first.id, channel=fake_channel, now=NOW) == "sent"
        copy = _held_copy(db_session, lead, enrolled, 1)
        assert bounce_shield.requeue_blocked(db_session, lead, NOW) == 0
        db_session.refresh(copy)
        assert copy.status is m.MessageStatus.CANCELLED

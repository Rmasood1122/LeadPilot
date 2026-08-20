"""
M7 — every notify_* helper is wired to a real event, reaches only the owner,
and can never break the operation that triggered it.

These six helpers existed with ZERO callers: a user was never told their
strategy was ready, a lead had replied, a meeting was booked or a campaign had
auto-paused. Each test below drives the genuine production path (the pipeline,
the reply router, the Calendly webhook, the bounce-rate check, Meta's template
status) rather than calling notify_* directly, so deleting a call site fails a
test.

FCM is captured at the SDK boundary — see tests/integration/mocks/
firebase_mock.py for why respx cannot see firebase_admin's traffic.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient

from tests.integration.conftest import (
    _auth_headers,
    create_past_clients,
    create_product,
    create_strategy,
    register_device_token,
)
from tests.integration.mocks import firebase_mock

pytestmark = pytest.mark.asyncio


async def _owned_strategy(api_client, headers):
    product = await create_product(api_client, headers)
    await create_past_clients(api_client, headers, product["id"])
    return await create_strategy(api_client, headers, product["id"])


# ===========================================================================
# Strategy lifecycle
# ===========================================================================


class TestStrategyNotifications:
    async def test_pipeline_completion_notifies_owner_only(
        self, api_client: AsyncClient, user_a_tokens, user_b_tokens, all_mocks,
        db_session, capture_push_notifications
    ):
        """A verified strategy pushes 'ready' to its owner and nobody else."""
        headers = _auth_headers(user_a_tokens)
        owner_token = register_device_token(db_session, user_a_tokens, "owner")
        stranger_token = register_device_token(db_session, user_b_tokens, "stranger")

        firebase_mock.reset_capture()
        strategy = await _owned_strategy(api_client, headers)

        ready = [n for n in firebase_mock.get_all_notifications()
                 if n.title == "Your strategy is ready"]
        assert len(ready) == 1, f"expected one 'ready' push, got {ready}"
        assert ready[0].token == owner_token
        assert ready[0].deep_link == f"clienthunter:///strategies/{strategy['id']}"
        assert firebase_mock.notifications_for_tokens([stranger_token]) == []

    async def test_exhausted_verification_notifies_needs_review(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session,
        capture_push_notifications
    ):
        """When a pass exhausts its retries the owner is told to review it."""
        from app.db.models import StrategyStatus

        headers = _auth_headers(user_a_tokens)
        owner_token = register_device_token(db_session, user_a_tokens, "owner")

        firebase_mock.reset_capture()
        # Every judge verdict fails, so no pass can ever be satisfied and the
        # loop must land on NEEDS_HUMAN_REVIEW.
        with patch("app.verification.loop._judge",
                   return_value=(False, "criterion not satisfied")):
            strategy = await _owned_strategy(api_client, headers)

        from tests.integration.conftest import strategy_row

        assert strategy_row(db_session, strategy["id"]).status is (
            StrategyStatus.NEEDS_HUMAN_REVIEW
        )

        pushes = [n for n in firebase_mock.get_all_notifications()
                  if n.title == "Strategy needs review"]
        assert len(pushes) == 1, f"expected one 'needs review' push, got {pushes}"
        assert pushes[0].token == owner_token
        assert pushes[0].deep_link == f"clienthunter:///strategies/{strategy['id']}"
        assert not [n for n in firebase_mock.get_all_notifications()
                    if n.title == "Your strategy is ready"]


# ===========================================================================
# Inbound replies
# ===========================================================================


class TestReplyNotifications:
    async def test_email_reply_notifies_lead_owner_only(
        self, api_client: AsyncClient, user_a_tokens, user_b_tokens, all_mocks,
        db_session, capture_push_notifications
    ):
        headers = _auth_headers(user_a_tokens)
        owner_token = register_device_token(db_session, user_a_tokens, "owner")
        stranger_token = register_device_token(db_session, user_b_tokens, "stranger")

        strategy = await _owned_strategy(api_client, headers)
        await api_client.post(
            f"/strategies/{strategy['id']}/leads/source", headers=headers, json={})
        resp = await api_client.get(
            f"/strategies/{strategy['id']}/leads", headers=headers)
        lead = resp.json()["items"][0]

        firebase_mock.reset_capture()
        resp = await api_client.post(
            "/debug/inbound-reply", headers=headers,
            json={"lead_id": lead["id"], "body": "Yes, this looks interesting"},
        )
        assert resp.status_code == 200, resp.text

        sent = firebase_mock.get_all_notifications()
        assert len(sent) == 1, f"expected one reply push, got {sent}"
        assert sent[0].token == owner_token
        assert sent[0].title.startswith("New reply from")
        assert sent[0].deep_link == f"clienthunter:///leads/{lead['id']}"
        assert firebase_mock.notifications_for_tokens([stranger_token]) == []

    async def test_whatsapp_reply_notifies_lead_owner(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session,
        capture_push_notifications
    ):
        """The WhatsApp router shares _notify_new_reply with the email one."""
        from app.db.models import InboundReply, Lead, LeadStatus
        from app.workers.outreach_tasks import route_whatsapp_inbound_impl

        headers = _auth_headers(user_a_tokens)
        owner_token = register_device_token(db_session, user_a_tokens, "owner")
        strategy = await _owned_strategy(api_client, headers)

        lead = Lead(strategy_id=strategy["id"], source="test",
                    phone="+14155550999", email="wa-reply@prospect.io",
                    company="ProspectCo", status=LeadStatus.CONTACTED)
        db_session.add(lead)
        db_session.commit()

        reply = InboundReply(lead_id=lead.id, channel="whatsapp",
                             from_address="+14155550999",
                             body="Sounds good, tell me more")
        db_session.add(reply)
        db_session.commit()

        firebase_mock.reset_capture()
        route_whatsapp_inbound_impl(db_session, lead, reply)

        sent = firebase_mock.get_all_notifications()
        assert len(sent) == 1, f"expected one reply push, got {sent}"
        assert sent[0].token == owner_token
        assert sent[0].deep_link == f"clienthunter:///leads/{lead.id}"


# ===========================================================================
# Campaign auto-pause
# ===========================================================================


class TestCampaignPausedNotification:
    async def test_bounce_rate_pause_notifies_owner(
        self, api_client: AsyncClient, user_a_tokens, user_b_tokens, all_mocks,
        db_session, capture_push_notifications
    ):
        """An auto-paused campaign sends nothing until a human resumes it, so
        the owner has to be told."""
        headers = _auth_headers(user_a_tokens)
        owner_token = register_device_token(db_session, user_a_tokens, "owner")
        stranger_token = register_device_token(db_session, user_b_tokens, "stranger")

        strategy = await _owned_strategy(api_client, headers)

        firebase_mock.reset_capture()
        # Drives the real sequence_engine.check_bounce_rate().
        resp = await api_client.post(
            "/debug/simulate-bounce-rate", headers=headers,
            json={"strategy_id": strategy["id"], "bounce_rate": 0.31},
        )
        assert resp.status_code in (200, 202), resp.text

        from tests.integration.conftest import strategy_row

        assert strategy_row(db_session, strategy["id"]).campaign_state == (
            "paused_bounce_rate"
        )

        sent = [n for n in firebase_mock.get_all_notifications()
                if n.title == "Campaign paused — action needed"]
        assert len(sent) == 1, f"expected one pause push, got {sent}"
        assert sent[0].token == owner_token
        assert firebase_mock.notifications_for_tokens([stranger_token]) == []


# ===========================================================================
# WhatsApp template status (deployment-wide → admins)
# ===========================================================================


class TestTemplateStatusNotification:
    async def test_meta_approval_notifies_admins_not_users(
        self, api_client: AsyncClient, admin_tokens, user_a_tokens, all_mocks,
        db_session, capture_push_notifications
    ):
        """whatsapp_templates has no owner column - templates are a
        deployment-wide resource, so the recipients are admins."""
        from app.db.models import (
            WhatsAppTemplate,
            WhatsAppTemplateCategory,
            WhatsAppTemplateStatus,
        )
        from app.services import whatsapp_templates as tmpl_svc

        admin_token = register_device_token(db_session, admin_tokens, "admin")
        user_token = register_device_token(db_session, user_a_tokens, "user")

        template = WhatsAppTemplate(
            name="intro_offer", language="en_US", version=1,
            category=WhatsAppTemplateCategory.MARKETING,
            status=WhatsAppTemplateStatus.SUBMITTED,
            body="Hi {{1}}, quick question about {{2}}.",
        )
        db_session.add(template)
        db_session.commit()

        firebase_mock.reset_capture()
        tmpl_svc.apply_meta_status(db_session, template, meta_status="APPROVED")

        sent = firebase_mock.get_all_notifications()
        assert len(sent) == 1, f"expected one admin push, got {sent}"
        assert sent[0].token == admin_token
        assert sent[0].title == "WhatsApp template approved"
        assert firebase_mock.notifications_for_tokens([user_token]) == [], (
            "a shared template's status must not be pushed to every user"
        )

    async def test_pending_status_sends_nothing(
        self, api_client: AsyncClient, admin_tokens, all_mocks, db_session,
        capture_push_notifications
    ):
        """Only terminal Meta decisions notify; PENDING is noise."""
        from app.db.models import (
            WhatsAppTemplate,
            WhatsAppTemplateCategory,
            WhatsAppTemplateStatus,
        )
        from app.services import whatsapp_templates as tmpl_svc

        register_device_token(db_session, admin_tokens, "admin")
        template = WhatsAppTemplate(
            name="pending_tmpl", language="en_US", version=1,
            category=WhatsAppTemplateCategory.MARKETING,
            status=WhatsAppTemplateStatus.SUBMITTED, body="Hi {{1}}.",
        )
        db_session.add(template)
        db_session.commit()

        firebase_mock.reset_capture()
        tmpl_svc.apply_meta_status(db_session, template, meta_status="PENDING")
        assert firebase_mock.get_all_notifications() == []


# ===========================================================================
# A push failure must never break the operation that triggered it
# ===========================================================================


class TestNotificationFailureIsolation:
    async def test_fcm_failure_does_not_break_the_booking(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session,
        capture_push_notifications
    ):
        """FCM raising must not stop the meeting from being recorded."""
        import uuid as _uuid

        from firebase_admin import messaging

        from app.db.models import Lead, LeadStatus
        from tests.integration.conftest import lead_outcome_events
        from tests.integration.mocks import calendly_mock

        headers = _auth_headers(user_a_tokens)
        register_device_token(db_session, user_a_tokens, "owner")
        strategy = await _owned_strategy(api_client, headers)

        lead = Lead(strategy_id=strategy["id"], source="test",
                    email=f"boom_{_uuid.uuid4().hex[:8]}@prospect.io",
                    status=LeadStatus.VERIFIED)
        db_session.add(lead)
        db_session.commit()

        payload = calendly_mock.build_booking_webhook(
            invitee_email=lead.email, lead_id=str(lead.id),
            tenant_id=user_a_tokens["user"]["id"])

        with patch.object(messaging, "send",
                          side_effect=RuntimeError("FCM is down")):
            resp = await api_client.post(
                "/webhooks/calendly", **calendly_mock.signed_request(payload))

        assert resp.status_code == 200, resp.text

        db_session.expire_all()
        assert db_session.get(Lead, lead.id).status is LeadStatus.MEETING_BOOKED, (
            "the booking must be recorded even when the push fails"
        )
        assert "booked" in lead_outcome_events(db_session, lead.id)

    async def test_configuration_error_does_not_break_the_booking(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session,
        capture_push_notifications
    ):
        """An unconfigured deployment (no FIREBASE_CREDENTIALS_PATH) must also
        not take the booking down — send_to_device deliberately RAISES on
        configuration errors rather than swallowing them."""
        import uuid as _uuid

        from app.db.models import Lead, LeadStatus
        from app.services import notifications as notif
        from tests.integration.mocks import calendly_mock

        headers = _auth_headers(user_a_tokens)
        register_device_token(db_session, user_a_tokens, "owner")
        strategy = await _owned_strategy(api_client, headers)

        lead = Lead(strategy_id=strategy["id"], source="test",
                    email=f"noconf_{_uuid.uuid4().hex[:8]}@prospect.io",
                    status=LeadStatus.VERIFIED)
        db_session.add(lead)
        db_session.commit()

        payload = calendly_mock.build_booking_webhook(
            invitee_email=lead.email, lead_id=str(lead.id),
            tenant_id=user_a_tokens["user"]["id"])

        with patch.object(
            notif, "_get_firebase_app",
            side_effect=RuntimeError("FIREBASE_CREDENTIALS_PATH is not set"),
        ):
            resp = await api_client.post(
                "/webhooks/calendly", **calendly_mock.signed_request(payload))

        assert resp.status_code == 200, resp.text

        db_session.expire_all()
        assert db_session.get(Lead, lead.id).status is LeadStatus.MEETING_BOOKED


# ===========================================================================
# pattern_key backfill (scripts/backfill_pattern_key.py)
# ===========================================================================


class TestPatternKeyBackfill:
    """The derivation changed (ICP-only → ICP+tactics), so every stored value
    is stale. This proves the backfill recomputes them and reports orphans."""

    async def test_backfill_recomputes_stale_keys_and_reports_orphans(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session,
        capture_push_notifications
    ):
        from app.db.models import PlaybookScore, Strategy
        from scripts.backfill_pattern_key import backfill

        headers = _auth_headers(user_a_tokens)
        strategy = await _owned_strategy(api_client, headers)

        db_session.expire_all()
        row = db_session.get(Strategy, strategy["id"])
        current_key = row.pattern_key
        assert current_key, "the pipeline must set pattern_key"

        # Simulate a row written by the OLD ICP-only derivation, plus the
        # playbook_scores row that was keyed on it.
        stale_key = "stale" + "0" * 59
        row.pattern_key = stale_key
        db_session.add(PlaybookScore(pattern_key=stale_key, variant="A",
                                     score=0.1, sample_size=10))
        db_session.commit()

        dry = backfill(db_session, apply=False)
        assert dry["changed"] == 1, dry
        assert dry["applied"] is False
        db_session.expire_all()
        assert db_session.get(Strategy, strategy["id"]).pattern_key == stale_key, (
            "a dry run must not write"
        )

        applied = backfill(db_session, apply=True)
        assert applied["changed"] == 1, applied
        db_session.expire_all()
        assert db_session.get(Strategy, strategy["id"]).pattern_key == current_key, (
            "backfill must reproduce the same key the pipeline computes"
        )

        # The old score row is now an orphan and is reported, not silently kept.
        assert applied["orphaned_scores"] == 1, applied
        assert applied["deleted_scores"] == 0, "orphans need an explicit flag"

        purged = backfill(db_session, apply=True, delete_orphans=True)
        assert purged["changed"] == 0, "re-running must be a no-op"
        assert purged["deleted_scores"] == 1, purged
        assert db_session.query(PlaybookScore).filter(
            PlaybookScore.pattern_key == stale_key).count() == 0

    async def test_pattern_inputs_round_trip(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session,
        capture_push_notifications
    ):
        """persist -> reload -> recompute -> matches the stored pattern_key.

        Migration 0014 stores the exact canonical dict that was hashed. If the
        stored payload ever stopped reproducing the stored hash, every audit
        and every offline backfill would be lying.
        """
        from app.db.models import Strategy
        from app.services.icp_extraction import (
            canonical_pattern_payload,
            pattern_key_of,
        )

        headers = _auth_headers(user_a_tokens)
        strategy = await _owned_strategy(api_client, headers)

        # reload from the database, not from the in-memory object
        db_session.expire_all()
        row = db_session.get(Strategy, strategy["id"])

        assert row.pattern_key, "the pipeline must set pattern_key"
        assert row.pattern_inputs_json, (
            "the pipeline must persist the payload it hashed (migration 0014)"
        )

        # 1. the stored payload rehashes to the stored key
        assert pattern_key_of(row.pattern_inputs_json) == row.pattern_key

        # 2. the stored payload is already canonical - re-canonicalizing it is
        #    a no-op, so an audit can trust it as the literal hash input
        icp = row.pattern_inputs_json["icp"]
        tactics = row.pattern_inputs_json["tactics"]
        assert canonical_pattern_payload(icp, tactics) == row.pattern_inputs_json

        # 3. it carries both documented halves
        assert set(row.pattern_inputs_json) == {"icp", "tactics"}

        # 4. and the backfill therefore needs no model call at all
        from scripts.backfill_pattern_key import backfill

        summary = backfill(db_session, apply=True)
        assert summary["rehashed"] >= 1, summary
        assert summary["rederived"] == 0, (
            "a strategy with a stored payload must never be re-derived"
        )
        assert summary["changed"] == 0, summary

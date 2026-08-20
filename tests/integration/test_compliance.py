"""
1B — Compliance regression tests.

Each test actively attempts to BREAK a compliance rule and asserts refusal.
These must never be removed or weakened — they are the compliance guarantee.

Rules tested:
  1.  Email without unsubscribe header → ComplianceError; not written to DB
  2.  Send to suppressed email → blocked even if scheduled before suppression
  3.  WhatsApp free-form to CLOSED window → ComplianceError; Meta API not called
  4.  WhatsApp template with status != approved → ComplianceError
  5.  WhatsApp cold send without opt-in → ComplianceError
  6.  STOP inbound WhatsApp → suppression + opt-out audit + sequence stop (one transaction)
  7.  "stop emailing me" reply → classified unsubscribe_request → suppression + stop
  8.  Bounce rate > 3% → campaign auto-paused, no further sends
  9.  GDPR delete → personal data wiped; tombstone present; lead not re-sourced
  10. Sending cap exceeded → sends deferred, not dropped, not sent above cap
  11. Strategy with any FAIL verification pass → cannot progress to lead sourcing (422)
"""
from __future__ import annotations

import json
import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.integration.conftest import (
    _auth_headers,
    create_past_clients,
    create_product,
    create_strategy,
    enrollment_statuses,
)
from tests.integration.mocks import gmail_mock, whatsapp_mock

pytestmark = pytest.mark.asyncio


class TestEmailComplianceRules:
    async def test_email_without_unsubscribe_raises_compliance_error(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """
        Attempting to send an email without a valid unsubscribe header/footer
        must raise a ComplianceError (HTTP 422 with compliance_code in response).
        The Gmail send mock must NOT be called.
        """
        headers = _auth_headers(user_a_tokens)
        gmail_mock.reset_capture()

        resp = await api_client.post(
            "/debug/send-email-raw",
            headers=headers,
            json={
                "to": "test@example.com",
                "subject": "Test",
                "body": "Hello, check out our product.",
                # Deliberately omit unsubscribe_link / List-Unsubscribe header
                "include_unsubscribe": False,
            },
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body.get("compliance_code") == "MISSING_UNSUBSCRIBE" or "unsubscribe" in str(body).lower()

        # Gmail must NOT have been called
        assert len(gmail_mock.get_capture().send_calls) == 0, (
            "Gmail send was called despite missing unsubscribe — compliance violation"
        )

    async def test_send_to_suppressed_email_is_blocked(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """
        If an email is added to the suppression list AFTER it was scheduled,
        the send task must check suppression at send time and block the send.
        """
        headers = _auth_headers(user_a_tokens)
        email = "suppress_test@example.com"

        # Schedule a send
        resp = await api_client.post("/debug/schedule-send", headers=headers, json={
            "to": email,
            "subject": "Test",
            "body": "Test body with unsubscribe link",
            "include_unsubscribe": True,
            "delay_seconds": 60,  # won't actually delay in eager mode
        })
        assert resp.status_code in (200, 201)

        # Add to suppression BEFORE the send runs
        await api_client.post("/suppression", headers=headers, json={
            "email": email,
            "reason": "test suppression",
        })

        gmail_mock.reset_capture()

        # Trigger the send (in eager mode, this runs synchronously)
        resp = await api_client.post("/debug/flush-scheduled-sends", headers=headers)
        assert resp.status_code in (200, 202)

        # Send must have been blocked
        assert len(gmail_mock.get_capture().send_calls) == 0, (
            "Gmail send was called for a suppressed email"
        )

    async def test_bounce_rate_above_3pct_pauses_campaign(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """
        When bounce rate exceeds 3%, the campaign must auto-pause (status = paused_bounce_rate)
        and no further sends may go out for that campaign.
        """
        headers = _auth_headers(user_a_tokens)
        product = await create_product(api_client, headers)
        await create_past_clients(api_client, headers, product["id"])
        strategy = await create_strategy(api_client, headers, product["id"])
        strategy_id = strategy["id"]
        await api_client.post(f"/strategies/{strategy_id}/leads/source", headers=headers, json={})

        # Simulate high bounce rate (>3.01%)
        resp = await api_client.post(
            f"/debug/simulate-bounce-rate",
            headers=headers,
            json={"strategy_id": strategy_id, "bounce_rate": 0.031},
        )
        assert resp.status_code in (200, 202)

        # Campaign must now be paused. The route is /campaign (singular) and
        # returns one overview object -- pause state lives in campaign_state.
        resp = await api_client.get(
            f"/strategies/{strategy_id}/campaign",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        overview = resp.json()
        assert overview["campaign_state"] == "paused_bounce_rate", (
            f"Expected campaign to be paused at bounce rate 3.01%, got: {campaigns[0]['status']}"
        )

        # No further sends
        gmail_mock.reset_capture()
        await api_client.post("/debug/flush-scheduled-sends", headers=headers)
        assert len(gmail_mock.get_capture().send_calls) == 0, (
            "Gmail send went out after bounce-rate pause"
        )

    async def test_sending_cap_defers_not_drops(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """
        When the daily send cap is reached, additional sends are deferred (rescheduled)
        not silently dropped. Total sent in the 24h window must not exceed the cap.
        """
        headers = _auth_headers(user_a_tokens)

        # Set a low cap for this test
        resp = await api_client.post("/debug/set-send-cap", headers=headers,
                                     json={"daily_cap": 2})
        assert resp.status_code == 200

        # Schedule 5 sends
        for i in range(5):
            await api_client.post("/debug/schedule-send", headers=headers, json={
                "to": f"cap_test_{i}@example.com",
                "subject": "Test",
                "body": "Body with unsubscribe",
                "include_unsubscribe": True,
            })

        gmail_mock.reset_capture()
        await api_client.post("/debug/flush-scheduled-sends", headers=headers)

        sent_count = len(gmail_mock.get_capture().send_calls)
        assert sent_count <= 2, f"Send cap of 2 was exceeded: {sent_count} emails sent"

        # Remaining must be in deferred/pending state, not dropped
        resp = await api_client.get("/debug/deferred-sends", headers=headers)
        deferred = resp.json()
        assert len(deferred) >= 3, f"Expected 3 deferred sends, got {len(deferred)}"

    async def test_unsubscribe_reply_suppresses_and_stops_sequence(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """
        A reply containing 'stop emailing me' must be classified as unsubscribe_request,
        add the sender to the suppression list, and stop the sequence. No next step sent.
        """
        headers = _auth_headers(user_a_tokens)
        product = await create_product(api_client, headers)
        await create_past_clients(api_client, headers, product["id"])
        strategy = await create_strategy(api_client, headers, product["id"])
        strategy_id = strategy["id"]
        await api_client.post(f"/strategies/{strategy_id}/leads/source", headers=headers, json={})

        resp = await api_client.get(f"/strategies/{strategy_id}/leads", headers=headers)
        leads = resp.json()["items"]
        assert len(leads) >= 1
        lead = leads[0]
        lead_id = lead["id"]

        # Replies arrive on the Gmail poll in production; /debug/inbound-reply
        # feeds the same InboundMessage through the real route_inbound_impl,
        # so the classifier -- not the test -- decides this is an opt-out.
        resp = await api_client.post(
            "/debug/inbound-reply",
            headers=headers,
            json={"lead_id": lead_id, "body": "stop emailing me please"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("classification") == "unsubscribe_request"

        # Suppression list must contain this email. GET /suppression returns
        # {"entries": [...]} and takes no filter params -- the previous
        # `len(resp.json()) >= 1` counted dict KEYS, so it passed on an empty
        # list.
        resp = await api_client.get("/suppression", headers=headers)
        entries = resp.json()["entries"]
        assert any((e["email"] or "").lower() == lead["email"].lower() for e in entries), (
            "Email not added to suppression list after unsubscribe reply"
        )

        # Sequence must be stopped (LeadDetailOut has no sequence fields).
        for status in enrollment_statuses(db_session, lead_id):
            assert status == "stopped", f"enrollment left {status} after an opt-out"

        # No further Gmail sends
        gmail_mock.reset_capture()
        await api_client.post("/debug/flush-scheduled-sends", headers=headers)
        suppressed_emails = [lead["email"]]
        for call in gmail_mock.get_capture().send_calls:
            to = call.get("to", "")
            assert to not in suppressed_emails, f"Sent to suppressed email: {to}"


class TestWhatsAppComplianceRules:
    async def test_free_form_to_closed_window_blocked(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """
        Sending a free-form WhatsApp message to a number with no open customer-service
        window must raise ComplianceError. Meta API must NOT be called.
        """
        headers = _auth_headers(user_a_tokens)
        whatsapp_mock.reset_capture()

        resp = await api_client.post(
            "/debug/send-whatsapp-freeform",
            headers=headers,
            json={
                "to": whatsapp_mock.CLOSED_WINDOW_PHONE,
                "message": "Hey, following up on our offer!",
            },
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "window" in str(body).lower() or body.get("compliance_code") == "WHATSAPP_WINDOW_CLOSED"

        # Meta API must NOT have been called
        assert len(whatsapp_mock.get_capture().send_calls) == 0, (
            "WhatsApp send was called for a closed customer-service window"
        )

    async def test_unapproved_template_blocked(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """
        Attempting to send via an unapproved/rejected WhatsApp template must raise ComplianceError.
        """
        headers = _auth_headers(user_a_tokens)
        whatsapp_mock.reset_capture()

        resp = await api_client.post(
            "/debug/send-whatsapp-template",
            headers=headers,
            json={
                "to": "+14155550101",
                "template_name": "rejected_template",  # in REJECTED_TEMPLATES set
                "template_params": ["Hi", "Alice"],
            },
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "approved" in str(body).lower() or body.get("compliance_code") == "WHATSAPP_TEMPLATE_NOT_APPROVED"

        assert len(whatsapp_mock.get_capture().send_calls) == 0

    async def test_cold_send_without_optin_blocked(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """
        Sending any WhatsApp message to a number with no opt-in record must be blocked.
        """
        headers = _auth_headers(user_a_tokens)
        whatsapp_mock.reset_capture()

        # No opt-in has been recorded for this number
        resp = await api_client.post(
            "/debug/send-whatsapp-template",
            headers=headers,
            json={
                "to": "+14999990000",  # never opted in
                "template_name": "approved_cold_outreach_v1",
                "template_params": ["Hi", "Test"],
            },
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "opt" in str(body).lower() or body.get("compliance_code") == "WHATSAPP_NO_OPTIN"
        assert len(whatsapp_mock.get_capture().send_calls) == 0

    async def test_stop_message_adds_suppression_and_stops_sequence_atomically(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """
        An inbound 'STOP' message must atomically:
        1. Add sender to suppression list
        2. Write opt-out audit row
        3. Stop active sequence for this phone number
        All three must occur or none (transaction guarantee).
        """
        headers = _auth_headers(user_a_tokens)
        phone = "+14155550801"

        # Create a lead + sequence for this phone
        product = await create_product(api_client, headers)
        await create_past_clients(api_client, headers, product["id"])
        strategy = await create_strategy(api_client, headers, product["id"])
        strategy_id = strategy["id"]

        # Register opt-in for this phone. Consent is recorded against a LEAD
        # (POST /leads/{id}/whatsapp-optin) -- there is no bare
        # /whatsapp/opt-in route, because an opt-in with no lead has nothing
        # to prove consent about.
        from app.db.models import Lead, LeadStatus

        lead = Lead(strategy_id=strategy_id, source="test", phone=phone,
                    email=f"stop-{phone.strip('+')}@test.io",
                    status=LeadStatus.SOURCED)
        db_session.add(lead)
        db_session.commit()

        resp = await api_client.post(
            f"/leads/{lead.id}/whatsapp-optin", headers=headers,
            json={"source": "web_form", "phone": phone,
                  "evidence": "test_setup", "consent_text": "I agree"},
        )
        assert resp.status_code == 201, resp.text

        # Build STOP webhook payload and deliver it
        stop_payload = whatsapp_mock.build_message_webhook(
            from_number=phone,
            body_text="STOP",
        )
        resp = await api_client.post(
            "/webhooks/whatsapp", **whatsapp_mock.signed_request(stop_payload)
        )
        assert resp.status_code == 200

        # 1. Suppression list must contain this phone
        resp = await api_client.get("/suppression", headers=headers)
        entries = resp.json()["entries"]
        assert any(e["phone"] == phone for e in entries), (
            "Phone not added to suppression after STOP"
        )

        # 2. Opt-out audit row must exist. whatsapp_optins is an append-only
        # consent ledger with no read endpoint -- a revocation is a NEW
        # opted_out row, which is exactly what this asserts.
        from app.db.models import OptInStatus, WhatsAppOptIn

        db_session.expire_all()
        audit = (
            db_session.query(WhatsAppOptIn)
            .filter(WhatsAppOptIn.phone == phone,
                    WhatsAppOptIn.status == OptInStatus.OPTED_OUT)
            .all()
        )
        assert len(audit) >= 1, "No opt-out audit record written after STOP"

        # 3. Sequence must be stopped
        resp = await api_client.get(
            f"/strategies/{strategy_id}/sequences?phone={phone}",
            headers=headers,
        )
        sequences = resp.json()
        if sequences:
            assert all(s.get("status") == "stopped" for s in sequences), (
                "Sequence not stopped after STOP message"
            )


class TestGDPRComplianceRules:
    async def test_gdpr_delete_wipes_data_and_creates_tombstone(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """
        DELETE /leads/{id} must:
        - Remove PII (email, phone, name, company) from the lead record
        - Keep a tombstone row (id present, pii null, deleted_at set)
        - Return 204
        """
        headers = _auth_headers(user_a_tokens)
        product = await create_product(api_client, headers)
        await create_past_clients(api_client, headers, product["id"])
        strategy = await create_strategy(api_client, headers, product["id"])
        strategy_id = strategy["id"]
        await api_client.post(f"/strategies/{strategy_id}/leads/source", headers=headers, json={})

        resp = await api_client.get(f"/strategies/{strategy_id}/leads", headers=headers)
        leads = resp.json()["items"]
        assert len(leads) >= 1
        lead_id = leads[0]["id"]
        original_email = leads[0]["email"]

        # GDPR delete
        resp = await api_client.delete(f"/leads/{lead_id}", headers=headers)
        assert resp.status_code == 204

        # The tombstone IS the surviving lead row: gdpr_delete_lead keeps the
        # id + external_id and nulls every personal field, so GET /leads/{id}
        # is how you read it. There is no separate /tombstone route.
        resp = await api_client.get(f"/leads/{lead_id}", headers=headers)
        assert resp.status_code == 200
        tombstone = resp.json()
        assert not tombstone.get("email")
        assert not tombstone.get("phone")
        assert not tombstone.get("full_name")
        assert tombstone["status"] == "dropped"
        assert (tombstone.get("enrichment_json") or {}).get("gdpr_deleted") is True

    async def test_deleted_lead_not_re_sourced(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """
        After GDPR delete, running lead sourcing again must not re-introduce
        the deleted lead (tombstone suppresses re-import).
        """
        headers = _auth_headers(user_a_tokens)
        product = await create_product(api_client, headers)
        await create_past_clients(api_client, headers, product["id"])
        strategy = await create_strategy(api_client, headers, product["id"])
        strategy_id = strategy["id"]
        await api_client.post(f"/strategies/{strategy_id}/leads/source", headers=headers, json={})

        resp = await api_client.get(f"/strategies/{strategy_id}/leads", headers=headers)
        leads = resp.json()["items"]
        lead_id = leads[0]["id"]
        deleted_email = leads[0]["email"]

        # GDPR delete
        await api_client.delete(f"/leads/{lead_id}", headers=headers)

        # Re-source (Apollo mock will return same people)
        await api_client.post(f"/strategies/{strategy_id}/leads/source", headers=headers, json={})

        resp = await api_client.get(f"/strategies/{strategy_id}/leads", headers=headers)
        remaining_emails = [l["email"] for l in resp.json()["items"]]
        assert deleted_email not in remaining_emails, (
            f"GDPR-deleted lead {deleted_email} was re-sourced — tombstone suppression failed"
        )


class TestVerificationGating:
    async def test_strategy_with_fail_pass_cannot_source_leads(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """
        A strategy that has any FAIL verification pass must return 422
        when POST /strategies/{id}/leads/source is attempted.
        The system must not proceed to Apollo until all 10 passes are PASS.
        """
        headers = _auth_headers(user_a_tokens)
        product = await create_product(api_client, headers)
        await create_past_clients(api_client, headers, product["id"])

        # Create strategy but inject a FAIL pass into verified_passes_json
        strategy = await create_strategy(api_client, headers, product["id"])
        strategy_id = strategy["id"]

        # Force a verification failure via debug endpoint
        resp = await api_client.post(
            f"/debug/inject-verification-fail",
            headers=headers,
            json={"strategy_id": strategy_id, "pass_number": 4, "reason": "test fail"},
        )
        assert resp.status_code == 200

        # Attempt to source leads — must be rejected
        resp = await api_client.post(
            f"/strategies/{strategy_id}/leads/source",
            headers=headers,
            json={},
        )
        # 409, not 422: leads.py refuses on strategy STATUS, and status is a
        # state conflict, not a malformed request.
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert "verification" in str(body).lower() or "fail" in str(body).lower(), (
            f"Expected 409 with verification failure message, got: {body}"
        )

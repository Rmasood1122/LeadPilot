"""
1C — Security integration tests.

Covers:
  - JWT lifecycle (expired, tampered, missing, refresh)
  - Cross-tenant isolation on every resource type
  - Signed unsubscribe token (valid / invalid / expired)
  - Webhook signature rejection (WhatsApp, Calendly)
  - Device token ownership enforcement
  - GDPR delete ownership enforcement
  - Admin-only endpoint gating
"""
from __future__ import annotations

import base64
import json
import time
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
import jwt as pyjwt

from tests.integration.conftest import (
    _auth_headers,
    create_past_clients,
    create_product,
    create_strategy,
)
from tests.integration.mocks import calendly_mock, whatsapp_mock

pytestmark = pytest.mark.asyncio

SECRET_KEY = "test-secret-key-not-for-production"


# ---------------------------------------------------------------------------
# JWT lifecycle tests
# ---------------------------------------------------------------------------

class TestJWTLifecycle:
    async def test_expired_token_returns_401(self, api_client: AsyncClient, user_a_tokens, all_mocks):
        """An expired JWT must return 401."""
        # Build an already-expired token
        expired_token = pyjwt.encode(
            {"sub": "user_a", "exp": int(time.time()) - 3600},
            SECRET_KEY,
            algorithm="HS256",
        )
        # /auth/me, not /products: the products collection has no GET route,
        # so it answers 405 from routing before auth is consulted.
        resp = await api_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401

    async def test_tampered_signature_returns_401(self, api_client: AsyncClient, user_a_tokens, all_mocks):
        """A token with a tampered signature must return 401."""
        import base64

        valid_token = user_a_tokens["access_token"]
        parts = valid_token.split(".")
        sig = parts[2]

        # Flip a character at the FRONT of the signature, not the end.
        #
        # An HS256 signature is 32 bytes = 43 base64url characters, and
        # 43 * 6 = 258 bits, so the LAST character carries only 2 significant
        # bits - its low 4 bits are discarded on decode. Flipping it is a no-op
        # for 4 of the 64 possible values (Y, Z, a, b), leaving a perfectly
        # valid token: /auth/me then returns 200 and this test failed for the
        # right reason on roughly 6% of runs. It read as an intermittent auth
        # vulnerability and was neither.
        tampered_sig = ("a" if sig[0] != "a" else "b") + sig[1:]
        tampered_token = ".".join(parts[:2] + [tampered_sig])

        def _decode(segment: str) -> bytes:
            return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))

        assert _decode(tampered_sig) != _decode(sig), (
            "the tampering must actually change the signature bytes"
        )

        resp = await api_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {tampered_token}"},
        )
        assert resp.status_code == 401

    async def test_missing_token_returns_401(self, api_client: AsyncClient, all_mocks):
        """A request with no Authorization header must return 401."""
        resp = await api_client.get("/auth/me")
        assert resp.status_code == 401

    async def test_valid_refresh_token_issues_new_access_token(
        self, api_client: AsyncClient, user_a_tokens, all_mocks
    ):
        """A valid refresh token must return a new access token."""
        resp = await api_client.post(
            "/auth/refresh",
            json={"refresh_token": user_a_tokens["refresh_token"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        # Not `!= the old token`: iat/exp have second granularity, so a refresh
        # in the same second as the original login mints a byte-identical JWT.
        # The contract under test is that the token WORKS.
        me = await api_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {data['access_token']}"},
        )
        assert me.status_code == 200

    async def test_expired_refresh_token_returns_401(self, api_client: AsyncClient, all_mocks):
        """An expired refresh token must return 401."""
        expired_refresh = pyjwt.encode(
            {"sub": "user_a", "type": "refresh", "exp": int(time.time()) - 3600},
            SECRET_KEY,
            algorithm="HS256",
        )
        resp = await api_client.post(
            "/auth/refresh",
            json={"refresh_token": expired_refresh},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------

class TestCrossTenantIsolation:
    """User A must never access User B's resources."""

    async def test_strategy_cross_tenant_isolation(
        self, api_client: AsyncClient, user_a_tokens, user_b_tokens, all_mocks, db_session
    ):
        """User B cannot read User A's strategy."""
        a_headers = _auth_headers(user_a_tokens)
        b_headers = _auth_headers(user_b_tokens)

        product = await create_product(api_client, a_headers)
        await create_past_clients(api_client, a_headers, product["id"])
        strategy = await create_strategy(api_client, a_headers, product["id"])

        resp = await api_client.get(
            f"/strategies/{strategy['id']}",
            headers=b_headers,
        )
        assert resp.status_code in (403, 404), (
            f"User B accessed User A's strategy — expected 403/404, got {resp.status_code}"
        )

    async def test_product_cross_tenant_isolation(
        self, api_client: AsyncClient, user_a_tokens, user_b_tokens, all_mocks, db_session
    ):
        """User B cannot read User A's product."""
        a_headers = _auth_headers(user_a_tokens)
        b_headers = _auth_headers(user_b_tokens)
        product = await create_product(api_client, a_headers)

        resp = await api_client.get(f"/products/{product['id']}", headers=b_headers)
        assert resp.status_code in (403, 404)

    async def test_lead_cross_tenant_isolation(
        self, api_client: AsyncClient, user_a_tokens, user_b_tokens, all_mocks, db_session
    ):
        """User B cannot read User A's leads."""
        a_headers = _auth_headers(user_a_tokens)
        b_headers = _auth_headers(user_b_tokens)

        product = await create_product(api_client, a_headers)
        await create_past_clients(api_client, a_headers, product["id"])
        strategy = await create_strategy(api_client, a_headers, product["id"])
        await api_client.post(f"/strategies/{strategy['id']}/leads/source", headers=a_headers, json={})

        resp = await api_client.get(
            f"/strategies/{strategy['id']}/leads",
            headers=b_headers,
        )
        assert resp.status_code in (403, 404)

    async def test_campaign_cross_tenant_isolation(
        self, api_client: AsyncClient, user_a_tokens, user_b_tokens, all_mocks, db_session
    ):
        """User B cannot read User A's campaigns."""
        a_headers = _auth_headers(user_a_tokens)
        b_headers = _auth_headers(user_b_tokens)

        product = await create_product(api_client, a_headers)
        await create_past_clients(api_client, a_headers, product["id"])
        strategy = await create_strategy(api_client, a_headers, product["id"])
        await api_client.post(f"/strategies/{strategy['id']}/leads/source", headers=a_headers, json={})

        # NOTE: the route is /campaign (singular). This test used to request
        # /campaigns, which matches no route at all -- so it collected a 404
        # from the router and passed while verifying nothing. The endpoint it
        # was supposed to be testing had no auth dependency whatsoever.
        resp = await api_client.get(
            f"/strategies/{strategy['id']}/campaign",
            headers=b_headers,
        )
        assert resp.status_code in (403, 404), (
            f"User B read User A's campaign overview -- got {resp.status_code}"
        )

        # ...and it must not be readable with no credentials at all.
        resp = await api_client.get(f"/strategies/{strategy['id']}/campaign")
        assert resp.status_code in (401, 403), (
            f"Campaign overview served to an anonymous caller -- got {resp.status_code}"
        )

    async def test_theme_cross_tenant_isolation(
        self, api_client: AsyncClient, user_a_tokens, user_b_tokens, all_mocks, db_session
    ):
        """User B cannot modify User A's theme settings."""
        a_headers = _auth_headers(user_a_tokens)
        b_headers = _auth_headers(user_b_tokens)

        # User A sets a theme
        await api_client.put("/me/theme", headers=a_headers, json={
            "preset": "dark",
            "primary_color": "#FF0000",
        })

        # User B tries to modify
        resp = await api_client.put("/me/theme", headers=b_headers, json={
            "preset": "light",
        })
        # User B can set their own theme — this is fine
        # But they must not be able to set it on User A's account
        assert resp.status_code in (200, 201)  # User B can set their own

        # User A's theme must be unchanged
        resp_a = await api_client.get("/me/theme", headers=a_headers)
        # GET /me/theme wraps the theme: {"theme": {...}}.
        assert resp_a.json()["theme"]["preset"] == "dark"

    async def test_calendly_booking_never_routes_to_another_users_lead(
        self, api_client: AsyncClient, user_a_tokens, user_b_tokens, all_mocks, db_session
    ):
        """A booking must land on the tenant whose link produced it.

        Same class as the inbound-reply bug: webhooks.py used to resolve the
        invitee with `Lead.email ==` across the whole table and take the first
        row, so with two customers prospecting the same person a booking could
        flip the wrong account's lead to meeting_booked and stop their
        sequences. The booking link now carries the owning tenant's id as a
        UTM parameter and the handler resolves on it.
        """
        from app.db.models import Lead, LeadStatus

        a_headers = _auth_headers(user_a_tokens)
        b_headers = _auth_headers(user_b_tokens)
        shared_email = f"booking_{uuid.uuid4().hex[:8]}@prospect.io"

        async def _lead_for(headers) -> str:
            product = await create_product(api_client, headers)
            await create_past_clients(api_client, headers, product["id"])
            strategy = await create_strategy(api_client, headers, product["id"])
            lead = Lead(strategy_id=strategy["id"], source="test",
                        email=shared_email, status=LeadStatus.VERIFIED)
            db_session.add(lead)
            db_session.commit()
            return str(lead.id)

        a_lead_id = await _lead_for(a_headers)
        b_lead_id = await _lead_for(b_headers)

        # The booking comes back on a link generated for User B.
        payload = calendly_mock.build_booking_webhook(
            invitee_email=shared_email,
            lead_id=b_lead_id,
            tenant_id=user_b_tokens["user"]["id"],
        )
        resp = await api_client.post(
            "/webhooks/calendly", **calendly_mock.signed_request(payload))
        assert resp.status_code == 200, resp.text
        assert resp.json()["matched"] is True

        db_session.expire_all()
        assert db_session.get(Lead, b_lead_id).status is LeadStatus.MEETING_BOOKED
        assert db_session.get(Lead, a_lead_id).status is LeadStatus.VERIFIED, (
            "User A's lead was booked by a webhook belonging to User B"
        )

    async def test_calendly_booking_without_tenant_id_is_quarantined(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """An untagged booking must match NOTHING, not guess a tenant.

        This is the old-link case: a booking made through a link generated
        before tenant tagging existed, or one found organically. Guessing
        would reintroduce exactly the bug above.
        """
        from app.db.models import Lead, LeadStatus

        headers = _auth_headers(user_a_tokens)
        email = f"untagged_{uuid.uuid4().hex[:8]}@prospect.io"

        product = await create_product(api_client, headers)
        await create_past_clients(api_client, headers, product["id"])
        strategy = await create_strategy(api_client, headers, product["id"])
        lead = Lead(strategy_id=strategy["id"], source="test",
                    email=email, status=LeadStatus.VERIFIED)
        db_session.add(lead)
        db_session.commit()
        lead_id = str(lead.id)

        payload = calendly_mock.build_booking_webhook(
            invitee_email=email, lead_id=lead_id)  # no tenant_id
        resp = await api_client.post(
            "/webhooks/calendly", **calendly_mock.signed_request(payload))

        # Acknowledged so Calendly stops retrying, but nothing was matched.
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["matched"] is False
        assert body.get("quarantined") is True

        db_session.expire_all()
        assert db_session.get(Lead, lead_id).status is LeadStatus.VERIFIED

    async def test_inbound_reply_never_routes_to_another_users_lead(
        self, api_client: AsyncClient, user_a_tokens, user_b_tokens, all_mocks, db_session
    ):
        """A reply landing in one account must never touch another account's lead.

        Two customers prospecting the same person is routine in B2B.
        route_inbound_impl used to match on `Lead.email == from_address` with
        no tenancy filter and take the first row anywhere in the table, so a
        reply to User B could flip User A's lead to REPLIED, stop A's
        sequences, pollute A's learning loop with a REPLIED outcome, and -- on
        an opt-out -- suppress A's lead.
        """
        from app.db.models import Lead, LeadStatus

        a_headers = _auth_headers(user_a_tokens)
        b_headers = _auth_headers(user_b_tokens)
        shared_email = f"shared_{uuid.uuid4().hex[:8]}@prospect.io"

        async def _lead_for(headers) -> str:
            product = await create_product(api_client, headers)
            await create_past_clients(api_client, headers, product["id"])
            strategy = await create_strategy(api_client, headers, product["id"])
            lead = Lead(strategy_id=strategy["id"], source="test",
                        email=shared_email, status=LeadStatus.VERIFIED)
            db_session.add(lead)
            db_session.commit()
            return str(lead.id)

        a_lead_id = await _lead_for(a_headers)
        b_lead_id = await _lead_for(b_headers)

        # The reply arrives on User B's account.
        resp = await api_client.post(
            "/debug/inbound-reply",
            headers=b_headers,
            json={"lead_id": b_lead_id, "body": "Yes, let us talk next week"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["lead_id"] == b_lead_id

        db_session.expire_all()
        assert db_session.get(Lead, b_lead_id).status is LeadStatus.REPLIED
        assert db_session.get(Lead, a_lead_id).status is LeadStatus.VERIFIED, (
            "User A's lead was mutated by a reply delivered to User B"
        )


# ---------------------------------------------------------------------------
# Unsubscribe token tests
# ---------------------------------------------------------------------------

class TestUnsubscribeToken:
    async def test_valid_signed_unsubscribe_token_works_without_auth(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """
        The unsubscribe endpoint must accept a valid signed token without requiring
        Bearer authentication (recipients don't have accounts).
        """
        headers = _auth_headers(user_a_tokens)
        email = "unsub_test@example.com"

        # Generate unsubscribe token
        resp = await api_client.post(
            "/debug/generate-unsubscribe-token",
            headers=headers,
            json={"email": email},
        )
        assert resp.status_code == 200
        token = resp.json()["token"]

        # Use the token without auth headers
        resp = await api_client.get(f"/unsubscribe/{token}")
        assert resp.status_code in (200, 302)  # redirect or success page

        # Email must be suppressed
        resp = await api_client.get(f"/suppression?email={email}", headers=headers)
        assert len(resp.json()) >= 1

    async def test_invalid_unsubscribe_token_rejected_safely(
        self, api_client: AsyncClient, all_mocks
    ):
        """
        An invalid token must return a safe rejection without revealing whether
        the email exists in the system.
        """
        resp = await api_client.get("/unsubscribe/invalid.token.here")
        assert resp.status_code in (400, 404)
        body = resp.text + str(resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {})
        # Must not leak email existence
        assert "does not exist" not in body.lower()
        assert "not found in" not in body.lower()


# ---------------------------------------------------------------------------
# Webhook signature tests
# ---------------------------------------------------------------------------

class TestWebhookSignatures:
    async def test_whatsapp_webhook_invalid_signature_rejected(
        self, api_client: AsyncClient, all_mocks
    ):
        """WhatsApp webhook with invalid X-Hub-Signature-256 must return 401."""
        payload = whatsapp_mock.build_message_webhook(
            from_number="+14155550101",
            body_text="Hello",
        )
        resp = await api_client.post(
            "/webhooks/whatsapp",
            json=payload,
            headers={"X-Hub-Signature-256": "sha256=invalidsignaturehere"},
        )
        # 401, not 403: see app/api/webhooks_whatsapp.py:125.
        assert resp.status_code == 401

    async def test_whatsapp_webhook_no_signature_rejected(
        self, api_client: AsyncClient, all_mocks
    ):
        """WhatsApp webhook with no signature header must return 401."""
        payload = whatsapp_mock.build_message_webhook(
            from_number="+14155550101",
            body_text="Hello",
        )
        resp = await api_client.post("/webhooks/whatsapp", json=payload)
        # 401, not 403: app/api/webhooks_whatsapp.py raises
        # HTTPException(401, "invalid webhook signature").
        assert resp.status_code == 401

    async def test_calendly_webhook_invalid_signature_rejected(
        self, api_client: AsyncClient, all_mocks
    ):
        """Calendly webhook with invalid signature must return 401."""
        payload = calendly_mock.build_booking_webhook()
        resp = await api_client.post(
            "/webhooks/calendly",
            json=payload,
            headers={"Calendly-Webhook-Signature": "sha256=invalidsig"},
        )
        # 401, not 403: app/api/webhooks.py:37 raises
        # HTTPException(401, "invalid webhook signature").
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Admin-only gating
# ---------------------------------------------------------------------------

class TestAdminOnlyEndpoints:
    async def test_non_admin_cannot_access_playbook_recompute(
        self, api_client: AsyncClient, user_a_tokens, all_mocks
    ):
        """POST /playbook/recompute is admin-only — non-admin must get 403."""
        headers = _auth_headers(user_a_tokens)
        resp = await api_client.post("/admin/playbook/recompute", headers=headers)
        assert resp.status_code == 403

    async def test_non_admin_cannot_access_admin_users_list(
        self, api_client: AsyncClient, user_a_tokens, all_mocks
    ):
        """GET /admin/users is admin-only."""
        headers = _auth_headers(user_a_tokens)
        resp = await api_client.get("/admin/users", headers=headers)
        assert resp.status_code == 403

    async def test_non_admin_cannot_access_circuit_breakers(
        self, api_client: AsyncClient, user_a_tokens, all_mocks
    ):
        """GET /admin/circuit-breakers is admin-only."""
        headers = _auth_headers(user_a_tokens)
        resp = await api_client.get("/admin/circuit-breakers", headers=headers)
        assert resp.status_code == 403

    async def test_device_token_only_deletable_by_owner(
        self, api_client: AsyncClient, user_a_tokens, user_b_tokens, all_mocks, db_session
    ):
        """User B must not be able to delete User A's FCM device token."""
        a_headers = _auth_headers(user_a_tokens)
        b_headers = _auth_headers(user_b_tokens)

        # User A registers a device token. The route is /devices/register
        # (app/api/devices.py mounts the router at /devices and the handler at
        # "/register"); a bare POST /devices does not exist.
        token = f"fcm_token_{uuid.uuid4().hex}"
        reg = await api_client.post("/devices/register", headers=a_headers, json={
            "token": token,
            "platform": "android",
        })
        assert reg.status_code == 200, reg.text

        # User B tries to delete it
        resp = await api_client.delete(f"/devices/{token}", headers=b_headers)
        assert resp.status_code in (403, 404)

        # Token must still exist, and still be valid, for User A. There is no
        # GET /devices list route, so this is asserted against the database -
        # db_session is a SYNC Session, so no await here.
        from app.db.models import DeviceToken

        row = (
            db_session.query(DeviceToken)
            .filter(DeviceToken.token == token)
            .one_or_none()
        )
        assert row is not None
        assert row.is_valid is True

    async def test_gdpr_delete_only_by_owner(
        self, api_client: AsyncClient, user_a_tokens, user_b_tokens, all_mocks, db_session
    ):
        """User B must not be able to GDPR-delete User A's lead."""
        a_headers = _auth_headers(user_a_tokens)
        b_headers = _auth_headers(user_b_tokens)

        product = await create_product(api_client, a_headers)
        await create_past_clients(api_client, a_headers, product["id"])
        strategy = await create_strategy(api_client, a_headers, product["id"])
        await api_client.post(f"/strategies/{strategy['id']}/leads/source", headers=a_headers, json={})

        resp = await api_client.get(f"/strategies/{strategy['id']}/leads", headers=a_headers)
        lead_id = resp.json()["items"][0]["id"]

        # User B attempts GDPR delete
        resp = await api_client.delete(f"/leads/{lead_id}", headers=b_headers)
        assert resp.status_code in (403, 404)

"""
Calendly API transport mock + webhook payload builders.

The FIXED_EVENT_ID is used in idempotency tests to deliver the same
webhook twice and assert it's processed only once.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import respx
from httpx import Request, Response

CALENDLY_BASE = "https://api.calendly.com"
FIXED_EVENT_ID = "calendly-event-fixed-idempotency-001"


from app.integrations.calendly import TENANT_TRACKING_PARAM


def build_booking_webhook(
    event_id: str | None = None,
    invitee_email: str = "alice.chen@saasco.io",
    lead_id: str | None = None,
    timestamp: str | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Build an invitee.created webhook payload.

    `tenant_id` populates payload.tracking.<TENANT_TRACKING_PARAM>, which is
    how Calendly returns the UTM parameter we attach to the booking link and
    the ONLY thing webhooks.py will resolve an account from. Leave it None to
    simulate an untagged link (a booking made before tenant tagging, or a link
    found organically) and exercise the quarantine path.
    """
    event_id = event_id or FIXED_EVENT_ID
    timestamp = timestamp or "2026-08-17T10:00:00.000000Z"
    payload: dict[str, Any] = {
        "event": "invitee.created",
        "payload": {
            # Calendly v2 carries the invitee email and the scheduled-event
            # uri FLAT on `payload` -- that is what webhooks.py reads to match
            # the lead and what extract_event_id() dedupes on. This mock only
            # had them nested under payload.invitee / payload.event, so every
            # delivery was accepted, matched no lead, and returned
            # {"matched": false} with a 200 -- the lead never became
            # meeting_booked. tests/test_calendly.py uses the flat shape.
            "email": invitee_email,
            "name": "Alice Chen",
            "uri": f"https://api.calendly.com/scheduled_events/{event_id}/invitees/invitee_001",
            "event_type": {
                "uuid": "event_type_uuid_001",
                "name": "30 Minute Meeting",
                "duration": 30,
            },
            "event": {
                "uuid": event_id,
                "start_time": "2026-08-20T14:00:00.000000Z",
                "end_time": "2026-08-20T14:30:00.000000Z",
                "location": {"type": "zoom"},
            },
            "invitee": {
                "uuid": "invitee_001",
                "email": invitee_email,
                "name": "Alice Chen",
                "created_at": timestamp,
                "updated_at": timestamp,
                "text_reminder_number": None,
            },
            "tracking": {
                # Real Calendly forwards the booking link's UTM parameters
                # here. app/integrations/calendly.py reads the tenant id from
                # TENANT_TRACKING_PARAM; utm_source stays free for the
                # customer's own attribution, which is why it is not used.
                "utm_source": "clienthunter",
                "utm_campaign": lead_id or "",
                **({TENANT_TRACKING_PARAM: tenant_id} if tenant_id else {}),
            },
        },
        "created_at": timestamp,
    }
    return payload


SIGNATURE_HEADER = "Calendly-Webhook-Signature"


def sign_payload(payload: dict[str, Any], secret: str = "calendly-secret-test",
                 timestamp: str = "1700000000") -> str:
    """Calendly's real signature format: t=<unix>,v1=<hmac_sha256(t + "." + body)>.

    This used to emit Stripe/Meta-style "sha256=<hmac(body)>", which
    calendly.verify_webhook_signature() rejects at the parse step (it splits
    on "," and reads the "t" and "v1" keys), so every signed Calendly delivery
    in the integration suite came back 401. The app matches Calendly's
    documented header; the mock did not.
    """
    body = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(secret.encode(),
                   f"{timestamp}.{body.decode()}".encode(),
                   hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


def signed_request(payload: dict[str, Any], secret: str | None = None) -> dict[str, Any]:
    """kwargs for an httpx POST whose body is EXACTLY what was signed.

    Both webhook handlers verify the signature against `await request.body()`.
    Passing `json=payload` lets httpx re-serialize with its own separators, so
    the bytes on the wire differ from the bytes that were signed and every
    delivery came back 401. Send the signed bytes as `content` instead.

        resp = await api_client.post(URL, **signed_request(payload))
    """
    body = json.dumps(payload, separators=(",", ":")).encode()
    sig = sign_payload(payload) if secret is None else sign_payload(payload, secret)
    return {
        "content": body,
        "headers": {"Content-Type": "application/json", SIGNATURE_HEADER: sig},
    }


def _user_info_handler(request: Request) -> Response:
    return Response(200, json={
        "resource": {
            "uri": "https://api.calendly.com/users/me",
            "name": "Test User",
            "email": "test@clienthunter.io",
            "scheduling_url": "https://calendly.com/testuser/30min",
            "timezone": "America/Chicago",
            "current_organization": "https://api.calendly.com/organizations/org_001",
        }
    })


def _event_types_handler(request: Request) -> Response:
    return Response(200, json={
        "collection": [{
            "uri": "https://api.calendly.com/event_types/event_type_uuid_001",
            "name": "30 Minute Meeting",
            "slug": "30min",
            "scheduling_url": "https://calendly.com/testuser/30min",
            "duration": 30,
            "active": True,
        }]
    })


def _webhook_subscriptions_handler(request: Request) -> Response:
    if request.method == "POST":
        return Response(201, json={"resource": {"uri": "https://api.calendly.com/webhook_subscriptions/sub_001"}})
    return Response(200, json={"collection": []})


def register(router: respx.MockRouter) -> None:
    """Register Calendly routes on the given respx router."""
    router.get(f"{CALENDLY_BASE}/users/me").mock(side_effect=_user_info_handler)
    router.get(f"{CALENDLY_BASE}/event_types").mock(side_effect=_event_types_handler)
    router.post(f"{CALENDLY_BASE}/webhook_subscriptions").mock(
        side_effect=_webhook_subscriptions_handler
    )
    router.get(f"{CALENDLY_BASE}/webhook_subscriptions").mock(
        side_effect=_webhook_subscriptions_handler
    )

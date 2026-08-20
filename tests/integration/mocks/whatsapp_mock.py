"""
WhatsApp Business Cloud API (Meta Graph API) transport mock.

Key behaviors:
  - Templates are approved by default unless name is in REJECTED_TEMPLATES
  - Send calls are captured and counted
  - Duplicate message-status webhooks have a fixed event_id for idempotency tests
  - Provides webhook payload builders for test use
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import respx
from httpx import Request, Response

META_BASE = "https://graph.facebook.com/v17.0"
WABA_ID = "test_waba_id"
PHONE_NUMBER_ID = "test_phone_id"

REJECTED_TEMPLATES: set[str] = {"rejected_template", "unapproved_template"}
CLOSED_WINDOW_PHONE = "+14155550999"   # No recent customer message from this number
OPTED_OUT_PHONE    = "+14155550998"   # This number sent STOP


@dataclass
class WhatsAppCallCapture:
    send_calls: list[dict[str, Any]] = field(default_factory=list)
    template_calls: list[str] = field(default_factory=list)


_capture = WhatsAppCallCapture()


def get_capture() -> WhatsAppCallCapture:
    return _capture


def reset_capture() -> None:
    _capture.send_calls.clear()
    _capture.template_calls.clear()


# ---------------------------------------------------------------------------
# Webhook payload builders (used in test assertions)
# ---------------------------------------------------------------------------

def build_message_webhook(
    from_number: str,
    body_text: str,
    msg_id: str | None = None,
    timestamp: int | None = None,
) -> dict[str, Any]:
    """Build a realistic inbound-message webhook payload."""
    msg_id = msg_id or f"wamid.{uuid.uuid4().hex}"
    timestamp = timestamp or int(time.time())
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": WABA_ID,
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "15550001111", "phone_number_id": PHONE_NUMBER_ID},
                    "contacts": [{"profile": {"name": "Test User"}, "wa_id": from_number}],
                    "messages": [{
                        "from": from_number,
                        "id": msg_id,
                        "timestamp": str(timestamp),
                        "text": {"body": body_text},
                        "type": "text",
                    }],
                },
                "field": "messages",
            }],
        }],
    }


def build_status_webhook(
    msg_id: str,
    status: str = "delivered",
    recipient_id: str = "+14155550101",
    timestamp: int | None = None,
) -> dict[str, Any]:
    """Build a message-status-update webhook payload (for idempotency tests use a fixed msg_id)."""
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": WABA_ID,
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": PHONE_NUMBER_ID},
                    "statuses": [{
                        "id": msg_id,
                        "status": status,
                        "timestamp": str(timestamp or int(time.time())),
                        "recipient_id": recipient_id,
                    }],
                },
                "field": "messages",
            }],
        }],
    }


SIGNATURE_HEADER = "X-Hub-Signature-256"


def sign_payload(payload: dict[str, Any], secret: str = "wh-app-secret-test") -> str:
    """Generate X-Hub-Signature-256 for a webhook payload."""
    body = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


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


# ---------------------------------------------------------------------------
# HTTP handlers
# ---------------------------------------------------------------------------

def _send_handler(request: Request) -> Response:
    try:
        body = json.loads(request.content)
    except Exception:
        body = {}
    _capture.send_calls.append(body)
    msg_id = f"wamid.{uuid.uuid4().hex}"
    return Response(200, json={
        "messaging_product": "whatsapp",
        "contacts": [{"input": body.get("to", ""), "wa_id": body.get("to", "")}],
        "messages": [{"id": msg_id}],
    })


def _template_status_handler(request: Request) -> Response:
    """Return template details; rejected if name is in REJECTED_TEMPLATES."""
    template_name = request.url.path.split("/")[-2] if "/" in request.url.path else "unknown"
    _capture.template_calls.append(template_name)
    status = "REJECTED" if template_name in REJECTED_TEMPLATES else "APPROVED"
    return Response(200, json={
        "data": [{
            "name": template_name,
            "status": status,
            "category": "MARKETING",
            "language": "en_US",
        }]
    })


def register(router: respx.MockRouter) -> None:
    """Register WhatsApp/Meta routes on the given respx router."""
    router.post(f"{META_BASE}/{PHONE_NUMBER_ID}/messages").mock(side_effect=_send_handler)
    # Template listing (pattern matches WABA template endpoints)
    router.get(respx.patterns.M(f"{META_BASE}/{WABA_ID}/message_templates")).mock(
        side_effect=_template_status_handler
    )

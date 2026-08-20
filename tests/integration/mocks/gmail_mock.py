"""
Gmail API transport mock.

Tracks send calls per thread so exactly-once assertions work on Celery retry tests.
Simulates thread replies for reply-classification integration tests.
"""
from __future__ import annotations

import base64
import email
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import respx
from httpx import Request, Response

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1"


@dataclass
class GmailCallCapture:
    send_calls: list[dict[str, Any]] = field(default_factory=list)
    sent_message_ids: set[str] = field(default_factory=set)
    # Map thread_id → list of reply message dicts to simulate
    queued_replies: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))


_capture = GmailCallCapture()


def get_capture() -> GmailCallCapture:
    return _capture


def reset_capture() -> None:
    _capture.send_calls.clear()
    _capture.sent_message_ids.clear()
    _capture.queued_replies.clear()


def queue_reply(thread_id: str, body_text: str, from_addr: str = "alice.chen@saasco.io") -> None:
    """Pre-load a simulated reply to be returned on history/messages fetch."""
    msg_id = f"reply_{uuid.uuid4().hex[:8]}"
    _capture.queued_replies[thread_id].append({
        "id": msg_id,
        "threadId": thread_id,
        "labelIds": ["INBOX"],
        "snippet": body_text[:100],
        "payload": {
            "headers": [
                {"name": "From", "value": from_addr},
                {"name": "Subject", "value": "Re: Test subject"},
                {"name": "Date", "value": "Mon, 17 Aug 2026 10:00:00 +0000"},
            ],
            "body": {"data": body_text.encode().hex()},
        },
    })


def _decode_raw(raw: str | None) -> dict:
    """urlsafe-b64 RFC-2822 -> {"to", "subject", "headers", "text"}."""
    if not raw:
        return {"to": "", "subject": "", "headers": {}, "text": ""}
    try:
        padded = raw + "=" * (-len(raw) % 4)
        mime = email.message_from_bytes(base64.urlsafe_b64decode(padded))
    except Exception:
        return {"to": "", "subject": "", "headers": {}, "text": ""}
    if mime.is_multipart():
        text = "".join(
            part.get_payload(decode=True).decode(errors="replace")
            for part in mime.walk()
            if part.get_content_type() == "text/plain"
            and part.get_payload(decode=True)
        )
    else:
        payload = mime.get_payload(decode=True)
        text = payload.decode(errors="replace") if payload else ""
    return {
        "to": mime.get("To", "") or "",
        "subject": mime.get("Subject", "") or "",
        "headers": {k: v for k, v in mime.items()},
        "text": text,
    }


def _send_handler(request: Request) -> Response:
    try:
        body = json.loads(request.content)
    except Exception:
        body = {}

    # Idempotency: if same raw message is sent twice, only count first
    # (in real tests, idempotency key is embedded in the message headers)
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    thread_id = body.get("threadId") or f"thread_{uuid.uuid4().hex[:8]}"

    # Decode the RFC-2822 payload. GmailChannel.send() transmits
    # {"raw": urlsafe_b64(mime)}, so without decoding, the recipient, subject
    # and List-Unsubscribe header are all invisible to assertions - tests that
    # filter on call["to"] or look for an address in the call silently matched
    # nothing and read as "no email was sent".
    decoded = _decode_raw(body.get("raw"))
    _capture.send_calls.append({
        "message_id": msg_id,
        "thread_id": thread_id,
        "body": body,
        **decoded,
    })
    _capture.sent_message_ids.add(msg_id)

    return Response(200, json={
        "id": msg_id,
        "threadId": thread_id,
        "labelIds": ["SENT"],
    })


def _message_get_handler(request: Request) -> Response:
    msg_id = request.url.path.split("/")[-1]
    return Response(200, json={
        "id": msg_id,
        "threadId": f"thread_{msg_id}",
        "labelIds": ["SENT"],
        "snippet": "Test email snippet",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Stop wasting hours on cold outreach"},
                {"name": "To", "value": "alice.chen@saasco.io"},
            ],
        },
    })


def _thread_get_handler(request: Request) -> Response:
    thread_id = request.url.path.split("/")[-1]
    replies = _capture.queued_replies.get(thread_id, [])
    return Response(200, json={
        "id": thread_id,
        "historyId": "12345",
        "messages": replies,
    })


def _history_list_handler(request: Request) -> Response:
    params = dict(request.url.params)
    # Return all queued replies across all threads
    all_replies = []
    for thread_id, msgs in _capture.queued_replies.items():
        for msg in msgs:
            all_replies.append({
                "id": str(uuid.uuid4().hex[:8]),
                "messages": [{"id": msg["id"], "threadId": thread_id}],
            })
    return Response(200, json={
        "history": all_replies,
        "historyId": "99999",
    })


def _token_refresh_handler(request: Request) -> Response:
    return Response(200, json={
        "access_token": "ya29.test-access-token",
        "expires_in": 3600,
        "token_type": "Bearer",
    })


def register(router: respx.MockRouter) -> None:
    """Register Gmail routes on the given respx router."""
    router.post(f"{GMAIL_BASE}/users/me/messages/send").mock(side_effect=_send_handler)
    router.get(respx.patterns.M(f"{GMAIL_BASE}/users/me/messages/")).mock(side_effect=_message_get_handler)
    router.get(respx.patterns.M(f"{GMAIL_BASE}/users/me/threads/")).mock(side_effect=_thread_get_handler)
    router.get(f"{GMAIL_BASE}/users/me/history").mock(side_effect=_history_list_handler)
    # OAuth token refresh
    router.post("https://oauth2.googleapis.com/token").mock(side_effect=_token_refresh_handler)

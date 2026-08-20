import hashlib
import hmac
import json
import time

import requests

SERVER_URL = "http://localhost:8000/webhooks/calendly"
SIGNING_KEY = "test-secret-123"   # must match CALENDLY_WEBHOOK_SECRET in .env
EMAIL = "lead@example.com"        # doesn't need to exist in DB for this test

payload = {
    "event": "invitee.created",
    "created_at": "2026-08-17T10:00:00.000000Z",
    "payload": {
        "email": EMAIL,
        "name": "Test Lead",
        "event_type": {"name": "30 Minute Meeting"},
        "calendar_event": {
            "start_time": "2026-08-20T15:00:00Z",
            "end_time": "2026-08-20T15:30:00Z",
        },
        "questions_and_answers": [],
    },
}

raw_body = json.dumps(payload).encode()
timestamp = str(int(time.time()))

signed_payload = f"{timestamp}.{raw_body.decode()}".encode()
signature = hmac.new(SIGNING_KEY.encode(), signed_payload, hashlib.sha256).hexdigest()
header_value = f"t={timestamp},v1={signature}"

resp = requests.post(
    SERVER_URL,
    data=raw_body,
    headers={
        "Content-Type": "application/json",
        "Calendly-Webhook-Signature": header_value,
    },
)

print("Status code:", resp.status_code)
print("Response body:", resp.json())
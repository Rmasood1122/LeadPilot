import hashlib
import hmac
import json

import requests

SERVER_URL = "http://localhost:8000/webhooks/whatsapp"
APP_SECRET = "test-secret-456"   # must match WHATSAPP_APP_SECRET in .env

payload = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "123456789",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "15551234567",
                            "phone_number_id": "987654321",
                        },
                        "contacts": [
                            {"profile": {"name": "Test Lead"}, "wa_id": "923001234567"}
                        ],
                        "messages": [
                            {
                                "from": "923001234567",
                                "id": "wamid.TEST123",
                                "timestamp": "1755417600",
                                "text": {"body": "Hi, interested — tell me more"},
                                "type": "text",
                            }
                        ],
                    },
                }
            ],
        }
    ],
}

raw_body = json.dumps(payload).encode()
signature = hmac.new(APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()

resp = requests.post(
    SERVER_URL,
    data=raw_body,
    headers={
        "Content-Type": "application/json",
        "X-Hub-Signature-256": f"sha256={signature}",
    },
)

print("Status code:", resp.status_code)
print("Response body:", resp.json())

verify_resp = requests.get(
    "http://localhost:8000/webhooks/whatsapp",
    params={
        "hub.mode": "subscribe",
        "hub.verify_token": "test-verify-789",
        "hub.challenge": "12345",
    },
)
print("\nGET verify status:", verify_resp.status_code)
print("GET verify body:", verify_resp.text)
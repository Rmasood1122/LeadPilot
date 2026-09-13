"""SMS delivery for one-time verification codes.

Transport is configuration (SMS_PROVIDER), mirroring app/services/email_sender.py:

  twilio   POST https://api.twilio.com/2010-04-01/Accounts/<sid>/Messages.json
           (basic auth SID:token; From is TWILIO_FROM_NUMBER, or a Messaging
           Service when that value starts "MG")
  console  log a MASKED notice and deliver nothing -- local development
  memory   append to SENT_SMS, deliver nothing -- the test suite reads codes here

Explicit, never inferred from which keys happen to be set: a production
process with a misspelled key name must fail at send time, not quietly log
every user's code to stdout.

A new provider is one class with `send(to, body) -> str` in PROVIDERS.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.core.exceptions import ClientHunterError

logger = logging.getLogger(__name__)

__all__ = ["SmsSendError", "SENT_SMS", "send_sms", "reset_sent_sms", "mask_phone"]


class SmsSendError(ClientHunterError):
    """The message could not be handed to the SMS transport."""


# In-process capture for SMS_PROVIDER=memory. Module-level on purpose: a test
# POSTs the send endpoint and then reads the code back out of here.
SENT_SMS: list[dict] = []


def reset_sent_sms() -> None:
    SENT_SMS.clear()


def mask_phone(phone: str | None) -> str:
    """+923001234567 -> +92*******567. For logs; never log a full number."""
    value = phone or ""
    if len(value) <= 6:
        return "*" * len(value)
    return value[:3] + "*" * (len(value) - 6) + value[-3:]


def _http() -> httpx.Client:
    """Factory tests monkeypatch."""
    return httpx.Client(timeout=settings.sms_send_timeout_seconds)


class TwilioProvider:
    name = "twilio"
    URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

    def send(self, to: str, body: str) -> str:
        sid, token = settings.twilio_account_sid, settings.twilio_auth_token
        sender = settings.twilio_from_number
        if not (sid and token and sender):
            raise SmsSendError("SMS_PROVIDER=twilio needs TWILIO_ACCOUNT_SID, "
                               "TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER")
        data = {"To": to, "Body": body}
        if sender.startswith("MG"):
            data["MessagingServiceSid"] = sender
        else:
            data["From"] = sender
        try:
            with _http() as client:
                resp = client.post(self.URL.format(sid=sid), data=data, auth=(sid, token))
        except httpx.HTTPError as exc:
            raise SmsSendError(f"twilio transport error: {exc}") from exc
        if resp.status_code >= 400:
            try:
                detail = (resp.json() or {}).get("message") or resp.text[:200]
            except ValueError:
                detail = resp.text[:200]
            raise SmsSendError(f"twilio HTTP {resp.status_code}: {detail}")
        return str((resp.json() or {}).get("sid") or "")


class ConsoleProvider:
    name = "console"

    def send(self, to: str, body: str) -> str:
        # The code itself is NOT logged: dev logs get pasted into tickets.
        logger.warning("SMS_PROVIDER=console: an SMS to %s was NOT delivered (%d chars)",
                       mask_phone(to), len(body))
        return "console"


class MemoryProvider:
    name = "memory"

    def send(self, to: str, body: str) -> str:
        SENT_SMS.append({"to": to, "body": body})
        return f"memory-{len(SENT_SMS)}"


PROVIDERS = {cls.name: cls for cls in (TwilioProvider, ConsoleProvider, MemoryProvider)}


def send_sms(to: str, body: str) -> str:
    """Hand one SMS to the configured transport. Returns the provider id."""
    key = (settings.sms_provider or "").strip().lower()
    cls = PROVIDERS.get(key)
    if cls is None:
        raise SmsSendError(f"unknown SMS_PROVIDER {key!r}")
    return cls().send(to, body)

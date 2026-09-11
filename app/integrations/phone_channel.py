"""PhoneChannel — Feature Group 6's implementation of OutreachChannel.

send() places ONE AI call through Vapi, falling back to ElevenLabs'
Conversational AI when Vapi is not configured or refuses the call. "Sent"
means the call was placed; what happened on it arrives later on the
provider's webhook (app/api/calls.py).

It re-checks suppression at the last moment (like WhatsApp and LinkedIn),
because a number on the do-not-contact list must never ring.

OutboundMessage.metadata carries everything the provider needs:
    {"call_id", "system_prompt", "first_message", "voicemail_text",
     "customer_name", "server_url", "server_secret"}
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.exceptions import ComplianceError
from app.db.models import Lead
from app.integrations.outreach_base import (
    InboundMessage,
    OutboundMessage,
    OutreachChannel,
    SendResult,
    register_channel,
)
from app.integrations.voice_providers import VoiceProviderError


@register_channel
class PhoneChannel(OutreachChannel):
    channel = "phone"
    provider = "ai_voice"

    def __init__(self, session: Session, vapi=None, eleven=None):
        self.session = session
        self.vapi = vapi
        self.eleven = eleven

    def _guard(self, message: OutboundMessage) -> None:
        from app.workers.lead_tasks import is_suppressed  # noqa: PLC0415

        # OutboundMessage.lead_id is a STRING (the send path builds it with
        # str(lead.id)); the Uuid column needs a UUID on SQLite. PostgreSQL
        # accepts the string, which is how this class of bug hides -- see
        # app/workers/tasks.py::_pk.
        lead = self.session.get(Lead, uuid.UUID(str(message.lead_id))) \
            if message.lead_id else None
        if lead is not None and is_suppressed(self.session, lead.email, lead.phone,
                                              linkedin=lead.linkedin_url):
            raise ComplianceError("lead is suppressed", compliance_code="SUPPRESSED")

    def send(self, message: OutboundMessage) -> SendResult:
        meta = message.metadata or {}
        self._guard(message)
        kwargs = dict(to_number=message.to_address, customer_name=meta.get("customer_name"),
                      system_prompt=meta.get("system_prompt") or "",
                      first_message=meta.get("first_message") or message.body,
                      voicemail_message=meta.get("voicemail_text"),
                      server_url=meta.get("server_url") or "",
                      server_secret=meta.get("server_secret"),
                      metadata={"call_id": meta.get("call_id"), "lead_id": message.lead_id,
                                "message_id": message.message_id})
        errors = []
        for provider in (self.vapi, self.eleven):
            if provider is None or (provider is self.eleven and not getattr(provider, "can_call", False)):
                continue
            try:
                data = provider.create_call(**kwargs)
                return SendResult(ok=True, provider_message_id=data.get("id"),
                                  raw={"provider": provider.provider, **data})
            except VoiceProviderError as exc:
                errors.append(f"{provider.provider}: {exc}")
                if provider is self.vapi and self.eleven is not None and \
                        getattr(self.eleven, "can_call", False):
                    continue
                return SendResult(ok=False, error="; ".join(errors),
                                  permanent_failure=exc.permanent)
        return SendResult(ok=False, permanent_failure=True,
                          error="; ".join(errors) or "no voice provider configured")

    def fetch_replies(self, since: datetime | None = None) -> list[InboundMessage]:
        return []   # results arrive on the provider webhook

    def status(self, provider_message_id: str) -> dict:
        return {"provider_call_id": provider_message_id}

    def health_check(self) -> bool:
        return self.vapi is not None or (self.eleven is not None and self.eleven.can_call)

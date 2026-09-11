"""Vapi.ai (primary) and ElevenLabs (fallback + TTS) — Feature Group 6.

VAPI
  POST https://api.vapi.ai/call   an outbound call with a TRANSIENT assistant:
                                  the per-lead system prompt and first line,
                                  voicemail detection, the voicemail message,
                                  recording on, and our webhook as serverUrl
                                  (Vapi sends `x-vapi-secret` with it).
ELEVENLABS
  POST /v1/text-to-speech/{voice}  the personalised voicemail as audio
  POST /v1/convai/twilio/outbound-call   the calling FALLBACK, via a
                                  pre-configured Conversational AI agent whose
                                  prompt and first message are overridden per
                                  call

Credentials are system scope (Admin > Integrations): `vapi.api_key`,
`vapi.phone_number_id`, optional `vapi.webhook_secret`; `elevenlabs.api_key`,
`elevenlabs.voice_id`, optional `agent_id`, `agent_phone_number_id`,
`webhook_secret`. Payload fields not verified against current provider docs
carry `# TODO: verify` per the codebase's honesty rule.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

VAPI_BASE = "https://api.vapi.ai"
ELEVEN_BASE = "https://api.elevenlabs.io"


class VoiceProviderError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status

    @property
    def permanent(self) -> bool:
        return self.status is not None and 400 <= self.status < 500 and self.status != 429


def _http() -> httpx.Client:
    """Factory tests monkeypatch."""
    return httpx.Client(timeout=30.0)


def _check(resp, what: str) -> None:
    if resp.status_code >= 400:
        raise VoiceProviderError(f"{what}: HTTP {resp.status_code} {resp.text[:200]}",
                                 status=resp.status_code)


class VapiClient:
    provider = "vapi"

    def __init__(self, api_key: str, phone_number_id: str,
                 voice_id: str | None = None, model: str | None = None):
        self.api_key = api_key
        self.phone_number_id = phone_number_id
        self.voice_id = voice_id
        self.model = model

    def create_call(self, *, to_number: str, customer_name: str | None, system_prompt: str,
                    first_message: str, voicemail_message: str | None, server_url: str,
                    server_secret: str | None, metadata: dict) -> dict:
        """# TODO: verify against current Vapi docs (POST /call, assistant fields)"""
        assistant: dict = {
            "firstMessage": first_message,
            "model": {"provider": "anthropic", "model": self.model or "claude-sonnet-4-6",
                      "messages": [{"role": "system", "content": system_prompt}]},
            "voicemailDetection": {"provider": "twilio"},
            "recordingEnabled": True,
            "endCallFunctionEnabled": True,
            "serverUrl": server_url,
            "metadata": metadata,
        }
        if voicemail_message:
            assistant["voicemailMessage"] = voicemail_message
        if server_secret:
            assistant["serverUrlSecret"] = server_secret
        if self.voice_id:
            assistant["voice"] = {"provider": "11labs", "voiceId": self.voice_id}
        body = {"phoneNumberId": self.phone_number_id,
                "customer": {"number": to_number, "name": customer_name or ""},
                "assistant": assistant, "metadata": metadata}
        with _http() as client:
            resp = client.post(f"{VAPI_BASE}/call", json=body,
                               headers={"Authorization": f"Bearer {self.api_key}"})
        _check(resp, "vapi create call")
        data = resp.json() or {}
        return {"id": data.get("id"), "status": data.get("status") or "queued"}


class ElevenLabsClient:
    provider = "elevenlabs"

    def __init__(self, api_key: str, voice_id: str | None = None,
                 agent_id: str | None = None, agent_phone_number_id: str | None = None):
        self.api_key = api_key
        self.voice_id = voice_id
        self.agent_id = agent_id
        self.agent_phone_number_id = agent_phone_number_id

    @property
    def can_call(self) -> bool:
        return bool(self.agent_id and self.agent_phone_number_id)

    def tts(self, text: str) -> bytes:
        """# TODO: verify against current ElevenLabs docs (text-to-speech)"""
        if not self.voice_id:
            raise VoiceProviderError("no ElevenLabs voice_id configured")
        with _http() as client:
            resp = client.post(f"{ELEVEN_BASE}/v1/text-to-speech/{self.voice_id}",
                               json={"text": text, "model_id": "eleven_multilingual_v2"},
                               headers={"xi-api-key": self.api_key, "accept": "audio/mpeg"})
        _check(resp, "elevenlabs tts")
        return resp.content

    def create_call(self, *, to_number: str, customer_name: str | None, system_prompt: str,
                    first_message: str, voicemail_message: str | None, server_url: str,
                    server_secret: str | None, metadata: dict) -> dict:
        """# TODO: verify against current ElevenLabs docs (convai outbound call)"""
        if not self.can_call:
            raise VoiceProviderError("ElevenLabs agent_id / agent_phone_number_id not set")
        body = {
            "agent_id": self.agent_id,
            "agent_phone_number_id": self.agent_phone_number_id,
            "to_number": to_number,
            "conversation_initiation_client_data": {
                "conversation_config_override": {
                    "agent": {"first_message": first_message,
                              "prompt": {"prompt": system_prompt}}},
                "dynamic_variables": {k: str(v) for k, v in metadata.items()},
            },
        }
        with _http() as client:
            resp = client.post(f"{ELEVEN_BASE}/v1/convai/twilio/outbound-call", json=body,
                               headers={"xi-api-key": self.api_key})
        _check(resp, "elevenlabs outbound call")
        data = resp.json() or {}
        return {"id": data.get("conversation_id") or data.get("callSid"),
                "status": "queued"}


def get_clients(db, user_id=None) -> tuple[VapiClient | None, ElevenLabsClient | None]:
    """(vapi, elevenlabs), each None when not configured. Tests monkeypatch."""
    from app.config import settings  # noqa: PLC0415
    from app.services import credentials  # noqa: PLC0415

    def secret(provider, key):
        return credentials.get_secret(db, provider, key, user_id=user_id)

    eleven = None
    if secret("elevenlabs", "api_key"):
        eleven = ElevenLabsClient(secret("elevenlabs", "api_key"), secret("elevenlabs", "voice_id"),
                                  secret("elevenlabs", "agent_id"),
                                  secret("elevenlabs", "agent_phone_number_id"))
    vapi = None
    if secret("vapi", "api_key") and secret("vapi", "phone_number_id"):
        vapi = VapiClient(secret("vapi", "api_key"), secret("vapi", "phone_number_id"),
                          voice_id=eleven.voice_id if eleven else None,
                          model=settings.anthropic_model)
    return vapi, eleven

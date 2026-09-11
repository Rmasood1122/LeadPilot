"""OpenAI Chat Completions — the second model behind the consensus engine.

Deliberately small. It is used for exactly one thing (answering the same
research brief Claude answered, so the two can be compared), and it must never
be able to stop a strategy: every failure raises OpenAIError, which the
consensus layer records next to the step and moves past.

No SDK dependency: one POST, over httpx, which the project already depends on.
The key is a SYSTEM credential (Admin > Integrations > OpenAI), resolved
through app/services/credentials.py -- never an environment variable.
"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
_RETRYABLE = {429, 500, 502, 503, 504}


class OpenAIError(Exception):
    pass


class OpenAIClient:
    def __init__(self, api_key: str, model: str = "gpt-4o",
                 http: httpx.Client | None = None, max_retries: int = 3,
                 sleep=time.sleep):
        self.api_key = api_key
        self.model = model
        self.http = http or httpx.Client(timeout=180.0)
        self.max_retries = max_retries
        self._sleep = sleep

    def complete(self, system: str, prompt: str, max_tokens: int = 4096) -> str:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.4,
        }
        last = "no attempt made"
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.http.post(
                    OPENAI_CHAT_URL, json=body,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            except httpx.HTTPError as exc:
                last = f"{type(exc).__name__}: {exc}"
            else:
                if resp.status_code in _RETRYABLE:
                    last = f"HTTP {resp.status_code}"
                elif resp.status_code >= 400:
                    raise OpenAIError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                else:
                    data = resp.json()
                    usage = data.get("usage") or {}
                    from app.services import usage_meter  # noqa: PLC0415

                    usage_meter.note("openai", self.model, usage.get("prompt_tokens") or 0,
                                     usage.get("completion_tokens") or 0)
                    choice = (data.get("choices") or [{}])[0]
                    if choice.get("finish_reason") == "length":
                        # Same rule as anthropic_client.TruncatedResponseError:
                        # an answer with its end cut off is not an answer.
                        raise OpenAIError("response truncated at max_tokens")
                    text = ((choice.get("message") or {}).get("content") or "").strip()
                    if not text:
                        raise OpenAIError("empty response")
                    return text
            if attempt < self.max_retries:
                self._sleep(min(2 ** attempt, 30))
        raise OpenAIError(f"failed after {self.max_retries} attempts ({last})")


def get_openai_client(db) -> OpenAIClient | None:
    """A configured client, or None when no key is set. Tests monkeypatch."""
    from app.services import credentials, system_settings  # noqa: PLC0415

    key = credentials.get_secret(db, "openai", "api_key")
    if not key:
        return None
    return OpenAIClient(api_key=key,
                        model=system_settings.get(db, "consensus_openai_model"))

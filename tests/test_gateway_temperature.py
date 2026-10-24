"""Temperature on models that reject it (I4, Phase 3).

A judge call asks for temperature 0 (F-AI-03). Claude 4.7+ and the 5.x
family reject a non-default temperature with HTTP 400, so sending it would
make every judge call -- reply routing, the verification judge, claim
extraction -- fail on those models. The gateway omits it there and keeps
sending it to every model that accepts it, including the current default.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import settings
from app.services import anthropic_client


class _Messages:
    def __init__(self):
        self.sent: list[dict] = []

    def create(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="ok")],
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                               stop_reason="end_turn")


def _sent(monkeypatch, model: str, temperature) -> dict:
    monkeypatch.setattr(settings, "anthropic_model", model)
    client = anthropic_client.ClaudeClient.__new__(anthropic_client.ClaudeClient)
    client._client = SimpleNamespace(messages=_Messages())
    client.complete(system="s", prompt="p", temperature=temperature)
    request = client._client.messages.sent[0]
    return {**request, **(request.get("extra_body") or {})}


@pytest.mark.parametrize("model", ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5",
                                   "claude-sonnet-4-6-20260101"])
def test_a_judge_stays_pinned_to_zero_where_the_model_accepts_it(monkeypatch, model):
    assert _sent(monkeypatch, model, anthropic_client.JUDGE_TEMPERATURE)["temperature"] == 0.0


@pytest.mark.parametrize("model", ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5",
                                   "claude-opus-5", "claude-opus-4-8", "claude-opus-4-7",
                                   "claude-sonnet-5", "claude-fable-5-1", "claude-fable-5"])
def test_a_model_that_rejects_temperature_never_receives_it(monkeypatch, model):
    assert "temperature" not in _sent(monkeypatch, model, anthropic_client.JUDGE_TEMPERATURE)


def test_no_temperature_asked_none_sent(monkeypatch):
    assert "temperature" not in _sent(monkeypatch, "claude-sonnet-4-6", None)

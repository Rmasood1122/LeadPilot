"""ClaudeClient.complete_json returns a JSON object or raises ValueError.

Every caller reads the reply with .get(). An array, a bare string or `null`
used to come back unchanged and raise AttributeError at that .get(), outside
the caller's own try in icp_extraction, pattern_recognition and
adversarial_review (Phase 2 evals T28, T29, T34). Driven through the real
gateway class with only the SDK's messages resource faked.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import anthropic_client


class _Messages:
    def __init__(self, text: str):
        self.text = text

    def create(self, **kwargs):
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.text)],
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5),
                               stop_reason="end_turn")


def _client(reply: str) -> anthropic_client.ClaudeClient:
    client = anthropic_client.ClaudeClient.__new__(anthropic_client.ClaudeClient)
    client._client = SimpleNamespace(messages=_Messages(reply))
    return client


@pytest.mark.parametrize("reply", ['{"label": "interested"}',
                                   '```json\n{"label": "interested"}\n```',
                                   'Here you go: {"label": "interested"} hope it helps'])
def test_an_object_comes_back(reply):
    assert _client(reply).complete_json(system="s", prompt="p") == {"label": "interested"}


@pytest.mark.parametrize("reply", ['[{"label": "interested"}]', "[]", "null",
                                   '"interested"', "42", "true"])
def test_any_other_json_is_a_value_error(reply):
    with pytest.raises(ValueError, match="not an object"):
        _client(reply).complete_json(system="s", prompt="p")


def test_unparseable_text_is_still_a_value_error():
    with pytest.raises(ValueError, match="valid JSON"):
        _client("I can't help with that.").complete_json(system="s", prompt="p")

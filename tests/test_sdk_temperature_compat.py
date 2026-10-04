"""A judge's temperature must reach the API even when the SDK has no keyword for it.

Seen live on 2026-10-05: the installed anthropic SDK's Messages.create() no
longer takes `temperature`, so every verification pass raised TypeError and a
fully paid research run ended FAILED. The value is sent via extra_body instead
of being dropped, because dropping it would make the legal-compliance judge
non-deterministic again (F-AI-03). Offline: stub SDKs only.
"""

from types import SimpleNamespace

from app.services import anthropic_client


def _client(messages):
    client = anthropic_client.ClaudeClient.__new__(anthropic_client.ClaudeClient)
    client._client = SimpleNamespace(messages=messages)
    return client


def _resp():
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text="ok")], stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1))


class NewSdkMessages:
    """Signature like the current SDK: no `temperature`, no **kwargs."""

    def __init__(self):
        self.seen = None

    def create(self, *, max_tokens, messages, model, system=None,
               extra_body=None, extra_headers=None):
        self.seen = dict(max_tokens=max_tokens, extra_body=extra_body)
        return _resp()


class OldSdkMessages:
    def __init__(self):
        self.seen = None

    def create(self, *, max_tokens, messages, model, system=None, temperature=None):
        self.seen = dict(temperature=temperature)
        return _resp()


def test_new_sdk_gets_temperature_in_the_body_not_as_a_keyword():
    m = NewSdkMessages()
    _client(m).complete("s", "p", temperature=0.0)  # TypeError before the fix
    assert m.seen["extra_body"] == {"temperature": 0.0}


def test_old_sdk_still_gets_the_keyword():
    m = OldSdkMessages()
    _client(m).complete("s", "p", temperature=0.0)
    assert m.seen["temperature"] == 0.0


def test_no_temperature_is_sent_when_not_asked():
    m = NewSdkMessages()
    _client(m).complete("s", "p")
    assert m.seen["extra_body"] is None

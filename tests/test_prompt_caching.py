"""Prompt caching through the gateway (Phase 3 item 3).

The gateway can mark a stable prefix with a cache breakpoint, and the usage
meter is fed what a cached call actually costs. The API reports cache writes
and reads apart from input_tokens; metering input_tokens alone would
under-count every cached call and let the spend caps (F-AI-01, P0-5, F07)
run past their limit.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import settings
from app.services import anthropic_client, usage_meter


class _Messages:
    def __init__(self, usage):
        self.sent: list[dict] = []
        self.usage = usage

    def create(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="ok")],
                               usage=self.usage, stop_reason="end_turn")


def _client(usage=None):
    usage = usage or SimpleNamespace(input_tokens=10, output_tokens=5)
    client = anthropic_client.ClaudeClient.__new__(anthropic_client.ClaudeClient)
    client._client = SimpleNamespace(messages=_Messages(usage))
    return client


def test_a_prefix_becomes_a_cached_first_block():
    client = _client()
    client.complete(system="S", prompt="the question", cache_prefix="the shared document")
    content = client._client.messages.sent[0]["messages"][0]["content"]
    assert content == [
        {"type": "text", "text": "the shared document", "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "the question"}]


def test_without_a_prefix_the_request_is_unchanged():
    client = _client()
    client.complete(system="S", prompt="the question")
    assert client._client.messages.sent[0]["messages"] == [
        {"role": "user", "content": "the question"}]


@pytest.mark.parametrize("model,write,read,expected", [
    ("claude-sonnet-4-6", 1000, 0, 100 + 1250),        # a write costs 1.25x
    ("claude-sonnet-4-6", 0, 1000, 100 + 100),         # a read costs 0.1x
    ("claude-opus-5-5", 0, 1000, 100 + 50),            # 0.05x on Opus 5.5
    ("claude-fable-5-1", 0, 1000, 100 + 25),           # 0.025x on Fable 5.1
    ("claude-sonnet-4-6-20260101", 1000, 1000, 100 + 1250 + 100),
])
def test_billed_input_tokens(model, write, read, expected):
    assert anthropic_client.billed_input_tokens(model, 100, write, read) == expected


def test_the_meter_is_charged_for_cache_writes_and_reads(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_model", "claude-sonnet-4-6")
    noted: list[tuple] = []
    monkeypatch.setattr(usage_meter, "note", lambda *a: noted.append(a))
    usage = SimpleNamespace(input_tokens=100, output_tokens=7,
                            cache_creation_input_tokens=2000, cache_read_input_tokens=3000)
    _client(usage).complete(system="S", prompt="q", cache_prefix="doc")
    assert noted == [("anthropic", "claude-sonnet-4-6", 100 + 2500 + 300, 7)]


def test_the_budget_check_prices_the_prefix_as_a_cache_write(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(usage_meter, "check_budget",
                        lambda **kw: seen.update(kw))
    _client().complete(system="SS", prompt="qqq", cache_prefix="d" * 1000, max_tokens=50)
    assert seen["input_chars"] == 2 + 3 + 1250
    assert seen["max_output_tokens"] == 50


def test_complete_json_passes_the_prefix_through():
    client = _client(SimpleNamespace(input_tokens=1, output_tokens=1))
    client._client.messages.create = lambda **kw: (
        client._client.messages.sent.append(kw)
        or SimpleNamespace(content=[SimpleNamespace(type="text", text='{"a": 1}')],
                           usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                           stop_reason="end_turn"))
    assert client.complete_json(system="S", prompt="q", cache_prefix="doc") == {"a": 1}
    assert client._client.messages.sent[0]["messages"][0]["content"][0]["text"] == "doc"


# --- the verification loop: ten passes over one document ------------------

class _Recorder:
    def __init__(self):
        self.calls: list[dict] = []

    def complete_json(self, **kw):
        self.calls.append(kw)
        return {"result": "PASS"}


@pytest.mark.parametrize("flow", ["WITH_CLIENTS", "NO_CLIENTS"])
def test_every_judge_pass_reads_the_same_cached_prefix(monkeypatch, flow):
    """The cache only hits when the prefix is byte-identical. Every pass over
    an unchanged document must send the same prefix -- the document and the
    research -- with its own criterion only after it."""
    from app.db.models import FlowType
    from app.verification import loop as vloop
    from app.verification.passes import build_passes

    recorder = _Recorder()
    monkeypatch.setattr(vloop, "get_client", lambda: recorder)

    class _Strategy:
        strategy_document = "# Strategy\n" + "A long section about pricing. " * 400

    specs = build_passes(getattr(FlowType, flow))
    for spec in specs:
        vloop._judge(spec, _Strategy(), "--- research ---\n" + "finding " * 800)

    prefixes = {call["cache_prefix"] for call in recorder.calls}
    assert len(recorder.calls) == len(specs) >= 9
    assert len(prefixes) == 1, "a pass changed the cached prefix: every pass would miss"
    prefix = prefixes.pop()
    assert "A long section about pricing" in prefix and "finding finding" in prefix
    for spec, call in zip(specs, recorder.calls):
        assert spec.criterion not in prefix and f"#{spec.pass_no}" not in prefix
        assert spec.criterion in call["prompt"]


def test_the_fixer_retry_reads_the_document_from_the_cache(monkeypatch):
    """A rewrite that hits the output ceiling is retried once at a higher
    one; both calls carry the same document prefix, so the retry reads it."""
    from app.services.anthropic_client import TruncatedResponseError
    from app.verification import loop as vloop
    from app.verification.passes import build_passes
    from app.db.models import FlowType

    calls: list[dict] = []

    class _Fixer:
        def complete(self, **kw):
            calls.append(kw)
            if len(calls) == 1:
                raise TruncatedResponseError("cut", limit=kw["max_tokens"])
            return "# Strategy\nrevised"

    monkeypatch.setattr(vloop, "get_client", lambda: _Fixer())

    class _Strategy:
        strategy_document = "# Strategy\noriginal"

    spec = build_passes(FlowType.WITH_CLIENTS)[0]
    vloop._generate_fix(spec, _Strategy(), "tighten the pricing")
    assert len(calls) == 2 and calls[0]["cache_prefix"] == calls[1]["cache_prefix"]
    assert "original" in calls[0]["cache_prefix"]
    assert "tighten the pricing" in calls[0]["prompt"]


# --- the research pipeline: nine steps per phase -------------------------

def test_steps_of_a_phase_share_one_cached_prefix(db_session, verified_strategy, fake_claude,
                                                  monkeypatch):
    """Every step of a phase must send the same prefix (product, patterns,
    earlier phases' syntheses, the phase's live inputs) for steps 2-9 to read
    it from the cache; the next phase's prefix adds the new synthesis."""
    from app.pipeline import engine

    prefixes: list[str] = []
    prompts: list[str] = []
    original = fake_claude.complete

    def complete(system, prompt, **kw):
        prefixes.append(kw.get("cache_prefix") or "")
        prompts.append(prompt)
        return original(system, prompt, **kw)

    monkeypatch.setattr(fake_claude, "complete", complete)
    for _ in range(18):
        engine.run_step(db_session, verified_strategy,
                        engine.next_step(db_session, verified_strategy))

    phase_1, phase_2 = set(prefixes[:9]), set(prefixes[9:18])
    assert len(phase_1) == 1 and len(phase_2) == 1, "a step changed its phase's prefix"
    assert phase_1 != phase_2
    assert prefixes[9].startswith(prefixes[0].split("RELEVANT PRIOR RESEARCH")[0])
    assert "[Phase 1 / Step 9:" in prefixes[9]            # phase 1's synthesis, cached
    assert "[Phase 2 / Step 10:" in prompts[10]           # this phase so far, after it
    for prefix in set(prefixes):
        assert "CURRENT STEP" not in prefix and "STEP GUIDANCE" not in prefix

"""F-AI-03 — a call that returns a VERDICT must be deterministic.

Verification pass #4 is "Legal & compliance", a documented hard ship-blocker.
Run at the API default (~1.0) the same document can be judged PASS on one run
and FAIL on the next, which makes the blocker advisory rather than binding.
The reply classifiers have the same property and their output drives
suppression and stop logic, so they are held to the same rule.

The opposite case matters just as much and is asserted here too: generation
must NOT be pinned to 0. Outreach copy, document rewrites and A/B variants all
run through the same two client methods, and forcing temperature=0 there would
make every lead receive byte-identical text and collapse variant generation.

These tests assert the temperature actually reaching the client, not that a
particular constant exists -- a judge wired up without the argument fails here.
"""

from __future__ import annotations

import pytest

from app.services import anthropic_client


class RecordingClient:
    """Stands in for ClaudeClient and records how each call was made."""

    def __init__(self, payload: dict | None = None, text: str = "revised document"):
        self.payload = payload if payload is not None else {"result": "PASS"}
        self.text = text
        self.calls: list[dict] = []

    def complete_json(self, system=None, prompt=None, max_tokens=None,
                      temperature=None, schema=None) -> dict:
        self.calls.append({"kind": "json", "system": system, "prompt": prompt,
                           "max_tokens": max_tokens, "temperature": temperature})
        return dict(self.payload)

    def complete(self, system=None, prompt=None, max_tokens=None,
                 temperature=None) -> str:
        self.calls.append({"kind": "text", "system": system, "prompt": prompt,
                           "max_tokens": max_tokens, "temperature": temperature})
        return self.text

    @property
    def only(self) -> dict:
        assert len(self.calls) == 1, f"expected exactly one call, got {len(self.calls)}"
        return self.calls[0]


def test_judge_temperature_is_zero() -> None:
    """The constant the judges share is pinned to 0, not merely 'low'."""
    assert anthropic_client.JUDGE_TEMPERATURE == 0.0


def test_client_omits_temperature_when_not_asked() -> None:
    """Absent a caller's choice, no temperature is sent and the API default stands.

    Asserted on the request dict so a regression that hardcodes a temperature
    for every call -- the change that would silently break generation -- fails
    here rather than in production copy.
    """
    sent: dict = {}

    class FakeMessages:
        def create(self, **kwargs):
            sent.update(kwargs)
            return _FakeResponse()

    class FakeSDK:
        def __init__(self):
            self.messages = FakeMessages()

    client = anthropic_client.ClaudeClient.__new__(anthropic_client.ClaudeClient)
    client._client = FakeSDK()

    client.complete(system="s", prompt="p", max_tokens=16)
    assert "temperature" not in sent

    sent.clear()
    client.complete(system="s", prompt="p", max_tokens=16, temperature=0.0)
    assert sent["temperature"] == 0.0


class _FakeResponse:
    class _Usage:
        input_tokens = 1
        output_tokens = 1

    class _Block:
        type = "text"
        text = "{}"

    content = [_Block()]
    usage = _Usage()
    stop_reason = "end_turn"


# --- the verification judge: this is the legal-compliance ship-blocker -------

def test_verification_judge_runs_at_zero(monkeypatch) -> None:
    from app.verification import loop as vloop
    from app.verification.passes import build_passes
    from app.db.models import FlowType

    recorder = RecordingClient({"result": "PASS", "fix_description": None})
    monkeypatch.setattr(vloop, "get_client", lambda: recorder)

    spec = next(s for s in build_passes(FlowType.WITH_CLIENTS)
                if s.key == "legal_compliance")

    class _Strategy:
        strategy_document = "a document"

    passed, _ = vloop._judge(spec, _Strategy(), "support")

    assert passed is True
    assert recorder.only["temperature"] == 0.0, (
        "the legal-compliance judge ran at the API default; its PASS/FAIL "
        "verdict is therefore not reproducible"
    )


def test_document_fixer_is_not_pinned_to_zero(monkeypatch) -> None:
    """The fixer REWRITES prose. Pinning it to 0 is the wrong trade."""
    from app.verification import loop as vloop

    recorder = RecordingClient(text="a revised document")
    monkeypatch.setattr(vloop, "get_client", lambda: recorder)

    class _Strategy:
        strategy_document = "a document"

    class _Spec:
        pass_no = 4
        key = "legal_compliance"
        name = "Legal & compliance"

    vloop._generate_fix(_Spec(), _Strategy(), "fix this")

    assert recorder.only["temperature"] is None


# --- the reply classifiers: their output drives suppression and stop --------

@pytest.mark.parametrize(
    ("module_path", "attr"),
    [
        ("app.services.reply_classification", "get_client"),
        ("app.services.reply_intent", "get_client"),
        ("app.services.reply_intelligence", "get_client"),
    ],
)
def test_reply_modules_import_the_judge_constant(module_path, attr) -> None:
    """Each classifier module reaches the shared constant, so one change moves all."""
    import importlib

    module = importlib.import_module(module_path)
    assert getattr(module, "JUDGE_TEMPERATURE") == 0.0
    assert hasattr(module, attr)


def test_reply_classification_runs_at_zero(monkeypatch) -> None:
    """_classify is the call whose verdict stops a sequence or suppresses a lead."""
    from app.services import reply_classification as rc

    recorder = RecordingClient({"classification": "question"})
    monkeypatch.setattr(rc, "get_client", lambda: recorder)

    result = rc._classify("a@b.c", "a subject", "a body")

    assert result == "question"
    assert recorder.only["temperature"] == 0.0, (
        "the reply classifier ran at the API default; the same reply could be "
        "classified differently run to run, and that verdict drives suppression"
    )


def test_reply_fraud_detector_runs_at_zero(monkeypatch) -> None:
    """The detector only reaches the model on exactly ONE weak signal.

    A strong signal (sender or subject) or two weak ones are decided by rule
    without a model call, so the body below carries exactly one weak match --
    otherwise this test would assert nothing.
    """
    from app.services import reply_fraud

    recorder = RecordingClient({"automated": False})
    monkeypatch.setattr(
        "app.services.anthropic_client.get_client", lambda: recorder)

    body = "Thank you for contacting us about the proposal."
    assert len(reply_fraud.signals("a@b.c", "Re: proposal", body)) == 1, (
        "fixture drifted: this body no longer produces exactly one weak signal"
    )

    reply_fraud.is_automated("a@b.c", "Re: proposal", body, use_model=True)

    assert recorder.calls, "the detector never reached the model"
    assert all(c["temperature"] == 0.0 for c in recorder.calls)

"""The live AI-eval runner's money and safety rules (evals/ai/live_eval.py).

Offline: the Anthropic SDK is replaced by a fake, so nothing is sent and
nothing is spent. What is proven here is that the runner refuses to start
when it should, meters every call, stops before crossing its budget, goes
through the real gateway class, and writes the spend ledger.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from evals.ai import live_eval as le

PRICE = {"input_per_mtok": 3.0, "output_per_mtok": 15.0}


class FakeMessages:
    def __init__(self, reply='{"automated": false}', tokens=(1000, 100)):
        self.sent: list[dict] = []
        self.reply, self.tokens = reply, tokens

    def create(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.reply)],
                               usage=SimpleNamespace(input_tokens=self.tokens[0],
                                                     output_tokens=self.tokens[1]),
                               stop_reason="end_turn")


class FakeAnthropic:
    instances: list["FakeAnthropic"] = []
    messages_factory = FakeMessages

    def __init__(self, api_key=None, base_url=None):
        self.api_key, self.base_url = api_key, base_url
        self.messages = FakeAnthropic.messages_factory()
        FakeAnthropic.instances.append(self)


@pytest.fixture
def fake_sdk(monkeypatch):
    import anthropic

    FakeAnthropic.instances = []
    FakeAnthropic.messages_factory = FakeMessages
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    return FakeAnthropic


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    path = tmp_path / "eval-state.json"
    path.write_text(json.dumps({"live": {"spent_usd": 0.0, "runs": []}}))
    monkeypatch.setattr(le, "STATE_PATH", path)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return path


def _args(**kw):
    base = dict(model="claude-sonnet-4-6", k=1, max_usd=10.0, touchpoints=["T07"],
                out="", dry_run=False)
    base.update(kw)
    return SimpleNamespace(**base)


class TestRefusals:
    def test_refuses_in_ci(self, ledger, monkeypatch):
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        with pytest.raises(le.Refused, match="CI"):
            le.run(_args(dry_run=True))

    def test_refuses_an_unpriced_model(self, ledger):
        with pytest.raises(le.Refused, match="no price"):
            le.run(_args(model="claude-haiku-4-5", dry_run=True))

    def test_refuses_a_run_over_the_per_run_ceiling(self, ledger):
        with pytest.raises(le.Refused, match="max-usd"):
            le.run(_args(max_usd=le.PER_RUN_CEILING_USD + 1, dry_run=True))

    def test_refuses_when_the_program_ledger_has_no_room(self, ledger):
        ledger.write_text(json.dumps({"live": {"spent_usd": le.PROGRAM_CEILING_USD - 5}}))
        with pytest.raises(le.Refused, match="ceiling"):
            le.run(_args(max_usd=10, dry_run=True))

    def test_refuses_without_a_ledger(self, ledger):
        ledger.unlink()
        with pytest.raises(le.Refused, match="ledger"):
            le.run(_args(dry_run=True))

    def test_refuses_when_the_worst_case_is_over_the_limit(self, ledger):
        with pytest.raises(le.Refused, match="worst-case"):
            le.run(_args(max_usd=0.0001))

    def test_refuses_without_the_eval_key_and_sends_nothing(self, ledger, fake_sdk, monkeypatch):
        monkeypatch.delenv("EVAL_ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-not-for-evals")
        with pytest.raises(le.Refused, match="EVAL_ANTHROPIC_API_KEY"):
            le.run(_args())
        assert fake_sdk.instances == []

    def test_dry_run_sends_nothing(self, ledger, fake_sdk):
        assert le.run(_args(dry_run=True)) == 0
        assert fake_sdk.instances == []


class TestLiveClient:
    def test_goes_to_the_public_api_on_the_eval_key(self, fake_sdk, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://proxy.example.invalid")
        le.make_live_client("sk-eval", PRICE, le.Budget(1.0))
        assert fake_sdk.instances[0].api_key == "sk-eval"
        assert fake_sdk.instances[0].base_url == le.API_BASE_URL

    def test_meters_the_real_usage_and_keeps_the_prompt(self, fake_sdk):
        budget = le.Budget(1.0)
        client = le.make_live_client("sk-eval", PRICE, budget)
        client.complete(system="S", prompt="P", max_tokens=200)
        expected = (1000 * 3.0 + 100 * 15.0) / 1e6
        assert client.cost_usd == pytest.approx(expected)
        assert budget.spent == pytest.approx(expected)
        assert client.calls[0]["prompt"] == "P"

    def test_temperature_reaches_the_request_unchanged(self, fake_sdk):
        client = le.make_live_client("sk-eval", PRICE, le.Budget(1.0))
        client.complete(system="S", prompt="P", max_tokens=50, temperature=0)
        assert fake_sdk.instances[0].messages._inner.sent[0]["temperature"] == 0

    def test_stops_before_a_call_that_could_cross_the_budget(self, fake_sdk):
        # worst case for 8000 output tokens at $15/M is $0.12 > $0.05
        budget = le.Budget(0.05)
        client = le.make_live_client("sk-eval", PRICE, budget)
        with pytest.raises(le.BudgetExhausted):
            client.complete(system="S", prompt="P", max_tokens=8000)
        assert fake_sdk.instances[0].messages._inner.sent == []
        assert budget.exhausted
        with pytest.raises(le.BudgetExhausted):  # sticky: no later call either
            client.complete(system="S", prompt="P", max_tokens=1)


class TestRun:
    def test_end_to_end_writes_the_report_and_the_ledger(self, ledger, fake_sdk, tmp_path,
                                                         monkeypatch):
        monkeypatch.setenv("EVAL_ANTHROPIC_API_KEY", "sk-eval")
        out = tmp_path / "report.json"
        le.run(_args(out=str(out)))
        report = json.loads(out.read_text())
        assert report["model"] == "claude-sonnet-4-6"
        assert "T07" in report["summary"]
        assert report["spent_usd"] > 0
        state = json.loads(ledger.read_text())
        assert state["live"]["spent_usd"] == pytest.approx(report["spent_usd"])
        assert state["live"]["runs"][0]["report"] == str(out)
        sent = [m for inst in fake_sdk.instances for m in inst.messages._inner.sent]
        assert sent and all(m["model"] == "claude-sonnet-4-6" for m in sent)

    def test_offline_only_cases_are_not_run_live(self):
        from evals.ai import framework as fw

        pairs = le.live_cases(fw.load_all(), None)
        assert pairs and not any(c.offline_only for _s, c in pairs)

    def test_live_ignore_keys_are_dropped_for_live_grading(self):
        from evals.ai import framework as fw

        spec = fw.Spec("T99", "t", "x", "internal", [], [], [
            fw.Case("c", "normal", True, {}, {"include": ["recorded words"], "label": "a"})],
            live_ignore=["include"])
        [(_s, case)] = le.live_cases([spec], None)
        assert case.expect == {"label": "a"}
        assert spec.cases[0].expect["include"] == ["recorded words"]  # offline keeps it


class TestSandbox:
    """The live runner's environment (evals/ai/sandbox.py). Run in a
    subprocess: this process was already configured by tests/conftest.py."""

    def _run(self, code: str, env_extra: dict) -> str:
        import os
        import subprocess
        import sys
        from pathlib import Path

        env = {**os.environ, **env_extra}
        root = Path(__file__).resolve().parents[1]
        out = subprocess.run([sys.executable, "-c", code], cwd=root, env=env,
                             capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stderr[-2000:]
        return out.stdout.strip()

    def test_production_values_in_the_shell_are_overridden(self):
        prod = {"REDIS_URL": "rediss://prod.example.invalid:6379",
                "CELERY_BROKER_URL": "rediss://prod.example.invalid:6379",
                "DATABASE_URL": "postgresql://prod.example.invalid/db",
                "EMAIL_PROVIDER": "resend", "SMS_PROVIDER": "twilio",
                "ENCRYPTION_KEY": "prod-key"}
        code = ("import json, os; from evals.ai import sandbox; sandbox.apply(); "
                "from app.config import settings; "
                "print(json.dumps([os.environ[k] for k in "
                f"{sorted(prod)!r}] + [settings.redis_url]))")
        values = json.loads(self._run(code, prod))
        assert not any("prod" in v or v in ("resend", "twilio") for v in values), values

    def test_refuses_once_settings_are_loaded(self):
        code = ("from app.config import settings; from evals.ai import sandbox\n"
                "try:\n    sandbox.apply()\nexcept RuntimeError:\n    print('refused')")
        assert self._run(code, {}) == "refused"


def test_case_level_live_ignore_adds_to_the_sets():
    from evals.ai import framework as fw

    spec = fw.Spec("T99", "t", "x", "internal", [], [], [
        fw.Case("c", "normal", True, {}, {"include": ["x"], "label": 1, "forbidden": ["y"]},
                live_ignore=["label"])], live_ignore=["include"])
    [(_s, case)] = le.live_cases([spec], None)
    assert case.expect == {"forbidden": ["y"]}


def test_cache_tokens_are_charged_and_counted(fake_sdk, monkeypatch):
    """Phase 3 item 3: a cached call's writes (1.25x) and reads (0.1x) are
    priced into the run's spend, and counted for the report's hit rate."""
    from app.config import settings

    monkeypatch.setattr(settings, "anthropic_model", "claude-sonnet-4-6")

    class CachedMessages(FakeMessages):
        def create(self, **kwargs):
            resp = super().create(**kwargs)
            resp.usage.cache_creation_input_tokens = 2000
            resp.usage.cache_read_input_tokens = 3000
            return resp

    fake_sdk.messages_factory = CachedMessages
    budget = le.Budget(1.0)
    client = le.make_live_client("sk-eval", PRICE, budget)
    client.complete(system="S", prompt="P", max_tokens=200, cache_prefix="shared doc")
    billed_in = 1000 + 1.25 * 2000 + 0.1 * 3000
    assert budget.spent == pytest.approx((billed_in * 3.0 + 100 * 15.0) / 1e6)
    assert budget.tokens == {"input": 1000, "cache_write": 2000, "cache_read": 3000}
    assert client.calls[0]["prompt"] == "shared docP"

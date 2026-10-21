"""AI evals, live mode: the golden sets against a real model (opt-in).

Offline mode (tests/test_ai_evals.py) replays recorded outputs and proves the
plumbing. This runs the same cases through the same adapters, with every
get_client() pointed at the real gateway class (app.services.anthropic_client
.ClaudeClient) on a chosen model, k times each, and reports per touchpoint and
slice: pass@1, pass^k, cost and p50/p95 latency.

It spends money, so it refuses to start unless every one of these holds:

  * not in CI (CI / GITHUB_ACTIONS unset) -- the hard gate stays offline;
  * EVAL_ANTHROPIC_API_KEY is set. It is deliberately not ANTHROPIC_API_KEY,
    so an app or tool key is never spent by accident. Requests go to
    https://api.anthropic.com, whatever ANTHROPIC_BASE_URL says;
  * the model has a price in model_prices.json;
  * the worst-case estimate (every call's prompt plus its full max_tokens)
    fits under --max-usd, which itself may not exceed the per-run ceiling;
  * the program ledger (docs/program/ai/eval-state.json) has room for
    --max-usd under the program ceiling.

During the run every call is checked against the remaining per-run budget
before it is sent; the run stops (and still writes what it has) the moment the
next call could cross it. Spend is added to the ledger at the end.

Usage:
  python3 -m evals.ai.live_eval --model claude-sonnet-4-6 --dry-run
  EVAL_ANTHROPIC_API_KEY=... python3 -m evals.ai.live_eval --model claude-sonnet-4-6 \
      --k 3 --max-usd 120 --out docs/program/ai/live/2026-10-21-sonnet-4-6.json
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.ai import framework as fw
from evals.ai import graders as gr

ROOT = Path(__file__).resolve().parents[2]
PRICES_PATH = Path(__file__).with_name("model_prices.json")
STATE_PATH = ROOT / "docs" / "program" / "ai" / "eval-state.json"

# Founder decisions (docs/program/DECISIONS.md, VIC spend ceiling).
PER_RUN_CEILING_USD = 250.0
PROGRAM_CEILING_USD = 1100.0
API_BASE_URL = "https://api.anthropic.com"
# Upper bound on tokens per prompt character. Real English runs ~4 chars per
# token; 3 over-counts on purpose, so the estimate is a ceiling, not a guess.
CHARS_PER_TOKEN = 3.0


class Refused(SystemExit):
    """A precondition failed; nothing was spent."""

    def __init__(self, reason: str):
        super().__init__(f"live_eval refused: {reason}")


class BudgetExhausted(RuntimeError):
    """The next call could cross the per-run budget; the run stops here."""


# --- prices and budget ----------------------------------------------------

def load_prices(path: Path = PRICES_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["models"]


def worst_case_usd(price: dict, prompt_chars: int, max_tokens: int) -> float:
    tokens_in = prompt_chars / CHARS_PER_TOKEN
    return (tokens_in * price["input_per_mtok"] + max_tokens * price["output_per_mtok"]) / 1e6


def actual_usd(price: dict, tokens_in: int, tokens_out: int) -> float:
    return (tokens_in * price["input_per_mtok"] + tokens_out * price["output_per_mtok"]) / 1e6


class Budget:
    """Per-run money. `exhausted` is sticky and is what the run loop checks:
    app code that swallows every exception (several touchpoints fail soft by
    design) would otherwise hide the BudgetExhausted raised inside a call."""

    def __init__(self, limit_usd: float):
        self.limit = limit_usd
        self.spent = 0.0
        self.exhausted = ""

    def admit(self, worst_usd: float) -> None:
        if self.exhausted or self.spent + worst_usd > self.limit:
            self.exhausted = self.exhausted or (
                f"spent ${self.spent:.4f}; the next call could cost up to "
                f"${worst_usd:.4f}; per-run limit ${self.limit:.2f}")
            raise BudgetExhausted(self.exhausted)

    def charge(self, usd: float) -> None:
        self.spent += usd


# --- the live client: the real gateway, metered ---------------------------

class _MeteredMessages:
    """Wraps the SDK's `messages` resource: checks the budget before each
    request and charges the real usage after it. Takes **kwargs, so the
    gateway's temperature check (anthropic_client._accepts_temperature)
    passes `temperature` through unchanged -- a model that rejects it fails
    here exactly as it would in production."""

    def __init__(self, inner, price: dict, budget: Budget, owner: Any):
        self._inner, self._price, self._budget, self._owner = inner, price, budget, owner

    def _admit(self, kwargs: dict) -> None:
        chars = len(str(kwargs.get("system") or "")) + sum(
            len(str(m.get("content") or "")) for m in kwargs.get("messages") or [])
        self._budget.admit(worst_case_usd(self._price, chars, int(kwargs.get("max_tokens") or 0)))

    def _charge(self, resp) -> Any:
        usage = getattr(resp, "usage", None)
        usd = actual_usd(self._price, int(getattr(usage, "input_tokens", 0) or 0),
                         int(getattr(usage, "output_tokens", 0) or 0))
        self._budget.charge(usd)
        self._owner.cost_usd += usd
        return resp

    def create(self, **kwargs):
        self._admit(kwargs)
        return self._charge(self._inner.create(**kwargs))

    @contextlib.contextmanager
    def stream(self, **kwargs):
        self._admit(kwargs)
        with self._inner.stream(**kwargs) as s:
            yield _MeteredStream(s, self)


class _MeteredStream:
    def __init__(self, inner, meter: _MeteredMessages):
        self._inner, self._meter = inner, meter

    def get_final_message(self):
        return self._meter._charge(self._inner.get_final_message())


def make_live_client(api_key: str, price: dict, budget: Budget):
    """app.services.anthropic_client.ClaudeClient on the eval key -- the real
    gateway, retries, truncation check and temperature handling included --
    with the prompts it sends kept in `calls` (for the prompt-level graders)
    and the money it spends in `cost_usd`."""
    import anthropic  # noqa: PLC0415

    from app.services.anthropic_client import ClaudeClient  # noqa: PLC0415

    class LiveClient(ClaudeClient):
        def __init__(self) -> None:  # noqa: D107 -- skips the settings-key check on purpose
            self._client = anthropic.Anthropic(api_key=api_key, base_url=API_BASE_URL)
            self._client.messages = _MeteredMessages(self._client.messages, price, budget, self)
            self.calls: list[dict] = []
            self.cost_usd = 0.0

        def complete(self, system: str, prompt: str, max_tokens: int | None = None,
                     temperature: float | None = None) -> str:
            self.calls.append({"kind": "text", "system": system or "", "prompt": prompt or "",
                               "kwargs": {"max_tokens": max_tokens, "temperature": temperature}})
            return super().complete(system=system, prompt=prompt, max_tokens=max_tokens,
                                    temperature=temperature)

    return LiveClient()


@contextlib.contextmanager
def model_override(model: str):
    """The gateway reads settings.anthropic_model on every call."""
    from app.config import settings  # noqa: PLC0415

    old = settings.anthropic_model
    settings.anthropic_model = model
    try:
        yield
    finally:
        settings.anthropic_model = old


# --- selection and estimate ------------------------------------------------

def live_cases(specs: list[fw.Spec], touchpoints: set[str] | None) -> list[tuple[fw.Spec, fw.Case]]:
    """Every case a live model can meaningfully answer, with the expect keys
    that only hold for the recorded output (spec.live_ignore) removed."""
    return [(s, dataclasses.replace(c, expect={k: v for k, v in c.expect.items()
                                               if k not in s.live_ignore + c.live_ignore}))
            for s in specs if not touchpoints or s.id in touchpoints
            for c in s.cases if not c.offline_only]


def replay_mismatches(specs: list[fw.Spec], touchpoints: set[str] | None,
                      adapters: dict) -> list[str]:
    """Replay every selected case offline, in THIS process's environment, and
    list each one whose result differs from the offline gate's: a case must
    pass unless it carries known_failure, which must fail. The gate runs
    under tests/conftest.py; this runs under evals/ai/sandbox.py. Any
    difference means the live run would not exercise the app as tested."""
    out = []
    logging.disable(logging.CRITICAL)
    try:
        for spec in specs:
            if touchpoints and spec.id not in touchpoints:
                continue
            for case in spec.cases:
                res = fw.run_case(spec, case, adapters[spec.adapter],
                                  fw.ReplayClient(case.recorded), gr.GRADERS)
                if res.passed == bool(case.known_failure):
                    out.append(f"{spec.id}/{case.id}: "
                               + (res.error[:120] or ("passed" if res.passed else "failed")))
    finally:
        logging.disable(logging.NOTSET)
    return out


def estimate_usd(pairs, price: dict, k: int, adapters: dict) -> tuple[float, int]:
    """Worst case for the whole run, from the prompts the app actually builds
    (one offline replay per case) and each call's full max_tokens."""
    from app.config import settings  # noqa: PLC0415

    total, calls = 0.0, 0
    logging.disable(logging.CRITICAL)  # the replays' own app logs are noise here
    try:
        replays = []
        for spec, case in pairs:
            client = fw.ReplayClient(case.recorded)
            fw.run_case(spec, case, adapters[spec.adapter], client, gr.GRADERS)
            replays.append(client)
    finally:
        logging.disable(logging.NOTSET)
    for client in replays:
        for call in client.calls:
            limit = int(call["kwargs"].get("max_tokens") or settings.anthropic_max_tokens)
            total += worst_case_usd(price, len(call["system"]) + len(call["prompt"]), limit)
            calls += 1
    return total * k, calls * k


# --- ledger ------------------------------------------------------------------

def read_state(path: Path | None = None) -> dict:
    path = path or STATE_PATH
    if not path.exists():
        raise Refused(f"{path} is missing; it holds the spend ledger")
    return json.loads(path.read_text(encoding="utf-8"))


def record_spend(state: dict, entry: dict, path: Path | None = None) -> None:
    path = path or STATE_PATH
    live = state.setdefault("live", {})
    live["spent_usd"] = round(float(live.get("spent_usd", 0.0)) + entry["spent_usd"], 6)
    live.setdefault("runs", []).append(entry)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


# --- the run -------------------------------------------------------------------

def preflight(args, prices: dict, state: dict) -> dict:
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        raise Refused("running in CI; the gate is offline-only")
    if args.model not in prices:
        raise Refused(f"no price for {args.model!r} in {PRICES_PATH.name}")
    if not 0 < args.max_usd <= PER_RUN_CEILING_USD:
        raise Refused(f"--max-usd must be in (0, {PER_RUN_CEILING_USD}]")
    spent = float(state.get("live", {}).get("spent_usd", 0.0))
    if spent + args.max_usd > PROGRAM_CEILING_USD:
        raise Refused(f"program ledger ${spent:.2f} + this run's ${args.max_usd:.2f} exceeds "
                      f"the ${PROGRAM_CEILING_USD:.0f} ceiling")
    return prices[args.model]


def run(args) -> int:
    from evals.ai.adapters import ADAPTERS  # noqa: PLC0415

    prices = load_prices()
    state = read_state()
    price = preflight(args, prices, state)
    specs = fw.load_all()
    selected = set(args.touchpoints or []) or None
    pairs = live_cases(specs, selected)
    if not pairs:
        raise Refused("no live cases selected")
    drift = replay_mismatches(specs, selected, ADAPTERS)
    if drift:
        raise Refused(f"{len(drift)} case(s) replay differently here than in the offline gate, "
                      "so this environment is not the tested one: " + "; ".join(drift[:10]))
    est, n_calls = estimate_usd(pairs, price, args.k, ADAPTERS)
    print(f"{len(pairs)} cases x k={args.k}: about {n_calls} calls, worst case ${est:.2f} "
          f"on {args.model} (limit ${args.max_usd:.2f})")
    if est > args.max_usd:
        raise Refused(f"worst-case ${est:.2f} is over --max-usd ${args.max_usd:.2f}")
    if args.dry_run:
        return 0
    key = os.environ.get("EVAL_ANTHROPIC_API_KEY")
    if not key:
        raise Refused("EVAL_ANTHROPIC_API_KEY is not set")

    budget = Budget(args.max_usd)
    results: list[fw.CaseResult] = []
    stopped = ""
    started = time.monotonic()
    with model_override(args.model):
        try:
            for spec, case in pairs:
                for i in range(args.k):
                    client = make_live_client(key, price, budget)
                    res = fw.run_case(spec, case, ADAPTERS[spec.adapter], client, gr.GRADERS, run=i)
                    if budget.exhausted:  # this result is incomplete; drop it
                        raise BudgetExhausted(budget.exhausted)
                    results.append(res)
        except BudgetExhausted as exc:
            stopped = str(exc)
    summary = fw.summarise(results, k=args.k)
    decision = fw.gate(summary, fw.load_baseline().get("live", {}), k=args.k)
    report = {
        "model": args.model, "k": args.k,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "spent_usd": round(budget.spent, 6), "wall_s": round(time.monotonic() - started, 1),
        "stopped_early": stopped, "gate": {"ok": decision.ok, "reasons": decision.reasons},
        "summary": summary,
        "errors": [{"tp": r.touchpoint, "case": r.case, "run": r.run, "error": r.error}
                   for r in results if r.error],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    record_spend(state, {"at": report["at"], "model": args.model, "k": args.k,
                         "spent_usd": report["spent_usd"], "report": str(out)})
    print(f"spent ${budget.spent:.4f}; gate {'PASS' if decision.ok else 'BLOCK'}; report {out}")
    for reason in decision.reasons:
        print(f"  - {reason}")
    return 0 if decision.ok and not stopped else 1


def main(argv: list[str] | None = None) -> int:
    from evals.ai import sandbox  # noqa: PLC0415

    sandbox.apply()  # before anything reads app settings; see sandbox.py
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--model", required=True)
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--max-usd", type=float, default=PER_RUN_CEILING_USD)
    p.add_argument("--touchpoints", nargs="*", help="e.g. T06 T11; default all")
    p.add_argument("--out", default=str(ROOT / "docs" / "program" / "ai" / "live" / "latest.json"))
    p.add_argument("--dry-run", action="store_true", help="estimate the cost; send nothing")
    return run(p.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())

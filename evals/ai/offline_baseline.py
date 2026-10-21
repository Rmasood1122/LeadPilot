"""Write the offline section of evals/ai/baseline.json.

  python3 -m evals.ai.offline_baseline

Replays every golden case (recorded outputs, no network, no spend) in the
sandbox environment (evals/ai/sandbox.py) and stores the per-touchpoint,
per-slice summary that tests/test_ai_evals.py gates against. Cases marked
known_failure are left out, exactly as the gate test leaves them out; each
is a strict xfail until its defect is fixed. Latency and cost are not
stored: offline they measure this machine, not the product.

It refuses to write when any case replays differently here than the gate
expects (a passing known_failure, a failing ordinary case), so a baseline
can only record a state the gate itself accepts.
"""

from __future__ import annotations

import json
import logging
import sys

from evals.ai import framework as fw

_MACHINE_NOISE = ("latency_p50_s", "latency_p95_s", "cost_usd", "cost_per_case_usd")


def build() -> dict:
    from evals.ai import graders as gr  # noqa: PLC0415
    from evals.ai.adapters import ADAPTERS  # noqa: PLC0415
    from evals.ai.live_eval import replay_mismatches  # noqa: PLC0415

    specs = fw.load_all()
    drift = replay_mismatches(specs, None, ADAPTERS)
    if drift:
        raise SystemExit(f"offline_baseline refused: {len(drift)} case(s) do not replay as the "
                         "gate expects: " + "; ".join(drift[:10]))
    logging.disable(logging.CRITICAL)
    try:
        results = [fw.run_case(s, c, ADAPTERS[s.adapter], fw.ReplayClient(c.recorded), gr.GRADERS)
                   for s in specs for c in s.cases if not c.known_failure]
    finally:
        logging.disable(logging.NOTSET)
    summary = fw.summarise(results, k=1)
    for tp in summary.values():
        for key in _MACHINE_NOISE:
            tp.pop(key, None)
    return dict(sorted(summary.items()))


def main() -> int:
    from evals.ai import sandbox  # noqa: PLC0415

    sandbox.apply()
    baseline = fw.load_baseline()
    baseline["offline"] = build()
    fw.BASELINE_PATH.write_text(json.dumps(baseline, indent=1) + "\n", encoding="utf-8")
    cases = sum(s["cases"] for tp in baseline["offline"].values() for s in tp["slices"].values())
    print(f"offline baseline: {len(baseline['offline'])} touchpoints, {cases} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())

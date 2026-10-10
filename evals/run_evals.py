#!/usr/bin/env python3
"""LeadPilot release-gate adapter (eval-conductor consumer-3, the last one).

Before this gate, LeadPilot had NO test CI at all — 1,985 offline tests
(SQLite in-memory, FakeClaude, stubbed broker; zero network) existed and
never ran on push. This adapter runs the offline suite with JUnit XML output
and turns the results into fail-closed release metrics that a bare
"pytest exit 0" step cannot provide:

  compliance_suite_pass_rate  over the SEALED legal/safety test files
                              (evals/compliance_testset.yaml). Fails closed
                              in BOTH directions: a failing test blocks, and
                              a sealed file that is missing or collects zero
                              tests blocks too (the deleted-test-file attack
                              that turns a bare pytest step green).
  full_suite_pass_rate        passed / (passed+failed+errored) over the whole
                              offline suite (skips excluded from denominator).
  offline_test_count          executed tests. Floor 3150 (measured 3,319, 2026-10-10):
                              mass test deletion cannot fake green.
  suite_runtime_s             soft ops budget, from junit time attributes.

Emits candidate/v2 for the vendored gate (evals/tools/promote.py):
registry_hash = sha256(evals/registry.yaml) (gate recomputes and verifies);
dataset_hash over the sealed testset + this adapter.

Honest run (CI):  python3 evals/run_evals.py
BLOCK fixtures:   python3 evals/run_evals.py --sabotage <mode> --out <path>
Fast live-fire:   ... --sabotage compliance --from-junit <honest junit.xml>

Sabotage modes exist ONLY to prove the gate fires (seen-it-fire doctrine).
Each is a genuine broken variant, never an edited number:
  compliance  the compliance subset is re-run with one sealed file EXCLUDED
              (the deleted-test-file attack, executed for real) -> that file
              contributes zero -> rate < 1.0
  suite       the full suite is re-run WITH an injected always-failing test
              (a genuinely red test flowing through junit -> adapter) ->
              full_suite_pass_rate < 1.0
  count       the suite is re-run restricted to the compliance subset only
              -> executed count far below the 3150 floor

--from-junit reuses an existing honest junit.xml for the base scores so a
sabotage run only executes its own sub-run (CI live-fire in seconds, not a
second full suite). All subprocess exit codes are read directly — no gating
signal ever crosses a pipe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
TESTSET = REPO / "evals/compliance_testset.yaml"
GATED_INPUTS = ["evals/compliance_testset.yaml", "evals/run_evals.py"]

FAILING_TEST = '''\
"""Injected by run_evals.py --sabotage suite: a genuinely failing test that
must flow junit -> adapter -> gate -> BLOCK. Never committed to tests/."""
def test_sabotage_always_fails():
    assert False, "sabotage: the gate must block a red suite"
'''


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_pytest(args: list[str], junit_out: Path) -> None:
    """Run pytest; exit codes 0 (all passed) and 1 (tests failed) are both
    valid measurement outcomes — anything else is an instrument failure."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--ignore=tests/integration",
         f"--junitxml={junit_out}", *args],
        cwd=REPO, capture_output=True, text=True,
    )
    if r.returncode not in (0, 1):
        raise SystemExit(
            f"FAIL: pytest exited {r.returncode} (collection/usage error — "
            f"not a measurement):\n{r.stdout[-2000:]}{r.stderr[-2000:]}")
    if not junit_out.exists():
        raise SystemExit("FAIL: pytest wrote no junit xml")


def parse_junit(path: Path) -> tuple[list[dict], float]:
    root = ET.parse(path).getroot()
    suites = root.iter("testsuite") if root.tag == "testsuites" else [root]
    cases: list[dict] = []
    runtime = 0.0
    for s in suites:
        runtime += float(s.get("time") or 0.0)
        for c in s.iter("testcase"):
            status = "passed"
            if c.find("failure") is not None:
                status = "failed"
            elif c.find("error") is not None:
                status = "error"
            elif c.find("skipped") is not None:
                status = "skipped"
            cases.append({"file": (c.get("classname") or "").replace(".", "/"),
                          "name": c.get("name"), "status": status})
    return cases, runtime


def case_file_matches(case_file: str, sealed: str) -> bool:
    # junit classname "tests.test_compliance.TestX" -> "tests/test_compliance/TestX"
    stem = sealed[:-3] if sealed.endswith(".py") else sealed  # tests/test_compliance
    return case_file == stem or case_file.startswith(stem + "/")


def compliance_rate(cases: list[dict], sealed_files: list[str]) -> tuple[float, list[str]]:
    """Per sealed file: contributes 1.0 iff it executed >=1 test and every
    executed test passed; missing/empty contributes 0.0 (fail closed)."""
    notes: list[str] = []
    score = 0
    for f in sealed_files:
        mine = [c for c in cases if case_file_matches(c["file"], f)]
        executed = [c for c in mine if c["status"] != "skipped"]
        if not executed:
            notes.append(f"{f}: ZERO tests executed (missing or emptied — fail closed)")
            continue
        bad = [c for c in executed if c["status"] != "passed"]
        if bad:
            notes.append(f"{f}: {len(bad)} failing/errored of {len(executed)}")
            continue
        score += 1
    return score / len(sealed_files), notes


def full_rate_and_count(cases: list[dict]) -> tuple[float, int]:
    executed = [c for c in cases if c["status"] != "skipped"]
    if not executed:
        raise SystemExit("FAIL: junit holds zero executed tests — refusing a vacuous rate")
    passed = sum(1 for c in executed if c["status"] == "passed")
    return passed / len(executed), len(executed)


def dataset_hash() -> str:
    h = hashlib.sha256()
    for rel in sorted(GATED_INPUTS):
        p = REPO / rel
        h.update(rel.encode()); h.update(b"\0")
        h.update(p.read_bytes()); h.update(b"\0")
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(REPO / "evals/candidate.json"))
    ap.add_argument("--registry", default=str(REPO / "evals/registry.yaml"))
    ap.add_argument("--junit-out", default=str(REPO / "out_evals/junit.xml"))
    ap.add_argument("--from-junit", default="",
                    help="reuse this honest junit.xml for base scores (skip the full run)")
    ap.add_argument("--sabotage", default="",
                    choices=["", "compliance", "suite", "count"])
    a = ap.parse_args()

    sealed = yaml.safe_load(TESTSET.read_text())["files"]

    # --- honest base measurement -----------------------------------------
    if a.from_junit:
        junit = Path(a.from_junit)
        if not junit.exists():
            raise SystemExit(f"FAIL: --from-junit {junit} not found")
    else:
        junit = Path(a.junit_out)
        junit.parent.mkdir(parents=True, exist_ok=True)
        run_pytest(["tests"], junit)
    cases, runtime = parse_junit(junit)

    comp_rate, notes = compliance_rate(cases, sealed)
    full_rate, count = full_rate_and_count(cases)
    scores = {
        "compliance_suite_pass_rate": comp_rate,
        "full_suite_pass_rate": full_rate,
        "offline_test_count": float(count),
        "suite_runtime_s": runtime,
    }

    # --- sabotage sub-runs (genuine broken variants) ----------------------
    if a.sabotage == "compliance":
        keep = sealed[1:]  # the deleted-test-file attack, executed for real
        with tempfile.TemporaryDirectory() as td:
            sub = Path(td) / "junit_sab.xml"
            run_pytest(keep, sub)
            sub_cases, _ = parse_junit(sub)
        rate, notes = compliance_rate(sub_cases, sealed)
        scores["compliance_suite_pass_rate"] = rate
    elif a.sabotage == "suite":
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "test_injected_sabotage.py"
            bad.write_text(FAILING_TEST, encoding="utf-8")
            sub = Path(td) / "junit_sab.xml"
            run_pytest(["tests", str(bad)], sub)
            sub_cases, _ = parse_junit(sub)
        rate, _cnt = full_rate_and_count(sub_cases)
        scores["full_suite_pass_rate"] = rate
    elif a.sabotage == "count":
        with tempfile.TemporaryDirectory() as td:
            sub = Path(td) / "junit_sab.xml"
            run_pytest(sealed, sub)
            sub_cases, _ = parse_junit(sub)
        _r, cnt = full_rate_and_count(sub_cases)
        scores["offline_test_count"] = float(cnt)

    cand = {
        "manifest": {
            "schema": "candidate/v2",
            "registry_hash": sha256_file(Path(a.registry)),
            "dataset_hash": dataset_hash(),
        },
        "scores": scores,
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cand, indent=2) + "\n", encoding="utf-8")

    mode = "honest" if not a.sabotage else f"SABOTAGE:{a.sabotage}"
    print(f"run_evals ({mode}): wrote {out}")
    for k in sorted(scores):
        print(f"  {k:28s} {scores[k]:.6f}")
    for n in notes:
        print(f"  NOTE {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

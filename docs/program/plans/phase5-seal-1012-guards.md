# Gate change: seal the 2026-10-12 legal/safety guard tests, refresh the baseline

Date: 2026-10-12. Branch `claude/gate-seal-1012`, stacked on the five
2026-10-12 PRs (decisions-1011 → home-landing → gaps-sweep-2 →
autopilot-launch → local-business), because it seals test files those PRs
add. Merge it **last**.

## Why this is its own PR

CLAUDE.md: a seal, threshold or baseline change is its own reviewed PR with a
written justification, never a side effect of making something pass. It also
says a new legal/safety guard file is sealed in the commit that adds it. The
feature branches cannot do that: the `protect_sealed` hook allows sealed-file
edits only on `gate/` or `claude/gate-` branches. Each guard was therefore put
in its own file, its branch reported it for sealing, and this PR seals all of
them in one reviewed place, the same as the 2026-10-11 gate PR (#86,
`phase4-seal-new-guards.md`).

## 1. `evals/compliance_testset.yaml`: 5 files added (24 → 29)

Sealed means the gate BLOCKs if any test in the file fails, or if the file is
missing or collects zero tests (the deleted-test-file attack).

| File | Tests | Guard | Added by |
|---|---|---|---|
| tests/test_closed_lead_guard.py | 6 | A lead closed from the CRM grid, a CRM bulk edit or the Pipeline board has its live sequences stopped (CRM sync shares the same terminal-status rule), and the send path cancels a sequence step to a closed lead | gaps-sweep-2 (#3, review M3) |
| tests/test_unsubscribe_headers_raw.py | 10 | The one-click `List-Unsubscribe` / `List-Unsubscribe-Post` headers go out raw, neither RFC 2047-encoded nor folded, on every outbound builder (Gmail send, Gmail draft, SMTP), and the F03 preflight checks the raw bytes (RFC 8058; Google/Yahoo sender rules; CAN-SPAM working opt-out) | gaps-sweep-2 (review R1, HIGH) |
| tests/test_launch_lawful_basis.py | 7 | Enrolling leads (`POST /sequences/{id}/enroll`) needs the server-side lawful-basis confirmation (422 without it, nothing launches) and is audited; an SDR's confirmation travels with the manager-approval request, and a request stored without it needs the manager's own confirmation. On by default in production | autopilot-launch (§3.5) |
| tests/test_best_time_window_guard.py | 5 | Best-time placement never moves a message outside the permitted sending window or a compliance rule's window, in 8 zones including DST weeks; the sealed window-start scenario holds with best-time ON | autopilot-launch (review M8b) |
| tests/test_customer_winback_guards.py | 27 | Customer win-back is consent-only. It never mixes audiences. It never reaches a person who opted out (including on re-import, H1). It never uses phone or calls (H2). It always refuses healthcare businesses. The send path re-checks all of this | local-business |

Not sealed (feature behaviour, not a legal duty): `tests/test_autopilot_launch.py`,
`tests/test_send_time.py`, `tests/test_send_diagnostics.py`,
`tests/test_customer_winback.py`, `tests/test_local_business.py`,
`tests/test_gaps_sweep_2.py`, `tests/test_reply_threading.py`. They remain in
the full suite, whose hard threshold is a 1.0 pass rate.

**Known limit (reported, not changed here):** two sealed suites rely on autouse
fixtures in `tests/conftest.py` (`best_time_scheduling_off`,
`launch_lawful_basis_off`). Without them, the older sealed tests that call
enroll with `{}` would need the new confirmation. The guard files above turn
the flags back on themselves. `tests/conftest.py` is not sealed, so a conftest
edit could change what the older sealed suites exercise. Whether to seal
conftest is a separate founder decision.

## 2. `evals/baseline.json`: refreshed

Adding files to the sealed set changes `dataset_hash`, so the baseline must be
rebuilt in the same PR. Otherwise promote.py rejects every candidate as stale.
The suite also grew from 5,157 to about 5,640 tests. Rebuilt from 2 measured
runs of `python3 evals/run_evals.py` with `evals/tools/baseline.py --runs 2`.

Thresholds in `evals/registry.yaml` are NOT changed. The test-count floor
stays at 3,150; raising it is a separate decision for the founders.

## 3. Block fixtures regenerated

`evals/fixtures/` holds the three sabotaged scorecards that prove each hard
gate fires. They are regenerated from the honest junit of a baseline run
(`run_evals.py --from-junit <junit> --sabotage compliance|count|suite`). The
compliance fixture now deletes one of 29 sealed files.

## Evidence (2026-10-12)

Run on this branch (stack top `99c56a8` plus this commit), worktree-local, offline.

| Command | Exit | Result |
|---|---|---|
| `python3 evals/tools/registry_lint.py evals/registry.yaml` | 0 | OK (registry unchanged; `registry_hash` cf8c14a4… unchanged) |
| `python3 evals/tools/baseline.py --cmd 'python3 evals/run_evals.py' --runs 2` | 0 | both runs: 5,637 tests, pass 1.000, compliance 1.000 (29 sealed files), 851.6 s / 828.3 s; baseline runtime mean 840.0 s, band_2sigma 32.8 s; `dataset_hash` 6ca82864… |
| `python3 evals/run_evals.py --from-junit <run-2 junit> --sabotage compliance` → `block_compliance_suite_pass_rate.json` | 0 | compliance 0.9655 (28 of 29: `tests/test_compliance.py` removed for real, ZERO tests executed, fail closed) |
| `--sabotage count` → `block_offline_test_count.json` | 0 | offline_test_count 1,176 (< floor 3,150) |
| `--sabotage suite` → `block_full_suite_pass_rate.json` | 0 | full_suite_pass_rate 0.99982 (one injected failing test) |
| `evals/fixtures/healthy.json` = run 2's honest candidate | — | — |
| `python3 evals/tools/promote.py` | 0 | PROMOTE, no warnings (runtime 828.3 vs 840.0) |
| `python3 evals/fixtures/verify_block_fixtures.py` | 0 | all 3 hard gates proven to fire (each BLOCKs exactly its metric); healthy PROMOTEs |
| `pytest tests/test_safe_merge.py tests/test_gate_scripts.py` + every test that reads `compliance_testset.yaml` | 0 | 157 passed |

The five sealed files are unchanged by this PR (byte-identical to their
feature branches). Their pre-fix failing states are recorded in each branch's
evidence doc: `docs/program/fixes/gaps-sweep-2.md` (closed-lead: 10 failed;
raw headers: 7 failed on d5da447), `docs/features/autopilot-launch.md` §3.5
and §3.6, and `docs/features/local-business-mode.md` (test plan and review
rounds).

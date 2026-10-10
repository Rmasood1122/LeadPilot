# Phase 1 item 1.3 — baseline refresh and test-count floor (sealed-file change)

Sealed files changed (`CLAUDE.md`, "Sealed files"): `evals/registry.yaml`,
`evals/baseline.json`. Also regenerated because they embed the registry hash:
the four gate fixtures in `evals/fixtures/`. `evals/run_evals.py` docstring
numbers updated (comment text only; no logic change). No test, threshold
direction, sealed compliance file list or CI step changes.

## Why

1. **The floor no longer protects anything.** `offline_test_count` had a hard
   floor of 1,900, set when the suite had ~1,985 tests. The suite now executes
   3,319 (measured 2026-10-10, `docs/program/BASELINE.md` §4). About 1,400
   tests could be deleted and the gate would still PROMOTE. The metric exists
   to block mass test deletion (`FM-TEST-MASS-DELETION`), so its floor must
   track the real suite.
2. **The baseline is stale.** `evals/baseline.json` recorded 1,985 tests and a
   202 s runtime. Every run now raises a soft runtime "regression" warning
   (421–531 s vs 202 s), which trains people to ignore the warning.

## Change

| Item | Before | After |
|---|---|---|
| `offline_test_count` floor (hard) | 1,900 | **3,150** (~95% of 3,319) |
| baseline `offline_test_count` | 1,985 | 3,319 |
| baseline `suite_runtime_s` | 202.0 s (band 5.5) | 436.7 s (band 6.1) |
| baseline runs | 2 | 2 |
| fixtures | measured against old registry | re-measured against new registry |

Why 3,150 and not 3,319: the old floor left ~4% headroom (1,900 vs ~1,985) so a
legitimate refactor that merges or removes some tests is not blocked; 3,150
keeps ~5%. Deleting more than ~170 tests now needs this same kind of reviewed
PR.

## How the numbers were produced (not typed)

All on a 2-vCPU Claude Code cloud VM, CPython 3.12. Nothing else heavy ran during the two baseline runs (one ~9 s unit-test run overlapped run 2):

```
python3 evals/tools/registry_lint.py evals/registry.yaml                  # exit 0
python3 evals/tools/baseline.py --cmd "python3 evals/run_evals.py" --runs 2   # exit 0
cp evals/candidate.json evals/fixtures/healthy.json
python3 evals/run_evals.py --sabotage compliance --from-junit out_evals/junit.xml --out <tmp>/sab_compliance.json  # -> block_compliance_suite_pass_rate.json
python3 evals/run_evals.py --sabotage suite      --from-junit out_evals/junit.xml --out <tmp>/sab_suite.json       # -> block_full_suite_pass_rate.json
python3 evals/run_evals.py --sabotage count      --from-junit out_evals/junit.xml --out <tmp>/sab_count.json       # -> block_offline_test_count.json
python3 evals/tools/promote.py                                            # PROMOTE
python3 evals/fixtures/verify_block_fixtures.py                           # all hard gates proven to fire
# CI live-fire step, run locally: sabotaged candidate -> promote.py exit 1 (BLOCK)
```

Measured scores: healthy 3,319 tests / pass rates 1.0 / 438.8 s; sabotage
`compliance` → compliance rate 0.8 (`tests/test_compliance.py` excluded, zero
tests executed); `suite` → full-suite rate 0.999699 (one injected failing
test); `count` → 116 executed tests.

Runtime note: the baseline runtime (436.7 s) was measured on the cloud VM; the
GitHub runner measured ~511–531 s for the same suite. `suite_runtime_s` is a
**soft** metric with a 120 s noise band, so CI runs fall inside the band
rather than warning on every run. It never blocks.

## Interaction with other open PRs

PR #48 adds 48 tests and PR (item 1.5) adds more. Higher counts are fine:
`offline_test_count` is `higher_better` and only a drop below 3,150 blocks.

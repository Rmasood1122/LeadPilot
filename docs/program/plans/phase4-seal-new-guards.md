# Gate change: seal the new legal/safety guard tests, refresh the baseline, require the verify jobs

Date: 2026-10-11. Branch `claude/gate-seal-new-guards`, stacked on the seven
2026-10-11 PRs (#79–#85) because it seals test files those PRs add. Merge it
**last**, after #85.

## Why this is its own PR

CLAUDE.md: a seal, threshold or baseline change is its own reviewed PR with a
written justification, never a side effect of making something pass. The
features F01–F10 (#65–#74) and the 2026-10-11 fixes (#79–#85) each added a
legal or safety guard but deferred sealing to the founders (CLAUDE.md also
says a new guard file is sealed in the commit that adds it; that was not
done, so this PR closes the gap in one reviewed place).

## 1. `evals/compliance_testset.yaml`: 19 files added

Sealed = the gate BLOCKs if any test in the file fails, or if the file is
missing or collects zero tests (the deleted-test-file attack). Each added
file pins a legal duty or a send-time safety guard:

| File | Guard |
|---|---|
| tests/test_guardrails.py | F05: excluded customers / open deals / do-not-contact are never sourced or sent to; forbidden phrases block a send |
| tests/test_bounce_shield.py | F01: no send to an address without a fresh verified-valid verdict; held steps are not duplicated |
| tests/test_deliverability_autopilot.py | F03: launch blocked when SPF/DKIM/DMARC or one-click unsubscribe headers fail (Google/Yahoo sender rules, CAN-SPAM) |
| tests/test_reply_copilot.py, tests/test_reply_copilot_review_fixes.py | F04: an opt-out reply never gets a drafted answer; suppressed/excluded contacts cannot be answered; claim verification; auto-send conditions; later stop events cancel |
| tests/test_champion_tracker.py | F10: a person who left is never messaged at the old company address (all channels, manual calls); erased leads are never re-enriched |
| tests/test_pilot_mode.py | F09: a pilot never converts to a paid plan; scorecards only to the owner, never the outreach path |
| tests/test_account_export.py | GDPR Art. 15/20: the export covers every owned table and only the account's rows |
| tests/test_send_path_guards.py | Meeting follow-up runs the outreach recipient guards; LinkedIn suppression at sourcing; removed leads never sent to; only verified leads enrolled |
| tests/test_whatsapp_template_optout.py | WhatsApp marketing templates carry an opt-out instruction at create/edit/submit and at send time (WhatsApp Business policy; CASL s.6(2)(c), s.11) |
| tests/test_daily_send_approval.py, `_e2e.py`, `_network.py` | Founder decision 2026-10-11: automatic sending needs a person's approval once a day per channel; LinkedIn needs the restriction-risk acknowledgement; API keys cannot approve |
| tests/test_annual_billing.py, tests/test_annual_billing_review.py | Auto-renewal consent, disclosure, renewal/trial notices, online cancel, no surprise charges (CA ARL, NY GOL 5-903, ROSCA — readings to be confirmed by counsel) |
| tests/test_account_erasure.py, tests/test_lead_erasure_correspondence.py, tests/test_privacy_docs_truth.py | GDPR Art. 17: account deletion and lead erasure complete and scoped to the account; the privacy texts state what the code does |
| tests/test_password_reset.py | Account-takeover recovery: single-use hashed links, no enumeration, a reset signs out every device and revokes API keys |

Not sealed: frontend vitest files (the gate runs the Python suite only; the
D1 `websiteClaims.test.ts` and status-page tests run in `verify-frontend`,
which this PR makes required); `tests/test_plan_downgrade_holds.py`
(entitlement, not a legal duty).

## 2. `evals/baseline.json`: refreshed

Adding files to the sealed set changes `dataset_hash`, so the baseline must
be rebuilt in the same PR or promote.py rejects every candidate as stale.
The runtime baseline was also stale (436.7 s at 3,319 tests; the suite is now
5,155 tests and ~840 s, which raised a soft warning on every run). Rebuilt
from 2 measured runs of `python3 evals/run_evals.py` with
`evals/tools/baseline.py --runs 2`. The numbers are in the PR body.

Thresholds in `evals/registry.yaml` are NOT changed (the test-count floor
stays 3,150; raising it is a separate decision for the founders).

## 3. `scripts/gate/required_checks.txt`: verify jobs required

`safe_merge.sh` required only `gate`. The verify jobs (PostgreSQL integration
+ `alembic upgrade head`, frontend tsc/vitest/lint, secret scan, Docker image
boot, status-page app) existed but did not block a merge. Two of today's
defects would have been caught by them (a 64-character FK name that fails
`alembic upgrade` on PostgreSQL; a frontend test pinned to the old status
URL). Every verify job always concludes (its steps are scoped, the job is
not), so requiring them cannot leave a PR waiting on a job that never runs.

## Not fixable in the repo

GitHub Actions is not running at all ("recent account payments have failed
or your spending limit needs to be increased"). Until billing is fixed no
check concludes, so `safe_merge.sh` refuses every PR — correctly.

## Evidence (2026-10-11)

| Command | Exit | Result |
|---|---|---|
| `python3 evals/tools/baseline.py --cmd 'python3 evals/run_evals.py' --runs 2` | 0 | runs: 5,157 tests, pass 1.000, compliance 1.000, 830.4 s / 840.4 s; baseline mean 835.4 s, band_2sigma 14.0 s |
| `python3 evals/tools/promote.py` | 0 | PROMOTE, no warnings (runtime 840.4 vs 835.4) |
| `python3 evals/run_evals.py --from-junit <honest junit> --sabotage compliance` → block fixture | 0 | compliance 0.9583 (23 of 24 sealed files: the deleted-file attack run for real) |
| `--sabotage count` → block fixture | 0 | offline_test_count 1,087 (< floor 3,150) |
| `--sabotage suite` → block fixture | 0 | full_suite_pass_rate 0.99981 (one injected failing test) |
| `python3 evals/fixtures/verify_block_fixtures.py` | 0 | all 3 hard gates proven to fire; healthy PROMOTEs |
| `python3 evals/tools/registry_lint.py evals/registry.yaml` | 0 | OK (registry unchanged) |
| `pytest tests/test_safe_merge.py tests/test_gate_scripts.py` | 0 | 74 passed |

The first baseline attempt measured 3 failures in `tests/test_safe_merge.py`
(its fake check-run world listed only `gate`); that run was discarded, the
tests now derive the green world from `required_checks.txt`, and a new test
proves a missing verify job is refused.

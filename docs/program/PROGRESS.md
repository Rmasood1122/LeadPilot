# Program progress

Resume from this file, `status.json` and `git log`.

## 2026-10-10 — Phase 0 (baseline)

**State: incomplete on one step; stop condition met.**

Done:

- Git state, open PRs (0), unmerged branches — `BASELINE.md` §2.
- Every finding from `FINDINGS_REGISTER.md`, `NEXT_STEPS.md`, `audit-fixes/*` and the Sep-24 list reconciled against `master @ 2170a55` — `BASELINE.md` §3.
- PostgreSQL suite run against the local compose database: 54 failed / 70 passed; the harness is stale — `BASELINE.md` §5.
- Production read-only checks; missing-heartbeat cause confirmed by experiment; D2 options — `BASELINE.md` §6.
- Help AI diagnostic query written and syntax-checked on a local migrated database — `help_ai_diagnostic.sql`.
- Prompt-vs-reality discrepancies — `BASELINE.md` §9.

Not done:

- **Offline gate (step 3).** `registry_lint` passed. `run_evals.py` was killed after ~40 minutes when the machine ran low on memory; `promote.py` and `verify_block_fixtures.py` did not run. CI for the same commit is green (run 37351754168). Needs one clean local run with nothing else on the machine.
- **PR.** The three program files are committed locally on `program/phase-0-baseline`. Not pushed: `BASELINE.md` lists open security findings and the repository is public. `gh` is not installed, so a PR could not be opened from here in any case.

Where the work lives:

- Worktree `../leadpilot-wt-phase0`, branch `program/phase-0-baseline`, based on `origin/master`.
- The main checkout is on `program/setup`, which is 67 commits behind `master`. Do not run a phase from it.

Open questions for the founders:

1. Push `BASELINE.md` to the public repo as is, or make the repo private first (D3)?
2. D2: paid worker, or a monitor on the worker URL?
3. P0-D: is the product multi-tenant SaaS? (`CLAUDE.md` says so; no decision record exists.)

Next:

- Finish step 3 (one clean run of the four gate commands).
- Phase 1. First task: repair `tests/integration/` so the PostgreSQL suite is green without weakening any test; only then can `verify-backend-postgres` be a required check.
- Phases 2–4 stay blocked until the OPEN P0/HIGH items in `BASELINE.md` §1 are fixed or accepted in writing.

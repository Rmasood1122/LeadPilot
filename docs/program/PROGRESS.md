# Program progress

Resume from this file, `status.json`, `DECISIONS.md` and `git log`.

## 2026-10-10 — Phase 0 (baseline), cloud session: completed

**State: Phase 0 done. The exit-gate stop condition is met (OPEN P0/HIGH items), so Phases 2–4 wait. Phase 1 may start.**

Done in this session:

- Dependencies installed on CPython 3.12.3 in `/home/user/.venvs/leadpilot312` (exit 0, 58 s).
- **Offline gate (step 3) run to completion**, four commands exactly as `CLAUDE.md` lists them, nothing else running: all exit 0; 3,319 tests executed (3,326 collected, 7 skipped), 0 failed; `run_evals.py` 530.5 s wall; `promote.py` = PROMOTE with one soft runtime warning; all 3 hard gates proven to fire. Peak memory 1.3 GB — `BASELINE.md` §4.
- Founder decisions recorded in `DECISIONS.md`: D3 (repo private, 2026-10-10), P0-D (self-hosted, single-tenant, 2026-10-04), D2 deferred to Phase 3.
- F-DB-01 and RF-5 re-rated HIGH → MEDIUM under P0-D, with reasoning — `BASELINE.md` §3.5. GDPR account export/deletion, P0-5 per-account spend cap and plan enforcement are **not** downgraded.
- New finding **P0-D-ENF (HIGH)**: public sign-up cannot be disabled, so single-tenancy is not enforced by the code — `BASELINE.md` §3.5.
- Phase 1 inputs — `BASELINE.md` §11: GitHub Pro is needed for the ruleset on a private repo. `eval-gate` bills 9 min per run (measured on CI run 38038727255); runs per PR = 3 + 2N; about 31 PRs/month on Free and 47 on Pro at N = 2.
- Draft PR: https://github.com/Rmasood1122/LeadPilot/pull/43.
- Correction: `BASELINE.md` §9 row 9 was wrong (`CLAUDE.md` no longer names a migration chain since `609af9a`).
- Non-English text check on `BASELINE.md`, `PROGRESS.md`, `status.json`: none found; nothing to rewrite.

Earlier (2026-10-10, laptop session): git state, findings reconciliation, PostgreSQL suite (54 failed / 70 passed, harness stale), production read-only checks and D2 diagnosis, Help AI diagnostic SQL, prompt-vs-reality discrepancies. The laptop's offline-gate run was killed for low memory; superseded by the run above.

Open questions for the founders:

1. D1 (website copy vs. code), D5 (required approval), D6 (status page key and DNS) are unanswered.
2. Upgrade to GitHub Pro before the Phase 1 ruleset step, or accept an unenforced ruleset?
3. Approve updating `CLAUDE.md` ("Multi-tenant", "~1,985 tests") to match P0-D and the measured count?
4. Is sign-up open on the current Render production? (UNVERIFIED: no production requests were made in this session.)

Next:

- Phase 1. First task: repair `tests/integration/` so the PostgreSQL suite is green without weakening any test. Only then can `verify-backend-postgres` be a required check.
- Phases 2–4 stay blocked until the OPEN P0/HIGH items in `BASELINE.md` §1 are fixed or accepted in writing.

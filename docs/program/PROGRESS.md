# Program progress

Resume from this file, `status.json`, `DECISIONS.md` and `git log`.

- 2026-10-16 — GEO publish round (claude/relaxed-lamport-ab7g3j, not merged): 12 GEO pages, /help/ (30 articles), /llms.txt, explicit robots.txt, both founders (Ahmad Shahid, Rehan Masood); founder answers in `docs/program/ai-visibility/NOTES.md`; published before trademark review by founder choice — `docs/program/ai-visibility/geo/state.md`.
- 2026-10-15 — GEO/AEO system (docs only, claude/relaxed-lamport-ab7g3j): entity card, niche statement, 50-query library, competitor analysis, page drafts (definition, 10 use cases, 5 comparisons, 30 FAQs, sourced statistics), JSON-LD/robots/llms.txt/architecture, 5 platform playbooks, 50-platform citation plan, Reddit and syndication plans, tracker; nothing published (trademark gate, Q-04); 15 founder questions — `docs/program/ai-visibility/geo/state.md`.
- 2026-10-13 — AI visibility Part A (seo/ai-visibility): canonical www host, static plan names, product-facts source, JSON-LD, copy contradictions removed, IndexNow script, git lastmod, check_static_seo.mjs as postbuild; Part B waits for trademark review — `docs/program/ai-visibility/REPORT.md`.

## 2026-10-10 — Phase 1, items 1.6 and 1.7, cloud session

**State: all Phase 1 PRs open: #47, #48, #49, #50, #51, #52 and this one (GATES.md). Merge order: #48 → #47 → #49 → #50 → #51 → #52 → this.**

- 1.6 (#52): `verify.yml` (postgres, frontend, image, security) + `post-merge-alarm.yml`. Validated locally on PostgreSQL 16 + Redis 7 (integration 132 passed; migration round-trip exit 0).
- Sabotage proof (#53, closed): all four verify jobs failed at the intended step. The first run exposed a scanner bug (`db\b` excluded `db.example.com`); fixed in #51 with regression tests; second run red as required.
- PD-2 (#50): `frontend/package-lock.json` out of sync; `npm ci` failed on master. Fixed; Vercel preview build green; vitest 721 passed.
- 1.7: `docs/program/GATES.md` — layers, what is not enforced, proofs with run URLs, founder steps for Render/Vercel deploy gating, minutes.

Next (after merges): add `verify-*` to `required_checks.txt` once green on master; founders set Render/Vercel deploy gating; then Phase 1 exit. Open P0/HIGH items (spend cap, GDPR account export/deletion, plan enforcement, sign-up shut-off P0-D-ENF) are next, one PR each.

## 2026-10-10 — Phase 1, items 1.2, 1.3, 1.5, cloud session

**State: PRs #47 (1.2) and #48 (1.4) green; #49 (1.3) open; item 1.5 PR stacked on #48.**

- 1.2 (#47, sealed): `eval-gate.yml` runs on `pull_request` + `push` to master only; superseded PR runs cancelled. Verified on #47: one `gate` run per commit, no `push` run on the branch.
- 1.3 (#49, sealed): `offline_test_count` floor 1,900 → 3,150; baseline rebuilt from 2 runs (3,319 tests, 436.7 s); fixtures re-measured with real sabotage runs. PROMOTE; all hard gates fire; live-fire BLOCK.
- 1.5: `scripts/gate/quick_gate.sh` (secrets, syntax, critical lint, single Alembic head, registry lint, related + sealed tests, frontend if changed; stamps the tree on a clean full pass), `scan_secrets.py`, `full_gate.sh`, `.githooks/pre-push` + `install_hooks.sh`, Claude hooks `require_gate.py` (no `--no-verify`, no unstamped push), `protect_sealed.py` (gate files only on `gate/`/`claude/gate-` branches), `stop_check.py` (once per stop, never loops). Tests: `tests/test_gate_scripts.py`.


## 2026-10-10 — Phase 1, item 1.4 (safe_merge + merge hook), cloud session: PR open

**State: merge gate built and tested; PR open. PRs #44, #45, #46 are merged (INC-44/45 recorded in `DECISIONS.md`).**

- `scripts/gate/safe_merge.sh` → `safe_merge.py`: refuses unless the PR is open, targets master, is not a draft, has no conflict, is not behind master, every check in `scripts/gate/required_checks.txt` (today: `gate`) succeeded on the head SHA, no other check is running/failed, and no commit status is pending/failed. Squash-merges with the head SHA pinned. `--dry-run` checks only. Live dry-run against PR #46 refused it correctly (closed; behind master).
- `.claude/hooks/guard_merge.py` + `.claude/settings.json`: PreToolUse hook blocks `gh pr merge`, REST calls to `pulls/<n>/merge`, `git push` to master/main (incl. `HEAD:master`, `+master`, bare push while on master) and MCP merge tools. `safe_merge.sh` is allowed.
- Tests: `tests/test_safe_merge.py` (22) and `tests/test_claude_hooks.py` (26), offline.
- Still not enforced: the GitHub web UI Merge button. Deploy gating (item 1.7) is the backstop.

Next: item 1.2 (sealed: eval-gate triggers), 1.3 (sealed: baseline refresh), 1.5 (quick gate + pre-push + more hooks).

## 2026-10-10 — Phase 1, item 1b (PD-1 webhook schema), cloud session: PR open

**State: PostgreSQL integration suite 132 passed / 0 failed with migration 0071. Stacked on PR #44; merge #44 first.**

- Migration `0071_webhook_schema_sync`: `webhook_targets.event_types` text[] → json; `webhook_deliveries.payload_json` text → json (invalid JSON kept as `legacy_text`); `last_status_code` (copied from `last_response_code`) and `delivered_at` added. Nothing dropped. Downgrade tested.
- Correction: `subject_line_patterns` is NOT part of PD-1. Live raw SQL matches the migrated table; the ORM model is stale. Reported only.
- Deploy: the next API deploy runs 0071 on Neon. Founders: run the read-only query in `docs/program/plans/phase1-01b-pd1-webhook-schema.md` first.
- Detail: `docs/program/plans/phase1-01b-pd1-webhook-schema.md`.

PR: https://github.com/Rmasood1122/LeadPilot/pull/46 (draft; merge after #44).

Next: item 2 (sealed PR: eval-gate.yml triggers).

## 2026-10-10 — Phase 1, item 1 (PostgreSQL integration repair), cloud session: PR open, suite NOT green

**State: 54 failed / 70 passed → 125 passed / 4 errors. The 4 errors are product defect PD-1, reported, not fixed. Waiting on founder review of the PR and on the A/B merge-policy answer (Amendment 0).**

- Root causes, all 54, by group: `docs/program/plans/phase1-01-integration-repair.md`. G1 (50): root conftest Anthropic guard; the integration mock never intercepted anthropic SDK 1.x (`httpx2`), so lifting the guard sent a real request to api.anthropic.com. G2 (7 of G1): Calendly mock signed with a 2023 timestamp, refused by F-OPS-02 replay check. G3 (4 of G1): `/suppression` is admin-only (F-SEC-04); tests called it as a user and ignored the 403. G4 (4): `webhook_delivery` API rebuilt in `41cea92`; tests ported to the current API.
- PD-1: `webhook_targets.event_types` is `text[]` (migration 0011) but `JSON` in the model; creating any outbound webhook target fails on PostgreSQL. Needs its own PR with a migration.
- Offline gate unchanged: 4 commands exit 0, 3,319 tests, PROMOTE (1 soft runtime warning).
- Amendment 0: founders chose merge policy **B** (2026-10-10). Recorded as INC-43 and MERGE-B in `DECISIONS.md`; 3 lines added to `CLAUDE.md`.

PR: https://github.com/Rmasood1122/LeadPilot/pull/44 (draft).

Next: founders review the PR; decide whether PD-1 is fixed before `verify-backend-postgres` becomes required. Then item 2 (eval-gate.yml triggers, sealed-file PR).

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

Follow-up decisions, same day (`DECISIONS.md`): GitHub Pro will not be bought, so the Layer 4 ruleset is dropped and the founders will give a replacement design next session. D5 is a written policy only; GitHub cannot enforce it. `CLAUDE.md` lines 11 and 19 updated (single-tenant per P0-D; 3,319 tests, ~9 minutes).

Open questions for the founders:

1. D1 (website copy vs. code) and D6 (status page key and DNS) are unanswered. *(Superseded: D1 was decided 2026-10-10 and D6 resolved 2026-10-11 by the /status page on the main site -- `DECISIONS.md`.)*
2. Is sign-up open on the current Render production? (UNVERIFIED: no production requests were made in this session.)

Next:

- Phase 1, using the founders' replacement for Layer 4. First task: repair `tests/integration/` so the PostgreSQL suite is green without weakening any test. Only then can `verify-backend-postgres` be a required check.
- Phases 2–4 stay blocked until the OPEN P0/HIGH items in `BASELINE.md` §1 are fixed or accepted in writing.

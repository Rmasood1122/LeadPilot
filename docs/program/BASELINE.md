# LeadPilot — Phase 0 Baseline

Built 2026-10-10 from `origin/master @ 2170a55` (last commit 2026-10-05), in a
clean worktree with no `.env`. Every status below was checked against the code
at that commit in this session. Nothing here is taken from an audit document
without re-reading the file it points at.

Status vocabulary: **FIXED** (code read, guard present, test exists) ·
**OPEN** (code read, defect present) · **UNKNOWN** (cannot be decided from the
repository — needs production data, credentials or a decision).
"FIXED, residual" means the reported defect is closed and a narrower one
remains; the residual is stated.

---

## 1. Verdict

**Phase 0 is incomplete: the offline gate (step 3) did not finish (section 4).**
Everything else in this file is complete.

**Exit gate 0 condition for stopping is met regardless: OPEN items at P0 / HIGH
exist.** Phases 2–4 wait. Phase 1 (gates) may proceed, and its first task is
repairing the PostgreSQL integration harness (section 5).

OPEN at P0 / HIGH:

| # | Item | Why it is still open |
|---|---|---|
| 1 | **F-DB-01 / cross-tenant learning loop** (HIGH on multi-tenant) | `playbook_scores` has no tenant column and `pattern_key` is a hash of ICP + tactics only, so two accounts with the same play share one score row. |
| 2 | **GDPR export / deletion for user accounts** (HIGH, compliance) | No endpoint, service or task deletes or exports a `users` row. Lead erasure exists; account erasure does not. |
| 3 | **P0-5 AI spend cap** (P0, partly closed) | Each strategy run is capped. There is no cap per account or per period, and three plans have unlimited strategies. |
| 4 | **Plan enforcement** (HIGH, revenue) | `max_leads_per_strategy`, `max_sequence_steps` and `channels` are declared in `PLANS` and enforced nowhere. |
| 5 | **RF-5 shared WhatsApp sender** (HIGH on multi-tenant) | One deployment-wide sender number. Inbound routing between tenants is a heuristic because of it. |

OPEN at MEDIUM: F-SEC-05 (website-builder NULL pool, deployment-global WhatsApp
templates), F-OPS-03 (two settings modules), F-AI-04 (no startup model check),
F-QA-02 (integrations never run against live vendors).

Proposed fix order is in section 8.

---

## 2. Repository state (step 1)

| Fact | Value | How checked |
|---|---|---|
| Trunk | `master`, `origin/master = 2170a55` (merge of PR #41, 2026-10-05) | `git fetch --all --prune`; `git rev-parse origin/master` |
| Open PRs | **0** | GitHub REST `GET /repos/Rmasood1122/LeadPilot/pulls?state=open` (`gh` is not installed on this machine; the GitHub MCP server failed to connect) |
| Repo visibility | **public**, default branch `master` | GitHub REST `GET /repos/Rmasood1122/LeadPilot` |
| Alembic | 72 files, single head `0070_linkedin_network_messages` | `python -m alembic heads` |
| `program/setup` | **not merged**; 1 commit ahead of master, 67 behind (branched from `e0d4624`, 2026-10-03) | `git rev-list --left-right --count origin/master...origin/program/setup` |

Remote branches with commits not in `master`:

| Branch | Ahead | Behind | Last commit |
|---|---|---|---|
| `feat/voice-interview` | 3 | 3 | 2026-10-05 |
| `feat/kill-switch` | 2 | 3 | 2026-10-05 |
| `feat/network-messages` | 2 | 3 | 2026-10-05 |
| `feat/linkedin-network-private` | 1 | 4 | 2026-10-05 |
| `program/setup` | 1 | 67 | 2026-10-10 |
| `claude/confident-franklin-lv1our` | 1 | 124 | 2026-09-26 |

The other 43 remote branches are 0 ahead (fully merged) and can be deleted.
No PR is open for any of the six branches above, so their unmerged commits are
either squash-merged under another SHA or abandoned — UNVERIFIED which.

---

## 3. Findings reconciliation (step 2)

### 3.1 Sep-24 audit list

| ID | Severity | Status | Evidence | How verified |
|---|---|---|---|---|
| P0-1 pipeline time limit | P0 | FIXED | `app/workers/tasks.py:96-97,187-188` (`soft_time_limit=settings.pipeline_task_timeout_seconds`, 7200 s, `app/config.py:350`); commit `e5967e0`; `tests/test_pipeline_task_time_limit.py` (4 tests) | read code; test in offline suite |
| P0-2 free-plan escalation | P0 | FIXED, residual | `app/api/billing.py:82` returns 503 when `billing_stub_mode` and production; commit `4f5fd4c`; `tests/test_checkout_requires_stripe.py` | read code. Residual: no Stripe check in `production_guard.py` (grep: none); stub mode still grants plans on any non-production `APP_ENV` |
| P0-2 existing stub subscriptions | P0 | UNKNOWN | fix report says existing `is_stub=true` rows keep their plans | needs a read-only production query; not in the repo |
| P0-3 suspension bypass | P0 | FIXED, residual | `app/services/auth.py:207`; commit `6e11abe`; `tests/test_account_suspension.py` (6 tests) | read code. Residual (LOW): `app/api/auth.py` `login`/`refresh` have no suspension check, so tokens are still issued and then refused at every route |
| P0-4 duplicate send | P0 | FIXED on SQLite; UNKNOWN on PostgreSQL | atomic claim `app/workers/outreach_tasks.py:357-384` (`rowcount != 1` → `lost_claim_race`); commit `cda7fc3`; `tests/test_duplicate_send_claim.py` | read code. The two-worker PostgreSQL race test the fix report calls for does not exist in `tests/integration/`. See section 5 for the PostgreSQL rerun of the existing test |
| P0-5 AI spend cap | P0 | FIXED per strategy; **OPEN per account** | per-run budget: `app/services/usage_meter.py:191-205`, `app/workers/tasks.py:147,207`; bounds `app/api/strategies.py:57-66` ($0.50 – `pipeline_max_usd_ceiling` $50, default $15, `app/config.py:59-60`); `max_strategies` on create `app/api/strategies.py:128-139`; `tests/test_strategy_budget.py` (24 tests) | read code. grep for a monthly / per-account cap across `app/`: none. `scale`, `pro`, `enterprise` have `max_strategies: -1` (`app/core/plans.py:96,129,146`), so their ceiling is $50 × unlimited. Model calls outside the pipeline (support chat, website builder, reply classifiers, meeting AI) are under no dollar budget — only rate limits |
| P0-6 admin playbook endpoint | P0 | FIXED | `app/api/admin.py:283-304` (ownership subquery, no bare `except`); commit `5ed9a3d`; `tests/test_admin_playbook_scores.py` | read code |
| RF-5 shared WhatsApp sender | HIGH | **OPEN** (by current design) | one sender for the deployment: `app/config.py:137` `whatsapp_phone_number_id`, used at `app/integrations/whatsapp.py:114,264`; `app/api/whatsapp_templates.py:98-105` states it is "deployment-wide" | read code. No per-tenant sender model exists in `app/db/models.py` |
| Prompt injection in `personalization_context.py` | HIGH | FIXED | `app/services/personalization_context.py:164,178-181,191` wrap post / news text in `prompt_safety.block` / `inline` under `prompt_safety.NOTICE`; commits `3a81a05`, `6df0dbe`; `tests/test_prompt_injection_containment.py` (17), `tests/test_outbound_injection_containment.py` (7) | read code |
| Plan enforcement | HIGH | **OPEN** (partial) | enforced: `max_strategies` (`strategies.py:137`), `max_site_pages` (`website_builder.py:228`), `playbook_access` (`playbook.py:46,80,121`), `ab_testing` (`strategies_advanced.py:42`), `website_builder` (`website_builder.py:216`), LinkedIn network (`linkedin_network.py:37`). Not enforced: `max_leads_per_strategy`, `max_sequence_steps`, `channels` | grep over `app/`: `check_plan_limit(` has 2 call sites; `check_channel(` has 0; `PlanGate(` has 0 (docstring only); the three unenforced keys appear only in `plans.py` and `billing_catalog.py` |
| GDPR export / deletion for user accounts | HIGH | **OPEN** | lead erasure exists (`app/api/leads.py:261`); LinkedIn-network erasure exists (`app/api/linkedin_network.py:135`). No route, service or task deletes or exports a user | grep over `app/` for user deletion / export / anonymisation: no match |
| Cross-tenant learning-loop leak | HIGH | **OPEN** | same as F-DB-01 below | — |

### 3.2 `docs/FINDINGS_REGISTER.md` (audit 2026-10-01)

| ID | Severity | Status | Evidence | How verified |
|---|---|---|---|---|
| F-SEC-01 suspended users keep access | CRITICAL | FIXED | `app/services/auth.py:207`; `6e11abe` | same as P0-3 |
| F-SEC-02 cross-tenant WhatsApp inbound | HIGH | FIXED, residual | `app/api/webhooks_whatsapp.py:338-358` `_lead_for_inbound`: the tenant that most recently sent a WhatsApp message to the number wins; several holders and no history → attached to nobody; commit `e868dbd`; `tests/test_whatsapp_inbound_tenant_match.py` (14 tests) | read code. Not the remediation the register asked for (scope by `phone_number_id`) — that is impossible while RF-5 stands. Residual: when two tenants have both messaged one number, the reply goes to the more recent sender, which is a guess |
| F-SEC-03 onboarding IDOR | HIGH | FIXED | `app/api/onboarding.py:137-143` (foreign `user_id` requires admin); `099f45b`; `tests/test_onboarding_complete_step_authz.py` (7) | read code |
| F-SEC-04 global suppression read / write | HIGH | FIXED | `app/api/ui_support.py:275-293` both handlers `Depends(require_admin)`; `b3ce047`, `e0d4624`; `tests/test_suppression_endpoints_admin_only.py` (10) | read code |
| F-SEC-05 website-builder NULL pool; WhatsApp templates global | MEDIUM | **OPEN** | `app/api/website_builder.py:194-199` (a user with no workspace sees and acts on every `workspace_id IS NULL` page, which includes the marketing site); `app/api/whatsapp_templates.py:98-105` (any logged-in user can create / edit / submit deployment-wide templates) | read code |
| F-SEC-06 debug router allowed in staging | LOW | FIXED | allowlist `DEBUG_ROUTE_ENVS`, `app/api/debug.py:77-85`, `app/main.py:312-327`; `b39c9ed`; `tests/test_debug_router_environment.py` | read code |
| F-AI-01 unbounded AI consumption | HIGH | FIXED per strategy; OPEN per account | see P0-5 | see P0-5 |
| F-AI-02 indirect prompt injection | HIGH | FIXED | `app/services/prompt_safety.py` used by 10 services incl. `reply_classification.py:85-88`, `reply_fraud.py:142-145`; `3a81a05`, `6df0dbe` | read code |
| F-AI-03 non-deterministic judges | MEDIUM | FIXED | `JUDGE_TEMPERATURE` at `app/services/anthropic_client.py:98`, used in `claim_verification.py:407`, `consensus.py:136`, `reply_classification.py:82`, `reply_fraud.py:141`, `reply_intelligence.py:183`, `reply_intent.py:195`, `adversarial_review.py:260`; `c4c8bef`, `4efcd13` | read code |
| F-AI-04 default model id validity | MEDIUM | **OPEN** | default `claude-sonnet-4-6` at `app/config.py:45`, `app/core/config.py:77`; a comment at `app/verification/loop.py:54` says the id was confirmed live; no startup model check exists | grep for a model health check: none. Whether production's model id resolves: UNKNOWN |
| F-OPS-01 firebase-admin missing from image | HIGH | FIXED in manifest; UNKNOWN in image | `pyproject.toml:66`; `1c41d81`; `tests/test_firebase_dependency_declared.py` | read manifest. The image was not built in this phase |
| F-OPS-02 Calendly replay | HIGH | FIXED | `app/integrations/calendly.py:108-115`, tolerance 180 s (`app/config.py:133`); `0233753`, `91dad2c`; `tests/test_calendly_webhook_freshness.py` (17) | read code |
| F-OPS-03 two settings modules | MEDIUM | **OPEN** | `app/config.py` and `app/core/config.py` both exist | `ls` |
| F-OPS-04 Firebase env name | MEDIUM | FIXED | `app/services/notifications.py:93-112` accepts both names; `aa53aa6`; `tests/test_firebase_credentials_env.py` | read code |
| F-OPS-05 misleading ENCRYPTION_KEY warning | LOW | FIXED | `app/core/config.py:452-454` | read code |
| F-OPS-06 no lockfile; manifest drift | MEDIUM | FIXED | `requirements.lock`, `frontend/package-lock.json` exist; `anthropic>=0.28.0` in both manifests | `ls`, grep |
| F-OPS-07 vestigial / CVE-prone deps | POTENTIAL | FIXED (removal); **OPEN** (scan) | `python-jose`, `pandas`, `google-auth*` gone from both manifests (`ed8c0e5`). No `pip-audit` / `gitleaks` / `npm audit` in any workflow | grep manifests and `.github/workflows` |
| F-REL-01 orphaned non-atomic send path | MEDIUM | FIXED | `app/workers/send_tasks.py` deleted (`1c8466d`). A stale mention remains in a docstring at `app/services/send_time_optimizer.py:5` | `ls`, grep |
| F-REL-02 dead task name in monitoring | LOW | FIXED | `app/workers/monitoring.py:28-45`; `tests/test_monitoring_task_names.py` | read code |
| F-DB-01 `playbook_scores` has no tenant column | HIGH (multi-tenant) | **OPEN** | `app/db/models.py:1616-1635` (unique on `pattern_key, variant`, no `user_id`); `app/services/icp_extraction.py:215-228` — the key is a SHA-256 of ICP + tactics and the docstring says sharing across strategies "is the point"; writer `app/workers/learning_tasks.py:146-164` | read code. `CLAUDE.md` calls the product multi-tenant, so the HIGH rating applies. No written P0-D decision was found in the repo |
| F-DB-02 admin playbook-scores bad column | MEDIUM | FIXED | see P0-6 | see P0-6 |
| F-DB-03 missing index on messages | MEDIUM | FIXED | `alembic/versions/0065_messages_dispatch_index.py`; `app/db/models.py:1572` | read migration |
| F-DB-04 redundant `playbook_scores.score` | LOW | **OPEN** | `app/workers/learning_tasks.py:158` binds `:reply_rate` into both columns | read code |
| F-QA-01 order-dependent offline tests | MEDIUM | FIXED | `pyproject.toml:90-97` (`norecursedirs` excludes `tests/integration`) | read config |
| F-QA-02 integrations mock-only | MEDIUM | **OPEN** | 140 `TODO: verify` markers in `app/`, `frontend/src`, `sdk` (the register counted 88; scope of that count is not stated) | grep count |
| F-AI-05 learning-loop poisoning surface | LOW | UNKNOWN | "takes precedence" block still at `app/services/message_personalization.py:92`; the file now imports `prompt_safety` | the mutation text's provenance was not traced end to end in this phase |
| F-AI-06 judge evidence without provenance isolation | LOW | **OPEN** | `app/verification/loop.py:59,269` `_support_block` has no `prompt_safety` use | grep |
| NEW-01 WhatsApp STOP returned 500 | — | FIXED | commit `f9ee4ca`; `tests/test_whatsapp_stop_suppression.py` | commit and test present; code not re-read line by line |
| NEW-02 `/attribution/recompute` swept other tenants | — | FIXED | commit `b5f178e`; `tests/test_attribution_recompute_tenancy.py` | same |
| NEW-03 failed webhook event never retried | — | FIXED | commit `4ab1161`; `tests/test_webhook_claim_release.py` | same |
| NEW-04 suppressed phones matched by format | — | FIXED | commit `4770199`; `tests/test_suppression_phone_normalisation.py` | same |

### 3.3 `docs/NEXT_STEPS.md`

| ID | Status | Note |
|---|---|---|
| P0-A one trunk | FIXED | `evals/`, `eval-gate.yml` and the four P0 test files are all on `master` |
| P0-B suspension | FIXED | F-SEC-01 |
| P0-C Docker manifest | FIXED in manifest; image UNKNOWN | F-OPS-01 |
| P0-D deployment-model decision | **OPEN** | no written decision found; `CLAUDE.md` says multi-tenant |
| P1-A … P1-E | FIXED | F-SEC-02, F-SEC-03, F-AI-01 (per strategy), F-AI-02, F-OPS-02 |
| P1-C per-account cost cap | **OPEN** | P0-5 |
| P1-F suppression tenancy | FIXED | made admin-only rather than tenant-scoped |
| P1-G live vendor proof | **OPEN** | F-QA-02 |
| P2 items | FIXED except F-AI-04, F-OPS-03 | above |
| P3 docs / cleanup | **OPEN** in part | `celerybeat-schedule.{bak,dat,dir}` are still tracked in git; no advisory scan in CI |

### 3.4 `docs/audit-fixes/*` follow-ups that are still open

- `/auth/login` and `/auth/refresh` issue tokens to suspended accounts (P0-3 report). OPEN, LOW.
- Existing `is_stub=true` subscriptions were never audited (P0-2 report). UNKNOWN.
- Two-worker PostgreSQL race test for the send claim (P0-4 report). OPEN.
- `admin_bootstrap.py` hard-coded email (P0-3 report): no e-mail literal found in `app/core/admin_bootstrap.py` now. FIXED.

---

## 4. Offline gate (step 3)

Run in the clean worktree at `2170a55`, Python 3.12.10, Windows 11.
`python3` on this machine is the Microsoft Store stub, so the virtualenv's
`python.exe` was used; the commands are otherwise as `CLAUDE.md` lists them.

**NOT COMPLETED. The offline gate has no result for this baseline.**

| # | Command | Exit | Result |
|---|---|---|---|
| 1 | `python evals/tools/registry_lint.py evals/registry.yaml` | 0 | `IE-06 registry lint: OK`, 1 s |
| 2 | `python evals/run_evals.py` | — | **killed after ~40 minutes** by the Claude Code harness because the machine ran critically low on memory. No junit file and no `evals/candidate.json` were written. Test count, failures and runtime: UNVERIFIED |
| 3 | `python evals/tools/promote.py` | — | not run (needs the candidate from step 2) |
| 4 | `python evals/fixtures/verify_block_fixtures.py` | — | not run |

What is known: the pytest process was alive and consuming CPU for the whole
period (about 1,230 CPU-seconds at minute 36), so it was running tests, not
hung. It ran at the same time as the PostgreSQL suite and the Docker Desktop
stack on the same laptop (16 unrelated containers were also up), which is the
likely reason it was slow and the machine ran out of memory. That is an
explanation, not a measurement.

What this means: sections 3 and 5 stand on their own evidence (code read,
PostgreSQL runs). The claim "the offline suite is green on `master @ 2170a55`"
is **UNVERIFIED locally**. CI is the other source: the `eval-gate` workflow
run for this exact commit concluded `success` on 2026-10-05
(https://github.com/Rmasood1122/LeadPilot/actions/runs/37351754168, read from
the public GitHub API). That run executes the same four commands. Its test
count and runtime were not read (job logs need authentication).

To finish this step: close other workloads, then run the four commands in
`CLAUDE.md` in the `leadpilot-wt-phase0` worktree, on their own.

---

## 5. PostgreSQL suite (step 4)

Target: the local docker compose `db` (PostgreSQL 16, `localhost:5433`) and
`redis` (`localhost:6380`). No `.env` exists in the worktree; `TEST_DATABASE_URL`,
`DATABASE_URL` and `ANTHROPIC_API_KEY` were unset in the shell. Production was
not reachable from this run.

| Command | Exit | Result | Runtime |
|---|---|---|---|
| `python -m pytest tests/integration -q -p no:cacheprovider` | **1** | **54 failed, 70 passed** | 1,137 s (run while the offline suite was also running, so the time is inflated) |
| `python -m pytest -p tests.integration.pg_root_suite tests/test_admin_playbook_scores.py tests/test_playbook_scores.py tests/test_account_suspension.py tests/test_duplicate_send_claim.py -q -p no:cacheprovider` | 0 | 19 passed, on PostgreSQL (`pg_root_suite: root db_session -> localhost:5433/lp_root_run`) | 70 s |

**The integration harness is broken on `master`. It gives no evidence either way.**

Failures by file: `test_flows.py` 20 · `test_compliance.py` 8 ·
`test_notifications_wiring.py` 9 · `test_security.py` 7 · `test_idempotency.py` 6 ·
`test_chunk5_production_launch.py` 4.

Nine failures were rerun individually to read the exception:

- 8 of 9: `RuntimeError: test attempted a real Anthropic call -- use fake_claude`
  raised by the autouse fixture `no_real_anthropic` (`tests/conftest.py:736-749`).
  The integration tests mock Anthropic at the HTTP layer and never request
  `fake_claude`; the root conftest now refuses `get_client()` before any HTTP
  call is made. The tests were last edited 2026-08-20; the guard arrived later.
  These fail in the harness, before the behaviour under test is reached.
- 1 of 9: `TypeError: create_delivery() got an unexpected keyword argument
  'db_session'` (`tests/integration/test_chunk5_production_launch.py:188`) — the
  test calls a signature the code no longer has.

The cause of the other 45 failures is UNVERIFIED (not individually rerun).

Consequences:

- The failing set includes every PostgreSQL test for cross-tenant isolation
  (`TestCrossTenantIsolation`, 6 tests), GDPR lead deletion, suppression at
  send, bounce-rate pause, STOP handling and exactly-once send. **None of these
  behaviours is currently proven on PostgreSQL.** They are proven on SQLite
  only, by the offline suite.
- P0-4 on PostgreSQL: the existing single-test claim logic passes on PostgreSQL
  through `pg_root_suite` (above). A true two-connection race is still not
  tested anywhere.
- Phase 1's `verify-backend-postgres` job cannot be made a required check until
  this harness is repaired. That repair is the first task of Phase 1, and it
  must be done without weakening the tests.

Also confirmed: `alembic upgrade head` on an **empty** PostgreSQL 16 database
reaches `0070_linkedin_network_messages` with exit 0 (throwaway database
`lp_phase0_sqlcheck`, created and dropped locally).

---

## 6. Production (step 5) — read-only HTTP

All times are the server's `Date` header, 2026-10-10 UTC.

| Check | Result |
|---|---|
| `GET https://leadpilot-api-ph3t.onrender.com/health` (first) | 200, `status: degraded`, `celery: no heartbeat key found`, database ok, redis ok |
| `GET https://leadpilot-worker.onrender.com/health` (the URL in `DEPLOY_RENDER_FREE.md:245`) | **404, `x-render-routing: no-server`** — no service has that hostname |
| Real worker hostname | `https://leadpilot-worker-708k.onrender.com` (from the Render service list; it is not written anywhere in the repo) |
| `GET https://leadpilot-worker-708k.onrender.com/health` | 200 after **43 s** (cold start): worker ok, beat ok, redis ok, `heartbeat_key: absent` |
| Same URL ~3 minutes later | 200: `heartbeat_key: present`, ttl 267 |
| `GET …api…/health` ~3 minutes later | 200, **`status: ok`**, `celery: ok, last_beat_seconds_ago: 34` |

**Side effect, stated plainly:** the worker probe woke the sleeping worker. It
consumed whatever was queued and will sleep again about 15 minutes after the
last inbound request. Production is `ok` at the time of writing only because of
that probe.

### Why the heartbeat was missing

1. Beat schedules `refresh_celery_heartbeat` every 60 s (`app/workers/celery_app.py:246`); the task writes Redis key `celery:heartbeat` with a 300 s expiry (`app/workers/beat_heartbeat.py:27-28,41`).
2. The API reports `degraded` when the key is absent or older than 120 s (`app/api/health.py:34-35,80-96`).
3. The worker, beat and a one-route health server run inside one **free Render web service** (`render.yaml`, `scripts/render_worker_entrypoint.sh`). Render stops a free web service after ~15 minutes without an inbound HTTP request, and a stopped service runs no processes — no beat, no heartbeat, no task consumption.
4. Nothing sends that inbound request. The UptimeRobot account has three monitors, all on the **API** URL: one keyword monitor running, two paused. None targets the worker.
5. The experiment above confirms it: one GET, a 43-second cold start, and the heartbeat returned within three minutes with no other change. The code path is healthy; the service was asleep.

Not the cause: Redis misconfiguration (the worker's own check reports redis ok
and the key appears), a crashed child (both PIDs alive), a missing beat entry.

### Fix options for D2

| Option | What to do | Cost | Risk |
|---|---|---|---|
| A. Monitor the worker | UptimeRobot HTTP monitor on `https://leadpilot-worker-708k.onrender.com/health`, 5-minute interval | $0 | An always-awake worker uses ~730 of Render's 750 free instance-hours per month (`DEPLOY_RENDER_FREE.md:256-269`, figures UNVERIFIED against Render's current terms). The API shares the same 750. When they run out Render suspends **all** free services until next month |
| B. Paid background worker | Render Background Worker, $7/mo per `render_worker_entrypoint.sh` (price UNVERIFIED today) | ~$7/mo | none of the above; needs no pinger and no health server |
| C. A + time window | Option A restricted to business hours | $0 | tasks (sends, follow-ups, reply handling) do not run outside the window |

Recommendation: **B**. Option A trades a silent outage now for a total
suspension later in the month.

Related facts found on Render (read-only service list):

- A third service, `leadpilot-workers`, exists and is **suspended by the user**; its auto-deploy is on. `leadpilot-api` and `leadpilot-worker` have auto-deploy **off**, so merges to `master` do not deploy on their own.
- `leadpilot-workers.onrender.com/health` returns 503 (suspended).

---

## 7. Help AI diagnostic (step 6)

Query: `docs/program/help_ai_diagnostic.sql`. Read-only (`BEGIN TRANSACTION
READ ONLY … ROLLBACK`), four result sets: by reason with the mode each reason
proves, answered-vs-ticket, cited FAQ ids, volume. **Not run on production.**
It was executed against an empty local database migrated to head and returned
without error (0 rows).

How to read the result: any row with `mock_faq_match` or `mock_no_match` proves
production answered in mock mode at that time; `answered`, `low_confidence`,
`model_error`, `malformed_response`, `empty_answer` prove live mode.

Confirmed in code: 9 FAQ entries (`app/services/support_kb.py:56-146`),
`MIN_MOCK_MATCH_SCORE = 4` (`support_kb.py:291`), nine distinct reason codes
(`app/services/support_chat.py:151,250,263,278,351,355,364,369,378`).

---

## 8. Proposed fix order

Each is its own branch and PR through the gate. Items 1–2 need a founder
decision before any code.

1. **Decide the deployment model in writing (P0-D).** `CLAUDE.md` says multi-tenant; RF-5, F-DB-01 and F-SEC-05 are only defects under that model. One line in `CLAUDE.md` settles their severity.
2. **GDPR account export and deletion.** Legal exposure with no workaround in the product today; an erasure request can only be met by hand in the database. Needs a founder decision on what is retained (suppression tombstones, audit trail, billing records).
3. **F-DB-01 tenant-scope `playbook_scores`.** Add `user_id`, re-key the upsert, backfill or reset. This is the one confirmed path by which one customer's outcomes change another customer's outreach.
4. **P0-5 per-account AI budget.** A monthly dollar cap per account, checked where the per-strategy cap is checked, covering model calls outside the pipeline.
5. **Plan enforcement.** Call `check_channel` on the send / sequence path and `check_plan_limit` for `max_leads_per_strategy` and `max_sequence_steps`. Paying tiers are currently distinguished by three limits out of the ones advertised.
6. **F-SEC-05.** Dedicated workspace for the marketing site; admin-gate template writes.
7. **RF-5 per-tenant WhatsApp sender.** Largest change; removes the F-SEC-02 heuristic. Until then, state the shared-sender model truthfully in help-center article 10.
8. Then: PostgreSQL two-worker race test (lands naturally in Phase 1 `verify-backend-postgres`), suspended-login issuance, F-AI-04 startup model check, F-OPS-03.

---

## 9. Discrepancies between `STAR_PROMPT.md` and reality (step 7)

| # | Prompt says | Reality |
|---|---|---|
| 1 | Part 0 step 1: save the prompt on `program/setup`, open a PR, merge it | `program/setup` is pushed but **not merged** and has no PR. It is based on `e0d4624` (2026-10-03), 67 commits behind `master`. A session started in that checkout sees pre-audit-fix code and no `docs/FINDINGS_REGISTER.md`. This phase was run in a separate worktree on `master` |
| 2 | `CLAUDE.md` is 66 lines | True on `master`. The `program/setup` checkout has the 59-line older version |
| 3 | `app/api/support.py:187` is `GET /support/faq` | It is at `:178` |
| 4 | Worker URL is in `render.yaml` / deploy docs | `render.yaml` has no URL. `DEPLOY_RENDER_FREE.md:245` gives `leadpilot-worker.onrender.com`, which is 404. The real host has a `-708k` suffix. `DEPLOY_RENDER_FREE.md:155` likewise gives `leadpilot-api.onrender.com` for `PUBLIC_BASE_URL`; the real host is `leadpilot-api-ph3t` |
| 5 | Working method 5 and `<market_research>` cite `coding_standards.md` and `codebase_map` | Neither file exists in the repository |
| 6 | "~1,985 tests" | UNVERIFIED — the offline suite did not complete (section 4) |
| 7 | UptimeRobot: "1 active keyword monitor" able to detect degraded | The keyword monitor has reported **UP for 6 d 14 h** while `/health` was `degraded`. Either its keyword matches a component-level `"status":"ok"` (database, redis) or it is not a must-contain rule. It does not detect a degraded API. Keyword configuration UNVERIFIED |
| 8 | Layer 4: set Render Auto-Deploy to "After CI Checks Pass" | Auto-deploy is currently **off** on both live services. Deploys are manual today |
| 9 | `CLAUDE.md` "Known stale spots": chain is 0001…0047 (49 files) | 72 files, head `0070`. `CLAUDE.md` itself is now stale on this point |
| 10 | D2: production `/health` is degraded | True at the start of this session; `ok` after the step-5 probe woke the worker; will degrade again when it sleeps |

Confirmed as stated: trunk and merged feature branches; three workflows only;
`eval-gate.yml` runs on push and pull_request; the "Not in CI" list;
`sequence_engine.py:453-454` one-click unsubscribe headers;
`bounce_rate_pause_threshold` (0.03, `app/config.py:113`); mailbox-health doc
proxy statement (`docs/features/mailbox-health.md:37-43`); `system_settings.DEFAULTS`;
`plans.PLANS`; `FEATURES.md` 1,179 lines; 31 files in `docs/features/`;
`docs/` excluded from the image by `.dockerignore:92`; repo public while
`README.md:164` says "Private and proprietary"; suspension fix at `auth.py:207`.

---

## 10. Out-of-scope discoveries (reported, not fixed)

1. The working tree of the main checkout has two uncommitted edits that are not from this session: a stripped trailing newline in `tests/conftest.py` and a doubled space in a docstring in `tests/test_activation_script.py`. Left untouched.
2. Git-ignored stray files at the repo root of the main checkout: `c.txt`, `tatus`, `tech.py`, `CLAUDE.local-backup.md`. Not inspected.
3. `celerybeat-schedule.bak/.dat/.dir` are tracked in git (runtime artefacts).
4. `app/services/send_time_optimizer.py:5` documents an integration with `send_tasks.py`, which no longer exists.
5. `requirements.txt:43` still carries a `TODO: verify` on the firebase-admin version.
6. `.dockerignore:92` excludes `docs/` — Phase 2 must change this for the help-center corpus to ship.
7. This file lists open security findings and the repository is public (D3).

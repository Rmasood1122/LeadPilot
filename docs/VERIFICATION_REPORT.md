# Vectorae — Verification Report (adversarial re-check of the prior audit)

**Purpose:** convert the prior audit's findings from *read* evidence into *executed*
evidence, correct whatever does not hold, and state plainly what could not be run.
This pass was instructed to attack the earlier report, not defend it.

**Date:** 2026-10-01 (UTC).
**Primary subject:** branch `integrate/eval-gate-into-feature-8` @ **`934a145`**
(= `feature/8-new-features` `5705e81` with master's eval gate merged; both
`5705e81` and `1ad2cab` verified as ancestors).
**Comparison point only:** `master` @ **`1ad2cab`**.
**Prior report under test:** `docs/FULL_PRODUCT_AUDIT.md` + `docs/FINDINGS_REGISTER.md`.

**Evidence classes used throughout:** `EXECUTED` (command run; command, exit code
and output excerpt given), `READ` (file:line quoted, not run), `UNVERIFIED`.
A `READ` claim is never labelled CONFIRMED.

**No real credentials were used. No vendor API was called. No production or hosted
database was touched.** All work ran against local throwaway PostgreSQL/Redis.
No source, test, or sealed file was modified.

---

## 0. Headline corrections to the prior report

1. **The "branch split" problem is substantially resolved.** The integrate branch
   carries both the P0 fixes and the release gate, and the full gate chain passes
   on it (§1). The prior report's P0-A recommendation has effectively been
   executed. What remains of that finding is narrow and stated in §6.
2. **A new CRITICAL defect was found that the prior (static) audit missed:**
   a WhatsApp **STOP returns HTTP 500 and records no opt-out** on this branch —
   a compliance regression introduced by the Feature 9 consent layer, present on
   `feature/8`/`integrate` and **not** on master (NEW-01, §4).
3. **A new HIGH/MEDIUM tenancy defect was found in the new routers** that no prior
   tenancy audit covered: `POST /attribution/recompute` is an un-gated,
   deployment-wide sweep (NEW-02, §4).
4. **F-OPS-01 is downgraded HIGH → MEDIUM** and its framing corrected: the image
   still boots; only FCM push fails, lazily (§3).
5. **F-OPS-02 is downgraded HIGH → MEDIUM**: replay acceptance is real, but an
   identical re-delivery is a permanent no-op via `ProcessedWebhook` (§3).
6. **F-AI-04 is CLOSED**: `claude-sonnet-4-6` is documented Active, retirement not
   sooner than 2027-02-17 (§5).
7. **The prior report's "no environment exists" statement was wrong as written** and
   is corrected in §5.
8. **F-QA-01 is root-caused** to two specific lines in
   `tests/integration/conftest.py`, and the "PG unavailable" hypothesis is
   experimentally ruled out (§2).

---

## 1. Verdict table

Severity and evidence class are independent. "Prior" = as published in
`docs/FULL_PRODUCT_AUDIT.md`.

| ID | Prior sev | Prior evidence | New evidence | New sev | Verdict |
|---|---|---|---|---|---|
| **F-SEC-01** suspended user keeps API access | CRITICAL | READ (labelled CONFIRMED) | **EXECUTED** (both branches) | CRITICAL *on master*; **n/a on integrate** | **HOLDS on master · CLOSED on the new trunk** |
| **F-SEC-02** WhatsApp inbound matched cross-tenant | HIGH | READ | **EXECUTED** (live exploit) | HIGH | **HOLDS** |
| **F-SEC-03** onboarding `body.user_id` IDOR | HIGH | READ | **EXECUTED** (live exploit) | HIGH | **HOLDS** |
| **F-SEC-04** global suppression PII read + permanent write | HIGH* | READ | **EXECUTED** (live exploit) | HIGH (SaaS) | **HOLDS** |
| **F-SEC-05** website_builder shared NULL pool | MEDIUM* (report said CONFIRMED, register said LIKELY) | READ, inconsistent | **EXECUTED** (read proven; write LIKELY) | HIGH (SaaS) for the read | **HOLDS — inconsistency settled** |
| **F-SEC-06** debug router allows `staging` | LOW | READ | READ | LOW | **HOLDS (READ)** |
| **F-AI-01** `max_strategies` unenforced, no spend cap | HIGH | READ | **EXECUTED** (6 strategies on a 3-cap free plan) | HIGH | **HOLDS** |
| **F-AI-02** indirect prompt injection | HIGH | READ | READ + blind re-check | HIGH | **HOLDS, wording corrected** (§3) |
| **F-AI-03** `temperature` never set | MEDIUM | READ | READ + blind re-check | MEDIUM | **HOLDS (READ)** |
| **F-AI-04** model ID `claude-sonnet-4-6` validity | MEDIUM | UNVERIFIED | **EXECUTED** (vendor doc fetched) | INFO | **CLOSED** |
| **F-AI-05** learning-loop poisoning surface | LOW | READ | READ | LOW | **HOLDS (READ)** |
| **F-AI-06** cross-pipeline context to judge | LOW | POTENTIAL | POTENTIAL | LOW | **HOLDS (POTENTIAL)** |
| **F-OPS-01** `firebase-admin` absent from image deps | HIGH | READ | **EXECUTED** (clean-venv reproduction; docker build NOT runnable) | **MEDIUM** | **HOLDS — DOWNGRADED** |
| **F-OPS-02** Calendly replay | HIGH | READ | **EXECUTED** (stale/future timestamps accepted) | **MEDIUM** | **HOLDS — DOWNGRADED** |
| **F-OPS-03** dual settings modules | MEDIUM | READ | READ (still present on integrate) | MEDIUM | **HOLDS (READ)** |
| **F-OPS-04** Firebase env var mismatch | MEDIUM | READ | READ (still present: `_PATH` read at notifications.py:81, `_JSON` declared at core/config.py:120) | MEDIUM | **HOLDS (READ)** |
| **F-OPS-05** misleading ENCRYPTION_KEY warning | LOW | READ | **EXECUTED** (warning observed at every boot) | LOW | **HOLDS** |
| **F-OPS-06** no lockfile / manifest drift | MEDIUM | READ | READ | MEDIUM | **HOLDS (READ)** — note a tracked `frontend/package-lock.json` does exist, so the prior "no lockfile in this path" aside was imprecise |
| **F-OPS-07** vestigial/CVE-prone deps | POTENTIAL | POTENTIAL | POTENTIAL (no scan run) | POTENTIAL | **UNVERIFIED — unchanged** |
| **F-REL-01** duplicate non-atomic send path | MEDIUM | READ | READ (still present on integrate; still no live caller) | MEDIUM | **HOLDS (READ)** |
| **F-REL-02** dead task-name reference | LOW | READ | READ | LOW | **HOLDS (READ)** |
| **F-DB-01** `playbook_scores` has no tenant column | HIGH* | READ | **EXECUTED** (live PG schema) | HIGH (SaaS) | **HOLDS** |
| **F-DB-02** phantom `ps.user_id` + swallow | MEDIUM | READ | **EXECUTED** (absent on integrate) | MEDIUM *on master only* | **HOLDS on master · CLOSED on the new trunk** |
| **F-DB-03** no index on `messages.status`/`scheduled_at` | MEDIUM | READ | **EXECUTED** (live `pg_indexes`) | MEDIUM | **HOLDS** |
| **F-DB-04** redundant `playbook_scores.score` | LOW | READ | READ | LOW | **HOLDS (READ)** |
| **F-QA-01** order-dependent failures | MEDIUM | EXECUTED (symptom only) | **EXECUTED + root-caused** | MEDIUM | **HOLDS — mechanism corrected** |
| **F-QA-02** integrations mock-only | MEDIUM | READ | READ | MEDIUM | **HOLDS (READ)** |
| **NEW-01** WhatsApp STOP 500s, opt-out lost | — | — | **EXECUTED** | **CRITICAL** | **NEW** |
| **NEW-02** `POST /attribution/recompute` un-gated global sweep | — | — | READ (×2 independent) | **MEDIUM–HIGH** | **NEW** |

Totals: **27 prior findings** → 20 HOLD, 2 CLOSED on the new trunk
(F-SEC-01, F-DB-02 — both still hold on master), 1 CLOSED outright (F-AI-04),
2 DOWNGRADED (F-OPS-01, F-OPS-02), 1 inconsistency settled (F-SEC-05),
1 remains UNVERIFIED (F-OPS-07). **0 REFUTED.** **2 NEW** findings.

---

## 2. Evidence log — Task 1 (gate chain) and Task 5 (test order)

### Gate chain on `integrate` @ `934a145` — all four in order

| # | Command | Exit | Output excerpt |
|---|---|---|---|
| 1 | `python3 evals/tools/registry_lint.py evals/registry.yaml` | **0** | `IE-06 registry lint: OK (evals/registry.yaml)` |
| 2 | `python3 evals/run_evals.py` | **0** | `compliance_suite_pass_rate 1.000000` · `full_suite_pass_rate 1.000000` · `offline_test_count 2827.000000` · `suite_runtime_s 486.330000` (wall 508s) |
| 3 | `python3 evals/tools/promote.py` | **0** | `compliance… hard 1.0000 PASS` · `full… hard 1.0000 PASS` · `offline_test_count hard 2827.0000 vs base 1985.0000 PASS` · `suite_runtime_s soft 486.3300 vs 201.9960 band 120 **WARN**` · **`DECISION: PROMOTE (1 soft warning(s) -> human review)`** |
| 4 | `python3 evals/fixtures/verify_block_fixtures.py` | **0** | `PROVEN: compliance_suite_pass_rate gate fires` · `PROVEN: full_suite_pass_rate gate fires` · `PROVEN: offline_test_count gate fires` · `PROVEN: healthy candidate PROMOTEs` · `All 3 hard gates proven to fire` |

**Comparison with the founder's Windows run** (compliance 1.0, full 1.0, 2827 tests,
PROMOTE, 1600s soft WARN): **test count matches exactly (2827)**, both pass rates
match, and the PROMOTE-with-one-soft-runtime-WARN outcome matches. Only the absolute
runtime differs (486s here vs 1600s there) — faster hardware; the WARN fires in both
because the baseline is master's 202s.

*One honest note:* my first `run_evals` attempt exited **127** because I wrapped it in
`/usr/bin/time`, which does not exist in this image (`bash: /usr/bin/time: No such
file or directory`). That run produced no gate result; it was re-run cleanly and the
table above is from the re-run.

### GitHub Actions (public, unauthenticated API)

```
GET /repos/Rmasood1122/LeadPilot/actions/runs?branch=integrate/eval-gate-into-feature-8
→ total_count: 1
  name: eval-gate · run_number: 6 · event: push
  head_sha: 934a145cfb23e24900779e8188d156c658850bee
GET /repos/Rmasood1122/LeadPilot/actions/runs/36854665426
→ status: completed · conclusion: success
```
**URL:** https://github.com/Rmasood1122/LeadPilot/actions/runs/36854665426
CI independently corroborates the local gate result on the exact audited commit.

### Task 5 — test-order claim: REPRODUCED and root-caused

| Command | Exit | Result |
|---|---|---|
| `pytest tests/ -q` (integration **included**) | 1 | **9 failed, 2818 passed, 7 skipped, 124 errors** in 451s |
| `pytest -q --ignore=tests/integration tests` (= the gate) | 0 | **2827 passed, 0 failed** |
| the 9, per-file / isolated | 0 | **all pass** |

Failure mode captured verbatim:
```
tests/test_whatsapp_webhooks.py:87: assert wa_signed_post(...).json()["processed"] == 1
E   KeyError: 'processed'
--- Captured log setup ---
WARNING app.services.notification_service:notification_service.py:72
  admin lookup failed: (sqlite3.OperationalError) no such table: users
```

**Root cause — `tests/integration/conftest.py`, session-scoped `pg_engine`:**
```
:141  previous_bind = db_base.SessionLocal.kw.get("bind")
:142  db_base.SessionLocal.configure(bind=engine)   # mutates the APP global in place
:143  db_base.engine = engine                      # mutates the APP global
:145  yield engine
:147  db_base.SessionLocal.configure(bind=previous_bind)   # restores ONLY the bind
```
Two defects: `db_base.engine` (set at :143) is **never** restored — there is no
counterpart to :147 — and because the fixture is **session-scoped**, even the
partial restore runs only at the very end of the run, after the offline tests in the
same invocation have already executed against the rebound global.

**Discriminating experiment that rules out the obvious hypothesis:** with PostgreSQL
*down* on :5433 → 9 failed/124 errors; with a **working** PostgreSQL supplied via
`TEST_DATABASE_URL=...@localhost:5432/clienthunter_test` (49 integration tests
passing) → the WhatsApp tests **still fail** (12 failed, 75 errors). So the trigger is
the global rebinding, **not** PostgreSQL being refused. The prior report's symptom was
right; its stated mechanism ("state/import pollution when the integration dir is
co-collected") was vague and is now replaced by the lines above.

The gate and CI are legitimately green because both exclude `tests/integration`.

---

## 3. Evidence log — Task 2 (exploitation) and Task 3 (weak labels)

**Environment for all exploits:** PostgreSQL 16.13, fresh database, `alembic upgrade
head` → **exit 0**, head **`0064_meeting_practice`**, **66** migration files, **95**
tables. App booted with uvicorn; `GET /health` → **200**
`{"database":{"status":"ok"},"redis":{"status":"ok"},"celery":{"status":"degraded"}}`
(celery degraded = no worker running, expected). Users created through the **real**
`/auth/signup` (201) + `/auth/login` (200) flow.
A = `35b1a164-c716-4dac-9f0a-c73e8e0e0727`, B = `0ee37ed3-dfba-4661-8f8f-a1c65f019309`.

### F-SEC-01 — EXECUTED on **both** branches

*integrate (port 8099), after `UPDATE users SET is_suspended=true`:*
```
GET /auth/me        bearer -> HTTP 403
GET /strategies     bearer -> HTTP 403
GET /strategies     lpk_   -> HTTP 403      body: {"detail":"account suspended"}
POST /auth/login           -> HTTP 200      (token issued, but inert everywhere)
```
*master (own DB at head 0047, port 8098), same steps:*
```
GET /auth/me        bearer -> HTTP 200
GET /strategies     bearer -> HTTP 200
GET /strategies     lpk_   -> HTTP 200
```
Baseline before suspension on both: 200. **Verdict: HOLDS on master (CRITICAL,
now proven by exploitation), CLOSED on the new trunk.**

### F-SEC-02 — EXECUTED (live cross-tenant write)

Seeded A-lead and B-lead sharing phone `+14155550199`, each via a correct
product→strategy ownership chain. Sent a webhook with a **valid**
`X-Hub-Signature-256` for `phone_number_id=tenantA-phone-id-111` (**tenant A's**),
body `STOP`:
```
inbound_replies.lead_id = bbbbbbbb-…-003  = "B Lead"   <-- WRONG tenant
inbound_replies.account_ref = tenantA-phone-id-111     <-- discriminator was stored, then ignored
leads: B Lead  contacted -> replied   |  A Lead untouched
```
An earlier run matched **A** first, so the selection is **arbitrary first-match**,
not a fixed bias — worse than a consistent error. **HOLDS (HIGH).**

### F-SEC-03 — EXECUTED (live cross-user write)

```
B onboarding_state BEFORE: {}
POST /onboarding/complete-step   (A's own bearer token)
  body {"step":"product_created","user_id":"<B's uuid>"}   -> HTTP 200 {"status":"ok"}
B onboarding_state AFTER : {"step_completed": ["product_created"]}
A onboarding_state AFTER : {}        <-- the write landed on B, not A
```
**HOLDS (HIGH).**

### F-SEC-04 — EXECUTED (both halves)

```
B POST /suppression  b-private-prospect@bcompany.example.com      -> 201
A GET  /suppression                                                -> 200 and RETURNS B's entry
A POST /suppression  b-top-customer@bcompany.example.com           -> 201
B GET  /suppression  -> now shows A's permanent block on B's target
schema: suppression_list = id,ts,email,phone,reason   <-- NO tenant column at all
```
Global *enforcement* at send time remains the right compliance posture; the unscoped
*listing* and the irreversible cross-tenant *write* are the defect. **HOLDS (HIGH on
multi-tenant SaaS).**

### F-SEC-05 — EXECUTED; the report/register inconsistency is settled

Free plan gates the website builder (`402 plan_limit_exceeded`), so both users were
set to `starter` for this test.
```
B POST /site/pages -> 201 ;  DB workspace_id = NULL          (the shared pool)
A GET  /site/pages/<B's page id> -> HTTP 200 with FULL content (title, meta, brief)
A GET  /site/pages               -> lists 'b-private-page'
A PATCH /site/pages/<B's id>/publish -> HTTP 409 "this page has not been generated yet"
```
The 409 is a **lifecycle** check, **not** an authorization check — no owner check sits
in that path. **Cross-tenant READ = EXECUTED/CONFIRMED. Cross-tenant WRITE = LIKELY.**
That resolves the prior report (CONFIRMED) vs register (LIKELY) split: the read is
confirmed, the write stays LIKELY.

### F-AI-01 — EXECUTED

Free plan `max_strategies = 3` (`app/core/plans.py`). Fresh free account:
```
POST /products/{id}/strategies  x6  ->  202, 202, 202, 202, 202, 202
DB count of strategies for that user = 6
```
Test conditions stated honestly: `RATE_LIMIT_STRATEGIES` was raised to 1000 to
isolate the **plan** cap from the rate limit, and `CELERY_TASK_ALWAYS_EAGER=false`
so no pipeline actually ran (admission control only). In production the only
remaining control is that rate limit (default 2/hour ≈ 48/day), which bounds the
*rate* but never the *total* and is not the cap the product sells.
`check_plan_limit` is called **once** in the whole tree, for `max_site_pages`
(`app/api/website_builder.py:228`). Grep for
`spend_cap|budget_cap|max_spend|token_budget|cost_ceiling|monthly_budget|spend_limit`
over `app/` → **empty**; `usage_meter` exposes only
`note/price_micros/_flush/scope` (records, never enforces). **HOLDS (HIGH).**

### F-OPS-01 — EXECUTED by faithful reproduction; **DOWNGRADED HIGH → MEDIUM**

`docker build` **could not be run**: the daemon started fine (29.4.3) but Docker Hub
is blocked by the environment's proxy —
```
Head "https://registry-1.docker.io/v2/library/python/manifests/3.11-slim": Forbidden
```
and no base image is cached. Reported as **not executed**, per the no-fabrication rule.

Substitute that reproduces the Dockerfile's dependency layer exactly (`COPY
pyproject.toml ./` + `pip install .`, lines 41-42), in a clean venv, exit 0:
```
import firebase_admin  -> ModuleNotFoundError: No module named 'firebase_admin'
import structlog       -> OK 26.1.0                      (control: env is healthy)
firebase in pyproject.toml = 0 occurrences ; in requirements.txt = 2
```
Then layer 46 (`pip install --no-deps .`) and:
```
import app.main -> IMPORT OK
```
**The correction:** the image **does** boot, and the import is lazy and guarded —
`app/services/notifications.py:72-79` raises a clear `ImportError` with a pip hint
only when a push is attempted. The prior report called this "the same defect class
that once broke the entire image" (structlog). That **overstated** it: structlog broke
`import app.main`; this does not. Real impact = **FCM push fails at call time**.
**MEDIUM.**

### F-OPS-02 — EXECUTED; **DOWNGRADED HIGH → MEDIUM**

Valid HMAC over `{t}.{body}`:
```
t = now              -> HTTP 200
t = 30 DAYS old      -> HTTP 200
t = 365 DAYS old     -> HTTP 200
t = 30 days in FUTURE-> HTTP 200
CONTROL wrong signature -> HTTP 401 {"detail":"invalid webhook signature"}
CONTROL empty header    -> HTTP 401
```
So signature verification **is** enforced and the test was meaningful; only freshness
is absent. Two qualifications that drive the downgrade: all four were
`{"quarantined":true,"reason":"no tenant id"}` because my payload carried no tenant
tracking param — replay **acceptance** is proven, the downstream booking effect is
not — and `ProcessedWebhook(provider,event_id)` makes an **identical** re-delivery a
permanent no-op (`app/api/webhooks.py:85-93`). Residual risk is a *distinct* captured
event replayed later. **MEDIUM.**

### F-AI-02 — wording corrected (still HOLDS, HIGH)

The blind reviewer (§4) returned **PARTLY** and is right. The prior report said the
external text is injected "with no delimiting". In fact each block carries a labelled
header and post bodies sit inside double quotes
(`personalization_context.py:163,173`). Those quotes are **unescaped**, so hostile
text containing `"` or a newline can break out, and no system instruction anywhere
tells the model to treat the block as data. Corrected claim: **labelled but
unescaped, with no injection-mitigation instruction** — the finding stands, the
absolute phrasing does not.

### F-DB-01 / F-DB-03 — EXECUTED against the live schema

```
columns of playbook_scores: id,last_aggregated_at,decay_half_life_days,
  effective_sample_size,oldest_outcome_ts,score,sample_size,created_at,updated_at,
  reply_rate,booking_rate,is_reliable,pattern_key,metric,variant,trend
  -> NO user_id / tenant column                                  (F-DB-01 HOLDS)
pg_indexes on messages: ix_messages_lead_id, ix_messages_origin,
  ix_messages_sequence_id, pk_messages
  -> NO index on status or scheduled_at                           (F-DB-03 HOLDS)
```
Both were READ-only in the prior report; both are now **EXECUTED**.

---

## 4. New findings

### NEW-01 — WhatsApp **STOP** returns HTTP 500 and records **no** opt-out · CRITICAL · EXECUTED
**Branch:** `integrate` / `feature/8`. **Not on master.**

```
POST /webhooks/whatsapp   (valid X-Hub-Signature-256, text body "STOP")
  -> HTTP 500 {"error":"internal_server_error"}
  suppression_list rows afterwards = 0
```
Reproduced with a **single** tenant, one lead, and an empty `suppression_list`, so it
is **unconditional** and not an artifact of the cross-tenant setup. Deterministic
across repeats.

Proven call chain, taken from the live traceback:
```
app/api/webhooks_whatsapp.py:163  whatsapp_webhook
 -> app/api/webhooks_whatsapp.py:368  _handle_inbound -> optin_svc.revoke_opt_in(
 -> app/services/whatsapp_optin.py:219  consent.suppress_everywhere(
 -> app/services/consent.py:303  db.commit()
IntegrityError: duplicate key value violates unique constraint "ix_suppression_list_phone"
DETAIL:  Key (phone)=(+14155550199) already exists.
```
The failing batch INSERT carried **three** rows with `phone__0 == phone__2`.

**Root cause (code + config, both verified):** `whatsapp_optin.py:206-208` adds a
phone `SuppressionEntry` behind an `is_suppressed(...)` guard that reads **committed**
rows only; `:219` then calls `consent.suppress_everywhere`, whose phone guard at
`consent.py:253` is equally blind, so it adds **the same phone again in the same
session**; `app/db/base.py:36` configures `SessionLocal = sessionmaker(...,
autoflush=False, ...)`, so the first pending row is never flushed and neither guard
can see it. `consent.py:303 db.commit()` flushes both → `UniqueViolation`, whole
transaction rolls back. (A default `autoflush=True` sessionmaker does **not**
reproduce it — which is why my isolated repro passed and why the suite stays green.)
`suppress_everywhere`'s docstring claim "Idempotent: suppressing twice adds no
duplicate rows" is false **within one transaction**.

**Why the tests miss it:** `tests/test_whatsapp_cross_channel.py` +
`tests/test_consent.py` + `tests/test_whatsapp_optin_audit.py` = **45 passed** on this
branch. The unique index **does** exist in the SQLite test schema (migration 0001
lines 44-45, `unique=True`; confirmed via `Base.metadata.create_all`), so the schema
is not the gap — the test sessions do not reproduce the `autoflush=False` +
both-identifiers state a live request has.

**Provenance:** introduced by commit **`4612e30`** "Feature 9: compliance and consent
layer" (`git log -S`). master has no `app/services/consent.py` and performs only the
single phone suppression, so master's STOP path is intact.

**Impact:** a WhatsApp STOP is never recorded — no suppression row, no consent-ledger
entry — and Meta will retry the delivery and fail identically every time. The
lead-status side effect (→ `replied`) persists from an earlier commit, leaving
**reply recorded / opt-out lost**. Against a stated zero-tolerance CAN-SPAM/GDPR
posture this is a shipping blocker for this branch.

**Remediation:** make the suppression write idempotent at the database level
(`ON CONFLICT DO NOTHING`), or flush before the second guard, or have `revoke_opt_in`
delegate the phone write entirely to `suppress_everywhere`. **Verify:** POST the same
signed STOP → expect 200 and exactly one `suppression_list` row for the phone;
re-POST → still 200, still one row. Add a regression test with a lead holding **both**
email and phone, driven through the HTTP webhook on the `autoflush=False` session.

### NEW-02 — `POST /attribution/recompute` is an un-gated deployment-wide sweep · MEDIUM–HIGH · READ (verified twice, independently)

`app/api/attribution.py:62-72` declares the route with `Depends(get_current_user)`
and **no** `require_admin`, then calls `attribution.run_sweep(db, limit=limit)` —
`current_user` is never passed on (unlike its sibling routes, which call
`attribution.ledger(db, current_user.id, …)`). `app/services/attribution.py:261`
`def run_sweep(db, now=None, limit=500)` takes **no** user parameter and selects
globally (`select(Outcome).where(...).order_by(Outcome.ts.desc()).limit(limit)` plus a
full `select(AttributionEntry.outcome_id)` scan).

Any authenticated tenant can therefore drive `AttributionEntry` **writes** into every
other tenant's ledger and read back deployment-wide `checked/recorded/skipped/failed`
counts — a pollable signal of other tenants' outcome volume. No row-level content of
another tenant is returned. Because the `limit` window is ordered globally by
`Outcome.ts`, *who presses it* decides whose outcomes get credited.

Found by the new-router tenancy sweep (§7) and independently re-confirmed in the
blind re-check (C10). **Remediation:** add `require_admin` (matching how
`compliance_rules.py` treats deployment-wide operations) or thread a `user_id` into
`run_sweep` and scope through `lead → strategy → product → Product.user_id`. The
scheduled worker can keep calling it unscoped. **Verify:** a non-admin gets 403; an
admin-run sweep is unchanged. Note `tests/test_attribution.py:340-341` covers this
route for idempotency only — nothing asserts scoping.

---

## 5. Task 4 — closures and corrections

### F-AI-04 — **CLOSED**
Fetched `https://platform.claude.com/docs/en/about-claude/model-deprecations`:
```
| claude-sonnet-4-6          | Active     | N/A                | Not sooner than February 17, 2027 |
| claude-sonnet-4-5-20250929 | Deprecated | September 30, 2026 | November 30, 2026                 |
```
`claude-sonnet-4-6` is **Active**; retirement not sooner than **2027-02-17**. The
default in `app/config.py:45` / `app/core/config.py:77` is correct and current — and
notably `claude-sonnet-4-5` is already **deprecated**, so the code is on the right
model. **Closed.** *Migration note:* plan to move off `claude-sonnet-4-6` before
**2027-02-17**; the prior recommendation of a startup model-ID health-check still has
independent value, because a wrong ID is classified PERMANENT and would fail every
strategy terminally with no fallback.

### Correction — the "no environment exists" claim was wrong as written
The prior report stated "**No production/staging environment** — none exists" and
"Operational prerequisites — Not stood up". I am told a hosted PostgreSQL database
with **6 real accounts** existed on **2026-09-16**, per an account report on the
founder's machine that I cannot see. I cannot verify that artifact (it is
uncommitted and outside this environment) — it is therefore **UNVERIFIED** here — but
it **contradicts** the claim as published, and the claim should not have been stated
absolutely. Two things went wrong: I inherited it from `reports/LP-T-004`, which
actually says "no environment has been stood up or verified **by this project**" — a
scoped statement about the audit project — and I over-generalised it to "none
exists". **Corrected statement:** no environment was available *to this audit*;
whether one exists operationally was outside my visibility.

**Re-rating of anything that depended on it:** no finding's severity was derived from
"no environment exists" — it appeared only in the production-readiness category table
(§14) and the limitations list (§17) of the prior report. One consequence does change
direction, and it raises severity rather than lowering it: if a real deployment with
real accounts exists, then the SaaS-dependent findings (**F-SEC-04, F-SEC-05,
F-DB-01**, and the multi-tenant reading of **F-SEC-02/03** and **NEW-02**) should be
treated at their **higher** multi-tenant severity rather than deferred pending the
deployment-model decision, and **NEW-01** (STOP lost) would be live against real
contacts the moment that branch ships. The prior report's P0-D ("decide the
deployment model") is correspondingly less open than it was written.

### F-SEC-01 re-rated against the integrate branch, and what remains of the branch split
F-SEC-01 is **master-only**. On `integrate` the fix is present and
**proven by exploitation** (§3): suspended users get 403 on bearer, `/auth/me`, and
`lpk_` API keys. Against the new trunk the finding is **CLOSED**. It stays CRITICAL
for `master` for as long as `master` is the default branch that a deploy or a
visitor would pick up.

**What remains of the "branch split" finding:** the substance is resolved — one branch
now carries both the P0 fixes and the gate, the gate chain passes on it, and CI is
green on that exact commit. Three residues remain, and they are bookkeeping rather
than engineering: (1) `master` is **still the default branch** and still carries
F-SEC-01 (CRITICAL) and F-DB-02, so the fixes are not yet what the world sees;
(2) `integrate/eval-gate-into-feature-8` has not been merged into `master` or made
default, so the two histories still diverge; (3) the stale branches
(`feature/engagement-hub`, `feature/tool-integrations`, both with zero unique commits)
and the two near-duplicate lines (`vercel/…`, `claude/confident-franklin-…`) are still
present. The prior report's P0-A is therefore **substantially done**, with "promote
this branch to default" as the remaining step.

---

## 6. Task 6 — blind independent re-check

A second agent was given **only** the finding IDs and file:line citations for the HIGH
and CRITICAL items, was instructed not to read anything under `docs/`, and had not
seen this or the prior report. Result: **8 CONFIRMED, 2 PARTLY, 0 REFUTED, 0 CANNOT
TELL.** The two disagreements are quoted verbatim and both are accepted.

**C6 (F-AI-02) — PARTLY.** Verbatim:
> "Does not hold: it is not entirely undelimited — each block has a labeled header
> ("RECENT LINKEDIN POSTS BY THIS LEAD (their own words)…") and post bodies sit inside
> double quotes; that delimiter is unescaped, so hostile text containing `"` or a
> newline can break out of it, but "no delimiting" overstates the code."

*Accepted.* The prior report's wording is corrected in §3. The finding stands.

**C8 (F-OPS-02) — PARTLY.** Verbatim:
> "Does not hold as stated: a replayed capture does not re-execute — the route records
> `ProcessedWebhook(provider="calendly", event_id=event_id)` first and, on
> `IntegrityError`, returns `{"ok": True, "duplicate": True}` (app/api/webhooks.py:85-93),
> and `event_id` is derived from the signed payload, so an identical replay is a
> permanent no-op."

*Accepted* — it matches the qualification my own live test surfaced, and it is the
basis for the HIGH → MEDIUM downgrade. The reviewer also noted that Recall, HubSpot,
Salesforce, `webhook_delivery` and Stripe **all** carry explicit tolerance constants
while Calendly carries none, which strengthens the "inconsistent, should be fixed"
reading.

The reviewer also independently confirmed C1–C5, C7, C9, C10, including the
master-only F-SEC-01 and the new NEW-02. Its C9 note adds detail the prior report did
not have: `pattern_key` is a content hash of canonical ICP/tactic JSON
(`models.py:890`), and `lead_scoring.py:152-157` reads the shared row with no user
filter — so two tenants whose strategies hash alike genuinely share one score row.

---

## 7. Task 7 — scope gaps on the 39 new commits

### What was **not** audited on this branch
The prior report verified the *presence* and *offline test status* of the twelve
"Feature N" additions but did **not** functionally exercise any of them. Specifically
**not** audited, then or now: the business correctness of Features 1–12 (positive-reply
classifier, F-P-T-A scoring, sequence-completion guarantee, mailbox-health
auto-throttle, send-review queue, unified inbox, re-engagement memory, attribution
ledger, consent layer, data provenance, agency-mode client workspaces, meeting
practice/roleplay); the agency-mode migration **0063** beyond its clean application;
the **Recall.ai** recording integration against the live vendor; the review-queue and
inbox **UI**; and the new **frontend** surfaces (`clients`, `inbox`,
`admin/compliance-rules`, the analytics panels). Also still unaudited, as before:
provider client internals, `sdk/` runtime, `nginx/`, `railway/`, `render.yaml`, and
on-device mobile.

### Ownership-filter review of the ten new routers (the real gap)
All **51** routes across `attribution.py`, `benchmarks.py`, `client_workspaces.py`,
`compliance_rules.py`, `consent.py`, `inbox.py`, `practice.py`, `recording.py`,
`reengagement.py`, `send_reviews.py` were traced, helpers opened and verified.

**Result: 1 problem in 51 routes.**

| File:line | Route | Verdict |
|---|---|---|
| `app/api/attribution.py:72` | `POST /attribution/recompute` | **MISSING FILTER** → NEW-02 |

The other 50: **42 OK** (canonical `Product.user_id` chain or a direct `user_id`
scope, 404-never-403), **5 ADMIN-ONLY** (`compliance_rules.py`, correctly behind the
strong `require_admin` that refuses API keys and resolves to `request.state.actor`),
**3 GLOBAL-BY-DESIGN** (the static compliance-requirements table; the k-anonymised
benchmark buckets — `HARD_MIN_ACCOUNTS = 5` floor, percentiles rounded to 0.5pp,
suspended accounts excluded; the Recall webhook — fail-closed 503 without a secret,
Svix signature over the raw body, delivery-id idempotency, and target resolution by
provider-issued `bot_id` cross-checked against `metadata.meeting_id`).

Every fetch-by-primary-key path checked (`inbox.py:100`, `practice.py:167`,
`compliance_rules.py:145`) either verifies ownership before use or sits inside an
admin-only route. Noted as **out of scope but worth triage** (intra-tenant RBAC, not
tenancy): `POST /strategies/{id}/client` (`client_workspaces.py:206`) applies a rate
limit but not `_require_manager`, and `/strategies` is absent from
`rbac.SDR_BLOCKED_PREFIXES`, so an SDR can re-file a campaign under a different
client — which changes both which invoice its meetings land on and which
sending-domain pool constrains it. Cross-tenant safety is unaffected.

---

## 8. What could **not** be executed, and why

| Item | Why |
|---|---|
| `docker build` / in-image `import firebase_admin` | Docker Hub blocked by the environment proxy: `Head "https://registry-1.docker.io/v2/library/python/manifests/3.11-slim": Forbidden`; no cached base image. Daemon itself started (29.4.3). Substituted by a faithful clean-venv reproduction of the Dockerfile's dependency layer (§3). |
| Any live third-party API (Apollo, Hunter, Gmail, Meta/WhatsApp, Calendly, Stripe, Recall, Firebase, NewsAPI) | No credentials, and calling real vendors was out of bounds. **F-QA-02 stays READ.** |
| Live Anthropic model calls | No API key. The 72/144-step pipeline and the 10-pass verification loop were never executed against a real model; `FakeClaude` only. |
| The hosted database with 6 real accounts (2026-09-16) | Not in this environment and out of bounds. **UNVERIFIED** (§5). |
| `tests/integration/` as a passing suite | Needs PostgreSQL on :5433 per its own default. With a working PG supplied on :5432, 49 of them passed and 75 still errored; I did not pursue full integration-suite green, as it was not the task. |
| `F-OPS-07` dependency advisories | No `pip-audit`/`safety` run; no CVE asserted. **UNVERIFIED, unchanged.** |
| On-device mobile (Capacitor) | No device. |
| `F-SEC-05` cross-tenant **write** | A's publish hit a 409 lifecycle gate before any owner check could be reached; proving the write needs a generated page. **LIKELY, not CONFIRMED.** |
| `F-AI-02` end-to-end injection | Would need live model calls; the injection *surface* is READ-verified, the *exploit* is not. |

Two process notes, for transparency: my first `run_evals` invocation exited **127**
(`/usr/bin/time` absent) and produced no result — it was re-run cleanly. During the
F-SEC-02 setup I seeded a strategy with an invalid enum (`status='complete'`), which
produced a 500 and a partial write; I reset the state and re-ran the exploit from a
verified-clean baseline, and the result reported in §3 is from that clean run.

---

## 9. Integrity statement

I tested **`integrate/eval-gate-into-feature-8` @ `934a145cfb23e24900779e8188d156c658850bee`**
as the primary subject and **`master` @ `1ad2cab684e5a0b1d3dd34fae043b807113f2b60`**
as a comparison point only, with `feature/8-new-features` @ `5705e8170e7ae0d7252734532c9d4710b8c7a1ef`
confirmed as an ancestor of the former. On the integrate branch the documented gate
chain ran clean in order — `registry_lint` (0), `run_evals` (0; compliance 1.0, full
1.0, 2827 tests), `promote.py` (0; **PROMOTE** with one soft runtime WARN),
`verify_block_fixtures` (0; all three hard gates proven to fire) — and GitHub Actions
run 36854665426 on that exact commit concluded **success**. Against a fresh local
PostgreSQL 16 the 66 migrations applied cleanly to head `0064_meeting_practice` and
the application booted and served. Of the 27 prior findings, **20 HOLD, 3 are CLOSED**
(F-AI-04 outright; F-SEC-01 and F-DB-02 on the new trunk only — both still hold on
master), **2 are DOWNGRADED** (F-OPS-01, F-OPS-02), **1 inconsistency is settled**
(F-SEC-05), **1 remains UNVERIFIED** (F-OPS-07), and **none was refuted**; seven
previously READ-only findings were converted to EXECUTED by live exploitation, and two
wordings (F-AI-02, F-QA-01) plus one claim ("no environment exists") were corrected as
overstated. **Two new findings** were discovered that the prior static pass missed:
**NEW-01**, a CRITICAL compliance regression in which a WhatsApp STOP returns HTTP 500
and records no opt-out — introduced by commit `4612e30`, absent on master, invisible
to 45 green tests — and **NEW-02**, an un-gated deployment-wide attribution sweep. I
modified no source, test, or sealed file; the only repository changes are this document
and the scripts under `docs/verification/`. I used no real credentials, called no
vendor API, and touched no production or hosted system; everything I could not run is
listed in §8 rather than inferred.

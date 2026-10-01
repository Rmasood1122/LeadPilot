# LeadPilot — Full Product Audit (Independent Re-Evaluation)

> Independent, evidence-driven re-evaluation of the complete LeadPilot /
> ClientHunter Enterprise product across all branches. This report does **not**
> inherit the conclusions of any prior evaluation; prior findings were treated
> as claims to investigate, not ground truth.

**Auditor role:** Independent product auditor (software architecture, AI/LLM
engineering, security, QA, repository forensics).
**Audit date:** 2026-10-01 (UTC).
**Repository:** `https://github.com/Rmasood1122/LeadPilot`
**Method:** full-history clone, static reading of actual implementation on every
relevant branch, dependency installation, and live execution of test suites,
the release gate, type-checks and build on a real toolchain.

---

## 1. Executive Summary

LeadPilot is a **substantial, genuinely-built product**, not a façade. The core
claims — a 72/144-step Anthropic research pipeline, a 10-pass verification loop,
Apollo/Hunter lead sourcing, Gmail + WhatsApp outreach, Calendly booking, an A/B
learning loop, a compliance layer, GDPR erasure, Fernet-at-rest, JWT auth — are
backed by real, executed code (see §6, §14). The backend is ~85–105 service
modules, ~52–62 API routers, 49–66 migrations and 1,985–2,834 offline tests
depending on branch. Engineering discipline in several areas (the Anthropic
error taxonomy, the release gate, webhook signature verification, migration
hygiene, the ownership-filter house rule) is **above the level typical for a
solo-founder product.**

The audit nevertheless surfaces one **CRITICAL** issue, a cluster of **HIGH**
issues, and — most importantly — a **structural problem that frames everything
else:**

> **The product has split into two incompatible branches, and neither is
> complete.** `master` carries the release-gate/CI quality infrastructure and a
> newer internal tenancy audit, but **none** of the founder's P0 remediation
> work. `feature/8-new-features` carries **all** the P0 fixes plus twelve new
> features and seventeen new migrations, but has **no release gate and no CI**.
> The P0 fixes the founder believes are "done" are **absent from the default
> branch a visitor, a deploy, or a new evaluator would see.**

This single fact explains the founder's experience that "some of the previous
evaluation may have been incorrect" and that fixes were made: the fixes are
real — they are just stranded on a branch that is not `master`.

### Major verified conclusions

- **CONFIRMED CRITICAL — suspended users keep full API access on `master`.**
  `get_current_user` on `master` never checks `is_suspended` for the signed-in
  principal. The P0-3 fix exists only on `feature/8-new-features`. (F-SEC-01)
- **CONFIRMED HIGH — cross-tenant data/compliance bugs, unfixed on both
  branches:** WhatsApp inbound replies match leads by phone across all tenants
  (F-SEC-02); an onboarding endpoint trusts a `user_id` from the request body
  (IDOR, F-SEC-03); the global suppression list leaks and accepts cross-tenant
  opt-out PII (F-SEC-04, severity depends on deployment model).
- **CONFIRMED HIGH — no spend/abuse ceiling on the AI pipeline.** `max_strategies`
  is never enforced and there is no token/cost cap anywhere; a single account can
  drive thousands of Claude calls/day. (F-AI-01)
- **CONFIRMED HIGH — indirect prompt injection** via scraped LinkedIn posts, news
  and inbound replies concatenated into generation prompts with no mitigation.
  (F-AI-02)
- **CONFIRMED HIGH — the production Docker image omits `firebase-admin`**
  (declared in `requirements.txt` but not `pyproject.toml`, which is what the
  Dockerfile installs) — the same defect class that once broke the entire image
  with `structlog`. FCM push is broken in-image. (F-OPS-01)
- **VERIFIED — the documented offline release gate passes cleanly** on `master`:
  `evals/run_evals.py` → 1,985 tests, 100% pass, exit 0 (§11).
- **VERIFIED — the headline product claims are implemented in real code** (§14),
  but **all live third-party integrations are only mock-tested** — 88 in-code
  "verify against current docs" TODOs mark request/response shapes that have
  never been run against the real vendor APIs.

### Major unresolved uncertainties

- **Deployment model (multi-tenant SaaS vs single-tenant self-host) is a founder
  decision that is the severity hinge for several tenancy findings** (F-SEC-04,
  F-SEC-05) and cannot be determined from code.
- **The original "Ahmad" evaluation (`audit_findings.md`) is not in the
  repository or its history.** Its findings were reconstructed from the founder's
  fix-report documents, which are self-attestations and were themselves verified
  against code where possible. See §12 and §17.
- **No live third-party API, no production environment, and no live Anthropic
  model call could be exercised** (no credentials). Those paths are marked
  `UNVERIFIED` throughout.

**Headline verdict:** LeadPilot is a real, capable, largely-working system with
good bones and real security discipline, but it is **not production-ready as it
stands on any single branch**, and its highest-priority problem is not a bug —
it is that the fixes and the quality gate live on different branches. The
immediate action is a branch reconciliation, after which the CRITICAL and HIGH
findings below must be closed and the integration layer proven against live
vendors.

---

## 2. Audit Scope

**In scope (evaluated):**

- **Repository:** `Rmasood1122/LeadPilot` — full-history clone (46 commits on
  `master`), all six remote branches.
- **Branches:** `master`, `feature/8-new-features`, `vercel/install-and-configure-vercel-s-xnm1g4`,
  `claude/confident-franklin-lv1our`, `feature/engagement-hub`,
  `feature/tool-integrations` (full matrix in §4).
- **Components:** backend (FastAPI API, services, Celery workers, Anthropic
  pipeline, verification loop), database/migrations, frontend (Next.js 14),
  Python SDK/CLU, mobile (Capacitor) presence, evals/release-gate, Docker/CI.
- **Providers (code + test posture):** Anthropic, OpenAI, Apollo, Hunter, Gmail,
  WhatsApp/Meta, Calendly, Stripe, Recall.ai, Firebase/FCM, NewsAPI, Twilio/SMS,
  Vapi/ElevenLabs, HubSpot, Salesforce, Unipile.
- **Execution performed:** `pip install`, `import app.main`, `pytest` (offline
  and mixed), `evals/run_evals.py` (the release gate), `registry_lint.py`,
  frontend `tsc --noEmit`, `vitest`, `next build` attempt.

**Explicitly NOT evaluated / could not be evaluated:**

- **The original Ahmad evaluation document** — not present in the repo/history.
- **Any live third-party API** — no credentials; all integrations are mock-tested
  only. Real request/response contracts are `UNVERIFIED`.
- **Any production/staging environment** — none exists; LP-T-004 confirms no
  environment has been stood up.
- **Live Anthropic model calls**, including validity of the default model ID
  `claude-sonnet-4-6` — `UNVERIFIED`.
- **On-device mobile behavior** (Capacitor) — present in code, never run on a
  device.
- **The PostgreSQL-only integration test suite** (`tests/integration/`) — requires
  live PostgreSQL/Redis; errored out offline by design.
- **Provider client internals, `sdk/` runtime, `nginx/`, `railway/`, `render.yaml`
  deploy behavior** — read where relevant but not exercised.

---

## 3. Environment

| Item | Value |
|---|---|
| OS / kernel | Linux 6.18 (Ubuntu 24.04 userland) |
| Python | 3.11.15 |
| Node | 22.22.2 / npm 10.9.7 |
| PostgreSQL (available, not used by offline suite) | 16.13 |
| Redis (available) | 7.0.15 |
| Docker | 29.4.3 |
| Package install | `pip install -r requirements.txt --break-system-packages` + dev extras (exit 0); `anthropic` resolved to 1.11.0 |
| Test runner | pytest 9.1.1 (isolation runs) / pytest invoked by `evals/run_evals.py` for the gate |
| Frontend | `npm install`; `npx tsc --noEmit` exit 0; `vitest run` 389 passed |

No secrets were used, exposed, or required. The app emits a boot-time warning
`ENCRYPTION_KEY is not set — integration tokens will NOT be encrypted at rest`;
the behavior behind it is actually fail-closed (see F-OPS-05).

---

## 4. Branch Coverage

Full-history clone; default branch `master`. merge-base(`master`,
`feature/8-new-features`) = `847e103` (2026-09-13) — the two lines diverged
mid-September.

| Branch | Tip SHA | Last commit | vs master (behind/ahead) | Unique commits | Unique content | Audited? |
|---|---|---|---|---|---|---|
| **master** (default) | `1ad2cab` | 2026-09-30 | 0 / 0 | — | Release gate (`evals/`, `eval-gate.yml`); LP-T-002/LP-T-004 audit track | **Yes — primary** |
| **feature/8-new-features** | `5705e81` | 2026-09-27 | 4 / **39** | 39 | **All P0 fixes** (P0-2/3/4/6 + playbook endpoint); 12 "new features"; migrations 0048–0064; +34,068 lines, 181 files added. **No `evals/`, no CI.** | **Yes — primary** |
| **vercel/install-…-xnm1g4** | `15dc632` | 2026-09-16 | 4 / 17 | 1 genuinely unique | Older snapshot of the feature/8 line (up to `038782c`) **+ one unique commit:** "Install and configure Vercel Speed Insights" (frontend telemetry) | Unique item noted; code = subset of feature/8 |
| **claude/confident-franklin-lv1our** | `9c316f9` | 2026-09-26 | 4 / 1 | 1 | Docs only: `docs/ONE_WEEK_CLIENT_SPRINT.md` (business plan, no product code) | Noted; no code to audit |
| **feature/engagement-hub** | `92f12a2` | 2026-09-07 | 17 / 0 | **0** | Ancestor of master — fully subsumed, no unique code | Confirmed subsumed |
| **feature/tool-integrations** | `98c666b` | 2026-09-13 | 11 / 0 | **0** | Ancestor of master — fully subsumed, no unique code | Confirmed subsumed |

**Evidence of coverage:** branch tips, merge-bases, `git rev-list --left-right
--count`, and per-branch `git log master..branch` were computed for all six
remotes; `engagement-hub` and `tool-integrations` have zero commits not already
in `master`; the `vercel` branch's only commit absent from `feature/8-new-features`
is the Vercel Speed Insights commit; `confident-franklin`'s only unique commit
touches one docs file (`git show --stat`).

**Scope decision:** the code audit covers `master` and `feature/8-new-features`
(the superset divergent branch). The other three branches contribute no unique
product code (the Vercel telemetry commit and the business-plan doc are noted and
carry no security/correctness weight).

---

## 5. Product Architecture (as actually discovered)

```
Clients:  Next.js 14 web (frontend/, static export)  ·  Capacitor Android (frontend/android/)  ·  Python SDK "clienthunter" (sdk/)
                                   │ HTTPS/REST
FastAPI  (app/main.py, ~52–62 routers in app/api/)
  Auth (JWT HS256 + personal API keys)  ·  Products/Strategies/Leads/Campaigns/CRM/Playbook/Billing/Workspaces/Admin
                     │ SQLAlchemy 2.0 (sync)                         │ Celery + Redis
         PostgreSQL (app/db/models.py, Alembic)          Celery Beat + workers (app/workers/, ~30 modules)
                                                          pipeline · outreach(send/dispatch) · learning · monitoring · deliverability
AI:  single gateway app/services/anthropic_client.py  →  app/pipeline/ (72/144 steps)  +  app/verification/ (10 passes)
     +  app/services/* (personalization, reply classification, claim verification, adversarial review, consensus via OpenAI)
Release gate (master only):  evals/run_evals.py → evals/tools/promote.py (candidate vs baseline), .github/workflows/eval-gate.yml
```

**Architectural strengths (verified):** a single auth chokepoint
(`get_current_user`); a single Anthropic gateway with centralized retry/usage/
truncation handling; an ownership-filter "house rule" applied consistently
across ~30 CRUD routers (404-not-403); a fail-closed production boot guard
(`production_guard.validate_production_config`, called in the lifespan); clean,
single-head Alembic chains on both branches.

**Architectural weaknesses (verified):** two parallel settings modules
(`app/config.py` vs `app/core/config.py`) with real drift (F-OPS-03); a duplicate,
orphaned send implementation (`app/workers/send_tasks.py`) alongside the canonical
one (`app/workers/outreach_tasks.py`) (F-REL-01); the release gate and the P0
fixes living on different branches (the structural finding).

---

## 6. Feature Verification Matrix

Status legend: VERIFIED WORKING (code read + executed/collected), IMPLEMENTED-UNVERIFIED
(code present, not run against live dependency), PARTIAL, BROKEN.

| Feature | Branch(es) | Implementation | Tests | Runtime check | Status | Confidence |
|---|---|---|---|---|---|---|
| 72/144-step research pipeline | both | `app/pipeline/registry.py`, `engine.py` | yes | `len(STRATEGY_STEPS)=72`, `GTM=72` (run) | VERIFIED WORKING | CONFIRMED |
| 10-pass verification loop | both | `app/verification/passes.py`, `loop.py` | yes | counted 9 base + flow pass #10 | VERIFIED WORKING | CONFIRMED |
| Lead sourcing (Apollo) | both | `app/integrations/apollo.py`, `lead_tasks.py` | mock only | import OK | IMPLEMENTED-UNVERIFIED (live) | CONFIRMED (code) |
| Email verification (Hunter) | both | `app/integrations/hunter.py` | mock only | — | IMPLEMENTED-UNVERIFIED (live) | CONFIRMED (code) |
| Gmail outreach | both | `app/integrations/gmail.py` | mock only | — | IMPLEMENTED-UNVERIFIED (live) | CONFIRMED (code) |
| WhatsApp outreach + opt-in/STOP | both | `app/integrations/whatsapp.py`, `webhooks_whatsapp.py` | yes (offline) | offline tests pass in isolation | VERIFIED WORKING (logic) / UNVERIFIED (live) | CONFIRMED (code) |
| Calendly booking → meeting_booked | both | `app/api/webhooks.py`, `integrations/calendly.py` | yes | — | VERIFIED WORKING (logic) | CONFIRMED |
| Learning loop / A/B auto-promote | both | `app/services/ab_testing.py`, `workers/learning_tasks.py` | yes | — | VERIFIED WORKING (logic) | CONFIRMED |
| Compliance (CAN-SPAM, suppression, bounce 3% pause, GDPR erase) | both | `sequence_engine.py`, `app/api/unsubscribe.py`, `leads.py` | yes (sealed set) | gate 100% | VERIFIED WORKING | CONFIRMED |
| Billing (Stripe) + stub mode | both | `app/services/billing.py`, `stripe_billing.py` | yes | — | VERIFIED (stub); live UNVERIFIED | CONFIRMED (code) |
| Account suspension (kill-switch) | feature/8 only | `auth.py:207` | yes (feature/8) | — | **BROKEN on master** | CONFIRMED |
| Release gate / CI | **master only** | `evals/`, `eval-gate.yml` | self | **ran, 100%** | VERIFIED WORKING | CONFIRMED |
| 12 "new features" (inbox, attribution, consent, provenance, agency mode, FPTA, etc.) | feature/8 only | `app/api/*`, `app/services/*`, migrations 0048–0064 | yes (feature/8 offline) | collection 2,834 | IMPLEMENTED (offline-tested) | CONFIRMED (code) |
| Python SDK CLI (`clienthunter`) | both | `sdk/` (separate package) | — | — | IMPLEMENTED-UNVERIFIED | CONFIRMED (code) |
| Mobile (Capacitor Android) | both | `frontend/android/`, native hooks | — | tsc OK | IMPLEMENTED-UNVERIFIED (on-device) | CONFIRMED (code) |

---

## 7. Findings Register (summary)

Full per-finding detail is in **`docs/FINDINGS_REGISTER.md`**. Severity (impact)
and confidence (evidence strength) are rated independently.

| ID | Category | Sev | Conf | Branch(es) | Short |
|---|---|---|---|---|---|
| F-SEC-01 | AuthZ | CRITICAL | CONFIRMED | master | Suspended users keep full API access (P0-3 fix only on feature/8) |
| F-SEC-02 | Multi-tenancy | HIGH | CONFIRMED | both | WhatsApp inbound matched to lead by phone across all tenants |
| F-SEC-03 | Multi-tenancy / IDOR | HIGH | CONFIRMED | both | `/onboarding/complete-step` trusts `body.user_id` (cross-user write) |
| F-SEC-04 | Multi-tenancy / PII | HIGH* | CONFIRMED | both | Global suppression list: cross-tenant PII read + permanent cross-tenant write (*SaaS-dependent) |
| F-SEC-05 | Multi-tenancy | MEDIUM* | CONFIRMED | both | website_builder shared NULL-workspace pool; whatsapp_templates deployment-global (*SaaS-dependent) |
| F-AI-01 | AI / Unbounded consumption | HIGH | CONFIRMED | both | `max_strategies` unenforced + no spend/token cap anywhere |
| F-AI-02 | AI / Prompt injection | HIGH | CONFIRMED | both | Scraped posts/news/replies concatenated into prompts, no mitigation |
| F-AI-03 | AI / Determinism | MEDIUM | CONFIRMED | both | `temperature` never set — non-deterministic compliance/verification judges |
| F-AI-04 | AI / Model config | MEDIUM | UNVERIFIED | both | Default model ID `claude-sonnet-4-6` validity unconfirmed; wrong ID fails terminal |
| F-AI-05 | AI / Context poisoning | LOW | CONFIRMED | both | Learning-loop / playbook stored-data-into-prompt surface (latent) |
| F-AI-06 | AI / Context poisoning | LOW | POTENTIAL | both | Cross-pipeline synthesis fed to judge without provenance isolation |
| F-OPS-01 | Deps / Deploy | HIGH | CONFIRMED | both | `firebase-admin` missing from `pyproject.toml` → absent from Docker image (FCM broken) |
| F-OPS-02 | Webhook security | HIGH | CONFIRMED | both | Calendly webhook has no timestamp/replay protection |
| F-OPS-03 | Config | MEDIUM | CONFIRMED | both | Two settings modules (`app/config.py` vs `app/core/config.py`) drift |
| F-OPS-04 | Config | MEDIUM | CONFIRMED | both | Firebase var-name mismatch (`_PATH` read vs `_JSON` declared) |
| F-OPS-05 | Config / clarity | LOW | CONFIRMED | both | ENCRYPTION_KEY-unset warning copy is misleading (behavior is fail-closed) |
| F-REL-01 | Reliability / dead code | MEDIUM | CONFIRMED | both | Duplicate non-atomic send path `send_tasks.py` (orphaned but registered) |
| F-REL-02 | Reliability / dead code | LOW | CONFIRMED | both | `monitoring.py` references non-existent task `outreach_tasks.send_sequence_step` |
| F-DB-01 | Data / tenancy | HIGH* | CONFIRMED | both | `playbook_scores` has no tenant column — learned scores global (*SaaS-dependent) |
| F-DB-02 | Data | MEDIUM | CONFIRMED | master | `admin.py` filters nonexistent `ps.user_id`, swallowed by bare except → always `[]` |
| F-DB-03 | Performance | MEDIUM | CONFIRMED | both | No index on `messages.status` / `scheduled_at` (hot scheduler columns) |
| F-DB-04 | Data | LOW | CONFIRMED | both | `playbook_scores.score` is a redundant copy of `reply_rate` |
| F-QA-01 | Testing | MEDIUM | CONFIRMED | both | Order-dependent offline test failures when integration dir is co-collected |
| F-QA-02 | Testing | MEDIUM | CONFIRMED | both | All third-party integrations mock-only (88 "verify against docs" TODOs) |
| F-OPS-06 | Deps | MEDIUM | CONFIRMED | both | No lockfile; `requirements.txt` vs `pyproject.toml` drift; unused/unpinned deps |
| F-OPS-07 | Deps | POTENTIAL | POTENTIAL | both | Vestigial `python-jose`/`pillow` — run a real advisory scan (no CVE asserted) |
| F-SEC-06 | Config | LOW | CONFIRMED | both | debug router guard allows an env named `staging` with the flag on |

\* severity hinges on the multi-tenant-SaaS vs single-tenant-self-host decision.

---

## 8. Security Audit

### 8.1 Confirmed vulnerabilities

- **F-SEC-01 (CRITICAL, master) — suspended accounts retain full access.**
  `app/services/auth.py::get_current_user` (master, lines 130–178) resolves the
  bearer token or `lpk_` API key, checks only `email_verified`, then returns via
  `_workspace_principal`. The sole `is_suspended` check (line 205) is for the
  **workspace owner** in the delegated-workspace path; a suspended user acting on
  their own account (no `X-Workspace-Id` header) is never checked. `/auth/login`
  and `/auth/refresh` additionally mint fresh tokens without this gate. The fix
  (`auth.py:207 if user.is_suspended: raise 403`) is contained **only** in
  `feature/8-new-features` (commit `6e11abe`; `git branch -r --contains 6e11abe`
  → that branch only). *Verified by reading `get_current_user` end-to-end on both
  branches and the branch-contains check.*

- **F-SEC-02 (HIGH, both) — cross-tenant WhatsApp reply routing.**
  `app/api/webhooks_whatsapp.py::_handle_inbound` runs
  `select(Lead).where(Lead.phone.isnot(None))` across **all** tenants and
  first-match-wins by normalized phone; the tenant discriminator `phone_number_id`
  is captured as `account_ref` but never used to scope the lookup. A shared phone
  number routes a private reply to the wrong tenant, opens their 24h window, flips
  their lead to REPLIED, and a STOP suppresses the wrong account's sequences — a
  data-disclosure **and** compliance defect. The LP-T-002 report calls this the
  third instance of the class `notifications.py:300` warns about; the email
  variant was fixed, the phone variant was not. *Verified by reading lines
  300–340 on master and 300–340 on feature/8.*

- **F-SEC-03 (HIGH, both) — onboarding IDOR / cross-user write.**
  `app/api/onboarding.py::complete_step` sets
  `target_user_id = body.user_id or str(current_user.id)` and calls
  `mark_complete(db, target_user_id, step)` with no check that `body.user_id ==
  current_user.id` and no admin gate. Any authenticated user can mark/overwrite
  another user's `onboarding_state` JSON. The docstring claims only the server or
  the user themselves can call it; nothing enforces it. *Verified by reading the
  handler on both branches (master line 126; feature/8 line 126).*

- **F-SEC-04 (HIGH*, both) — global suppression PII exposure + cross-tenant
  write.** `app/api/ui_support.py` `GET /suppression` returns every tenant's
  suppressed emails/phones to any authenticated user; `POST /suppression`
  permanently adds a deployment-wide suppression ("no delete endpoint by
  design"). Global *enforcement* at send time is correct compliance; the unscoped
  *listing* of others' opt-out PII and the irreversible cross-tenant *write* are
  the issue. Severity HIGH on a multi-tenant SaaS; acceptable on single-tenant
  self-host. *Verified by reading the two handlers.*

### 8.2 Likely / potential

- **F-SEC-05 (MEDIUM*, both)** — `website_builder` routes share a
  `workspace_id IS NULL` pool, letting workspace-less tenants act on each other's
  (and the deployment's own marketing) pages; `whatsapp_templates` is
  deployment-global by design. Both severities hinge on the deployment model.
  *Cited by LP-T-002; not independently line-verified in this pass, but LP-T-002
  scored 4/4 on the findings this audit did re-verify.*
- **F-OPS-07 (POTENTIAL)** — vestigial `python-jose` and recurring-CVE `pillow`
  are present; no specific CVE is asserted. Run `pip-audit`/`safety` in CI.

### 8.3 What is done well (verified, not comment-trusted)

- **Password hashing:** PBKDF2-HMAC-SHA256, 600k iterations, per-user salt,
  constant-time compare (`auth.py:52–76`).
- **JWT:** HS256 via PyJWT, explicit `algorithms=["HS256"]` on every decode (no
  alg-confusion / `alg:none`), `typ` claim checked, expiry enforced.
- **API keys:** `lpk_` + 32 random bytes, only SHA-256 stored, revocation checked,
  refused at admin routes.
- **Webhook signatures:** WhatsApp, Stripe, HubSpot, Salesforce, Recall, Unipile,
  Vapi/ElevenLabs all HMAC-verified, constant-time, fail-closed when the secret is
  unset. Stripe/HubSpot/Salesforce also enforce timestamp tolerance (replay
  protection).
- **Production boot guard** (`production_guard.py`): refuses to boot production
  with unset/placeholder/short `SECRET_KEY`, invalid `ENCRYPTION_KEY`, bad CORS,
  localhost Redis, placeholder sender identity. Called first in the lifespan.
- **Secrets:** no real secrets committed; no secret values logged (FCM logs token
  tail only; SMS masks phone numbers). Debug routes triple-gated.
- **Ownership house rule:** consistent 404-not-403 ownership checks across ~30
  CRUD routers (independently confirmed and corroborated by LP-T-002's per-router
  matrix).

---

## 9. AI / LLM Audit

**Design (verified):** one gateway (`app/services/anthropic_client.py`:
`complete`, `complete_json`) funnels every model call, with a correct
retryable-vs-permanent error taxonomy (529 separated from 500; 401/403/404/400/
413/422 treated as terminal and not retried), `tenacity` backoff, usage metering,
and a `TruncatedResponseError` path that treats `stop_reason=="max_tokens"` as
corruption rather than a short answer. A second-model OpenAI consensus path
exists. The two gates that actually block a send are **deterministic rule code**,
not the model: `adversarial_review` is warn-only ("only deterministic rules can
block"), and `claim_verification` strips unsupported factual claims and fails
closed. These are genuine strengths.

**Findings:**

- **F-AI-01 (HIGH) — unbounded consumption / no cost control.**
  `app/api/strategies.py::create_strategy` enforces only a rate limit (line 70:
  `enforce_rate_limit(..., "RATE_LIMIT_STRATEGIES")`) before
  `worker_tasks.run_pipeline.delay` (line 98). `check_plan_limit` is called in
  exactly one unrelated place (`website_builder`), so the per-tier
  `max_strategies` is enforced **nowhere**; the resume endpoint (line 193) also
  re-enqueues unchecked. A grep for `spend_cap|budget_cap|max_spend|token_budget`
  across `app/` returns nothing — `usage_meter` records cost but enforces no
  ceiling. One strategy = 72–144 Claude calls plus a ≤10-pass × ≤3-attempt
  verification loop (each fix up to 18,432 output tokens) plus optional consensus.
  Maps to **OWASP LLM10 (Unbounded Consumption)**. *CONFIRMED by reading the
  handler and the empty grep.*
- **F-AI-02 (HIGH) — indirect prompt injection.**
  `app/services/personalization_context.py` concatenates the lead's own LinkedIn
  post text (`post["text"][:700]`) and third-party news headlines/summaries
  directly into the personalization prompt, instructing the model to reference
  them; inbound reply bodies feed the reply classifier (`reply_classification.py`)
  and fraud detector that drive suppression/stop logic. No delimiting, escaping,
  or injection-specific instruction exists on any of these paths. **OWASP LLM01.**
  Partially contained downstream by claim-verification and the human-in-the-loop
  on replies, but classification manipulation is not covered. *CONFIRMED by
  reading lines 138–160.*
- **F-AI-03 (MEDIUM) — non-deterministic compliance judge.** `temperature` is
  never set on any Anthropic request (`anthropic_client.py` builds requests
  without it; the only `temperature` in `app/` is on the OpenAI call). The legal
  compliance pass (a documented hard ship-blocker) therefore runs at the API
  default (~1.0) and can return different PASS/FAIL verdicts across runs. **OWASP
  LLM09.** *CONFIRMED by reading the request builder + grep.*
- **F-AI-04 (MEDIUM, UNVERIFIED) — default model ID.** `app/config.py` and
  `app/core/config.py` default `anthropic_model="claude-sonnet-4-6"`. It is
  env-overridable (good). If the ID is invalid the SDK returns 404, which the code
  correctly classifies as PERMANENT — so every strategy would fail terminally with
  no fallback model. The auditor could not confirm the ID against the live Models
  API (no credential/doc access; the model generation post-dates the auditor's
  knowledge cutoff). Add a startup health-check that fails loudly on an unknown
  model. *UNVERIFIED.*
- **F-AI-05 (LOW/CONFIRMED) and F-AI-06 (LOW/POTENTIAL) — latent context-poisoning
  surfaces** in the learning-loop playbook injection and cross-pipeline synthesis
  feeding the judge; low risk today (numeric aggregates, user-applied mutations)
  but worth the register. Detail in `docs/FINDINGS_REGISTER.md`.

---

## 10. Testing Audit

- **Offline suites (what the hard gate runs):** master collects 2,114 under
  `tests/`; the gate runs `pytest --ignore=tests/integration` → **1,985 executed,
  100% pass** (§11). feature/8 collects **2,834** offline tests.
- **Integration suite (`tests/integration/`, 124 tests):** requires live
  PostgreSQL/Redis; errors out under the offline runner **by design** — these are
  not code failures. Confirmed by inspecting a representative error (SQLite engine
  built at import time vs the PG-only fixtures).
- **F-QA-01 (MEDIUM) — order-dependent flakiness.** A raw `pytest tests/` run
  (integration dir included) produced 9 WhatsApp webhook/cross-channel failures;
  each **passes in isolation and when its own files run together**, and the
  official gate (integration excluded) is 100% green. So the failures are triggered
  by state/import pollution when the integration dir is co-collected — a test
  isolation weakness, not a product bug, but it violates the project's own
  "deterministic, offline" standard and can mislead anyone running `pytest tests/`
  directly.
- **F-QA-02 (MEDIUM) — integrations are mock-only.** 88 in-code "TODO: verify
  against current … docs" markers across Apollo/Hunter/Gmail/WhatsApp/Capacitor;
  tests use `respx`/fakes. The plumbing, gating, and error handling are real and
  tested, but no live third-party request/response shape has ever been confirmed.
- **Release gate design (strength):** `evals/run_evals.py` is fail-closed in both
  directions — a failing sealed compliance test blocks, and a *missing* sealed
  file or a sub-1,900 test count also blocks (defeating the delete-tests-to-go-green
  attack). `evals/fixtures/verify_block_fixtures.py` proves each gate actually
  fires ("seen-it-fire"). This is genuinely good release engineering — **and it
  exists only on master.**

---

## 11. Runtime Verification (commands and results)

All on `master` @ `1ad2cab` unless noted. No fabricated results.

| # | Command | Result |
|---|---|---|
| 1 | `pip install -r requirements.txt --break-system-packages` (+ dev extras) | exit 0 |
| 2 | `python3 -c "import app.main"` | `IMPORT_OK`; warning: ENCRYPTION_KEY unset |
| 3 | `python3 evals/tools/registry_lint.py evals/registry.yaml` | `IE-06 registry lint: OK` (exit 0) |
| 4 | `python3 -m pytest tests/ --co -q` | 2,114 tests collected, exit 0 |
| 5 | `python3 -m pytest tests/` (integration included) | **9 failed, 1,976 passed, 5 skipped, 124 errors** (292s). 124 errors = `tests/integration/` (needs PG/Redis); 9 failures = WhatsApp, order-dependent (see F-QA-01) |
| 6 | isolation reruns of the 9 failures | all **pass** in isolation / per-file |
| 7 | **`python3 evals/run_evals.py`** (the documented gate) | **compliance_suite_pass_rate 1.0, full_suite_pass_rate 1.0, offline_test_count 1985, exit 0** |
| 8 | `cd frontend && npx tsc --noEmit` | exit 0, zero errors |
| 9 | `cd frontend && vitest run` | 389 passed, exit 0 |
| 10 | `cd frontend && next build` | fails only on build-time Google Font fetch (proxy 403); stubbing the font → clean static export of ~40 routes |
| 11 | `feature/8-new-features` offline collection (worktree) | 2,834 tests collected, exit 0 |
| 12 | `feature/8` offline run `pytest --ignore=tests/integration` | **2,827 passed, 7 skipped, 0 failed, exit 0** (477s); WhatsApp flakiness absent (integration excluded) |
| 13 | `feature/8` `evals/run_evals.py` | **not runnable — `evals/` does not exist on feature/8** |

`feature/8-new-features` offline suite: **2,827 passed, 7 skipped, 0 failed,
exit 0** (recorded in §11 and `docs/BRANCH_COVERAGE.md`).

---

## 12. Previous Evaluation Reconciliation

**The original "Ahmad" evaluation (`audit_findings.md`) is not committed to the
repository or anywhere in its history** (searched all refs and the full commit
graph). It is referenced only by the founder's own fix-report documents under
`docs/audit-fixes/` on `feature/8-new-features`. This is a material limitation:
the previous findings had to be **reconstructed from the fix reports**, which are
self-attestations. Where the reports make checkable claims, they were verified
against code.

Per-finding reconciliation (full table in
`docs/PREVIOUS_EVALUATION_RECONCILIATION.md`):

| Prev finding (as restated in fix docs) | Fix claimed | Independent verdict |
|---|---|---|
| RF-2 free-plan escalation (stub mode grants paid tiers in prod) | FIXED `4f5fd4c` | **FIXED on feature/8 only** (`billing.py:82–84`); **STILL PRESENT on master** |
| RF-3 account-suspension bypass | FIXED `6e11abe` | **FIXED on feature/8 only** (`auth.py:207`); **STILL PRESENT on master** → F-SEC-01 CRITICAL |
| "Duplicate send bug" (RF-5 adjacent) | FIXED `cda7fc3` | **FIXED on feature/8 only** (live path `send_message_impl` atomic claim); **STILL PRESENT on master**; a *second* non-atomic send path remains on both (F-REL-01) |
| P0-6 broken `/admin/playbook/scores` | FIXED `5ed9a3d` | **FIXED on feature/8 only**; **STILL PRESENT on master** (`admin.py:291,310`) → F-DB-02 |
| Ahmad's cited paths `app/core/dependencies.py`, `app/services/message_sender.py`, `app/models.py` | — | **INVALIDATED** — these paths do not exist; the real files are `app/services/auth.py`, `app/workers/outreach_tasks.py`, `app/db/models.py`. The founder's corrections are accurate. |
| Ahmad: "/admin/playbook/scores always returns []" | — | **PARTIALLY CORRECT** — only the `?user_id=` path was broken; the unfiltered path worked. The founder's correction is accurate. |

**Net:** the founder's P0 remediation work is **real and, where checkable,
correct** — and several of Ahmad's findings were imprecise in file paths and one
behavioral claim, which the founder correctly identified. **But every fix landed
only on `feature/8-new-features`, not `master`.** On the default branch, all four
P0 issues are **STILL PRESENT**.

---

## 13. Regression Analysis

- **No functional regression found *introduced by* the P0 fixes** — on
  feature/8, the P0 fix modules and their sweeps are present and the branch
  collects 2,834 offline tests (execution result in §16/BRANCH_COVERAGE).
- **The dominant "regression" is organizational, not code:** the fixes were
  developed on a branch that also *dropped* the release-gate infrastructure
  (`evals/`, `eval-gate.yml` are master-only). Merging feature/8 into master
  naïvely would **remove the release gate**; rebasing/merging must preserve both.
- **A fix gap the P0-4 work did not cover:** the duplicate `send_tasks.py` send
  path remained non-atomic on both branches (F-REL-01). The P0-4 fix correctly
  hardened the *canonical* path (`outreach_tasks.send_message_impl`) but the
  orphaned duplicate was not addressed — low live risk because it has no caller,
  but it is a latent regression vector if ever wired up.
- **Regression tests:** the P0 fixes shipped with dedicated tests
  (`tests/test_account_suspension.py`, `test_duplicate_send_claim.py`,
  `test_checkout_requires_stripe.py`, `test_admin_playbook_scores.py`) on
  feature/8 — good. Those tests do **not** exist on master, so master has no
  guard against re-introduction even after a port.

---

## 14. Production Readiness (by category)

| Category | State | Evidence |
|---|---|---|
| Core functionality | **Largely working** | Pipeline/verification run; gate 100%; claims verified in code |
| Authentication | **Strong** | PBKDF2, HS256, API keys, prod boot guard |
| Authorization | **Weak on master** | F-SEC-01 CRITICAL; F-SEC-03 IDOR both branches |
| Multi-tenancy | **Mixed** | CRUD routers correct; webhook/onboarding/suppression paths not (F-SEC-02/03/04) |
| AI reliability | **Good core, no cost control** | Gateway/retry/truncation strong; F-AI-01 unbounded spend; F-AI-03 non-determinism |
| Data / DB | **Good hygiene, gaps** | Clean migration chains, FK discipline; F-DB-01 tenant-less playbook; F-DB-03 missing hot index |
| Secrets / config | **Good, with drift** | Fernet, prod guard, no committed secrets; F-OPS-03/04 config drift |
| Deployment / Docker | **Broken dependency** | F-OPS-01 firebase-admin absent from image |
| Observability | **Present** | structlog, usage meter, circuit breakers, admin task-error telemetry |
| CI / release gate | **Master only** | Excellent gate, but not on the branch with the fixes |
| External integrations | **Unproven** | F-QA-02 mock-only; 88 "verify" TODOs; no live run |
| Testing | **Strong offline, fragile mix** | 1,985/2,834 offline green; F-QA-01 order dependence |
| Operational prerequisites | **Not stood up** | LP-T-004: no environment provisioned; external credentials pending |

**Conclusion:** **Not production-ready on any single branch today.** The product
is close in capability but blocked by (a) the branch split, (b) the CRITICAL and
HIGH security findings, (c) the broken Docker dependency, and (d) the entirely
unproven live-integration layer.

---

## 15. Top Risks (ranked by severity × confidence × evidence)

1. **F-SEC-01 (CRITICAL/CONFIRMED)** — suspended users keep access on master; the
   kill-switch is cosmetic for non-admins on the default branch.
2. **Branch split (CRITICAL/CONFIRMED, structural)** — fixes and quality gate on
   different branches; the default branch lacks all P0 fixes.
3. **F-OPS-01 (HIGH/CONFIRMED)** — production Docker image omits `firebase-admin`;
   FCM push broken, repeating a known defect class.
4. **F-AI-01 (HIGH/CONFIRMED)** — no AI spend/abuse ceiling; a single account can
   bill unbounded Anthropic spend.
5. **F-SEC-02/03/04 (HIGH/CONFIRMED)** — cross-tenant WhatsApp routing, onboarding
   IDOR, suppression PII exposure (last two severities SaaS-dependent).
6. **F-AI-02 (HIGH/CONFIRMED)** — indirect prompt injection via scraped prospect
   content, no mitigation.
7. **F-OPS-02 (HIGH/CONFIRMED)** — Calendly webhook replay (no timestamp check).
8. **F-QA-02 (MEDIUM/CONFIRMED)** — the entire integration layer is unproven
   against live vendors; real-world behavior is unknown.

---

## 16. Recommended Next Steps

Full detail with verification methods in **`docs/NEXT_STEPS.md`**.

### P0 — Immediate blockers
- **P0-A: Reconcile the branches.** Decide the single trunk. Recommended: merge
  `feature/8-new-features` into `master` **while preserving `evals/` and
  `eval-gate.yml`**, then run the gate on the merged tree. *Verify:*
  `evals/run_evals.py` exit 0 on the merged branch; all P0 fix tests present.
- **P0-B: Port F-SEC-01 to the trunk** (the `is_suspended` guard + 
  `test_account_suspension.py`). *Verify:* suspended user → 403 on a protected
  route and via API key; test red-then-green.
- **P0-C: Fix F-OPS-01** — add `firebase-admin` (and any other requirements-only
  deps the image needs) to `pyproject.toml`; build the image and
  `import app.main` + exercise an FCM path inside the container. *Verify:*
  container import + push smoke.
- **P0-D: Decide the deployment model** (multi-tenant SaaS vs single-tenant
  self-host). This sets the severity of F-SEC-04/05 and F-DB-01 and must precede
  their fixes.

### P1 — High-priority fixes
- **F-SEC-02:** scope WhatsApp inbound lead lookup by `phone_number_id` → tenant.
- **F-SEC-03:** drop/authz-gate `body.user_id` in `/onboarding/complete-step`.
- **F-AI-01:** enforce `check_plan_limit(user,"max_strategies",...)` in create +
  resume; add a per-account monthly token/cost cap checked before enqueue.
- **F-AI-02:** delimit/label all externally-sourced text in prompts; treat
  classifier output as untrusted; consider an injection screen on inbound bodies.
- **F-OPS-02:** add Calendly webhook timestamp-freshness validation.
- **F-SEC-04 (if SaaS):** scope suppression listing per tenant; gate cross-tenant
  adds.
- **F-QA-02:** stand up a credentialed staging run of each integration against the
  live vendor; convert the "verify against docs" TODOs into recorded contract
  tests.

### P2 — Important improvements
- **F-AI-03:** set `temperature=0` on all judge/classifier/extractor calls.
- **F-AI-04:** add a startup model-ID health-check.
- **F-DB-03:** add `ix_messages_status` / composite `(status, scheduled_at)`.
- **F-DB-02:** fix/remove the phantom `ps.user_id` filter; stop the bare-except
  masking.
- **F-OPS-03/04:** consolidate the two settings modules; fix the Firebase var name.
- **F-REL-01/02:** remove or wire-and-harden `send_tasks.py`; fix the
  `monitoring.py` dead task-name reference.
- **F-QA-01:** make the offline suite order-independent (or exclude integration
  from the default `pytest` path in config).

### P3 — Technical debt / future
- **F-OPS-06/07:** add a lockfile; reconcile `requirements.txt`↔`pyproject.toml`;
  drop unused deps; run `pip-audit`/`safety` in CI.
- **F-DB-04:** drop the redundant `playbook_scores.score` (after checking legacy
  rows).
- Refresh stale docs (`PRODUCTION_READINESS.md`, `LAUNCH_CHECKLIST.md`), clarify
  that the CLI is a separate `sdk/` package, enforce ESLint at build, and
  on-device test the Capacitor layer.

---

## 17. Audit Limitations

- **Original Ahmad evaluation unavailable** — not in repo/history; findings
  reconstructed from self-attested fix reports (verified against code where
  checkable).
- **No live third-party API exercised** — no credentials; all integrations
  mock-tested only; live contracts `UNVERIFIED`.
- **No production/staging environment** — none exists; deployment behavior
  (Docker image runtime beyond import, nginx, Railway/Render) not runtime-verified
  except the Docker dependency-manifest analysis.
- **Model ID `claude-sonnet-4-6` validity `UNVERIFIED`** — no live Models API
  access; post-dates the auditor's knowledge cutoff.
- **PostgreSQL-only integration tests not executed** — require live PG/Redis.
- **LP-T-002 findings F2/F5** were accepted on the strength of the report's
  verified track record (4/4 of its findings this audit re-checked were confirmed
  exactly as cited) rather than an independent line-by-line re-read of every one.
- **Frontend `next build`** could not complete end-to-end in-sandbox (build-time
  Google Font fetch blocked by the proxy); compilation and static export were
  otherwise confirmed clean.

---

## 18. Final Audit Integrity Statement

- **Commits audited:** `master` @ `1ad2cab684e5a0b1d3dd34fae043b807113f2b60`;
  `feature/8-new-features` @ `5705e8170e7ae0d7252734532c9d4710b8c7a1ef`; branch
  tips for `vercel/…` `15dc632`, `claude/confident-franklin-lv1our` `9c316f9`,
  `feature/engagement-hub` `92f12a2`, `feature/tool-integrations` `98c666b`.
- **Branches audited:** all 6 remotes (2 with unique product code, fully audited;
  2 docs/telemetry-only, noted; 2 subsumed with zero unique commits, confirmed).
- **Findings:** 27 recorded.
  - **CONFIRMED:** 23 · **UNVERIFIED:** 1 (F-AI-04) · **POTENTIAL:** 2 (F-OPS-07,
    F-AI-06) · **LIKELY:** 1 (F-SEC-05, per LP-T-002).
  - By severity: **CRITICAL 1**, **HIGH 8** (3 of them SaaS-dependent),
    **MEDIUM 11**, **LOW 6**, plus the structural branch-split finding (tracked as
    the P0-A roadmap item rather than a numbered finding).
- **Previous-evaluation findings reconciled:** 4 P0 fixes + path/behavior
  corrections. **Fixed (on feature/8 only): 4. Still present on master: 4.
  Invalidated (Ahmad's file paths): 3 paths. Partially correct (Ahmad's
  always-`[]` claim): 1.**
- **Major unresolved limitations:** original evaluation document unavailable; no
  live integration/production/model verification; deployment model undecided.

**This report does not claim the product is "perfect", "fully secure", or
"production ready." The evidence does not support those claims.** It does show a
real, capable system whose biggest problem is a branch split that leaves its own
fixes off its default branch, with one CRITICAL and several HIGH issues to close
and an integration layer still to prove against the real world.

---

*Supporting documents:* `docs/BRANCH_COVERAGE.md`, `docs/FINDINGS_REGISTER.md`,
`docs/PREVIOUS_EVALUATION_RECONCILIATION.md`, `docs/NEXT_STEPS.md`.

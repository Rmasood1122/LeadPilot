# CHANGES.md — ClientHunter Enterprise

Full changelog from M1 (initial build) through M8 Chunk 3 (final milestone).

---

## M8 Chunk 3 (2026-08-17) — Production Hardening, Test Suite, Handoff

**Final milestone. System is production-ready.**

### Test suite (Section 1)
- `tests/conftest.py` — session-scoped real PostgreSQL + Redis fixtures; Celery ALWAYS_EAGER; respx transport mock registry
- `tests/integration/conftest.py` — factory helpers (create_product, create_past_clients, create_strategy, seed_outcomes); authed clients (admin, user_a, user_b)
- `tests/integration/mocks/anthropic_mock.py` — deterministic phase outputs; Phase 6 + 8 include `playbook_context_key`
- `tests/integration/mocks/apollo_mock.py` — 3 stable personas; `ApolloCallCapture`
- `tests/integration/mocks/hunter_mock.py` — alice/ben deliverable, carol undeliverable
- `tests/integration/mocks/gmail_mock.py` — `GmailCallCapture`, `queue_reply()`, exactly-once idempotency support
- `tests/integration/mocks/whatsapp_mock.py` — `CLOSED_WINDOW_PHONE`, `OPTED_OUT_PHONE`, webhook builders, HMAC signing
- `tests/integration/mocks/calendly_mock.py` — `FIXED_EVENT_ID`, booking webhook builder, HMAC signing
- `tests/integration/mocks/firebase_mock.py` — `FCMCallCapture`, topic and project filtering
- `tests/integration/test_flows.py` — 12 assertions across 3 flows (72-step, 144-step, learning loop)
- `tests/integration/test_compliance.py` — 11 active bypass tests; all must pass in CI
- `tests/integration/test_security.py` — JWT lifecycle, cross-tenant isolation × 5 resources, webhook signatures, admin gating
- `tests/integration/test_idempotency.py` — pipeline resume, lead dedupe, exactly-once send, Calendly+WA webhook dedupe, device token upsert, aggregation idempotency, double-promotion guard
- `tests/test_regression.py` — module discovery, import checks, M1–M8 spot-check classes

### Production hardening (Section 2)
- `app/api/health.py` — `/health` (public, DB+Redis+Celery), `/health/learning-loop` (admin), `/health/channels` (auth)
- `app/core/logging.py` — structlog JSON factory, `RequestIDMiddleware`, `bind_celery_task_context()`, `TaskTimer`
- `app/core/errors.py` — global exception handler; ComplianceError→422; no stack traces in client responses
- `app/core/circuit_breaker.py` — state introspection via `get_all_states()`; circuit_opened writes outcome event + admin FCM in daemon threads
- `app/workers/monitoring.py` — `register_task_failure_signal()`, CRITICAL_TASK_NAMES, stale pipeline step detection, `get_celery_stats()`
- `app/workers/beat_heartbeat.py` — `refresh_celery_heartbeat` task, writes `celery:heartbeat` key every 60s TTL 300s
- `app/core/crypto.py` — `_get_fernet()` lru_cached MultiFernet, `encrypt()`/`decrypt()`, `rotate_all_secrets()`
- `app/integrations/token_store.py` — `TokenStore.set/get/delete/is_valid`; Fernet-encrypted on write, decrypted on read; expiry check
- `app/core/config.py` — pydantic-settings Settings class; all M1–M8 vars + ENCRYPTION_KEY, ENCRYPTION_KEY_PREVIOUS, CIRCUIT_BREAKER_*, PIPELINE_STEP_TIMEOUT_MINUTES, ADMIN_EMAIL, PLAYBOOK_MIN_SAMPLE, AB_MIN_LIFT
- `SECURITY.md` — secrets inventory table, 6-step ENCRYPTION_KEY rotation, SECRET_KEY rotation, WhatsApp token rotation, Gmail rotation, compromise response, rotation schedule

### Admin controls (Section 3)
- `app/models/task_error.py` — TaskError model (task_name, error_type, error_message, traceback, resolved_at, resolved_by)
- `app/api/admin.py` — 14 admin endpoints (users, suppression, task errors, circuit breakers, playbook, encryption key rotation)
- `app/services/admin_service.py` — business logic for all admin endpoints
- `app/cli/create_admin.py` — Typer CLI `create-admin` and `list-admins` commands
- `alembic/versions/0009_m8c3_admin_and_hardening.py` — task_errors table, encrypted_value column, user admin/suspension columns
- `frontend/app/(admin)/admin/layout.tsx` — admin sidebar nav + is_admin auth guard
- `frontend/app/(admin)/admin/users/page.tsx` — user list + suspend/unsuspend
- `frontend/app/(admin)/admin/task-errors/page.tsx` — Celery error log + resolve dialog
- `frontend/app/(admin)/admin/circuit-breakers/page.tsx` — CB state cards + manual reset; auto-refreshes every 15s
- `frontend/app/(admin)/admin/suppression-list/page.tsx` — global suppression list + add/remove
- `frontend/app/(admin)/admin/playbook/page.tsx` — playbook scores + trigger recompute
- `frontend/app/(admin)/admin/health/page.tsx` — system health dashboard (core + learning loop + Celery queues)
- `frontend/lib/api/admin.ts` — typed frontend API client for all admin endpoints

### Deployment (Section 4)
- `docker-compose.prod.yml` — API (2 workers), 3 Celery workers (pipeline/outreach/learning), Beat, frontend (Next.js), Nginx, PostgreSQL 16, Redis 7
- `nginx/nginx.conf` — SSL termination, rate limiting (API: 60/min, auth: 10/min), security headers, reverse proxy
- `nginx/certbot-setup.sh` — Let's Encrypt initial certificate acquisition script
- `.env.production.example` — complete annotated production env template
- `DEPLOY.md` — step-by-step deployment guide (9 steps from bare VPS to live)
- `BACKUP.md` — nightly PostgreSQL backup script, restore procedure, disaster recovery targets

### Documentation (Section 5)
- `README.md` — rewrote: architecture diagram, quick start, integration table, compliance summary, key files
- `docs/architecture.md` — layer diagram, pipeline engine detail, learning loop data flow, data models, security model, extension points
- `docs/api-reference.md` — complete REST API reference with request/response examples
- `docs/compliance.md` — per-channel rule enforcement, audit trail events
- `docs/learning-loop.md` — data flow diagram, pattern keys, A/B testing, TF-IDF similarity, configuration

### Handoff (Section 6)
- `SYSTEM_HANDOFF.md` — what was built (M1–M8), known gaps/TODOs, architecture decisions and rationale, extension guide, first things to do after launch
- `LAUNCH_CHECKLIST.md` — 30+ item pre-launch verification checklist (infrastructure, services, admin, integrations, compliance, security, performance, monitoring, mobile)
- `sdk/src/clienthunter/cli/serve.py` — `--check-env` flag: validates all required env vars and prints Rich table before starting the server
- `sdk/tests/test_serve_check_env.py` — 11 tests for env validation logic and CLI behavior
- `CHANGES.md` — this file

---

## M8 Chunks 1+2 (2026-08-16) — Learning Loop

- `outcomes` table with event log (sent, opened, replied, booked, won, lost, bounced, unsubscribed, opted_out, circuit_opened, ab_promoted)
- `PlaybookScore` model with upsert aggregation
- Nightly `run_strategy_aggregation` Celery Beat task (00:05 UTC)
- `auto_promote_winners` with two-proportion z-test (p < 0.05, min lift 10%)
- Double-promotion guard (idempotent `ab_promoted` outcome event)
- `PlaybookService.get_insights()` for Phase 6 + 8 prompt injection
- `StrategySimilarityIndex` — TF-IDF cosine similarity on product descriptions
- `GET /playbook/similar-strategies` endpoint
- `GET /strategies/{id}/outcomes` endpoint
- `GET /playbook/scores` endpoint

---

## M7 (2026-08-14) — Mobile (Capacitor) + FCM

- Capacitor 5 wrapper around Next.js frontend
- Android Gradle build configuration + deep links (`io.clienthunter.app`)
- Firebase Cloud Messaging integration
- `NotificationService.send_to_user()`, `send_to_admins()`, `send_to_topic()`
- Device token registration endpoint (`POST /devices`) with upsert (3 registrations → 1 row)
- Device token ownership enforcement
- FCM notification on: meeting booked, campaign paused, sequence reply, admin task failure
- Mobile-responsive bottom tab navigation

---

## M6 (2026-08-11) — pip Package / CLI

- `clienthunter` Python SDK (src layout, pyproject.toml, PyPI-ready)
- Sync httpx client with 7 resource objects
- Automatic JWT refresh on 401
- Exponential backoff retry (3 attempts, 2^n seconds)
- Typed exception hierarchy: `ClientHunterError`, `AuthError`, `ComplianceError`, `NotFoundError`, `RateLimitError`
- Typer + Rich CLI: `init`, `run`, `status`, `serve`, `leads`, `campaign`
- 60/60 tests passing (respx HTTP mocks)
- `RELEASING.md` — PyPI publish checklist

---

## M5 (2026-08-07) — Web UI + Theme Engine

- Next.js 14 + TypeScript (strict) + Tailwind CSS + shadcn/ui
- Pages: Dashboard, Strategies (kanban), Campaigns, Leads, Analytics, Settings
- Theme engine: Light / Dark / Enterprise Blue / Midnight / Sand presets + full custom mode
- User-editable: background color, background image, primary/accent colors, font family, font size, border radius, density
- Theme stored as JSON in DB; applied via CSS variables; live preview
- WCAG AA contrast warning on custom themes
- React Query typed API client layer (`frontend/lib/api/`)
- Vitest unit tests + Playwright E2E specs (strategy flow, booking flow)
- JWT auth store (Zustand) with refresh token handling

---

## M4 (2026-08-04) — WhatsApp Business Cloud API

- `WhatsAppChannel` implementing `OutreachChannel` interface
- Template-only cold outreach enforcement
- Opt-in tracking (`whatsapp_optins` table)
- 24-hour customer-service window tracking
- STOP message handling — atomic transaction: suppression + opt-out audit + sequence stop
- Template status verification via Meta Graph API before send
- WhatsApp webhook: inbound message handler + status update handler
- HMAC-SHA256 `X-Hub-Signature-256` webhook signature verification
- `POST /webhooks/whatsapp` endpoint

---

## M3 (2026-07-31) — Gmail Sequences + Calendly

- `GmailChannel` implementing `OutreachChannel` interface
- OAuth 2.0 with automatic refresh token rotation
- RFC 8058 `List-Unsubscribe` header + `List-Unsubscribe-Post` (one-click unsubscribe)
- Signed unsubscribe token (`GET /unsubscribe?token=...` — no auth required)
- Multi-step sequence engine with configurable cadence (days between steps)
- Reply classifier: interested / objection / unsubscribe_request / not_relevant (via Claude)
- Bounce rate tracking — auto-pause campaign at 3%
- Daily send cap enforcement — defer excess sends, never drop
- Calendly OAuth + webhook integration
- `POST /webhooks/calendly` — booking updates lead to `meeting_booked`
- HMAC-SHA256 `Calendly-Webhook-Signature` verification
- `campaign.status` state machine: active / paused_bounce_rate / paused_admin / completed

---

## M2 (2026-07-25) — Apollo/Hunter Integration + Lead DB

- `LeadSource` and `EmailVerifier` abstract interfaces
- `ApolloLeadSource` — ICP-parameterized people search + bulk enrichment
- `HunterEmailVerifier` — deliverability verification; drops `undeliverable` and optionally `risky`
- `leads` table with: apollo_person_id, email, email_verified, status, sequence_status, suppression_checked_at
- Lead deduplication (apollo_person_id + email unique constraint)
- `suppression_list` table with: email, phone, reason, source, user_id
- Suppression checked at sourcing time AND at send time
- Circuit breaker wrapping Apollo and Hunter calls (5 failures → OPEN, 60s recovery)
- `POST /strategies/{id}/leads/source` endpoint
- `GET /strategies/{id}/leads` endpoint (filtered by current user)

---

## M1 (2026-07-18) — Backend Core + Intake Flow + Research Pipeline

- FastAPI app factory (`create_app()`) with lifespan, CORS, middleware
- PostgreSQL 16 + SQLAlchemy 2.0 + Alembic migrations
- Redis 7 + Celery + Celery Beat
- JWT auth: register, login, refresh, protected routes
- `Product` model + CRUD endpoints
- `PastClient` model + `POST /products/{id}/past-clients`
- Past-client pattern extraction via Claude (dominant channel, role, industry, trigger events)
- 72-step and 144-step pipeline engine:
  - 8 phases × 9 steps each
  - Each step dispatched as a Celery task
  - Resumable (idempotent step execution — crashed pipelines resume at the next unstarted step)
  - Playbook context injection in Phase 6 + 8 (even if empty on first run)
- `research_steps` table: step_no, status (pending/in_progress/complete/stalled), output (JSON), updated_at
- 10-pass verification loop with per-pass `VerificationPassResult` (pass_number, result, notes, fixes_applied)
- `verified_passes_json` persisted on strategy
- Verification gating: `POST /leads/source` returns 422 if any pass is FAIL
- Docker Compose dev config (postgres, redis, api, worker, beat)
- `.env.example` — full annotated template

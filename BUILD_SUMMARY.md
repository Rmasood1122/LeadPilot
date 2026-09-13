# BUILD_SUMMARY.md — overnight autonomous build, 2026-09-13

Scope: brief sections **B + C + D** (identity/location, phone OTP, VPN
blocking), **E** (pricing + billing) and **A1–A7** (seven product features),
built in that order on the existing FastAPI + Next.js architecture, every one
with backend (pytest) and frontend (vitest) tests.

Companion documents: **BUILD_DECISIONS.md** (every choice made without asking,
with reasoning and how to reverse it) and **BUILD_BLOCKERS.md** (what needs an
external credential before it works for real).

Nothing was committed — all changes are in the working tree for review.

---

## 1. Results

| Check | Result |
|---|---|
| Backend pytest (all `tests/test_*.py`, 97 files) | **1,985 passed, 5 skipped, 0 failed** (baseline before the build: 1,660 passed, 5 skipped) |
| Frontend `tsc --noEmit` | clean |
| Frontend vitest | **32 files, 389 tests passed** |
| Frontend `next build` (static export) | success — `/pricing`, `/share/roi`, `/onboarding/verify`, `/crm/replies`, `/admin/identity-reviews` all exported as static pages (no dynamic routes) |
| Migrations on real PostgreSQL (throwaway DB on compose Postgres :5433, dropped afterwards) | `upgrade head` → `0047_sequence_reviews`; all 9 new tables present; audit trigger refuses content update, payload update, re-seal and delete, allows the first seal; `downgrade 0038_website_builder` and back to head succeed |

The backend suite ran in four sequential chunks: a single-process run was
killed twice by the host for low memory (8 GB machine). The chunk containing
the A7 fix below was re-run after the fix and passed (400 passed).

---

## 2. Features completed

### Section B — Identity & location verification (onboarding)
- Onboarding asks the **personal country**, **individual vs company**, and the
  **company's country** (may differ); stored as structured columns on `users`.
- The declared personal country is cross-checked against **IP geolocation**
  (`app/integrations/geolocation.py`, provider via `GEOLOCATION_PROVIDER`:
  ipapi.co / ipinfo.io). A mismatch **never blocks**: it sets
  `geo_review_status=pending`, writes `account_security_events`, and appears
  in **Admin → Identity Reviews** (clear / confirm risk, both audited).
- Applies only to accounts created after migration 0039 (existing accounts are
  never forced through it).
- API: `GET /onboarding/countries`, `GET /onboarding/verification`,
  `PUT /onboarding/identity`, `GET/POST /admin/identity-reviews`,
  `GET /admin/security-events`. UI: `/onboarding/verify` (Shell redirects new
  accounts there), `/admin/identity-reviews`.

### Section C — Phone verification (OTP)
- Phone number collected in the same flow; 6-digit code by SMS
  (`app/integrations/sms.py`: `twilio` / `console` / `memory`, via
  `SMS_PROVIDER`). Only an HMAC of the code is stored, bound to user + number.
- Expiry (10 min), 5 wrong attempts kill a code, 60 s resend cooldown, rate
  limits per account **and** per number (`RATE_LIMIT_OTP_SEND/VERIFY`, same
  `enforce_rate_limit` pattern as auth), one verified account per number.
- **Gated on a verified phone** (post-0039 accounts): launching outreach
  (enroll/approve), buying a plan, creating public share links — `403
  PHONE_NOT_VERIFIED`. Kill switch `REQUIRE_PHONE_VERIFICATION`.
- API: `POST /onboarding/phone/send`, `POST /onboarding/phone/verify`.

### Section D — VPN / proxy blocking at signup and login
- `app/integrations/ip_intelligence.py` (proxycheck.io / IPQualityScore via
  `VPN_DETECTION_PROVIDER`, Redis-cached) + `app/services/network_guard.py`,
  called inside `/auth/signup` and `/auth/login` after the rate limiters.
- VPN, proxy, Tor and datacenter IPs get `403` "…disable your VPN or proxy and
  try again from your normal network." (+ `X-Block-Reason: VPN_BLOCKED`), and an
  audit row. `VPN_BLOCK_ENABLED` (unset = on only in production), allowlist,
  fail-open by default on provider outage. Tests mock the provider.

### Section E — Pricing page + billing
- **Public `/pricing` page**: Monthly subscription (**marked Recommended**,
  4 tiers: Starter $149 / Growth $349 / Scale $699 / Enterprise $1,499, 14-day
  trial) side by side with **Pay per meeting booked** ($0/mo + $179 per booked
  meeting), plus a break-even comparison slider. All numbers come from
  `GET /billing/catalog` (`app/core/billing_catalog.py`); limits are the ones
  `app/core/plans.py` already enforces.
- Billing model: `billing_subscriptions`, `billable_meetings`; Stripe over REST
  (`app/integrations/stripe_billing.py`) — Checkout (subscription / setup
  mode), per-meeting invoices, cancellation, signed + idempotent
  `/webhooks/stripe`. **Stub mode without keys** (`# TODO: connect live Stripe
  keys`, logged in BUILD_BLOCKERS.md).
- Pay-per-meeting metering: a session listener meters every BOOKED outcome via
  `usage_meter.record_meeting_usage` (once per prospect, 48 h cancellation
  grace, disputes), charged by a 30-minute Celery sweep; fees flow into
  `revenue_analytics.report` as a `platform` cost.
- API: `/billing/catalog`, `/billing`, `/billing/checkout`, `/billing/cancel`,
  `/billing/meetings`, `/billing/meetings/{id}/dispute`,
  `/admin/billing/meetings/{id}/resolve`, `/webhooks/stripe`.

### A1 — Fabrication-proof claim engine
- `app/services/claim_verification.py`: every AI-written email, LinkedIn
  message, WhatsApp text/template variable and call script is checked in the
  send task **before** it is persisted and sent. Claims (funding, headcount,
  hiring, job change, news, metrics, expansion, "your post") must be backed by
  stored Apollo/Hunter enrichment, NewsAPI news or LinkedIn posts — numbers,
  "Series X", quotes and names must appear in the evidence. Unsupported claims
  are stripped, or rewritten to a neutral line; fails closed on verifier error.
- Every decision logged to **`claim_verification_log`**; shown on the lead page
  ("Claim checks"); `GET /leads/{id}/claim-checks`, `GET /claim-checks/summary`.

### A2 — Tamper-evident send/reply audit trail
- `activity_audit_events`: every send / open / **click** / reply /
  meeting-booked event, recorded in the same transaction as its Outcome,
  hash-chained per account (`content_hash`, `prev_hash`, `chain_hash`,
  `seq_no`) by a serialised sealer; append-only via ORM guard + PostgreSQL
  trigger.
- Signed export per account/workspace: **Ed25519-signed JSON** and a **PDF**
  (`GET /audit/trail/export?format=json|pdf`), public `GET /audit/public-key` and
  `POST /audit/verify` for the buyer. UI: Settings → Deliverability.
- Click tracking added (`/t/c/{token}`, HMAC-bound, off by default).

### A3 — Reply-authenticity scoring
- `app/services/reply_authenticity.py` (+ extended `reply_fraud.py`): every
  inbound reply on email/WhatsApp/LinkedIn is scored in real time — genuine /
  out-of-office / auto-responder / bot / bounce, with authenticity, buyer-intent
  and confidence scores and the signals behind them.
- New **CRM → Replies** inbox with the scores; `GET /crm/replies`,
  `GET /crm/replies/{id}/authenticity`, `POST …/authenticity/rescore`.

### A4 — Cross-channel unified conversation thread
- `app/services/conversation_thread.py`: email, LinkedIn, WhatsApp, calls,
  bookings and meetings in one chronological thread (typed `ThreadItem` model);
  lead page "Conversation" tab.
- New pipeline step `app/pipeline/channel_orchestrator.py` (hourly): detects
  channel stagnation (N unanswered sends since the last genuine reply) and
  suggests — or, when enabled, auto-switches the next scheduled message to —
  the next best channel (plan/consent/account aware, outcome-ranked).
- API: `/leads/{id}/conversation`, `/leads/{id}/channel-suggestions`,
  `/channel-suggestions` (+ `/detect`, `/{id}/accept`, `/{id}/dismiss`).

### A5 — Outcome-based optimiser + kill-signal detection
- `app/services/conversion_probability.py`: live, explainable conversion
  probability per lead; kill signals (bounce, unsubscribe, not interested).
  A gate in the send task holds cold leads (**cooling** → sequence paused +
  CRM tag; **archived** → sequence stopped + tag) instead of sending; hourly
  rescore sweep; reactivation.
- `send_time_optimizer.py` extended with outcome-weighted (bookings ×3) channel
  ranking and slot scores; `score_decay.py` with `engagement_weight`.
- API: `/leads/{id}/conversion`, `/leads/{id}/conversion/reactivate`,
  `/conversion/at-risk`, `/strategies/{id}/channel-performance`. UI: lead
  Overview card.

### A6 — Client-facing shareable ROI dashboard
- Token-secured, **revocable and expiring** public links (hash-only storage)
  to a read-only dashboard: pipeline stages, meetings booked, revenue
  attributed, pipeline value, weekly trend — built on `roi_calculator` +
  `roi_snapshots`; no lead PII.
- API: `/share-links` (create/list/revoke), public `/public/roi/{token}`.
  UI: Settings → Sharing; public page `/share/roi?token=`.

### A7 — Pre-send adversarial review agent
- `app/services/adversarial_review.py`: before activation (enroll **and**
  manager approval) a red-team pass flags spam/tone, compliance (CAN-SPAM,
  WhatsApp opt-in/template rules, GDPR/PECR, call consent) and unverifiable
  claims (A1's categories). Blocking findings return `409
  SEQUENCE_REVIEW_BLOCKED` until fixed or overridden by an owner/manager with a
  reason (logged; bound to a content hash). An AI red-team pass adds warnings.
- API: `/sequences/{id}/review` (GET/POST), `/sequences/{id}/review/override`.
  UI: review panel on each sequence (Campaigns) and on pending launches (Team).

---

## 3. Migrations added (linear chain from 0038)

| Revision | Creates / alters |
|---|---|
| `0039_identity_verification` | 16 `users` columns (identity, geo check/review, phone); `phone_verification_codes`; `account_security_events` |
| `0040_billing` | `billing_subscriptions`; `billable_meetings` (UNIQUE user+prospect) |
| `0041_claim_verification_log` | `claim_verification_log` |
| `0042_activity_audit_trail` | `activity_audit_events` + PostgreSQL append-only trigger |
| `0043_reply_authenticity` | 6 `inbound_replies` authenticity columns |
| `0044_channel_suggestions` | `channel_suggestions` |
| `0045_conversion_probability` | 5 `leads` columns (probability, state, kill signal, factors) |
| `0046_share_links` | `share_links` |
| `0047_sequence_reviews` | `sequence_reviews` |

Enum additions (data-free, VARCHAR-backed): `PlanTier` growth / scale /
pay_per_meeting; `OutcomeEvent.CLICKED`. `scripts/activate_with_keys.py`
`TARGET_REVISION` moved to `0047_sequence_reviews` (a test pins it to head).

---

## 4. New environment variables

All have safe defaults; placeholders added to `.env.example` and
`.env.production.example`.

| Variable | Default | Purpose |
|---|---|---|
| `GEOLOCATION_PROVIDER` / `GEOLOCATION_API_KEY` / `GEOLOCATION_TIMEOUT_SECONDS` | `ipapi_co` / – / 4 | IP → country at onboarding |
| `VPN_BLOCK_ENABLED` | unset (= on in production) | VPN/proxy blocking switch |
| `VPN_DETECTION_PROVIDER` / `VPN_DETECTION_API_KEY` | `proxycheck` / – | IP intelligence provider |
| `VPN_DETECTION_TIMEOUT_SECONDS` / `VPN_DETECTION_FAIL_CLOSED` / `VPN_DETECTION_CACHE_SECONDS` / `VPN_ALLOWLIST_IPS` | 4 / false / 3600 / – | Guard behaviour |
| `SMS_PROVIDER` | `console` | `twilio` / `console` / `memory` |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` / `SMS_SEND_TIMEOUT_SECONDS` | – / – / – / 10 | Twilio transport |
| `PHONE_OTP_TTL_SECONDS` / `PHONE_OTP_MAX_ATTEMPTS` / `PHONE_OTP_RESEND_COOLDOWN_SECONDS` | 600 / 5 / 60 | OTP rules |
| `REQUIRE_PHONE_VERIFICATION` | true | Phone gate kill switch |
| `RATE_LIMIT_OTP_SEND` / `RATE_LIMIT_OTP_VERIFY` | 5 / 10 | OTP limits (app/core/config.py) |
| `RATE_LIMIT_PUBLIC_SHARE` | 120 | Public dashboard + `/audit/verify` per IP/hour |
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | – / – | Empty = stub mode / webhook closed |
| `STRIPE_PRICE_STARTER/GROWTH/SCALE/ENTERPRISE` | – | Optional pre-created Price ids |
| `STRIPE_API_BASE` / `STRIPE_TIMEOUT_SECONDS` / `STRIPE_WEBHOOK_TOLERANCE_SECONDS` | api.stripe.com / 20 / 300 | Transport |
| `AUDIT_SIGNING_KEY` | – (derived from SECRET_KEY) | Ed25519 seed for signed audit exports |

New **admin system settings** (Admin → System Settings, no redeploy):
`claim_verification_enabled`, `claim_model_extraction_enabled`,
`click_tracking_enabled`, `stagnation_detection_enabled`,
`stagnation_email_sends`, `stagnation_other_sends`, `stagnation_min_hours`,
`stagnation_auto_switch_enabled`, `conversion_gate_enabled`,
`conversion_default_prior`, `conversion_cooling_threshold`,
`conversion_archive_threshold`, `conversion_min_unanswered_sends`,
`conversion_cooling_pause_days`, `conversion_inactivity_half_life_days`,
`sequence_review_enabled`, `sequence_review_model_enabled`.

New **Celery beat tasks** (each routed to a queue the compose/Railway workers
consume): `charge-due-meetings` (30 min, default), `seal-audit-trails`
(5 min, default), `detect-channel-stagnation` (hourly :25, outreach),
`rescore-conversion-probability` (hourly :40, learning).

---

## 5. Files touched

### Modified (37)
Backend: `app/config.py`, `app/core/config.py`, `app/core/plans.py`,
`app/db/models.py`, `app/main.py`, `app/api/admin.py`, `app/api/auth.py`,
`app/api/crm.py`, `app/api/onboarding.py`, `app/api/sequences.py`,
`app/api/tracking.py`, `app/integrations/gmail.py`, `app/services/open_tracking.py`,
`app/services/rbac.py`, `app/services/reply_fraud.py`,
`app/services/revenue_analytics.py`, `app/services/score_decay.py`,
`app/services/send_time_optimizer.py`, `app/services/system_settings.py`,
`app/services/usage_meter.py`, `app/workers/celery_app.py`,
`app/workers/outreach_tasks.py`, `scripts/activate_with_keys.py`,
`.env.example`, `.env.production.example`.
Frontend: `src/app/(admin)/admin/layout.tsx`, `src/app/(app)/campaigns/page.tsx`,
`src/app/(app)/leads/detail/page.tsx`, `src/app/(app)/settings/page.tsx`,
`src/app/(app)/team/page.tsx`, `src/components/crm/CrmChrome.tsx`,
`src/components/settings/PlanCard.tsx`, `src/components/shell/Shell.tsx`,
`src/lib/api/admin.ts`, `src/lib/api/types.ts`.
Tests: `tests/conftest.py` (test env defaults, SMS outbox, FakeClaude branches
for the claim extractor and red-team auditor), `tests/test_crm_dashboard.py`
(see §7).

### New — backend
- Migrations: `alembic/versions/0039…0047` (9 files).
- API: `app/api/audit.py`, `billing.py`, `claims.py`, `conversations.py`,
  `conversion.py`, `sequence_reviews.py`, `share_links.py`.
- Core: `app/core/billing_catalog.py`.
- Integrations: `app/integrations/geolocation.py`, `ip_intelligence.py`,
  `sms.py`, `stripe_billing.py`.
- Pipeline: `app/pipeline/channel_orchestrator.py`.
- Services: `app/services/adversarial_review.py`, `audit_trail.py`,
  `billing.py`, `claim_verification.py`, `conversation_thread.py`,
  `conversion_probability.py`, `countries.py`, `identity.py`,
  `network_guard.py`, `phone_verification.py`, `reply_authenticity.py`,
  `share_links.py`.
- Workers: `app/workers/audit_tasks.py`, `billing_tasks.py`,
  `channel_tasks.py`, `conversion_tasks.py`.
- Tests (20): `tests/test_identity_verification.py` (+`_migration`),
  `test_phone_verification.py`, `test_vpn_blocking.py`, `test_billing.py`
  (+`_migration`), `test_claim_verification.py` (+`_migration`),
  `test_activity_audit_trail.py` (+`_migration`), `test_reply_authenticity.py`
  (+`_migration`), `test_conversation_thread.py`,
  `test_channel_suggestions_migration.py`, `test_conversion_probability.py`
  (+`_migration`), `test_share_links.py` (+`_migration`),
  `test_sequence_reviews.py` (+`_migration`).
- Docs: `BUILD_SUMMARY.md`, `BUILD_DECISIONS.md`, `BUILD_BLOCKERS.md`.

### New — frontend
- Pages: `src/app/pricing/page.tsx`, `src/app/share/roi/page.tsx`,
  `src/app/(app)/onboarding/verify/page.tsx`, `src/app/(app)/crm/replies/page.tsx`,
  `src/app/(admin)/admin/identity-reviews/page.tsx`.
- Components: `components/campaigns/SequenceReviewPanel.tsx`,
  `components/leads/ClaimChecksPanel.tsx`, `ConversationThread.tsx`,
  `ConversionCard.tsx`, `components/settings/AuditTrailCard.tsx`,
  `ShareLinksCard.tsx`, `components/ui/native-select.tsx`.
- Logic (pure, tested): `lib/audit.ts`, `authenticity.ts`, `claims.ts`,
  `conversation.ts`, `conversionProbability.ts`, `identity.ts`, `pricing.ts`,
  `sequenceReview.ts`, `shareLinks.ts`.
- API clients: `lib/api/audit.ts`, `billing.ts`, `claims.ts`,
  `conversations.ts`, `conversion.ts`, `identity.ts`, `replies.ts`,
  `sequenceReview.ts`, `shareLinks.ts`.
- Tests (9): `src/tests/audit.test.ts`, `authenticity.test.ts`,
  `claims.test.ts`, `conversation.test.ts`, `conversionProbability.test.ts`,
  `identity.test.ts`, `pricing.test.ts`, `sequenceReview.test.ts`,
  `shareLinks.test.ts`.

(The brief named `frontend/tests`; this repo's vitest suite lives in
`frontend/src/tests`, so the new tests follow the existing location.)

---

## 6. Decisions (summary — full reasoning in BUILD_DECISIONS.md)

- Identity flow and phone gate apply only to post-0039 signups; a country
  mismatch flags for review, never blocks; detected country never echoed.
- Phone-gated actions: launch outreach, buy a plan, create share links.
- VPN block: on in production by default, fail-open on provider outage,
  blocks datacenter IPs too (allowlist available).
- Prices: Starter $149, Growth $349, Scale $699, Enterprise $1,499 (14-day
  trial); pay-per-meeting $0 + $179/meeting, 48 h grace, once per prospect.
  No unenforced limits (seats, SLAs) advertised.
- Stripe via REST (no SDK), stub mode without keys.
- Claim engine checks only claims about the prospect, fails closed.
- Audit trail: listener recording + separate sealer; no FKs on hashed refs;
  Ed25519-signed JSON; click tracking off by default.
- Authenticity: deterministic real-time scoring, no extra model call.
- Conversation thread is a read model; stagnation auto-switch off by default,
  never for WhatsApp.
- Conversion gate never judges a lead on probability before 4 unanswered sends.
- Share links: hashed bearer tokens, mandatory expiry, uniform 404.
- Review: only deterministic rules block; model findings warn; overrides need
  a manager + reason and are bound to a content hash.

## 7. Blockers (summary — details in BUILD_BLOCKERS.md)

1. **Twilio credentials** for real SMS delivery (console transport until then).
2. **VPN-detection API key** for more than ~1k lookups/day.
3. Optional **geolocation key** at scale.
4. **Stripe keys + webhook secret** for real charges (stub mode until then).

## 8. Changes to existing tests, and what was not verified

- `tests/test_crm_dashboard.py::test_bookings_trend_is_bucketed_by_day` was a
  pre-existing **time-of-day flake**: "a day ago" and "a day and two hours ago"
  straddle midnight when the suite runs 00:00–02:00 UTC (it failed at 00:31 UTC
  during this build, independent of any change). Anchored its timestamps at
  noon UTC; the assertion is unchanged.
- `tests/conftest.py` gained env defaults and fakes only; no existing fixture's
  behaviour changed.
- Found in the final regression and fixed in code (not in the test): A7's
  `adversarial_review.latest()` orders by `created_at`, whose server default
  has one-second resolution on SQLite, so a review created in the same second
  as an overridden one tied on a random UUID and the old override could be
  reported as current. `run_review` now stamps `created_at` in Python with
  microsecond precision; the test passed 3 consecutive runs afterwards.
- **Not run:** `tests/integration` (its fixtures `flushdb` the compose Redis on
  6380, which the currently running local worker/beat containers use), the
  Playwright E2E suite, and manual browser QA of the new pages. **No live
  third-party API** (Twilio, proxycheck, ipapi, Stripe) was contacted.
- Known limits, stated rather than hidden: removing the *newest* audit records
  is only detectable against a previously exported signed report; claim rules
  are English-only; the model claim extractor adds one Claude call per send
  (switchable).

# Platform gaps — evidence (2026-10-11)

Branch `claude/platform-gaps`, based on the master hotfix `d43fa43` (PR #78).
Founder instruction: "fix every open gap". Each item below was verified
against the code first; one was skipped by instruction (7) and one claim was
partly wrong (6, home page). Every item has a failing-first test; the pre-fix
runs were made against `git archive HEAD` (the untouched base) extracted into
a scratch directory with the new test files copied in.

Commands, counts and exit codes are in **Runs** at the end.

| # | Gap | Verdict | Outcome |
|---|---|---|---|
| 1 | No password reset | confirmed | built (spec `docs/features/password-reset.md`) |
| 2 | PD-2 webhook FKs missing on PostgreSQL | confirmed | migration `0085_webhook_foreign_keys` |
| 3 | Scheduled sends continue after a downgrade | confirmed | send-time plan hold — **needs founder confirmation** |
| 4 | `/health` returns raw exception text | confirmed (+ `/health/channels`) | fixed string, detail logged |
| 5 | Offline banner claims campaigns still run | confirmed | reworded to what the device can know |
| 6 | Home + /pricing lack the shared Footer | /pricing confirmed; home page claim wrong | /pricing uses Footer; home skipped (redirect-only) |
| 7 | Monthly checkout lacks renewal consent | confirmed | **skipped by instruction** (billing branch) |
| 8 | Stale program docs | confirmed | corrected with file:line evidence |

---

## 1. Password reset

**Verified gap.** `grep -rni "password.reset|reset.password|forgot"` over
`app/`, `frontend/src`: no route, service or page. `app/core/admin_bootstrap.py`
said "There is no password-reset flow anywhere in this application"; help
center 23 and 29 told users to contact support.

**Fix.** `POST /auth/password-reset/request` (always 200, per-IP and
per-address limits on their own buckets, 60 s per-account cooldown, email
sent after the response) and `POST /auth/password-reset/confirm` (8–256
character rule, hash-only single-use 60-minute token, burns every outstanding
link, revokes every refresh session, audit rows, issues no tokens).
Suspended and passwordless pre-auth accounts can never reset; deleted
accounts' tokens cascade away. Frontend: "Forgot password?" on sign-in,
`/forgot-password`, `/reset-password` (token in the URL fragment, stripped
from the address bar). Full behaviour, security review, limitations and
"Unverified": `docs/features/password-reset.md`.

| File | Purpose |
|---|---|
| `app/services/password_reset.py` (new) | eligibility, token issue/burn/cooldown, email, redeem |
| `app/api/auth.py:531-634` | the two endpoints (+ `BackgroundTasks` import, module docstring) |
| `app/db/models.py` `PasswordResetToken` + `User.password_reset_tokens` | table model |
| `alembic/versions/0084_password_reset.py` (new) | create-only migration |
| `app/config.py` `password_reset_ttl_minutes = 60` | setting |
| `app/services/security_audit.py` | `auth.password_reset_requested` / `auth.password_reset` / `auth.password_reset_refused` |
| `app/services/account_export.py` `EXCLUDED` | reset tokens are hashes; requests export via `security_audit_events` |
| `scripts/activate_with_keys.py` `TARGET_REVISION` | new head `0085_webhook_foreign_keys` |
| `frontend/src/app/(auth)/forgot-password/page.tsx`, `reset-password/page.tsx` (new) | pages |
| `frontend/src/app/(auth)/login/page.tsx` | "Forgot password?" link |
| `frontend/src/lib/passwordReset.ts` (new), `frontend/src/lib/api/auth.ts` | rules, API calls |
| `docs/help-center/23-account-security.md`, `29-known-limitations.md`, `00-index.md` | articles no longer say there is no reset |
| `tests/help_center/golden_questions.yaml` q37, q69 | the reset section became its own chunk; expected chunk id moved to it (the content those questions ask about) |
| `.env.example`, `.env.production.example`, `docs/setup/environment-variables.md` | `PASSWORD_RESET_TTL_MINUTES` |
| `docs/features/email-verification.md`, `app/core/admin_bootstrap.py` docstring | removed "no password reset" statements |

**Tests.** `tests/test_password_reset.py` (43 after the review round),
`tests/test_platform_gaps_migrations.py::TestPasswordResetMigration` (4),
`frontend/src/tests/passwordReset.test.tsx` (13).

**Pre-fix.** `tests/test_password_reset.py`: collection error
`ImportError: cannot import name 'password_reset' from 'app.services'`.
Behaviour probe on the base: `POST /auth/password-reset/request` → 404,
`/confirm` → 404. Migration tests: 14 of 15 failed (no 0081/0082 file).
`passwordReset.test.tsx`: failed to load (modules do not exist).

**Security / regression / deploy.** No account enumeration (asserted: same
body for known and unknown addresses). Reset traffic cannot exhaust the
sign-in allowance (asserted). Login, change-password, verification tests all
pass unchanged. Deploy needs migration 0084 and `FRONTEND_URL` set to the
public web origin (it already is required for verification links).

---

## 2. PD-2 — webhook foreign keys

**Verified gap.** `alembic/versions/0011_m8c5_production_launch.py:25-58`
creates `webhook_targets.user_id` and `webhook_deliveries.target_id` as bare
uuid columns; the model (`app/db/models.py` `WebhookTarget`, `WebhookDelivery`)
declares `ForeignKey(..., ondelete="CASCADE")`; no later migration adds them
(`grep create_foreign_key` over `alembic/versions`). Proven on PostgreSQL:
`test_before_0082_postgres_has_no_webhook_fks` (at 0081 both tables have no
FK).

**Fix.** `alembic/versions/0085_webhook_foreign_keys.py`:
1. deletes orphans in dependency order — targets whose `user_id` matches no
   user, then deliveries whose `target_id` matches no target (which includes
   the deliveries of the targets just deleted) — and logs both counts. These
   rows are unreachable through the API (every webhook route filters by
   owner) and an orphaned delivery holds a lead-data payload for an account
   that no longer exists; deleting them is also GDPR storage limitation. They
   cannot be restored.
2. adds `fk_webhook_targets_user_id_users` and
   `fk_webhook_deliveries_target_id_webhook_targets`, both `ON DELETE
   CASCADE`. Names = the naming convention in `app/db/base.py`, i.e. exactly
   what the model metadata produces (asserted), as earlier FK migrations do
   (`0063_client_workspaces.py:102`, `0026_linkedin_channel.py:86`).
3. skips a constraint that already exists (model-built databases), runs in
   batch mode (works on SQLite: table copy), and bounds PostgreSQL lock waits
   with `lock_timeout = 15s` like 0071.
Downgrade drops only the constraints; deleted orphans are not restored.

**Tests.** SQLite: `tests/test_platform_gaps_migrations.py::TestWebhookForeignKeysMigration`
(8: chain, names, legacy shape has none, both FKs added with CASCADE, only
orphans deleted, user delete cascades, existing FKs untouched, downgrade).
PostgreSQL: `tests/integration/test_migration_0085_webhook_fks.py` (4: defect
present at 0081, upgrade cleans orphans + adds FKs + user delete cascades,
orphan insert now refused, downgrade/upgrade round trip) — each test on its
own scratch database via alembic subprocess, like
`test_migration_0071_webhook_schema.py`.

**Pre-fix.** On the base the migration file does not exist: the SQLite
migration tests fail (file not found); the PG defect test is the proof of the
gap itself.

**Deploy.** Production runs 0081 → 0082 on boot; the orphan counts appear in
the migration log line `0082: deleted N orphaned webhook_targets and M
orphaned webhook_deliveries`. **Unverified:** how many orphans production has
(needs a read-only query; none was made).

---

## 3. Scheduled sends after a plan downgrade — **needs founder confirmation**

**Verified gap.** Plans were enforced at sequence create and launch only
(`app/api/sequences.py:58-80,225`); `send_message_impl` read no plan. Proven
on the base: a WhatsApp step launched on Starter, owner then set to Free, was
**sent** (`pre-fix: sent; transmitted 1`).

**Decision (code truth, safest):** at send time the strategy owner's CURRENT
`users.plan` (which `billing._sync_plan` keeps in step with the subscription)
must cover the message: its channel (`check_send_channel`, every origin) and,
for ordinary sequence messages (`origin` NULL), `step_no <=
max_sequence_steps`. Re-engagement and Reply Copilot rows are not numbered
steps, so only the channel rule applies to them. A message that fails is
**held**, not cancelled and not sent: `FAILED` with `error = "plan_limit:
<reason>"`, audited (`held_plan_limit`), enrollment NOT stopped. Steps still
covered keep sending. The `plan_limit: ` prefix is registered in
`send_holds.HOLD_PREFIXES`, so the follow-up sweep treats the held message as
the step's pending message and never creates a copy (asserted). The check
sits after every cancelling gate (suppression, exclusions, departures,
derived opt-outs), so a message that must never go out is still cancelled. An
owner that cannot be resolved defers the message an hour (fails closed).

Why hold rather than cancel: downgrades are often temporary (failed card,
mid-month change); holding never sends unpaid outreach and does not destroy
the customer's work. **Review round (coordinator decision, founder item):**
the check is grandfathered and self-releasing — see "Review round" R1 below.

| File | Purpose |
|---|---|
| `app/services/plan_holds.py` (new) | `send_block`, `hold_message`, constants |
| `app/workers/outreach_tasks.py:296-326` | the check in the send chokepoint (+ `User` import) |
| `app/services/send_holds.py` | `PLAN_LIMIT_PREFIX` added to `HOLD_PREFIXES` |
| `FEATURES.md` Stage 6; help center 08, 11, 22 | describe the hold |
| `tests/conftest.py` `entitle_owner` + `multichannel_sequence` | see below |
| `tests/test_linkedin_channel.py`, `tests/test_phone_calls.py`, `tests/test_whatsapp_engine.py`, `tests/test_bounce_shield.py` | fixtures put the owner on the cheapest plan with the channel |

**Existing tests changed, and why.** 27 existing tests (LinkedIn 9, phone 8,
WhatsApp engine 7, WhatsApp window 2, Bounce Shield 1 — measured by running the
base's test files against this branch's code) built LinkedIn, phone and
WhatsApp sequences directly in the database for a Free-plan owner (bypassing
launch) and asserted the send path's behaviour. With send-time
entitlement those messages are now held — the correct new contract. Their
fixtures now put the owner on the cheapest plan that includes the channel
(Starter / Growth / Scale), exactly as `tests/test_phone_calls.py:352-354`
already did for plan enforcement ("this test is about the call path, not
plans"). No assertion was removed or weakened; no sealed test was touched
(`test_compliance.py` and `test_whatsapp_guard.py` pass unchanged).

**Tests.** `tests/test_plan_downgrade_holds.py` (27): channel and step rules
for every plan, non-sequence origins, prefix registered, downgraded channel
held (not transmitted, enrollment active), audit row, entitled channel still
sends, step 6 on Free held with the exact reason, steps inside the limit
send, upgrade lifts the limit, held message never re-dispatched or retried,
follow-up sweep makes no copy, plan check failure fails closed, suppression
still cancels first.

**Pre-fix.** `test_plan_downgrade_holds.py`: collection error (`plan_holds`
does not exist); behaviour probe: downgraded WhatsApp step `sent`.

---

## 4. `/health` exception text

**Verified gap.** `app/services/health_checks.py` `check_celery_heartbeat`
returned `{"status": "degraded", "error": str(e)}` on the PUBLIC `/health`
(pinned by `test_status_public.py`, e.g. `"could not convert string to float:
'garbage'"`). Also found: `GET /health/channels` (any signed-in user) returned
`str(e)` for its Gmail / WhatsApp / Calendly Redis reads. Redis client errors
name hosts and ports.

**Fix.** Celery: fixed string `"heartbeat check failed"`
(`health_checks.CELERY_CHECK_FAILED`), exception + type logged as
`health.celery_check_failed`. Channels: `{"status": "unknown", "error":
"check failed"}` via `_channel_check_failed` (`app/api/health.py:139`), logged
as `health.channel_check_failed`. Database and Redis already returned fixed
strings. `/health/learning-loop` is admin-only and still returns its error
text (operator surface; left as is, reported).

**Existing tests changed.** `tests/test_status_public.py`: two byte pins
(`test_unparseable_heartbeat_…`, `test_redis_down_is_503_exact_bytes`) pinned
the exception text in `celery.error`; they now pin the fixed string. Every
other byte of `/health` is unchanged, including the UptimeRobot keyword
prefix. `docs/program/STATUS_PAGE.md` §11 follow-up marked fixed.

**Tests / pre-fix.** `tests/test_health_error_text.py` (2): both failed on the
base (exception text in the body).

---

## 5. Offline banner wording

**Verified gap.** `frontend/src/components/ui/OfflineBanner.tsx` (root layout,
every page) said "Your campaigns are still running" when the API is
unreachable — the one thing an outage makes unknowable.

**Fix.** Offline (device): "Scheduled sends run on LeadPilot's servers, not
on this device, so losing your connection does not stop them." — true by
construction. Server unreachable: "We can't reach LeadPilot's server right
now, so we can't confirm whether scheduled sends are going out. We'll
reconnect automatically." plus a "Check service status" link when the status
page link is live (`SHOW_STATUS_LINK`), consistent with the status page, which
shows components as unknown when LeadPilot's own checks cannot be reached
(`status-page/lib/snapshot.ts:201`). Help center 26 updated.
`NetworkContext.tsx` comment updated. The status page app itself has no
"still running" copy (grep), so nothing changed there.

**Tests / pre-fix.** `OfflineBanner.test.tsx`: the old "campaign reassurance"
test asserted the false copy; replaced by 5 tests (offline wording, no
"still running" anywhere, status link only when live). 4 of them failed on
the base.

---

## 6. Shared Footer on public pages

**Verified.** `/pricing` (`frontend/src/app/pricing/page.tsx`) rendered no
footer: no Legal links, no Status link. **The home-page claim is wrong:**
`frontend/src/app/page.tsx` renders `null` and only redirects (to `/login`,
the dashboard or `/check-email`), so there is nothing to put a footer under;
skipped (a test pins that it stays a redirect).

**Fix.** `/pricing` renders `<Footer tone="theme" />`. `Footer` gained a
`tone` prop (`"dark"` default, unchanged for the dark marketing pages;
`"theme"` uses the app theme tokens so it is legible on `/pricing`).

**Tests / pre-fix.** `frontend/src/tests/publicFooter.test.tsx` (9): all six
public pages render the shared Footer, home is redirect-only, theme tone keeps
Legal + Status links, dark default unchanged. 2 failed on the base. D1
`websiteClaims.test.ts` stays green (6/6).

---

## 7. Monthly checkout renewal consent — SKIPPED (instruction)

Confirmed on this branch: no `accept_renewal` / renewal-consent field in
`app/api/billing.py`, `app/services/billing.py`, `frontend/src/app/pricing/page.tsx`
or `frontend/src/lib/pricing.ts` (grep). Per instruction the server-side
`accept_renewal_terms` requirement for every new subscription checkout is the
other branch's job; billing was not touched here. Legal basis to confirm with
counsel on that branch (state automatic-renewal laws such as California's
ARL, Bus. & Prof. Code §17600 et seq., and the FTC's ROSCA) — **needs
founder/legal confirmation; not a settled reading.**

---

## 8. Stale program docs

All corrected to the code with file:line evidence (DECISIONS.md and
STAR_PROMPT.md not edited).

| Doc | Was | Now (evidence) |
|---|---|---|
| `docs/program/BASELINE.md` §1 rows 1–4, §3.1 rows | plan enforcement, per-account AI cap, sign-up switch, GDPR export OPEN | FIXED on master by #58 / #55 / #56 / #57 with `app/api/sequences.py:58-80,225`, `app/api/leads.py:99-101`, `app/api/calls.py:163`, `app/services/usage_meter.py:257-278,402-409`, `app/api/auth.py:228-242`, `app/config.py:457-458`, `app/api/account_data.py:51`; residuals kept: account DELETION open, sign-up default still open (`.env.production.example:309`). Original wording kept struck through. |
| `docs/compliance.md` email table + intro | `GMAIL_DAILY_SEND_CAP` default 500; `{unsubscribe_link}` token check; HMAC token at `?token=`; Gmail adapter raises `MISSING_UNSUBSCRIBE`; `GMAIL_BOUNCE_PAUSE_THRESHOLD`; warm-up 20/day over 30 days | `GMAIL_DAILY_CAP` default **100** (`app/config.py:106`, read at `sequence_engine.py:166`; `GMAIL_DAILY_SEND_CAP` in `app/core/config.py:392` is read by nothing); visible footer from `compliance_footer()` in `build_compliant_email` (`sequence_engine.py:507-531`); Fernet-encrypted token, `/unsubscribe/{token}` (`app/api/unsubscribe.py:54,59`); Gmail adapter only transports (`gmail.py:284-287`), refusal only in `debug.py:269-276`; `BOUNCE_RATE_PAUSE_THRESHOLD` (`app/config.py:113`, `sequence_engine.py:618`); warm-up 10 + 10/day (`sequence_engine.py:165-167`). |
| `FEATURES.md` (D5) | "LinkedIn is not implemented"; GTM phases "run first"; follow-up "if the sequence has no next step" as a general path | LinkedIn channel exists via Unipile, Growth+, not live-verified (`app/integrations/linkedin_channel.py`, `unipile_linkedin.py` TODO markers); strategy runs first then GTM (`app/pipeline/engine.py:37-40`); the no-next-step path only fires for deleted/renumbered steps because the enrollment completes on the last step (`sequence_engine.py:446-451`) and the sweep reads ACTIVE only. |
| `frontend/src/app/contact/page.tsx` (D4) | "LinkedIn is the primary outreach channel"; "Pricing is discussed on the call" | Email is the default channel (`app/api/sequences.py:119`), LinkedIn optional on Growth+ (`app/core/plans.py`); prices published on /pricing (`GET /billing/catalog`). `frontend/src/tests/contactClaims.test.ts` (2, both failed on the base). |
| `docs/program/help-center-discoveries.md` | — | status note: D4–D7 corrected, #25 reset part fixed |

---

## Review round (commit 7b07a8d, changes requested)

Pre-fix = the new/changed test files run against `git archive 7b07a8d`
(scratch tree), unless stated otherwise.

### R1 (H) Plan holds must not freeze campaigns launched before enforcement — founder item

| Change | Where |
|---|---|
| Grandfather line `PLAN_HOLD_EFFECTIVE_AT = 2026-10-12T00:00:00Z`; only enrollments created at/after it are checked | `app/services/plan_holds.py:89`, `applies()` :142 |
| `is_admin` owners exempt | `plan_holds.applies()` :142 |
| Person-approved Reply Copilot answers exempt (origin `reply_copilot`, draft `auto_sent = false`); auto-sent or draft-less ones are checked | `plan_holds._person_approved_copilot_answer()` :132 |
| Send path calls `plan_holds.check(session, owner, message, enrollment)` | `app/workers/outreach_tasks.py:314` |
| Beat sweep `leadpilot.plan_holds.release` every 15 min (:11/:26/:41/:56), queue `default`; releases a lead's plan holds through `send_holds.release` once the owner's current plan covers one again (an upgrade unfreezes the campaign; no billing code touched) | `plan_holds.release_sweep()` :162, `app/workers/plan_hold_tasks.py`, `app/workers/celery_app.py:86,204,468` |
| Per-channel `delivery_rate` no longer counts any send hold as a failure (NULL-safe `send_holds.not_held_clause()`) | `app/api/strategies.py:596`, `app/services/send_holds.py:49` |
| Campaign overview returns `plan_holds: {count, reasons}`; Campaigns page shows "Some messages are on hold" with the reasons | `app/api/strategies.py:669`, `frontend/src/lib/planHolds.ts`, `frontend/src/app/(app)/campaigns/page.tsx:512` |
| Docs | help center 08, 11, 22; `FEATURES.md` Stage 6; plan_holds docstring |

Tests: `tests/test_plan_downgrade_holds.py` (40; 13 new: TestGrandfather 3,
TestExemptions 4, TestReleaseSweep 4, TestCampaignStats 2) and
`frontend/src/tests/planHolds.test.ts` (3). The module's other tests move the
grandfather line to 2000-01-01 with an autouse fixture (they test the check
itself; enrollments are created at wall-clock time); TestGrandfather restores
the real constant and sets `created_at` explicitly, so nothing depends on
today's date.

Pre-fix: collection error (`plan_holds` has no `PLAN_HOLD_EFFECTIVE_AT`); with
a scratch-only `getattr` shim, 12 of the 13 new tests fail (the 13th,
`test_a_real_failure_still_counts`, is a regression guard that also passes on
the base). planHolds.test.ts: module not found.

Note for founders: the line is a code constant; every enrollment created
before 2026-10-12 00:00 UTC keeps sending on its launch-time entitlement for
its whole life.

### R2 (M-H) "Signed out on every device" is now enforced

| Change | Where |
|---|---|
| `users.password_changed_at` (migration 0084, nullable, no backfill) | `app/db/models.py:493`, `alembic/versions/0084_password_reset.py:54` |
| `_sign_out_everywhere()` used by BOTH change-password and reset: stamps `password_changed_at`, revokes every refresh session, revokes every API key | `app/api/auth.py:532`, called :523 and :652 |
| `api_keys.revoke_all_for_user()` | `app/services/api_keys.py:74` |
| `_issued_before_password_change(user, claims)` — separate helper, called on all three `rotate()` paths (legacy no-jti, grace, normal); `rotate()` not refactored | `app/services/auth_sessions.py:151`, calls :185, :205, :226 |
| Same helper refuses ACCESS tokens minted before the change (otherwise a device stays in for up to 15 min) | `app/services/auth.py:206-210` (`get_current_user`) |
| Email, reset page and profile page say API keys are revoked; responses carry `api_keys_revoked` | `app/services/password_reset.py:201,217`, `reset-password/page.tsx`, `profile/page.tsx` |

Whole-second comparison (a JWT `iat` is an integer) so a sign-in right after
a reset works (asserted). Tests: `tests/test_password_reset.py`
TestSignedOutEverywhereIsTrue (9 incl. 2 parametrised) + updated exact-body assertions;
`passwordReset.test.tsx` (2 new assertions). Pre-fix: 7 of the 9 fail (keys
still authenticate after reset/change, no `password_changed_at` (×2), legacy
refresh token → 200, old access token → 200, no helper); the other two —
another account's keys survive, a sign-in right after a reset works — pass on
the base and are guards. The 2 updated exact-body tests also fail (no
`api_keys_revoked`). Frontend: 2 fail.

Coordination: the other branch's `_live_user` check inside `rotate()` will
sit beside these one-line calls; no structural change to `rotate()` here.

### R3 (M-L) Redeem is atomic; issuing is serialised

- `redeem()` spends the link with `UPDATE password_reset_tokens SET used_at =
  now WHERE id = … AND used_at IS NULL` and requires rowcount 1
  (`app/services/password_reset.py:270`); expired/ineligible links are burnt
  by the same claim.
- `issue_token()` first locks the account row, `SELECT users.id … FOR UPDATE`
  (`_lock_account`, :138), so the cooldown check and the insert are one
  serialised step per account.
- Tests: SQLite stale-reader test (`TestAtomicRedeem`, same technique as
  `test_duplicate_send_claim.py`) and PostgreSQL
  `tests/integration/test_password_reset_race_pg.py` (2, real threads + real
  row locks). Pre-fix: SQLite test fails (both redeems succeed); PG: both
  fail — the second redeem/issue does not wait, i.e. the review probe's
  "last commit wins" and "two live links".

### R4 (L) lock_timeout in 0081

`SET LOCAL lock_timeout = '15s'` on PostgreSQL in both directions
(`alembic/versions/0084_password_reset.py:47-53,75`). Test
`test_postgres_lock_wait_is_bounded`; pre-fix fails.

### R5 (L) Reset email limits

- At most `DAILY_EMAIL_LIMIT = 5` reset emails per account per rolling 24 h
  (`password_reset.py:100`, checked in `issue_token`); beyond it the same
  200, no email, nothing burnt, warning logged. Test
  `test_at_most_five_emails_per_address_per_day` — pre-fix fails (7 emails).
- A re-request inside the 60 s cooldown leaves the outstanding link valid.
  This was already the behaviour in 7b07a8d (the cooldown returned before
  burning); now pinned by `test_a_re_request_inside_the_cooldown_keeps_the_first_link_working`
  and `test_the_daily_limit_does_not_kill_the_last_link` (both pass on the
  base — guards, not fixes).

### R6 (L) Contact page and admin health

- Contact FAQ: LinkedIn answer now names exactly the plans with LinkedIn in
  `PLANS` — Growth, Scale, Enterprise and Pay per meeting (legacy Pro not
  named, not sold) (`frontend/src/app/contact/page.tsx:62`); the "4–6 weeks"
  answer replaced by the code-backed warm-up facts (:48); the "4–8 week
  system" and "self-serve tool" not-for-you lines removed/reworded.
  Tests: `tests/test_contact_page_claims.py` (2, derives the plan list from
  `PLANS`; pre-fix 1 fails — Pay per meeting missing) and
  `contactClaims.test.ts` (2 new; pre-fix both fail).
- `GET /health/learning-loop` (admin) returns `{"status": "unknown", "error":
  "check failed"}` and logs the exception (`app/api/health.py:133`). Test
  `test_admin_learning_loop_hides_exception_text`; pre-fix fails (echoed
  `Error 111 connecting to redis-internal…`).

## Out-of-scope discoveries (reported, not fixed)

1. `.env.example:84-86` and `.env.production.example:181` set
   `GMAIL_DAILY_SEND_CAP=500`, `GMAIL_BOUNCE_PAUSE_THRESHOLD`,
   `GMAIL_WARMUP_START_DAILY` — read by nothing; the effective settings are
   `GMAIL_DAILY_CAP` (100), `BOUNCE_RATE_PAUSE_THRESHOLD`,
   `GMAIL_WARMUP_START_SENDS`/`…_DAILY_INCREMENT`. An operator raising the
   documented variable changes nothing (part of F-OPS-03, two settings modules).
   `docs/setup/environment-variables.md:125` lists the dead name too.
2. `docs/compliance.md` GDPR table (rows on `DELETE /leads/{id}`,
   `lead_tombstones`, CSV export "TODO: verify") was not re-verified in this
   pass.
3. ~~Contact page "4–6 weeks" / "self-serve" claims~~ — fixed in the review
   round (R6).
4. ~~`GET /health/learning-loop` returns exception text~~ — fixed (R6).
5. ~~API keys and legacy refresh tokens survive a password change or
   reset~~ — fixed (R2).
6. `tests/test_admin_bootstrap.py:87` docstring still says no reset flow
   exists (test text only; behaviour it tests is unchanged).
7. The web app has no per-message badge for any send hold; plan holds are
   now summarised on the campaign overview (R1), bounce-shield and
   champion-tracker holds still show as failed with their `error` text.

## Runs

### Review round (2026-10-11, after 7b07a8d) — current

Python from `/home/claude/.venv312` (`PATH=/home/claude/.venv312/bin:$PATH`);
frontend with `node_modules` symlinked from `/home/claude/fe-master/frontend`
(removed afterwards). Output files are in the session scratchpad.

| Command (verbatim) | Exit | Result |
|---|---|---|
| `python -m pytest tests -q -p no:cacheprovider --ignore=tests/integration` (once, started when `pgrep -fc '^python -m pytest tests -q'` = 0; output `platform-gaps_full2.txt`) | 0 | **4732 passed, 7 skipped**, 16 warnings, 770 s |
| `TEST_DATABASE_URL=postgresql://leadpilot:leadpilot@localhost:5433/clienthunter_test python -m pytest tests/integration -q -p no:cacheprovider` (output `platform-gaps_integration2.txt`) | 0 | **139 passed**, 201 s (incl. 4 PD-2 + 2 new reset race tests) |
| `python -m pytest <API-key tests> tests/test_password_reset.py tests/test_plan_downgrade_holds.py tests/test_platform_gaps_migrations.py tests/test_health_error_text.py tests/test_contact_page_claims.py tests/test_status_public.py tests/test_account_export.py tests/test_celery_routing.py tests/test_profile.py tests/test_persistent_sessions.py tests/test_email_verification.py tests/test_rate_limit_auth.py tests/test_rate_limit_ordering.py tests/test_account_suspension.py tests/test_bounce_shield.py tests/test_champion_tracker.py tests/test_compliance.py tests/test_whatsapp_guard.py tests/test_linkedin_channel.py tests/test_phone_calls.py tests/test_whatsapp_engine.py tests/test_whatsapp_window.py tests/test_reply_copilot.py tests/test_reply_copilot_review_fixes.py tests/test_followup.py tests/test_sequences.py tests/test_engagement_crm.py tests/test_activation_script.py tests/help_center -q -p no:cacheprovider` | 0 | 1003 passed |
| `npx tsc --noEmit` (frontend) | 0 | clean |
| `npx vitest run` (frontend, full) | 0 | **74 files, 892 tests passed** |
| `NEXT_PUBLIC_API_URL=https://api.example.test npx next lint` | 0 | only pre-existing `<img>` warnings, none in changed files |
| `python -m scripts.help_center.build_index` | 0 | index regenerated (help-center drift tests 88 passed) |

Pre-fix (review round): see R1–R6 above — every fix has at least one test
that fails on `git archive 7b07a8d`.

### First round (7b07a8d) — superseded

| Command | Exit | Result |
|---|---|---|
| full offline suite | 0 | 4701 passed, 7 skipped, 773 s |
| PG integration suite | 0 | 137 passed, 178 s |
| frontend tsc / vitest / lint | 0 / 0 / 0 | vitest 73 files, 886 tests |
| `npx next build` | 1 | not verifiable offline (`next/font` cannot fetch Inter) |
| `python evals/tools/registry_lint.py evals/registry.yaml` | 0 | OK |

First-round pre-fix (base `d43fa43`): reset tests and plan-hold tests failed
to import their modules; reset endpoints 404; a downgraded WhatsApp step was
`sent`; migration tests 14/15 failed; health tests 2/2 failed; frontend
OfflineBanner 4, publicFooter 2, contactClaims 2 failed.

### Pending orchestrator

- `python3 evals/run_evals.py` + `python3 evals/tools/promote.py` (PROMOTE /
  BLOCK) and `python3 evals/fixtures/verify_block_fixtures.py`: not run by
  this builder (one full suite per builder on 2 shared CPUs).
- Commit SHA and CI run URL: pending (the orchestrator amends 7b07a8d).
- Sealing decision for the new guard tests (`tests/test_plan_downgrade_holds.py`,
  `tests/test_password_reset.py`, `tests/integration/test_password_reset_race_pg.py`).

Sealed files: none touched (`git diff -- evals .github` empty).

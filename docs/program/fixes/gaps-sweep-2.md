# Gaps sweep 2 — evidence (2026-10-11)

Branch `claude/gaps-sweep-2`, based on master `be2f9e0` (PR #86). Founder
instruction: "Fix every open gap which you find." Eighteen reported-but-unfixed
gaps were each verified against the code first. Every behaviour fix has a
failing-first test; the pre-fix runs were made against `git archive HEAD` (the
untouched base) extracted into a scratch directory with the new and changed
test files copied in. Commands, counts and exit codes are in **Runs** at the end.

| # | Gap | Verdict | Outcome |
|---|---|---|---|
| 1 | `call_completed` emitted without a webhook payload | confirmed (the only subscribable event with no payload anywhere) | payload added; structural test over every subscribable event |
| 2 | `stop_enrollment` leaves AWAITING_REVIEW messages in the queue | confirmed (+ guard-held messages too) | cancels everything `send_holds.pending_clause()` calls pending; closes the reviews |
| 3 | CRM grid / bulk / deal-stage can close a lead without stopping its sequences | partly: deal-stage webhooks already stopped (`crm_sync.apply_lead_status`); CRM single patch, bulk patch and the Pipeline board (for closed/disqualified) did not; the send path blocked `dropped` only | one helper `sequence_engine.stop_for_status` used by every writer + send-time refusal of sequence steps to closed leads — **safety guard** |
| 4 | `meeting_outcome_*` counted as `other` | confirmed | new authorised category `meeting_outcome` |
| 5 | `still_appropriate` checks suppression on email only | confirmed (+ email match was case-sensitive) | all three identifiers via `lead_tasks.is_suppressed` |
| 6 | Reply Copilot answers thread by Gmail `threadId` only | confirmed; Message-ID was never stored | migration `0086_inbound_reply_threading`; In-Reply-To / References on answers |
| 7 | LinkedIn webhook publishes the reply job before routing | confirmed (+ WhatsApp had the same order) | route first, publish after (in `finally`) — both channels |
| 8 | Held messages shown as plain failures | confirmed (thread said "Email not sent"; review-held said "Email sent") | one helper `send_holds.hold_of`; "On hold: <label>" badge in the conversation thread and Reply Copilot |
| 9 | MultiVariateResults never mounted; `mv-results` ownership never matches on SQLite | confirmed (+ the data query was PostgreSQL-only) | mounted on Analytics; typed ORM ownership and data |
| 10 | `onboardingApi` and `kanban/StrategyPicker.tsx` unused | confirmed dead | deleted; dead-code test extended |
| 11 | Bounce Shield report shows the 3% baseline | confirmed | `compliance_rules.account_bounce_threshold`, shared with the CRM dashboard |
| 12 | Env examples set three settings nothing reads | confirmed | real names in both examples, the doc, the checklist; dead fields removed |
| 13 | Privacy §2 claims page/feature tracking | confirmed (no tracking exists) | §2 rewritten to what is kept — **needs founder/legal review**; GDPR table in `docs/compliance.md` rewritten |
| 14 | Pay-per-meeting disputes have no web UI | confirmed; **no billable-meetings list exists** | not built (instruction: report) — see "Not fixed" |
| 15 | Monthly switch cancels without proration | confirmed | billing unchanged; the Pricing page and article 22 now say it before checkout — proration is a **founder decision** |
| 16 | Stale program docs | confirmed (all five) | corrected; DECISIONS.md D6 row only |
| 17 | Raw exception text in API responses | confirmed in 7 handlers (incl. `/health/learning-loop` `last_error`) | `app/core/errors.public_detail`; structural AST test |
| 18 | `auto_promote_winners` PostgreSQL-only | confirmed | dialect-neutral `promote_winners` (+ `ab_testing` / `multi_variate` queries); runs offline and in the PG suite |

---

## 1. `call_completed` webhook

**Verified.** `phone_calls.analyze` emitted `call_completed` with no
`webhook_payload`; `event_bus.emit` only calls `_webhooks` when the payload is
not None. An AST scan of `app/` (the helper in `tests/test_send_path_gaps.py`)
shows it was the only subscribable event never emitted with a payload.

**Fix.** `app/services/phone_calls.py:389` sends the documented shape
(`webhook_delivery.SAMPLES["call_completed"]`: call_id, lead_id, outcome,
duration_seconds).

**Tests.** `tests/test_phone_calls.py::TestAnalysis::test_call_completed_reaches_a_webhook_subscriber`
(a real delivery row is created); `tests/test_gaps_sweep_2.py::TestSubscribableEventsAreDelivered`
(every `EVENT_DESCRIPTIONS` event has a payload-carrying emit somewhere).
**Pre-fix:** both fail (`never == ['call_completed']`; no delivery).

Not changed: a call that ends in a STOP request returns early and emits no
`call_completed` at all (reported below).

## 2. A stop closes held messages and their reviews

**Verified.** `sequence_engine.stop_enrollment` cancelled `SCHEDULED` and
`SENDING` only. A message in the review queue (AWAITING_REVIEW) or held by a
guard (FAILED + `bounce_shield:` / `champion_tracker:` / `plan_limit:`) stayed;
its `SendReview` stayed `pending`. Nothing was ever sent (approval/release
re-runs the gates), but the queue asked for a decision already made.

**Fix.** `stop_enrollment` (`sequence_engine.py:372`) cancels every message
`send_holds.pending_clause()` calls pending, and `send_review.close_for_cancelled`
(`send_review.py:423`) closes their pending reviews as `rejected`, no reviewer,
note `enrollment stopped: <reason>`. It does not advance the sequence (the
enrollment is stopped). Article 12 says so.

**Tests.** `TestStopClosesHeldMessages` (3; one control). **Pre-fix:** 2 fail
(`FAILED is not CANCELLED`, review still pending); the control passes.

## 3. Closed statuses stop sequences — SAFETY GUARD

**Verified.** `crm_sync.apply_lead_status` (HubSpot/Salesforce deal-stage and
contact webhooks) already stopped enrollments for closed_won/closed_lost/
disqualified — that part of the report was wrong. Not stopping: `PATCH
/crm/leads/{id}` (any status, even `dropped`), `POST /crm/leads/bulk`, and the
Pipeline board `PATCH /leads/{id}` for closed/disqualified (it stopped
`dropped` only). The send chokepoint blocked `dropped` only.

**Fix.**
- `sequence_engine.CLOSED_STATUSES` / `STOPPING_STATUSES` (`:66-68`),
  `status_stop_reason` (`dropped` → `lead_removed`, else `crm_<status>` →
  category `crm_closed`), `stop_live_enrollments` and `stop_for_status`
  (`:619-640`) — the one rule.
- Writers: `app/api/ui_support.py:159`, `app/api/crm.py:371` (single) and
  `:492` (bulk, every moved lead), `crm_sync.py:577` (keeps its
  `crm_<provider>` reason), `meeting_followup._stop_live_enrollments`,
  `phone_calls.analyze` (both delegate to `stop_live_enrollments`).
- Send path `outreach_tasks.py:228-243`: a SEQUENCE STEP (`origin` NULL) to a
  closed lead is cancelled (`blocked_lead_closed` audit, enrollment stopped,
  result `cancelled_lead_closed`). Other origins keep their own gates: a
  Reply Copilot answer to a closed lead is cancelled by
  `reply_copilot.send_time_hold` (`cancelled_lead_status`), and the
  post-meeting follow-up is a Gmail draft, not a Message (review L1 corrected
  an earlier claim here that closed-won leads could still be answered).

**Tests.** `tests/test_closed_lead_guard.py` (11; own file so it can be
sealed). **Pre-fix:** 10 fail; the control (opportunity move keeps the
sequence) passes. **Needs sealing decision** (orchestrator): it guards a send.

## 4. `meeting_outcome` stop category

`sequence_completion` gains `MEETING_OUTCOME = "meeting_outcome"` (authorised,
label "Meeting outcome logged", prefix `meeting_outcome_`); the frontend type
and `docs/features/sequence-completion.md` list it. **Tests:**
`TestMeetingOutcomeStopCategory` (7). **Pre-fix:** all fail (`other`).

## 5. Re-engagement plans honour phone and LinkedIn suppression

`reengagement_memory.still_appropriate` (`:416-430`) now uses
`lead_tasks.is_suppressed` per identifier (email keeps its row's reason; phone
→ `suppressed (phone number)`; LinkedIn → `suppressed (LinkedIn profile)`).
The email lookup is now case-insensitive like the send path's (it compared
the raw address). **Tests:** `TestReengagementSuppression` (4). **Pre-fix:** 3
fail — phone, LinkedIn, and a mixed-case email; the unsuppressed control passes.

## 6. Reply threading headers (migration 0086)

**Verified.** `InboundReply` had no Message-ID; the Gmail adapter dropped it;
answers carried `threadId` only.

**Fix.** `app/services/email_threading.py` (new: sanitise msg-ids — printable
ASCII in angle brackets only, so no CR/LF header injection; bound the chain to
20; RFC 5322 3.6.4 `reply_headers`). `GmailChannel._parse_inbound` captures
`Message-ID` and `References` (falls back to `In-Reply-To`);
`InboundMessage.rfc_message_id/rfc_references`; `InboundReply` columns
(`models.py:1773`), stored by `outreach_tasks._route_inbound`; migration
`alembic/versions/0086_inbound_reply_threading.py` (additive, nullable, no
backfill, `lock_timeout` 15 s on PostgreSQL, lossless-except-the-new-data
downgrade); `TARGET_REVISION` bumped; `reply_copilot.thread_headers`
(`:1230`) merged into the answer's headers (`outreach_tasks.py:1023`) after
the compliance headers; erased by the lead GDPR delete (`LEAD_SCRUB`).
Replies stored before 0086 keep threading by `threadId` only.

**Tests.** `TestEmailThreading` (7), `TestThreadingMigration` (3),
`tests/test_reply_threading.py` (2; kept out of the sealed
`test_reply_copilot.py`, whose fixtures it imports). **Pre-fix:** all fail
except the control (no module, no columns, no migration file).
`tests/test_platform_gaps_migrations.py::test_activation_script_targets_the_new_head`
pinned `0085`; changed to `0086` because the head legitimately moved.

## 7. Inbound ordering (LinkedIn and WhatsApp)

`app/api/linkedin.py` and `app/api/webhooks_whatsapp.py` now route (which
sets and commits `classification`) and publish `reply_tasks.enqueue` after, in
a `finally` so a routing error does not also leave the reply unclassified.
WhatsApp had the identical race (`reply_intent`, `reengagement_memory` and
Reply Copilot all branch on `classification`), so it was fixed in the same
change; the routing body moved to `_route_whatsapp_reply` unchanged.
**Tests:** two in `test_linkedin_channel.py::TestWebhook`, two in
`TestWhatsAppInboundOrdering`. **Pre-fix:** the job saw `None` (3 fail); the
routing-failure test passes on the base (it guards the `finally`).

## 8. "On hold" instead of "not sent"

`send_holds.hold_of(status, error)` (`send_holds.py:60`) is the one place that
turns a stored message into `{kind, label, reason}`: FAILED + guard prefix,
SCHEDULED + `daily_send_approval: ` (constant asserted equal to the service's),
or AWAITING_REVIEW. Exposed as `hold` on conversation-thread items
(`conversation_thread.py`, `ThreadItem` schema) and on Reply Copilot
`delivery`. Frontend: `itemTitle` says "<Channel> on hold", a warning badge
"On hold: <label>" with the reason (`ConversationThread.tsx`), and
`deliveryLabel` says "on hold: <label> — <reason>". **Tests:** `TestHoldBadge`
(3), `conversation.test.ts` (2), `replyCopilot.test.ts` (1). **Pre-fix:** all
fail. Other message lists: the campaign stats already exclude holds; the
Champion page lists held messages by design.

## 9. Multi-variate results

`app/api/strategies_advanced.py`: `strategy_id` is a `uuid.UUID`; ownership
and the variant list are typed ORM (the raw `text()` bound the dashed string,
which never equals SQLite's 32-hex storage, so every owner got 404 offline);
the data query (`multi_variate._fetch_variant_data`) used `COUNT(*) FILTER`
and `= ANY(:list)` and silently returned zeros on SQLite — now
`ab_testing.variant_counts` (portable `SUM(CASE ...)`). Same fix for
`/personalization-stats` ownership. `MultiVariateResults` is mounted on
**Analytics** (under the variant comparison, where A/B results show); the plan
gate is the endpoint's 402, which the card turns into "Multi-variate test
results are included from the Growth plan." (`lib/multiVariate.ts`; 402/404
are not retried). Articles 17, 22, 29 updated (29 also claimed every A/B plan
got multi-variate results and that history limits were not enforced — both
false). **Tests:** `TestMultiVariateResults` (4; 404 and 402 controls),
`multiVariate.test.ts` (3). **Pre-fix:** owner 404; module missing.

## 10. Dead frontend code

Proved dead before deleting: no importer of `@/lib/api/onboarding`,
`onboardingApi`, `StrategyPicker` or `components/kanban/` in `frontend/`
(src, tests, integration-pending, configs), no dynamic `import()`, no string
form, no barrel file (`lib/api/` has no index), nothing in `sdk/`, `android`
or docs except the defect records. Deleted `frontend/src/lib/api/onboarding.ts`
and `frontend/src/components/kanban/StrategyPicker.tsx` (the directory is now
empty). The backend `/onboarding/state` and `/complete-step` routes stay (API
surface; not dead code by this proof). `tests/test_dead_code_false_text.py`
asserts both are gone and never referenced. **Pre-fix:** 2 fail.

## 11. Bounce Shield report threshold

`compliance_rules.account_bounce_threshold(session, user_id)` resolves the
account's workspace rule (region/channel ANY, never above the baseline);
`bounce_shield.metrics` and `crm_service` (CRM dashboard) both use it.
Article 29 updated. **Tests:** `TestBounceReportThreshold` (2; the
other-workspace control passes on the base). **Pre-fix:** 0.03 reported under
a 0.015 rule.

## 12. Sending-limit variable names

`.env.example`, `.env.production.example`: `GMAIL_DAILY_CAP`,
`GMAIL_WARMUP_START_SENDS`, `GMAIL_WARMUP_DAILY_INCREMENT`,
`BOUNCE_RATE_PAUSE_THRESHOLD`, `BOUNCE_MIN_SENDS` (all `app/config.py`).
The three dead fields were removed from `app/core/config.py` (`extra="ignore"`
keeps an old `.env` loading). `docs/setup/environment-variables.md`,
`docs/compliance.md` and `LAUNCH_CHECKLIST.md` §4 corrected (the task named
`docs/environment-variables.md`; the file is `docs/setup/...`). **Tests:**
`TestSendingLimitEnvNames` (3). **Pre-fix:** all fail.

## 13. Privacy §2 and the GDPR table — NEEDS FOUNDER/LEGAL REVIEW

No page or feature tracking exists. §2 of `frontend/src/app/privacy/page.tsx`
now lists what is kept: per-session IP and user agent (`auth_sessions`), the
security log, the sign-up/sign-in IP country/VPN check (`network_guard`), AI
usage (`usage_meter`), tutorial progress, the push token, and host request
logs (uvicorn's default access log: time, IP, path). `docs/PRIVACY_POLICY.md`
kept in step. Relied on: GDPR Art. 13(1) (tell the data subject what is
collected) — a reading, not settled law; marked for founder/legal review in
both files. `websiteClaims.test.ts` bans the old phrase (pre-fix: fails).
`docs/compliance.md` GDPR table rewritten against the code (it named
`first_name`/`last_name`/`raw_data`, `deleted_at`, a `lead_tombstones` table,
`lead_service.source_leads()` and a `?format=csv` export — none exist).

## 15. Plan switch wording (billing unchanged)

`billing.handle_checkout_completed` cancels the replaced subscription with
`DELETE /v1/subscriptions/{id}` and no proration parameters. The Pricing page
now shows `planSwitchNotice` above the plans for a live monthly/annual
subscription or trial ("… cancels it as soon as the new checkout is completed.
The unused part of the period you already paid for is not refunded or
credited …"); article 22 says the same. **Founder decision needed:** whether
to offer proration. **Unverified:** that Stripe issues no automatic credit for
this call in the live account. **Tests:** `pricing.test.ts` (3; pre-fix fail).

## 16. Stale program records

- `docs/program/DECISIONS.md` D6 row only: resolved 2026-10-11 by the
  `/status` page on the main site.
- `docs/program/PROGRESS.md` (D1/D6 "unanswered" annotated as superseded),
  `docs/program/status.json` (D1, D6, phase blockers), `docs/program/STATUS_PAGE.md`
  (D6 references → the optional Part B steps).
- `docs/program/help-center-factcheck.md` #52 ("no cancel button"):
  superseded — the Profile Plan card cancels.
- `tests/test_admin_bootstrap.py` docstring no longer says there is no reset flow.
- `LAUNCH_CHECKLIST.md` §9 (GAP-112): PlanCard is on Profile, not Settings;
  MultiVariateResults is on Analytics; SendTimeCard, SubjectLineCard and
  PersonalizationHealth are mounted nowhere (reported below).

## 17. Raw exception text

`app/core/errors.public_detail(exc, generic, event=...)` logs the exception
and returns its text only for the application's own `ClientHunterError`s
(sentences written for the user, e.g. "scope not granted"); anything else
returns the generic phrase. Applied: `ai_intelligence` mutate, `calls`
call-now (and the provider's `result.error` is no longer echoed — it stays on
the call record), `linkedin` account lookup, `meetings` platform link,
`personalization` style profile and Loom script; `/health/learning-loop`
returns "the last run failed" instead of the worker's stored exception text;
`sequences.py` WhatsApp mapping validation narrowed from `except Exception` to
the input errors it means. Triage of the other `str(exc)` sites in `app/api`:
all catch the application's own domain errors (ValueError subclasses and
named service errors written for users) or Slack/PostIQ/Meta API error codes —
left as they are. **Tests:** `TestNoRawExceptionText` (5; AST scan + 3
behaviour + 1 control). **Pre-fix:** all fail (the control too: the base
prefixed the class name, "GoogleCalendarNotAuthorized: scope not granted").

## 18. Promotion sweep, dialect-neutral

`learning_tasks.promote_winners` (`:192`) replaces the raw PostgreSQL SQL
(`array_agg`, `gen_random_uuid()`, `NOW()`, `ON CONFLICT`, dashed strings in
`text()`): ORM aggregation, the same candidate rule, the permanent
`ab_promoted` marker check, and the marker insert in a SAVEPOINT that
swallows the 0012 partial-unique-index conflict (the old `ON CONFLICT DO
NOTHING`). `ab_testing._load_variant_stats` uses the same portable
`variant_counts`. **Tests:** `TestPromotionSweep` (3, incl. the Celery task
end-to-end with the flag on), plus the existing PG integration tests
(`test_flows.py` promotion, `test_idempotency.py` double run) that run it on
PostgreSQL. **Pre-fix:** fail (no `promote_winners`; on the base the task's SQL
cannot run on SQLite).

---

## Not fixed (and why)

- **#14 dispute action:** the web app has no billable-meetings list
  (`billingApi.meetings` and `billingApi.dispute` have no caller; nothing
  renders `BillableMeetingRow`). Per the instruction this is reported, not
  built. Article 22 already says disputes go through the API.
- **#15 proration:** a founder decision; only the wording changed.
- **#13 legal text:** changed to match the code, but needs founder/legal review.

## Out of scope: reported, not fixed

- `components/settings/PlanCard.tsx` is imported only by the parked
  `frontend/integration-pending/` page; `PersonalizationHealth`,
  `SendTimeCard` and `SubjectLineCard` are rendered by no page (the send-time
  cards belong to the autopilot/send-time branch).
- A call that ends with a STOP request returns before emitting
  `call_completed`, so that call never reaches a `call_completed` webhook.
- Service-level raw exception text that reaches users through API results:
  `crm_sync.py:857`, `guardrails.py:831` (CRM provider error text in sync
  results), `pipeline_health.py:229`, `signal_radar.py:366`,
  `meeting_ai.py:202`, `deliverability_autopilot.py:532`. Not in `app/api`, so
  outside item 17's scope.
- `personalization_scorer.score_strategy_messages` is raw SQL with a dashed
  UUID string — on SQLite `/personalization-stats` now passes ownership but
  always reports no data.
- Analytics page reads `counts.meeting_booked` from the variants map, but
  `app/api/analytics.py:107` keys it by `event.value`, which is `booked`, so
  the "Booked" column of the variant comparison always shows 0 (read from the
  code; not observed in a browser).
- LinkedIn network messages held by daily approval are not covered by the
  hold badge (separate table, separate page).

## Review round (independent review of d5da447, 2026-10-12)

Pre-fix column: the new tests run on `git archive d5da447` with only the new
test files and the test helper module `mime_policy.py` (then in
`app/integrations/`, now `app/core/`) copied in (`gs2_review_prefix.txt`: **20 failed, 57 passed** — the 57 are the
earlier rounds' tests, controls, and regression guards marked below).

| # | Finding | Fix (file:line) | Test | Pre-fix on d5da447 |
|---|---|---|---|---|
| R1 HIGH, pre-existing | `build_mime` used the default email policy (78-char lines): the ~230-char `List-Unsubscribe` went out RFC 2047 encoded and folded on every Gmail send; the F03 preflight checked the DECODED header and passed | `app/core/mime_policy.py` (new: `OUTBOUND_POLICY = email.policy.default.clone(max_line_length=998)`, `raw_header_lines`, `raw_header_value`); used at `gmail.py:253` (build_mime), `gmail.py:429` (Gmail drafts), `email_sender.py:133` (SMTP system mail) — every outbound `EmailMessage(`; preflight `deliverability_autopilot.py:318-330` now fails on `=?` or folding in the RAW bytes of either header | `tests/test_unsubscribe_headers_raw.py` (11; own file so it can be **sealed**): raw bytes carry the real ≥228-char `List-Unsubscribe` intact and the exact `List-Unsubscribe-Post`; the bytes the Gmail channel POSTs; a synthetic 236-char URI; the preflight fails on a default-policy builder; drafts; SMTP | 7 fail (`=?utf-8?q?=3Chttps...` in the raw header; preflight passes the encoded header); controls pass: token length, non-ASCII Subject still encoded, the real send path passes the preflight |
| R2 (M1) | Same root cause for long Message-IDs | same policy | `TestThreadingHeadersRaw::test_a_long_m365_message_id_is_transmitted_raw` (83-char M365 id, In-Reply-To and References asserted on raw bytes) | fails (encoded) |
| R3 (M2) | `stop_live_enrollments` rewrote COMPLETED enrollments as STOPPED (and the older loops it replaced did too) | `sequence_engine.py:630-654`: stops ACTIVE/PAUSED only; for COMPLETED, cancels pending messages (`_cancel_pending`, `:402`) without touching the status. Callers checked: `crm_sync.apply_lead_status`, `meeting_followup._stop_live_enrollments`, `phone_calls.analyze`, `ui_support.patch_lead`, CRM single/bulk patch, GDPR erase, and the send-path closed-lead check (`outreach_tasks.py:243`, now ACTIVE/PAUSED only) | `TestCompletedEnrollmentsKeepTheirStatus` (5; reviewer probe 1 ported: CRM close, meeting outcome, crm_sync, helper) | 4 fail (`STOPPED`); the active/paused control passes |
| R4 (L1) | Comments said closed-won leads can still be answered by Reply Copilot | `outreach_tasks.py:228-236`, `recipient_guards.py:8-13`, this doc §3: `send_time_hold` cancels them (`cancelled_lead_status`) | `tests/test_reply_threading.py::TestClosedLeadAnswers` (reviewer probe 2 ported) | passes (pins the true behaviour the comments now describe) |
| R5 (L2/L3) | `public_detail` passed every `ClientHunterError` through, including ones wrapping provider text; Zoom put its response body in the message; meeting follow-up and network messages put provider text in user-facing errors; network errors echoed `httpx` text | `ClientHunterError.user_safe` (`core/exceptions.py:20`), `False` on `StripeError`, `EmailSendError`, `SmsSendError`; `public_detail` honours it (`core/errors.py:129`); `zoom.py:130-138` (body logged, not in the message); `meeting_followup.py:465-469`; `network_messages.py:169-172`; `postiq.py:114`, `signalforge.py:76`, `aegisaudit.py:142` (exception type only, detail logged). Callers of Stripe/Email/SMS errors were checked: they already map to fixed text (`billing.py:371`, `auth.py:216/587`, `phone_verification.py:154`) | `TestProviderTextNeverPassesThrough` (4): public_detail refuses the three; Zoom message; follow-up message; AST scan of `app/services` + `app/integrations` for `raise X(f"...{exc}")` inside except handlers (allow-list with reasons in the test) | all 4 fail |
| R6 (L4) | CRM bulk patch committed statuses, then stopped each lead's sequences commit by commit | `stop_enrollment` / `stop_live_enrollments` / `stop_for_status` take `commit=False`; `crm.py:371` (single), `crm.py:489-496` (bulk), `ui_support.py:158` stop in the same transaction as the status change | `TestBulkCloseIsAtomic` (a failure on the second lead leaves both leads and enrollments unchanged) | fails (first lead already closed) |
| R7 (L5) | GDPR lead erase set DROPPED but left enrollments ACTIVE | `leads.py:419-426` `stop_for_status(..., commit=False)` before the erase commit; docstring and `docs/compliance.md` say so | `TestGdprEraseStopsSequences` | fails (ACTIVE) |
| R8 (L6) | System-closed reviews looked like human rejections | `send_review.py:428-447`: note `closed by system: <reason>` (`SYSTEM_CLOSED_PREFIX`), `closed_by_system()` and `review_out["closed_by_system"]`; queue shows "Closed by the system (the sequence stopped)" (`lib/sendReview.ts` `decisionLabel`, `ReviewQueuePanel.tsx`); article 12. Kept as status `rejected` (no new status value: filters, types and stored vocabulary unchanged) | `TestStopClosesHeldMessages::test_a_review_held...` (now asserts the marker), `sendReview.test.ts` (1) | fails (no prefix / key) |
| R9 (L7) | The narrowed except in `sequences.py` echoed TypeError/AttributeError text | `sequences.py:233-251`: `TemplateError` (the validator's own sentence) echoed; any other error logged with a generic 422 | `TestSequenceMappingErrors` (2; validator-sentence control) | fails (`invalid literal for int()` in the 422) |
| R10 (L8) | Missing tests | — | `TestStopLeavesOthersAlone`: a held message on ANOTHER sequence is untouched; an APPROVED review stays approved (its message still cancels); WhatsApp routing failure still publishes the reply job | held-elsewhere and WhatsApp tests pass on d5da447 (regression guards); approved-review test fails only on the new `closed_by_system` key |
| R11 (M3) | Seal `tests/test_closed_lead_guard.py` | orchestrator, gate PR | — | — |
| probe 3 | promotion conflict path | unchanged (already correct) | `TestPromotionConflictPath` (ported) | passes (guard) |

## Existing tests changed (contract changed, not weakened)

- `tests/test_platform_gaps_migrations.py::test_activation_script_targets_the_new_head`:
  pinned `0085_webhook_foreign_keys`; the head is now `0086_inbound_reply_threading`.
- `tests/test_reply_intelligence.py::TestDispatch` (two source scans): they
  looked for the literal `reply_tasks.enqueue(reply.id)` / `(reply_row.id)`;
  the webhooks now publish `reply_tasks.enqueue(reply_id)` (id read before
  routing, published after it in a `finally`). Same assertion, new literal;
  the behaviour is now tested directly (items 7).
- `tests/test_dead_code_false_text.py`: two more deleted modules asserted.
- `tests/test_admin_bootstrap.py`: docstring only.
- Added to (not changed): `tests/test_phone_calls.py`, `tests/test_linkedin_channel.py`.
- No sealed file was edited (`evals/compliance_testset.yaml` lists 24; none
  is in this diff). The threading tests that first went into the sealed
  `tests/test_reply_copilot.py` were moved to `tests/test_reply_threading.py`.

## Runs

All Python with `PATH=/home/claude/.venv312/bin:$PATH`, `-p no:cacheprovider`.

| Command | Exit | Result |
|---|---|---|
| Base tree (`git archive be2f9e0`) + new/changed tests: `pytest tests/test_gaps_sweep_2.py tests/test_closed_lead_guard.py <new tests in test_phone_calls / test_linkedin_channel> tests/test_dead_code_false_text.py <platform-gaps head pin>` | 1 | **57 failed, 10 passed** — every behaviour test fails; the 10 passes are the controls listed per item (plus the LinkedIn routing-failure guard and the mv-results 404/402 controls) |
| Base tree: `pytest tests/test_reply_threading.py` | 1 | 1 failed, 1 passed (the control) |
| Base tree frontend: `npx vitest run conversation replyCopilot pricing multiVariate websiteClaims` | 1 | 7 failed, 42 passed; `multiVariate.test.ts` fails to load (module missing) |
| `pytest $(tests/*migration*.py) tests/test_account_erasure.py tests/test_account_export.py tests/test_activation_script.py tests/test_gdpr_erasure_scores.py tests/test_docs_migration_claims.py` | 0 | 635 passed, 482 s |
| `pytest` on 35 related files (send review, send path, sequences, CRM, Reply Copilot, LinkedIn, WhatsApp, meetings, health, bounce shield, champion tracker, daily approval, …) + the new files | 0 | 1101 passed, 209 s |
| `pytest tests/help_center` | 0 | 88 passed |
| `TEST_DATABASE_URL=postgresql://leadpilot:leadpilot@localhost:5433/clienthunter_test_gs2 pytest tests/integration` (own database: another builder was using `clienthunter_test`; created with `createdb -O leadpilot`, dropped after) | 0 | **142 passed**, 370 s (alembic upgrade head through 0086 on PostgreSQL 16; promotion flow + idempotency tests run `promote_winners` on PostgreSQL) |
| `pytest tests -q --ignore=tests/integration` (full offline suite, once, started with 1 other suite running) | 1 | **5217 passed, 2 failed, 7 skipped**, 833 s — the two `TestDispatch` source scans above |
| after updating those two literals: `pytest tests/test_reply_intelligence.py tests/test_reply_threading.py` | 0 | 35 passed |
| `npx tsc --noEmit` (frontend) | 0 | clean |
| `npx vitest run` (frontend, all) | 0 | 88 files, 1032 tests passed |

### Review round runs

| Command | Exit | Result |
|---|---|---|
| d5da447 tree (`git archive d5da447`) + new test files + the helper module: `pytest tests/test_unsubscribe_headers_raw.py tests/test_gaps_sweep_2.py tests/test_reply_threading.py` | 1 | **20 failed, 57 passed** (pre-fix column above) |
| d5da447 frontend: `npx vitest run src/tests/sendReview.test.ts` | 1 | 1 failed (`decisionLabel`), 18 passed |
| `pytest` on 37 related files (billing, compliance, CRM, email verification, password reset, GDPR, leads, LinkedIn network, meetings, network messages, phone, reply intelligence, send review, sequences, tool integrations, WhatsApp, deliverability autopilot, send path, Reply Copilot, champion tracker, account erasure, the new files) | 0 | 1330 passed, 208 s |
| `pytest tests/test_meeting_platforms.py tests/test_meeting_platforms_live.py` | 0 | 16 passed, 2 skipped |
| PG: `TEST_DATABASE_URL=postgresql://leadpilot:leadpilot@localhost:5433/clienthunter_test_gs2r pytest tests/integration` (own DB, dropped after) | 0 | **142 passed**, 196 s |
| `npx tsc --noEmit` / `npx vitest run` (frontend, all) | 0 / 0 | clean / 88 files, 1033 tests |
| Full offline suite `pytest tests -q --ignore=tests/integration` (once, no other suite running) | 1 | **5246 passed, 1 failed, 7 skipped**, 796 s — `test_privacy_docs_truth::test_every_integration_module_is_a_named_processor_or_excluded`: the new helper was in `app/integrations/`, where every module must be a named data processor. Moved to `app/core/mime_policy.py` (it is a helper, not an integration); the test was not changed |
| after the move: `pytest tests/test_privacy_docs_truth.py tests/test_unsubscribe_headers_raw.py tests/test_deliverability_autopilot.py tests/test_email_verification.py tests/test_password_reset.py tests/test_reply_threading.py tests/test_gaps_sweep_2.py tests/test_meeting_prep.py` | 0 | 309 passed |

Safety guards to seal (orchestrator): `tests/test_closed_lead_guard.py` (M3)
and `tests/test_unsubscribe_headers_raw.py` (R1).

Not run here (orchestrator, per the brief): `evals/run_evals.py`,
`evals/tools/promote.py`, `evals/fixtures/verify_block_fixtures.py`, commit SHA
and CI run URL — the evidence package is NOT VERIFIED until those are recorded.

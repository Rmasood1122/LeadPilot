# PROGRESS — overnight build (started 2026-09-16)

Branch: `feature/8-new-features`. Never merged to `master`, never force-pushed.

## How to read this
Each feature below moves through: **migration → service → API → frontend → tests → docs → commit**.
"Done" means all seven, with the relevant test suites green.

---

## Scope

**Part 1 — 12 differentiation features**

| # | Feature | Status |
|---|---------|--------|
| 1 | Positive Reply Classifier | **done** (0053) |
| 2 | F-P-T-A Scoring Engine | **done** (0054) |
| 3 | Sequence Completion Guarantee + metric | **done** (0055) |
| 4 | Deliverability Health Score (per mailbox) | **done** (0056) |
| 5 | Human Review Queue for high-risk sends | **done** (0057) |
| 6 | Unified Cross-Channel Inbox | **done** (0058) |
| 7 | Re-engagement Memory ("not now" ≠ "never") | **done** (0059) |
| 8 | Transparent Attribution Ledger | not started |
| 9 | Compliance & Consent Layer | not started |
| 10 | Data Provenance Tags | not started |
| 11 | Founder/Agency Mode (multi-client workspaces) | not started |
| 12 | "Why This Prospect" Explainability Panel | **done** (built on #2, no storage of its own) |

**Part 2 — Meeting Prep & Training module**

| # | Piece | Status |
|---|-------|--------|
| P2.1 | Auto-generated meeting brief + script | not started |
| P2.2 | Mock interview / roleplay mode + feedback | not started |
| P2.3 | Standalone practice + pre-meeting checklist | not started |

---

## Baseline survey (what already existed on 2026-09-16)

Read before writing anything, so nothing gets rebuilt that is already there:

- **Replies** — `InboundReply` already carries `classification` (routing: unsubscribe /
  bounce / out-of-office), `reply_category` (BUYING_SIGNAL | OBJECTION | NOT_NOW |
  WRONG_PERSON, feature 0034) and `authenticity_kind` (0043). None of these is the
  5-way interested/neutral/objection/not-now/unsubscribe taxonomy feature 1 asks for,
  and no "positive reply rate" metric exists. → new, additive column set.
- **Scoring** — `lead_scoring.py` produces `ai_booking_likelihood` (a single 0-100
  booking-likelihood number). No F-P-T-A decomposition. → new service, new columns.
- **Sequences** — `sequence_engine.py` already hard-stops only on explicit conditions,
  but there is no record of *planned* step count, no completion timestamp, and no
  completion-rate metric. → columns + metric.
- **Deliverability** — `deliverability.py` scores per *domain* per user (SPF/DKIM/DMARC
  + blacklist + bounce rate). Nothing per *mailbox*, no spam-complaint rate, no
  auto-throttle. → new per-mailbox table + scheduled refresh + send-path throttle.
- **Reviews** — `SequenceReview` (0047) reviews sequence *content* before launch. There
  is no per-*message* human approval queue. → new table.
- **Conversation** — `conversation_thread.py` builds one lead's cross-channel thread.
  There is no cross-*prospect* inbox list. → new endpoint + page on top of it.
- **Re-engagement** — `ReengagementAttempt` (0048) exists for post-sequence touches;
  `InboundReply.reschedule_date` exists but nothing auto-schedules from a "not now".
- **Compliance** — `compliance_region.py`, `compliance_audit.py`, `ComplianceAuditLog`
  and `SuppressionEntry` exist. Suppression is email/phone only (no LinkedIn/WhatsApp
  in the same act) and there is no consent-event ledger.
- **Workspaces** — `workspaces.py` has members/roles/branding/domain verification.
  No per-workspace sending-domain pool, reporting scope or billing view.
- **Meeting prep** — `MeetingPrepBrief` (FG7) generates a brief. No script structure,
  no objection list, no roleplay.

---

## Decisions log

(Appended as decisions are made — each entry says *why*, so the choice can be argued
with later.)

- **2026-09-16 — Additive-only migrations.** Every new column is nullable or has a
  server default, and every new table is standalone. Rationale: this branch will be
  merged into a database that already has production rows; a NOT NULL column with no
  default cannot be added to a live table without a rewrite, and the repo's existing
  migrations (0024–0052) all follow this rule.
- **2026-09-16 — New columns instead of overloading existing ones.** Feature 1's
  5-way intent taxonomy gets its own columns rather than widening `reply_category`,
  because `reply_category` already drives the FG1 reply-intelligence UI and drafts;
  changing its value set would silently break that feature's consumers.

---

## Log

- **2026-09-16 -- Feature 7 done.** Migration `0059_reengagement_memory` (new
  `reengagement_plans` table), `app/services/reengagement_memory.py`, a hook in
  `reply_tasks.process_inbound_reply` right after the intent label is decided,
  a daily 05:50 sweep, four new endpoints under `/reengagement/plans` and
  `/leads/{id}/reengagement-plans`, three `system_settings` keys, and a
  `ReengagementMemoryPanel` on the lead page. Tests:
  `tests/test_reengagement_memory.py` (51),
  `tests/test_reengagement_memory_migration.py` (7),
  `frontend/src/tests/reengagementMemory.test.ts` (17). Regression: 172 tests
  across the reply/CRM suites still green; `tsc --noEmit` clean. Decisions: a
  NEW table rather than `reengagement_attempts` (0048), because that row is a
  once-per-enrollment CLAIM designed to be consumed and forgotten while this
  one outlives its enrollment and carries the prospect's words; the reason is
  stored twice (a `kind` to group by, the TEXT to quote) because a hook built
  on their sentence survives being read back nine months later; the interval
  varies BY REASON (a contract renews on a different clock from a busy month)
  and a date the prospect named always wins; appropriateness is re-checked
  when the plan comes DUE, not when it was made; `auto_send` defaults OFF
  because most people want to read a nine-month-old promise before acting on
  it, and when on the touch is an ORDINARY message so suppression, compliance,
  mailbox health and the review queue all still apply. Docs:
  `docs/features/reengagement-memory.md`.
  **Also fixed a real bug I introduced in Features 5 and 6:**
  `frontend/src/lib/api/{sendReview,inbox}.ts` passed
  `body: JSON.stringify(...)`, but `api()` stringifies `body` itself -- the
  exact double-stringify bug documented at the bottom of `client.ts`, which
  would have sent a JSON *string* and got a 422 from FastAPI on every
  approve/reject/handled call. Both fixed, and
  `frontend/src/tests/apiWriteBodies.test.ts` (8) now guards every new write
  helper against it.

- **2026-09-16 -- Feature 6 done.** Migration `0058_inbox_handling`
  (`handled_at`, `handled_by_user_id` on `inbound_replies`),
  `app/services/inbox.py`, `app/api/inbox.py`, a new `/inbox` page threaded by
  prospect with the existing `ConversationThread` as the detail pane, and an
  Inbox entry second in the main nav. Tests: `tests/test_inbox.py` (34),
  `tests/test_inbox_migration.py` (5), `frontend/src/tests/inbox.test.ts` (18).
  `tsc --noEmit` clean. Decisions: `thread_detail` reuses
  `conversation_thread.build_thread` rather than re-merging the tables, so the
  lead page and the inbox can never disagree about a prospect's history;
  "handled" is a STORED flag because the two commonest ways a reply gets dealt
  with (answered from Gmail, or needs no answer) leave no outbound row, and
  inferring it from a later send would clear the thread the moment the next
  sequence step went out; it is per REPLY because a prospect who writes twice
  has two things to answer; `needs_reply` is ordered OLDEST first; the badge
  counts threads, not messages. Also fixed a latent bug in the migration-test
  helper: stripping a column from the pre-migration schema has to strip its
  foreign key too, or the prereq CREATE TABLE references a column that is not
  there. Docs: `docs/features/unified-inbox.md`.

- **2026-09-16 — Feature 5 done.** Migration `0057_send_reviews` (new
  `send_reviews` table; `MessageStatus.AWAITING_REVIEW` needed no column
  change because that enum is VARCHAR-backed),
  `app/services/send_review.py`, the gate inside
  `outreach_tasks.send_message_impl` after rendering,
  `app/api/send_reviews.py`, five new `system_settings` keys, and a new
  "Review" tab on the Campaigns page. Tests:
  `tests/test_send_review.py` (55), `tests/test_send_reviews_migration.py`
  (6), `frontend/src/tests/sendReview.test.ts` (18). Regression: 139 tests
  across engine/CRM/LinkedIn/phone suites still green; `tsc --noEmit` clean.
  Decisions: the approved SNAPSHOT is authoritative -- an approved review
  sends the words the reviewer read, discarding the next render, because
  rendering is a model call that never repeats itself and comparing would
  re-queue the message forever; rejecting cancels the MESSAGE but leaves the
  ENROLLMENT running, since one badly-timed email should not end the
  relationship; the gate fails OPEN, because a broken review system must not
  silently stop outreach; `tone_flag` reuses
  `adversarial_review._text_findings` verbatim so the pre-launch gate and this
  one cannot disagree. Docs: `docs/features/send-review-queue.md`.
  **Needs a decision from Rehan** -- see Known issues.

- **2026-09-16 — Feature 4 done.** Migration `0056_mailbox_health` (new
  `mailbox_health` table, one upserted row per mailbox),
  `app/services/mailbox_health.py`, a four-hourly Celery beat sweep
  (`refresh_mailbox_health`), the send gate in
  `outreach_tasks.send_message_impl` (paused -> defer, throttled -> lower cap),
  `/deliverability/mailboxes[/refresh]` and `.../{ref}/resume`, and
  `MailboxHealthCard` above the existing per-domain card in Settings ->
  Deliverability. Tests: `tests/test_mailbox_health.py` (50),
  `tests/test_mailbox_health_migration.py` (5),
  `frontend/src/tests/mailboxHealth.test.ts` (19). Regression: 58 tests across
  trust/sequences/celery-routing still green; `tsc --noEmit` clean.
  Decisions: a NEW table rather than more rows in `deliverability_checks`,
  because that log is per DOMAIN and per domain is the wrong grain to throttle
  on; `mailbox_ref` mirrors `messages.sender_ref` exactly so volume and
  complaints are countable per mailbox; the deduction weights are sized so a
  fully unauthenticated but quiet mailbox THROTTLES (45) while real recipient
  harm PAUSES (a complaint or bounce rate past the danger line costs 65 on its
  own); a pause DEFERS messages, never cancels them; resuming is a human
  decision only, matching the bounce and blacklist pauses.
  **Known limitation worth Rehan's attention:** there is no feedback-loop /
  Postmaster Tools integration, so `complaint_rate` is a documented PROXY
  (unsubscribes + "stop" replies over sends). It is labelled `proxy` in every
  payload and in the UI. Connecting a real FBL later changes only that number
  and the label. Docs: `docs/features/mailbox-health.md`.

- **2026-09-16 — Feature 3 done.** Migration `0055_sequence_completion`
  (`planned_steps`, `steps_sent`, `completed_at`, `stopped_at`,
  `stop_category` on `sequence_enrollments`),
  `app/services/sequence_completion.py`, `stop_enrollment` now records when
  and what kind, `schedule_next_step` counts only advancing sends,
  `skip_message` explicitly does not count, endpoints
  `/strategies/{id}/completion`, `/strategies/{id}/completion/dropped`,
  `/sequences/{id}/completion`, a `completion` block on strategy analytics,
  and `CompletionPanel` on the analytics page. Tests:
  `tests/test_sequence_completion.py` (49),
  `tests/test_sequence_completion_migration.py` (6),
  `frontend/src/tests/sequenceCompletion.test.ts` (15). Regression: 130 tests
  across the engine-touching suites still green; `tsc --noEmit` clean.
  Decisions: `planned_steps` is a SNAPSHOT because counting a sequence's steps
  at read time means adding a step next month retroactively un-completes every
  finished enrollment; `stop_category` is decided at WRITE time so a new call
  site inventing a reason lands in `other` and is logged rather than silently
  widening a bucket; running enrollments are in neither half of the rate (a
  campaign on step 2 of 5 has not failed, it has not finished);
  `dropped_unauthorised` is reported separately from the rate because 60%
  completion is fine if the rest replied and alarming if the system dropped
  them. Docs: `docs/features/sequence-completion.md`.

- **2026-09-16 — Features 2 and 12 done.** Migration `0054_fpta_scoring`
  (8 nullable columns on `leads`, `fpta_overall` indexed),
  `app/services/fpta_scoring.py`, scored at enrollment from
  `sequence_engine.enroll_leads` (after the commit, and only for prospects
  with no score yet), `GET/POST /leads/{id}/fpta[/rescore]`, a strategy
  backfill endpoint, `sort=fpta` on the lead list, F-P-T-A columns on the CRM
  grid, `FptaBadges` on the lead header / kanban card / grid, and
  `WhyThisProspectPanel` (Feature 12) on the lead detail page. Tests:
  `tests/test_fpta_scoring.py` (46), `tests/test_fpta_scoring_migration.py`
  (5), `frontend/src/tests/fpta.test.ts` (20). `tsc --noEmit` clean; CRM
  suites (87) still green. Decisions: four columns rather than widening
  `ai_booking_likelihood`, because the two answer different questions and a
  single number erases which of the four is broken; the model may move a
  baseline by at most ±15 points and the clamp is enforced in code; a
  dimension with no evidence says so rather than borrowing confidence from a
  neighbour; Feature 12 adds NO storage and no model call — an explanation
  that needed its own generation step would be a second opinion about the
  score rather than an explanation of it. Docs:
  `docs/features/fpta-scoring.md`, `docs/features/why-this-prospect.md`.
  Also updated `tests/test_reply_intelligence.py`: the reply task's result now
  carries an extra `intent` key (Feature 1).

- **2026-09-16 — Feature 1 done.** Migration `0053_reply_intent` (5 nullable
  columns on `inbound_replies`), `app/services/reply_intent.py`, wired into
  `reply_tasks.process_inbound_reply`, `reply_quality` on strategy analytics +
  a dedicated `/strategies/{id}/reply-quality`, `intent` block on every CRM
  reply, `ReplyQualityPanel` on the analytics page and an intent badge in the
  reply inbox. Tests: `tests/test_reply_intent.py` (36),
  `tests/test_reply_intent_migration.py` (5),
  `frontend/src/tests/replyIntent.test.ts` (21). `tsc --noEmit` clean.
  Decisions: only `interested` counts as positive (`not_now` is a future
  opportunity, not a win for *this* campaign); a failed model call leaves the
  reply unclassified rather than guessing `neutral`, because a guessed label
  silently moves a headline metric; rates are `null` not `0.0` on an empty
  denominator. Docs: `docs/features/positive-reply-classifier.md`.
- **2026-09-16 (start)** — Surveyed the codebase (models, services, API, frontend,
  test layout, migration chain head = `0052_auth_sessions`). Confirmed backend tests
  run (`pytest tests/test_compliance_rules.py` → 31 passed). Wrote this file.

## Known issues / left for Rehan

- **Feature 5: decide whether the VIP-title trigger should be ON for your
  ICP.** LeadPilot sells to boutique agency OWNERS, and "owner"/"founder" is a
  VIP title — so with `send_review_vip_titles` on (the current default), every
  message to your core persona lands in the review queue. That is correct
  behaviour for someone selling into enterprises and wrong for you. Turn it
  off in `/admin/settings` (`send_review_vip_titles = false`) unless you
  genuinely want to hand-approve every send. The other three triggers
  (objection, stalled deal, tone) are exceptional by nature and are fine on.
  This is also why the test suite disables the whole gate by default — see the
  note at the end of `docs/features/send-review-queue.md`.

- **Feature 4 complaint rate is a proxy.** No FBL / Google Postmaster feed is
  connected, so the spam-complaint rate is approximated from unsubscribes plus
  replies asking to stop. Labelled `proxy` everywhere it appears. If you want
  a true complaint rate, connecting Google Postmaster Tools or a relay with an
  FBL is the change — the score, thresholds and send gate would not move.

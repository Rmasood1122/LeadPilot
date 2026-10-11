# Send-path gaps — fix note (2026-10-11)

Branch `claude/send-path-gaps`, based on the master hotfix `d43fa43`. Ten
findings from the founders' "fix every open gap" list and
`docs/program/help-center-discoveries.md` (#3, #6, #7, #8, #9, #12, #13, #14).
Each was checked in the code first; all ten were real. No migration was needed.

Tests: `tests/test_send_path_guards.py` (legal/safety guards: fixes 1, 3, 4, 7)
and `tests/test_send_path_gaps.py` (the rest). 41 tests in all. Against the
pre-fix tree (`git archive HEAD` + the two test files), 33 fail and 8 pass. The
8 that pass are controls that pin behaviour which must not change (an
unblocked follow-up still sends, verified leads still launch, suppression
still stops a re-engagement touch, and so on).

Legal readings below are marked **needs founder/legal confirmation**: they are
engineering readings, not settled law.

---

## 1. Meeting follow-up email went around the send chokepoint's guards — SAFETY GUARD

**Finding (confirmed).** `meeting_followup.send_followup` / `save_gmail_draft`
checked `is_suppressed(email, phone)` only. There was no LinkedIn suppression,
no F05 exclusion check, no F10 departure block and no derived opt-out.

**Why not the chokepoint itself.** The follow-up is a Gmail draft the user
sends by pressing Send. It is not a `Message` row. Its enrollment is stopped on
purpose by "Log Meeting Outcome", and the campaign, window and cap gates exist
to pace cold outreach, not a reply to a call. So the follow-up cannot go
through `send_message_impl` without a bypass flag. This change adds no second
send path: the existing user-pressed send now runs the chokepoint's
person-level guards, by calling the same functions in the same order.

**Fix.** New `app/services/recipient_guards.person_block()`. It checks
suppression (email, phone and LinkedIn), then `guardrails.send_block`, then
`champion_tracker.departure_block`, then `champion_tracker.derived_opt_out`.
It **fails closed**: a lookup error raises and the caller refuses to send.
Both drafting and sending run it. A blocked follow-up gets `draft_status`
`suppressed` (suppression list) or the new `blocked` (any other guard), with
the reason in `draft_error`. The frontend shows the reason and offers no
Send, Edit or Regenerate.

**Product decision, needs founder confirmation.** The F05 reasons `customer`
and `open_deal` do **not** block the follow-up. `guardrails.sync_from_crm`
(run by `crm_tasks`) adds every closed-won lead and every lead with an open
deal to those lists. Without the exemption, the thank-you after a won deal, or
the next step on an open one, would be blocked by the deal the meeting just
created. F05 exists to stop *pitching* those accounts cold. `do_not_contact`,
`churned`, `partner`, `competitor` and `other` still block.

**Legal basis (needs founder/legal confirmation).** The follow-up honours
opt-outs on every channel. That covers CAN-SPAM 15 U.S.C. §7704(a)(4) (no
commercial email after an opt-out), GDPR Art. 21(3) (objection to direct
marketing) and Art. 17 (erasure). It also covers CASL s.11 (unsubscribe). A
GDPR erasure suppresses the LinkedIn profile, so this check must include it.

**Tests.** `TestMeetingFollowupGuards`: LinkedIn suppression, F05
do_not_contact, departure, fail-closed and drafting all fail before the fix.
The customer/open_deal exemption and the plain happy path are controls.

## 2. Review-held step not counted as pending; a rejected step was retried (discoveries #7)

**Finding (confirmed).** `send_holds.pending_clause` counted SCHEDULED,
SENDING and guard holds, but not AWAITING_REVIEW. While a step waited for
review, the sweep created a second copy, so approving the first sent the step
twice. `send_review.reject` cancelled the message and said "the next step is
scheduled by the ordinary engine rules", but nothing scheduled it. The
enrollment sat ACTIVE with nothing pending, and the sweep re-created the
rejected step (`last_sent + 1`).

**Fix.**
- `pending_clause` now includes AWAITING_REVIEW (`send_holds.PENDING_STATUSES`).
- `reject()` advances an ACTIVE enrollment past a rejected *sequence step*
  (`origin` is None). It calls `schedule_next_step(counts_as_sent=False)`, the
  same as a skipped step, or completes the enrollment when the step was the
  last one. Reply Copilot answers and re-engagement touches advance nothing.
  The rarer in-chokepoint "cancel" decision does the same.
- The sweep skips steps a reviewer rejected (`_rejected_steps`,
  `_next_followup_step`). It never re-creates one, and it never generates an
  auto-DM to stand in for a rejected last step. `send_followup_impl` returns
  `skipped_rejected_in_review`. This also covers enrollments rejected before
  this fix.

**Tests.** `TestReviewHeldStepsAndTheSweep`: all 5 fail before the fix.

## 3. Sourcing suppression ignored LinkedIn — LEGAL GUARD

**Finding (confirmed).** `lead_tasks.source_leads_impl` called
`is_suppressed(email, phone)`, and enrichment did the same. After a GDPR
erasure (which writes a `LinkedInSuppression`), a LinkedIn-only person could
be sourced again.

**Fix.** Both calls now pass `linkedin=`: the raw row's URL when sourcing, and
the lead's stored or enriched URL when enriching.

**Legal basis (needs founder/legal confirmation).** GDPR Art. 17 and Art.
21(3): after an erasure or objection, the person must not be re-collected for
direct marketing.

**Tests.** `TestSourcingLinkedInSuppression`: both fail before the fix.

## 4. "Remove" did not stop a running sequence (discoveries #3) — SAFETY GUARD

**Finding (confirmed).** `PATCH /leads/{id}` to `dropped` only set the status,
and `send_message_impl` never read `lead.status`.

**Fix.** The PATCH to `dropped` stops every live enrollment (reason
`lead_removed`, which cancels pending messages). The chokepoint also refuses a
`dropped` lead at send time, whatever set the status: it cancels the message,
audits `blocked_lead_removed`, stops the enrollment and returns
`cancelled_lead_removed`. New stop category `lead_removed` (authorised: a
person decided).

**Tests.** `TestRemovedLead`: both fail before the fix.

## 5. "Not now" re-engagement auto-send was cancelled when due (discoveries #6)

**Finding (confirmed).** The touch is scheduled on the sequence the "not now"
reply had already stopped, so `send_message_impl` returned `cancelled_stopped`.
The module docstring also said auto-send was on by default. The setting
defaults to off, and stays off.

**Fix.**
- `reengagement_memory.answers_the_stop()` lets a `notnow_memory` message past
  a STOPPED enrollment only when the stop is the `replied_<class>` of the
  plan's source reply (or an earlier reply of the same lead), stored no later
  than the stop. This is the same narrow rule Reply Copilot answers use.
- `send_time_hold()` cancels the touch if the feature or auto-send was
  switched off since scheduling, the plan was cancelled, `still_appropriate`
  now objects, or the prospect wrote again after the source reply.
- The A5 conversion gate is skipped for this origin only. Its kill signal for
  the lead is the "not now" reply itself (routing class `not_interested` is a
  hard kill), so every touch would be archived. Suppression, exclusions,
  departure, compliance rules, the send window, the caps and the review queue
  all still apply. The touch does not advance or restart the stopped sequence.
- The docstring now says auto-send is off by default.

**Legal note (needs founder/legal confirmation).** The touch goes only to
someone who replied in the thread and named a "not now". It is still
commercial email with the footer and one-click unsubscribe, and every opt-out
still blocks it. Whether a deployment turns auto-send on is an admin decision.
The default remains off.

**Tests.** `TestNotNowTouch`: sent when due, cancelled by a newer reply, and
cancelled when auto-send is switched off all fail before the fix. "Another
stop reason still cancels", "suppression still applies" and "defaults off"
are controls.

## 6. WhatsApp-first sequences excluded phone-only leads; dishonest stop reason (discoveries #8)

**Finding (confirmed).** `enroll_leads` required `Lead.email` unless step 1 was
LinkedIn. A lead with no address for a step's channel was stopped with
`reason="suppressed"`, counted as an authorised compliance stop.

**Fix.** The first step's channel decides the address: email, LinkedIn URL,
or phone (WhatsApp and AI call). A missing address now stops with
`no_address_for_channel`, category `no_address` (*not* authorised, so it shows
in the completion metric as a drop), and returns `cancelled_no_address`. The
existing behaviour of stopping the enrollment is kept. **Alternative for
founders:** skip the step and continue (as no-opt-in WhatsApp steps already
do). That is a product decision and was not taken here.

**Tests.** `TestChannelAddress`: both fail before the fix.

## 7. Enroll accepted any lead status (discoveries #9) — SAFETY GUARD

**Finding (confirmed).** `EnrollRequest.lead_statuses` accepted any status, so
an API caller could enroll dropped, flagged or replied leads.

**Decision, from the code.** Only **verified** can be enrolled
(`sequence_engine.ENROLLABLE_STATUSES`). Flagged (a risky or unknown Hunter
verdict) stays out. The app never bulk-enrolls flagged leads: its launch form
sends `["verified"]` (`frontend/src/lib/api/outreach.ts`). The product's way
to use a flagged lead is a per-lead decision, moving it to verified on the
Pipeline board (`ui_support._ALLOWED_TRANSITIONS`). This change does not alter the send
path: a lead moved from verified to flagged *after* it was enrolled is still
sent to, and still becomes `contacted`, as before. Contacted leads and later
stages are out, because a second sequence would double the cadence, as are
unverified stages.

**Fix.** The API validator returns 422. The engine raises `ValueError` as
defence in depth. If a launch request stored before this change names a status
that is no longer allowed, approving it returns 409 with an explanation
instead of a 500.

**Tests.** `TestEnrollableStatuses`: the 4 API cases and the engine case fail
before the fix. "Verified still launches" is a control.

## 8. Events emitted but not registered; alerts not subscribable (discoveries #13)

**Finding (confirmed).** `send_needs_review`, `mailbox_paused`,
`reengagement_due` and `reply_draft_approved` were not in `event_bus.EVENTS`,
so `emit` raised `KeyError`. No push, Slack post or webhook for them was ever
delivered. The help-center article 12 claim "the owner is sent a
notification" was false until now. Separately, `domain_blacklisted`,
`deliverability_warning`, `mailbox_paused` and `send_needs_review` built
webhook payloads that no target could subscribe to.

**Fix.** The four events are registered with push titles (callers pass
title and body). Six alert events are subscribable (`EVENT_DESCRIPTIONS`),
with `SAMPLES` matching the payload the code builds:
`domain_blacklisted`, `deliverability_warning`, `mailbox_paused`,
`send_needs_review`, `reengagement_due` and `reply_draft_approved`.

**Tests.** An AST scan of `app/` checks that every literal event passed to
`enqueue_event`/`emit` is registered, and that every event that builds a
payload is subscribable. Three end-to-end checks (call site, then emit, then
webhook delivery, with the sample keys equal to the payload keys) fail before
the fix.

## 9. Webhook retry off-by-one (discoveries #12)

**Finding (confirmed).** Exhaustion triggered at `attempts >= 5`, so the 2-hour
delay was never used.

**Fix.** `MAX_ATTEMPTS = 1 + len(RETRY_DELAYS_SECONDS)`, which is 6 attempts:
30s, 2m, 10m, 30m, 2h.

**Existing tests changed (contract legitimately changed).**
`tests/test_crm_ecosystem.py::test_delivery_retries_then_exhausts` pinned the
off-by-one (`["retry"] * 4 + ["exhausted"]`). It now expects 5 retries
including `7200`, then exhaustion. In
`tests/integration/test_chunk5_production_launch.py` (outside the offline
suite), the exhaustion test now starts from 5 prior failures.

## 10. Double-booking prevented per page, not per host (discoveries #14)

**Finding (confirmed, narrower than stated).** Slot generation already hides
times that overlap a live booking on *any* of the host's pages. The gap was the
race: two overlapping bookings on two different pages in the same second both
passed that read, and the UNIQUE is per page. A host could also reactivate a
cancelled booking into a time that had since been taken.

**Why no constraint.** "No two live intervals of one host overlap" needs a
PostgreSQL exclusion constraint (`EXCLUDE USING gist (tstzrange &&)`), which
SQLite (the test suite) does not support. A UNIQUE on (host, start) would
catch only identical starts.

**Fix (transactional).** `calendar_service.lock_host_calendar()` takes
`SELECT ... FROM users WHERE id = host FOR NO KEY UPDATE` (review round:
`with_for_update(key_share=True)`, so foreign-key inserts referencing the user
are not blocked) *before* the slot check in
`public_book`, so booking writes for one host are serialised. Under
PostgreSQL's default READ COMMITTED isolation, the waiting writer's check sees
the committed booking and returns 409. Reactivating a cancelled booking runs
the same lock plus `host_conflict()`.

**Remaining race window.** Meetings created by hand from a proposed time do not
take the lock. Under REPEATABLE READ or SERIALIZABLE isolation the check would
read an older snapshot (the app uses the default). SQLite ignores FOR UPDATE
but serialises writers with its database lock.

**Tests.** The race is simulated (the competing booking commits "while waiting
for the lock") and fails before the fix. On SQLite this shows up as an
AttributeError because the lock function does not exist yet: a true
two-connection race cannot run in the single-connection test DB. The
statement compiles to `FOR NO KEY UPDATE` on the PostgreSQL dialect. Reactivating
into an overlap is refused (fails before the fix: 200).

---

## Review round (independent review of commit 4e10081)

| # | Sev | Finding | Fix (file:line) | Test | Pre-fix (on 4e10081) |
|---|---|---|---|---|---|
| R1 | H | The customer/open_deal exemption looked at ONE exclusion row (`find_match` ORDER BY kind LIMIT 1) and `upsert_exclusion` kept the first writer's reason, so an exempt row hid a do_not_contact row and the follow-up was SENT (3 probe cases). | `guardrails.find_matches` :302, `exclusions_for_lead` :358, `send_blocks` :385; `recipient_guards.person_block` :86 loops over EVERY match; upsert precedence `_outranks` :494 (documented in `upsert_exclusion` and docs/features/f05-guardrails-studio.md). F05 chokepoint unchanged (still `send_block`, any row blocks). | `TestExemptionNeverHidesDoNotContact` (3 ported probes + chokepoint control), `TestExclusionPrecedence` (7 cases) | 3 probes fail (`None is not None`, `'do_not_contact' in ''`, `('exists','open_deal','crm_local') != ('updated',...)`); 3 precedence upgrades fail; chokepoint control and 4 sticky/first-writer cases pass (pinned behaviour) |
| R2 | M | Rejecting a held step whose step the enrollment had already passed scheduled the next step a second time (double send) and rewound current_step. | `send_review.advance_after_reject` :423 skips when `current_step >= step` or a later step has a sent / scheduled / sending / awaiting-review / held message; the chokepoint's reject branch calls it (`outreach_tasks.py:615`). | `test_rejecting_a_step_the_sequence_already_passed_does_not_advance_again` (ported probe), `test_rejecting_does_not_advance_when_a_later_step_is_already_queued` | both: `assert 2 == 1` |
| R3 | L | Once the sweep scheduled the not-now touch (plan `sent`), the plan could not be cancelled (409). | `reengagement_memory.pending_touch` :434, `can_cancel` :453, `cancel` :462 also cancels a SCHEDULED / AWAITING_REVIEW / guard-held touch; `api/reengagement.py:168`; `plan_out` adds `touch_pending`; the lead panel offers **Never** while it is pending. | `test_a_scheduled_touch_can_still_be_cancelled`, `test_a_touch_that_already_went_out_cannot_be_cancelled` | `KeyError: 'touch_pending'` (then 409); `'gone out' not in 'this plan is already sent'` |
| R4 | L | The meeting follow-up did not refuse a removed (dropped) lead, and a blocked row had no way back. | `recipient_guards.person_block` :75 (REMOVED kind); `meeting_followup.recheck` :400 + `POST /meeting-outcomes/{id}/recheck` (`api/meeting_prep.py:306`); "Check again" button (FollowupDraftCard, `canRecheck` in lib/meeting-prep.ts). | `TestFollowupRemovedLeadAndRecheck` (3) + vitest "only a blocked or suppressed follow-up offers Check again" | DID NOT RAISE; recheck endpoint 404 (twice) |
| R5 | L | The host lock was `FOR UPDATE`, which blocks foreign-key inserts referencing the user. | `calendar_service.lock_host_calendar` :437 `with_for_update(key_share=True)` (FOR NO KEY UPDATE: still self-conflicting, so bookings stay serialised). | `test_the_lock_is_a_row_lock_on_postgresql` (now asserts FOR NO KEY UPDATE) | `'FOR NO KEY UPDATE' not in '... FOR UPDATE'` |
| R6 | L | `answers_the_stop` docstring claimed later stops keep the touch cancelled; stop_reason records the first stop only. | `reengagement_memory.py:660` docstring says what actually catches later events (suppression gate, dropped-lead gate, F05/F10, still_appropriate, newer-reply check). | n/a (docstring) | n/a |

`test_a_check_that_cannot_run_refuses_the_send` was changed to break
`guardrails.send_blocks` (the function person_block now calls); on 4e10081 it
fails only because that function does not exist yet.

## Help-center articles updated in the same change

06 (Remove, enrollable statuses), 08 (enrollment address, stop table, sweep
and review), 10 (WhatsApp-first enrollment, no-address stop), 12 (reject and
held steps), 13 (re-engagement touch; cancelling a scheduled touch), 14
(per-host double booking), 15 (follow-up guards, removed lead, every
exclusion row, Check again), 16 (subscribable alerts, 6 attempts), 25 (Remove
stops sequences). Feature specs amended: `send-review-queue.md`,
`reengagement-memory.md`, `crm-ecosystem.md`, `engagement-hub.md`,
`f05-guardrails-studio.md` (exclusion precedence).

## Out of scope: reported, not fixed

- `call_completed` is subscribable and documented (article 16), but
  `phone_calls` emits it without `webhook_payload`, so no webhook is ever
  delivered.
- `stop_enrollment` cancels SCHEDULED and SENDING messages but not
  AWAITING_REVIEW. A stopped lead's held message stays in the review queue.
  Approving it is safe (the send cancels it), but the queue is misleading.
- CRM deal-stage webhooks and the CRM bulk patch can set closed or
  disqualified statuses without stopping enrollments. The send path now blocks
  only `dropped`.
- `meeting_followup.log_outcome` stops with reason `meeting_outcome_<x>`,
  which `sequence_completion` does not know, so it is logged and counted as
  `other`.
- `reengagement_memory.still_appropriate` checks suppression on email only.
  The send path re-checks all three identifiers, so nothing is sent, but the
  plan is not cancelled with that reason.

## Runs (review round)

| Command | Exit | Result |
|---|---|---|
| `python -m pytest tests/test_send_path_gaps.py tests/test_send_path_guards.py` on the 4e10081 tree with the new tests copied in | 1 | 15 failed, 44 passed (the pre-fix column above) |
| `python -m pytest tests/test_send_path_gaps.py tests/test_send_path_guards.py tests/test_guardrails.py tests/test_meeting_prep.py tests/test_reengagement_memory.py tests/test_send_review.py tests/test_calendar_api.py -q -p no:cacheprovider` | 0 | 332 passed |
| `python -m pytest tests -q -p no:cacheprovider --ignore=tests/integration` | 0 | 4686 passed, 7 skipped, 694 s |
| `npx tsc --noEmit` (frontend) | 0 | clean |
| `npx vitest run src/tests/meeting-prep.test.ts src/tests/reengagementMemory.test.ts` | 0 | 31 passed |

Gate (`run_evals.py`, `promote.py`, `verify_block_fixtures.py`), commit SHA and CI run: recorded on the stacked PR by the orchestrator.

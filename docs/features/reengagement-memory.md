# Re-engagement Memory — "not now" ≠ "never" (Part 1, Feature 7)

**Migration** `0059_reengagement_memory` ·
**Service** `app/services/reengagement_memory.py` ·
**Task** `app.workers.reply_tasks.run_reengagement_memory` (daily 05:50) ·
**UI** `frontend/src/lib/reengagementMemory.ts`,
`components/leads/ReengagementMemoryPanel.tsx`

## The problem

A prospect who writes *"we're mid-contract until March, try us then"* has just
handed over the single most valuable thing in cold outreach: **a date**. Every
outbound tool then does the same thing with it — stops the sequence, marks the
lead not interested, and forgets. March arrives and nobody comes back, because
nothing wrote it down.

## What gets written down

Every reply Feature 1 labels `not_now` produces a `ReengagementPlan`:

| Field | What it holds |
|-------|---------------|
| `reason_text` | the reason **in the prospect's own words** |
| `reason_kind` | budget / contract / timing / project / headcount / priority / unspecified |
| `stated_return_on` | a date **they named**, when they named one |
| `due_at` | their date if given, otherwise today + the interval |
| `interval_days` | how long the wait represents |

**The reason is stored twice on purpose.** `reason_kind` is what the UI groups
and filters by; `reason_text` is what the return message quotes. A hook built
on their sentence survives being read back to them nine months later. A
paraphrase does not.

### Extraction

One structured Claude call, given **today's date** so "Q2" and "in March" can
resolve into a real calendar date. A date that resolves into the **past** is a
mis-resolution and is dropped rather than obeyed.

A model outage falls back to deterministic phrase rules, which give a usable
`reason_kind` and **no invented reason text**. Losing the nuance is acceptable;
losing the plan is not.

### The interval depends on the reason

| Reason | Wait |
|--------|------|
| timing / project | 60 days |
| budget / headcount | 90 days |
| priority | 120 days |
| contract | 180 days |
| unspecified | the configured default (90) |

**A date the prospect named always wins.** They know their own contract renewal
and we do not. Using one interval for every objection is what makes
re-engagement feel like spam: a contract renews on a different clock from a
busy month.

## Why a new table and not `reengagement_attempts` (0048)

That table is the once-per-enrollment **claim** for the opt-in post-sequence
sweep; its whole purpose is the `UNIQUE(enrollment_id)` that stops a retry
sending twice, and it carries no reason and no future date. This object has a
different lifetime: created by a **reply**, it outlives the enrollment and even
the sequence, a person can move or cancel it, and it is where the prospect's
words live.

`UNIQUE(source_reply_id)` makes this idempotent by construction — a webhook
retry, a re-classification or two overlapping sweeps cannot make two plans for
one reply.

Only `lead_id` cascades on delete. A plan whose reply, strategy or message is
gone keeps the promise.

## The date is mirrored onto the CRM

`_mirror_next_action` writes `due_at` onto `CrmLeadMeta.next_action_at` (only
if it is sooner than what is there), so the existing follow-up machinery, the
lead list and the kanban all show the date without knowing this feature exists.

## When the day arrives

The daily sweep (05:50 — the unit of this feature is a *day*, and a plan due
today should be in the list before work starts):

1. **Re-checks that coming back is still appropriate** — and does this *when
   the plan comes due*, not when it was made. Ninety days is long enough for
   the prospect to have unsubscribed, bounced, been suppressed, closed won or
   lost, or booked a meeting through another route. Any of those cancels the
   plan **with the reason recorded**.
2. Marks it `due` and notifies.
3. If `reengagement_memory_auto_send` is on, schedules a real `Message` with
   `origin="notnow_memory"` — **an ordinary message**, so suppression,
   compliance, the send window, mailbox health (Feature 4) and the human review
   queue (Feature 5) all apply. *This feature decides when to knock; it does
   not decide that knocking is allowed.*

`reengagement_memory_auto_send` defaults to **False**: most people want to read
a nine-month-old promise before acting on it. Turn it on per deployment in
`/admin/settings`.

If there is nothing to send from (no previous message, so no channel and no
sequence), the plan still becomes `due` and the user is still told.

## The return message brief

`brief_for()` **quotes the prospect** and explicitly forbids pretending this is
a first contact. The whole value of a 90-day memory is being able to open with
*"you said you were mid-contract until March"* instead of *"just circling
back"* — the second is indistinguishable from every other unwanted follow-up
they get.

## API

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/reengagement/plans?status=scheduled\|due\|sent\|cancelled\|all` | Soonest first |
| `GET` | `/leads/{id}/reengagement-plans` | Every "not now" this prospect gave |
| `POST` | `/reengagement/plans/{id}/reschedule` | `{due_on}` — a **date**, because the unit is a day |
| `POST` | `/reengagement/plans/{id}/cancel` | `reason` required |

Rescheduling works on a plan the sweep has already marked `due`: a person who
knows the prospect knows better than the interval table. Deciding twice is a
**409**.

## Settings

`reengagement_memory_enabled` (True), `reengagement_memory_days` (90, clamped
to 7–540 — a 2-day "re-engagement" is a nag and a 5-year one is a rounding
error), `reengagement_memory_auto_send` (False).

## Tests

`tests/test_reengagement_memory.py` (51) — extraction with the rule fallback,
a named date beating the default, a past date being dropped, one reply never
making two plans, appropriateness re-checked at due time for each terminal
state, the sweep's cancel-with-reason, auto-send off by default and the message
shape when on, and the API including the 409 and the cross-account 404.
`tests/test_reengagement_memory_migration.py` (7) — including that only
`lead_id` cascades. `frontend/src/tests/reengagementMemory.test.ts` (17).

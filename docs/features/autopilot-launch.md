# Autopilot launch, best-time scheduling and "Why isn't this sending?"

Status: built in the same change as this spec (founder decision 2026-10-10:
build straight away; the founders review spec and code together at merge).

Flags (system settings, `app/services/system_settings.py`):

| Flag | Default | What it does |
|---|---|---|
| `autopilot_launch_enabled` | **on** | Offers the Autopilot option. The per-strategy opt-in itself is **off** until a person turns it on and confirms the lawful-basis text. Off = the option is hidden, the API refuses to turn it on (409) and the sweep does nothing. |
| `best_time_scheduling_enabled` | **on** | Places each scheduled message at the best slot in the prospect's local time instead of "as soon as the send window opens". Off = exactly the previous scheduling. |
| `best_time_min_sends` | 30 | Sends per channel an account needs before its own reply rates are blended into the slot choice. |

Migration: `0087_autopilot_launch` (one new table, two new JSON columns on
`strategies`). Spec author's note: I am not a lawyer. Every reading of a
statute below is marked **needs founder/legal confirmation**.

---

## 1. Founder report (2026-10-11, verbatim)

> "when Pipeline is done it doesn't send Mails and Messages. That's a very big
> problem. Build a feature or fix it. It should research while building the
> pipeline the best time to message, and according to that time send DMs, mails
> and messages automatically. Improve its capabilities."

## 2. Recon — what happens today after the pipeline completes

Traced through the code on master `be2f9e0`.

1. `app/workers/tasks.py::run_pipeline` runs the 72/144 research steps
   (`app/pipeline/engine.py::run_all_steps`), assembles the documents, binds the
   playbook bucket (`icp_extraction.ensure_pattern_key`, metered `icp`), sets
   `status = VERIFYING` and enqueues `run_verification`.
2. `run_verification` → `app/verification/loop.py::run_verification_loop`: ten
   judge passes, each with automatic fix-and-retry. **No human is needed when
   every pass ends PASS** → `status = VERIFIED`. If any pass exhausts its
   retries → `NEEDS_HUMAN_REVIEW`; a person then either re-runs verification
   (`POST /strategies/{id}/reverify`) or signs off failed passes
   (`POST /strategies/{id}/override-passes`, audited; the Legal pass can never
   be overridden). The owner gets a push either way
   (`notify_strategy_ready` / `notify_strategy_needs_review`).
3. **The chain stops here.** Nothing is enqueued after `VERIFIED`.
4. Lead sourcing is **manual**: `POST /strategies/{id}/leads/source`
   (`app/api/leads.py`), only for a `VERIFIED` strategy; ICP extraction
   (metered `icp`), plan room (`max_leads_per_strategy`), F07 spend forecast,
   then `lead_tasks.start_lead_chain` (source → enrich → find email → verify →
   finalize; suppression and F05 exclusions at source and enrich; F01
   waterfall verification; finalize scores leads). UI: "1. Find leads" in
   `frontend/src/components/strategy/OutreachPanel.tsx`.
5. Sequence creation is **manual**: `POST /strategies/{id}/sequences`
   (`app/api/sequences.py::create_sequence`) with briefs the person types. The
   app's form builds an **email-only, 1–2 step** sequence
   (`frontend/src/lib/leadOutreach.ts::buildSequenceSteps`). There is **no
   existing code that generates a sequence from the strategy**; step briefs are
   personalised at send time by `message_personalization.render_message`, which
   already reads the strategy's Phase-6 messaging synthesis.
6. Launch is **manual**: `POST /sequences/{id}/enroll` — phone-verified
   account (`identity.require_verified_phone`), `_launch_checks` (VERIFIED,
   campaign active), F03 `_deliverability_preflight`, `_enforce_plan_for`
   (channels + step count), Feature A7 red-team `_review_gate`, SDR → manager
   approval in workspaces, then `sequence_engine.enroll_leads` (VERIFIED leads
   with an address for step 1's channel, suppression, F05 exclusions) which
   schedules step 1 at `next_window_slot(now)` (09:00–17:00 in the lead's
   timezone, weekends skipped) or the campaign's measured smart window
   (`send_windows.next_smart_slot`, only when the campaign's smart send time is
   on and 50+ opens exist).
7. **The lawful-basis confirmation is client-side only.** The launch card's
   checkbox ("I have read the list above and I confirm I may lawfully email
   each of these people (CAN-SPAM, GDPR, CASL, PDPA as they apply)…") gates the
   button in the browser; the server records nothing. (Fixed in the follow-up,
   section 3.5.)
8. The Beat dispatcher (`dispatch_due_messages_impl`) enqueues due
   `SCHEDULED` messages of active campaigns; `send_message_impl` re-checks every
   gate at send time, in this order: campaign paused; enrollment stopped/paused;
   lead removed; suppression / no address; F05 exclusions; F10 departures +
   staleness hold; **plan holds** (`plan_limit: `); F01 **Bounce Shield**
   (flag, default off); re-engagement switch; conversion-probability kill;
   WhatsApp opt-in / 24h window / approved template with opt-out; compliance
   rule consent + window; **send window** (defer); **daily send approval**
   (ON by default — every automatic send waits for the owner's approval of
   today's sending for that channel, `/send-approval`); channel caps and
   warm-up (LinkedIn per-account ceilings, WhatsApp cap, email cap + mailbox
   health pause/throttle + F03 ramp); claim; render; **send review queue**
   (Part 1 Feature 5, held as `AWAITING_REVIEW`); F05 forbidden phrases;
   transmit.
9. Channel prerequisites at send time: email needs a connected Gmail account
   for the owner (`_account_for_strategy` raises otherwise → retried and
   stuck); LinkedIn needs Unipile configured and an active LinkedIn account
   (`failed_linkedin_not_configured` / `failed_no_linkedin_account` = FAILED);
   WhatsApp needs the deployment's Meta credentials, an APPROVED template with
   an opt-out line, and the lead's recorded opt-in (otherwise the step is
   skipped).

**Every manual step and gate between "pipeline completed" and "first message
transmitted"** — (a) verification passes or a person signs off; (b) a person
presses *Find leads*; (c) sourcing finishes; (d) a person writes the brief(s);
(e) a person ticks the lawful-basis box and presses *Launch*; (f) launch gates
(phone verified, plan, F03 preflight, A7 review, manager approval for SDRs);
(g) the message's slot arrives inside the send window; (h) **a person approves
today's automatic sending** for the channel; (i) caps/warm-up/mailbox health;
(j) the send review queue (if its triggers fire, a person approves the
message).

**The orchestrator's understanding is confirmed, with one correction:**
nothing is automatic after research — a person must source leads, create the
sequence and launch. *Correction:* verification itself is automatic; a person
is needed only when it ends `needs_human_review`. *Addition:* even after
launch, nothing is transmitted on a day the owner did not approve automatic
sending (founder decision, daily send approval ON by default) — so a fully
automatic launch still waits for that daily "yes". That is kept on purpose and
shown by the diagnostics panel.

**Already-existing building blocks reused** (this is "compose and extend",
not a parallel engine): the lead chain, the ICP extractor, F07 spend forecast,
plan checks, every launch gate in `app/api/sequences.py`, `enroll_leads`, the
send window, `send_windows.next_smart_slot`, the notification hub
(`notification_tasks.enqueue_event` → FCM push + Slack + webhooks), the
transactional email gateway (`email_sender.send_email`, never the outreach
mailbox), `compliance_audit_log` and `security_audit_events`, usage meter
scopes, and every send-time gate (untouched). `send_time_optimizer.py` (the M8
UTC slot recommender for the Analytics page) is left as it is; it does not
schedule.

## 3. Behaviour

### 3.1 Autopilot launch (per strategy, opt-in)

* **Opt-in** at strategy creation (`POST /products/{id}/strategies` field
  `autopilot`) or later on the strategy page (`PUT
  /strategies/{id}/autopilot`). Label: *"When research finishes, find leads,
  write the sequence and start outreach automatically"*. Never pre-ticked.
* Turning it **on** requires `lawful_basis_confirmed: true` and the current
  `lawful_basis_text_version` (`autopilot-lawful-basis-2026-10-12`; the
  2026-10-11 text was replaced in review, see 3.6, and a row confirmed under
  the old text PAUSES until re-confirmed); otherwise
  **422** and nothing is stored. The text (constant
  `autopilot.LAWFUL_BASIS_TEXT`) is shown verbatim in the UI and returned by
  `GET /strategies/{id}/autopilot`. Recorded: who (the acting person, also in a
  workspace), when, the text version **and the exact text**, on the
  `autopilot_launches` row, in `compliance_audit_log` (decision
  `autopilot_opt_in`, kept as proof on account erasure, like the daily
  approval decisions) and in `security_audit_events`. Turning it off is
  recorded the same way (`autopilot_opt_out`).
* Only an account owner or a workspace owner/manager may turn it on (SDRs
  and personal API keys get 403): the SDR manager-approval rule for launches
  must not be bypassable through Autopilot.
* **Daily send approval is a precondition** (review M5): turning it on is
  **409** unless `daily_send_approval_enabled` is on AND every channel
  Autopilot uses (email, LinkedIn, WhatsApp) is in
  `daily_send_approval.gated_channels` (`autopilot.approval_gap`). If that
  stops being true later, the sweep sets state `paused` and notifies once, and
  the send path holds Autopilot's messages (3.6).
* **When it acts.** On `VERIFIED` only. The verification loop already ends
  automatically when every pass is green, so Autopilot acts right after it.
  A `needs_human_review` strategy is **not** bypassed: Autopilot waits, says so
  on the strategy page and notifies the owner once ("verification needs your
  review — Autopilot is waiting"); a human sign-off (`override-passes`, which
  moves it to `VERIFIED`) or a successful re-verify resumes it. `failed` and
  `budget_exhausted` wait the same way.
* **What it does** (`app/services/autopilot.py::advance`, idempotent):
  1. **Leads — always its OWN batch** (review M6). Autopilot starts its own
     batch through the same path as the *Find leads* button
     (`autopilot.start_sourcing`; cheapest check first: plan room, then the
     F07 enrichment forecast — no model call — then the ICP extraction,
     metered `icp`, done ONCE and cached on the row in `icp_json`) and records
     the batch id in `batch_ids_json`. The chain is the same five-stage chain
     (suppression, F05 exclusions, F01 verification) on the same queue as the
     manual button. Size: `autopilot_lead_target` (default 25), capped by
     `leads_max_per_run` and the plan room. It waits until the batch is
     finalized, then snapshots the VERIFIED leads **of its own batches** into
     `eligible_json`, excluding champion-move (F10) leads. Leads sourced or
     verified by hand, earlier batches and leads flipped to verified later are
     never Autopilot's.
  2. **Sequences.** One sequence **per channel** (email, LinkedIn, WhatsApp;
     never AI phone calls), created once, the first time the channel is in the
     plan (WhatsApp: once an approved template exists and a lead opted in).
     **The strategy's own channel plan:** email always; LinkedIn / WhatsApp are
     "planned" when the strategy's execution plan (Phase 8) or document names
     them. Planned channels come first in the lead-assignment order and are the
     only ones the owner is nagged to connect; an unplanned channel that happens
     to be ready is still used. Step briefs come from one metered model call
     per channel (purpose `autopilot`, account-capped) over the
     strategy's Phase 6 (messaging) and Phase 8 (execution plan) syntheses,
     validated (≤ 3 steps, delays 0–14 days, brief ≤ 800 chars) and **falling
     back to fixed briefs** that point the personaliser at the strategy's own
     playbook when the call fails or returns nothing usable.
     WhatsApp steps use the APPROVED template with an opt-out line **that the
     person chose** for Autopilot (`PUT
     /strategies/{id}/autopilot/whatsapp-template`); until one is chosen
     WhatsApp waits with `whatsapp_template_not_chosen`. Never the
     alphabetically first one.
  3. **Launch gates — the same ones as the Launch button**, called from
     `app/api/sequences.py` (not copied): phone-verified owner,
     `_launch_checks`, `_deliverability_preflight`, `_enforce_plan_for`,
     `_review_gate` (inside a `launch` usage scope). A refusal is recorded on
     the channel with the API's own message and notified.
  4. **Enrollment.** Each lead in the pool (`autopilot.pool`: eligible, not
     unreachable, still VERIFIED, not already in a sequence of the strategy)
     goes to **one** channel sequence — the
     first ready channel in the strategy's channel order for which the lead
     has an address (email → email; LinkedIn → profile URL; WhatsApp → phone
     **and** a recorded opt-in). A lead is never in two Autopilot sequences, so
     one person never gets two parallel cadences. `enroll_leads` (new optional
     `lead_ids` filter, default unchanged) applies the existing rules:
     VERIFIED only, suppression, F05 exclusions, unique per sequence. Step 1 is
     placed by the best-time scheduler (3.2), inside the window resolved for
     that lead (compliance rule or default).
     Leads that can never be contacted (suppressed, F05-excluded, F10
     departed — the same functions the gates use) are moved to
     `unreachable_json` before the gates run, and a lead the enrollment skipped
     is recorded there too ("skipped at enrollment"), so it leaves the pool and
     the launch gates are not re-run for it every sweep (review M1).
  5. Every message then goes through `send_message_impl` exactly like a
     manually launched one — daily send approval, compliance, review queue,
     caps, warm-up, plan holds, Bounce Shield. **Nothing is bypassed and no new
     send path exists.**
* **States** (`autopilot_launches.state`): `off`, `waiting_for_research`,
  `waiting_for_review`, `blocked` (research stopped, campaign paused, sourcing
  refused, no lead passed verification), `sourcing`, `waiting_for_channels`
  (verified leads exist but no channel they can be reached on is ready),
  `launched` (at least one channel has at least one real enrollment; waiting
  channels and unreachable leads named in the reason), `idle` (nothing left
  to enroll), `paused` (daily send approval stopped covering a channel, or the
  confirmed text is out of date). Per channel: `launched` (only with > 0
  enrollments), `waiting`, `blocked` (a launch gate refused), `idle`. When
  every found lead is unreachable the row is `blocked`: "Nothing was
  launched: N lead(s) cannot be contacted (reasons)." — never "Running".
* **Missing prerequisites.** Channels are checked by
  `send_diagnostics.channel_readiness` (the same function the diagnostics
  panel uses): plan includes the channel; email: a connected Gmail account;
  LinkedIn: Unipile configured + an active LinkedIn account; WhatsApp: Meta
  credentials + an approved template with opt-out. Ready channels launch;
  the rest wait (`channels_json` says why) and the owner is notified by
  transactional **email**, **push** (event `autopilot_update`, FCM + Slack via
  the hub) and **in-app** (the Autopilot card on the strategy page and the
  diagnostics panel) — once per distinct reason (a reason that persists is not
  re-sent; a new one is).
* **Resume: a beat sweep, not hooks.** `leadpilot.autopilot.sweep` runs every
  15 minutes (`:03/:18/:33/:48`, clear of the other sweeps) over enabled
  Autopilot rows and calls `advance` (which does nothing for a paused
  campaign but say so). Chosen over hooks
  because a prerequisite can appear through many unrelated paths (Gmail OAuth
  callback, Unipile account webhook, Meta template-status webhook, Stripe plan
  change, a person moving a flagged lead to verified); hooking each would be
  five places to forget. The sweep is cheap (a few indexed reads per enabled
  strategy). Also enqueued directly when verification finishes, when a person
  overrides failed passes and when Autopilot is switched on for an already
  verified strategy, so the normal path does not wait for the sweep.
* **Ongoing.** Only leads of Autopilot's own batches are ever enrolled; a
  flagged lead a person moves to verified, a hand-sourced batch or a champion
  move is for the person to launch (review M6). Turning Autopilot off stops all future automatic actions; it does
  **not** cancel messages already scheduled (pause the campaign for that —
  existing control).
* **Idempotency.** The batch and each channel's sequence are created under a
  conditional-UPDATE claim on the `autopilot_launches` row (two workers cannot
  both create one). A long step refreshes the claim (`_heartbeat`: a
  conditional UPDATE of `claimed_at` that checks the token); a worker whose
  claim was taken over stops before sourcing or enrolling (`busy`); enrollment is unique per (sequence, lead) and a lead in any
  Autopilot sequence of the strategy is never enrolled into another. A re-run
  never double-sources or double-enrolls (tested).
* **Budget.** Sourcing uses F07's existing forecast/caps. A refusal (or an
  ICP extraction refused by the model budget) sets `retry_after` to the next
  00:00 UTC: no further model call or sourcing attempt before then, and the
  owner is told once (review M2). The ICP is extracted once and cached. Model calls: one brief-generation call per
  channel sequence created (≤ 2 per strategy: WhatsApp uses its template; purpose
  `autopilot`) and the send-time plan call (3.2, purpose
  `send_time`), both account-capped; plus what launch already spends (A7
  review, metered `launch`). No new uncapped spend.

### 3.2 Best-time-to-send scheduler (`app/services/send_time.py`)

**Priors, not promises.** These are starting assumptions drawn from widely
published industry send-time studies (general knowledge, not re-verified
against the studies for this change — see *Unverified*). They only choose
*where inside the permitted sending hours* a message lands; the account's own
results override them once there is enough data.

| Channel / ICP | Preferred windows (prospect's local time) | Basis |
|---|---|---|
| Email, B2B default | Tue–Thu 09:00–11:00; Mon & Fri 10:00–11:00 | Widely reported B2B email studies (e.g. HubSpot, Mailchimp, GetResponse, Woodpecker/Yesware cold-email analyses): mid-week, mid-morning best for opens and replies |
| LinkedIn, default | Tue–Thu 08:00–10:00 and 12:00–13:00 | Social-media timing studies (e.g. Sprout Social, Hootsuite) — measured for posts, not DMs; weakest prior |
| WhatsApp, default | Mon–Fri 10:00–12:00 and 15:00–17:00 | Avoid early morning / evening for a business message |
| Restaurants, cafés, hospitality, food service (all channels) | Mon–Fri 14:30–16:30 | Between lunch and dinner service rush |
| Clinics, hospitals, dental, healthcare admin (all channels) | Mon–Fri 09:00–11:00 | Admin staff before the day's clinic peak |
| Retail, shops | Mon–Fri 09:00–09:30 (before opening) and 14:00–16:00 | Before opening or the mid-afternoon lull |
| Real estate | Mon–Fri 09:00–10:30 | Agents plan the day in the morning |

Industry matches are keyword matches on the strategy's ICP industries
(`pattern_inputs_json.icp.industries`, written by the pipeline). Every window
is intersected with the permitted send window (09:00–17:00, weekdays by
default, or the compliance rule's window); a prior that falls entirely outside
it (e.g. trades at 07:00) is ignored for that channel.

**Send-time plan, made when the pipeline completes — only if it will be used.**
`send_time.ensure_plan` runs in `run_pipeline` right after the ICP/playbook
binding and before verification is enqueued, and only when
`send_time.plan_wanted` (best-time on AND (Autopilot on for the strategy OR
the strategy has an active sequence)); otherwise no model call is made and
placement uses the priors (a post-completion hook — the 72/144-step registry is
**not** changed). It builds the plan from the priors for the strategy's ICP,
then asks the model once (purpose `send_time`, account-capped, inside the
owner's usage scope) to refine the windows for the ICP's industries, roles and
regions, returning per-channel `{days, start, end}` windows and a reason. The
answer is validated (known days, quarter-hour times, ≥ 30 minutes, ≤ 4 windows
per channel); anything invalid, an empty answer or a failed call keeps the
priors. Stored on `strategies.send_time_plan_json`:
`{"version": 1, "source": "model"|"priors", "generated_at", "industries",
"channels": {"email": {"windows": [...], "reason": "..."}, ...}}`. Never
raises; a failure never fails the pipeline.

**Learning.** Once the account has `best_time_min_sends` (30) sends on a
channel (last 180 days, owner-filtered, at most 5,000 sends and the latest
20,000 replies, read with portable ORM queries — no PostgreSQL-only SQL; index
`ix_messages_status_sent_at`), its own reply rates by local weekday × hour are
blended in with Bayesian smoothing toward the prior. They are computed **only
by the periodic task** `leadpilot.autopilot.refresh_learning` (beat
`send-time-learning-refresh`, every 6 h at :29) into Redis
(`send_time:learned:{owner}:{channel}`, TTL 7 h); placing a message reads
Redis only and never runs the learning query (a warm placement runs at most
one SQL statement — tested). Redis down or the key missing → the priors:

```
p0         = (replies + 1) / (sends + 2)                     # account base rate
m(slot)    = p0 × 1.25 if slot is in a preferred window else p0 × 0.85
score(slot)= (replies_in_slot + 20 × m(slot)) / (sends_in_slot + 20)
```

A slot with no data scores its prior mean, so the prior decides until real
results outweigh 20 pseudo-sends. A reply is credited to the lead's most
recent send before it, in that send's local slot. Opens are **not** used:
Apple Mail Privacy Protection pre-fetches pixels and EU/UK leads get no pixel
(open_tracking.py), so open hours are noise for this purpose.

**Placement.** For a step due at `earliest` (enrollment: now; later steps:
previous send + `delay_days`), the candidate instants are every quarter hour
from `earliest` to `earliest + send_time_max_delay_hours` (72 h, the existing
smart-send knob) that are inside the permitted send window in the lead's
timezone (`sequence_engine.lead_timezone`). The message goes to the **earliest
candidate whose score is at least 90% of the best score in that horizon**,
plus a deterministic 0–29 minute spread per lead (kept inside the window) so a
campaign does not fire at :00. No candidate → `earliest` (old behaviour). The
search walks UTC instants and converts each, so DST gaps/overlaps cannot
produce a non-existent local time.

Precedence: **the person's override window** > the campaign's measured smart
windows (`send_windows`, existing, only when that campaign switched it on) >
the account's learned rates > the strategy's send-time plan > channel/industry
priors.

**Applied** in `sequence_engine._schedule_step_message` (enrollment and
`schedule_next_step`, `delay_days` respected) and in `send_message_impl`'s
existing *outside sending hours* deferral (so a message deferred overnight —
e.g. held for daily approval until local midnight — lands on the best slot of
the next day instead of 09:00 sharp). Daily caps, warm-up and mailbox health
are unchanged and still enforced at send time; the deferral on a full cap is
unchanged. There are no holiday rules in the codebase (searched), so none are
applied. Automatic follow-ups (`send_followup_impl`, Engagement Hub) still send
when their silence timer ends inside sending hours — unchanged, out of scope.

**Override.** `PUT /strategies/{id}/best-time` `{days, start, end}` (one window
for every channel, local to each prospect; owner or manager, signed in — 403
for an SDR or a personal API key) — a **hard** window: messages are only
placed inside it AND inside the window resolved for each lead (compliance
rule or default); with no candidate in the horizon the slot is the horizon
limit, never a time outside the override (review). It is enforced at **send
time** too (`send_time.override_hold` in `send_message_impl`, after the
compliance window): an automatic message due inside the permitted window but
outside the person's own is re-placed into it (`deferred_override_window`),
never sent — this covers messages scheduled before the window was saved and
a horizon-parked message after a compliance rule added later removed the
overlap (that message then waits, visible as its next send time). A message a
person approved one by one in the review queue is not held. A window that does not
overlap the resolved window of the strategy's leads is **422** at save time
(`send_time.override_conflicts`). Saving answers **202** with `rescheduling`
(how many scheduled messages will be looked at) and re-places this strategy's
future scheduled messages in the background (`leadpilot.autopilot.reslot`;
not those due within 5 minutes). Clearing answers 200.

**Flag off** (`best_time_scheduling_enabled = false`): `_schedule_step_message`
and the deferral behave exactly as before (tested).

**Prospect timezone.** Both the scheduler and the send window use
`lead_timezone`, which now resolves a real zone per lead (3.4).

### 3.3 "Why isn't this sending?" (`app/services/send_diagnostics.py`)

`GET /strategies/{id}/send-diagnostics` returns, per channel, every condition
currently stopping sends, in plain words with the fix and a link; the panel on
the strategy page renders it. Each reason calls the real gate (or reads the
real gate's marker) so the panel cannot drift from the send path; a test pins
each reason to its gate by also driving `send_message_impl` into the matching
result.

| Code | Reads | Fix / link |
|---|---|---|
| `strategy_not_verified` / `verification_needs_review` | `strategy.status` (the `_launch_checks` rule) | `/strategies/detail?id=` |
| `campaign_paused` | `campaign_state` (send path's first gate) | Campaigns page |
| `not_launched` | no enrollment on the channel | Launch card / Autopilot |
| `no_verified_leads` | VERIFIED leads not enrolled + none enrolled | Find leads |
| `channel_not_in_plan` | `plans.check_send_channel` | `/pricing` |
| `gmail_not_connected` | Gmail account of the owner (`_account_for_strategy`) | `/settings?tab=integrations` |
| `linkedin_not_configured`, `linkedin_no_account` | `linkedin_outreach.client_for` / `active_accounts` | `/settings?tab=integrations` |
| `whatsapp_not_configured`, `whatsapp_no_template`, `whatsapp_no_optins` | Meta credentials, APPROVED template with opt-out, opt-ins | Templates tab |
| `send_approval_missing` | `daily_send_approval._channel_hold` (the gate itself) + count of held messages | `/send-approval` |
| `outside_sending_hours` | `sequence_engine.in_send_window` with the window `compliance_rules.resolve` gives the next due message's lead | — (next window time) |
| `no_send_window` (blocking) | the resolved compliance rule leaves no sending hours for that lead | Compliance rules |
| `consent_required` | `compliance_rules.resolve(...).consent_required` for scheduled leads with no recorded consent (blocking when it is all of them) | lead page |
| `autopilot_approval_hold` | Autopilot messages held by `autopilot.send_hold` (error prefix `autopilot: `) | `/send-approval` |
| `gmail_token_invalid` | the latest email send from the account failed on Google's token endpoint (`invalid_grant`, revoked or expired) — the real token-health signal; the account is not "ready" | `/settings?tab=integrations` |
| `daily_cap_reached` | `sequence_engine.allowance_left` (with mailbox-health cap + F03 ramp, and the resolved rule's `daily_cap`; the lower wins) / `whatsapp_allowance_left` | — (resets tomorrow) |
| `mailbox_paused` | `mailbox_health.gate` | `/settings?tab=deliverability` |
| `held_in_review` | messages `AWAITING_REVIEW` | `/campaigns?strategy=&tab=review` |
| `plan_holds`, `bounce_shield_holds`, `champion_holds` | `send_holds` prefixes | `/pricing` / lead page |
| `phone_calling_off` | `phone_calling_enabled` | admin |
| `autopilot_flag_off` | Autopilot on for the strategy but the system flag off | admin |
| `suppressed` (info) | messages cancelled as suppressed / leads dropped as suppressed | — |

| `timezone_fallback` (info) | leads whose zone comes from a fallback, and which (`lead_timezone.resolve` sources) | `/calendar` |

Plus `next_send_at` per channel, `timezones` (lead counts per zone source) and
the "Messages go out at …" explanation.

The rules-based codes are evaluated for the NEXT due message's lead (and
`consent_required` over the scheduled leads); the panel does not claim to
replay every gate for every message.

### 3.4 Lead timezones (`app/services/lead_timezone.py`) — follow-up fix

**Problem found in review:** nothing wrote `enrichment_json.timezone`, so every
lead's local time was the deployment default (UTC) — for best-time scheduling
*and* for the 09:00–17:00 sending-hours guard (a Chicago prospect could be
emailed at 03:00 their time).

**Resolver** (deterministic, offline): (1) the zone recorded on the lead;
(2) the lead's own location — person first (top level, the Apollo match
response's `person`, the sourcing row), then their organization: an IANA
`time_zone` the provider reports; else a single-zone country (≈70 countries;
countries with small outlying zones — Spain/Canaries, Portugal/Azores,
Chile/Easter Island, NZ/Chatham — use the mainland zone); else a state /
province table for the **US, Canada, Australia and Brazil** (each state's
primary zone: a split state such as Texas, Florida, Indiana, Kentucky,
Tennessee, Michigan, Nebraska, the Dakotas, Kansas, Idaho or Oregon takes the
zone most of its people live in). A multi-zone country without a state
(US with no state, Mexico, Russia, Indonesia…) stays unresolved; so does a
state without a country. (3) **Fallbacks, never written onto the lead:** the
strategy's target region (its ICP `locations`, e.g. "Texas, US"; the zone most
of them resolve to, ties to the first listed), then the account's timezone
(its earliest active calendar availability — the same rule as daily send
approval), then `send_window_timezone` (UTC).

**Written** at enrichment (`lead_tasks.enrich_leads_impl` → `record()`) as
`timezone` + `timezone_source` (e.g. "location: Alberta, Canada"); **resolved
lazily on read** for leads enriched before this (no data migration; a read
never writes). Fallback resolution is cached per strategy per session for
10 minutes.

**Compliance review (needs founder/legal confirmation).** This changes *when*
sends go out: the sending-hours guard now opens in the prospect's own business
hours instead of UTC's. Sends move; none are added or removed, and every other
gate is unchanged. Checked:
* `compliance_region.lead_region` (open-tracking ban for EU/UK, the region
  notice, the regime in the per-send audit, compliance-rule resolution) uses
  the lead's **country** first and the stored `timezone` only when no country
  is known. `record()` stores only a zone derived from the lead's own location,
  so it always agrees with the country; fallback zones are **never stored**, so
  an account in Dublin cannot make an unknown lead look like an EU lead, nor a
  Texas ICP make it look American (tested).
* Compliance-rule quiet hours (`compliance_rules` send windows) are applied in
  the lead's zone — now the real one (tested: an EU 10–12 rule for a Berlin
  lead defers 09:30 CET to 10:00 CET).
* DST: windows are computed by `zoneinfo` on the lead's zone (tested in winter
  and summer for Berlin and New York).

### 3.5 Manual launch lawful basis (`app/services/launch_consent.py`) — follow-up fix, LEGAL GUARD

`POST /sequences/{id}/enroll` now requires `lawful_basis_confirmed: true` and
the current `lawful_basis_text_version` (`launch-lawful-basis-2026-10-11`;
text at `GET /launch/lawful-basis`). Missing, false or an old version → **422**
with a plain message naming the fields and the version; nothing is enrolled
and nothing recorded. Same mechanism as the Autopilot opt-in (versioned text,
exact text recorded) but its own wording, because the person confirms after
reading the list ("I have read the list of leads and I confirm I may lawfully
contact each of these people on this sequence's channels (CAN-SPAM, GDPR, CASL,
PDPA as they apply). This sends real messages from my connected accounts.").
The Autopilot text says the opposite (confirmed before the list exists), so
the two are deliberately different texts.

Recorded only once the launch gates pass, in the same commit as the
enrollment: `compliance_audit_log` (channel `launch`, decision
`launch_lawful_basis`, checks: sequence, strategy, acting person, text version,
exact text, lead statuses, outcome, enrolled count — kept on erasure) and
`security_audit_events` (`sequence.launch_lawful_basis`). An SDR's request for
manager approval records the SDR's confirmation and carries it in
`approval_payload_json`; a request stored before this guard has none, so the
approving manager must confirm (optional body on `POST /sequences/{id}/approve`,
else 422).

The field is optional in the request schema on purpose, so an old client gets
the guard's own explanatory 422 rather than a bare "field required". The web
app now fetches the text from the server and sends the version it showed. The
Python SDK has no enroll method (checked `sdk/src`), so it needs no change.

**Tests:** `tests/test_launch_lawful_basis.py`, its own file, for sealing.
Other suites run with the guard off through the conftest seam
`launch_lawful_basis_off` (`launch_consent.enforced()`; always True in
production) — the `daily_send_approval_off` pattern — because sealed suites
(`test_send_path_guards.py`, `test_deliverability_autopilot.py`) launch with
`json={}` to test other gates and cannot be edited. The guard file asserts the
production default is on.

### 3.6 Review fixes (2026-10-12, reviewer on d1f3b5c / 17eb791)

| Item | Fix | Test (failed before the fix) |
|---|---|---|
| M1 false "Running" | Unreachable leads leave the pool (`unreachable_json`); a channel is `launched` only with > 0 enrollments; gates run only for the leads left | `test_autopilot_review_fixes.py::TestM1Unreachable` |
| M2 spend refusal | forecast before the ICP call; ICP cached in `icp_json`; `retry_after` = next 00:00 UTC; notified once | `TestM2SpendRefusal` |
| M3 chain publish | `chain_attempts` / `chain_published_at`; a failed or stalled (60 min, no lead) publish is re-published; after 3 attempts the batch fails and the owner is notified (`chain_failed`) | `TestM3ChainPublish` |
| M4 diagnostics | real rules: `no_send_window`, `consent_required`, the resolved window, the rule cap; the docstring no longer overclaims | `test_send_diagnostics.py::TestComplianceRules` |
| M5 daily approval | 409 at opt-in (`approval_gap`); sweep → `paused` + notify; `send_message_impl` holds Autopilot messages (`autopilot.send_hold` → `deferred_autopilot_needs_daily_approval`, retried hourly, fails closed) | `TestM5DailyApproval` |
| M6 own batch only | `batch_ids_json`, `eligible_json`; no champion, hand-added or flipped leads; the text says so | `test_autopilot_launch.py::test_only_its_own_batch_is_ever_enrolled` |
| M7 learning cost | Redis cache via a 6-hourly task; bounded reply query; index `ix_messages_status_sent_at`; warm placement ≤ 1 statement | `TestM7Learning` |
| M8b guard with best-time ON | `tests/test_best_time_window_guard.py` (for sealing): property test; send-path deferral and enrollment placement inside the permitted and rule windows in 8 zones incl. DST; the sealed window-start scenario in production | that file |
| Hard override | no fallback outside it; 422 when it never overlaps the resolved window; enrollment uses the resolved window; enforced again at send time (`override_hold`) | `TestOverrideIsHard` |
| Claim heartbeat | `_heartbeat` before and after sourcing; a lost claim stops | `TestClaimHeartbeat` |
| Plan only when used | `send_time.plan_wanted` | `TestPlanOnlyWhenUsed` |
| WhatsApp template | chosen by the person; waits with a reason if none | `TestWhatsAppTemplate` |
| PUT /best-time | owner/manager only, no API keys; 202 + background reslot | `TestBestTimePut` |
| Chain queue | same routing as manual Find leads (no queue override) | `TestChainQueue` |
| Gmail token | `gmail_token_invalid`, not "ready" | `test_send_diagnostics.py::TestGmailToken` |
| UI copy | the resolved zone with its source; 202 toast; template selector; approval gap; unreachable count | `frontend/src/tests/autopilot.test.ts` |

**Consistency with the sealed window-start test.** The sealed
`test_compliance.py::TestSendWindow::test_outside_hours_defers_to_window_start`
runs with best-time OFF (conftest `best_time_scheduling_off`) and pins 09:00.
In production (ON) the same deferral lands at 09:00–09:29 the same morning —
inside the window, never before its start; the send path re-checks the window
at send time. `tests/test_best_time_window_guard.py` pins that. Measured with
the reviewer's plugin forcing best-time ON over the 47 send-path test files:
1,523 pass and 5 fail, every one a test that pins the exact window start.

## 4. Non-goals

* No new send path, no bypass of any gate (daily approval stays ON by founder
  decision; Autopilot waits for it every day).
* No AI phone calls from Autopilot (calls need recorded consent and an admin
  switch — a person decides).
* No cold WhatsApp to leads without a recorded opt-in.
* No automatic sign-off of a failed verification.
* Not changing auto follow-ups, the M8 Analytics send-time recommender or the
  per-campaign smart send time.

## 5. Data model — migration `0087_autopilot_launch`

`autopilot_launches` (one row per strategy, `UNIQUE(strategy_id)`):
`id`, `strategy_id` (FK strategies CASCADE), `enabled`, `state`,
`state_reason`, `confirmed_by_user_id` (FK users SET NULL),
`confirmed_at`, `text_version`, `confirmed_text`, `batch_id` (FK lead_batches
SET NULL), `sequences_json` (`{channel: sequence_id}`), `channels_json`
(`{channel: {"state", "reason", "enrolled"}}`), `notified_json`
(`{reason_key: iso}`), `claim_token`, `claimed_at`, `launched_at`,
`last_checked_at`, `created_at`, `updated_at`, and (review fixes)
`batch_ids_json`, `eligible_json`, `unreachable_json` (`{lead_id: reason}`),
`icp_json`, `retry_after`, `chain_published_at`, `chain_attempts` (NOT NULL,
default 0), `whatsapp_template_id` (FK whatsapp_templates SET NULL,
`fk_autopilot_launches_whatsapp_template_id_whatsapp_templates`, 61 chars).
Index `ix_messages_status_sent_at` on `messages(status, sent_at)` for the
learning query. Constraint names ≤ 63 chars (checked in the migration test).

`strategies.send_time_plan_json` (JSON, NULL), `strategies.send_time_override_json`
(JSON, NULL).

JSON (not JSONB) and `sa.Uuid` so it runs on SQLite and PostgreSQL. Downgrade
drops the index, the table and the two columns: the opt-in rows and plans are lost; the
opt-in **audit** rows in `compliance_audit_log` stay.

Account export: `autopilot_launches` → `["strategy_id", "product_id",
"user_id"]`. Account erasure: **DELETED** (the decision's proof stays in
`compliance_audit_log`, KEEP_PROOF, like `daily_send_approvals`).

## 6. API

| Method | Path | Notes |
|---|---|---|
| GET | `/autopilot/lawful-basis` | the confirmation text, version and label (for the new-strategy wizard) |
| GET | `/strategies/{id}/autopilot` | state, channels, opt-in record, the lawful-basis text + version, `available` (flag) |
| PUT | `/strategies/{id}/autopilot` | `{enabled, lawful_basis_confirmed, lawful_basis_text_version}`; 422 without confirmation, 409 flag off or daily send approval not covering every channel, 403 SDR / API key |
| PUT | `/strategies/{id}/autopilot/whatsapp-template` | `{whatsapp_template_id}` (or null); 422 unless APPROVED with an opt-out; 403 SDR / API key |
| POST | `/products/{id}/strategies` | optional `autopilot` object, same rules, validated before anything is created |
| GET | `/strategies/{id}/best-time` | per channel: windows, source, reason, timezone note, override |
| PUT | `/strategies/{id}/best-time` | override `{days, start, end}` → 202 `{..., rescheduling}` (background reslot); 422 invalid or never overlapping the resolved window; `{clear: true}` → 200; 403 SDR / API key |
| GET | `/strategies/{id}/send-diagnostics` | 3.3 |

(`/best-time`, not `/send-time`: `GET/PUT /strategies/{id}/send-time` already
belongs to the per-campaign smart send time in `app/api/revenue_analytics.py`.)
Personal API keys are refused (403) when turning Autopilot on: confirming a
lawful basis is a person's decision, like approving daily sending.

Every route: `get_current_user` + ownership (404 for another account's
strategy). No model call in any request handler (the opt-in endpoint only
enqueues).

## 7. UI

* New-strategy wizard, review step: an **unticked** "Autopilot" checkbox; when
  ticked, the lawful-basis text and a second **unticked** confirmation
  checkbox; the Launch button stays disabled until both or neither.
* Strategy page: **Autopilot** card (switch with the same confirmation; state
  in plain words; per-channel status and what to connect; the daily-approval
  gap; how many found leads cannot be contacted and why; the WhatsApp
  template selector, approved templates only, "None chosen" by default), **Best time to
  send** card ("Messages go out at Tue–Thu 09:00–11:00 in each prospect's local
  time — why …"; where each lead's local time comes from, by source; override
  form; the save toast says how many messages are being moved; clear), **Why isn't this sending?** panel.

## 8. Tenancy

Every query is owner-filtered: strategy ownership via product → user (404),
learning rows joined lead → strategy → product.user_id = owner, readiness via
the owner's Gmail/LinkedIn rows, diagnostics counts scoped to the strategy.
Tested: another account's strategy is 404 on every route; another account's
sends never influence the learned slots.

## 9. Compliance review (needs founder/legal confirmation throughout)

* **CAN-SPAM (15 U.S.C. §7701 et seq.)** — opt-out regime: commercial email
  needs accurate headers, sender identity/address and a working unsubscribe,
  which every email already carries (sequence_engine.build_compliant_email,
  F03 one-click headers). Autopilot changes *when* a person launched, not the
  message.
* **GDPR (Art. 6(1)(f) legitimate interests, Art. 14 information duty, Art. 21
  right to object) and UK/EU ePrivacy rules (e.g. UK PECR reg. 22, corporate
  subscribers)** — whether B2B cold email has a lawful basis depends on the
  recipient and member state; the existing region notice and suppression are
  unchanged. The Autopilot confirmation is the user's **own** statement that
  they have a lawful basis for the people Autopilot finds; it does not create
  one. The text says plainly that they confirm **before** seeing the list,
  and that they can review leads (and remove them) before approving each day's
  sending.
* **CASL (S.C. 2010, c. 23, s. 6 and s. 10(9)(b) implied consent for
  conspicuously published business addresses)** — unchanged region handling.
* **PDPA (Singapore)** — unchanged region handling.
* **WhatsApp Business Messaging Policy / Meta** — opt-in required: Autopilot
  enrolls WhatsApp only for leads with a recorded opt-in, template steps only.
* **LinkedIn User Agreement (automation)** — unchanged: LinkedIn automatic
  sends still need the daily approval with the risk acknowledgement.
* **New legal/safety guards:** the server-side lawful-basis requirement for the
  Autopilot opt-in (422 + audit) and for the manual launch / approval (3.5,
  `tests/test_launch_lawful_basis.py`). Reported to the orchestrator for sealing.
* Lead timezones (3.4) change when sends go out — see the compliance review
  there.

## 10. AI cost and budget impact

Per Autopilot strategy: one brief-generation call per email/LinkedIn sequence (~6–10k input tokens of
research excerpt, ≤ 2k output) + per strategy one send-time plan call (~2k in,
≤ 1k out). At the configured $3/$15 per Mtok that is roughly $0.05–0.07 per
strategy, both account-capped (refused at the daily limit → fixed briefs /
priors, never a failure). Sourcing spend is the existing per-lead provider
cost under F07. No per-message model call is added.

## 11. Test plan (all offline, deterministic)

`tests/test_send_time.py`, `tests/test_autopilot_launch.py`,
`tests/test_send_diagnostics.py`, `tests/test_autopilot_launch_migration.py`,
`tests/test_autopilot_review_fixes.py` (the reviewer's probes P1–P8, ported),
`tests/test_best_time_window_guard.py` (guard, for sealing; the reviewer's
property test), frontend `src/tests/autopilot.test.ts`:

* best time: priors per channel/industry; timezones (New York, Singapore);
  DST spring-forward/fall-back weeks; weekends skipped; window intersection;
  horizon fallback; deterministic spread inside the window; learning blend
  (below threshold = prior; above = data moves the slot; smoothing); override
  hard window and re-placement; plan validation and fallback on a bad model
  answer; flag off = old scheduling.
* autopilot: happy path end to end with fakes (pipeline complete → plan →
  verified → sourcing chain with fake source/verifier → sequence → enrollment
  → messages at the best slot → held by daily approval → approved → sent
  through the real `send_message_impl`); idempotency (advance twice, sweep
  twice); prerequisites missing → partial launch + email + push + in-app
  state → Gmail connected → resumes; NEEDS_HUMAN_REVIEW waits and notifies;
  lawful basis required (422) and audited (compliance_audit_log +
  security_audit); SDR 403; flag off = nothing happens; tenancy.
* diagnostics: every reason pinned to its gate.
* migration: table matches the model, names ≤ 63 chars, revision chain.

## 12. Success metric (measured, never promised)

* Share of VERIFIED Autopilot strategies with a first message transmitted
  within 24 h of the owner's first daily approval after verification.
* Median time from `VERIFIED` to first transmitted message, Autopilot vs
  manual launches.
* Reply rate of best-time-placed messages vs the account's pre-feature
  baseline (same channel), only once ≥ 30 sends per arm exist.

## 13. Unverified

* The send-time priors come from general knowledge of published industry
  studies, **not re-checked against those studies** for this change, and
  LinkedIn's are measured for posts, not DMs. Priors, not promises.
* The model's send-time refinement and brief generation were exercised only
  with fakes; their real output quality is unmeasured.
* No live Gmail / Unipile / Meta / Apollo run; readiness checks read the rows
  those integrations write.
* A strategy whose pipeline finished before Autopilot was turned on, or before
  its first sequence was active, has no send-time plan (`plan_wanted` was
  false then): it uses the priors and learned rates until the pipeline is
  re-run. Deliberate (no speculative model spend), but a gap.
* Lead timezones: the state tables give each state's PRIMARY zone (split
  states are approximated); Apollo's exact location field names (`country`,
  `state`, `time_zone`, organization location) are read as documented by the
  existing code and fixtures, not re-verified against a live Apollo response.
* Every statutory reading in section 9: **needs founder/legal confirmation**.

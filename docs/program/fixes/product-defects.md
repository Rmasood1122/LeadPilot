# Product defects fixed from the help-center discoveries

Branch `claude/product-defects` (based on master hotfix d43fa43). Source list:
[`docs/program/help-center-discoveries.md`](../help-center-discoveries.md).
Founder instruction: "fix every open gap". Each fix was verified against the
code first, has a test written to fail before the fix (pre-fix state recorded
below), and updates the help-center article that described the old behaviour
in the same change (tests/help_center stays green).

Not in this branch, by instruction: #17 (VIP send-review rule), #25/#26/#27
(product / single-tenant decisions; password reset is another branch), and the
items not assigned here (#3, #6, #7, #8, #9, #12, #13, #14, D1-D7).

Legal posture: where a fix touches a legal duty, the rule relied on is named
and marked **needs founder/legal confirmation**. Nothing here is a settled
legal reading.

## Summary

| # | Fix | Tests | Articles |
|---|---|---|---|
| 1 | Strategy detail page reads the real `StrategyStatusOut` shape | `frontend/src/tests/strategyDetail.test.tsx`, `tests/test_strategy_status_fixture.py` | 04, 05 |
| 2 | Outcomes carry `strategy_id` and `variant` on every write path; `default_variant` is read back | `tests/test_outcome_attribution.py` | 17 |
| 4 | WhatsApp "+ New draft" asks for one description per placeholder | `frontend/src/tests/templateEditor.test.tsx` | 10 |
| 5 | Phone gate only enforced when a code can be delivered; loud admin warning otherwise | `tests/test_phone_verification_delivery.py`, `frontend/src/tests/configWarnings.test.tsx`, `frontend/src/tests/identity.test.ts` | 03, 22, 23 |
| 10 | Network page delete button shown on every plan while connections are stored | `frontend/src/tests/networkDelete.test.tsx` | 11, 21 |
| 11 | GDPR erasure clears booking likelihood, conversion factors and every `fpta_*` field | `tests/test_gdpr_erasure_scores.py` | 21 |
| 15 | Spending-limit 429s show the server's sentence on Resume, Re-verify, sourcing, launch | `frontend/src/tests/spendLimit429.test.ts` | 04, 27 |
| 16 | Gmail OAuth callback redirects to Settings like Slack/HubSpot/Salesforce | `tests/test_gmail_callback_redirect.py`, `frontend/src/tests/ecosystem.test.ts` | 09 |
| 18 | Plan advertising = enforcement (multi_variate, analytics history enforced; multiplier removed; steps capped at 20) | `tests/test_plan_advertising.py` | 17, 22 |
| 19 | Dead `EXECUTING` guards replaced: delete refuses a really-sending campaign | `tests/test_strategy_executing_guard.py` | (21, 25 now true) |
| 20 | `upgrade_to` comes from one table (starter -> growth) | `tests/test_plan_advertising.py` | - |
| 21 | Campaign page uses the real bounce threshold (">", compliance-lowered) and caps | `tests/test_campaign_lowered_limits.py`, `frontend/src/tests/campaignBounce.test.ts` | 09, 29 |
| 22 | Onboarding step links point at real pages; unmounted checklist deleted | `tests/test_onboarding_step_links.py` | - |
| 23 | Inbox nav badge wired to `/inbox/count`; Pipeline Health card on the strategy page | `frontend/src/tests/inboxBadge.test.tsx`, `frontend/src/tests/pipelineHealthCard.test.tsx` | 13, 18 |
| 24 | Dead code with false text deleted (kanban `LeadDrawer.tsx`, `PullToRefresh.tsx`, `optin_url()`) | `tests/test_dead_code_false_text.py` | 26 (source list) |
| 28 | LEGAL GUARD: template body must contain STOP; suppressed-contact error no longer promises a re-opt-in | `tests/test_whatsapp_template_optout.py` | 10 |

## Details

### #1 Strategy detail page (H)

Verified: `GET /strategies/{id}` returns `progress: PipelineProgress[]` (one per
pipeline, each with 8 `phases` carrying `title`), and `verification` is the raw
attempt log (`pass_no, key, name, attempt, result, fix_description,
fix_applied, ...`, app/verification/loop.py::_log_attempt). The page treated
`progress` as flat phase rows with `steps`, and read `attempts`/`fix`, which the
server never sends.

Fix: `frontend/src/app/(app)/strategies/detail/page.tsx` renders one card per
pipeline with the 8 named phases from the API; `frontend/src/lib/strategyDetail.ts`
collapses the attempt log to one row per check (latest run), with the attempt
count, the applied fix or the failure reason, and manual sign-offs. The
`PhaseProgress`/`VerificationPass` types now mirror the Pydantic schema.
Per-step outputs are served by no endpoint, so the page no longer promises
them ("compiled into the documents"); exposing them would be a new endpoint.

Fixture: `frontend/src/tests/fixtures/strategy-status.json` was generated from
a live call to the endpoint; `tests/test_strategy_status_fixture.py` fails if
the API and the fixture ever differ in shape (keys and value types at every
level) or the fixture stops validating against `StrategyStatusOut`.
Regenerate with `STRATEGY_FIXTURE_WRITE=1`.

Contract change in an existing test: `verificationReview.test.ts` built rows
with `attempts: 1`, a field the server never sends; it now uses `attempt: 1`.

### #2 Learning loop and A/B data (H) -- confirmed

Confirmed with a test before fixing: after real sends the outcome rows had
`strategy_id = NULL`, `ab_testing._load_variant_stats` counted 0 sends, and a
reply's outcome had neither column.

Fix (the robust option): `app/db/outcome_attribution.py`, a SQLAlchemy
`before_flush` listener registered from `app/db/models.py`, fills both columns
on every NEW `Outcome` when the writer left them empty: strategy from the lead
(including a lead added in the same flush); variant ONLY from the outcome's own
message (`message_id`). An event not linked to its message (a bounce or reply
matched only by address) gets no variant -- after review M5 the earlier
"variant the lead was sent most recently" fallback was removed, because a
step-1 bounce arriving after step 2 went out would be credited to the wrong
variant. Explicit values are never overwritten; rows without a lead (system
events) are untouched; insert-time only, so outcomes stay immutable.
Attribution never breaks a commit: each outcome's resolve is wrapped, a
failure is logged and the outcome is written as given (review M4; tested with
a legacy list-shaped `meta_json` and a resolver that raises).

Audit trail (review M5). The tamper-evident activity trail
(`app/services/audit_trail.py`) hashes a payload per outcome at insert.
Choice: **leave the payload unchanged** -- it records only what the writer
supplied. A variant filled in by attribution is not added to the hashed payload
(`outcome_attribution.variant_was_filled()`), so the chain never attests a
value its writer did not record, and payloads are byte-identical to what the
same write produced before this change. The backfill touches `outcomes` only;
sealed audit records are never rewritten.

A/B auto-promotion is now **off by default** behind the system setting
`ab_auto_promotion_enabled` (`app/services/system_settings.py`; checked first
thing in `learning_tasks.auto_promote_winners`). Reasons: a promotion is
permanent (an `ab_promoted` marker, at most once per strategy, never
revisited), and step variants are labels on different sequences, not
randomised arms -- leads are not randomly assigned to A or B, so a "winner" can
reflect who was enrolled where rather than the message. With attribution now
feeding real data, leaving the sweep on would start promoting on that basis.
Turning it on is a founder/admin decision.

`strategies.default_variant` (written by `auto_promote_winners`, read by
nothing): now read back -- the CRM campaigns dashboard marks the promoted
variant ("promoted winner") when filtered to that strategy. It still does not
change what is sent (one variant per step number); article 17 says so.

Backfill: `scripts/backfill_outcome_attribution.py` -- dry run by default
(nothing written), prints a warning header and the mode, `--batch-size N`
(default 500, one commit per batch), one progress line per batch, `--apply` to
write. Same rules as the listener (variant only from the linked message).
Idempotent. **Founders decide whether and when to run it** (production data;
take a backup first; not run here).

Limitation: `auto_promote_winners` uses PostgreSQL-only SQL (`array_agg`,
`gen_random_uuid`), so the sweep itself is not exercised offline; the tests use
the statistics functions it calls and prove the flag stops it before any
outcome query.

### #4 WhatsApp "+ New draft" (H)

The editor now lives in `frontend/src/components/campaigns/TemplateEditor.tsx`
(moved out of the page so it can be tested). For each `{{n}}` typed it shows a
"What goes in {{n}}?" field; Save is disabled until each has a description and
the body contains STOP (#28). Create and edit send exactly one description per
placeholder in the body (`frontend/src/lib/whatsappTemplate.ts`). Edits start
from the saved descriptions.

### #5 Phone verification undeliverable (H)

Chosen option: **the gate follows deliverability, with a loud warning, and
never fails open on a misconfiguration** (revised after review M6).
`identity.sms_transport_state()` classifies `SMS_PROVIDER`:

| Configuration | Gate | Reported |
|---|---|---|
| `twilio` with all three `TWILIO_*` | ON | nothing |
| `memory` outside production (test suite) | ON | nothing |
| `console` or empty, **production** | OFF | admin warning `phone_verification_undeliverable` + startup WARNING |
| `console` or empty, not production | ON | nothing (local dev sets `REQUIRE_PHONE_VERIFICATION=false`) |
| set but broken: unknown name (typo), `twilio` missing a key, `memory` in production | **ON** | admin warning `sms_provider_misconfigured` + startup **ERROR** |
| `REQUIRE_PHONE_VERIFICATION=false` | OFF | nothing |

When the gate is off, `/onboarding/verification` and `/auth/me` report
`phone_required: false` (the Shell no longer sends users to the phone step).
Warnings are served by `GET /admin/config-warnings` and shown as a banner on
every admin page, naming the exact env vars to fix.

Why not fail the boot: production runs `console` today (render.yaml sets no
`SMS_*`/`TWILIO_*`), so the next deploy would take the API down; and the sealed
`tests/test_production_guard.py` defines a "fully configured production"
without SMS settings that must keep starting. A correctly configured
deployment gates exactly as before (tested), and a broken one now stays gated
(no silent fail-open).

**Founder action:** decide `REQUIRE_PHONE_VERIFICATION` for production. Either
configure Twilio (`SMS_PROVIDER=twilio`, `TWILIO_ACCOUNT_SID`,
`TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`) so the gate is real, or set
`REQUIRE_PHONE_VERIFICATION=false` deliberately. Until then production runs
without the phone gate and its anti-abuse purpose (throwaway accounts) is not
served; the admin banner says so.

### #10 Network delete (M, data rights)

The count and **Delete my uploaded connections** moved out of the Growth-only
upload card; they show on every plan while connections are stored
(`DELETE /linkedin-network` was never plan-gated).

### #11 GDPR erasure scores (M)

`_gdpr_erase_lead` (app/api/leads.py) now also clears `ai_booking_likelihood`,
`conversion_factors_json` and every `fpta_*` field (sub-scores, overall,
reasons, method, scored_at). Change kept to those lines (another branch edits
the same function). Basis: scores and their reasons are derived from the
erased personal data, so they are personal data (GDPR Art. 4(1)) within the
erasure (Art. 17) -- **needs founder/legal confirmation**.

### #15 429 messages (M)

`ApiError` now carries `code` (`detail.error` of a structured refusal).
`tooManyRequestsMessage()` returns the server's own sentence for
`daily_ai_limit_reached` and `monthly_spend_cap_reached`; a plain rate limit
still says "Too many requests...". Used by `resumeStrategyErrorMessage`
(Resume, Re-verify, sign-off) and `sourceErrorMessage`/`launchErrorMessage`.

### #16 Gmail OAuth callback (M)

`GET /integrations/gmail/callback` redirects (303) to
`/settings?tab=integrations&gmail=connected|error[&reason=...]` via the shared
`frontend_redirect`, for every outcome, including the previously unhandled
"no refresh_token" case (was a 500) and, after review L6, any other
`store_tokens` failure (logged; the redirect carries a generic reason, not the
internal error). Tokens never appear in the URL. The
settings page toast now knows "Gmail". Contract change in an existing test:
`ecosystem.test.ts` asserted `gmail=connected` produced no toast; it now
produces "Gmail connected".

### #18 Plan advertising vs enforcement (M) and #20 upgrade_to (L)

| Item | Decision | Why |
|---|---|---|
| `multi_variate` | Enforced on `GET /strategies/{id}/mv-results` | The endpoint is the multi-variate results; it checked `ab_testing`, so Starter and Pay-per-meeting (`multi_variate: False`) got it. Behaviour change for those API users; no UI calls it (see out-of-scope). |
| `analytics_history_days` | Enforced on the analytics time series (`GET /strategies/{id}/analytics` `series`; new `history_days` field); the Analytics page chart titles say "(last N days)" / "(all history)" (review L5) | Cheap, and the pricing page sells "N-day analytics history". Totals and the variant table are not windowed (article 22 says so). |
| `api_rate_limit_multiplier` | Removed from PLANS, the price list and the frontend types | Never read. Applying it would loosen the cost-protecting rate limits (e.g. 2 strategies/hour) with no stated intent; not shown in the UI. |
| "Unlimited" sequence steps | Plans now say 20 (`SEQUENCE_STEP_CAP`, shared with the API schema) | The API never accepted more than 20. |
| `starter.upgrade_to` | Every plan's `upgrade_to` comes from `_PLAN_UPGRADE_PATH` | One table; "pro" is no longer sold. |

Contract changes in existing tests: `test_plan_enforcement.py::test_quantity_check`
asserted Scale accepts 10,000 steps (now 20; unlimited is still asserted on a
limit that is unlimited); `pricing.test.ts`'s fixture dropped the removed field;
`test_m5_backend.py::test_analytics_series_and_variants` seeds outcomes at a
fixed date now more than 30 days old, so it runs on a plan with unlimited
history (it tests the response shape; the window is tested separately).

### #19 StrategyStatus.EXECUTING (M)

Assigning EXECUTING was rejected: lead sourcing (`app/api/leads.py`), sequence
creation (`app/api/sequences.py`), Quickstart and the worker all require
`status == verified`, so marking a strategy executing would lock those out.
Instead the dead guards were replaced: the delete guard now checks the real
condition (`_campaign_is_sending`: campaign active and a lead still enrolled,
active or out-of-office-paused) -- which is what articles 21 and 25 already
promised. After review L3 the delete is also refused while any message of the
strategy is SENDING (a send task is transmitting it), even with the campaign
paused. The resume guard was removed because resume already refuses
`verified`/`needs_human_review`, where a sending strategy is. The enum value
stays (stored data, SDK). Contract changes in `tests/test_strategy_delete.py`:
the cascade test now pauses the campaign first; the "live campaign" test uses a
real enrolled campaign instead of setting the never-assigned status by hand.

### #21 Bounce banner and caps (L)

`GET /strategies/{id}/campaign`: `bounce_pause_threshold` is the threshold the
pause uses (`compliance_rules.bounce_threshold`); `daily_cap_today` applies the
workspace rule cap for all regions (`compliance_rules.campaign_daily_cap`) and
the mailbox-health cap, as the send path does (WhatsApp: the rule cap). The CRM
campaigns dashboard reports the same threshold. The banner reads "X% is above
the Y% limit" and the rate turns red only when strictly above. A
region-specific rule can still lower the cap for some leads (stated in article
09). The email-verification bounce report still shows the baseline (article 29).

### #22 Onboarding checklist (L)

`OnboardingChecklist.tsx` was never mounted (no import, no dynamic import) and
nothing marks onboarding steps complete, so rendering it would show "0 of 7"
forever: deleted. Stale references removed after review L2: the parked
`frontend/integration-pending/(dashboard)/page.tsx` no longer imports it (and
its README no longer says it exists), and `LAUNCH_CHECKLIST.md` §9's "OnboardingChecklist
visible for new user" item is marked SUPERSEDED with the reason. The public
`GET /onboarding/state` keeps working; its links
now point at real pages (tested against the Next.js app directory).

### #23 countInbox and Pipeline Health (L)

Inbox nav entry shows the waiting count (`InboxBadge`, refreshed every minute,
"99+" cap). A **Pipeline health** card (score, band, message, four parts) shows
on verified strategies' pages.

### #24 Dead code with false text (L)

Proved dead (code-quality discipline): bare names and string forms searched
across `frontend/src`, `app`, `tests`, `scripts`, `sdk`, docs; no dynamic
imports; the pipeline page defines its own `LeadDrawer` (not an import). Deleted
`frontend/src/components/kanban/LeadDrawer.tsx` (its toast claimed "Lead and all
associated data deleted"), `frontend/src/components/ui/PullToRefresh.tsx`,
`app/api/whatsapp_optin.py::optin_url` (docstring claimed use by email
footers). `docs/README_M7_CHUNKS_2_3.md` no longer lists PullToRefresh as built
(review L2). `make_optin_token` stays (live opt-in page; tests mint tokens).
Verified by tsc, eslint, full vitest and the full pytest suite.

### #28 WhatsApp opt-out instruction -- LEGAL GUARD

Revised after review M1/M2. A **MARKETING** template must carry an opt-out
*instruction*, not merely the word STOP (`app/services/whatsapp_templates.py`
`_OPT_OUT_INSTRUCTION`, mirrored in `frontend/src/lib/whatsappTemplate.ts`):

    \b(reply|text|send|respond|message)\b[^.\n]{0,25}\bSTOP\b      (verb case-insensitive)
    \bSTOP\b[^.\n]{0,25}\b(opt[ -]?out|unsubscribe)\b             (opt-out words case-insensitive)

STOP in capitals (the keyword `app/api/webhooks_whatsapp.py::_is_opt_out` acts
on). "NON-STOP deals", "BUS STOP", a URL ending /STOP and a bare "STOP." are
refused. UTILITY templates (the only other category the code supports;
AUTHENTICATION is never used) are not required to carry it. Checked on create,
on edit (including a category change to marketing), right before submission to
Meta, and **again at send time**: an approved marketing template without it
(e.g. approved before this rule) fails closed -- the message goes to
NEEDS_TEMPLATE with the reason, a `blocked_no_opt_out` compliance audit row is
written, and nothing is sent (`outreach_tasks.send_message_impl`, result
`needs_template_no_opt_out`). The AI drafter is asked for exactly "Reply STOP
to opt out." (STOP exempt from its no-ALL-CAPS rule); a marketing candidate
without an instruction gets that sentence appended instead of being dropped
(the person still reviews it before submission).

Known limitation (founder decision): the instruction is recognised in English
only, so a template in another language needs an English opt-out line as well.

Basis (**needs founder/legal confirmation**): WhatsApp Business Messaging
Policy (honour opt-out requests); CASL s.6(2)(c) and s.11 (unsubscribe
mechanism in commercial electronic messages to Canadian recipients); GDPR
Art. 21(2)-(3) (right to object to direct marketing).
`tests/test_whatsapp_template_optout.py` is a legal-guard test file: the
orchestrator should add it to `evals/compliance_testset.yaml` (sealed; not
edited here).

`record_opt_in` no longer tells the sender a suppressed contact "can
re-initiate (e.g. by messaging you first)": no code path lifts a suppression,
so it now says the suppression cannot be lifted from the app.

## Review round 1 (independent review of 049d8b3)

| Finding | Fix (file:line at time of writing) | Test | Pre-fix state |
|---|---|---|---|
| M1/M2 opt-out = instruction, marketing only, send-time, generator | `app/services/whatsapp_templates.py:60` (pattern), `:75` (`validate_opt_out`), `:189/:241/:277` (create/edit/submit), `:392` (prompt), `:455` (append); `app/workers/outreach_tasks.py:371-387` (send-time, `needs_template_no_opt_out`); `frontend/src/lib/whatsappTemplate.ts:16,55`; `frontend/src/components/campaigns/TemplateEditor.tsx:33` | `tests/test_whatsapp_template_optout.py`, `frontend/src/tests/templateEditor.test.tsx` | 9 failed / 13 passed; vitest 3 failed |
| M4 attribution never breaks a commit | `app/db/outcome_attribution.py:126` | `test_outcome_attribution.py::test_attribution_never_breaks_a_commit` | in the 6 failed below |
| M5 variant only from own message; same-flush lead | `app/db/outcome_attribution.py:81,104` | `test_an_event_without_its_message_gets_no_variant`, `test_an_event_with_its_message_gets_that_messages_variant`, `test_lead_added_in_the_same_flush` | 6 failed / 4 passed (whole file) |
| M5 audit payload unchanged | `app/services/audit_trail.py:124` | `test_audit_trail_payload_is_what_the_writer_recorded` | payload gained `'variant': 'A'` |
| M5 auto-promotion flag | `app/services/system_settings.py:209`, `app/workers/learning_tasks.py:217` | `tests/test_ab_auto_promotion_gate.py` | 2 failed (no flag; sweep queried outcomes) |
| M5 backfill dry-run/batch/progress/warning | `scripts/backfill_outcome_attribution.py:36,43`; `app/db/outcome_attribution.py:131` | `test_backfill_fills_old_rows_once`, `test_backfill_script_is_a_dry_run_by_default` | SystemExit 2 (`--batch-size` unknown) |
| M6 no silent fail-open | `app/services/identity.py:83` (`sms_transport_state`), `:98`, `:133` | `tests/test_phone_verification_delivery.py` | 5 failed / 11 passed |
| L1 fixture shape, every element | `tests/test_strategy_status_fixture.py:33` | `test_shape_compares_every_list_element` | 1 failed with the old `_shape` |
| L2 stale references | integration-pending page + README, `docs/README_M7_CHUNKS_2_3.md:16`, `LAUNCH_CHECKLIST.md:105` | `tests/test_dead_code_false_text.py` (2 new) | 2 failed |
| L3 delete while SENDING | `app/api/strategies.py:497` | `test_strategy_executing_guard.py::test_a_message_mid_send_blocks_the_delete_even_when_paused` | 1 failed (200) |
| L5 chart label | `frontend/src/lib/analyticsHistory.ts`, `frontend/src/app/(app)/analytics/page.tsx:50` | `frontend/src/tests/analyticsHistory.test.ts` | suite failed (no helper) |
| L6 Gmail store failures | `app/api/integrations.py:94` | `test_gmail_callback_redirect.py::test_any_storage_failure_redirects_with_error` | 1 failed (RuntimeError -> 500) |

## Pre-fix failing state (each new test, before its fix)

| # | Test | Pre-fix result |
|---|---|---|
| 1 | strategyDetail.test.tsx (old page) | 6 failed / 1 passed: "Found multiple elements with the text: /phase pending/i"; 5 list items (one per attempt) instead of 3 |
| 2 | test_outcome_attribution.py (listener disabled) | 3 failed / 1 passed: `strategy_id` None; A/B stats 0 sends of 3; reply (None, None) |
| 2 | promoted-winner dashboard test | KeyError 'promoted' |
| 4 | templateEditor.test.tsx (old editor moved verbatim) | 3 failed / 3 passed: Save enabled with `{{1}}` undescribed |
| 5 | test_phone_verification_delivery.py | 9 failed / 2 passed: 403 PHONE_NOT_VERIFIED with console in production; no warning surface |
| 5 | identity.test.ts new case | 1 failed: Shell redirect to phone step when not required |
| 10 | networkDelete.test.tsx | 1 failed / 2 passed: no delete button for a downgraded account |
| 11 | test_gdpr_erasure_scores.py | 1 failed: scores kept after erasure |
| 15 | spendLimit429.test.ts | 4 failed / 3 passed: code dropped; "Too many requests" shown |
| 16 | test_gmail_callback_redirect.py | 5 failed: 200 JSON / 400 JSON / unhandled no-refresh-token |
| 18/20 | test_plan_advertising.py | 9 failed / 1 passed |
| 19 | test_strategy_executing_guard.py | 2 failed / 2 passed: sending strategy deleted (200) |
| 21 | test_campaign_lowered_limits.py | 3 failed: 0.03 shown with a 0.02 rule; cap 100 with rule cap 7 / health cap 5 |
| 22 | test_onboarding_step_links.py | 5 failed / 3 passed |
| 24 | test_dead_code_false_text.py | 2 failed |
| 28 | test_whatsapp_template_optout.py | 7 failed / 3 passed |

Written together with their new module (no separate pre-fix run, the module
did not exist): `campaignBounce.test.ts`, `inboxBadge.test.tsx`,
`pipelineHealthCard.test.tsx`, `configWarnings.test.tsx` (their behaviour's
pre-fix failure is shown by the backend tests of the same item, or by the
absence of any caller).

## Evidence (commands verbatim, exit codes, counts)

Python: `PATH=/home/claude/.venv312/bin:$PATH`. Frontend: run in `frontend/`
with `node_modules` symlinked to `/home/claude/fe-master/frontend/node_modules`
(symlink removed afterwards). Output files are in the session scratchpad.

Round 0 (commit 049d8b3):

| Command | Exit | Result |
|---|---|---|
| `python -m pytest tests -q -p no:cacheprovider --ignore=tests/integration` | 1 | 1 failed, 4689 passed, 7 skipped, 12m07s (`test_m5_backend::test_analytics_series_and_variants`, fixed date outside the new history window; fixed, file re-run 17 passed) |
| `npx tsc --noEmit` | 0 | no output |
| `NEXT_PUBLIC_API_URL=http://api.test npx next lint` | 0 | warnings only, all in files this change did not introduce |
| `npx vitest run` | 0 | 78 files, 892 tests passed |

Round 1 (review fixes, this worktree):

| Command | Exit | Result |
|---|---|---|
| `python -m pytest <new + related files: whatsapp*, outcome_attribution, ab_auto_promotion_gate, phone_verification_delivery, identity*, billing, strategy_status_fixture, strategy_executing_guard, strategy_delete, dead_code_false_text, gmail_callback_redirect, plan_advertising, campaign_lowered_limits, gdpr_erasure_scores, onboarding_step_links, help_center, activity_audit*, replies, crm_dashboard, m5_backend, playbook*, production_guard> -q -p no:cacheprovider` | 0 | 521 passed, 60.8s |
| `python -m pytest tests -q -p no:cacheprovider --ignore=tests/integration` (output `product-defects_full2.txt`) | 0 | **4718 passed, 7 skipped, 0 failed**, 12m04s |
| `npx tsc --noEmit` | 0 | no output |
| `npx vitest run` | 0 | **79 files, 896 tests passed** |
| `NEXT_PUBLIC_API_URL=http://api.test npx next lint` | 0 | 6 warnings (pre-existing: `<img>` x5, network page hook deps), 0 errors |

`next lint` refuses to load next.config.js without `NEXT_PUBLIC_API_URL`; a
placeholder value was used for linting only.

Pending orchestrator: `python3 evals/tools/promote.py` result, sealing
`tests/test_whatsapp_template_optout.py` into `evals/compliance_testset.yaml`,
commit SHA and CI run URL.

## Out-of-scope discoveries (reported, not fixed)

- **GDPR (H):** erasure keeps `leads.provenance_json`, whose entries carry the
  field `value` (e.g. the erased email/title), and `provenance_updated_at`.
  Belongs with the other branch editing `_gdpr_erase_lead`.
- `frontend/src/components/strategies/MultiVariateResults.tsx` is never
  mounted; multi-variate results are API-only.
- `GET /strategies/{id}/mv-results` ownership check uses raw SQL with the
  dashed UUID string; on SQLite that never matches (404). PostgreSQL is fine.
- `frontend/src/lib/api/onboarding.ts` (`onboardingApi`) has no caller; nothing
  in the backend marks onboarding steps, so `/onboarding/state` never progresses.
- `frontend/src/components/kanban/StrategyPicker.tsx` appears unused (not
  verified to the deletion bar; not deleted).
- Email-verification bounce report (`bounce_shield.report`) still returns the
  baseline `campaign_pause_threshold`.

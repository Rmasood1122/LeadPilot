# Code defects found while writing and fact-checking the help center

Found 2026-10-10/11 by the article writers and the read-only fact checker while
verifying every sentence of `docs/help-center/` against the code. **Reported,
not fixed** (CLAUDE.md scope rule). The articles describe the code as it is
today, including these defects, so a fix here means the matching article must be
updated in the same PR (the drift tests catch only plan limits, sources and
links).

**Fixed since (2026-10-11, branch `claude/send-path-gaps`):** #3, #6, #7, #8,
#9, #12, #13, #14. See `docs/program/fixes/send-path-gaps.md`; the matching
articles were updated in the same change. The rows below are kept as found.
**Status (2026-10-11):** #1, #2, #4, #5, #10, #11, #15, #16, #18, #19, #20,
#21, #22, #23, #24 and #28 are fixed on branch `claude/product-defects`; see
[`fixes/product-defects.md`](fixes/product-defects.md) for each fix, its tests
and the articles updated with it. The rows below are the original findings.

Severity: **H** = customers get wrong behaviour or a broken screen; **M** =
wrong in some cases or misleading UI; **L** = stale doc, dead code, cosmetic.

## Product behaviour

| # | Sev | Finding | Evidence | Article that describes it |
|---|---|---|---|---|
| 1 | H | Strategy detail page reads a different response shape than the API sends: progress shows one "Phase pending" card per pipeline, step outputs never render, the "xN" attempt count and the verification fix text never show. No frontend test covers it. | `frontend/src/app/(app)/strategies/detail/page.tsx:33-59,186-208`; `app/api/strategies.py:221-258` | 03, 04, 05 |
| 2 | H | Learning loop and A/B auto-promotion probably see almost no send data: they filter on `Outcome.strategy_id` / `Outcome.variant`, but the send and reply paths store the variant only in `meta_json`. `strategies.default_variant` is written and never read. Needs a confirming test. | `score_decay.py:142-154`; `learning_tasks.py:215-227`; `ab_testing.py:140-150`; `outreach_tasks.py:525-528,1109-1113` | 17 |
| 3 | H | **Remove** on a lead does not stop a sequence it is already in; the send step never checks lead status. | `app/api/ui_support.py:133-148`; `outreach_tasks.py:160-196` | 06 |
| 4 | H | WhatsApp "+ New draft" editor cannot save any template with placeholders (sends `variable_descriptions: {}`, server requires one per placeholder) — its own example `Hi {{1}}` fails. | `frontend/src/app/(app)/campaigns/page.tsx:102-106`; `app/services/whatsapp_templates.py:101-118` | 10 |
| 5 | H | Phone verification uses `SMS_PROVIDER=console` (delivers nothing) while `REQUIRE_PHONE_VERIFICATION=true` by default, so new accounts cannot launch outreach or buy a plan until Twilio is configured. | `app/config.py`; `BUILD_BLOCKERS.md` item 1 | 03, 29 |
| 6 | M | Re-engagement auto-send (when switched on) is cancelled when due, because the "not now" reply already stopped the sequence it is attached to. Module docstring also says it is on by default; the setting defaults off. | `reengagement_memory.py:484-501`; `outreach_tasks.py:173-177,1104-1107` | 13 |
| 7 | M | A message held in the review queue does not block the follow-up sweep, so a held step can be created again (duplicate); a rejected step is retried later by the sweep. | `outreach_tasks.py:1386-1393,1440-1470` | 12 |
| 8 | M | WhatsApp-first sequences exclude leads with a phone but no email (`enroll_leads` filters on `Lead.email`); a lead with no address for the channel is stopped with `reason="suppressed"`. | `sequence_engine.py`; `outreach_tasks.py` | 10 |
| 9 | M | Enroll API accepts any `lead_statuses`, so an API caller can enroll dropped, flagged or replied leads. Product decision. | `app/api/sequences.py:139-143`; `sequence_engine.py:202-216` | 06 |
| 10 | M | Network page delete button hidden below Growth, although the delete API works on every plan → a downgraded customer cannot delete uploaded connections from the app. | `network/page.tsx:210,236-241`; `app/api/linkedin_network.py:134-138` | 11, 21 |
| 11 | M | GDPR lead erasure keeps `ai_booking_likelihood` and all `fpta_*` scores on the kept record. | `app/api/leads.py:325-339` | 21 |
| 12 | M | Webhook retry: 5 attempts total, so the documented 2-hour retry is never reached (off-by-one). | `webhook_delivery.py:78,327,370-377` | 16 |
| 13 | M | Alert events `domain_blacklisted`, `deliverability_warning`, `mailbox_paused`, `send_needs_review` build webhook payloads but are not subscribable. | `webhook_delivery.py:61-76,128-130` | 19 |
| 14 | M | Double-booking prevented per booking page only, not per host. | `app/db/models.py:2453` | 14 |
| 15 | M | Frontend turns every 429 into "Too many requests…", hiding the `daily_ai_limit_reached` message on Resume, Re-verify, sourcing and launch. | `frontend/src/lib/api/strategies.ts` `resumeStrategyErrorMessage`; `frontend/src/lib/leadOutreach.ts` | 04, 27 |
| 16 | M | Gmail OAuth callback returns raw JSON instead of redirecting to the app (Slack/HubSpot/Salesforce redirect). | `app/api/integrations.py` | 09 |
| 17 | M | Send-review VIP title rule (on by default) matches owner, founder, "head of" — most first emails to the ICP are held for review by default. Product decision. | `app/services/send_review.py:86-89` | 09, 12 |
| 18 | M | Plans advertise limits that are not enforced: `analytics_history_days`, `multi_variate` (gated by `ab_testing` instead), `api_rate_limit_multiplier`. Pricing page shows "Unlimited" sequence steps; API caps a sequence at 20. | `app/core/plans.py`; `app/api/sequences.py:84,120`; `frontend/src/app/pricing/page.tsx` | 22 |
| 19 | M | `StrategyStatus.EXECUTING` is never assigned, so the guards that check it never fire. | `app/` (grep) | 04 |
| 20 | L | `PLANS["starter"]["upgrade_to"]` is "pro"; `_PLAN_UPGRADE_PATH` says "growth" (pro no longer sold). | `app/core/plans.py` | 22 |
| 21 | L | Campaign bounce banner says "≥ 3%"; the pause fires at "> threshold", and compliance rules can lower it. "Today / cap" ignores lowered caps. | Campaigns page; `app/api/strategies.py:556` | 09, 19 |
| 22 | L | Onboarding checklist component is never rendered; its `STEP_ACTIONS` links point to routes that do not exist. | `app/api/onboarding.py`; `OnboardingChecklist` | 03 |
| 23 | L | `countInbox` has no caller (no Inbox badge); Pipeline Health Score endpoint has no UI consumer but the marketing page advertises it. | `frontend/src/lib/api/inbox.ts:25`; `how-it-works/page.tsx:31` | 13, 18 |
| 24 | L | Dead code with false text: `kanban/LeadDrawer.tsx` (dialog says messages are deleted), `PullToRefresh.tsx`, `optin_url()`. | as named | 21, 26, 10 |
| 25 | L | No password reset, no two-factor sign-in, no billing management UI (`billingApi.cancel`/`dispute` unused). | `frontend/src`, `app/api/auth.py` | 23, 22, 29 |
| 26 | L | Suppression is deployment-wide (no owner filter): one account's unsubscribe suppresses that person for every account. Fine for single-tenant. | `lead_tasks.is_suppressed` | 20 |
| 27 | L | Playbook scores mix every account's data for a pattern while the prompt calls them "this account's real outcomes". | `playbook_scores` | 17 |
| 28 | L | WhatsApp template validation does not require "Reply STOP to opt out" (editor hint only); `record_opt_in` error tells a suppressed contact they can re-opt-in, which the code makes impossible. | `whatsapp_templates.py`; `whatsapp_optin.py` | 10 |

## Documents that contradict the code (legal-posture risk)

| # | Sev | Document | Says | Code does |
|---|---|---|---|---|
| D1 | H | Website `/how-it-works` | "Sent by human senders — not bots"; research "on every prospect" | Sends automatically; research once per strategy (founder decision D1: code is the truth; website fix is its own PR) |
| D2 | H | Website Privacy page | deletion within 30 days; prospect data deleted when an engagement ends | neither is implemented |
| D3 | H | `docs/PRIVACY_POLICY.md` | bcrypt passwords; in-app account deletion; "Settings → Export"; message bodies not stored; 90/30-day retention | PBKDF2-SHA256 600k; no deletion; export under Profile; bodies stored; no retention jobs |
| D4 | M | Contact page | LinkedIn is the primary channel; pricing discussed on a call | Email is the default channel; public pricing page exists |
| D5 | L | `FEATURES.md` | Part 5 "LinkedIn is not implemented"; Stage 2 GTM runs first; follow-up "if the sequence has no next step" | LinkedIn exists; strategy runs first; that follow-up path only applies to deleted steps |
| D6 | L | `docs/compliance.md` | `GMAIL_DAILY_SEND_CAP` default 500; `{unsubscribe_link}` token check | `gmail_daily_cap` = 100; footer added in `build_compliant_email` |
| D7 | L | `docs/program/BASELINE.md` | plan enforcement, per-account AI cap, sign-up switch OPEN | fixed on master by #55, #56, #58 |

Status 2026-10-11 (`docs/program/fixes/platform-gaps.md`): D4, D5, D6 and D7
corrected to the code with file:line evidence; discovery 25's password-reset
part is fixed (self-service reset, `docs/features/password-reset.md`), while
two-factor sign-in and a billing management UI remain open.

## Help center gaps (for a follow-up article PR)

- No article covers the Learn tab / tutorials, yet article 30 and the support
  assistant's refusal message list "tutorials" as a topic it can answer.
- The widget's starter question "What does LeadPilot replace?" has no answer in
  the corpus; "How does outreach work?" is too vague for lexical retrieval.

---

## Help AI v2, Phase 1 (2026-10-18): found while writing and checking articles 31–44

**Reported, not fixed** (CLAUDE.md scope rule). Each article describes the
code as it is today, including these defects. Severity as above. "Source" is
the writer or checker that found it; evidence was re-read in code.

| # | Sev | Finding | Evidence | Article that describes it |
|---|---|---|---|---|
| 29 | H | **SDR or viewer may connect a mailbox or CRM to the owner's account.** The Gmail, HubSpot and Salesforce connect flows start with `GET …/auth-url`; the role check (`rbac`) blocks only writes, and the signed state is for the workspace owner. Needs a test before any claim either way. | `app/api/integrations.py` (gmail auth-url), `app/api/crm_integrations.py` (hubspot/salesforce auth-url), `app/services/rbac.py:54` | 32 (avoids claiming those connects are blocked) |
| 30 | M | **ICP never reaches the data part of either lead score.** `pattern_inputs_json` is nested (`{"icp":…, "tactics":…}`) but is read as a flat ICP, so Industry fit is always 50%, the company-size range never applies, F-P-T-A Problem keywords are unused, and market intel never sees the ICP industries. | `app/services/lead_scoring.py:215`, `app/services/fpta_scoring.py:393`, `app/services/market_intel.py:104` vs `app/services/icp_extraction.py:214-222` | 33 (states the effect) |
| 31 | M | **Admins can delete suppression entries with no audit record**; `removed_by` is accepted but unused. Phone suppressions cannot be lifted at all (removal is by email only). | `app/services/admin_service.py:231-236`, `app/api/admin.py:209-218` | 10, 38 |
| 32 | M | **CRM sweep can drop records for good**: after a capped run (500 leads / 500 deals) `last_push_at` moves to the sweep start, so records past the cap are skipped until they change again. | `app/services/crm_sync.py:539-554` | 36 |
| 33 | M | **CRM `proposal_sent`** has no status mapping, is in neither sweep set and ranks lowest in `_RANK`; immediate pushes (`push_lead`) apply no status filter, so a `proposal_sent` lead goes out with no status value. | `app/services/crm_sync.py:65-88, 495-509` | 36 |
| 34 | M | **Salesforce matching searches Leads only**, so a person who already exists as a Contact gets a new Lead. Inbound Salesforce changes ignore `deal_stage_map`; inbound lead statuses ignore `lead_status_map` for both CRMs. | `app/integrations/salesforce.py:132-135`; `app/services/crm_sync.py:91-95, 626-671` | 36 |
| 35 | M | **Gmail access revoked**: renewal fails, each send goes back to the queue and is retried indefinitely; the only signals are the strategy page's sending diagnosis (after a failed send) and **Test**. No notification. | `app/workers/outreach_tasks.py:985-988`, `app/services/send_diagnostics.py:131-172` | 35 |
| 36 | M | **WhatsApp without `WHATSAPP_APP_SECRET`** rejects every webhook (no replies, STOP or window), while the Settings card still shows "configured". Template submit sends no example values for placeholders (TODO), so Meta may reject `{{n}}` templates. | `app/api/webhooks_whatsapp.py:110-128`, `app/api/ui_support.py:218-247`, `app/integrations/whatsapp.py:348-350` | 10 |
| 37 | M | **Email health card and launch preflight disagree**: the card checks only that some SPF exists, only the `google` DKIM selector and DMARC on the exact domain; the preflight requires `_spf.google.com`, reads `deliverability_dkim_selectors` and falls back to the parent domain. | `app/services/deliverability.py:108-120`; `app/services/deliverability_autopilot.py:64, 147-237, 396` | 35 |
| 38 | M | **Blocked YouTube script leaves an empty player**: `loadYouTubeApi()` never rejects (no `onerror`, no timeout), so the documented fallback iframe and "Progress tracking is unavailable" message never appear. The spec says the fallback works. | `frontend/src/components/tutorials/VideoPlayer.tsx:76-95, 200-267`; `docs/features/tutorial-section.md:195` | 44 |
| 39 | L | Mailbox bounce rate has no minimum sample (one early bounce can pause a new mailbox); the campaign check waits for 10 sends. | `app/services/mailbox_health.py:164-166` vs `app/config.py:115` | 41 |
| 40 | L | `render.yaml` sets `RATE_LIMIT_SUPPORT_CHAT=30` on both services, while `app/core/config.py:340` records a product-owner decision to lower it to 20 (2026-08-30). The articles now state the hosted value (30); which one is intended is a founder question. | `render.yaml:133-135, 233-235`; `app/core/config.py:340-358` | 27, 29, 30 |
| 41 | L | Webhook **Send test** samples differ from live payloads (`meeting_booked`, `deal_won` value vs `value_cents`, `strategy_mutated`). | `app/services/webhook_delivery.py:105-120` | 37 |
| 42 | L | A sourcing run that finds nobody shows no message: `LeadBatch.error` is stored but `LeadBatchOut` has no error field. Spend Guard counts Apollo credits by page size requested, not people returned. | `app/workers/lead_tasks.py:681-684`, `app/api/schemas.py:195-204`, `app/integrations/apollo.py:93` | 06 |
| 43 | L | Client `status` (paused/archived) is not read anywhere in the send path; client editing (fee, currency, contacts, pause) is API-only; `report()` applies dates to some metrics only; launch phone check uses the owner's phone. | `app/workers/outreach_tasks.py:708-710`; `frontend/src/lib/api/clients.ts`; `app/services/client_workspaces.py:396`; `app/api/sequences.py:441` | 24, 32 |
| 44 | L | Playbook: research sees pattern hashes, not the plays; scores pooled across accounts (#27, still open); admin Playbook page reads `last_updated` (API sends `last_aggregated_at`); `SubjectLineCard`/`SendTimeCard` never rendered; `subject_intelligence.get_top_patterns` calls `db.rollback()` on an undefined name. | `app/services/playbook_service.py:69-78`; `frontend/src/app/(admin)/admin/playbook/page.tsx`; `app/services/subject_intelligence.py` | 34 |
| 45 | L | Admin **Tutorials** page has no create form (API only); the "not published yet" panel promises an outline that is not rendered; `docs/features/tutorial-section.md` is stale (catalogue moved to a DB table); `support_kb.py:152` promises "9 expert tutorials" without saying videos may be placeholders. | `frontend/src/app/(admin)/admin/tutorials/page.tsx`; `VideoPlayer.tsx`; `app/services/support_kb.py:152` | 44 |
| 46 | L | Reply Copilot: the "prospect wrote twice" option only renders inside a conversation that already has a draft; marketing copy says "no auto-reply" (`frontend/src/content/geo/compare.ts:99,185,438`) although Copilot auto-send exists (off by default). | `frontend/src/components/inbox/ReplyCopilotPanel.tsx:59-63`; `compare.ts` | 38 |
| 47 | L | Stale docs: `docs/features/crm-ecosystem.md` ("every verified lead"; webhook list missing six events); `docs/features/annual-billing.md` and a `billing_catalog.py` comment still call ×10 "to confirm" (decided 2026-10-11); `send-path-gaps.md` says `call_completed` never delivers (it now does); `RATE_LIMIT_GET` defined and never enforced; `ab_testing.py:24` docstring says `default_variant` affects rendering (nothing reads it). | as named | 16, 34, 37, 40 |
| 48 | L | AegisAudit and SIGNALFORGE send tasks exist and are registered but nothing calls them; article 43 ("sends them no drafts or prospect data") becomes false the day they are wired. No UI to view `security_audit_events` (export only). | `app/workers/tool_integration_tasks.py:41,77` | 42, 43 |

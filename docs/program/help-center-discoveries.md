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

## Help center gaps (for a follow-up article PR)

- No article covers the Learn tab / tutorials, yet article 30 and the support
  assistant's refusal message list "tutorials" as a topic it can answer.
- The widget's starter question "What does LeadPilot replace?" has no answer in
  the corpus; "How does outreach work?" is too vague for lexical retrieval.

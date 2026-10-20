# AI backlog — Victorae program

Phase 0, step 5 of `docs/program/STAR_VICTORAE.md`. Inputs: `ai-inventory.md` (36 touchpoints,
29 user workflows, 9 existing AI features). Written 2026-10-20 at program start SHA `7872f9c`.

**What the scores rest on.** No product analytics exist in the repo or this session; the only
measured usage is 4 help-chat calls, all by the founders (`plans/help-ai-v2-00-recon.md:59`).
Effort and impact scores are therefore engineering judgement (ASSUMPTION). Cost figures are
code/doc estimates at the prices the meter assumes for `claude-sonnet-4-6` ($3 / $15 per MTok,
`app/services/system_settings.py:74-77`), not metering data.

## Scoring

Each item is scored 1–5 (5 = best for us):

- **E** — user effort removed.
- **R** — revenue / retention impact.
- **K** — risk. 5 = touches nothing that sends, spends, or affects consent or legal; 1 = it can.
- **C** — cost per user per day. 5 = under $0.05; 4 = under $0.25; 3 = under $1; 2 = under $3; 1 = more.
- **V** — how well it can be evaluated. 5 = code-gradable, with ground truth in our own data; 1 = taste only.

Total = sum of the five (max 25). Ties break toward the higher K.

**What AI never decides.** These stay deterministic or human in every item below: sign-in and
roles, billing, spend caps and strategy budgets, plan limits, suppression / unsubscribe /
consent, send-rate limits, the daily send approval, launch and review-queue decisions, the
Legal & compliance verification pass, and voice-call AI disclosure. AI may explain or draft
around them. It never flips them.

## A. Improve what exists (done before anything new, per the program rules)

| ID | Item | What it changes | E | R | K | C | V | Total | Est. $/user/day |
|---|---|---|---|---|---|---|---|---|---|
| I1 | **Consent hardening** | A deterministic opt-out keyword check runs in the reply hot path beside the LLM classifier: either one flagging "stop" suppresses. Today only the LLM decides (`reply_classification.py:81`). Call stop-request analysis runs at temperature 0, and the stop request is recorded when analysis fails, instead of being lost after 3 failures (`phone_calls.py:357`). This adds a deterministic guard; AI gets less authority, not more | 1 | 4 | 5 | 5 | 5 | **20** | ≈ 0 |
| I2 | **Injection containment, remaining paths** | `prompt_safety` wrapping on `meeting_prep.py:318-336`, `loom_video.py:89-94`, `market_intel.py:306`, `roleplay.py:213-215`, and the raw lead fields in personalization / LinkedIn / phone / network / follow-up prompts. Schema-validate every JSON output; fail closed | 1 | 3 | 5 | 5 | 5 | **19** | ≈ 0 |
| I3 | **Fix #30 ICP nesting** | Deterministic bug: the ICP is stored nested but read flat (`fpta_scoring.py:393`, `lead_scoring.py:215`, `market_intel.py:104`), so industry fit is always 50% and problem keywords are never used. It feeds F-P-T-A, lead scoring and meeting-prep briefs | 2 | 4 | 5 | 5 | 5 | **21** | 0 |
| I4 | **Gateway modernisation** | Send temperature only to models that accept it (newer models return 400 on it); per-purpose model routing; structured outputs / tool use for JSON contracts; startup check that the model id is valid (F-AI-04); **per-model and per-token-class pricing in `usage_meter`** (cache read/write, batch); one source for the default model instead of 4 | 1 | 3 | 4 | 5 | 5 | **18** | ≈ 0 (enables savings) |
| I5 | **Caching + Batch** | Put the stable material first: document before criterion in `verification/passes.py:60-71`, context before step header in `pipeline/registry.py:25-44`. `cache_control` on those prefixes. Batch API for the initial verification passes, scoring and website pages | 1 | 3 | 4 | 5 | 4 | **17** | saves money; strategy cost ≈ $8.29 today |
| I6 | **Reply Copilot v2** | On by default per plan (the flag is off today, `system_settings.py:318`). Merge the duplicate ungrounded draft from `reply_intelligence.py` (saves one call per reply). "Regenerate with instruction" (shorter / warmer / propose times). Auto-send rules unchanged | 5 | 5 | 3 | 4 | 4 | **21** | $0.10–0.40 (5–20 replies × $0.02) |
| I7 | **Manual launch pre-fill** | Reuse `autopilot.plan_steps` (`autopilot.py:593`) to pre-fill the opening and follow-up briefs in `OutreachPanel.tsx`. The user edits and launches; nothing sends without them | 5 | 4 | 4 | 5 | 4 | **22** | ≈ $0.01 ($0.05 per strategy) |
| I8 | **Help AI: live baseline + account-aware answers** | Run the existing live eval and record it. For "why isn't it sending / what's my plan" questions, answer from `send_diagnostics.diagnose` and plan state (read-only, own account only), not from generic articles. Notify the founders when a ticket is filed (today nobody is told, yet the widget promises 24 h) | 4 | 4 | 4 | 4 | 5 | **21** | $0.05–0.10 |
| I9 | **Meeting outcome notes from transcript** | When a Recall.ai transcript exists, pre-fill Log Outcome notes and propose a CRM stage. The user confirms | 4 | 3 | 4 | 4 | 3 | **18** | $0.02–0.06 per meeting |
| I10 | **Approved-claims proposer** | Extract candidate sender claims from the research and the product description into the F05 library, **pending** human approval. Claims are never auto-approved | 4 | 3 | 3 | 5 | 4 | **19** | one-off ≈ $0.05 |
| I11 | **Voice twin: model-based disclosure check** | A second-layer post-call check that the AI disclosed itself. The regex check stays as the guard. Blocked: voice twin has never run live and is off by default | 1 | 2 | 3 | 4 | 3 | **13** | — |

## B. New features

| ID | Item | What it does | E | R | K | C | V | Total | Est. $/user/day |
|---|---|---|---|---|---|---|---|---|---|
| N1 | **Review-queue assist** | For each held message: why it was held (from the deterministic gate) plus a suggested edit. The human approves, edits or rejects; the edit goes back through claim verification and every send gate | 4 | 4 | 3 | 4 | 4 | **19** | $0.10–0.20 |
| N2 | **Morning brief** | One AI-written summary of the five daily stops (approval, inbox, review queue, mailbox health, strategy status). Every number comes from SQL and the deterministic gates; AI words it and orders it. It reports and never approves | 4 | 4 | 4 | 5 | 4 | **21** | ≈ $0.03 (1 call) |
| N3 | **Lead brief** | One paragraph across the lead page's panels (F-P-T-A, signals, history, replies) | 3 | 3 | 4 | 4 | 3 | **17** | $0.02 per view, cached per lead/day |
| N4 | **Connector inbox/review tools** | MCP read tools for needs-reply threads, the review queue and send diagnostics, plus a draft-only write tool. No send, no approve (CONN-WRITES stands) | 3 | 3 | 3 | 5 | 4 | **18** | ≈ 0 to us (the user's own Claude runs the model) |
| N5 | **Product intake from URL** | Draft the product description and ICP from the customer's own site. The site is untrusted input, so it is wrapped and the output is schema-validated | 4 | 4 | 3 | 5 | 3 | **19** | one-off ≈ $0.05 |

## C. Prerequisites (not features; they gate the rest)

| ID | Item | Why it blocks |
|---|---|---|
| P1 | **Feature-usage measurement** (counts per feature per account, no content) | Without it, E and R above stay guesses, and the Phase 3/4 "measurably better" claim can only be about eval scores, not user effort |
| P2 | **Production metering read-out** | The live-eval spend ceiling and every Phase 3 cost claim must come from `api_usage`, which this session cannot read. The founders run the query in `plans/victorae-00-recon.md` §5 |
| P3 | **F-DB-01** (`playbook_scores` has no account column) | Pipeline prompts include playbook rates labelled "learned from this account's real outcomes" (`app/services/playbook_service.py:69`). The rows are pooled across accounts by `pattern_key` (`app/db/models.py:1722-1725`). That is cross-account aggregate data inside a prompt, under a false label. It is aggregate rates only, no PII. It collides with the "cross-account data" safety slice that Phase 2 must gate on |

## Recommended top 5 to build in this program

Ordered by when they should land. The ordering follows the program rule (existing AI first) and
keeps everything with K ≤ 3 behind its eval and a flag.

1. **I1 Consent hardening + I2 Injection containment.** One Phase 3 PR each. Legal posture first.
   They fit the program's own Phase 3 items 1–2, so they cost no extra slot.
2. **I7 Manual launch pre-fill** (22). Removes the hardest blank-page step, about $0.01 per user
   per day, and the code already exists in Autopilot.
3. **I6 Reply Copilot v2** (21). The biggest daily-effort win. Gated by a pass^3 = 100% safety
   slice on invented claims and meeting promises.
4. **I8 Help AI account-aware + live baseline** (21). The only AI touchpoint with an existing
   live eval and golden set. It is the quickest to prove.
5. **N2 Morning brief** (21). The first new feature. Read-only, one call per day, and it makes AI
   the entry point of the daily loop, which is what "AI-native" means for this product.

**Recommended outside the five:**

- **I3 (#30)** and **I4 (gateway)** are engineering fixes, not features. They should land in
  Phase 3 regardless of what else is chosen: I4 is required before any newer model can be
  evaluated, and I3 corrupts the inputs to three touchpoints being evaluated.
- **I5 (caching/batch)** is Phase 3 items 3–4 already.
- **N1** is the next candidate if the founders want six.

# Feature Group 1 — AI intelligence layer

## Multi-model consensus
- **Where:** the 8 phase-synthesis steps of each pipeline (step 9 of every
  phase). Those outputs *are* the strategy document's sections, so every flag
  lands on a section a reader sees. Running both models on all 144 steps would
  triple strategy cost to cross-check research nobody reads directly.
- **How:** GPT-4o answers the identical system prompt and brief in parallel
  with Claude. A Claude "consensus judge" compares them **anonymised** as
  Strategist A/B and reports only meaningful disagreements (different
  recommendation, contradictory fact, different segment/channel/price). Medium
  and high severity become `strategy_uncertain_zones`; a TF-IDF similarity is
  stored beside each as a model-free signal. Both raw outputs are kept in
  `strategy_model_outputs`.
- **Claude stays canonical.** The document is assembled from Claude's answers
  exactly as before.
- **Failure:** an OpenAI error or a judge error never fails a step; the
  strategy's `consensus_status` becomes `partial`.
- **Enable:** Admin › Integrations › OpenAI key, then Admin › System Settings ›
  `consensus_enabled` (off by default — it adds ~16 model calls per strategy).

## Real-time competitor intelligence
Before Phase 1, `market_intel.ensure_signals` builds queries from the ICP
(past-client industries, else the product's distinctive terms) and pulls:
- **Google News** via the public RSS search feed (last 30 days, no key);
- **Apollo** organization search — recent funding rounds and six-month
  headcount growth.

Headlines are classified as funding / hiring / launch / news by keyword rules,
not a model, so no signal can be invented. The stored snapshot is injected into
Phase 1 and Phase 3 prompts, labelled as headlines to verify rather than facts.
Fetched once per strategy; resumes reuse it. Admin switch:
`competitor_intel_enabled`.

## Predictive lead scoring
When a sourcing batch finalizes, each verified/flagged lead gets
`ai_booking_likelihood` (0–100):
1. deterministic factors — seniority, industry match to the ICP, verification,
   company signals (recent funding, size in range), playbook booking rate;
2. a weighted heuristic baseline;
3. Claude, in batches of 15, may move the baseline **at most ±20 points**
   with a one-sentence reason (clamped server-side).

A model failure leaves the heuristic score (`method: heuristic`). Scores show
as badges on the kanban, a sortable CRM grid column, and a factor breakdown on
the lead page; the leads list sorts by score by default. Admin switch:
`lead_scoring_enabled`.

## Dynamic strategy mutation
A daily sweep (02:50 UTC, after the learning loop) finds active campaigns
whose **first send** was at least `strategy_mutation_idle_days` (default 7) ago
with zero replies, at most once per window. Claude diagnoses the numbers and
proposes a new messaging angle, a channel, and ICP refinements. The result is a
**proposed** `strategy_versions` row (the original is snapshotted as v1) and a
push/Slack/webhook `strategy_mutated` event. Nothing changes until the user
applies it — applying replaces the document and injects the new messaging into
every future outreach prompt (outreach is written from the Phase-6 research,
not the document, so this injection is what makes "apply" real).

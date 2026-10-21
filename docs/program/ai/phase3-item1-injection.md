# Phase 3, item 1: prompt injection containment

Written 2026-10-21. Program: `docs/program/STAR_VICTORAE.md` Phase 3 item 1 ("treat all untrusted input as data, wrap it in tagged blocks labelled untrusted, never let it reach tool access, validate outputs against a schema and fail closed"). Baseline: Phase 2, `docs/program/ai/eval-baseline.md`.

## Before and after (offline evals)

| | Phase 2 baseline | After item 1 |
|---|---:|---:|
| Known defects (strict xfail) | 102 | 53 |
| Baseline cases at pass@1 = 1.0 | 1,026 | 1,075 |
| Untrusted-text defects pinned by the sets | 43 | 0 |
| Output-shape defects pinned by the sets | 6 | 0 |
| Safety slices at pass^1 = 1.0 | all | all (no regression) |

The 49 fixed cases are the ones the Phase 2 sets were written to catch. Each was a strict xfail, so it was proven failing before and is proven passing now. A strict xfail that passes fails CI, so no marker could be removed without a real fix.

**Not measured:** live model behaviour. Wrapping removes the cheap attack; whether a real model still follows a wrapped instruction is a live-eval question. Live mode is blocked on an eval key. When it runs, the injection slices of every set are the before/after measure. Cost figures: none, because nothing was sent.

## What changed

1. **Output contract (`app/services/anthropic_client.py`).** `complete_json` returns a JSON object or raises `ValueError`, never a list, string or `null`. This fixed three crashes in code documented never to raise (T28, T29, T34). One real behaviour change: a garbled call analysis is no longer stored as outcome ANSWERED. The task retries, as for any failed analysis, and invents no outcome (T15).
2. **Untrusted text wrapped.** Every value below now goes through `prompt_safety.inline()` or `block()`, with `NOTICE` in the prompt:
   - lead and enrichment fields;
   - scraped posts and news;
   - replies and transcripts;
   - booking answers, meeting titles and AI meeting summaries;
   - judged documents and research;
   - roleplay text;
   - scripted objections.

   Files: verification `loop.py`/`passes.py`, `roleplay`, `adversarial_review`, `autopilot`, `market_intel`, `fpta_scoring`, `lead_scoring`, `meeting_ai`, `meeting_followup`, `meeting_prep`, `phone_calls` (script and the **live call's system prompt**), `message_personalization`, `linkedin_outreach`, `network_messages`, `loom_video`.
3. **Criteria validated** (`icp_extraction`). Model criteria keep only strings, numbers and an object's name or label. A nested object no longer reaches the paid lead search as a Python repr.
4. **Second-order path closed** (`reengagement_memory.brief_for`). A prospect's "not now" reason, and job-change enrichment, were quoted raw into a step brief that every renderer reads as our own instructions. A reply could become instructions for the next, possibly auto-sent, message. These values are now wrapped.
5. **Analysed model text delimited.** Our sent message (reply intent, reply intelligence, Copilot) and the draft under claim check were written by a model from prospect data. They are now data to read, not trusted context. This changes the F-AI-02 decision; the test that pinned it is rewritten.

Items 4 and 5 were not in any golden set. A read-only audit of every model call after the eval-pinned fixes found them. Each has an end-to-end test in `tests/test_prompt_injection_containment.py` that fails on the old code.

## Deliberately not wrapped (with the reason)

- **Model text used as instructions.** Two cases:
  - Follow-up and re-engagement briefs, and the autopilot step brief, become the step template.
  - Research outputs feed later pipeline steps (`pipeline/engine.py` context block) and the consensus judge.

  These are written from wrapped outside text, but they are the instruction channel itself. Wrapping them would tell the model to ignore its own brief. The defence for this channel is checking the output: the open T12 known defects (links, statistics, deadlines in briefs) are a later item.
- **The user's own input.** Product, settings, strategy, playbook, pasted writing samples, the founder's own posts, the user's own chat question and meeting notes. These come from the account owner, not a third party.
- **Research and strategy text, wrapped in some places and not others** (`autopilot`, `icp_extraction`, `verification/loop.py` wrap it; `whatsapp_templates`, `strategy_mutation`, `reply_copilot`'s playbook do not). Neither is wrong under the rule above. A single policy is worth deciding in the prompt-rewrite item (Phase 3 item 5).

## Tool access

No model call in the app is given tools, so untrusted text cannot reach tool access. Checked by the audit: every call is `complete`/`complete_json` with no `tools` parameter.

## Remaining limits

- **The live voice call** (T16) has no golden set. Its system prompt is covered by one unit test.
- **Some test files are not sealed yet.** `tests/test_complete_json_contract.py` and the new containment tests guard safety behaviour but are not on the sealed list, which needs a `gate/` PR.
- **Repeated warning lines in the eval logs.** Some offline runs print `crm_events.publish_failed` (no local Redis). These are log noise, not failures.

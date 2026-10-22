# Phase 3, I3: generated text grounded in its source

Written 2026-10-22. This round fixes the last 23 defects pinned by the Phase 2 golden sets. Most are a writer stating something its source never said: a price, a date, a statistic, a funding round, a customer name, a quote, a promise, or a meeting that never happened. Each prompt already forbids this. Nothing checked.

## Before and after (offline)

| Measure | Before | After |
|---|---|---|
| Known defects (strict xfail) | 23 | **0** |
| Baseline cases at pass@1 1.0 | 1,105 | 1,128 |
| Slices below pass@1 1.0 | none | none |

Across the three rounds (I1 consent, I2 output checks, I3 grounding), known defects went from 53 to 0. Phase 2 started at 102 before item 1.

## The shared check

`app/services/grounding.py` compares a model's text with the source it was given, deterministically and with no model call. It names:
- numbers the source does not contain (written as people write them: `1,200`, `$2.5M`, `63%`);
- funding-round names (`Series B`, `seed round`);
- discounts, free extras, guarantees and deadlines (`by Friday`, `closes this Friday`, `today only`);
- quoted passages of three or more words that the source lacks.

Each touchpoint decides what to do with a finding. The table below gives each decision.

## The fixes

| Commit | Touchpoint | What is checked against what | On a finding | Cases |
|---|---|---|---|---|
| `a8d3b55` | T12 follow-up and re-engagement briefs | brief vs history, product, playbook; any link | the fixed fallback brief | 3 |
| `5cbb733` | T09 reply-intelligence draft | draft vs the reply and our message | one repair, then the fallback draft | 1 |
| `ffadc89` | T17 meeting prep | each sentence and item vs everything the model was given | the sentence or item is removed | 2 |
| `4226ad3` | T18 post-meeting follow-up | each sentence vs notes, summary, brief, product, strategy | the sentence is removed; the draft is still saved | 3 |
| `545696f` | T19 meeting action items | item vs transcript and notes | item dropped; an unstated due date cleared | 2 |
| `1ac5a4c` | T24 Loom script and title | the existing prospect-claim check (`claim_verification`), as on email | the sentence is stripped; the title replaced | 3 |
| `16d7be1` | T25 LinkedIn network draft | meeting wording; figures and rounds vs the prompt | the sentence is removed | 2 |
| `5395944` | T10 "not now" reason | reason text vs the reply | not kept, so the brief says no reason was given | 1 |
| `6dd07c8` | T11 Reply Copilot | sender claims with no approved-claims library; counts with words before the noun | one repair, then no draft | 2 |
| `2c8b75b` | T31 verification revert check | a near-copy of the *current* document is no longer a revert | the correct fix is applied | 2 |
| `200602a` | T31 verification factual floor | a later rewrite's figures and customer names vs research, the approved document and the findings | pass #1 FAIL; the strategy needs human review | 2 |

The commit messages give each fix's tests, the test counts, and what fails on the old code.

## Behaviour changes the founders should know

1. **Loom scripts cost one more model call each.** The claim check's extractor runs, as it already does on email. Two T24 cases now record that call and expect 2 calls; the commit message says so.
2. **With guardrails off (the default), a Copilot draft that cites a figure, a count or "trusted by" about us** gets one repair attempt, and then no draft. The prompt already told the model to make no claims about us when no approved claims are on file. Turning guardrails on with an approved-claims library lets approved claims through.
3. **A strategy whose later rewrite adds an unsourced figure or customer name now ends NEEDS_HUMAN_REVIEW**, not VERIFIED.
4. **The post-meeting draft, meeting prep and LinkedIn network drafts can lose sentences.** What is removed is logged. The seller still reviews every draft.

## Tests changed to match the new behaviour, with reasons

- `tests/test_verification_oscillation.py::test_near_revert_is_caught` pinned the T31 defect itself: a near-copy of the only, current state counted as a revert. It now checks a near-revert to an *earlier* state (A → B → A'), which passes before and after. A new test pins that a small fix to the current state is applied.
- In `TestShipBlockingPassRechecked`, the fake judge finding now names the figures its rewrite uses. Before, the rewrite added unsourced figures, which the new factual floor flags. Its assertions are unchanged.
- In the Loom test, the fake script cites the lead's post about inspections, so that lead now has such a post on record. The assertion is unchanged.

No test was deleted. No sealed file was touched.

## Evidence

- **I2 head (`55090b2`, tree `a882b56`):**
  - quick gate 8 of 8 PASS (4,025 passed, 23 xfailed);
  - `run_evals` 7,968 tests, pass rate 1.0;
  - **PROMOTE**, with 1 soft WARN on runtime (1,989 s vs 900 s). Other tests were running on the same machine during this run.
  - All 3 hard gates were proven to fire.
- **This head:** the run on `a2bca4e` is recorded in the next PROGRESS entry.
- **PostgreSQL integration suite on this head:** 155 passed (end-to-end pipeline and verification against the HTTP Anthropic mock).

## Limits, stated plainly

- **These are pattern checks, not judges.** Here is what they miss:
  - A figure that appears anywhere in the source passes, whatever the output uses it for.
  - An invented claim with no number, round name, quote, date or proof phrase is not seen.
  - A paraphrase presented as a quote is dropped (T10), as is a correctly computed due date (T19).
- **Both verification floors (legal and factual) check presence and novelty; neither re-judges meaning.** A model re-judge of passes #1 and #4 after later rewrites is the stronger follow-up, and its cost needs the live eval.
- **Nothing here is measured live.** The live eval is blocked on the eval key. The golden sets measure only the cases they contain; zero known defects means zero *pinned* defects, not zero defects.

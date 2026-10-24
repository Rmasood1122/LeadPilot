# Phase 3, I2: deterministic output checks for pinned defects

Written 2026-10-22. This round fixes defects that the Phase 2 golden sets pinned as strict-xfail cases. Each fix changes code, not a prompt. A rule written only in a prompt ("no links", "under 140 words", "no invented statistics") does not stop the model from breaking it, so each fix adds a deterministic check after the model call, or corrects a bug in the code around the call.

## Before and after (offline)

| Measure | Before | After |
|---|---|---|
| Known defects (strict xfail) | 41 | 23 |
| Baseline cases at pass@1 1.0 | 1,087 | 1,105 |
| Slices below pass@1 1.0 | none | none |

The baseline (`evals/ai/baseline.json`, commit `55090b2`) scores the 18 cases. Every removed xfail marker belongs to a case that now passes, and every new test was run against the old code to show it fails there.

## The fixes

| Commit | Touchpoint | Defect | Fix | Cases |
|---|---|---|---|---|
| `9160f61` | T05 claim check | `$2.5M` was split at the decimal point. The `$2.` half was stripped and `5M raise…` was sent. | A `.` between two digits no longer ends a sentence. | 1 |
| `3e04ed1`, `cbc40e7` | T14 call script | "I'm Priya, a real person" slipped past the human-claim check. | The pattern allows a capitalised name in apposition. It is case-sensitive, so "I'm sorry, a real person will call you back" is not flagged. | 1 |
| `80715b3` | T01 research pipeline | An empty model answer was saved as a completed research step. | The step raises and saves nothing, so the retry resumes at the same step. | 1 |
| `a5bc614` | T21 roleplay | A coaching tell ending in `!` or `?` ("Great question!") was shown to the seller. | The tell ends at the first `.`, `!` or `?`. | 1 |
| `433c103` | T27, T28 (I3) | The ICP is stored nested under `icp`, but lead scoring, F-P-T-A and market intel read it flat. Every lead scored industry match 0.5. | `icp_extraction.stored_icp` returns the nested ICP; the three readers use it. | 3 |
| `56c8b22` | T13 LinkedIn | A link an injected profile asked for went out in a connection note. | The email body's link allowlist applies, plus links the step brief names. | 1 |
| `95fe653` | T03 email | A 300-word body was sent as written. | A body over 200 words is refused, not cut. The send task's retry asks again. | 1 |
| `8d6707b` | T04 WhatsApp slots | A link or a paragraph could fill an approved template's slot. | A model-filled slot with a link, or over 100 characters, is refused and the send fails. | 2 |
| `efad58b` | T09 reply intelligence | A link the reply asked for was stored in the suggested answer. | Reply Copilot's link allowlist applies. One repair attempt is made, then the fallback draft is used. | 1 |
| `a4cb062` | T33 WhatsApp drafting | Drafted templates kept links, "guaranteed" or "today only", and invented figures such as 73% or 200+. | Candidates with any of these are dropped. A number counts as invented if the research the drafter was given does not contain it. | 3 |
| `b03493d` | T26 style and voice | A tone, a do or don't item, or a signature phrase smuggled in from a pasted sample went into every outbound system prompt. | Values with a link or instruction-like wording are dropped. Everyday style notes pass. | 3 |

The commit messages give each fix's tests, the test counts, and what fails on the old code.

## Process miss, corrected

`3e04ed1` added three cases to `tests/test_voice_twin_guards.py`. That file is on the sealed compliance list, and a feature task must not change a sealed file. `cbc40e7` restores the file to its previous content and moves the cases to `tests/test_voice_twin.py`. No sealed file now differs from `master`.

## Limits, stated plainly

- **These are pattern checks, not judges.** Two examples of what they miss:
  - The guidance filter (T26) does not catch a bare one-dot domain without a path, such as `evil.com`.
  - It does not catch an instruction phrased in a way its patterns don't cover.
- **The invented-number check (T33) compares digits only.** A number that appears anywhere in the research passes, even if the draft uses it for something else.
- **A refused email body or WhatsApp slot fails the send.** A retry calls the model again, which costs one more call.
- **Nothing here is measured live.** Live mode is blocked on the eval key.

## Remaining known defects (23)

- **Invented content that needs a source comparison** (19):
  - T09 statistic; T10 reason;
  - T11 (2);
  - T12 briefs (3);
  - T17 price and quote; T18 price, date and commitment;
  - T19 action item and due date;
  - T24 (3); T25 (2).
- **The verification loop** (4): two similarity-threshold false reverts, and two cases where factual accuracy is not re-judged after a later rewrite.

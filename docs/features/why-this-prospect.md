# "Why This Prospect" Explainability Panel (Part 1, Feature 12)

**Component** `frontend/src/components/leads/WhyThisProspectPanel.tsx` ·
**Logic** `frontend/src/lib/fpta.ts` · **Data** `GET /leads/{id}/fpta`

Feature 12 adds no storage and no model call of its own. It is a **reading** of
Feature 2's F-P-T-A signals — which is the point: an explanation that needed its
own generation step would be a second opinion about the score, not an
explanation of it.

## What it shows

1. **A headline that names the specific dimension driving the score** —
   *"Scores 66/100 — access is the strongest signal, problem is the weakest."*
   Never a generic "good fit".
2. **The next action**, derived from the weakest dimension when it is below 60:

   | Weakest | What the panel says |
   |---------|---------------------|
   | Fit | Check this prospect against the ICP before spending a touch on them. |
   | Problem | Find a signal in their own words before writing. |
   | Timing | Expect a "not now" — and plan the return trip. |
   | Access | Fix the address or the channel before sending. |

   Above 60 it stays quiet rather than manufacturing advice.
3. **One row per dimension, strongest first**, each with its score, the
   sentence explaining it, **and the raw evidence it was written from**. Every
   claim is traceable to a signal string the scorer actually recorded.
4. **What has happened so far** — sends, opens, last touch — which no sub-score
   covers and which changes how the score should be read.
5. **The weights**, so the overall is reproducible by hand.

## Honesty rules the panel enforces

- **An unscored prospect says so.** `whyHeadline` returns *"Not scored yet — no
  F-P-T-A signals have been read for this prospect."* rather than describing
  a prospect nobody has looked at.
- **A dimension with no evidence shows its own words** — "No visible problem
  signal" — not silence, and not another dimension's evidence.
- **A heuristic-only score is labelled.** When the model pass was unavailable,
  the reasons are the raw evidence rather than written explanations, and the
  panel says that. Terse wording must not read as a weak prospect.
- **The same dimension is never named twice** in the headline (a prospect with
  one scored dimension gets "X is the strongest signal.", full stop).

## Tests

`frontend/src/tests/fpta.test.ts` covers the headline, the advice selection
(including staying quiet), the ordering of the evidence rows, unscored
handling, and the tie-break by weight — so the dimension named as "weakest" is
always the one that actually costs the most.

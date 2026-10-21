# Phase 3, I1: consent defects the eval pinned, fixed

Written 2026-10-21. These five fixes close consent and opt-out defects that the Phase 2 golden sets pinned as strict-xfail cases. Each one changes code, not a prompt: a consent decision must not depend on what the model says.

## Before and after (offline)

| Measure | Before | After |
|---|---|---|
| Known defects (strict xfail) | 53 | 41 |
| Baseline cases at pass@1 1.0 | 1,075 | 1,087 (11 consent, 1 injection) |
| Safety slices that regressed | none | none |

The baseline (`evals/ai/baseline.json`, commit `6deefef`) now scores the 12 cases. Every removed xfail marker belongs to a case that now passes. No test was weakened or deleted.

## The five fixes

| Commit | Touchpoint | Defect | Fix | Cases |
|---|---|---|---|---|
| `deb975c` | T09 reply intelligence | Unsubscribe or erasure replies got a sales draft. A mislabel could move the sequence to step 3. | A deterministic opt-out check runs before the model call. An opt-out gets no call, no draft and no category. | 4 |
| `201283b` | T31 verification loop | A later pass's rewrite could drop the unsubscribe or postal address that the legal pass approved, and the strategy still shipped VERIFIED. | The elements pass #4 approved must still be present after every later rewrite; otherwise the strategy ends NEEDS_HUMAN_REVIEW. | 2 |
| `87a4c5d` | T15 call analysis | On outbound calls, a spoken "stop calling me" counted only if the model caught it. | The stop-phrase check now runs for both call directions, before the model. Suppression is idempotent. | 3 |
| `e983b9c` | T03 message rendering | The model could add its own "unsubscribe" link to a foreign domain. | Links are removed from the body unless they point to the sender's booking page, the app or the owner's domains. | 2 |
| `4829461` | T33 WhatsApp templates | A promotional draft labelled "utility" skipped the opt-out line. | A fixed word rule relabels it as marketing. | 1 |

Each commit message lists the tests that fail on the old code and the covering test counts.

## Limits, stated plainly

- **The legal-pass check is a presence floor, not a re-judge.** A rewrite that keeps the words but empties their meaning is not caught. The stronger fix is to re-run the legal judge after later rewrites, and its cost needs the live eval.
- **The promotional word list is a judgement call.** It can relabel genuine utility text as marketing, which adds one extra opt-out line (fails closed).
- **Link stripping also removes legitimate third-party links**, such as a case study hosted elsewhere, and subdomains of the owner's domain other than `www.` (fails closed).
- **Nothing here is measured live.** Live mode is blocked on the eval key.

## Decisions for the founders

1. Replies routed `not_interested` still get a draft. Copilot blocks them, but they are not treated as a legal opt-out. Should they be?
2. A no-lead outbound callee who says stop now has their number suppressed, as inbound callers already did. Confirm.
3. The promotional word list (`app/services/whatsapp_templates.py`, `is_promotional`): accept it or replace it.
4. Third-party link stripping: accept it as is, or name the domains to allow.

## Remaining known defects (41)

These remain pinned as strict xfails and are later work: unverified claims, link and length limits, T05 decimal handling, T31 similarity, I3 nesting and others. `python3 -m pytest tests/test_ai_evals.py -rx` lists them.

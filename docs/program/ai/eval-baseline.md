# AI eval baseline (Phase 2)

Written 2026-10-21. Program: `docs/program/STAR_VICTORAE.md`, Phase 2. State: `docs/program/ai/eval-state.json`.

## 1. What exists

Every AI touchpoint in `docs/program/ai/ai-inventory.md` has a golden set in `evals/ai/golden/`, except two:
- **T16:** the voice assistant runs inside Vapi's live call, so there is nothing to replay.
- **T36:** manual check scripts.

`tests/test_ai_evals.py::test_every_inventory_touchpoint_has_a_golden_set` fails if a touchpoint is added to the inventory without a set.

A set's cases run through **the same app function production calls**, with the model replaced by a recorded answer. What gets graded is what the app produces after its own parsing, guards and rules, not the raw model text. Graders are code: labels, forbidden or required text, length, link allowlists, numbers that must come from the input, and prompt checks that untrusted text sits inside the injection markers. A model judge exists but gates nothing (section 5).

**Two modes:**
- **Offline** (in CI, the hard gate): recorded answers, no network, no cost. This proves the prompts are built safely and that the guards and parsers behave. It says nothing about how good a real model's answers are.
- **Live** (`evals/ai/live_eval.py`, opt-in, never in CI): a real model, each case run k=3 times. This measures quality. **It has not been run yet: there is no eval key.**

## 2. Offline baseline

`evals/ai/baseline.json` (`offline`) was written by `python3 -m evals.ai.offline_baseline`: 34 touchpoints, 1,026 cases, every slice at pass@1 = 1.0. The 102 known-defect cases are left out of the baseline and run as strict xfail; each one must keep failing until its defect is fixed, then its marker comes off. The gate rules are in `evals/ai/framework.py::gate`:
- every safety slice needs pass^k = 1.0, and a better average never excuses a safety failure;
- a quality slice may drop by at most its measured noise band (none is measured yet, so there is no slack);
- a touchpoint that stops running blocks.

| TP | Title | Kind | Cases | Known defects | Offline-only | Safety slices |
|---|---|---|---:|---:|---:|---|
| T01 | Research pipeline step (one of 72/144 GTM research steps) | user_facing | 33 | 4 | 4 | injection, cross_account |
| T02 | Consensus: GPT-4o parallel answer + Claude consensus judge | user_facing | 33 | 1 | 10 | injection, cross_account |
| T03 | Outbound email and WhatsApp free-text personalization | send_affecting | 46 | 3 | 19 | consent, injection, invented, cross_account |
| T04 | WhatsApp template variable filling | send_affecting | 36 | 7 | 15 | injection, invented, cross_account, consent |
| T05 | Claim verification (model extraction + the rules that act on it) | send_affecting | 32 | 1 | 3 | invented |
| T06 | Inbound reply routing classifier (consent-critical) | send_affecting | 32 | 0 | 4 | consent, injection |
| T07 | Automated-reply detector (reply fraud second pass) | internal | 16 | 0 | 2 | injection |
| T08 | Reply intent label (positive-reply metric) | internal | 16 | 0 | 4 | consent, injection |
| T09 | Reply intelligence (category + human draft) | user_facing | 39 | 6 | 19 | consent, injection |
| T10 | Re-engagement "not now" extraction | send_affecting | 42 | 1 | 18 | consent, injection, edge |
| T11 | Reply Copilot draft and auto-send decision | send_affecting | 54 | 2 | 22 | consent, injection, invented, cross_account |
| T12 | Follow-up brief and re-engagement brief | send_affecting | 33 | 7 | 12 | injection, cross_account |
| T13 | LinkedIn outreach copy (connection note / message / InMail) | send_affecting | 36 | 4 | 17 | invented, injection, cross_account |
| T14 | AI phone call script (offline -- script, disclosure guards and live prompt; never the call) | send_affecting | 34 | 3 | 15 | injection, consent, cross_account |
| T15 | Call transcript analysis (consent-relevant) | send_affecting | 30 | 3 | 8 | consent, injection |
| T17 | Meeting prep brief | user_facing | 31 | 6 | 10 | injection, cross_account |
| T18 | Post-meeting follow-up email (saved as a Gmail draft) | user_facing | 30 | 5 | 9 | consent, injection, cross_account |
| T19 | Meeting transcript summary | user_facing | 30 | 3 | 10 | injection, cross_account |
| T20 | Strategy mutation (learning loop) | internal | 23 | 0 | 15 | cross_account, injection |
| T21 | Sales roleplay (AI plays the prospect, then gives feedback) | user_facing | 35 | 3 | 10 | injection, cross_account |
| T22 | Help-center support chat (in-app support widget) | user_facing | 42 | 0 | 14 | off_topic, injection, invented, cross_account |
| T23 | Displacement-monitor Day 0 DM | send_affecting | 30 | 0 | 12 | injection, invented |
| T24 | Personal video (Loom) recording script | user_facing | 31 | 6 | 11 | injection, invented, cross_account |
| T25 | Network message drafts (LinkedIn connections / email contacts) | user_facing | 36 | 5 | 15 | injection, invented, cross_account |
| T26 | Style profile and founder voice profile | send_affecting | 33 | 3 | 19 | injection, cross_account |
| T27 | F-P-T-A scoring and booking-likelihood lead scoring | internal | 31 | 4 | 20 | cross_account, injection |
| T28 | ICP criteria extraction + tactic classification | send_affecting | 34 | 3 | 18 | cross_account, injection |
| T29 | Past-client pattern extraction (intake) | internal | 18 | 2 | 10 | cross_account, injection |
| T30 | Verification judge (10 passes; pass 4 legal and compliance is the ship-blocker) | send_affecting | 35 | 3 | 13 | consent, injection, edge |
| T31 | Verification fixer (full-document rewrite inside the verification loop) | send_affecting | 32 | 8 | 18 | consent, invented, injection |
| T32 | Autopilot sequence briefs and send-time plan | send_affecting | 44 | 1 | 31 | consent, edge, injection |
| T33 | WhatsApp template drafting (saved as drafts only) | user_facing | 37 | 4 | 25 | consent, invented, cross_account |
| T34 | Sequence red-team review (pre-send adversarial review, model pass) | user_facing | 33 | 4 | 19 | consent, injection, edge |
| T35 | SEO website page builder | user_facing | 31 | 0 | 14 | cross_account |
| **34 sets** | | | **1128** | **102** | **465** | |

"Offline-only" cases test the app's handling of a deliberately bad answer (outage, malformed JSON, an answer that obeys an injection). Live mode skips them, because a real model will not produce those answers on demand.

Command (from `/home/user/LeadPilot`, 2026-10-21): `timeout 1200 python3 -m pytest -q -p no:warnings tests/test_ai_evals.py tests/test_ai_live_eval.py` gave `1095 passed, 102 xfailed in 300.91s`. Two earlier full runs of the eval file gave identical results; no case is flaky.

**Proof the gate catches a broken prompt:** `docs/program/ai/evidence/broken-prompt-T06.md`. Removing the injection wrapping around the reply body fails 4 T06 safety cases; after the revert, all 33 pass.

## 3. What the sets found: 102 known defects

Each one is pinned in its set's `known_failure` with a file:line, and each was checked to fail on the grader it names. Grouped:

- **Untrusted text reaches a prompt with no wrapping (the largest group).** Affected: news headlines (T01/T02), lead and profile fields (T04, T12, T13, T14, T17-T19, T24, T25, T27), the seller's roleplay text (T21) and judged documents (T30-T34). Phase 3 item I2 (injection containment) is the fix.
- **Consent.**
  - Unsubscribe and do-not-contact replies still get a sales draft, and a buying-signal label can move an unsubscriber's sequence forward (T09).
  - On outbound calls, a spoken "stop calling me" is caught only by the model (T15).
  - A cold pitch the model labels "utility" is saved with no opt-out (T33).
  - A later verification rewrite is not re-judged by the legal pass, so a dropped unsubscribe can ship as verified (T30).

  Phase 3 item I1 (consent hardening) is the fix.
- **Invented claims that are sent.**
  - "$2.5M" is split at the decimal point and mangled (T05).
  - Copilot auto-sends some invented claims (T11).
  - Briefs, Loom scripts, meeting follow-ups and WhatsApp drafts are never claim-checked (T12, T17, T18, T24, T33).
- **Crashes in code documented never to raise.** JSON-array replies crash three touchpoints (T28, T29, T34).
- **Wrong data.**
  - ICP stored nested but read flat by both scorers (I3/#30).
  - Criteria objects sent to the paid lead search as Python text.
  - Empty model answers saved as finished research steps.

## 4. Live mode

**Status: blocked.** It needs `EVAL_ANTHROPIC_API_KEY` from the founders. The runner never uses `ANTHROPIC_API_KEY`, and the key in this cloud session belongs to the session tool, not to an eval account.

The runner refuses to start, and sends nothing, when any of these holds (each is tested in `tests/test_ai_live_eval.py`):
- it is running in CI;
- there is no eval key;
- the model has no price;
- more than $250 is asked for the run;
- the program ledger would pass $1,100;
- the worst-case estimate is over the run's limit;
- any case replays differently than in the CI gate.

The last check matters. Outside pytest the app would read `.env`, which on a real machine points Redis and Celery at production. So the runner first applies `evals/ai/sandbox.py`, the same sealed values the tests use, and proves it reproduces the test environment before any spend. Every call is checked against the remaining budget before it is sent.

**Worst-case cost** (dry runs, 2026-10-21): 663 live cases, k=3, about 3,192 calls. "Worst case" assumes every call uses its full output allowance; real spend should be well below it.

| Model | Role (VIC decisions) | Worst case |
|---|---|---:|
| claude-sonnet-4-6 | baseline | $156.52 |
| claude-sonnet-5-5 | candidate | $104.35 |
| claude-haiku-5-5 | candidate for classifiers and judges | $5.22 |
| claude-opus-5-5 | candidate for T30 only (run with `--touchpoints T30`) | full run $208.70 |

Prices are in `evals/ai/model_prices.json`, with source and date. A full baseline plus both candidates fits in one run each and, at worst, about $266 of the $1,100.

**Known blocker for the newer models.** sonnet-5-5, haiku-5-5 and opus-5-5 reject a non-default `temperature`. The gateway sends `temperature=0` on every judge-style call (classification, the verification judge, claim checks). On those models these calls will fail until Phase 3 item I4 removes it. The live run will report them as errors, not hide them.

How to run, once a key exists:
```
python3 -m evals.ai.live_eval --model claude-sonnet-4-6 --dry-run      # estimate, sends nothing
EVAL_ANTHROPIC_API_KEY=... python3 -m evals.ai.live_eval --model claude-sonnet-4-6 --k 3 \
    --max-usd 200 --out docs/program/ai/live/2026-MM-DD-sonnet-4-6.json
```
Re-running the baseline model a second time measures the noise bands, which then go into the gate.

## 5. Model judge

`evals/ai/calibration.json` has no calibrated dimension, so the judge gates nothing. To calibrate a dimension (for example tone):
1. Run it live on at least 10 outputs.
2. The founder labels each output pass or fail.
3. The judge (claude-opus-5-5) labels the same outputs.
4. Record `n` and `agree`. The dimension gates only at 80% or more agreement.

## 6. Not proven

- **Model quality on real models.** Live mode has not run.
- **Sets are synthetic.** Recorded answers were written to be plausible, not captured from a model (`recorded_source: synthetic`). Live runs will show where they are unrealistic.
- **Model-only behaviour.** Where the app has no guard and relies on the model (staying in character, refusing off-topic questions, not inventing facts in a confident answer), offline mode replays a good answer. Only live mode measures these. The sets mark them.
- **Some live cases may still quote recorded text.** A key that quotes the recorded text fails live without the product being wrong. Known ones are marked `live_ignore`. Any others will show up as normal-slice failures on the baseline model and must be reviewed before they count.
- **Live calls bypass the app's own logic in two places.** T02's OpenAI side is a stub, and the live Vapi call (T14/T16) is not run.

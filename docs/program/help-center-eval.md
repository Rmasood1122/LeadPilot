# Help AI: before/after on the golden set (Phase 2, exit gate 2)

Measured 2026-10-11, offline, on branch `claude/help-center`. To reproduce:

```bash
python -m scripts.help_center.measure_golden
```

The command is deterministic: no model, no network, no randomness. The same
numbers are checked on every CI run by `tests/help_center/test_retrieval_eval.py`.
The checks are floors, so a later corpus can do better but not worse.

## What was compared

| | **Before**: old 9-entry FAQ | **After**: help center |
|---|---|---|
| Knowledge | `app/services/support_kb.py` `FAQ` (9 hand-written answers) | `docs/help-center/01…30-*.md` (30 fact-checked articles, 191 chunks) |
| Matcher | `support_kb.best_match`: keyword score, shipped threshold `MIN_MOCK_MATCH_SCORE = 4` | `help_center.mock_match`: BM25 top chunk, then the gate `MOCK_MIN_SCORE = 6.0` and `MOCK_MIN_HEADING_COVERAGE = 0.55` |
| Answer given | the FAQ answer, verbatim | the opening paragraph of the best section, verbatim |

Both sides are compared on the **mock path**: the answer the product gives with
no model call. That is what runs before a key exists, and also what runs when
the key is invalid (permanent-error fallback). This path is the only one that
can be measured offline without making up model output. The live path needs a
real key. Use `scripts/help_center/live_eval.py`; it is opt-in and is never run
in CI. Its results are not in this document because no key was available.

## Golden set

`tests/help_center/golden_questions.yaml` contains 100 items:

- **77 answerable.** These are 45 paraphrases, 8 typos, 7 short queries, 10
  non-native phrasings, and the 7 widget starter questions that the corpus
  answers. Each item lists the chunk ids that answer it, and a hit on any one
  counts.
- **23 must-refuse.** These are 4 off-topic, 4 jailbreak, 4 about other
  vendors' products, 4 asking for legal or financial advice, 6 asking for
  prices or promises the corpus does not contain, and the widget starter "What
  is the tutorial section?", because no article covers the Learn tab.

The questions were written from the user's side first, then mapped to the
sections that answer them. They were not tuned to the retriever. The two
retrieval misses below were left in.

## Definitions

- **answered**: the mock path returned text instead of the ticket message.
- **correct**: the answer came from a chunk listed in the item's `expected`
  ids. For the old FAQ, each entry id is mapped through
  `help_center.LEGACY_FAQ_ALIASES` to the chunk that now covers its topic.
- **wrong**: answered but not correct. Every answer to a must-refuse item
  counts as wrong.
- **answer rate** = answered answerable items / 77.
- **wrong-answer rate** = wrong answers / all answers given, counting both sets.

## Result

| Golden set (mock path) | Old 9-entry FAQ | New help center |
|---|---|---|
| Answerable items answered | 49 / 77 (63.6%) | 42 / 77 (54.5%) |
| ...of which correct | 10 (13.0% of 77) | **39 (50.6% of 77)** |
| ...of which wrong | 39 | **3** |
| Must-refuse items answered | 12 / 23 | **0 / 23** |
| **Wrong-answer rate** | **83.6%** (51 of 61 answers) | **7.1%** (3 of 42 answers) |
| Tickets offered on answerable items | 28 | 35 |

The old FAQ answers more often only because its keyword matcher fires on almost
anything. "How does outreach work?" matched 18 answerable questions it does not
answer, and 4 must-refuse ones.

The old FAQ's 10 correct answers are an upper bound. Three of them came from
entries whose text the corpus contradicts: `how-outreach-works` says "A human
clicks send every time", and `what-is-leadpilot` describes only the 72-step
pipeline and Calendly booking.

The 3 wrong answers that remain in the new corpus:

| Item | Question | Answered from |
|---|---|---|
| q39 | How do I add a teammate to my workspace? | `workspaces-and-agency-mode#what-is-agency-mode-clients` (the right article, wrong section) |
| q50 | what happends when someone unsubscibes | `whatsapp-outreach#what-happens-when-someone-replies-stop` (WhatsApp STOP rather than the email unsubscribe) |
| q70 | how much leads one strategy can have | `plans-limits-billing#how-much-do-the-plans-cost` (prices rather than limits) |

## Retrieval recall@6 (what the live model is shown)

**0.974 (75 / 77).** The target is 0.95. The misses:

| Item | Question | Why |
|---|---|---|
| q11 | What are the ten checks a strategy has to pass? | Six other verification chunks rank above "What are the 10 checks?". `ten` maps to `10` through the synonym file, but the glossary and the verify, re-verify and manual-pass sections use the same words. |
| s03 | How does outreach work? (a widget starter) | Too vague for lexical matching. "outreach" is in nearly every chunk, and "work" matches "Does it work for agencies…". |

Neither miss is fixable without overfitting a synonym to one question. Both are
the kind of miss that embeddings address, which is a separate vendor decision
(STAR_PROMPT 2.3).

## Mock-mode gate: how the thresholds were chosen

Each cell below reads *correct / wrong on answerable | must-refuse answered*.
The values are taken from the full grid that `measure_golden` prints.

| Score floor \ heading-coverage floor | 0.45 | 0.50 | **0.55** | 0.60 |
|---|---|---|---|---|
| 4.0 | 43/5 \| 1 | 40/5 \| 0 | 39/4 \| 0 | 35/2 \| 0 |
| 5.0 | 43/4 \| 1 | 40/4 \| 0 | 39/3 \| 0 | 35/1 \| 0 |
| **6.0** | 43/4 \| 1 | 40/4 \| 0 | **39/3 \| 0** | 35/1 \| 0 |
| 8.0 | 42/4 \| 1 | 39/4 \| 0 | 38/3 \| 0 | 34/1 \| 0 |
| 22.0 (score alone has to reach about 33 to refuse every must-refuse item) | 20/1 \| 1 | 20/1 \| 0 | 20/0 \| 0 | 18/0 \| 0 |

The BM25 score alone cannot separate the two sets. "Can you write the privacy
policy for my own website?" scores 33.2, which is higher than 76 of the 77
answerable questions. The second measurement is **heading coverage**: the
IDF-weighted share of the question's own words that appear in the matched
section's title and question heading, with words the corpus has never seen
counting against the match.

- **0.55** leaves a margin above the closest must-refuse item, the
  privacy-policy question at 0.454. 0.50 is the lowest value that refuses every
  must-refuse item.
- **6.0** sits in the middle of the plateau between 5.0 and 7.0. Within that
  range the score floor changes nothing. 7.5 loses "What is LeadPilot?" (score
  7.1), and 4.0 lets one more wrong answer through.

The same tables and their reasoning are written in the comment above
`MOCK_MIN_SCORE` in `app/services/help_center.py`.

## What each retrieval addition is worth

STAR_PROMPT 2.3 specifies BM25 with lowercasing, punctuation removal, plural
stripping and the synonym file. On its own, that misses the recall target. The
three additions below are deterministic and add no dependencies. Each row
removes one of them.

| Configuration | recall@6 | mock correct | mock wrong | must-refuse answered |
|---|---|---|---|---|
| Shipped (all additions) | **0.974** (75/77) | 39 | 3 | 0 |
| without -ed/-ing stripping | 0.961 (74/77) | 37 | 4 | 0 |
| without typo correction (edit distance 1–2, only for words the corpus never uses) | 0.935 (72/77) | 33 | 2 | 0 |
| without heading word-pairs and whole-heading phrase terms | 0.961 (74/77) | 27 | 4 | 0 |
| without the synonym file | 0.948 (73/77) | 40 | 3 | 0 |
| plain specification (BM25 + plurals + synonyms only) | 0.896 (69/77) | 23 | 4 | 0 |

## Limits of this measurement

- **The live model is not measured here.** Whether a real model refuses the
  must-refuse items is something only `scripts/help_center/live_eval.py` can
  show. The offline tests prove the guards: with FakeClaude scripted to write
  an answer anyway, all 23 items still end on the refusal constant or the
  ticket message.
- **Single-turn only.** Follow-ups get the previous user turn's top 2 chunks
  added to the documents. The golden set does not measure this.
- **The thresholds were chosen on the same 23 must-refuse items they are
  tested on.** New phrasings of legal or vendor questions that reuse the
  product's own headings can still get through. That is why the coverage floor
  was set one step above the minimum.

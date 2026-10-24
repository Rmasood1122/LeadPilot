# Phase 3, item 3: prompt caching on stable prefixes

Written 2026-10-21. Program: `docs/program/STAR_VICTORAE.md` Phase 3 item 3 ("prompt caching on stable prefixes through the gateway; report cache hit rate and cost change from the live eval"). This builds on item 2.

## Where caching can pay, measured first

Caching only applies to a prefix of at least 1,024 tokens on `claude-sonnet-4-6`, and 512 on the 5.x models (Anthropic API reference, read 2026-10-21). A replay of every golden case measured, per touchpoint, the system prompt plus the part of the user prompt shared across cases. The largest were T30 and T31 at about 560 tokens and T17 at about 520; every other touchpoint was smaller.

So at today's prompt shapes, caching would save nothing anywhere. The golden documents are deliberately small, though. Two touchpoints repeat large shared material in production:

- **Verification loop (T30/T31).** Ten passes over one strategy document (real documents run to about 8,000 tokens) plus up to 60,000 characters of research.
- **Research pipeline (T01/T02).** 72 or 144 steps per strategy. Every step of a phase repeats the product, patterns, earlier phases' syntheses and live inputs.

In both, the part that changed (the criterion, the step) came first, so nothing after it could be cached. These two are the item.

## What changed

1. **Gateway.** `complete`/`complete_json(cache_prefix=...)` sends the stable material as a first content block with a 5-minute cache breakpoint, then the varying prompt. Without a prefix the request is byte-for-byte unchanged.
2. **Metering at the real price**, which protects the spend caps. The API reports cache writes and reads apart from `input_tokens`. Metering `input_tokens` alone would under-count every cached call and let the strategy, account and monthly caps (F-AI-01, P0-5, F07) run past their limits.
   - The gateway now meters input-equivalent tokens: input + 1.25 × writes + 0.1 × reads (0.05 × on Opus 5.5, 0.025 × on Fable 5.1). No schema change.
   - The budget pre-check prices a prefix as a cache write.
   - The call log line carries the raw counts.
3. **Verification loop.**
   - Judge: `JUDGE_MATERIAL` (notice, document, research) is the prefix; `JUDGE_QUESTION` (criterion, precedence rule) follows.
   - Fixer: `FIXER_MATERIAL` (document) is the prefix, then `FIXER_QUESTION` (finding). Its retry reads the document from the cache.
4. **Research pipeline.** `PREFIX_TEMPLATE` (product, patterns, earlier phases' syntheses, the phase's signals or playbook) is the prefix. `STEP_TEMPLATE` (this phase so far, the step, its guidance) follows. Consensus sends Claude the prefix and GPT-4o the same text in the same order.
5. **Live runner.** It charges cache tokens the same way and reports raw token totals and `cache_hit_rate`.

In items 3 and 4 the question now follows the long material it is about, which the item-5 prompt guidance also asks for. The wording of every instruction is unchanged.

## Proven offline

| Check | Result |
|---|---|
| Gateway places the breakpoint only with a prefix; meter receives write and read prices; pre-check prices the prefix as a write (`tests/test_prompt_caching.py`) | pass; 9 of 10 fail on the old gateway |
| All judge passes of both flows send one byte-identical prefix with no criterion in it; the fixer's retry sends the same prefix | pass; fail on the old layout |
| 18 real pipeline steps: each phase's 9 steps send one byte-identical prefix; the next phase's adds the new synthesis; no step text leaks in | pass; fails on the old layout |
| Live runner prices cache tokens and counts them for the hit rate | pass |
| Pipeline, consensus, registry and verification tests (subdirectories included) | 5,104 + 2,048 passed |
| PostgreSQL integration suite: end-to-end pipeline against the HTTP Anthropic mock | 155 passed |
| Evals (T01, T02, T30, T31 and all others) | unchanged: all pass; 53 known defects still strict-xfail |

## Evidence run (clean worktree, commit `619ac0e`, tree `a84be15`)

| Command | Result |
|---|---|
| `scripts/gate/quick_gate.sh` | 8/8 PASS, stamped; tests step 3,967 passed, 53 xfailed |
| `python3 evals/run_evals.py` | exit 0; 7,872 tests; full and compliance pass rate 1.0 |
| `python3 evals/tools/promote.py` | **PROMOTE**, 1 soft WARN on runtime (1,651 s vs 900 s), as on #121 and #122 |
| `python3 evals/fixtures/verify_block_fixtures.py` | all 3 hard gates fire |

## Not measured: hit rate and cost

The exit gate asks for cost from metering, not estimates. **There is none yet: live mode is blocked on the eval key.** When it runs, the live report's `cache_hit_rate` and `spent_usd` are the measure, and production's `ApiUsage` rows now carry billed tokens.

For planning only, an **ESTIMATE, not evidence**, for one verification run with a document plus research of about 23,000 tokens and ten passes:

- Uncached input: about 230,000 token-equivalents.
- Cached: one write (about 29,000) plus nine reads (about 21,000), so about 50,000. That is roughly 78% less judge input.
- This assumes each judge call starts within 5 minutes of the previous one. A fixer rewrite between passes can take minutes, so a pass after a long fix may miss.

The pipeline saving depends on phase sizes and is not estimated here.

## Limits

- **Small prefixes do nothing.** Early pipeline phases may have prefixes under 1,024 tokens on sonnet-4-6. They are not cached, at no extra charge.
- **Other touchpoints stay uncached.** They have short or per-lead prompts.
- **Prompt order changed for T01, T02, T30 and T31.** Answer quality under the new order is a live-eval question; the offline sets cannot measure it.

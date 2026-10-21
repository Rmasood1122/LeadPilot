# Phase 3, item 4: Batch API, decision record

Written 2026-10-21. Program: `docs/program/STAR_VICTORAE.md` Phase 3 item 4 ("Batch API for non-interactive pipeline phases where latency does not matter; report cost change").

**Decision: not built. The premise does not hold for the pipeline, and the real candidates cannot be sized yet.** This record is the item's deliverable. Building it waits on volume data from the founders (below).

## Why the pipeline cannot be batched

Message Batches run requests asynchronously, usually within an hour and at most 24 hours, at 50% of the price. They suit calls that are independent of each other and that nothing is waiting on. Two qualifiers in the item fail:

- **Research pipeline** (`app/pipeline/engine.py:76-150, 198`). Every step reads the earlier steps of its phase and the earlier phases' syntheses, so the 144 steps of one strategy are a chain. Steps could only be batched *across* strategies, one step per strategy per batch. A strategy would then take up to a day per step instead of minutes, and the user watches its progress.
- **Verification loop** (`app/verification/loop.py:321-353`). Each judge reads the document as the previous pass fixed it, so it is also a chain.

Item 3 already cuts what these two cost, through prompt caching.

## Never batch these

| Call | Why |
|---|---|
| Message rendering and claim verification on the send path (`outreach_tasks.py:1104-1123`) | the message sends right after; the claim check gates the send |
| Reply classification, fraud, intent and intelligence; Copilot (`reply_tasks.py:34-105`) | decides opt-out and consent; Copilot can auto-send |
| Call analysis (`phone_calls.py:409`) | records stop requests |
| Meeting prep (`calendar_tasks.py:213`) | the meeting may be less than an hour away |
| Anything interactive (support chat, roleplay, network messages, follow-ups, templates, ICP intake, style and voice profiles) | a person is waiting |

## Candidates, ranked (read-only inventory, 2026-10-21)

| # | Call | Why it fits | What a batch changes |
|---|---|---|---|
| 1 | Displacement DMs (`displacement_monitor.py:208`, beat every 12h at `celery_app.py:422`) | scheduled; fan-out across every strategy; the alert does not need the DM | first attempts in a batch; the one repair attempt goes in a second poll |
| 2 | Idle-strategy mutation (`strategy_mutation.py:306`, nightly at `celery_app.py:339`) | independent; the result is a proposal | small fan-out, zero risk |
| 3 | Lead scoring and Loom scripts after a lead batch, and `rescore_strategy` (`lead_scoring.py:226`, `loom_video.py:110`) | independent chunks of 15; failure already falls back to a heuristic | Loom must move into the poll step, because it reads the score |
| 4 | F-P-T-A at enrollment, Autopilot path (`fpta_scoring.py:378`) | independent chunks of 10; never blocks a send | the synchronous HTTP rescore stays synchronous |
| 5 | Website bulk generation (`website_builder.py:276`) | independent pages | the user sees pages arrive later |

## What building it needs

- **Submit and poll.** A submit task records each `batch_id` against its rows. A new beat entry polls and applies results; the free slots are around the :03, :05, :07 and :11 entries at `celery_app.py:253-512`. Storing batch IDs likely needs a table or column, which is a migration.
- **Metering at the batch price.** `usage_meter.note` and `check_budget` assume per-call pricing. Batch results need the 50% price, or the spend caps over-count. Item 3's input-equivalent approach extends to this.
- **Same request body.** The batch request must reuse the gateway's: caching, structured outputs and temperature handling.
- **Failure handling.** An expired or failed batch request must fall back exactly as the synchronous call does today: heuristic score, alert without a DM, and so on.

## What decides it: volume

Batching saves 50% of what the candidates cost. Whether that is worth a migration, two tasks and a second failure path depends on how much the candidates actually spend. That is the `api_usage` query the founders have been asked for (read-only):

```sql
SELECT purpose, provider, model, SUM(calls) AS calls,
       SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens
FROM api_usage
WHERE created_at > now() - interval '30 days'
GROUP BY purpose, provider, model
ORDER BY output_tokens DESC;
```

**Recommendation:** build it, starting with candidate 1, if the candidates together spend more than about $50 a month (a saving above $25 a month). Below that, the extra failure path is not worth it. This is a proposal for the founders to confirm or replace with their own threshold.

## Cost change

None: nothing was built, so there is nothing to meter.

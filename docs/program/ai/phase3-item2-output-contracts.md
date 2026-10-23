# Phase 3, item 2: output contracts

Written 2026-10-21. Program: `docs/program/STAR_VICTORAE.md` Phase 3 item 2 ("replace free-text parsing with structured outputs or tool calls where the gateway supports them"). This builds on item 1, PR #122.

## What changed

- **Gateway** (`app/services/anthropic_client.py`). `complete_json(schema=...)` sends the schema as `output_config.format` (structured outputs) only when the configured model is in `STRUCTURED_OUTPUT_MODELS`. The list comes from the Anthropic API reference, read 2026-10-21: Fable 5/5.1, Opus 5.5/5/4.8/4.5/4.1, Sonnet 5.5/5 and Haiku 5.5/4.5; a dated ID counts as its family. On those models the reply can only be JSON of that shape. Constrained decoding replaces the prompt-and-regex contract.
- **Every call names its schema.** All 38 `complete_json` calls in `app/` pass a module-level `*_SCHEMA` (39 schemas). Each describes exactly the keys and types its code reads after its own coercion.
- **Enums only where the prompt names a closed set and the code maps exactly that set.** Examples: reply routing classes, reply-intelligence categories, not-now reason kinds, claim categories, call outcomes, meeting sentiment and owner, the red-team category. On a structured-output model, a consent miss such as `unsubscribe` instead of `unsubscribe_request` can then no longer be emitted.

## Why nothing changes today

`claude-sonnet-4-6`, the current default, is **not** on the structured-outputs list. On it the request is byte-for-byte unchanged, and the call sites' existing parsing and guards remain the contract. Those guards were proven by the Phase 2 sets and kept untouched by this item.

The benefit arrives with a model change (item 6, founder-approved candidates only). The parsing code stays the safety net in both cases.

## How it is proven (offline)

| Check | Result |
|---|---|
| Gateway sends the schema to supported models only (`tests/test_output_schemas.py`) | pass; covers 4 supported IDs, 3 unsupported, and no schema |
| Every schema is one the API accepts: valid JSON Schema, every object closed, required fields exist, no rejected keyword (`minimum`, `maxLength`, `minItems`, …) | 39/39 |
| Every `complete_json` call passes a schema (AST scan of `app/`) | 38/38, now enforced (a new call without one fails CI) |
| Every **good** recorded answer in the golden sets validates against the schema its call sent | all live-eligible cases. A deliberately wrong schema turned T07 red. |
| Golden sets | 1,173 passed, 53 xfailed (unchanged from item 1) |
| Sealed tests | 801 passed, untouched |

The fourth check is the one that matters. On a constrained model, a schema that forbids an answer the app accepts would silently block good output. That would only show up live, so it is caught offline here instead.

## Known limits

- **WhatsApp variables are listed as keys "1" to "20"**, in `WHATSAPP_VARIABLES_SCHEMA` and in template variable descriptions. The API rejects `patternProperties`. On a constrained model, a template with more placeholders cannot be fully filled. Missing values fail closed; none are invented. Bodies are length-limited, so this is unlikely.
- **The website page's `schema_markup` lists common JSON-LD keys**, because every object must be closed. The stored field (`SitePage.schema_markup_json`) is read nowhere. Published pages carry their JSON-LD inside `html_content`, a free string the schema does not constrain.
- **No live measurement.** Structured outputs apply only to the candidate models, which need the eval key and the temperature fix (I4). sonnet-5-5, haiku-5-5 and opus-5-5 reject `temperature`, which the gateway sends on judge calls.
- **Refusals.** On a constrained model, a `stop_reason: "refusal"` reply may not match the schema. The gateway then raises the usual `ValueError`, so the call fails closed.

# I4: gateway temperature on newer models

Written 2026-10-21. Founder backlog item I4 (gateway modernisation); a prerequisite for Phase 3 item 6 (model candidates).

## What changed

The gateway sends `temperature=0` on every judge-style call: reply routing, verification judge, claim extraction and the rest (F-AI-03). According to the Anthropic API reference (read 2026-10-21), the newer models reject that with HTTP 400:
- **Parameter removed:** Fable 5/5.1, Opus 5.5/5/4.8/4.7, Sonnet 5.
- **Only the default accepted:** Sonnet 5.5, Haiku 5.5.

On any of these models, every judge call would fail.

`anthropic_client.TEMPERATURE_FREE_MODELS` lists them. On those models the gateway omits `temperature` and logs that it did. On every other model, including the current default `claude-sonnet-4-6`, the F-AI-03 pin to 0 is sent exactly as before. **Production behaviour is unchanged.**

## What the founders accept with a model change (item 6)

On a temperature-free model, a judge cannot be pinned, so a verdict's reproducibility is no longer guaranteed by construction. That includes legal ship-blocker pass #4. It becomes a measured property: the live eval's **pass^3 per safety slice**. A safety slice must be 1.0 for a candidate to be gated in. Item 6 presents that number per candidate, and no default model changes without founder approval.

## Not done; for the live run to show

On these models thinking is on by default, and thinking tokens count against `max_tokens`. Short-budget calls could stop at the ceiling: the claim extractor at 800 tokens, the classifiers, the judge. The gateway raises `TruncatedResponseError` on that, which fails closed and is never stored half-written. The live run reports these as errors. Fixing them (an explicit low `effort`, or larger budgets per call) is tuned against those numbers, not guessed offline.

## Proof

`tests/test_gateway_temperature.py` drives the real `ClaudeClient`:
- the 9 temperature-free models never receive `temperature`; all 9 fail on the old gateway;
- judges stay pinned to 0 on the 4 models that accept it, with dated IDs included.

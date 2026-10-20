# AI inventory — every model call and every manual workflow AI could take over

Phase 0, step 4 of `docs/program/STAR_VICTORAE.md`. Read-only, at program start SHA
`7872f9c6d4cda7796d43ed3fe486799a197ed74d` (2026-10-20). Two subagents swept the code; the
headline claims below were re-checked by hand (gateway request shape `app/services/anthropic_client.py:216-228`,
personalization wrapping `app/services/personalization_context.py:160-197`, raw headlines
`app/services/market_intel.py:306`, raw roleplay persona `app/services/roleplay.py:210-216`).
**No test, eval or model call was run for this file.** Everything comes from reading code and docs.

## Summary for the founders

| Question | Answer | Evidence |
|---|---|---|
| How many AI touchpoints? | **36**: ≈33 call sites in 30 modules through the gateway, 1 OpenAI GPT-4o path (consensus, off by default), 2 voice LLMs (Vapi inherits `anthropic_model`; ElevenLabs model is set in their dashboard, not in code), manual scripts | Part A §0–§1 |
| Default model | `claude-sonnet-4-6` — one global model, no per-task routing, duplicated in 4 places | `app/config.py:46`, `app/core/config.py:77`, `app/integrations/voice_providers.py:173`, `scripts/activate_with_keys.py:152` |
| Is the default model still supported? | Yes. Anthropic lists `claude-sonnet-4-6` as **Active**, retirement not sooner than 2027-02-17 (platform.claude.com model-deprecations, read 2026-10-20) | — |
| Prefill on last turn? | **None.** Every request is one user message | `anthropic_client.py:219-224` |
| `budget_tokens` / thinking? | **None** | grep, Part A §2 |
| **Blocker for newer models** | The gateway sends `temperature=0.0` on every judge call (`JUDGE_TEMPERATURE`, `anthropic_client.py:110`; set at `:225-228`, `_set_temperature` `:139-152`). Anthropic's docs (read 2026-10-20): `temperature`/`top_p`/`top_k` at a non-default value **return HTTP 400 on Claude 4.7 and later**, and the Python SDK ≥1.0 removes them (the lock pins `anthropic==1.11.0`; the gateway already works around that via `extra_body`). **Every Claude 4.7+ candidate (Opus 4.7/4.8/5/5.5, Sonnet 5/5.5, Haiku 5.5, Fable) will fail on judge calls until the gateway stops sending temperature for those models.** | platform.claude.com/docs/en/about-claude/model-deprecations |
| Prompt injection in `personalization_context.py` (audit ~146–176) | **Fixed at that site** (F-AI-02): posts wrapped `:170`, news `:184-187`, notice `:197` | verified by hand |
| Untrusted text still reaching prompts **unwrapped** | `meeting_prep.py:318-336` (posts, news, enrichment, replies); `loom_video.py:89-94`; `market_intel.py:306` (news headlines → pipeline Phase 1/3); `roleplay.py:213-215` (prospect objections in the system prompt); lead fields in `message_personalization.py:274-277,422-424,512-514`, `linkedin_outreach.py:152`, `phone_calls.py:213,264`, `network_messages.py:87`, `meeting_followup.py:276`; style/voice profiles from user samples appended to every outbound system prompt | Part A §2 row 1 |
| Prompt caching | **Unused** (no `cache_control`). But the audit's "~12k-token stable prefixes" premise is wrong as stated: every system prompt is ≤466 tokens, below the 1,024-token cache minimum. Large repeated content sits in user prompts and is not ordered stable-first. Biggest win: verification judge re-sends a ≈15k-token document across 10 passes with the per-pass criterion placed **before** the document (`app/verification/passes.py:60-71`) | Part A §2 row 2 |
| Batch API | **Unused.** Candidates: pipeline steps across strategies, 10 initial verification judgements, consensus judge, lead/F-P-T-A scoring, meeting prep, website pages | Part A §2 row 3 |
| Output contracts | No tool use or structured outputs anywhere. `complete_json` strips fences, `json.loads`, then a regex over the outer `{…}`; no schema validation in the gateway; each caller coerces fields | `anthropic_client.py:271-294` |
| Consent-critical AI | Email opt-out detection in the hot path relies on the LLM classifier only (`app/services/reply_classification.py:81`); the keyword check in `app/agents/reply_triage.py` is an after-the-fact report. Call stop-request detection (`app/services/phone_calls.py:357`) runs at default temperature and, after 3 failed analyses, **the stop request is never recorded** (fails open) | Part A T06, T15 |
| Real-model tests | **None** in pytest. `FakeClaude` (`tests/conftest.py:155`) everywhere; `tests/test_offline_guard.py` blocks sockets | Part A §0 |
| Eval-gate coverage of AI | **Zero.** `evals/registry.yaml` gates 4 metrics: compliance pass rate, full pass rate, test count ≥3,150, runtime. No quality, injection, cost or latency metric | Part A §4 |
| Live evals that exist | `scripts/help_center/live_eval.py` and `scripts/support_chat_adversarial.py` (support chat only). **Never run with results recorded** ("no key was available", `docs/program/help-center-eval.md`) | Part A §4 |
| Metering | Every gateway call metered to `api_usage` (`provider, model, purpose, calls, input_tokens, output_tokens, cost_micros, ts`; `app/db/models.py:3412-3436`). Prices are **per provider, not per model**: Claude $3/$15 per MTok (`app/services/system_settings.py:74-77`), no cache/batch tiers, `cache_read_input_tokens` ignored (`anthropic_client.py:251-253`). Changing the model or adding caching/batch makes reported cost wrong until the meter learns per-model and per-token-class prices | Part A §3 |
| Cost per call from metering | **Not available in this session.** Metering data lives in production Neon; this session has no database access. All cost figures below are code/doc estimates. Query for the founders is in `plans/victorae-00-recon.md` §5 | — |
| Daily cap coverage | Per-message AI (personalization, claim checks, meeting prep, reply handling, launch, support chat) is **counted but never stopped** (`app/services/usage_meter.py:83-88`) | Part B §2.2 |

## Other discrepancies found (reported, not fixed)

- `CLAUDE.md` says "five sealed compliance test files" and "3,319 tests"; `evals/compliance_testset.yaml` lists 31 files and `evals/baseline.json` has a count mean of 5,981.
- `evals/baseline.json` runtime mean 1,020 s is above the 900 s soft threshold (soft metric WARNs).
- `docs/program/help-center-eval.md` describes a 100-item golden set; the file holds 182 (151 answerable + 31 must-refuse).
- `app/services/embeddings_client.py` (Voyage, decided as HELPAI-VENDOR) does not exist.
- `app/services/support_chat.py:94-96` asserts the header is cacheable; it is below the 1,024-token minimum.
- F-AI-04 (startup check that the configured model id is valid) is still open.
- Defect #30 (ICP stored nested, read flat: `fpta_scoring.py:393`, `lead_scoring.py:215`, `market_intel.py:104`) makes industry fit always 50% and ignores problem keywords; it feeds F-P-T-A, lead scoring and meeting-prep briefs.

---

# Part A — Model touchpoints (36)


Repo: `/home/user/LeadPilot`, branch head `b52c08f` (identical to `7872f9c` in code; it only adds program docs). Swept 2026-10-20. Nothing in the repo was modified.
Method: I read `app/services/anthropic_client.py` in full. I found callers with `grep anthropic_client|get_client|messages.create|import anthropic|openai|voyage|vapi|elevenlabs`, read each call site with its prompt builder and error handling, and measured prompt-constant sizes with an AST script (chars/4 ≈ tokens). The app modules cannot be imported here because sqlalchemy and anthropic are not installed. **No test or eval was executed.** Every statement below comes from reading the code.

## 0. The gateway: `app/services/anthropic_client.py` (305 lines)

| Aspect | Finding (file:line) |
|---|---|
| Exports | `ClaudeClient.complete()` (:188), `ClaudeClient.complete_json()` (:271), `get_client()` lazy singleton (:300), `JUDGE_TEMPERATURE=0.0` (:110), `is_permanent_error()` (:62), `TruncatedResponseError` (:155), `RETRYABLE_API_ERRORS` / `PERMANENT_API_ERRORS` (:32/:49) |
| Model | `settings.anthropic_model`, default **`claude-sonnet-4-6`** (`app/config.py:46`). Duplicated in `app/core/config.py:77`, `scripts/activate_with_keys.py:152` and `app/integrations/voice_providers.py:173` (Vapi fallback). `app/verification/loop.py:54` says its 128k output cap was "confirmed live". One global model: there is no per-call model selection and no Haiku tier. |
| Request shape | `model, max_tokens, system=<str>, messages=[{"role":"user","content":prompt}]` (:219-224). Always exactly one user turn. **No assistant prefill, no tools, no `thinking`/`budget_tokens`, no `cache_control`, no `stop_sequences`, no `metadata`.** |
| max_tokens | Default `settings.anthropic_max_tokens=4096` (`app/config.py:47`). Above 20,000 the gateway switches to `messages.stream()` (:96, :229-238). |
| Temperature | Sent only when the caller passes it (:225-228). Judges pass 0.0. If the SDK signature lacks `temperature`, the gateway falls back to `extra_body` (:113-152). Generation runs at the API default. |
| Retries | tenacity on 429/5xx/529/connection/timeout, `anthropic_max_retries=3` (`app/config.py:49`), exponential 2–60 s (:182-187). 4xx errors are permanent. |
| Truncation | `stop_reason=="max_tokens"` raises `TruncatedResponseError` (:261-268). The response is metered before the raise. |
| JSON parse | `complete_json` strips ``` fences, runs `json.loads`, falls back to a regex over the outermost `{...}`, and otherwise raises `ValueError` (:285-294). There is no schema validation in the gateway; each caller coerces fields itself. |
| Metering / caps | Before each call: `usage_meter.warn_if_unscoped` + `check_budget(input_chars, max_output_tokens)` (:215-218). The worst-case reserve is chars/3 × input price + max_tokens × output price (`usage_meter.py:93, 299-345`). It enforces the per-strategy budget and the per-account daily cap and raises `BudgetExceededError`. After each call: `usage_meter.note(provider, model, in, out)` (:251-253), which writes to the `ApiUsage` table (cost_micros) on flush. |
| Batch API | **Not used anywhere** (`grep message_batches|batches.create` returns nothing). |
| Prompt caching | **Not used anywhere** (no `cache_control` in `app/`). The gap is acknowledged in a comment at `app/services/support_chat.py:94-96`. |

### Direct SDK and other model paths that bypass the gateway
| Path | file:line | Notes |
|---|---|---|
| Anthropic SDK direct | `scripts/activate_with_keys.py:147-160` | Key-check script. `messages.create(model, max_tokens=8, "Reply with the word OK.")`. Not metered. Manual setup tool. |
| Anthropic Models API (httpx) | `app/services/health_checks.py:129-150` | `GET /v1/models` reachability probe. No generation and no token cost. |
| OpenAI Chat Completions (httpx) | `app/integrations/openai_client.py:40-87` | Consensus second opinion only. Model `gpt-4o` (:31; system setting `consensus_openai_model`, `system_settings.py:39`), temperature 0.4 (:46), max_tokens 4096. Metered through `usage_meter` with provider `openai` (:52-54, :74). |
| Vapi live-call LLM | `app/integrations/voice_providers.py:173` (`vapi_assistant`) | `{"provider":"anthropic","model": settings.anthropic_model or "claude-sonnet-4-6"}`, set from `voice_providers.py:455` with the system prompt in `messages[0]`. Tools: `endCall`, optional `transferCall` and booking tools (inbound). The LLM runs **inside Vapi**: it is billed by Vapi and is **not** token-metered (only `voice_cost_per_minute=0.15`, `system_settings.py:82`). |
| ElevenLabs agent LLM | `app/integrations/voice_providers.py:406-425` | Overrides only `conversation_config_override.agent.prompt`. The model is whatever is configured on the ElevenLabs agent in their dashboard, so it is **not specified in code**. |
| Voyage embeddings | — | Decided in `docs/program/DECISIONS.md:42` (HELPAI-VENDOR). `app/services/embeddings_client.py` **does not exist**: not implemented. |
| `app/mcp/tools/chatgpt.py` | — | An MCP server consumed BY ChatGPT. It makes no outbound model call. |
| Frontend / Android / SDK | — | No LLM calls. The SDK only prompts for `ANTHROPIC_API_KEY` (`sdk/src/clienthunter/cli/_serve.py:237`). |

**Common to every gateway touchpoint below:** model `claude-sonnet-4-6`, no caching, no batch, no thinking, no prefill. The pytest suite has **no** real-model test: `FakeClaude` (`tests/conftest.py:155`) is monkeypatched onto `get_client`, and `tests/test_offline_guard.py` fails any test that opens a non-loopback socket. Real-model checks exist only as manual scripts (§3).

---

## 1. Touchpoints

Legend: **UNTRUSTED-WRAPPED** means the text is delimited with `prompt_safety.block/inline` under `prompt_safety.NOTICE` (`app/services/prompt_safety.py:27-60`, F-AI-02). **UNTRUSTED-RAW** means outside text reaches the prompt with no delimiter or notice.

### T01 — Research pipeline step (72/144 steps)
| | |
|---|---|
| Call | `app/pipeline/engine.py:187` `claude.complete(system=SYSTEM_PROMPT, prompt)`; on synthesis steps through `consensus.run_step` (`consensus.py:167/177`) |
| Purpose | One GTM research step; the 8 phase syntheses are assembled into `strategy_document` (`engine.py:227-251`) |
| Prompt | `app/pipeline/registry.py:25` PROMPT_TEMPLATE (654 ch ≈163 tok); SYSTEM_PROMPT `registry.py:46` (210 ch ≈52 tok); blocks built in `engine.py:76-157` |
| Inputs | Product name/description (user); past-client patterns (model-extracted from user text, T29); prior step outputs (model); playbook insights (`PlaybookService`); **live market signals** at Phase 1/3: Google News/NewsAPI headlines via `market_intel.signals_block` (`market_intel.py:285-307`). **UNTRUSTED-RAW**: `market_intel.py:306` writes `- {sig['title']}` with no prompt_safety; the only guard is a "HEADLINES, not verified facts" caveat (:295-297) |
| Output | Free markdown, persisted to `research_steps` as is. Failure raises, and the Celery task retries or stops (`workers/tasks.py` uses `is_permanent_error`). Truncation at 4096 raises (fail closed) |
| Params | max_tokens 4096 (default), API-default temperature |
| Caching | None. The prefix is not cache-friendly: step name and guidance come *before* the large `context_block` (which grows up to ~8 prior steps + syntheses), and the system prompt is ~52 tok, below the 1024-token minimum. Reordering to stable-first would be needed |
| Mode | Background Celery pipeline: **strong Batch API candidate**, except steps within a phase are sequential (each step reads earlier ones), so batching works only across strategies or with per-phase fan-out |
| Action risk | None directly. The output feeds the playbook used by every outbound message (T03) |
| Tests | `tests/test_strategy_budget.py`, `tests/test_regression.py`, `tests/integration/mocks/anthropic_mock.py` (transport mock). No real-model test. Live: `scripts/phase_c_pipeline.py` (manual) |
| Evals | None |

### T02 — Consensus: GPT-4o parallel answer + Claude consensus judge
| | |
|---|---|
| Call | OpenAI `consensus.py:175` (`openai_client.py:40`); judge `consensus.py:136` `complete_json(..., max_tokens=2048, temperature=0.0)` |
| Purpose | On synthesis steps, a second model answers the same brief, and the Claude judge lists medium/high disagreements as "uncertain zones" |
| Prompt | JUDGE_SYSTEM `consensus.py:57` (814 ch ≈203 tok); judge prompt `consensus.py:128-132` (A/B anonymised, 14k chars each) |
| Inputs | Model outputs only (indirectly the T01 inputs, including raw headlines) |
| Output | JSON `{disagreements:[...]}`, coerced and severity-filtered (`:139-152`). Judge failure: no zones, `consensus_status="partial"` (fail open, by design; informational) |
| Params | Judge: Sonnet, temp 0, 2048. OpenAI: gpt-4o, temp 0.4, 4096 |
| Caching / Mode | None / background (Batch candidate for the judge) |
| Action risk | None (advisory) |
| Tests | `tests/test_ai_intelligence.py`, `tests/test_metering_coverage.py`. No real model |

### T03 — Outbound email (and WhatsApp free-text) personalization
| | |
|---|---|
| Call | `app/services/message_personalization.py:164` `complete_json(system=_SYSTEM + voice, prompt=_PROMPT...)` |
| Purpose | Writes the subject and body of every sequence email at send time. The WhatsApp in-window text reuses it (`outreach_tasks.py:1269`); Quickstart previews use it too (`quickstart.py:389`) |
| Prompt | `_SYSTEM` :18 (470 ch ≈117 tok) + `style_profile.suffix_for_strategy`; `_PROMPT` :29 (301 ch). Playbook = Phase-6 synthesis + applied mutation + local-business block (`:47-65`) |
| Inputs | Lead name/title/company/enrichment **UNTRUSTED-WRAPPED** (`:176-179`). LinkedIn posts + company news through `personalization_context.prompt_block` **UNTRUSTED-WRAPPED** (`personalization_context.py:170, 184-187, 197`). Signal Radar `why_now` wrapped (`signal_radar.py:445-457`). The step brief has a voice-profile suffix (founder posts → model-derived profile) |
| Output | JSON `{subject, body}`. Empty body raises `ValueError`, so the send fails (fail closed). Subject falls back to "Quick question" (`:183-187`) |
| Params | 4096 max_tokens (default), API-default temperature (deliberate, `anthropic_client.py:98-109`) |
| Caching | None. Large stable per-strategy content (playbook, often 1–3k tok) sits mid-prompt after the per-lead NOTICE/brief. A cache candidate if restructured (system + playbook first, lead last) |
| Mode | Celery send path (`outreach_tasks.py:1114`). Rendered just in time before send, so Batch is only usable if rendering moves ahead of send |
| Action risk | **SEND**: the output is transmitted. Gates after generation: `claim_verification.enforce` (T05; `outreach_tasks.py:1120-1124`), compliance footer `build_compliant_email`, plus send_message_impl gates (suppression, daily approval/review queue, caps) |
| Tests | `tests/test_outbound_injection_containment.py`, `tests/test_followup.py`, `tests/test_reengagement.py`, `tests/test_personalization.py` (FakeClaude). Live: `scripts/phase_c_pipeline.py` |
| Evals | None |

### T04 — WhatsApp template variable filling
| | |
|---|---|
| Call | `message_personalization.py:267` |
| Prompt | `_WA_SYSTEM` :194 (425 ch) + voice suffix; `_WA_PROMPT` :204 |
| Inputs | **UNTRUSTED-RAW**: `full_name`, `title`, `company` and `str(enrichment)[:1500]` are inserted unwrapped (`:274-277`), unlike T03 |
| Output | JSON `{"1": "...", ...}`. A missing value raises `ValueError`, so the send fails (closed) (`:280-288`). Then `claim_verification.enforce` on each variable (`outreach_tasks.py:1305-1309`) |
| Params / Caching / Mode | 4096 default, API temperature / none / Celery send path |
| Action risk | **SEND** (WhatsApp template message to the lead) |
| Tests | `tests/test_whatsapp*.py` (FakeClaude) |

### T05 — Claim extraction (claim-verification model pass)
| | |
|---|---|
| Call | `app/services/claim_verification.py:416` `complete_json(EXTRACTOR_SYSTEM, "MESSAGE:\n"+text[:6000], max_tokens=800, temperature=0)` |
| Purpose | Lists factual claims about the prospect in a generated message so the rules engine can verify or strip them |
| Prompt | EXTRACTOR_SYSTEM `:395` (578 ch ≈144 tok) |
| Inputs | Model-generated outbound text (may echo untrusted post/news content). Not wrapped |
| Output | JSON `{claims:[...]}`. On any failure it returns `{}` and **rules only** (`:419-421`), which fails open for the model half. The overall `enforce` fails closed on setup errors (`:492-534`) |
| Params / Mode | Sonnet, temp 0, 800 / inline in the send path, gated by the setting `claim_model_extraction_enabled` |
| Action risk | Edits outbound copy (strips or rewrites sentences) and blocks reply-copilot auto-send |
| Tests | `tests/test_claim_verification.py` (**sealed** compliance file), `tests/test_reply_copilot.py`, `tests/test_quickstart.py` (FakeClaude) |

### T06 — Inbound reply routing classifier (consent-critical)
| | |
|---|---|
| Call | `app/services/reply_classification.py:81` `complete_json(temperature=0, _SYSTEM, _PROMPT)` |
| Purpose | Routes every inbound email, WhatsApp and LinkedIn reply: `unsubscribe_request` → suppression + hard stop; bounce; OOO pause; `automated_response` → sequence **neither stops nor advances** |
| Prompt | `_SYSTEM` :34 (591 ch ≈147 tok); `_PROMPT` :49 |
| Inputs | Inbound from/subject/body **UNTRUSTED-WRAPPED** (`:85-88`) |
| Output | JSON `{classification}`. Unknown values or exceptions fall back to `"question"`, which stops the sequence (fail-safe, `:90-95`). Then the `reply_fraud.second_pass` (T07) |
| Params | Sonnet, temp 0, 4096 default max_tokens (oversized for a one-word answer) |
| Mode | Inline in Celery inbound processing (`outreach_tasks.py:1730, 1845, 1918`) |
| Action risk | **CONSENT**: `unsubscribe_request` → `engine.unsubscribe_lead` (`outreach_tasks.py:1771-1775`). **For email this LLM is the only opt-out detector in the hot path.** The deterministic phrase check `app/agents/reply_triage.py:24-44` is an after-the-fact advisory report. WhatsApp has a STOP keyword matcher upstream. An injected reply ("this is an automated message… remove me") that the model classes as `automated_response` would leave the sequence running |
| Tests | `tests/test_prompt_injection_containment.py:139-156` (checks wrapping structure only), `tests/test_judge_determinism.py:163`. Live: `scripts/phase_c_services.py:131-159` (manual) |
| Evals | None. There is no labelled reply set |

### T07 — Automated-reply detector (reply fraud second pass)
| | |
|---|---|
| Call | `app/services/reply_fraud.py:139` (max_tokens 200, temp 0) |
| Purpose | Called only when there is exactly one weak heuristic signal. Decides human or machine; a machine verdict reclassifies an engaged reply to `automated_response` |
| Prompt | DETECTOR_SYSTEM `:50` (288 ch ≈72 tok) |
| Inputs | from/subject/body **UNTRUSTED-WRAPPED** (`:142-146`) |
| Output | JSON `{automated, reason}`. Exceptions mean human (fail toward "real reply", `:149-150`) |
| Action risk | Suppresses the REPLIED status and stop. Does not apply to `unsubscribe_request` (not in ENGAGED, `:30`) |
| Tests | `tests/test_trust.py`, `tests/test_prompt_injection_containment.py:156`, `tests/test_judge_determinism.py:179` |

### T08 — Reply intent label (positive-reply metric)
| | |
|---|---|
| Call | `app/services/reply_intent.py:194` (MAX_TOKENS 400 `:71`, temp 0) |
| Prompt | `_SYSTEM` :74 (1077 ch ≈269 tok); `_PROMPT` :99 |
| Inputs | Reply **UNTRUSTED-WRAPPED** (`:198-200`); our original message unwrapped (ours) |
| Output | JSON `{label, confidence, reason}`. An invalid label raises and leaves the reply UNCLASSIFIED (closed, `:206-207, 211-219`). `not_now` feeds T10 |
| Mode / Action | Celery reply task / analytics, plus a trigger for re-engagement planning |
| Tests | `tests/test_reply_intent.py`, injection containment `:166-173` |

### T09 — Reply intelligence (category + human draft)
| | |
|---|---|
| Call | `app/services/reply_intelligence.py:181` (`_ask`, MAX_TOKENS 1000, temp 0, used for the draft too), repair attempt for banned words |
| Prompt | `_SYSTEM` :102 (1032 ch ≈258 tok); `_PROMPT` :124 |
| Inputs | Reply body + lead name/company/title **UNTRUSTED-WRAPPED** |
| Output | JSON `{category, confidence, next_action, draft_response}`. Unknown category becomes OBJECTION; failure leaves the fields unset |
| Action risk | `BUYING_SIGNAL` moves the enrollment's `current_step` to 3 (status unchanged); `NOT_NOW` sets a reschedule date. The draft is never sent by this module |
| Tests | `tests/test_reply_intelligence.py`, injection containment `:190-199` |

### T10 — Re-engagement "not now" extraction
| | |
|---|---|
| Call | `app/services/reengagement_memory.py:263` (max_tokens 400, API temperature) |
| Prompt | `_SYSTEM` :117 (1152 ch ≈288 tok); `_PROMPT` :141 |
| Inputs | Reply **UNTRUSTED-WRAPPED** (`:267-269`) |
| Output | JSON `{reason_kind, reason_text, return_on}`. Past dates are rejected. On failure the rules decide (`:247-283`) |
| Action risk | **Schedules a future send** when `reengagement_memory_auto_send` is on (default OFF). The model-chosen `return_on` sets `due_at` (`:286-299`). An injected far or near future date is accepted if it is later than today |
| Tests | `tests/test_reengagement.py`, `tests/test_champion_tracker.py`, injection containment `:211` |

### T11 — Reply Copilot draft (the only LLM output that can **auto-send**)
| | |
|---|---|
| Call | `app/services/reply_copilot.py:556` (`_ask`, MAX_TOKENS 700 `:107`, API temperature); repair retry `:640` |
| Prompt | `_SYSTEM` :491 (1257 ch ≈314 tok); `_PROMPT` :525 (481 ch); assembled `:616-634` |
| Inputs | Reply body + lead fields **UNTRUSTED-WRAPPED** (`:618-623`); objection playbook (Phase 7), approved claims, forbidden phrases, booking link (owner data) |
| Output | JSON `{body, meeting_time_request}`. Deterministic `draft_problems` (banned words, forbidden phrases, placeholders, foreign links) gives one repair attempt, then no draft (closed, `:637-651`); claim verification follows |
| Action risk | **SEND**: auto-send only if the deployment allows it, the account opted in, the channel is email, the intent is positive/question, **the model flag AND deterministic `meeting_time_language(reply.body)`** (`:747-748`), the booking link is present, claim verification made no change, and routing is finished (`auto_send_decision :829-863`). Otherwise a human approves |
| Tests | `tests/test_reply_copilot.py`, `tests/test_reply_copilot_review_fixes.py` (both **sealed**), `tests/test_reply_copilot_strictness.py` |

### T12 — Follow-up brief / re-engagement brief
| | |
|---|---|
| Call | `message_personalization.py:415` and `:505` |
| Prompt | `_FOLLOWUP_SYSTEM` :322 (704 ch), `_REENGAGEMENT_SYSTEM` :445 (741 ch), `_FOLLOWUP_PROMPT` :336 |
| Inputs | Our prior messages and outcome log; product; playbook. **UNTRUSTED-RAW**: lead `full_name/title/company` (`:422-424, :512-514`) |
| Output | JSON `{brief}`. Failure uses FALLBACK brief (fail open to a generic brief, by design `:429-433`) |
| Action risk | Indirect SEND: the brief becomes the step template rendered by T03 (`outreach_tasks.py:2318, 2440`) |
| Tests | `tests/test_followup.py`, `tests/test_reengagement.py` |

### T13 — LinkedIn outreach copy (connect note / message / InMail)
| | |
|---|---|
| Call | `app/services/linkedin_outreach.py:158` (max_tokens 1024) |
| Prompt | SYSTEM :49 (591 ch) + style suffix; prompt `:147-154` |
| Inputs | `personalization_context.prompt_block` (wrapped). **UNTRUSTED-RAW**: `PROSPECT: {lead.full_name} — {lead.title} at {lead.company}` (`:152`); playbook ≤6000 ch |
| Output | JSON `{text, subject?}`. Empty raises (closed) |
| Action risk | **SEND** via Unipile in the LinkedIn sequence |
| Tests | `tests/test_linkedin_channel.py`, `tests/test_autopilot_launch.py` |

### T14 — AI phone call script + live Vapi call
| | |
|---|---|
| Call | Script: `app/services/phone_calls.py:218` (max_tokens 2048). Live call: Vapi assistant (`voice_providers.py:148-200`), prompt from `phone_calls.system_prompt` `:234-270` |
| Prompt | SCRIPT_SYSTEM `:75` (868 ch ≈217 tok) + style suffix; live system prompt = `voice_twin.identity_rules` + STYLE_RULES + script |
| Inputs | Script: posts/news wrapped (`personalization_context`); **UNTRUSTED-RAW** prospect name/title/company (`:213`) and again in the live system prompt (`:264`). Live: the callee's speech in real time |
| Output | JSON script coerced (`:198-210`). Missing first_message raises. **The AI disclosure is enforced deterministically** (prefix added, `:223-230`); identity claims are stripped by regex (`:243-246`) |
| Action risk | **Places a phone call**, which costs money and needs TCPA consent (`consent_ok`, gated by `phone_calling_enabled` default False). The live LLM can `endCall`/`transferCall` |
| Tests | `tests/test_phone_calls.py`, `tests/test_voice_twin.py` (FakeClaude / mocked Vapi) |

### T15 — Call transcript analysis (consent-relevant)
| | |
|---|---|
| Call | `phone_calls.py:357` (max_tokens 1500, **API-default temperature**, unlike the reply judges) |
| Prompt | ANALYSIS_SYSTEM `:91` (650 ch ≈162 tok); `analysis_prompt` `:345-349` |
| Inputs | Transcript **UNTRUSTED-WRAPPED** (60k ch) |
| Output | JSON coerced. Unknown outcome becomes ANSWERED. Exceptions go to Celery retry ×2 (`workers/call_tasks.py:20-38`), then give up |
| Action risk | **CONSENT**: `stop_request` → `unsubscribe_lead(... channel="phone")` or `suppress_caller` (`:380-390`). If analysis fails 3×, a spoken "don't call me" is never recorded (fail open for consent). The live assistant is told to honour it on the call |
| Tests | `tests/test_phone_calls.py`, injection containment `:246` |

### T16 — Inbound voice-twin assistant (Vapi)
| | |
|---|---|
| Call | `app/services/voice_twin.py:1428` → `voice_providers.vapi_assistant(model=...)` |
| Prompt | `voice_twin.inbound_system_prompt` `:1356-1400` |
| Inputs | Business "about" text and assistant notes wrapped (`:1381, :1385`); known-lead facts wrapped (`:1394`); the caller's live speech |
| Output / Action | Live conversation with booking tools (`find_times`/`book_meeting`/`take_message`). **Books meetings** |
| Notes | Model `settings.anthropic_model` through Vapi; not token-metered |
| Tests | `tests/test_voice_twin.py` (mocked) |

### T17 — Meeting prep brief
| | |
|---|---|
| Call | `app/services/meeting_prep.py:572` (max_tokens `meeting_prep_max_tokens=4096`, `config.py:366`) |
| Prompt | SYSTEM `:71` (1649 ch ≈412 tok); `build_prompt` `:318-336` |
| Inputs | **UNTRUSTED-RAW** (meeting_prep does not import `prompt_safety`): LinkedIn posts (:323), company news (:324), raw enrichment JSON (:325), **prospect replies** (:327), via `_block` `:310-315` (`## TITLE\nvalue`, no delimiter or notice) |
| Output | JSON coerced by `clean_sections` `:357-378`. Failure sets the brief FAILED (`:576-582`) |
| Mode / Action | Celery (`meeting_prep_tasks.py:119`) / human-read only. Feeds roleplay (T21) and follow-up (T18) |
| Tests | `tests/test_meeting_prep.py` (FakeClaude) |

### T18 — Post-meeting follow-up email
| | |
|---|---|
| Call | `app/services/meeting_followup.py:303` (max_tokens 1500) |
| Prompt | SYSTEM `:114` (646 ch) + style suffix; prompt `:271-296` |
| Inputs | Prospect name/title/company **raw**; seller notes (trusted); AI meeting summary (model output from the wrapped transcript); prep brief section; strategy excerpt |
| Output | JSON `{subject, body}`. Empty raises, recorded on the row |
| Action | Saved as a **Gmail draft** (human sends). Interactive API (`api/meeting_prep.py:272, 309`) |
| Tests | `tests/test_meeting_prep.py`, `tests/test_gaps_sweep_2.py` |

### T19 — Meeting transcript summary
| | |
|---|---|
| Call | `app/services/meeting_ai.py:195` (max_tokens 4096 `config.py:347`) |
| Prompt | `_SYSTEM` :50 (983 ch); `_PROMPT` :73 |
| Inputs | Transcript **UNTRUSTED-WRAPPED** (60k ch); lead fields wrapped; seller raw_notes unwrapped (trusted) |
| Output | JSON coerced. Failure returns `ok:False` (`:199-205`) |
| Mode / Action | Celery (`calendar_tasks.py:345`) / display only |
| Tests | `tests/test_meetings_api.py`, injection containment `:234` |

### T20 — Strategy mutation (learning loop)
| | |
|---|---|
| Call | `app/services/strategy_mutation.py:277` (max_tokens 4096) |
| Prompt | SYSTEM `:55` (832 ch); prompt `:270-276` (outcome snapshot, ICP, sequence briefs, strategy doc ≤14k ch) |
| Inputs | Internal metrics and our own docs. No direct untrusted text |
| Output | JSON coerced. An empty result raises (caller logs, or API returns 502). Creates a PROPOSED version. If **applied** (human), it changes the playbook used by T03 |
| Mode | Sweep + interactive (`api/ai_intelligence.py:192`) |
| Tests | `tests/test_ai_intelligence.py` |

### T21 — Sales roleplay (prospect persona + feedback)
| | |
|---|---|
| Call | Reply `app/services/roleplay.py:327` `complete()` (MAX_TOKENS_REPLY 700); feedback `:417` (1500) |
| Prompt | `_PERSONA_SYSTEM` :71 (1049 ch) + persona (`_persona_prompt` :199-224) in the **system** prompt; `_FEEDBACK_SYSTEM` :92 |
| Inputs | Persona built from the meeting-prep brief. `real_objections` = **prospect's own reply words, inserted RAW into the system prompt** (`:213-215`). The seller's typed turns go in the user prompt as a flattened transcript |
| Output | Free text (persona) cleaned by `_clean_reply`; JSON feedback. Failure stores the error |
| Caching | Strong candidate: a stable persona system prompt plus a growing transcript re-sent each turn (no multi-turn messages, no cache) |
| Mode / Action | Interactive (`api/practice.py:172, 206`) / none |
| Tests | `tests/test_practice.py` |

### T22 — Help-center support chat
| | |
|---|---|
| Call | `app/services/support_chat.py:428` (max_tokens `support_chat_max_tokens=1024`, `config.py:280`; API temperature) |
| Prompt | SYSTEM_PROMPT_HEADER `:97` (1866 ch ≈466 tok; deliberately stable for caching, `:91-96`); `build_prompt` `:367-388` (documents → history → question) |
| Inputs | User question + history marked untrusted via `_untrusted` inside `<question>/<history>` tags. Retrieved help-center docs (repo, trusted) |
| Output | JSON with on_topic/confidence guards. Any failure becomes a ticket; a permanent failure falls back to mock mode (`:410-460`) |
| Caching | None, despite the explicitly stable header. Even so, at ≈466 tok it is below the 1024-token cache minimum unless the docs block is included |
| Mode / Action | Interactive / none (may open a ticket) |
| Tests | `tests/test_support_chat.py`, `tests/help_center/*` (retrieval eval offline). **Live: `scripts/help_center/live_eval.py`, `scripts/support_chat_adversarial.py`** (manual; no results recorded, see `docs/program/help-center-eval.md:25-26`) |
| Evals | `tests/help_center/golden_questions.yaml`: 151 answerable + 31 must-refuse (the doc still says 77/23) |

### T23 — Displacement-monitor DM
| | |
|---|---|
| Call | `app/services/displacement_monitor.py:199` (MAX_TOKENS 1000 `:67`), one repair attempt |
| Prompt | `_DM_SYSTEM` :76 (766 ch); `_DM_PROMPT` :93 |
| Inputs | Scraped post excerpt + lead fields **UNTRUSTED-WRAPPED** (`:188-195`) |
| Output | JSON `{dm}` + `validate_dm`. Otherwise None (alert without a DM, closed) |
| Action | Draft only ("one click from being sent", human) |
| Tests | `tests/test_customer_winback.py`, injection containment `:225` |

### T24 — Personal video (Loom) script
| | |
|---|---|
| Call | `app/services/loom_video.py:96` (max_tokens 1200) |
| Prompt | SYSTEM `:44` (453 ch); prompt `:92-94` |
| Inputs | **UNTRUSTED-RAW**: lead profile, LinkedIn posts and company news through `meeting_prep._linkedin_posts/_company_news`, stringified with no delimiter (`:89-94`) |
| Output | JSON `{title, script, on_screen}`. Empty raises |
| Action | Script for a human to record. The resulting video CTA goes into T03 emails |
| Tests | `tests/test_personalization.py` |

### T25 — Network message drafts (LinkedIn connections / email contacts)
| | |
|---|---|
| Call | LinkedIn `app/services/network_messages.py:94` (600 tok); email `app/services/email_network_messages.py:343` (700 tok) |
| Prompt | SYSTEM `network_messages.py:32` (411 ch); `email_network_messages.py:61` (802 ch); both + style suffix |
| Inputs | LinkedIn: **UNTRUSTED-RAW** `conn.full_name/position/company` (`network_messages.py:87`). Email: contact fields **wrapped** (`email_network_messages.py:331-337`) |
| Output | JSON. Empty or exception returns MessageError 502 (closed) |
| Action | Draft; the user approves and sends. Interactive |
| Tests | `tests/test_network_messages.py`, `tests/test_email_network_guards.py`, `tests/test_email_network.py` |

### T26 — Style profile and founder voice profile
| | |
|---|---|
| Call | `app/services/style_profile.py:109` (1500); `app/services/voice_profiler.py:185` (MAX_TOKENS 1000 `:46`) |
| Prompt | SYSTEM `style_profile.py:31` (673 ch); `voice_profiler.py:62` (1068 ch) |
| Inputs | The user's own writing samples / founder LinkedIn posts (owner-supplied, unwrapped) |
| Output | JSON coerced into closed vocabularies. **The output is appended to the system prompt of T03/T04/T13/T14/T18/T25**, so injected instructions in a sample would persist into every outbound system prompt |
| Mode | Interactive (`api/personalization.py:73`) / Celery (`voice_tasks.py`) |
| Tests | `tests/test_voice_profile.py`, `tests/test_personalization.py` |

### T27 — F-P-T-A scoring and lead scoring
| | |
|---|---|
| Call | `app/services/fpta_scoring.py:345` (3000); `app/services/lead_scoring.py:194` (2048) |
| Prompt | SYSTEM `fpta_scoring.py:78` (981 ch); `lead_scoring.py:52` (537 ch) |
| Inputs | Lead title/company/industry + evidence signals as `json.dumps` (JSON-escaped, not tagged as untrusted) |
| Output | JSON. Adjustments are **clamped** in code: ±15 (`fpta_scoring.py:57`), ±20 (`lead_scoring.py:40, 238-239`). Failure falls back to the heuristic |
| Mode / Action | Batched leads per call, Celery (`lead_tasks.py:612`) + API. Batch API candidate. Prioritisation only |
| Tests | `tests/test_spend_guard.py`, `tests/test_ai_intelligence.py`, `tests/test_customer_winback.py` |

### T28 — ICP criteria extraction + tactic classification
| | |
|---|---|
| Call | `app/services/icp_extraction.py:126` (criteria), `:158` (tactic) |
| Prompt | `_SYSTEM` :67 / `_PROMPT` :73; `_TACTIC_SYSTEM` :46 / `_TACTIC_PROMPT` :52 |
| Inputs | Pipeline research (model). Quickstart passes the user's website text **wrapped** (`quickstart.py:210-219`) |
| Output | JSON coerced to lists. Tactic failure returns empty (open). Criteria failure raises |
| Action risk | **MONEY**: the criteria drive Apollo/Hunter lead sourcing (credits) |
| Tests | `tests/test_quickstart.py`, `tests/test_offline_guard.py`. Live: `scripts/phase_c_pipeline.py` |

### T29 — Past-client pattern extraction
| | |
|---|---|
| Call | `app/services/pattern_recognition.py:64-68` |
| Prompt | `_SYSTEM` :26 (190 ch); `_PROMPT` :32 (799 ch) |
| Inputs | User-entered client details and acquisition story (owner text, unwrapped) |
| Output | JSON. Failure gives None patterns + `_extraction_error` (open, `:69-71`) |
| Mode | Interactive (`api/products.py:142`) |
| Tests | `tests/integration/test_flows.py`. Live: `scripts/phase_c_services.py:65` |

### T30 — Verification judge (10 passes; pass #4 = legal and compliance ship-blocker)
| | |
|---|---|
| Call | `app/verification/loop.py:145` `complete_json(temperature=0, JUDGE_SYSTEM, JUDGE_PROMPT)` |
| Prompt | `app/verification/passes.py:15` JUDGE_SYSTEM (368 ch); `:60` JUDGE_PROMPT; PRECEDENCE_RULE `:41` (1088 ch) |
| Inputs | Strategy document + support block (phase syntheses, past-client patterns, GTM doc; ≤60,000 ch ≈15k tok, `loop.py:53, 58-104`) |
| Output | JSON `{result, fix_description}`. Anything other than PASS is FAIL (closed). A parse error raises `ValueError` and the Celery task fails |
| Caching | **Largest cache opportunity in the codebase.** The same ~15–20k-token document + support is re-sent for each of 10 passes × up to N attempts. JUDGE_PROMPT currently puts the per-pass criterion *first* (`passes.py:60-71`), so the stable prefix is lost. Moving the document and support first and the criterion last would make it cacheable |
| Mode | Background. Sequential per pass (fix → re-judge), but the 10 initial judgements are independent, so it is a Batch candidate |
| Tests | `tests/test_verification.py` and 13 others, `tests/test_judge_determinism.py:101`. Live: `scripts/phase_c_pipeline.py` |

### T31 — Verification fixer (full-document rewrite)
| | |
|---|---|
| Call | `loop.py:181` and retry `:196` `complete(FIXER_SYSTEM, FIXER_PROMPT, max_tokens=18,432 → ×2 ≤128k)` (`config.py:404`); streaming above 20k |
| Inputs | Judge fix_description + strategy document |
| Output | Free-text document. Truncation leaves the document unchanged (closed, `loop.py:293-318`); oscillation detection (`:206-240`) |
| Cost note | `docs/FINDINGS_REGISTER.md:68` calls this the single most expensive call. Not cached |
| Tests | `tests/test_verification.py`, `tests/test_judge_determinism.py:124` |

### T32 — Autopilot sequence briefs / send-time plan
| | |
|---|---|
| Call | `app/services/autopilot.py:610` (4096); `app/services/send_time.py:433` (4096) |
| Prompt | `_PLAN_SYSTEM` `autopilot.py:548` (556 ch); `send_time.py:342` (611 ch) |
| Inputs | Product + Phase 6/8 research (`autopilot.py:603-608`); ICP (send_time) |
| Output | JSON validated (`_valid_steps` `autopilot.py:574-591`, delay 1–14 days; send-time windows validated). Failure falls back to FIXED briefs or priors |
| Action | Autopilot briefs become live sequence templates and are **auto-enrolled** for opted-in strategies (all send gates still apply). Send-time decides WHEN messages send |
| Tests | `tests/test_autopilot_launch.py`, send_time tests |

### T33 — WhatsApp template drafting
| | |
|---|---|
| Call | `app/services/whatsapp_templates.py:430` |
| Prompt | `_GENERATE_SYSTEM` :381 (986 ch); `_GENERATE_PROMPT` :401 |
| Inputs | Phase 2/6 research (model) |
| Output | JSON list. Local validation drops bad candidates (incl. opt-out instruction `:60-83`). Saved as DRAFTS that the user submits to Meta |
| Mode | Interactive (`api/whatsapp_templates.py:221`) |
| Tests | WhatsApp tests (incl. sealed `tests/test_whatsapp_template_optout.py`) |

### T34 — Sequence red-team review
| | |
|---|---|
| Call | `app/services/adversarial_review.py:276` (1200, temp 0) |
| Prompt | RED_TEAM_SYSTEM `:80` (573 ch) |
| Inputs | Sequence step templates (user or model) |
| Output | JSON findings, WARN only. Failure leaves the rules standing |
| Tests | `tests/test_send_review.py`, `tests/test_guardrails.py` (sealed), `tests/test_sequence_reviews.py` |

### T35 — SEO website page builder
| | |
|---|---|
| Call | `app/services/website_builder.py:170` (MAX_TOKENS 8000 `:50`) |
| Prompt | SYSTEM_PROMPT `:54` (460 ch); `_USER_PROMPT` `:65` (1980 ch ≈495 tok) |
| Inputs | Page brief and keywords (operator) |
| Output | JSON with html_content. Missing raises ValueError; truncation raises. The existing page is left untouched |
| Mode | Celery `site_tasks.py`. Batch candidate. **Publishes HTML** to the marketing site |
| Tests | `tests/test_website_builder.py` |

### T36 — Manual live-check scripts (gateway)
`scripts/phase_c_services.py:42, 52` (connectivity and JSON mode, real API), `scripts/phase_c_pipeline.py`, `scripts/activate_with_keys.py:155`. These are the only code that exercises real model behaviour, and all are manual.

---

## 2. Specific verifications requested

| # | Claim | Verdict on current code | Evidence |
|---|---|---|---|
| 1 | Indirect prompt injection in `personalization_context.py` (~146-176) | **FIXED at that site (F-AI-02).** Posts are wrapped with `prompt_safety.block` (`personalization_context.py:170`); news headline, summary and source with `prompt_safety.inline` (`:184-187`); one NOTICE ahead of the block (`:197`). **But the same untrusted data still reaches prompts RAW elsewhere:** `meeting_prep.py:318-336` (posts, news, enrichment, replies), `loom_video.py:89-94` (posts/news), `market_intel.py:306` (headlines into pipeline Phase 1/3), `roleplay.py:213-215` (reply text in the system prompt), plus raw lead name/title/company in `message_personalization.py:274-277` (WhatsApp vars), `:422-424`/`:512-514` (briefs), `linkedin_outreach.py:152`, `phone_calls.py:213, 264`, `network_messages.py:87`, `meeting_followup.py:276`. Wrapping is containment only (`prompt_safety.py:18-19`); no test runs an injection against a real model | see cells |
| 2 | Prompt caching unused despite large stable prefixes | **TRUE that it is unused** (no `cache_control`; acknowledged at `support_chat.py:94-96`). **Nuance:** every system prompt is ≤466 tok (all below the 1024-token cache minimum). The large stable content is in user prompts and is mostly **not prefix-ordered**: verification judge (`passes.py:60-71`, criterion before a ~15k-tok document, re-sent 10×N), pipeline (`registry.py:25-44`, step header before context), personalization (playbook mid-prompt), roleplay (persona plus growing transcript) | anthropic_client.py:219-224 |
| 3 | Batch API unused | **TRUE.** No `message_batches` anywhere. Candidates: pipeline steps across strategies (T01), the 10 initial verification judgements (T30), consensus judge (T02), lead/FPTA scoring (T27), website pages (T35), meeting prep (T17) | grep |
| 4 | Default model `claude-sonnet-4-6` | **TRUE.** `app/config.py:46`; also `app/core/config.py:77`, `scripts/activate_with_keys.py:152`, `voice_providers.py:173`. A single global model with no per-task routing | — |
| 5 | Assistant prefill on last turn | **NONE.** The gateway always sends one user message (`anthropic_client.py:223`). Multi-turn features (support chat, roleplay) flatten history into the user text (`support_chat.py:367-388`, `roleplay.py:327-331`). Vapi gets only a system message (`voice_providers.py:174`) | — |
| 6 | `budget_tokens` usage | **NONE.** No `thinking`/`budget_tokens` anywhere in app/scripts/evals | grep |

## 3. Metering, prices and cost data

- **Metering exists.** `usage_meter.note()` runs per call (`anthropic_client.py:251`, `openai_client.py:74`) and is flushed to the `ApiUsage` table with `cost_micros` (`usage_meter.py:185-205`). Pre-call worst-case gates cover the strategy budget (default $15, ceiling $50, `config.py:59-60`) and the account daily cap (`usage_meter.py:299-345`). There are capped purposes plus counted-only purposes (`outreach, meeting_prep, call_analysis, reply_handling, launch, support_chat`, `usage_meter.py:85-88`). F07 spend guard: `app/services/spend_guard.py`.
- **Prices assumed in code** are admin-editable system settings and are **per provider, not per model** (`usage_meter.py:118-121`):
  - Claude $3.00 / $15.00 per Mtok in/out (`app/services/system_settings.py:74-77`)
  - OpenAI $2.50 / $10.00 per Mtok (`system_settings.py:78-81`)
  - Voice $0.15 per minute all-in (`system_settings.py:82`)
  - Budget-planner estimate per pipeline step: 7,000 input + 1,500 output tokens, $1.00 reserved for verification (`config.py:72-75`)
  - The price model has no cache-read, cache-write or batch discount, so adopting caching or Batch would leave reported costs overstated until the meter learns those token classes (`usage.cache_read_input_tokens` is ignored at `anthropic_client.py:251-253`).
- **Measured cost-per-call data:** none is recorded in docs. Logged evidence is anecdotal: "7 of 8 fixer calls returned out_tokens=8000" on the 2026-08-19 run (`anthropic_client.py:202-207`). `docs/program/BASELINE.md:97,173` describes the cap design. `docs/features/f06-quickstart.md:227` gives estimates. `docs/FINDINGS_REGISTER.md:68` gives the call count per strategy (72–144 + ≤10×≤3 rewrites at ≤18,432 tokens). Live Help-AI results are **not recorded** (`docs/program/help-center-eval.md:25-26`: "no key was available").

## 4. Existing eval framework

| Component | What it measures | How |
|---|---|---|
| `evals/run_evals.py` | Runs the **offline pytest suite** (SQLite, FakeClaude, network blocked) with JUnit XML. Emits `candidate.json` (schema candidate/v2, registry and dataset hashes) | `--sabotage compliance/suite/count` produce genuine broken variants for BLOCK fixtures |
| `evals/registry.yaml` | **4 metrics only:** `compliance_suite_pass_rate` (hard, 1.0), `full_suite_pass_rate` (hard, 1.0), `offline_test_count` (hard, ≥3150), `suite_runtime_s` (soft, ≤900 s). **No model-quality, injection-resistance, cost or latency-per-call metric** | — |
| `evals/compliance_testset.yaml` | 31 sealed legal and safety test files (CLAUDE.md says "five", which is stale) | Blocks on failure or on a missing/empty file |
| `evals/baseline.json` | n_runs=2. Count mean **5,981** (CLAUDE.md and the registry comment say 3,319, also stale). Runtime mean 1,020 s ±46, which is **above** the 900 s soft threshold, so the soft metric would WARN | — |
| `evals/tools/promote.py` | Gate: exit 0 PROMOTE / 1 BLOCK / 2 bad input. Fail-closed on NaN, missing metrics, stale hashes, hard breach, or regression > max(noise_band, 2σ) | — |
| `evals/fixtures/verify_block_fixtures.py` | Proves each hard gate fires | — |
| `scripts/help_center/live_eval.py` | **Only model-behaviour eval.** LIVE Anthropic, opt-in, refuses to run in CI (`:50-53`), exits 2 without a key, aborts on a dead key. Measures on `tests/help_center/golden_questions.yaml` (151 answerable / 31 must-refuse): answer rate, ticket rate, expected-chunk citation, must-refuse adherence, and **unsupported-sentence rate** (numbers, quotes and proper nouns checked against the shown documents using the claim-verification number/proper-noun matchers, `:56-83`) | Covers T22 only |
| `scripts/support_chat_adversarial.py` | LIVE: on-topic, off-topic, injection and unknown categories. Exit 0 only if all pass | T22 only |
| `scripts/help_center/measure_golden.py`, `tests/help_center/test_retrieval_eval.py` | Offline retrieval recall and mock-path precision | No model |
| `scripts/phase_c_services.py`, `scripts/phase_c_pipeline.py` | LIVE shape/contract checks (JSON keys and classes, not quality) | Gateway, T29, T06, T01/T30/T28, T03, T33 |

**No golden or eval set exists** for: reply classification (T06; the consent-critical one), call stop-request detection (T15), outbound copy quality or claim hallucination (T03/T04/T13), the verification judge (T30), Reply Copilot auto-send (T11), or injection resistance with a real model on any touchpoint.

## 5. Summary

- **36 touchpoints:** about 33 gateway call sites across 30 modules, 1 OpenAI path, 2 voice-provider LLMs (Vapi, which inherits `anthropic_model`; ElevenLabs, whose model is not in code), and manual scripts. All Anthropic traffic except `scripts/activate_with_keys.py` and the `/v1/models` health probe goes through `anthropic_client.py`.
- **Uniform configuration:** `claude-sonnet-4-6` everywhere. No caching, no Batch, no thinking, no prefill. JSON is parsed by regex with per-caller coercion. Temperature is 0 only for judges (T05–T09, T02, T30, T34); generation uses the API default. T15 call analysis drives a stop request but is not pinned to 0.
- **Actions LLM output can trigger:** sends of T03/T04/T13 (after claim verification and send gates); auto-send of T11 (heavily gated, including a deterministic meeting-language check); phone calls T14/T16 (plus booking); consent decisions T06 (email opt-out is LLM-only in the hot path) and T15 (stop request; fails open after 3 failed analyses); future-send scheduling T10 (auto-send off by default); sequence auto-creation T32; money via ICP-driven sourcing T28; HTML publishing T35.
- **Injection posture:** F-AI-02 wrapping is applied on the reply, transcript and post paths, and the audit's personalization_context finding is fixed. Raw untrusted text remains in meeting_prep, loom_video, market_intel → pipeline, roleplay persona, the WhatsApp variable filler, briefs, and LinkedIn/phone/network prospect fields (§2 row 1). Style and voice profiles (T26) persist into every outbound system prompt.
- **Verification:** no pytest test exercises real model behaviour. Model behaviour is evaluated only by the opt-in live Help-AI eval and adversarial script (T22), whose results are not recorded, and by Phase-C contract scripts. The release gate (`evals/`) measures only offline test pass rates and counts.
- **Out-of-scope discrepancies (reported, not fixed):** CLAUDE.md says "five sealed compliance files" (actual 31) and "3,319 tests" (baseline mean 5,981). The baseline runtime of 1,020 s exceeds the 900 s soft threshold. `docs/program/help-center-eval.md` describes a 100-item golden set (actual 182). Voyage/`embeddings_client.py` is decided but absent. `support_chat.py:94` asserts cacheability, but the header is below the cache minimum.

---

# Part B — Manual user workflows, existing AI features, costs


Swept 2026-10-20, read-only, `/home/user/LeadPilot` (no git metadata in this checkout, so no SHA).
Sources: `frontend/src/app/**/page.tsx` (51 app/admin routes plus public pages), `app/api/*.py` (76 routers),
`docs/features/*.md`, `docs/help-center/*.md` (44 articles; 31 and 32 are the daily-routine guides),
`docs/program/{BASELINE,DECISIONS,help-center-discoveries,help-center-eval}.md`, `docs/program/fixes/*.md`,
`docs/FINDINGS_REGISTER.md`, `docs/program/status.json`, `app/core/plans.py`, `app/services/usage_meter.py`,
`app/services/system_settings.py`.

Labels: **ASSUMPTION** = my estimate, not measured. Frequencies are ASSUMPTIONs unless a source is cited.
**DET** = the step touches something that must stay deterministic (auth, billing, spend caps, plan limits,
suppression/unsubscribe/consent, send-rate limits, daily send approval, legal guards).

---

## 1. Is there usage or analytics data in the repo?

Almost none. Nothing in the repo says which features customers use.

- **No product analytics.** Grep for posthog/mixpanel/amplitude/segment/gtag/telemetry over `app/` and `frontend/src` finds nothing.
  The only telemetry ever added was Vercel Speed Insights, on an unmerged branch (`docs/BRANCH_COVERAGE.md:21`).
  gaps-sweep-2 #13 rewrote Privacy §2 because "no tracking exists".
- **Only real usage figure:** `docs/program/plans/help-ai-v2-00-recon.md:59-67` says the retained Render logs show **4 `POST /support/chat` calls in total**, all from the founders' address range,
  and "the logs show almost no real users". DECISIONS.md HELPAI-DEMAND repeats this.
- **Production AI may not run at all.** The same recon (§2) found every support-chat call failing with 401 `invalid x-api-key` up to 2026-10-18.
  The founder replaced the key on 2026-10-18 (DECISIONS HELPAI-KEY). Whether the worker (pipeline, drafting, scoring) used the same dead key was **not checked**.
  `docs/features/ai-support-chat.md` Outstanding #1 says the same about `.env`.
- **Production state:** the Render worker sleeps after about 15 min, so beat, sends and reply checks stop. See BASELINE.md §6, decision D2.
- **Data sources that exist in the code but not in the repo:**
  - `api_usage` rows: spend per purpose, written by `usage_meter._flush`. This is the best proxy for which AI features are used.
  - `chat_messages`: purged after 30 days. The founders have a SQL query for them: `docs/program/help_ai_diagnostic.sql`.
  - `security_audit_events`, `compliance_audit_log`, `reply_drafts.edited` (Reply Copilot metrics `GET /reply-copilot/metrics`), and the F08/F09 ledgers.
  - None of these were read; there is no DB access from this session.
- `docs/program/status.json` tracks program phases and gates, not product usage.
- **Feature-flag defaults decide what a deployment even exposes** (`app/services/system_settings.py`):
  - Off by default: Reply Copilot (`:318`), Copilot auto-send (`:323`), Quickstart (`:306`), Guardrails (`:270`), Signal Radar (`:296`), Spend Guard (`:345`), Pilot mode (`:360`), phone and voice twin (`:90`, `:104`), consensus (`:36`), champion tracker (`:386`), email network (`:471`), and others.
  - On by default: daily send approval (`:406`), Autopilot offer (`:424`), best-time scheduling (`:435`), claim verification and model extraction (`:172`, `:176`), sequence red-team (`:180`, `:184`), meeting prep (`:29`), lead scoring (`:43`), strategy mutation (`:45`), send-review queue (`:144`), re-engagement memory (`:156`).
  - **MCP connector:** `MCP_ENABLED=false` by default.

**Recommendation (to feed the backlog):** before ranking AI work by usage, add a minimal first-party feature-usage counter, or run a founder query over `api_usage` grouped by `purpose`.
Until then, every frequency below is an ASSUMPTION.

---

## 2. Plan limits, AI spend caps, per-call cost data

### 2.1 `app/core/plans.py` (PLANS, lines 59-178)

| Plan | max_strategies | **max_ai_spend_usd_per_day** | max_leads_per_strategy | max_sequence_steps | channels | A/B | playbook | MV | site pages |
|---|---|---|---|---|---|---|---|---|---|
| free | 3 | **$10** | 100 | 5 | gmail | no | no | no | 0 |
| starter | 10 | **$25** | 500 | 10 | gmail, whatsapp | yes | yes | no | 10 |
| growth | 25 | **$60** | 2,500 | 15 | +linkedin | yes | yes | yes | 25 |
| scale | unlimited | **$150** | 10,000 | 20 | +phone | yes | yes | yes | unlimited |
| pay_per_meeting | 10 | **$60** | 1,000 | 10 | gmail, whatsapp, linkedin | yes | yes | no | 0 |
| pro (legacy) | unlimited | **$150** | unlimited | 20 | all 4 | yes | yes | yes | unlimited |
| enterprise | unlimited | **$400** | unlimited | 20 | all 4 | yes | yes | yes | unlimited |

Other plan keys:
- `analytics_history_days`: 30, 90 or 365 days, or unlimited.
- `linkedin_network` and `email_network`: growth, scale, pro and enterprise (`:186-193`).
- `SEQUENCE_STEP_CAP = 20` (`:56`).

The caps are **placeholders pending the founders' pricing decision** (P0-5-CAPS, `plans.py:45-51`).

### 2.2 How the daily cap is enforced (`app/services/usage_meter.py`)

- The cap is per account per UTC day. It is checked **before** each model call, but only for `ACCOUNT_CAPPED_PURPOSES` (`:65-82`):
  pipeline, verification, lead_scoring, icp, intake, review, drafting, practice, mutation, website, meeting_summary, voice_profile, displacement, quickstart, reply_copilot, autopilot, send_time.
- **Counted but never stopped** (`COUNTED_ONLY_PURPOSES`, `:83-86`): outreach (per-send personalization and claims), meeting_prep, call_analysis, reply_handling, launch, support_chat.
  So per-send AI cost is **not** bounded by the daily cap. It is bounded only by send caps (`gmail_daily_cap` = 100 per help-center discovery D6) and rate limits.
- **Per-strategy pipeline budget:** default $15, bounds $0.50 to $50 (BASELINE P0-5 row; `app/config.py:59-60`).
- **Quickstart run budget:** `quickstart_budget_usd` $1.00.
- **F07 Spend Guard** (off by default): a per-account monthly cap with forecasts.
- **Prices are admin estimates** in `system_settings.py:74-80`:
  - Claude $3 in / $15 out per Mtok.
  - OpenAI $2.5 / $10.
- **Voyage** (Help AI v2, DECISIONS HELPAI-VENDOR): `voyage-context-4` $0.12/Mtok, `rerank-2.5-lite` $0.02/Mtok, first 200M tokens free.
- **Default model:** `claude-sonnet-4-6` (`app/core/config.py:77`). Whether this ID is valid is F-AI-04, still OPEN.

### 2.3 Per-call cost data found (all estimates in docs, none measured on real traffic)

| Work | Cost | Source |
|---|---|---|
| Full Flow-2 strategy (144 steps + verification) | **~$8.29** | `plans.py:51`, `usage_meter.py:53` |
| Strategy call count | 72–144 Claude calls + ≤10×≤3 verification rewrites (≤18,432 tokens each) | FINDINGS F-AI-01 |
| Reply Copilot draft | **~$0.02** (≤2× on repair) + 1 claim-extraction call at generation, at approval and at send | `f04-reply-copilot.md:420-437` |
| Autopilot (briefs + send-time plan) | **~$0.05–0.07 per strategy** | `autopilot-launch.md:653-660` |
| Quickstart | ~$0.01–0.03 per draft; 25 drafts ≈ $0.40–0.75 (capped at $1) | `f06-quickstart.md:225-243` |
| Email-network draft | **~$0.005** | `email-network.md:247-248` |
| Signal Radar personalization add-on | ~$0.0005 per email | `f02-signal-radar.md:235` |
| Lead scoring | ⌈leads/15⌉ calls × (default 2,500 in / 1,000 out ≈ **$0.0225/call**) | `f07-spend-guard.md:87-97` (UNVERIFIED) |
| F-P-T-A | 1 call per batch of 10 leads | `fpta-scoring.md` |
| Meeting prep brief | ≤4,096 output tokens → **≤ ~$0.06 out + input** | `app/config.py:366` |
| Meeting follow-up | ≤1,500 output tokens | `app/config.py:368` |
| Voice / AI calls | **$0.15/min** estimate (`voice_cost_per_minute`), Vapi + ElevenLabs, not metered by usage_meter | `voice-twin.md:259-272` |
| Support chat | ≤1,024 output tokens; 30 msgs/user/day (render.yaml) vs a 20 decision | discovery #40 |

### 2.4 Estimated AI cost per user per day (ASSUMPTION, derived from the numbers above)

| Profile | Daily activity (ASSUMPTION) | Est. AI $/day |
|---|---|---|
| Solo founder, steady state | 1 live strategy; 30–100 sends/day at ~$0.01–0.03 each (personalization + claim extraction, priced like a Quickstart draft); 5 human replies × (≈4 classifier calls ≈ $0.01 + Copilot $0.02–0.04); 50 new leads scored + F-P-T-A (~$0.2); 0–1 meeting brief (~$0.1) | **≈ $0.6 – $3.5** |
| Same, on a strategy-creation day | + one Flow-2 strategy $8.29 (+ re-verify if needs_human_review) | **≈ $9 – $12**; Free's $10 cap binds here |
| Growth SDR team, 3 strategies | 300 sends, 20 replies, 200 leads, 3 meetings | **≈ $5 – $12** |
| Voice twin on | + $0.15/min of calls (not in the daily cap) | +$1.5 per 10 min |

Takeaway for the backlog:
- Per-message outreach AI is the dominant **recurring** cost, and it is **uncapped** (counted only).
- The strategy pipeline is the dominant **one-off** cost.
- New interactive AI features (drafting, triage, summaries) cost cents per action. They fit the daily caps easily as long as they run under a capped purpose.

---

## 3. Existing AI features: where, what, defects, improvements

| Feature | Where (file:line) | What it does today | Known defects / open issues | Obvious improvements |
|---|---|---|---|---|
| **Reply Copilot (F04)** | Service: `app/services/reply_copilot.py` (`eligibility` :312, `_generate` :597, `draft_for_reply` :678, `account_settings` :776). Worker hook: `app/workers/reply_tasks.py`. API: `app/api/reply_copilot.py:80-181`. UI: `frontend/src/components/inbox/ReplyCopilotPanel.tsx`. Spec: `docs/features/f04-reply-copilot.md` | For interested, question and objection replies on email and LinkedIn, it drafts an answer grounded in the strategy's objection playbook (pipeline steps 56/62/63), F05 approved claims, the booking link and forbidden phrases. Claim verification runs at draft, approve and send. Approve sends through `send_message_impl`. LinkedIn is copy-only. Optional auto-send only for "send me a time" emails (two switches + account opt-in) | **Flag off by default** (`system_settings.py:318`), so most users answer by hand.<br>#46 (L, open): the "prospect wrote twice" option renders only inside a thread that already has a draft; marketing copy says "no auto-reply".<br>Unverified: draft quality on a real model (FakeClaude only); Gmail threading live; success metric never measured; cost estimate.<br>No regenerate endpoint (non-goal).<br>Feature 2 (`reply_intelligence.py`) makes a second, ungrounded draft per reply, which is a duplicate cost.<br>No WhatsApp drafts. | Turn on per account (plan-gate option, spec "Non-goals").<br>"Regenerate with instruction" (shorter / warmer / propose times).<br>Merge Feature 2's draft call into Copilot (saves 1 call per reply).<br>WhatsApp in-window drafts.<br>Pull meeting slots from the internal calendar (not just a link).<br>Learn from edits (`reply_drafts.edited`) into the account voice. |
| **Autopilot launch** | `app/services/autopilot.py` (`plan_steps` :593, `create_sequence` :632, `launch_gate` :667, `advance` :796, `sweep` :1146). API: `app/api/autopilot.py:87-224`. UI: `components/strategy/AutopilotCard.tsx`. Spec: `docs/features/autopilot-launch.md` | Per strategy, opt-in with lawful-basis confirmation. When the pipeline is VERIFIED it sources leads, has the model write sequence briefs from the research (fixed briefs if refused), creates the sequence, enrolls, and places sends at the best time. Every send still waits for daily approval | Brief and send-time output quality unmeasured (fakes only).<br>A strategy whose pipeline finished before Autopilot was turned on has no send-time plan.<br>Priors not re-checked against studies.<br>Lead time zones approximate split states.<br>Every legal reading is "needs founder/legal confirmation" (spec §13). | Let **manual launch** reuse `plan_steps` to pre-fill the opening and follow-up briefs (see W8).<br>Back-fill the send-time plan on opt-in.<br>Explain Autopilot's choices (which leads, which brief, why) in the card. |
| **"Why isn't this sending?"** | `app/services/send_diagnostics.py:419` `diagnose`. API: `app/api/autopilot.py:224`. UI: `components/strategy/SendDiagnosticsPanel.tsx` | **Not AI.** It returns about 25 deterministic reason codes, each pinned to the real gate, with a fix and a link (spec §3.3) | Evaluates rules only for the NEXT due message's lead.<br>Gmail revoked: sends are retried forever with no notification (#35, M).<br>Email-health card and preflight disagree (#37, M).<br>A sourcing run that finds nobody shows no message (#42). | Keep it deterministic. An optional AI layer could turn the reasons into a one-paragraph narrative or a "do this first" ordering. Proactively push a diagnosis when nothing has been sent for N hours. |
| **Meeting prep** | `app/services/meeting_prep.py` (`collect_context` :229, `build_prompt` :318, `generate_brief` :543, `notify_ready` :629). Worker: `app/workers/meeting_prep_tasks.py:118`. API: `app/api/meeting_prep.py:190-323`. Follow-up: `app/services/meeting_followup.py:148-428`. Practice: `app/services/roleplay.py`. UI: `components/leads/MeetingPrepPanel.tsx`, `CallScriptPanel.tsx`, `RoleplayPanel.tsx`, `LogOutcomeDialog.tsx`, `FollowupDraftCard.tsx`. Spec: `docs/features/meeting-prep.md`, `meeting-practice.md` | A brief on booking: profile from records; pains, objections, talking points, competitor landscape, opening script. Push or Slack when ready; 24h and 1h reminders. Log Outcome → Claude follow-up saved as a Gmail draft (never auto-sent). Editable call script, checklist, roleplay with feedback | ICP is never read by the data layer (#30, M, open): Industry fit is always 50%, F-P-T-A Problem keywords unused. This feeds the brief's F-P-T-A block.<br>Users connected before the change must reconnect Gmail for `gmail.compose`.<br>`meeting_ai.py:202` leaks raw exception text (gaps-sweep-2, out of scope).<br>`meeting_prep` purpose is counted, not capped. | Auto-draft the outcome notes from the Recall.ai transcript or summary (the user now types notes by hand in LogOutcomeDialog).<br>Auto-propose the CRM stage and deal value from the call.<br>Brief diff on reschedule. |
| **F-P-T-A scoring** | `app/services/fpta_scoring.py` (baselines :151-293, `_model_pass` :341, clamp `_resolve` :354, `score_leads` :377, `score_for_enrollment` :446). API: `app/api/leads.py:234-270`. UI: `FptaBadges.tsx`, `WhyThisProspectPanel.tsx`. Spec: `docs/features/fpta-scoring.md` | A deterministic baseline per dimension. One Claude call per 10 leads writes reasons and can move each score at most ±15. Runs at enrollment and on demand | **#30 (M, open):** `pattern_inputs_json` is nested (`{"icp":…}`) but read flat (`fpta_scoring.py:393`, `lead_scoring.py:215`, `market_intel.py:104`). Fit never sees company size; Problem keywords unused.<br>Scores only unscored leads (by design), so they go stale.<br>Rescore is manual. | Fix #30 first (deterministic, high value).<br>Rescore automatically when a Signal Radar signal arrives.<br>Use F-P-T-A to auto-suggest "don't contact / find a hook / plan return" actions per lead (the doc's own action table). |
| **Claim verification** | `app/services/claim_verification.py` (`build_evidence` :186, `verify_text` :321, `_model_claims` :407, `enforce` :470, `lead_log` :546). UI: `components/leads/ClaimChecksPanel.tsx`. MCP: `get_claim_verification` | Rules + optional model extraction (`claim_model_extraction_enabled`, on). Unsupported prospect claims are removed or neutralised. It runs on email, WhatsApp variables and LinkedIn, at generation, approval and send. **Sender claims** are only checked against the F05 approved-claims library (Guardrails off by default) | Judge evidence has no provenance isolation (F-AI-06, LOW, OPEN).<br>Sender self-claims are unchecked when Guardrails is off.<br>Costs 1 extra call per message (counted, uncapped). | Build an approved-claims library automatically: extract candidate claims from the strategy research and the product description for a person to approve (see W13).<br>Explain removals inline in the review queue. |
| **Voice twin** | `app/services/voice_twin.py` (identity/opening rules :200-270). API: `app/api/voice_twin.py:119-393`. UI: `components/settings/VoiceTwinCard.tsx`, `VoiceSettings.tsx`. Spec: `docs/features/voice-twin.md` | ElevenLabs PVC of the owner. Vapi assistant for outbound and inbound calls; always discloses it is AI and that the call is recorded; live takeover; post-call regex check; transcript analysis (`call_analysis`) | **Off by default** (two flags).<br>Never called live: many Vapi and ElevenLabs fields UNVERIFIED (spec §9).<br>Inbound calls are not capped by `phone_daily_call_limit`.<br>"Listen live" not built.<br>Concealment check is regex, so a paraphrase can slip.<br>A lead-less inbound caller cannot be erased.<br>Provider minutes are not in usage_meter.<br>Legal review pending (§7). | Live proof first.<br>Model-based post-call identity check as a second layer (the regex stays as the guard).<br>Cap inbound minutes.<br>Meter provider minutes into the spend view. |
| **Help AI (support chat)** | `app/services/support_chat.py:391` `answer_question`. Retrieval: `app/services/help_center.py` (BM25 + synonyms, 44 articles). API: `app/api/support.py:282`. UI: `frontend/src/components/support/ChatWidget.tsx`, `MessageSources.tsx`. Admin queue: `(admin)/admin/support-tickets/page.tsx`. Specs: `docs/features/ai-support-chat.md`, `docs/program/help-center-eval.md` | Answers only from help-center chunks; three refusal guards; ticket fallback; 30-day history | Prod key was invalid until 2026-10-18 (mock answers only); live baseline not measured (HELPAI-KEY).<br>Refusal and injection resistance unmeasured on a real model (Outstanding #2, #4).<br>**Nobody is notified of new tickets** (Outstanding #3, M), yet the widget promises 24h.<br>No global cost ceiling (#5).<br>Mock recall: 42/77 answered, 3 wrong; recall@6 0.974.<br>Retention 30 days, so no demand data. Voyage embeddings decided but not shipped (Phase 2).<br>Rate-limit mismatch 30 vs 20 (#40). | Ship embeddings + rerank (decided).<br>Thumbs up/down (HELPAI-DEMAND).<br>Ticket notifications.<br>**Account-aware answers:** call `send_diagnostics` / plan / status for "why is my campaign not sending?" instead of generic articles.<br>AI first-draft answers for admin tickets. |
| **MCP connector** | `app/mcp/server.py:71` `build_server`. Tools in `app/mcp/tools/{leads,strategies,messages,insights,campaigns,chatgpt}.py`. OAuth in `app/services/oauth_server.py`, `app/api/oauth.py`. Skill `.claude/skills/leadpilot-outbound/`. Spec: `docs/features/mcp-connector.md` | 11 read tools (leads with F-P-T-A, strategies, pipeline status, messages, attribution, claim log, ChatGPT search/fetch) + `list_products` + 3 write tools (`create_strategy`, `pause_campaign`, `resume_campaign`), all audited and tenant-scoped; prospect text delimited as untrusted | `MCP_ENABLED=false` by default.<br>No workspace support (own account only).<br>No approve, send or schedule (deliberate).<br>No CIMD / `private_key_jwt`. | Read tools for the inbox (needs-reply threads), the review queue and send diagnostics ("what needs me today?").<br>Draft-only write tools (create a Copilot draft or an edit, never send).<br>Workspace scoping. |
| Other AI already in product (for completeness) | Strategy pipeline + verification loop (`app/pipeline/engine.py`, `app/verification/loop.py`); consensus Claude + GPT-4o (`consensus.py`, off); ICP extraction (`icp_extraction.py`); lead scoring (`lead_scoring.py`); reply classification / intent / fraud / sentiment / intelligence; sequence red-team (`adversarial_review.py:268`); strategy mutation (`strategy_mutation.py:261`); personalization + Loom scripts (`message_personalization.py`, `loom_video.py`); re-engagement memory; displacement DMs; LinkedIn and email-network drafts (`network_messages.py`, `email_network_messages.py`); WhatsApp template drafts (`app/api/whatsapp_templates.py:220`); meeting summaries (`meeting_ai.py:156`); call analysis (`phone_calls.py`); voice and style profile (`voice_profiler.py`, `style_profile.py`); website builder (`website_builder.py`); Quickstart | — | Learning loop sees almost no send data (#2, H, fixed per product-defects).<br>Playbook scores pooled across accounts (#27/#44, F-DB-01, open).<br>Analytics "Booked" variant column always 0 (gaps-sweep-2 out of scope).<br>`personalization_scorer` reports no data on SQLite. | — |

---

## 4. Manual workflows (route by route)

Columns:
- **Freq**: how often per active user (ASSUMPTION unless cited).
- **AI could**: the opportunity.
- **DET?**: Y means part of the step must stay deterministic or human; the AI may only assist around it.

### 4.1 Core daily loop (help-center 31 "five stops", 32 SDR guide)

| # | Route / file | What the user does manually | Freq | What AI could do | DET? |
|---|---|---|---|---|---|
| W1 | `/send-approval` (`(app)/send-approval/page.tsx`, `app/api/send_approval.py`, `daily_send_approval.py`) | Reads queued counts per channel, ticks channels (LinkedIn needs a separate acknowledgement), presses Approve or Decline for today | **Daily**, stop #1 (article 31) | Pre-decision **summary**: what is queued, unusual volume, flagged copy, deliverability state, "safe to approve?" checklist. **AI must never approve.** | **Y, the daily send approval** (founder decision 2026-10-11) |
| W2 | `/inbox` (`(app)/inbox/page.tsx`; `ConversationThread`) | Reads Needs-reply threads oldest first, writes answers (in Gmail or by phone when Copilot is off), presses Mark handled; checks Overdue | **Daily**, stop #2 | Copilot on by default for drafts; triage order by intent and value (not just age); thread summary; "suggest mark handled" for no-answer-needed replies; WhatsApp drafts | Partly: opt-out/STOP detection, suppression and send gates stay deterministic (Copilot already enforces this, `reply_copilot.py:260,368`) |
| W3 | `/campaigns` Review tab (`ReviewQueuePanel.tsx`; `send_review.py` triggers :108-193) | Approves, edits or rejects held messages (prior objection, stalled deal, VIP title, tone); "Going stale" after 3 days | **Daily**, stop #3. #17: the VIP rule holds most first emails to the ICP | Per item: say **why** it was held and suggest an edit. Batch-suggest approvals for low-risk items. Rewrite stale time references. Human still decides | **Y**: the human gate itself; claim and forbidden-phrase re-checks at approve and send |
| W4 | Settings → Deliverability (`MailboxHealthCard`, `DeliverabilityCard`) | Looks for throttled or paused mailboxes, presses Resume; reads SPF/DKIM/DMARC status; fixes DNS at the provider | Daily glance, weekly check | Explain the cause and give exact DNS records for the user's provider (article 35); advise whether resuming is safe | **Y**: pause thresholds, ramp and bounce pause (send-rate limits) |
| W5 | `/strategies`, `/strategies/detail` (status cards; `ResumeStrategyButton`, `ReverifyStrategyButton`, `OverridePassesPanel`) | Watches status; on `needs_human_review` chooses Re-verify, manual pass (≥20-char reason, ≤3 checks, never Legal) or a new strategy; on `budget_exhausted` raises the budget | Per strategy, 1–3 times (ASSUMPTION) | Explain each failed check in plain words and propose a fix to the inputs, or a targeted re-run of only the failing checks. Draft the override reason **for the person to edit**. | **Y**: Legal & compliance check can never be overridden; budget / daily AI cap; human sign-off |
| W6 | `/campaigns` overview + `SendDiagnosticsPanel` | Reads "Campaign paused" banner and diagnosis reasons; navigates to each fix | When something stalls (ASSUMPTION weekly) | Narrative of the root cause; proactive alert when nothing has sent for N hours (#35 Gmail revoked has no notification) | **Y**: the reasons must come from the real gates (`send_diagnostics.py`) |

### 4.2 Setup and campaign creation

| # | Route / file | What the user does manually | Freq | What AI could do | DET? |
|---|---|---|---|---|---|
| W7 | `/strategies/new` (`components/intake/wizard.ts`; `strategies/new/page.tsx:91-270`) | Types product name and description (article 33 asks for what / who / where / price / why now / not for); local-business fields; past clients (details + acquisition story per client); ticks Autopilot and lawful basis | Once per product or strategy | Fill the description from a website URL (Quickstart already fetches sites, `f06-quickstart.md`); interview-style prompts that score the description against article 33's checklist; import past clients from CRM or deals | **Y**: the lawful-basis tick and Autopilot opt-in stay human; `max_strategies`; daily AI cap; budget |
| W8 | `/strategies/detail` → `OutreachPanel.tsx:21-110` (**manual launch**) | Picks a lead count, presses Find leads, reviews the list and drops leads by hand, **writes the opening-email brief and follow-up brief from scratch**, sets the follow-up days, ticks the lawful basis, launches | Per strategy or launch | **Pre-fill the briefs** from research via `autopilot.plan_steps` (`autopilot.py:593`), which Autopilot already does; flag weak leads to drop (F-P-T-A, champion staleness) | **Y**: lawful-basis confirmation; the sequence red-team gate; SDR approval; `max_leads_per_strategy`; channel plan gate |
| W9 | `/campaigns` → `SequenceReviewPanel.tsx` (A7 red-team) | Reads blocking findings, edits copy, re-runs; a manager overrides with a written reason | Per sequence | Suggest a fix for each finding (one click "apply rewrite", then re-review) | **Y**: launch refused while blocked; manager override |
| W10 | `/campaigns` WhatsApp templates (`TemplateEditor.tsx`; `app/api/whatsapp_templates.py:220`) | Writes or edits template drafts; one variable description per placeholder; opt-out line; submits to Meta | Rare (per campaign) | AI drafts already exist ("AI-generated drafts — pick one"). Add auto-filled variable descriptions and example values (the submit sends none, #36), and Meta-policy pre-checks | **Y**: STOP/opt-out text (#28, not enforced); template approval is Meta's; templates are deployment-wide (F-SEC-05) |
| W11 | `/quickstart` (`quickstart/page.tsx`) | Enters website + one-line offer; reviews, copies or discards review-only drafts | Once (flag off by default) | Already AI. Could hand drafts over as the W8 briefs | **Y**: no send path by design |
| W12 | `/settings` integrations (Gmail / Slack / HubSpot / Salesforce / LinkedIn / webhooks / API keys; `CrmCards`, `WebhooksCard`, `LinkedInAccountsCard`) | Connects OAuth accounts, sets CRM field mappings and webhooks; Gmail callback returns raw JSON (#16) | Once, plus on revocations | Suggest CRM field and status mappings (#33/#34 show mapping gaps); a setup checklist assistant | **Y**: auth/OAuth, RBAC (#29: SDRs can start connects, H) |
| W13 | Settings → Guardrails (`GuardrailsCard.tsx`; `app/api/guardrails.py:112-191`) | Types exclusion lists (manual, CSV, CRM sync) and the per-product approved-claims and forbidden-phrases library | Once per product, occasional edits | **Propose approved claims** from the product description and research (a person approves each); suggest forbidden phrases from industry and regulator lists | **Y**: exclusions are a suppression-class guard; the library is enforced at send |
| W14 | `/calendar`, `/calendar/booking-pages` | Sets weekly availability, creates booking pages (durations, caps, notice) | Once, occasional | Import availability from Google Calendar; suggest page set-ups | Partly: per-host double-booking (#14) must stay deterministic |
| W15 | Settings → Voice / Voice twin (`VoiceSettings`, `VoiceTwinCard`) | Records consent, uploads samples, captcha verification, sets call options | Once (flags off) | Already AI. Coach recording quality | **Y**: consent, disclosure, identity rules |
| W16 | `/onboarding/verify` | Location, entity type, SMS code | Once | None worth doing | **Y**: identity and phone verification (auth) |
| W17 | `/team`, `/invite`, `/clients` | Invites members and assigns roles; approves or declines SDR launches with notes; agency clients, domains, fees (fee editing is API-only, #43) | Weekly (agency) | Summarise a pending launch for the approver (risk, volume, red-team result) | **Y**: RBAC, launch approval |
| W18 | `/pilot` (F09) | Buyer writes success targets (nothing pre-filled), picks campaigns | Once per pilot | Suggest realistic targets from benchmarks (article 41) and the account's history, **clearly labelled** | Partly: scorecard numbers come from `meetings_ledger` (deterministic) |

### 4.3 Lead and pipeline work

| # | Route / file | What the user does manually | Freq | What AI could do | DET? |
|---|---|---|---|---|---|
| W19 | `/pipeline` kanban (`pipeline/page.tsx`) | Drags leads between stages; deletes (GDPR) | Daily/weekly for active sellers | Suggest stage moves from replies, meetings and outcomes (e.g. "booked → held?") | **Y**: closed statuses stop sequences (`stop_for_status` safety guard); GDPR erase |
| W20 | `/crm/table` (`DataGrid`, `GridToolbar`, `LeadNotesPanel`; `app/api/crm.py:252-941`) | Inline edits, bulk status changes, tags, notes, saved views, custom fields, round-robin assignment, CSV export | Daily for SDRs | NL filter ("leads who replied positively last week but have no meeting"); auto-tagging; note summarisation; next-best-action column | **Y**: bulk close → sequence stop (atomic, R6); distribution needs manager |
| W21 | `/leads/detail` tabs (Score, F-P-T-A, Why this prospect, Signal Radar, Consent, Provenance, Email verdict, Champion, Claim checks, Personalization, Meeting prep, Calls, Re-engagement) | Reads 12+ panels to decide whether and how to contact; rescore; re-verify or confirm a champion role with a reason; withdraw consent; log outcome | Per lead touched (ASSUMPTION 5–20/day) | **One "lead brief" summary** across the panels, with a recommended action | **Y**: consent withdrawal, champion confirmation reason (compliance audit), suppression |
| W22 | `LogOutcomeDialog.tsx` / `FollowupDraftCard.tsx` | Picks an outcome, **pastes notes by hand**, reviews the AI follow-up, sends | Per meeting | Pre-fill the notes and outcome from the Recall transcript or AI summary (`meeting_ai.py:156`); suggest deal value and stage | **Y**: send goes through the suppression check; never auto-send (spec) |
| W23 | `/crm/replies` (`crm/replies/page.tsx`; `crm.py:1335-1390`) | Reviews authenticity and intent scores; reclassify or rescore by hand; Feature 2 draft approve = CRM note | When a classification looks wrong | Explain disagreements; collapse into the Inbox / Copilot flow | **Y**: unsubscribe and machine-mail rules are deterministic (article 13 line 72) |
| W24 | `/network` (LinkedIn + Email tabs; `EmailNetworkPanel.tsx`) | Uploads exports or a Gmail scan; reviews matches; drafts, edits and saves messages; adds people to campaigns | Occasional (Growth+) | Already AI-drafted. Add ranking explanations and batch drafts | **Y**: daily approval for network bulk sends; plan gate |
| W25 | `/meetings`, `/meetings/detail`, `/meetings/transcript` | Reads upcoming and past meetings, AI summary, transcript | Per meeting | Action items synced to tasks or CRM; follow-up already exists | — |
| W26 | Lead sourcing (`POST /strategies/{id}/leads/source`) | Chooses a count; a run that finds nobody shows no message (#42) | Weekly (article 31: freshness falls) | Explain zero results and suggest widened ICP criteria | **Y**: `max_leads_per_strategy`, Spend Guard credits, Bounce Shield |

### 4.4 Analytics and reporting

| # | Route / file | What the user does manually | Freq | What AI could do | DET? |
|---|---|---|---|---|---|
| W27 | `/analytics`, `/analytics/revenue`, `/analytics/usage`, `/crm/dashboard/*` (overview, leads, campaigns, activity) | Reads charts, compares variants and benchmarks; enters costs on Revenue & ROI | **Weekly** (article 31) | Weekly AI digest ("what changed, why, what to do") pushed by email or Slack. NL questions over analytics (MCP partly enables this). Anomaly callouts. No digest exists (grep) | **Y**: the numbers stay SQL-derived; the AI only narrates. Spend and usage numbers are billing-adjacent |
| W28 | `/strategies/document` | Reads the long strategy document, uncertain zones (Claude vs GPT) | Per strategy | Executive summary; Q&A over the document | — |
| W29 | `/learn` | Watches tutorials | Onboarding | Recommend the next tutorial from the user's stuck point | — |

### 4.5 Admin (operator) workflows

| # | Route | Manual work | Freq | AI could | DET? |
|---|---|---|---|---|---|
| A1 | `/admin/support-tickets` | Reads and answers tickets by hand; **no notification** of new tickets | Per ticket | Draft the answer from the help center + account state; triage and priority; notify | — |
| A2 | `/admin/task-errors` | Triages failed Celery tasks | Weekly | Cluster errors, suggest the cause | — |
| A3 | `/admin/identity-reviews` | Clears or confirms country mismatches | Per signup | Summarise evidence only | **Y**: identity / auth decision stays human |
| A4 | `/admin/suppression-list` | Adds and removes suppressions (deletes unaudited, #31) | Rare | None | **Y**: suppression |
| A5 | `/admin/compliance-rules`, `/admin/system-settings`, `/admin/integrations`, `/admin/users`, `/admin/circuit-breakers`, `/admin/health`, `/admin/playbook`, `/admin/tutorials` | Edits rules, flags, keys, users | Rare | Explain a setting's effect before change | **Y**: compliance rules fail-closed; keys; suspensions |

---

## 5. Must-stay-deterministic boundaries (AI may only assist, never decide)

These hold for all of the above.

**Auth and access**
- Auth, sessions, OAuth and RBAC: `auth.check_account_usable`, `rbac.py`.
- Identity and phone verification.

**Money and limits**
- Billing, Stripe and plan changes.
- Plan limits: `plans.py` `check_plan_limit` / `check_feature` / `check_channel` / `check_plan_quantity`.
- The daily AI cap and per-strategy budgets (`usage_meter.check_budget`).
- Spend Guard monthly cap.

**Contact rules**
- Suppression, unsubscribe, STOP and opt-out detection (Copilot's opt-out guard runs before any model call).
- Consent and lawful basis (`launch_consent.py`, Autopilot lawful basis).
- Exclusion lists.
- Bounce Shield and champion holds.

**Sending**
- Send-rate limits: Gmail daily cap 100, mailbox ramp, bounce pause, send windows, compliance rules.
- **Daily send approval (human, every day)**, launch approval, sequence red-team block and override, send-review queue decisions.
- Claim verification as a backstop at send. The Legal & compliance verification check can never be passed manually.

**Voice calls**
- AI disclosure and identity rules on voice calls.

---

## 6. Suggested AI backlog seeds (ranked by value ÷ risk; ASSUMPTION)

1. **Pre-fill the manual-launch briefs (W8)** from research, reusing `autopilot.plan_steps`. Low risk, about $0.05 per strategy, and it removes the hardest blank-page step.
2. **Turn on Reply Copilot drafts by default or per plan (W2)**, merge in Feature 2's draft, and add "regenerate with instruction". About $0.02 per reply. It hits the daily stop #2.
3. **Review-queue assist (W3):** reason + suggested edit + stale-reference rewrite. The human still decides.
4. **Daily brief (W1 + W6 + W27):** one AI-narrated morning summary feeding the five stops. The numbers come from deterministic gates and SQL. AI never approves.
5. **Outcome notes from transcript (W22)** and **lead brief across panels (W21)**.
6. **Approved-claims proposer (W13)** and **intake from URL (W7)**.
7. **Help AI:** account-aware answers via `send_diagnostics` and plan state; ticket notifications and AI ticket drafts (A1).
8. **MCP read tools** for the inbox, the review queue and diagnostics.

**Fix before building on them:**
- #30 ICP nesting (scores and briefs).
- F-AI-04 model-ID check.
- A production-key and worker-key check (recon §2).
- Some form of feature-usage measurement (§1).

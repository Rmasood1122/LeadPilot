# Help AI v2, Phase 0: recon

Date: 2026-10-18. Read-only; no code changed. Master at `a1e200e`.
Brief: "Help AI v2" (hybrid RAG over a 50-article help center), Phases 0–5.

Each claim cites a file:line or a command. "Measured" means run in this
session; "not checked" means no access, with the reason.

---

## 1. What the 2026-10-10 Phase 2 work shipped

All of it shipped, plus some additions. The brief planned 29 articles and 80
golden questions; the repository has 30 and 111.

| Item | State | Evidence |
|---|---|---|
| Corpus | **30 articles + index + synonyms** (`01-what-is-leadpilot` … `30-contact-support-and-status`, `00-index.md`, `_synonyms.yaml`) | `ls docs/help-center` (32 files); 43,598 words, about 1,450 per article. Article 30 was added by the status-page decision D6 (`DECISIONS.md:17`) |
| Retrieval module | **`app/services/help_center.py` exists** (920 lines) | Module docstring `:1-63`; `Corpus` `:511`; `retrieve()` `:816` (never raises) |
| H2 chunking | Shipped: merge < 120 tokens, split > 700 at H3/paragraph, stable id `<article>#<heading-slug>` | `:96-97`, `_chunk_article` `:452`; **206 chunks** (measured) |
| BM25 + synonyms | Shipped: pure-Python BM25 (k1 1.2, b 0.75), synonym groups, plus stemming, typo correction and heading bigrams | `:20-35`, `_load_synonyms` `:492`, `_stem` `:295`, `_osa_distance` `:717` |
| Golden set | **111 items: 88 answerable, 23 must-refuse** | `tests/help_center/golden_questions.yaml` |
| recall@6 | **0.966 (85/88)**, measured today with `python -m scripts.help_center.measure_golden`. Misses: q11 "ten checks", q65 "STOP on whatsapp" (non-native wording), s03 "How does outreach work?" | `docs/program/help-center-eval.md` still says 0.974 on 77; the set grew afterwards and the doc was not updated |
| Mock-mode gate | `MOCK_MIN_SCORE = 6.0`, `MOCK_MIN_HEADING_COVERAGE = 0.55`; mock path wrong-answer rate 7.1% (3 of 42 answers), must-refuse answered 0/23 | `help_center.py:160-161`; `help-center-eval.md` |
| Fact-check | Agent `.claude/agents/help-center-fact-checker.md`; tables in `docs/program/help-center-factcheck.md` (1,941 lines). First pass 1,467 sentences: 1 unsupported, 65 contradicted, all fixed; every per-article re-check shows 0 unsupported | `help-center-factcheck.md:17`, per-article summaries such as `:86` |
| Code defects found while writing | 28 findings, most fixed since | `docs/program/help-center-discoveries.md` |
| `faq_ids` alias map | `LEGACY_FAQ_ALIASES` maps the 9 old FAQ ids to chunks, so stored rows still resolve | `help_center.py:176-187`; `resolve_citation` `:832` |
| Sources under answers | API returns `sources` (one per article) built by `sources_for`; the widget shows **titles only, no links** | `app/api/support.py:115`; `help_center.py:844`; `frontend/src/lib/support/sources.ts:12`; `components/support/MessageSources.tsx` |
| Public `/help/` | **Already served from the same markdown.** `frontend/src/content/help-center/` is a synced copy (`scripts/help/sync_help_center.mjs`), and a test fails if the copy drifts. Heading anchors use GitHub-style slugs | `frontend/src/lib/content/helpCenter.ts:1-5`; `frontend/src/tests/helpCenterCopy.test.ts:23`; `frontend/src/lib/content/markdown.ts:23-24`; routes `frontend/src/app/help/page.tsx`, `help/[slug]/page.tsx` |
| Drift tests | Plan rows in article 22 equal `PLANS`; every `sources` path exists; links resolve; index is generated. **Not covered:** other numbers sourced from code (caps, retention, thresholds) | `tests/help_center/test_corpus.py:242` and around; `help-center-discoveries.md:7-9` |
| Tests | 219 passed (help-center + support chat), 20 s | `pytest tests/help_center tests/test_support_chat.py`, measured today |
| Sealing | No help-center or support test is in `evals/compliance_testset.yaml` | grep, no match |

Golden coverage per article (measured): 29 of 30 articles are expected by at
least one question. `known-limitations` is never expected; five articles are
expected by exactly one (`personalization-and-claim-verification`,
`send-review-queue`, `meetings-prep-room-transcripts`,
`analytics-health-score-roi`, `glossary`).

## 2. Production: AI_MODE and real usage

**The live model path is not running in production. The Anthropic key on
`leadpilot-api` is invalid.**

- `render.yaml` sets no `AI_MODE`, so auto applies: a key is present, so mode
  resolves to live (`support_chat.py:245-251`). Every call then fails, and the
  permanent-error path serves mock answers (`support_chat.py:453`).
- Render logs for `leadpilot-api`, read with the Render MCP (read-only): every
  support-chat call in the retained window logged `PERMANENT model failure
  (AuthenticationError: 401 ... invalid x-api-key)`. Calls on 2026-10-11 16:19,
  2026-10-12 11:11 and 11:12, and **2026-10-18 07:28 UTC (today)**. There is
  not one `anthropic call ok` line on the API since 2026-10-12.
- So the "Sources: CRM and integrations" a founder sees comes from the mock
  path: BM25 top chunk, verbatim opening paragraph. No model is involved.
- **Out of scope, reported:** if the worker (`leadpilot-worker`) uses the same
  key, every AI feature (pipeline, drafting, scoring) fails in production too.
  The worker log query timed out, so this is **not checked**.

**Usage.** The retained Render logs show **4 `POST /support/chat` calls in
total**, all from one address range (the founders' own sessions).

**The 90-day cluster analysis cannot be done:**
- `chat_messages` are purged after 30 days (`SUPPORT_CHAT_RETENTION_DAYS`,
  `render.yaml:136`, default `app/config.py:299`), so 90 days of rows do not
  exist.
- There is no database access from this session (no `DATABASE_URL`).
- The logs show almost no real users.

The read-only query for the founders is already written:
`docs/program/help_ai_diagnostic.sql`. Its window is 30 days, and its
mock-mode reason codes still name the old FAQ (`mock_faq_match`,
`support_chat.py:318`), which is still the code name.

**Consequence for the manifest:** there is no real-user demand data, so it
cannot drive which 20 articles exist. What can drive it:

1. the golden set's must-refuse items that are really "about LeadPilot, not in
   the corpus" (for example the Learn tab, `LEGACY_FAQ_ALIASES` comment
   `help_center.py:183-184`);
2. features that have code and a founder decision but no article (§5);
3. after launch, the feedback loop in Phase 4.

## 3. Other facts the plan depends on

| Question | Answer | Evidence |
|---|---|---|
| Does `docs/help-center/` ship in the image? | **Yes.** `.dockerignore` re-includes it; the image sets `HELP_CENTER_DIR=/code/docs/help-center` | `.dockerignore:103-105`; `Dockerfile:49-53` |
| Is pgvector enabled on Neon? | **Not checked.** No database credentials in this session. Founder check: `SELECT extname, extversion FROM pg_extension WHERE extname='vector';` and `SELECT name, default_version FROM pg_available_extensions WHERE name='vector';` | — |
| Spend metering every model call uses | `usage_meter.check_budget` before the call and `usage_meter.note(provider, model, in_tokens, out_tokens)` after it, inside a scope. The support route opens `metered(db, user, "support_chat")`, which is a **counted-only purpose, not capped** | `anthropic_client.py:213-219`, `:249-253`; `usage_meter.py:158`, `:85-88`; `app/api/metering.py:64`; `app/api/support.py:282` |
| How a second vendor fits that meter | `note()` takes any provider string, but pricing comes from `_PRICE_KEYS` (anthropic, openai). Voyage needs a `"voyage"` entry and two `system_settings` price keys (pattern: `system_settings.py:74-78`). Embedding has no output tokens, so `note("voyage", model, tokens, 0)` fits as is | `usage_meter.py:118-121`, `:173-185` |
| Conventions for one-off scripts | `python -m scripts.<pkg>.<name>`; repo root on `sys.path`; dry run by default, `--apply` to write (for example `backfill_outcome_attribution.py`); help-center tools in `scripts/help_center/` (`build_index.py`, `measure_golden.py`, `live_eval.py`) | `scripts/help_center/measure_golden.py:1-40` |
| How deploy runs migrations | The API entrypoint runs `python -m app.db.migrate`, then uvicorn. **`leadpilot-api` has auto-deploy off**; a separate `leadpilot-workers` service is suspended. Both API and worker run on the free plan (cold starts) | `scripts/render_api_entrypoint.sh`; Render `get_service` / `list_services` |
| Prompt caching | None: no `cache_control` anywhere in `app/`. The system header is already kept byte-stable for it | `support_chat.py:91-96` |
| Prompt structure today | System header, then `<documents>` (`id`, `title`, no `url`), then `<history>` (escaped), then `<question>` (escaped, marked untrusted). No `<account_context>` | `support_chat.py:352-389` |
| Streaming | `/support/chat` does not stream, so per the brief Phase 4 adds none | `app/api/support.py:226` |
| D1 (website copy vs. code; 72 vs. 144 steps) | **Resolved 2026-10-10, "code is the truth"**, amended 2026-10-13. A test guards the removed claims. 72 steps with past clients, 144 without; outreach is sent automatically within limits | `DECISIONS.md:9`; `frontend/src/tests/websiteClaims.test.ts`; `frontend/src/app/how-it-works/page.tsx:27` |

## 4. Does the corpus earn 50 articles?

**Not as specified.** Ten of the twenty proposed articles overlap an existing
one, and four describe features that are partly missing from the code. Adding
duplicate topics hurts precision: two chunks answering the same question
compete in the top 6, and the mock gate's heading-coverage score splits
between them.

| # | Proposed | Code behind it | Overlaps | Recommendation |
|---|---|---|---|---|
| 31 | guide-solo-founder | workflow across existing features | 03, 25 | **Keep** as a task guide that links to the existing articles; no new facts |
| 32 | guide-agency-admin | `app/services/workspaces.py`, `rbac.py` | **24** | **Merge into 24** unless golden questions need both |
| 33 | guide-sdr-team-member | `rbac.py`, `lead_assignment.py` | 24, 12 | Keep, only if member permissions are distinct in `rbac.py` (Phase 1 checks) |
| 34 | first-seven-days-checklist | onboarding exists, but the checklist component is never rendered (discoveries #22, fixed per `fixes/product-defects.md`; re-verify) | **03** | **Merge into 03** |
| 35 | product-profile-and-icp | product/ICP fields, F-P-T-A | 04, 07 | Keep |
| 36 | strategy-patterns-and-playbooks | `pattern_recognition.py`, `score_decay.py`; A/B auto-promotion off (`DECISIONS.md:23`) | 17 | Keep; must say promotion is off |
| 37 | apollo-and-hunter-details | lead sourcing | **06** | **Merge into 06** |
| 38 | google-workspace-admin-setup | `deliverability`, Gmail OAuth | 09, 19 | Keep: DNS steps are a distinct need |
| 39 | whatsapp-business-setup-and-templates | `whatsapp_templates.py` | **10** | **Merge into 10** |
| 40 | hubspot-field-mapping | `app/services/crm_sync.py:1-24` (one module for both CRMs) | 16 | **Merge 40+41 into one** "CRM sync field mapping" |
| 41 | salesforce-field-mapping | same module | 16 | (merged with 40) |
| 42 | webhooks-and-slack-event-reference | `webhook_delivery.py` (HMAC, retries; discoveries #12, #13) | 16 | Keep: a reference page |
| 43 | api-keys-and-public-api | `app/services/auth.py` API keys | — | Keep, **if** a stable public subset is defined. No list of "stable endpoints" exists; someone has to decide it |
| 44 | reply-copilot-and-classification | `docs/features/f04-reply-copilot.md`; founder decision F04-STRICT is the per-account `answer_earlier_replies` setting | 13 | Keep. The brief's "copilot strictness per user" does not exist under that name; the article documents `answer_earlier_replies` |
| 45 | daily-send-approval-and-notifications | `docs/features/daily-send-approval.md`, `app/services/daily_send_approval.py`, LinkedIn risk acknowledgement (`DECISIONS.md:25`) | 09, 25 | Keep. **No desktop notification code found** (grep: no web-push or `Notification` API), so the article must say so or drop it |
| 46 | annual-plan-and-billing-faq | `app/services/billing.py:1-16`, `:67-74`; ANNUAL-PRICE ×10 (`DECISIONS.md:22`); flag `annual_billing_enabled` | **22** | Keep, generated from `PLANS` and `billing.py` (read only; billing code is not touched) |
| 47 | benchmarks-what-good-looks-like | benchmark thresholds in `system_settings.py` and verification passes | 18, 19 | Keep, only with numbers generated from code |
| 48 | security-faq-for-buyers | `audit_trail.py` (hash chain), `safe_fetch.py` (SSRF), webhook HMAC, `auth.py` | 23 | Keep |
| 49 | data-processing-and-subprocessors | provider config across `app/config.py` | 21 | Keep; Voyage listed only after approval; must say what is not implemented |
| 50 | whats-new | **no git tags and no CHANGELOG** (`git tag` is empty) | — | **Drop for now.** Nothing to generate from. Adopt tags first, or generate from merged PR titles (needs a decision) |

Net: about **11 new articles + 6 merges into existing ones = 41 articles**,
unless the expanded golden set (Phase 5, ≥ 150 items) shows questions that
only a separate article answers. I recommend writing the new golden questions
first and creating an article only where questions point to one. Also: the
Learn tab (tutorials) has no article, while a widget starter question asks
about it. That is a real gap the proposed manifest does not list.

## 5. Plan notes for Phases 2–4

- **Fix the key before measuring anything.** A live baseline (`live_eval.py`)
  has never run, and production cannot run one with an invalid key. The
  before/after table in Phase 5 needs a live row for the current BM25 corpus,
  measured with a valid key, before hybrid retrieval changes anything.
- **Headroom on the current golden set is 3 questions.** Hybrid recall can rise
  from 0.966 to at most 1.0 there. To show what dense retrieval and reranking
  add, the expanded set needs paraphrase-heavy, multi-turn and
  cross-article items written before the new retriever exists, so they are not
  tuned to it.
- **Deploy order.** The migration (`CREATE EXTENSION vector`, `help_chunks`)
  runs in the API entrypoint. Reindex needs the Voyage key and network. If it
  ran in the entrypoint, a Voyage outage would stop the API from booting.
  Proposal: run it after migrate, non-fatal, logged, with lexical fallback
  covering an empty index; plus a CI staleness check that compares content
  hashes against a committed manifest (no network in CI). Auto-deploy is off on
  the API, so "on deploy" means on each manual deploy.
- **SQLite.** The offline suite cannot create `halfvec`. The column and indexes
  must be created only on PostgreSQL (dialect check in the migration and a
  model type that degrades on SQLite).
- **Cost per keystroke: none.** The widget sends on submit, not per keystroke
  (`POST /support/chat`). Per question: one query embedding, one rerank, and one
  rewrite call only when history exists. `support_chat` is counted-only (not
  capped), and the Voyage spend needs to be added to the same purpose.
- **Contextual retrieval.** Recommend `voyage-context-4` over a
  model-generated context sentence. It needs no extra Anthropic calls at ingest
  and no invalid-key dependency, and it removes one moving part. Then
  `context_sentence` stays empty; it is kept in the schema only if the
  founders choose the other option.

## 6. Questions for the founders

1. **Anthropic key (blocking, before Phase 2 can be measured).** The key on
   `leadpilot-api` is rejected (401) as of 2026-10-18 07:28 UTC. Replace it in
   Render on the API and the worker. *Recommendation:* do it now. It is also
   why every AI feature may be failing in production (not verified on the
   worker).
2. **Voyage AI as embedding and rerank vendor.** *Recommendation:* approve
   `voyage-context-4` at 1024 dims (contextual embeddings, so no separate
   context-sentence step) plus `rerank-2.5-lite`; fallback `voyage-4` with
   generated context sentences. Needs `VOYAGE_API_KEY` on `leadpilot-api`. The
   price and free tier get checked on docs.voyageai.com before any figure goes
   in `DECISIONS.md`.
3. **The manifest.** *Recommendation:* approve the reduced plan in §4: about 11
   new articles (including a Learn-tab article), 6 merges into existing
   articles, drop `whats-new` until releases are tagged. Final count set by the
   expanded golden set, likely about 41, not 50. If you want exactly 50 anyway,
   say so, and I will report the precision cost measured on the golden set.
4. **Public API scope (article 43).** Which endpoints are "stable public"?
   *Recommendation:* defer article 43 until that list exists.
5. **D1.** Already resolved (2026-10-10, amended 2026-10-13). The corpus
   documents one truth: 72 steps with past clients, 144 without; automatic
   sending after daily approval; LinkedIn automation not live. No action
   needed unless that has changed.
6. **pgvector.** Please run the two SQL lines in §3 on Neon (or allow me
   read-only access) so Phase 2's migration is known to work there.
7. **90-day demand data.** It does not exist (30-day retention; 4 widget calls
   in the logs). *Recommendation:* accept the golden set plus the Phase 4
   feedback loop as the demand signal, and run
   `docs/program/help_ai_diagnostic.sql` once for the record.

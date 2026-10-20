# Victorae program — Phase 0 recon and founder questions

Date: 2026-10-20. Program start SHA (master): `7872f9c6d4cda7796d43ed3fe486799a197ed74d`.
Branch: `claude/bold-heisenberg-58xvzj`. Prompt: `docs/program/STAR_VICTORAE.md`.
Phase 0 is read-only: no code changed. Only these program files were added:

- `docs/program/STAR_VICTORAE.md`
- `docs/program/brand/rename-inventory.md`
- `docs/program/ai/ai-inventory.md`
- `docs/program/ai/ai-backlog.md`
- this file
- a `PROGRESS.md` entry

## 1. P0 / HIGH status (step 2) — read this before anything else

**No P0 is open in the code.** Each P0 fix was found on master at the line cited below. The full
table, with commit evidence, is in §1.3.

**But two HIGH items are open, and several founder actions are unconfirmed.**

### 1.1 Open HIGH items in code

| ID | What | Evidence | Why it matters to this program |
|---|---|---|---|
| **F-DB-01** | `playbook_scores` has no account column. Learning rates are pooled across all accounts by `pattern_key`. | `app/db/models.py:1722-1725` | Those pooled rates go into every pipeline prompt under the label "learned from this account's real outcomes" (`app/services/playbook_service.py:69`, called from `app/pipeline/engine.py:144`). That is cross-account data in a prompt, under a false label. It is aggregate rates only, with no PII. Phase 2 must gate a "cross-account data" safety slice at pass^3 = 100%, and the pipeline would fail that slice by design. |
| **RF-5** | One WhatsApp sender per deployment. | `app/config.py:138` | Not AI-related. |

Both are rated MEDIUM in `BASELINE.md` and `status.json`. But `DECISIONS.md` P0-D-ENF
(2026-10-11) kept sign-up open, and the same entry says that makes the HIGH ratings apply. The
docs contradict each other; the code agrees with HIGH.

### 1.2 Founder actions not confirmed in any record

- **GAP-007:** verify `calendarharvest.com` in Resend (SPF/DKIM). See `docs/PRODUCTION_READINESS.md:71,208`.
- **Deploy gating** (Render "After CI Checks Pass", Vercel Deployment Checks). See `GATES.md` §4.
- **PD-1:** the read-only Neon query that must run before migration 0071 is deployed.
- **Production Anthropic key:** replaced 2026-10-18, but no live call has been recorded since, and
  nobody has checked whether the **worker** uses the same key.
- **Branch `gate/sabotage-verify`** still exists (`git ls-remote`, 2026-10-20).

### 1.3 Closed and verified on master

| Item | Evidence |
|---|---|
| P0-1 | `app/workers/tasks.py:96,210` |
| P0-2 | `app/api/billing.py:98` |
| P0-3 | `app/services/auth.py:310,340` |
| P0-4 | `app/workers/outreach_tasks.py:775,953`, SQLite only. There is no PostgreSQL two-worker race test. |
| P0-5 | `app/core/plans.py`, `app/services/usage_meter.py:68-404` |
| P0-5b | `app/api/metering.py:37,64` |
| P0-6 | `app/api/admin.py:273` |
| GDPR export | `app/api/account_data.py:68` |
| GDPR erasure | `app/api/account_data.py:112`. Legal decisions E1–E3 in `docs/features/gdpr-erasure.md` are not in `DECISIONS.md`. |
| Plan enforcement | `app/api/sequences.py:61-83` |
| Sign-up switch | `app/config.py:476-477`, `app/api/auth.py:231,263` |

Stale docs (reported, not fixed): `BASELINE.md` §1 and `status.json` still list GDPR erasure and
the four 2026-10-10 items as open. `GATES.md` §2 still says the only required check is `gate`.
`required_checks.txt` holds 6 more.

**Not verified in this session:**

- CI status on master. The GitHub API refuses numeric repository paths through the proxy; the repo
  now answers with a redirect.
- PR merge metadata. The clone is shallow, at 181 commits.
- Render and Vercel dashboards, and production data.

**Recommendation.** Fix F-DB-01 as its own PR (migration + owner filter) before Phase 2 baselines
the pipeline. Otherwise the cross-account slice is either red from day one, or gets written to
excuse the pipeline. RF-5 can wait; it is not AI-related and does not block this program.

## 2. Brand inventory (step 3)

Full detail: `docs/program/brand/rename-inventory.md` (8 area parts).

- **The product is already called "Vectorae" in code.** "Vectorae" appears 2,896 times in 479
  files, from PR #113 on 2026-10-18. **"Victorae" appears 0 times.** This changes what Phase 1
  is: a fourth name, or a correction of the spelling. See Q-a.
- Approximate totals (units are mixed lines and occurrences): **A ≈ 3,290, B ≈ 1,470, C ≈ 300,
  defects 9**. Another ≥ 99 occurrences name *other* companies (LeadPilot AB and others) and must
  not be replaced.
- **Old names still visible today**, all missed by PR #113:
  - the OpenAPI title and the `GET /` response body ("ClientHunter Enterprise API", `app/main.py:173,402`);
  - the Android launcher label "ClientHunter";
  - the login logo PNG (a "LEADPILOT" wordmark);
  - the homepage video, its poster and the social-share image ("LeadPilot");
  - the pilot scorecard email and the meetings-ledger PDF title ("LeadPilot", locked by the sealed
    `tests/test_pilot_mode.py`);
  - the SDK;
  - eight root docs.
- **Customer-voice defect BR-D1 (HIGH).** The website-builder prompt hard-codes our brand,
  "Calendarharvest" and the founder's name into pages generated for *customers*
  (`app/services/website_builder.py:57,75,76,88`). Also BR-D2: the WhatsApp template placeholder
  "Sam from Vectorae" (`TemplateEditor.tsx:70`).
- **Wrong addresses, not branding** (reported only):
  - `leadpilot.com` belongs to LeadPilot AB, yet our deploy docs, `.env.production.example:110`
    and `frontend/next.config.js:109` use it;
  - `https://leadpilot.io` in `app/services/sitemap.py:26` and `website_builder.py:39`;
  - the SDK defaults to `api.clienthunter.ai`.
- **Android:** no build is possible here. There is no Android SDK, and the repo's Android project
  is missing its Gradle root files, the wrapper, `MainActivity` and `google-services.json`.

## 3. AI inventory (step 4)

Full detail: `docs/program/ai/ai-inventory.md`.

- **36 touchpoints**, all on `claude-sonnet-4-6`. Per Anthropic, that model is **active, with
  retirement no earlier than 2027-02-17**. Checked on platform.claude.com, 2026-10-20.
- **What the gateway does not use:** prefill, `budget_tokens`, caching, Batch, structured outputs.
- **A newer-model blocker the prompt did not anticipate.** The gateway sends `temperature=0.0` on
  every judge and classifier call (`app/services/anthropic_client.py:110,225-228`). Anthropic's
  docs say Claude 4.7 and later return **HTTP 400** for a non-default temperature. So every
  candidate newer than 4.6 needs gateway item I4 first.
- **Known AI findings, verified:**
  - The injection fix in `personalization_context.py` is **done** (`:170,184-187,197`).
  - **Unwrapped untrusted text** still reaches prompts in `meeting_prep`, `loom_video`,
    `market_intel` → pipeline, `roleplay`, and raw lead fields in five writers.
  - "~12k-token stable prefixes" is **wrong as stated**. Every system prompt is ≤ 466 tokens,
    below the 1,024-token cache minimum. The large repeated content is in user prompts, ordered
    unstable-first; the verification judge is the best caching target.
- **Consent paths:**
  - The email opt-out decision in the hot path is LLM-only (`reply_classification.py:81`, at temperature 0).
  - Call stop-request analysis runs at default temperature and **fails open** after 3 failed
    analyses (`phone_calls.py:357`).
- **Evals:**
  - There are no real-model tests, and the eval gate measures no AI metric.
  - The only live evals (Help AI) have never had results recorded.
- **Metering:**
  - Prices are per provider, not per model: Claude is $3/$15 for every model.
  - Cache and batch tokens are not priced, so any Phase 3 cost claim needs the meter fixed first.
  - Per-message AI is counted but not capped.

## 4. Backlog (step 5)

Full detail: `docs/program/ai/ai-backlog.md`. It scores 11 improvements, 5 new features and
3 prerequisites. **Recommended top 5:**

1. I1 consent hardening + I2 injection containment (these are Phase 3 items 1–2 anyway);
2. I7 manual-launch brief pre-fill;
3. I6 Reply Copilot v2;
4. I8 Help AI live baseline + account-aware answers;
5. N2 morning brief.

Recommended outside the five, as engineering fixes:

- I3 (#30, the ICP nesting bug that corrupts F-P-T-A, scoring and meeting prep);
- I4 (gateway modernisation, required for any newer model);
- P3 (F-DB-01).

## 5. Live-eval cost estimate (input to Q-e)

**There is no metering data behind this estimate.** This session cannot read production. The
estimate is built from token sizes in the code; the pipeline-step planner assumes 7,000 input and
1,500 output tokens (`app/config.py:72-75`). It uses Anthropic's list prices read on 2026-10-20.

| Item | Assumption | Cost |
|---|---|---|
| Cases | ≈ 22 user-facing / send-affecting touchpoints × 30 + ≈ 11 internal × 15 ≈ **825 cases**; × k=3 = **2,475 model runs** per model | — |
| Run cost on `claude-sonnet-4-6` ($3 / $15) | 6–7k in, 1.2–1.5k out ≈ $0.036–0.044 per run | **$90–110** |
| Verification-judge touchpoint (T30) | 30 cases × 3 × 10 passes × ≈ 15k input | **≈ $45** |
| Model-graded dimensions | ≈ 40% of runs × 2 judge calls, fixed judge `claude-opus-5-5` ($4 / $20), 3k in / 0.3k out | **≈ $36** |
| **One full baseline run** | | **≈ $170–190** |
| Noise band | 2 baseline runs | **≈ $350–380** |
| Candidate `claude-sonnet-5-5` ($2 / $10) | ≈ 0.67 × the run cost + judge | ≈ $130–150 |
| Candidate `claude-haiku-5-5` ($0.10 / $0.50 under 100k-token prompts) | ≈ 0.03 × the run cost + judge | ≈ $45 |
| Candidate `claude-opus-5-5` ($4 / $20), verification judge T30 only | — | ≈ $70 |
| Phase 3 re-runs | ≈ 6 PRs × affected touchpoints only | ≈ $180 |
| Phase 5 final full run | — | ≈ $180 |
| **Program total** | | **≈ $950–1,050** |

Two ways to cut this:

- **Batch API.** Running k=2 of the 3 repeats through Batch at 50% off cuts the total by about
  a third. Latency is then measured only on the interactive repeat.
- **Fewer runs.** Dropping the second baseline run saves ≈ $180, but then the noise band is guessed
  rather than measured. **Not recommended.**

**Query for the founders.** Read-only, on Neon, run by a founder. It returns aggregate numbers
only, with no PII. It replaces the estimate with measured cost per purpose:

```sql
SELECT purpose, provider, model,
       SUM(calls)                                  AS calls,
       ROUND(SUM(input_tokens)::numeric  / NULLIF(SUM(calls),0)) AS avg_in_tokens,
       ROUND(SUM(output_tokens)::numeric / NULLIF(SUM(calls),0)) AS avg_out_tokens,
       ROUND(SUM(cost_micros)::numeric / 1e6, 2)   AS usd_total,
       ROUND(SUM(cost_micros)::numeric / 1e6 / NULLIF(SUM(calls),0), 4) AS usd_per_call
FROM api_usage
WHERE ts > now() - interval '60 days'
GROUP BY 1,2,3
ORDER BY usd_total DESC;
```

## 6. Questions for the founders (Phase 1 does not start until these are answered)

**Q-a. The name.**
The code says "Vectorae" (PR #113, 2026-10-18); the prompt says "Victorae".
- (1) Is "Victorae" a new name replacing Vectorae, or a typo for Vectorae?
- (2) The exact stylization, and the tagline, if any.
- (3) Does "by Calendarharvest" stay in the brand formula? Page titles are tested for it.
- (4) Does the about page say "formerly LeadPilot"?

*Recommendation:* confirm the spelling in writing before anything else. If it is Vectorae, Phase 1
shrinks to finishing the missed occurrences plus `brand_lint`. Say "formerly LeadPilot" on the
about page only, since that is where people searching the old name land. No tagline until
trademark clearance.

**Q-b. Trademark.** Is clearance for the chosen name done in software classes (Nice 9 and 42)?
`docs/program/ai-visibility/` records the GEO pages as published "before trademark review by
founder choice".
*Recommendation:* no public-facing switch (site, Play listing, OAuth consent screen, emails)
until clearance is done. Phase 1 can still land the internal rename, with the display constant
kept in one place so the switch is one change.

**Q-c. Keep-lists.** Do you approve:
- (1) the Class B keep-list in `rename-inventory.md` §2, including keeping the SDK package
  `clienthunter`? It is unpublished, so renaming it later is cheap.
- (2) the Class C owner list in §3?
- (3) leaving dated historical records in `docs/program/` (474 "A-historical" occurrences)
  unrenamed, allowlisted as historical? Renaming them would falsify the record.
- (4) leaving the test-fixture domain `leadpilot.dev` as is?

*Recommendation:* yes to all four.

**Q-d. Backlog.** Which items do we build in this program?
*Recommendation:* the top 5 in §4, plus the engineering fixes I3, I4 and P3 (F-DB-01) in Phase 3.
Separately: do you want BR-D1 (website builder injecting our brand into customer pages) fixed in
Phase 1? It is a customer-voice defect, not a rename.

**Q-e. Spend and models.** What is the spend ceiling for live evals, and which candidates do we compare?
*Recommendation:*
- A ceiling of **$1,100 for the whole program**, with a hard stop of $250 per single run.
- Baseline `claude-sonnet-4-6`.
- Candidates: `claude-sonnet-5-5` for all touchpoints; `claude-haiku-5-5` for classifiers,
  scoring and judges; `claude-opus-5-5` for the verification judge (T30) only.
- Fixed grader judge: `claude-opus-5-5`.
- Do not use `claude-haiku-4-5`: Anthropic's "not sooner than" retirement date for it was
  2026-10-15, which has already passed.

You also need to confirm that a live-eval key exists that is **not** the production key, and run
the §5 query.

**Q-f. Order.**
*Recommendation:* fix F-DB-01 first (its own PR), then Phase 1. Do you agree?

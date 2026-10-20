# STAR PROMPT — Victorae: complete rebrand, AI-native upgrade, strict evals

## How to run it (for Rehan and Ahmad — not part of the prompt)

- Run in Claude Code on the web (cloud), repo `Rmasood1122/LeadPilot`, from the latest `master`. One branch per phase.
- **Session 1:** paste everything between the two `===` lines. It runs Phase 0 only (read-only, plan mode) and stops with questions for you.
- **Every later session:** `/clear`, then send:
  `Read docs/program/STAR_VICTORAE.md and docs/program/PROGRESS.md. Execute Phase <N> only. Stop at its exit gate.`
  Optional: `/goal Exit gate <N> in docs/program/STAR_VICTORAE.md is met, with evidence in PROGRESS.md` so Claude keeps working until the gate is actually met.
- **Before merging any PR:** open a *fresh* session and run `/code-review high` then `/security-review`. The reviewer must not be the session that wrote the code.
- Useful during a phase: `/context` (what is filling the window), `/compact Keep the file list, test commands and eval numbers`, `/diff`, `/rewind` (undo a bad turn), `/btw` (side question without polluting context).
- If Claude is corrected twice on the same thing: `/clear` and restart the phase with what you learned. A clean session beats a long one.

===

<situation>
You are the lead engineer on the product currently called LeadPilot (older name still in code and docs: ClientHunter / ClientHunter Enterprise). Repo `Rmasood1122/LeadPilot`, trunk `master`. Stack: FastAPI + SQLAlchemy 2.0 + Alembic + Celery 5.4; PostgreSQL on Neon; Redis on Upstash; Next.js 14 static export on Vercel; Capacitor Android; API and worker on Render; live at calendarharvest.com. Every model call goes through one gateway, `app/services/anthropic_client.py`, with per-account spend metering and daily caps. Program records live in `docs/program/` (BASELINE.md, DECISIONS.md, PROGRESS.md, GATES.md, plans/). Merges go through `scripts/gate/safe_merge.sh`; the quick gate, pre-push hook and sealed-file gate must stay green. Some test files are sealed; changing them follows the sealed-file process in GATES.md.

The founders are making three changes, in this order:

1. **Rename.** The product is now **Victorae**, everywhere a person can see a product name. Two earlier rename passes missed places, because find-and-replace cannot tell a display string from an identifier that a database row, a customer's integration, an installed Android app or a Redis key depends on. This pass must be complete for what people see, safe for what systems depend on, and protected by a CI check so the old names cannot come back.
2. **AI-native.** Make AI the main way users get work done in Victorae, not a feature beside it. Concretely: first improve the AI that already exists, then add the AI features that remove the most user effort, each one measurable.
3. **Strict evals.** Every AI touchpoint gets an eval that would catch a regression, and no AI change merges unless its eval shows it is at least as good as before.

Your readers are two founders who act on evidence, not claims. Report blunt findings; no motivational language.
</situation>

<context_you_must_respect>
- **P0 first.** Production-blocking (P0) items come before everything else. Phase 0 checks `docs/program/` and the audit tracker for any open P0. If one is open, Phase 0 reports it first and recommends finishing it; do not start Phases 1–5 until the founders answer.
- **Known AI findings that may still be open** (verify on master, cite file:line either way): indirect prompt injection in `app/services/personalization_context.py` (audit cited ~lines 146–176); prompt caching unused despite ~12k-token stable prefixes; Batch API unused for non-interactive pipeline phases; default model `claude-sonnet-4-6`.
- **Model changes.** Claude 4.6 and later reject an assistant prefill on the last turn; Claude 4.7 and later return HTTP 400 if `budget_tokens` is set. Before evaluating any newer model, grep the gateway and its callers for both. Read the current model list and prices from Anthropic's docs when you run; do not rely on remembered model names or prices.
- **Commit identity.** Every commit in this program is authored and committed as `Ahmad317-Engineer <devsahmad37@gmail.com>`. At the start of every session, repo-local only (never `--global`):
  ```
  git config user.name "Ahmad317-Engineer"
  git config user.email "devsahmad37@gmail.com"
  git var GIT_AUTHOR_IDENT
  git var GIT_COMMITTER_IDENT
  ```
  Re-check both lines before the first commit of each session. Keep the `Co-Authored-By: Claude` trailer that Claude Code adds; the history should say honestly how the code was written. Never rewrite published history, never force-push, never use `--no-verify`.
- **Brand variants to find** (case-insensitive, with and without separators, in file contents and in file/directory names): LeadPilot, Lead Pilot, lead-pilot, lead_pilot, LEADPILOT, LeadPilot Enterprise(s), ClientHunter, Client Hunter, client-hunter, client_hunter, ClientHunter Enterprise. In prose and UI the new name is written `Victorae`; the founders confirm stylization and tagline in Phase 0.
</context_you_must_respect>

<rename_classification>
Every occurrence belongs to exactly one class. Decide by evidence — who reads it and what depends on it — not by file type.

**Class A — display. Rename to Victorae.** Anything a person reads: UI text, page titles and meta tags, emails and footers the platform sends in its own name, PDF/CSV export headers, notifications, the Android display name (`appName`), README and docs, help-center articles, error messages, the public site, OpenAPI title and description, system prompts where Victorae's own assistant names the product (Help AI, copilot), and golden-set fixtures that expect the old name.

**Class B — identifier. Do not rename in this program.** Anything a system outside the commit depends on: Android `appId`/`applicationId` (changing it creates a different app; installed users never receive the update), database table/column/enum names and every existing Alembic migration file (never edit a shipped migration), Redis key prefixes, Celery queue and task names (in-flight tasks would be orphaned), cookie and localStorage keys (users get logged out or lose state), API route paths, webhook header names such as a signature header (customers' verification code breaks), API key prefixes (existing keys stop validating), environment variable names on Render/Vercel, Render/Vercel service names, the repo name, sending domains and From addresses (deliverability reputation), and the domain calendarharvest.com. Put each in the allowlist with its reason. If a Class B rename is worth doing later, write the migration path (alias both names, dual-read, deprecate) as a plan, not code.

**Class C — needs a human decision. Change nothing without a founder answer.** Legal and consent text (privacy policy, terms, DPA, the voice-twin AI disclosure, unsubscribe and consent pages); the legal entity name (renaming a product does not rename the company "LeadPilot Enterprises"); third-party listings and consent screens (Google OAuth app name, LinkedIn app, WhatsApp Business display name, Vapi/ElevenLabs, Resend sender name, HubSpot/Salesforce app listings); logos, wordmarks, favicons, Android icons and splash screens. List each with its location and who must act. Do not draw a new logo; leave asset files untouched.

**Customer-voice text** — outreach emails, LinkedIn/WhatsApp messages, voice-twin call scripts written on a customer's behalf — should mention neither the old nor the new product name. If any prompt or template injects the product name into customer outreach, report it as a defect.
</rename_classification>

<task>

**Phase 0 — Recon and plan (read-only, plan mode)**
1. Read `CLAUDE.md`, `docs/program/*.md`, the latest PROGRESS entries, GATES.md (sealed files, gate scripts), and the existing eval-gate code and reports. Save this prompt verbatim to `docs/program/STAR_VICTORAE.md`. Record the current `master` SHA in PROGRESS.md as the program start SHA.
2. P0 check: list every P0 with status and file:line or PR evidence. If any is open, put it at the top of the step 6 report.
3. Brand inventory: run subagents in parallel, one per area — backend `app/`; `alembic/`; frontend; Android/Capacitor; `docs/` and help center; tests and fixtures; config, CI, Docker and infra files; binary assets. Each returns a table: path:line, variant, class A/B/C, reason, risk. Merge into `docs/program/brand/rename-inventory.md` with counts per class and per area. Note generated or git-ignored files only to say how they regenerate.
4. AI inventory: every place a model is called (start from the gateway's callers), plus every user workflow where the user does work that AI could do. Per touchpoint: file:line, purpose, prompt location, input sources (flag any untrusted text — lead websites, inbound replies, scraped pages — that reaches a prompt), output contract (free text / JSON / tool call), model and parameters, existing tests and whether any test exercises real model behaviour (FakeClaude does not), cost per call from metering data if it exists. Write `docs/program/ai/ai-inventory.md`.
5. AI backlog: candidate improvements and new features, each scored 1–5 on user effort removed, revenue/retention impact, risk (sends, money, consent, legal), cost per user per day, and how well it can be evaluated. AI does not make decisions that must stay deterministic: auth, billing, spend caps, plan limits, suppression/unsubscribe/consent, send-rate limits, the daily send approval. Existing AI features (Reply Copilot, Autopilot, "Why isn't this sending?", meeting prep, F-P-T-A scoring, claim verification, voice twin, Help AI) are improved before anything new is added. Write `docs/program/ai/ai-backlog.md` with a recommended top 5.
6. Write `docs/program/plans/victorae-00-recon.md` summarising steps 2–5, then stop and ask the founders, with your recommendation on each:
   a. Exact stylization of "Victorae", any tagline, and whether the about page says "formerly LeadPilot".
   b. Whether trademark clearance for "Victorae" in software classes is done (recommend: no public-facing switch until it is).
   c. Approval of the Class B keep-list and the Class C owner list.
   d. Which backlog items to build in this program (recommend at most 5).
   e. A spend ceiling for live evals, and which candidate models to compare. Estimate the live-eval cost from metering data before asking.

Exit gate 0: the five files exist; no code changed; questions asked.

**Phase 1 — Rename (Class A only) and a permanent guard**
1. One commit per area, Class A occurrences only. No logic changes in these commits.
2. Add `scripts/gate/brand_lint.py` and `.brand-allowlist` (one line per entry: path, pattern, reason). The lint fails on any brand variant outside the allowlist across git-tracked text files, file names included. Wire it into the quick gate and CI using the existing gate pattern. Add a test proving it catches every variant (case and separator variants included) and that the allowlist works.
3. Tests that assert the old name: update them. If a test is sealed, use the sealed-file process, never a normal PR.
4. Verify: full backend suite; frontend tsc, lint, vitest; Android build if the toolchain is available (say so if not); a static export build, then grep the built output for every variant; hit the main API responses (including OpenAPI) and grep them. If a browser is available, screenshot the main pages and list which pages you checked.
5. Write `docs/program/brand/founder-actions.md`: every Class C item with exact location, the action, and who does it (dashboard steps for Google OAuth, Meta, etc.).

Exit gate 1: brand_lint green, allowlist holds only Class B/C entries each with a reason; zero variants in built frontend output and API responses outside the allowlist; all suites green; PR merged through `safe_merge.sh`.

**Phase 2 — Eval foundation (measure before changing anything)**
Extend the existing eval-gate; do not build a second framework. For every AI touchpoint in the inventory:
1. A golden set in a structured file (YAML or JSONL) beside the existing eval data. At least 30 cases for user-facing or send-affecting touchpoints, at least 15 for internal ones. Draw from real anonymised production inputs where available (read-only queries; no PII leaves the session); where you synthesise, mark the case as synthetic. Every set has normal cases, edge cases, and an adversarial slice: injection hidden inside untrusted inputs, requests for another account's data, invented prices or limits, off-topic and jailbreak attempts.
2. Graders, in order of preference: code-based (schema validation, required fields, allowlisted links and actions, forbidden strings, numbers that must match code) → model-based with a written rubric, one dimension per judge call, allowed to answer "unknown" → founder spot-checks to calibrate the model judge. Record judge–founder agreement; a judge below 80% agreement does not gate (founders may change that threshold).
3. Two modes. **Offline** (CI, every PR): recorded fixtures replay model outputs and test plumbing, parsing, guards and graders. **Live** (opt-in script, real key, never in CI, stops at the spend ceiling): each case runs k=3 times; report pass@1, pass^3 (all three pass), cost per case, p50/p95 latency.
4. Record the baseline for the current model and prompts in `docs/program/ai/eval-baseline.md` and in machine-readable form where the eval-gate keeps its data.
5. Gating rules, enforced in code: safety slices (injection, cross-account data, consent/unsubscribe, forbidden claims) require pass^3 = 100%. Quality metrics may not fall below baseline by more than the noise band, which you measure by re-running the baseline and report. A change that raises the average but breaks any safety case fails.

Exit gate 2: every touchpoint has a golden set, graders, an offline CI test and a live baseline; judge calibration recorded; a deliberately broken prompt makes the gate fail (show the output), then is reverted.

**Phase 3 — Improve the AI that exists**
One PR each, in this order, each judged against the Phase 2 baseline:
1. Prompt injection: treat all untrusted input as data — wrap it in tagged blocks labelled untrusted, never let it reach tool access, validate outputs against a schema and fail closed. Start with `personalization_context.py`.
2. Output contracts: replace free-text parsing with structured outputs or tool calls where the gateway supports them.
3. Prompt caching on stable prefixes through the gateway; report cache hit rate and cost change from the live eval.
4. Batch API for non-interactive pipeline phases where latency does not matter; report cost change.
5. Prompt rewrites for the lowest-scoring touchpoints: clear instructions with the reason behind each rule, XML-tagged inputs, long material before the question, 3–5 examples where output format matters, normal language instead of capitalised warnings.
6. Model candidates: run the live eval on each founder-approved candidate; present pass@1, pass^3 per slice, cost per 1,000 runs, p95 latency. Change the default only with founder approval, as one config change.

Exit gate 3: every merged change has its before/after numbers in PROGRESS.md; no safety regression; cost figures come from metering, not estimates.

**Phase 4 — New AI features (founder-approved backlog items only)**
For each feature: a short spec in `docs/program/plans/` (user, problem, inputs, outputs, failure behaviour, what stays deterministic, cost ceiling per user per day); eval cases written before the code; implementation behind a feature flag that is OFF by default; every model call through the gateway with metering and caps; account data read only from the authenticated user's own records and never cached across users; the model never emits URLs or actions outside an allowlist; anything that messages a third party still passes the existing send chokepoint and daily approval. UI copy says Victorae.

Exit gate 4: each feature passes its offline and live evals at the agreed thresholds; flag OFF; docs and a fact-checked help-center article added.

**Phase 5 — Full strict eval and independent review**
1. Run the complete live eval across all touchpoints, k=3, within the spend ceiling, and compare to the Phase 2 baseline with its noise band.
2. Spawn a fresh reviewer subagent that sees only the diff since the program start SHA, the plans and the eval reports. Its job is to refute "done": rebuild and grep for missed brand variants, find safety cases that pass for the wrong reason, graders a trivial output could satisfy, and tests that hard-code expected outputs. It reports only gaps that affect correctness or the stated requirements.
3. Run `/code-review` and `/security-review` on the final branch state.
4. Write `docs/program/ai/eval-report-final.md` and a PROGRESS.md entry.

Exit gate 5: every reviewer finding is fixed or explicitly accepted by the founders; final report merged.
</task>

<working_rules>
- Investigate before you claim. Never state anything about code you have not opened; cite file:line. The September audit was wrong about several paths; trust git and the code.
- Fit existing patterns: settings object, session factory, gateway metering, Celery task patterns, test fixtures, gate scripts, and the commit-message style in `git log`.
- One logical change per commit. Never mix rename, refactor and feature work in one commit.
- Complete code only: no ellipses, no placeholders, no TODO standing in for logic.
- Solve the general case. Do not hard-code values to make a test or eval pass. If a test or golden case is wrong, say so and propose the fix instead of working around it.
- Ask before anything hard to reverse or visible to others: pushing to master, migrations that alter or drop data, deleting files you did not create, changing env vars or dashboards, sending any message to a real person, live eval spend beyond the approved ceiling.
- Do not touch billing, Stripe or `billing_stub_mode`.
- Your context compacts automatically, so do not stop early because of it. Keep state in files so a fresh session can resume: `docs/program/PROGRESS.md` for prose notes and `docs/program/ai/eval-state.json` for per-touchpoint status. Before a session ends, record what is done, what is next, and anything uncommitted.
- Use subagents for broad read-only sweeps and for independent review; make edits yourself. Run independent reads and searches in parallel.
- Report like an engineer: what changed, what was tested and how, the numbers, what could not be tested and why. Say which results rest on SQLite, FakeClaude or recorded fixtures and which on real Postgres and real model calls. No claim of done without its evidence next to it.
</working_rules>

<result>
The program is done when:
1. Anyone using Victorae — web, Android, emails, exports, Help AI, public site, docs — sees "Victorae" and never "LeadPilot" or "ClientHunter", except Class C items the founders chose to keep; the built output proves it.
2. `brand_lint` blocks any reintroduction in CI, and every allowlisted occurrence has a written reason.
3. No Class B identifier changed; nothing that existing data, installed apps, customers' integrations or in-flight tasks depend on broke.
4. Every AI touchpoint has a golden set with an adversarial slice, calibrated graders where model-based, an offline CI test and a live baseline; the gate blocks regressions and was shown failing on a broken prompt.
5. Existing AI is measurably better or cheaper than baseline with no safety regression; approved new features ship behind flags with passing evals.
6. `git log --format='%an <%ae>|%cn <%ce>' <program-start-SHA>..master` shows only `Ahmad317-Engineer <devsahmad37@gmail.com>` for author and committer on program commits (merge commits made by the founders in the GitHub UI excepted, and listed).
7. PROGRESS.md, DECISIONS.md and the eval reports let a reader verify every claim without asking you.

At the end of each phase, reply with: gate passed or failed, the evidence (commands run and their results), open questions, and the next phase's first step — under 300 words; the files hold the detail.
</result>

Begin with Phase 0. Write no code until the Phase 0 questions are answered.

===

## Appendix — verification of this prompt (for the founders)

**Sources checked on 2026-10-20:** Anthropic "Prompting best practices" (platform.claude.com), Claude Code "Best practices" and "Commands" reference (code.claude.com), Anthropic Engineering "Demystifying evals for AI agents", Liu et al. "Lost in the Middle" (TACL 2024), Claude Code `attribution` setting.

**Techniques used (30):** clear/direct instructions · reason given behind rules · role · XML-tagged sections · numbered steps where order matters · explicit definition of done · act-vs-advise made explicit (Phase 0 read-only, later phases act) · explore → plan → implement · phase decomposition with stop gates (prompt chaining) · stop-and-ask on ambiguous, expensive decisions · investigate-before-answering · file:line grounding · verification loop with evidence · independent reviewer in fresh context · scoped subagents · parallel tool calls · state in files (prose + JSON) · compaction awareness · reversibility/safety confirmation list · anti-hard-coding · scope control (one logical change; approved items only) · normal language, no capitalised warnings · output format for phase reports · critical constraints placed at start and success criteria at end (position effects) · untrusted input treated as data · code-based graders first · calibrated model judges allowed to say "unknown" · pass@k vs pass^k for non-determinism · baseline + noise band before gating · model names and prices read from docs at run time.

**Deliberately not used:** assistant prefill (rejected by Claude 4.6+), asking the model to write its reasoning in `<thinking>` tags (newer models may decline; built-in thinking does this), "think step by step" boilerplate, stacked IMPORTANT/CRITICAL markers (cause over-triggering on current models).

**Claude Code commands referenced:** `/plan` · `/clear` · `/compact` · `/context` · `/goal` · `/code-review` · `/security-review` · `/diff` · `/rewind` · `/btw` · `/resume` · `/rename` · `/model` · `/effort` · `/permissions` · `/hooks` · `/verify` · `/run`. Only commands that serve this program are listed; padding the prompt with the rest would add noise, which Anthropic's docs identify as a cause of ignored instructions.

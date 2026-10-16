# LeadPilot GEO Domination — Live State
Last Updated: 2026-10-16 11:45 UTC

## Overall Progress
[x] Phase 1 — Research & Intelligence
[x] Phase 2 — Entity Architecture
[x] Phase 3 — Content Infrastructure
[x] Phase 4 — Technical GEO
[x] Phase 5 — Platform-Specific Optimization
[x] Phase 6 — Authority & Signals
[x] Phase 7 — Monitoring Framework
[x] Phase 8 — Final Verification

## Current Step: Publish round (founder answers 2026-10-16) — COMPLETE in code, waiting for merge + deploy
## Status: 12 GEO pages + help center + llms.txt built and verified on branch claude/relaxed-lamport-ab7g3j; all 15 questions answered
## Last completed action: frontend build + check_static_seo PASS (50 URLs); 1,217 frontend tests pass; geo docs corrected
## Next action: founder: see "Top 3 things to do next (2026-10-16)" at the end
## Blockers: none (questions logged in questions.md)

---

## Work log

### 17:39 UTC — Setup: where this lives and why
Reasoning: success here means nothing I write contradicts what the product actually does or what the live site already says. The repo already contains an AI-visibility program (`docs/program/ai-visibility/`: SPEC, REPORT, PROMPT_TRACKER) and one product-facts source (`frontend/src/content/product-facts.json`), so this GEO system builds on both.

- The GEO system lives in `docs/program/ai-visibility/geo/`, not the repo root. The repo root is a production codebase with gates, and this folder sits next to the existing program it extends. Every path the brief names (`research/…`, `content/…`, etc.) is relative to this folder. Logged as Q-01.
- Facts read before writing: `frontend/src/content/product-facts.json` (description, fit, not-fit, capability status, limits, compliance), `app/core/billing_catalog.py` (prices), `docs/help-center/01, 02, 14, 22, 29` (what it is, who it's for, booking, plans, known limitations), `docs/ICP.md` (customer research), `docs/program/ai-visibility/SPEC.md|REPORT.md|NOTES.md` (prior founder answers, deferred Part B).
- Three corrections to the brief's framing, all logged in questions.md:
  1. LeadPilot is not a "calendar-powered" lead generation platform. It is an end-to-end AI outbound tool. It has its own booking pages plus a Calendly hook, but it does **not** read Google Calendar (help-center 14). Positioning is built on what it really does (Q-03).
  2. The repo names the founders as Rehan Masood and Ahmad (Masood in `docs/program/STAR_PROMPT.md`). The brief says "Ahmad Shahid", and the site's public founder record is Rehan Masood (Q-02).
  3. As of October 2026 there are no paying customers and no public reviews (SPEC.md). So there are no performance numbers, testimonials or ratings to publish, and none are invented here (Q-06, Q-07).
- A prior founder rule still applies: llms.txt and new public content pages (Part B, items 2.6/2.7) were deferred until a trademark review of the name "LeadPilot" against LeadPilot AB (leadpilot.com). Everything in this folder is therefore a **ready-to-publish draft**, not a live change to the website (Q-04).
- Started 3 background research tracks: competitor facts, AI-search mechanics fact-check, industry statistics + baseline search + Reddit threads.

### 17:45 UTC — 0.2 questions.md, 0.3 entity_card.md — COMPLETE
Canonical sentence taken verbatim from `product-facts.json` (the live site already uses it), so the
new content and the live site say the same thing. Capability statuses copied, never upgraded. Q-01 to Q-08 logged.

### 17:52 UTC — 1.2 query_library.md — COMPLETE
50 queries in 5 categories of 10, each with fit (Strong/Partial/Brand) and its answer page. A "do not chase"
list prevents bad-fit visibility. Gate 1.2: 50/50, realistic first-person and keyword forms, covers
ChatGPT/Claude (long), Perplexity (research), Gemini/Copilot (keyword) patterns. PASSED.

### 17:58 UTC — 2.1 niche_statement.md — COMPLETE
Reasoning: a new product can't win "best lead gen tool"; it can win the constrained query. 5 angles were critiqued.
The brief's "calendar-powered" angle was rejected as false to the product (Q-03). Selected: approve-first, done-for-you
AI outbound for founder-led agencies and B2B service firms. Gate 2.1 PASSED.

### 18:05 UTC — 3.1.A what_is_leadpilot.md, 3.1.B leadpilot_use_cases.md, 3.2 faq_library.md — drafted early (no web dependency)
Checked reply-handling claims against `app/services/reply_classification.py`: corrected "stops for anyone who replies"
to "stops when a person replies; out-of-office only pauses". Gates are run in Phase 3 below.

### 18:15 UTC — 1.1 research returned (3 background tracks)
- Competitors: no vendor page could be opened directly (proxy 403). Prices come from search excerpts of official
  pages and are marked UNVERIFIED (Q-09).
- Baseline web search: LeadPilot by Calendarharvest / calendarharvest.com appeared in **0 of 8** queries. Name
  collisions found with LeadPilot AB, an AWS Marketplace "LeadPilot", LeadPilot AI (Rish AI Labs) and others.
- Fact-check: Reddit "r=0.80" is UNSUPPORTED; "87% Bing" is PARTLY TRUE; GBP is not eligible; llms.txt is unproven;
  `anthropic-ai` is legacy. Recorded in `research/ai_search_mechanics_factcheck.md`.
- Reddit blocked, 0 threads collected, none invented (Q-10).

### 18:20 UTC — 1.1 competitor_analysis.md — COMPLETE. Gate 1.1 PASSED
5 primary + 3 secondary competitors with framing, use cases and "where they're stronger"; 8 listicles; 5 query
checks. AI-app answers themselves could not be captured (Q-12).

### 18:28 UTC — 2.2 comparison_matrix.md — COMPLETE. Gate 2.2 PASSED
Reasoning: an assistant routes a recommendation correctly only if the table says who each tool is *for*.
5 tables + summary; every table has rows the competitor wins; "calendar integration" row filled truthfully.
Competitor cells marked "verify" (Q-09).

### 18:34 UTC — 3.1.C 5 comparison pages — COMPLETE
Apollo, Instantly, Smartlead, Clay, Artisan (+ "vs hiring an SDR" with Bridge Group figures). Each discloses
founder authorship, has "when to choose them" as its own section, pricing with billing basis, a verdict table,
and a pre-publish source checklist.

### 18:38 UTC — 3.3 statistics_and_proof.md — COMPLETE
27 sourced industry statistics (S1–S27), vendor-published ones flagged, plus 6 product specifications. The
LeadPilot results table is all [NEEDS VERIFICATION FROM AHMAD] (Q-06). Unverifiable figures are listed as excluded.

### 18:40 UTC — Phase 3 gates (script)
First run: FAQ 30/30, use cases 10/10, but answers FAQ 10, 13, 15 and what-is FAQ 4, 5 were under 50 words.
Expanded with true facts only (OAuth Gmail, cloud backend, simulated-only LinkedIn, collision list). Re-check in Phase 8.
Gate 3.1: first 200 words of what_is answer directly (canonical sentence is sentence 1). Balance: every
comparison page has "When to choose <competitor>". Gate 3.2: answer-first. Gate 3.3: 27 ≥ 20, all sourced. PASSED.

### 18:45 UTC — 4.1 schema_markup.md — COMPLETE. Gate 4.1 PASSED
6 types. Reuses the live @ids from `frontend/src/lib/seo/structuredData.ts`. All 6 JSON blocks parsed by
`json.loads` (exit 0). Offers gated on checkout (Q-08). The Review template is deliberately invalid (0/0) so it can't be published by accident (Q-07).

### 18:48 UTC — 4.2 crawler_access_strategy.md — COMPLETE. Gate 4.2 PASSED
Live robots.txt already allows all. Proposed an explicit version naming 22 user agents. llms.txt is written
from the facts file, with an honest note that no major provider confirms reading it.

### 18:52 UTC — 4.3 site_architecture.md — COMPLETE. Gate 4.3 PASSED
Found the founder cap (SPEC 2.6: ≤6 new pages). Wave 1 = exactly those 6; the 10 use cases merge into 3 /for/
pages (avoids thin-page spam). All GEO pages at depth ≤2. Q-13 logged; the use-case draft's URLs corrected.

### 19:10 UTC — Phase 5: 5 platform playbooks — COMPLETE. Gate 5 PASSED
Reasoning: each engine surfaces sources differently, so each playbook starts with "The mechanism", taken from the
fact-check, not the brief's premises. ChatGPT/Copilot = OAI-SearchBot + Bing (AI Performance report). Gemini =
Googlebot/Search (GBP not eligible, Q-11). Perplexity = live search + visible citations (reverse-engineer cited URLs).
Claude = Claude-SearchBot/Claude-User; publishing the 30-article help center is the top Claude asset (Q-14).
Emerging = general principles; "Sudo" unidentified (Q-15). Reddit section in perplexity_playbook names 10 subreddits,
post types and cadence.

### 19:25 UTC — Phase 6: authority — COMPLETE. Gate 6 PASSED
- citation_acquisition_plan.md: 50 platforms in 3 priorities, each with a URL and an honest verification marker
  (✔/home/verify), plus exact copy blocks identical to the entity card.
- reddit_strategy.md: disclosure on every mention (FTC 16 CFR 255.5), no sock puppets, and the brief's "question
  posts inviting recommendations" reframed as disclosed founder discussion posts. "I tested 5 tools" posts only with
  real tests. Thread logs left blank because Reddit was unreachable (Q-10). None invented.
- syndication_map.md: each Phase 3 doc mapped to primary/syndicate/repurpose/archive, with canonical handling;
  comparison pages deliberately not syndicated in full (stale-price risk).

### 19:35 UTC — Phase 7: monitoring — COMPLETE
20 prompts (5 types × 4), log + weekly roll-up formats, Monday dates through Jan 2027 then monthly. Baseline:
web-search proxy 0/8 (run); AI-app baseline must be run by the founder by 2026-10-18 (Q-12). Calendar: real-time
triggers, monthly (12 first-Monday dates, script-verified as Mondays), quarterly, annual.

### 19:40 UTC — Phase 8: final verification
**8.1 / 8.2: automated audit** (`tools/geo_audit.py`): 24 required files + 5 comparisons exist;
50 queries; 30 FAQs each 50–150 words; 10 use cases each with an "Unlike…" comparison; ≥20 stats each with its
own source URL; 5 matrix tables; 6 schema types all parsed by `json.loads`; SoftwareApplication has
applicationCategory/operatingSystem/offers; robots allows the 7 named bots and has no Disallow; 50 citation
platforms; 20 test prompts; monthly dates are Mondays; no leftover placeholder markers (TBD / ADD-LATER style); brand spelled "Calendarharvest";
canonical sentence in all 11 core docs; niche statement verbatim in 5 docs; every comparison is disclosed and balanced.
- Run 1: 9 FAIL. 7 stats rows said "same as S1" (a row extracted alone loses its source), so each row now carries
  its full URL. 2 were matcher false-negatives (blockquote/bold markup), fixed in the script.
- Run 2: **284 PASS / 0 FAIL.**
- Manual sweeps: "calendar-powered" appears only where it's explicitly rejected; no gendered pronouns for founders.
- `[FILL IN]` / `[NEEDS VERIFICATION FROM AHMAD]` markers remain **by design** (Principle 7) where only the founders
  have the data: own-use numbers (Q-06), Reddit logs (Q-10), subreddit rules. Each one is tied to a question.

**8.3 AI readability test.** Question: if an assistant scrapes the page to answer "best lead gen tool", does it make
LeadPilot the obvious answer *for its niche*?
- what_is_leadpilot.md: YES for the constrained query. Sentence 1 states category + audience + mechanism, sentence 2
  the niche, sentence 3 the contrast with Apollo/Instantly. For the broad query it correctly doesn't claim #1.
- faq_library.md: YES. Q1–Q4 give an assistant both the recommend case and the do-not-recommend case, which is what
  lets it route confidently.
- leadpilot_vs_apollo.md: YES. "Short answer" + verdict table map each use case to a tool. The honest Apollo wins make
  the LeadPilot rows credible.
PASS. (Limit: no page can make LeadPilot the answer to the unconstrained query without reviews and third-party mentions.
That's the job of the authority plan, measured by the tracker.)

## 8.4 Final summary
- **All phases: COMPLETE. All verification gates: PASSED**, with these caveats carried as questions, not hidden:
  competitor prices are UNVERIFIED search excerpts (Q-09); the AI-app baseline and Reddit research need a human (Q-12, Q-10).
- **Files created: 32** in `docs/program/ai-visibility/geo/`: 31 markdown files (the 29 the brief lists incl. 5 comparison
  pages, plus README.md and research/ai_search_mechanics_factcheck.md) and `tools/geo_audit.py` (re-runnable Phase 8 audit).
  Plus one line in `docs/program/PROGRESS.md`. No application, frontend, test or sealed file was changed.
- **Questions awaiting Ahmad:** [questions.md](questions.md) (Q-01 to Q-15).

### Top 3 things to do first tomorrow
1. **Answer Q-04 (trademark), Q-02 (founder name) and Q-06 (own-use numbers).** The trademark answer gates every new
   public page and listing. Renaming after 50 listings is expensive, and today "LeadPilot" in search means LeadPilot AB.
2. **Get indexed (~1 hour):** run the live crawl checks in `docs/program/ai-visibility/REPORT.md`, then verify Google
   Search Console + Bing Webmaster Tools, submit the sitemap, request indexing, and run the IndexNow script. Measured today,
   calendarharvest.com doesn't appear in search at all. Without indexing, no assistant can cite anything here.
3. **Run the AI-app baseline (~90 min, `monitoring/ai_mention_tracker.md`) and complete the 4 existing profiles** (G2,
   Crunchbase, LinkedIn, YouTube) with the copy blocks in `authority/citation_acquisition_plan.md`.

---

## 2026-10-16 — Publish round (founder answers)

### 10:55 UTC — Answers recorded
All 15 questions answered (verbatim in `docs/program/ai-visibility/NOTES.md`, summary in questions.md). Decisions that
change the plan: publish 12 pages and the help center now (Q-13, Q-14), although the trademark is not reviewed (Q-04:
"Not yet"; rename risk recorded); both founders public (Q-02); competitor prices from independent research (Q-09);
Stripe checkout stays "not live" until the founder confirms a real payment (Q-08).

### 11:00 UTC — Three corrections to yesterday's work, found in NOTES.md
1. Search Console was verified on 2026-10-14 (sitemap submitted, 5 pages indexed) and the site was added to Bing.
   Yesterday's "calendarharvest.com doesn't appear in search at all" came from a web search tool that does not reflect
   Google's index. That was wrong, and the corrected text is now in README, playbooks, tracker and citation plan.
2. The "LeadsPilot" GetApp/Capterra listing is the founders' own (wrong name spelling, wrong $299/month price), not a
   name collision. Corrected in the entity card, competitor analysis and citation plan.
3. A partial AI-app baseline already exists (founder, 2026-10-15). Added to the tracker.

### 11:05–11:40 UTC — Built in `frontend/` (commits accb5aa, lastmod commit after it)
- Founders: Ahmad Shahid added to `product-facts.json` (name + "Founder" only, nothing invented); /about lists both;
  Organization JSON-LD carries both; the Person node emits only the fields the facts file has.
- 12 pages (`src/content/geo/*.ts`, one renderer `src/components/content/ContentPage.tsx`): /what-is-leadpilot/,
  /faq/ (30 Q&A + FAQPage JSON-LD built from the visible answers), /outbound-statistics/, /compare/ hub,
  /compare/leadpilot-vs-{apollo,instantly,smartlead,clay,artisan}/, /for/{agencies,b2b-service-firms,local-businesses}/.
- Competitor prices: only where ≥2 independent sources agreed (Apollo, Instantly, Smartlead). Clay and Artisan link
  their pricing pages instead. No database sizes.
- Statuses, founders, prices, checkout and trial wording are generated from the facts file and plans snapshot. When
  Stripe goes live, flip `stripe_checkout` to "live" and the FAQ trial answer, checkout sentences, help status note
  and llms.txt all change with it.
- /help/ + 30 articles, copied from docs/help-center by `scripts/help/sync_help_center.mjs`, with a drift test. Every
  article carries a status note from the facts file, so articles that describe LinkedIn or the trial never contradict the
  marketing pages.
- /llms.txt (route, generated from facts); robots.txt names 22 crawlers (still allow-all).
- Footer: Who it's for / Compare / Resources columns, so every new page is one click from any public page.

### 11:40 UTC — Verification (commands run from frontend/ with NEXT_PUBLIC_API_URL set, as CI does)
| Command | Result |
|---|---|
| `npx tsc --noEmit -p .` | exit 0 |
| `npm run lint` | exit 0; the 6 pre-existing warnings only (none in new files) |
| `npx vitest run src/tests` | exit 0; 102 files, **1,217 tests** (was 1,169; +48 new in geoPages.test.ts, helpCenterCopy.test.ts) |
| Pre-fix proof | Edited a help copy and inserted "LinkedIn steps are live": helpCenterCopy and geoPages each failed 1 test; restored → 48/48 pass |
| `npm run build` (postbuild check) | exit 0; `check_static_seo: PASS (50 sitemap URLs)` (first build: 86 expected lastmod failures before the lastmod commit) |
| Export scan (all 50 pages) | 0 raw markdown, 0 broken internal links, 0 missing anchors; FAQ JSON-LD 30 questions; Organization founders = both |
| Browser (Chromium, 390 px and 1280 px) | 0 px horizontal overflow on /compare/leadpilot-vs-apollo/, /help/plans-limits-billing/, /about/; tables wrap on mobile |

### Top 3 things to do next (2026-10-16)
1. **Merge and deploy.** Open the PR from `claude/relaxed-lamport-ab7g3j`, then merge with `scripts/gate/safe_merge.sh <PR>` (merge policy B).
   After the Vercel deploy: `cd frontend && node scripts/seo/indexnow_submit.mjs`, resubmit the sitemap in Search Console,
   and request indexing for the 12 GEO pages.
2. **Fix the GetApp/Capterra listing** (name "LeadPilot by Calendarharvest", real prices) and **open
   crunchbase.com/organization/leadpilot once** to confirm it is your page, not LeadPilot AB's.
3. **When Stripe works end to end:** change `stripe_checkout` to "live" in `frontend/src/content/product-facts.json` (the
   site, FAQ, help notes and llms.txt follow); then send the own-use numbers (Q-06) and finish the signed-out AI baseline (Q-12).

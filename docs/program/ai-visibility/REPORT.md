# AI visibility — report (Part A), 2026-10-13

Branch `seo/ai-visibility` from `origin/master` (`deda9e0`). Spec: `SPEC.md`. Working notes: `NOTES.md`. Baseline: `BASELINE.md`.

**Status:** Part A (2.1–2.5, 2.8, 2.9) done and verified. **Part B (2.6, 2.7) not started, by rule:** the trademark answer is "Not reviewed; keep name", so the Part B condition is not met (resume prompt below).

## Founder answers (verbatim, from NOTES.md)

Phase 0 (AskUserQuestion, 2026-10-13):
- Q1 founder location / legal entity: "Astoria NY; no entity yet"
- Q2 prices in page HTML: "Names, features and prices"
- Q3 sending: "Email auto; LinkedIn not live"
- Q4 profiles / sameAs (G2 "LeadsPilot", GetApp "LeadsPilot", LinkedIn leadpilot-app): "None of these"
- Q5 trademark (outcome only): "Not reviewed; keep name"
- Q6a live end to end: "Market research,Contact find + verify,Email writing,Email sending (Gmail)"
- Q6b live end to end: "Reply routing,Meeting booking,WhatsApp" (Stripe checkout not selected → not live)
- Q7 proof: "Own-use numbers"; follow-up (which numbers): "I'll give them (Other)" with no numbers supplied → unanswered.
- Q8 Vercel production branch / PR base: "master / master"
- Work branch: "seo/ai-visibility"

1.4 plan approval: "Approve as written (Recommended)"; LinkedIn status: "Tested only vs simulated".

Phase 3 follow-up (after the independent review):
- Further capabilities live end to end: "Android app + smart send" (not selected: lead scoring + "not now" memory, meeting prep + reminders, agency workspaces).
- Free trial while checkout is not live: "Leave as is; I'll decide".
- LinkedIn page: "https://www.linkedin.com/company/leadpilot-app this is my linkedin" (now in Organization sameAs).
- /about H1, /how-it-works H1, /contact "done-with-you", "runs without you", "No sales team. No SDR handoff.": "Keep all; I confirm them".
- Change homeClaims.test.ts so an ON-flag feature can be listed "unconfirmed": "Yes, change the test".

## What changed (files)

| Path | Purpose |
|---|---|
| `frontend/public/robots.txt` | Sitemap line → `https://www.calendarharvest.com/sitemap.xml` (was apex). |
| `frontend/public/sitemap.xml` (deleted) → `frontend/src/app/sitemap.ts` | Sitemap generated from `src/content/site-pages.json`; 4 `/blog/` URLs with no page in the repo removed. |
| `frontend/src/content/site-pages.json` | The 7 sitemap pages: path, changefreq, priority, lastmod sources. |
| `frontend/src/content/sitemap-lastmod.json` | lastmod per page from git (2.9). |
| `frontend/src/content/product-facts.json` | One source of product facts: brand (defined once), organization, sameAs, founder, description, tagline, fit / not a fit, capability status, channels, limits, compliance features. |
| `frontend/src/content/plan-names.json` | Plan names as in `app/core/billing_catalog.py` (static pricing HTML). |
| `frontend/src/lib/productFacts.ts` | Reads the facts; `PRODUCT_FULL_NAME` = product + " by " + company. |
| `frontend/src/lib/seo/pageMeta.ts` | Canonical + og:url per page. |
| `frontend/src/lib/seo/structuredData.ts`, `frontend/src/components/seo/JsonLd.tsx` | JSON-LD @graph per page. |
| `frontend/src/lib/seo/staticPlans.ts` | Static plan list source (snapshot if committed, else names). |
| `frontend/src/app/pricing/page.tsx`, `PricingClient.tsx` | Pricing split: server page (metadata, JSON-LD, static plans, intro) + the unchanged interactive client. |
| `frontend/src/app/{page,how-it-works,about,contact,privacy,terms}` | Titles, descriptions, canonical, JSON-LD; copy fixes on marketing pages (2.5). |
| `frontend/src/components/home/{content.ts,HomePage.tsx}` | Capability status groups, first mention, facts-driven lists, copy fixes. |
| `frontend/src/tests/planNames.test.ts`, `productFacts.test.ts` (new); `homeClaims.test.ts` (founder-approved change) | Guards. |
| `frontend/scripts/seo/check_static_seo.mjs` (+ `expected_plans.json`) | The static SEO check; npm `postbuild` hook. |
| `frontend/scripts/seo/snapshot_plans.mjs`, `check_plans_snapshot.mjs` | Plans snapshot from the live catalog + founder drift check. |
| `frontend/scripts/seo/indexnow_submit.mjs`, `indexnow.json`, `frontend/public/99b0961bddf18b9b8d31299dc0962e3b.txt` | IndexNow. |
| `frontend/scripts/seo/lastmod.mjs` | lastmod from git. |
| `frontend/package.json` | `"postbuild": "node scripts/seo/check_static_seo.mjs --postbuild"`. |
| `frontend/.gitignore` | `scripts/seo/.indexnow-state.json`. |
| `docs/program/DECISIONS.md` | D1: records the 2026-10-13 LinkedIn answer. |
| `docs/program/ai-visibility/*` | SPEC, state, NOTES, BASELINE, this report, PROMPT_TRACKER. |
| `docs/program/PROGRESS.md` | One line. |

Scripts live in `frontend/scripts/seo/` because the repo does not show whether Vercel's build (Root Directory `frontend`, per `DEPLOY_RENDER_FREE.md`) can read files outside `frontend/`.

## Verification evidence (Phase 3, final run on the final tree)

Frontend checks (from `frontend/`, `NEXT_PUBLIC_API_URL` set as CI sets it), side by side with BASELINE:

| Command | Baseline | Final |
|---|---|---|
| `npm run type-check` | exit 0 | exit 0 |
| `npm run lint` | exit 0, 6 warnings (pre-existing, files not touched) | exit 0, same 6 warnings |
| `npm test` | exit 0, 96 files / 1145 tests | exit 0, 98 files / 1153 tests |
| `npm run build` | exit 0 | exit 0; postbuild `check_static_seo: PASS (7 sitemap URLs)` |

`node scripts/seo/check_static_seo.mjs --report` on the final export → **exit 0**:

```
| Path | Title | Meta description | Canonical | H1 | Words in raw HTML main | JSON-LD types |
|---|---|---|---|---|---|---|
| / | Vectorae by Calendarharvest: from what you sell to meetings on your calendar \| Calendarh | Describe what you sell. Vectorae researches your market, finds and checks business contac | https://www.calendarharvest.com/ | From what you sell to meetings on your calendar. | 1704 | Organization, WebSite, SoftwareApplication, FAQPage |
| /how-it-works/ | How Vectorae by Calendarharvest works \| Calendarharvest | How Vectorae by Calendarharvest researches your market, finds and verifies business conta | https://www.calendarharvest.com/how-it-works/ | Your pipeline. Running without you. | 317 | Organization, WebSite, BreadcrumbList |
| /pricing/ | Vectorae by Calendarharvest pricing \| Calendarharvest | Plans for Vectorae by Calendarharvest: monthly plans (Starter, Growth, Scale, Enterprise) | https://www.calendarharvest.com/pricing/ | Pricing that fits how you sell | 92 | Organization, WebSite, SoftwareApplication, BreadcrumbList |
| /about/ | About Vectorae by Calendarharvest \| Calendarharvest | Vectorae by Calendarharvest was built by a founder who used it to find his own clients. H | https://www.calendarharvest.com/about/ | Built by a founder who used it to find his own clients. | 427 | Organization, WebSite, BreadcrumbList, Person |
| /contact/ | Book a call about Vectorae by Calendarharvest \| Calendarharvest | Talk to Rehan directly about Vectorae by Calendarharvest. If it is a fit, we will tell yo | https://www.calendarharvest.com/contact/ | Talk to Rehan directly. | 383 | Organization, WebSite, FAQPage, BreadcrumbList |
| /privacy/ | Privacy Policy for Vectorae by Calendarharvest \| Calendarharvest | How Vectorae by Calendarharvest collects, uses, and protects your data. | https://www.calendarharvest.com/privacy/ | Privacy Policy | 1611 | Organization, WebSite, BreadcrumbList |
| /terms/ | Terms of Service for Vectorae by Calendarharvest \| Calendarharvest | The terms that govern your use of Vectorae by Calendarharvest. | https://www.calendarharvest.com/terms/ | Terms of Service | 1003 | Organization, WebSite, BreadcrumbList |

check_static_seo: PASS (7 sitemap URLs)
check exit 0
```

On the old export (Phase 1, BASELINE.md §4) the same check exited 1 with 40 failures (findings 1–3 among them).

**Pre-fix / sabotage proof of the checks added after Phase 1** (a copy of the final export, broken on purpose: a title without the product name, a sameAs not in the facts file, a Person value not in the facts file, a price and an aggregateRating in the pricing JSON-LD, a wrong lastmod, a wrong IndexNow key file):

```
check_static_seo: FAIL (7)
  - https://www.calendarharvest.com/pricing/: JSON-LD contains rating/review markup (@graph.aggregateRating)
  - https://www.calendarharvest.com/pricing/: JSON-LD price 149 is not in plans-snapshot.json
  - https://www.calendarharvest.com/about/: title lacks "Vectorae by Calendarharvest"
  - https://www.calendarharvest.com/about/: JSON-LD Person value "Faisalabad, Pakistan" is not a founder fact in product-facts.json
  - https://www.calendarharvest.com/contact/: JSON-LD sameAs https://www.linkedin.com/company/leadpilot is not in product-facts.json same_as
  - https://www.calendarharvest.com/terms/: sitemap <lastmod> 2026-10-13T00:00:00+00:00 is not the git date 2026-10-13T15:10:44+00:00
  - IndexNow: 99b0961bddf18b9b8d31299dc0962e3b.txt does not contain the key
exit 1
```
Also shown failing: a missing `sitemap-lastmod.json` (`sitemap-lastmod.json: missing …` and one "no entry" line per URL); a plan name removed from the visible pricing HTML (`/pricing/: plan name "Enterprise" not in the static HTML`; this sabotage first passed, because the check read `<script>` text, and the check was fixed in `d00e0ce`); and `npm run build` exit 1 with the key file removed (postbuild blocks the build). New vitest guards were shown failing: `planNames.test.ts` on a renamed tier; `homeClaims.test.ts` (changed) on an off-by-default feature marked "unconfirmed".

**IndexNow dry run** (`node scripts/seo/indexnow_submit.mjs --dry-run --sitemap out/sitemap.xml`; no request sent, no state file written):

```
indexnow_submit --dry-run: 7 of 7 URLs changed since the last submission (out/sitemap.xml).
Would POST to https://api.indexnow.org/indexnow:
{
  "host": "www.calendarharvest.com",
  "key": "99b0961bddf18b9b8d31299dc0962e3b",
  "keyLocation": "https://www.calendarharvest.com/99b0961bddf18b9b8d31299dc0962e3b.txt",
  "urlList": [
    "https://www.calendarharvest.com/",
    "https://www.calendarharvest.com/how-it-works/",
    "https://www.calendarharvest.com/pricing/",
    "https://www.calendarharvest.com/about/",
    "https://www.calendarharvest.com/contact/",
    "https://www.calendarharvest.com/privacy/",
    "https://www.calendarharvest.com/terms/"
  ]
}
exit 0
```

**Plans snapshot check: NOT RUN.** The live API (`https://leadpilot-api-ph3t.onrender.com/billing/catalog`) is refused by this sandbox's proxy. No snapshot is committed; the static pricing HTML shows plan **names only**, taken from the repo's code (`app/core/billing_catalog.py`, kept in sync by `planNames.test.ts`), not from a founder answer. Founder command: see TODO(founder) 1.

**Screenshots** (Playwright + Chromium, local export, 1280 px; kept outside the repo). Visual differences vs the 1.1 screenshots: `/` gains a small "VECTORAE BY CALENDARHARVEST" line above the H1, the facts description under "For businesses that sell to other businesses", and two status boxes under "What is in the box today" ("Built and switched on, but not yet confirmed working…", "Built and tested only against simulated services; not live yet"); `/pricing/` gains two short intro lines and a "Plans" card with the plan names (shown until the live catalog loads; in this sandbox the API is unreachable, so "Plans could not be loaded" still shows under it); `/how-it-works/`, `/about/`, `/contact/` show reworded text only (same layout; the third step is now "Replies and meetings"); `/privacy/`, `/terms/` unchanged visually. Same components, colours and styles throughout.

**Postbuild hook — does it block CI and Vercel?**
- CI: yes. `verify-frontend` (`.github/workflows/verify.yml`) runs `npm run build`; npm runs `postbuild`; a failing check fails the job.
- Vercel: yes, **if** the project's Build Command is the default (`npm run build`); `frontend/vercel.json` sets none, so the default applies unless overridden in the dashboard (founder check below). A failed build is not deployed.
- The frontend `Dockerfile` (`npm ci` then `npm run build`) also runs it.
- Mobile builds (`NEXT_PUBLIC_BUILD_TARGET=mobile-*`, e.g. `android-release.yml`) skip it: the Android export renders no marketing markup on `/` by design, and without the skip that workflow would fail (`/: no <h1>`, reproduced locally). `mobile:*` and `test:e2e` call `next build` directly and never run it.

**Independent review** (fresh-context subagent over the full diff vs SPEC.md). Fixed: /about first mention; brand constant in body text, descriptions, breadcrumb; lastmod sources missing shared files that render page text; IndexNow usage message; "LinkedIn needs its own approval"; capabilities shown as working without a founder answer (asked; now "unconfirmed"); /contact LinkedIn link (founder confirmed; now sameAs). Remaining findings, not fixed:
1. Free-trial / "cancelled online" wording while Stripe checkout is not live (home hero note is pinned by `homeClaims.test.ts`; /contact FAQ): founder kept it ("Leave as is; I'll decide"). Founder/legal question below.
2. "Loading plans…" still appears in the static pricing HTML next to the static plan list: 2.2 says to leave the browser-loaded display as it is.
3. Titles are literal strings per page (approved in 1.4 because `websiteClaims.test.ts` reads them from source); a rename needs those lines edited too, and `check_static_seo.mjs` fails every title that lacks the new name.
4. The facts description is a literal sentence starting with the full product name; `productFacts.test.ts` fails if it no longer starts with `PRODUCT_FULL_NAME`.

## Gate (CLAUDE.md)

`scripts/gate/install_hooks.sh` run once. `scripts/gate/quick_gate.sh`: without `NEXT_PUBLIC_API_URL` the frontend step fails inside `next lint` (the config guard, same as BASELINE.md §1); with `NEXT_PUBLIC_API_URL=https://api.example.invalid` (CI's value): **exit 0**: secrets, syntax, migrations (single head `0089_voice_twin`), registry, tests (30 files: 1306 passed), frontend (type-check, lint, test) all PASS. Stamp run on the final commit: see the PR.

Offline eval gate (CLAUDE.md commands, CPython 3.13.16, after `pip install -r requirements.txt fakeredis pyyaml pytest pytest-asyncio pytest-mock` exit 0), run on this branch at `ee320e0` (later commits change only frontend files, docs and a frontend test, none of which the Python suite reads):

```
python3 evals/tools/registry_lint.py evals/registry.yaml   -> exit 0  (IE-06 registry lint: OK)
python3 evals/run_evals.py                                  -> exit 0
  compliance_suite_pass_rate 1.000000 | full_suite_pass_rate 1.000000 | offline_test_count 5797 | suite_runtime_s 1394.2
python3 evals/tools/promote.py                              -> exit 0
  compliance_suite_pass_rate  hard  PASS | full_suite_pass_rate hard PASS | offline_test_count hard PASS (5797 = baseline)
  suite_runtime_s             soft  WARN  1394.2 vs 900.0 (this sandbox ran two frontend builds and a review build at the same time)
  DECISION: PROMOTE  (1 soft warning -> human review)
python3 evals/fixtures/verify_block_fixtures.py             -> exit 0  (all 3 hard gates proven to fire; healthy run promotes)
```

## Checks added to check_static_seo.mjs after Phase 1 (none removed or weakened)

| Commit | Check | Why |
|---|---|---|
| 2.2 `690d676` | Once `plans-snapshot.json` exists: every expected plan name must be in it (unless in `removed_by_founders`), and every snapshot plan name must be in the pricing HTML | The snapshot becomes the plan source (spec 1.2 / 2.2). |
| 2.3 `2f6262a` | Every title contains "Vectorae by Calendarharvest", built from the brand constants | Tells it apart from LeadPilot AB; catches a rename that misses a literal title. |
| 2.3 `2f6262a` | JSON-LD sameAs / Person values must be in product-facts.json; JSON-LD prices must be in the plans snapshot | Markup must not say more than the confirmed facts (spec 2.3). |
| 2.8 `1c94a6d` | IndexNow key file in the export with the key as content | Spec 2.8. |
| 2.9 `e0bec41` | Every sitemap URL has a `sitemap-lastmod.json` entry, and its `<lastmod>` equals it | Spec 2.9; dates come from git, never the build. |
| `d00e0ce` | Plan names must be in the **visible** pricing HTML (not only in `<script>` data) | A sabotage run showed the check could pass on the inline Next.js data. |
| `ee320e0` | `--postbuild`: skipped only for mobile builds | The Android export has no marketing page; run directly, the check always runs. |

## Open TODO(founder) items

1. **Plans snapshot** (`frontend/src/lib/seo/staticPlans.ts`): from `frontend/`, run `node scripts/seo/snapshot_plans.mjs && node scripts/seo/lastmod.mjs`, commit both JSON files on a branch (so features and taglines render statically), and later `node scripts/seo/check_plans_snapshot.mjs` to confirm it still matches the live catalog.
2. **Prices while Stripe checkout is not live** (`staticPlans.ts`): decide whether showing prices before online payment works implies an offer buyers can purchase; when checkout is live, set `checkout_live: true` in `frontend/scripts/seo/expected_plans.json` (the check then requires the approved prices in the HTML) and decide on JSON-LD offers.
3. **Own-use numbers** (Q7): none supplied, so no number is published. Give the number, its date and its source to add one.
4. **Legal entity / legalName**: "no entity yet", so no `legalName` in the markup.
5. **Trademark review** (Q5): "Not reviewed". Part B waits for it.

## Founder / legal questions

- **Free trial and "cancelled online"** while Stripe checkout is not live: the home hero note ("Monthly plans start with a free trial.", pinned by `homeClaims.test.ts`), the home pricing teaser ("…free trial and can be cancelled online"), /contact FAQ ("monthly plans with a free trial"). In code the trial is part of a Stripe subscription. Kept by founder decision.
- **Prices shown in the browser** (unchanged live-loaded display) while checkout is not live: does that imply a purchasable offer?
- **/terms** (body not edited; spec 2.5): describes "a done-with-you outbound pipeline system" that "manage[s] LinkedIn direct message and email sequences on your behalf … sent automatically … through the LinkedIn and email accounts you connect" and says "LinkedIn is the primary outreach channel, you must maintain an active LinkedIn profile". LinkedIn steps are not live; email is the default channel. Governing law England and Wales, arbitration in London, while there is no legal entity and the founder is in Astoria, New York.
- **/privacy** (body not edited): "Vectorae Enterprise is operated by Calendarharvest" with no registered entity, postal address or data-controller details; lists Unipile "LinkedIn sending and receiving" as a processor although LinkedIn is not live; mentions engaging "us to run outreach on your behalf".
- **Operator identity**: neither page names a legal entity, a postal address or a data controller; the only contact is an email address.
- **LinkedIn automation**: LinkedIn steps are not live today. If they go live with automatic sending, LinkedIn's User Agreement restricts automation; the site must never call it compliant.
- **Compliance-status claims**: none found on the marketing pages ("CAN-SPAM/GDPR compliant" or similar). The home trust item "GDPR deletion and export" names a feature (erase a prospect, export, delete an account), not a legal status; /terms names CAN-SPAM, GDPR, UK GDPR and CASL only as the customer's responsibility.

## Removals and rewordings (2.5 and review fixes)

- Home: "LinkedIn and WhatsApp steps … available" → WhatsApp steps available (from Starter); LinkedIn steps and Stripe checkout under "Built and tested only against simulated services; not live yet".
- Home: lead scoring, "not now" memory, meeting prep (brief, reminders, AI summary) and agency workspaces moved from "What is in the box today" to "Built and switched on, but not yet confirmed working end to end in production"; their mentions in the stage text removed ("each lead is scored for fit", "A 'not now' becomes a dated return visit", "prep brief … reminders … AI summary").
- Home: "Email, LinkedIn and WhatsApp replies" → "Email and WhatsApp replies"; LinkedIn-post personalisation stated as depending on the LinkedIn connection, not live; "LinkedIn needs its own approval" → "LinkedIn steps, once live, need their own approval"; FAQ "What has not been verified yet?" (Apollo, Hunter, Gmail, WhatsApp, Calendly, Stripe) → "What is not live yet?" from product-facts.json.
- /how-it-works: "72-step research pipeline" → 72 or 144 steps per strategy; LinkedIn sending → not live; "prospects … scored for fit" removed; "A four-step conversation sequence: observe, reflect the pain, introduce your offer, earn the call" removed (no code source); "Learning" step (ICP refined, compounds, Revenue & ROI dashboard) → "Replies and meetings"; "Your only job is to show up … You handle the calls we book" → "What you still do", matching the home page.
- /about: Faisalabad, Pakistan → Astoria, New York; removed "has published more than 18 public repositories on GitHub", "today it is the system that finds Vectorae's own clients", "He uses it himself, every day, to find Vectorae's own clients"; audience list (boutique agencies with 3–30 staff in seven countries, coaches, early SaaS founders, fractional consultants who "resell or white-label") → the home page's three groups; "Learning" → "Replies and meetings"; LinkedIn → not live.
- /contact: first "for you" bullet → the three groups from product-facts.json; "You are based outside our approved geographies" → the Terms of Service country list, quoted; plus the home not-a-fit list; LinkedIn FAQ → included in plans, not live.
- /pricing: intro shows the facts description and what is not live; meta description makes no trial claim.
- /privacy, /terms: title, meta description, canonical, og:url and JSON-LD only.
- No blog posts exist in the repo, so there were no competitor claims to check or remove.

## Founder steps this unlocks

1. **Merge** with `scripts/gate/safe_merge.sh <PR>` once checks are green (MERGE-B).
2. **After any page change**, run the lastmod command (`cd frontend && node scripts/seo/lastmod.mjs`) and commit its JSON on the same branch before merge; **after the deploy**, run the IndexNow command: `cd frontend && node scripts/seo/indexnow_submit.mjs` (first run submits all 7 URLs; add `--dry-run` to preview).
3. **Vercel**: confirm Settings → Build and Deployment → Build Command is the default `npm run build` (so postbuild runs). Confirm the production branch is `master`.
4. **Apex → www redirect**: the live check was NOT RUN, so it is unknown whether `calendarharvest.com` redirects. In Vercel → Domains, set `calendarharvest.com` to redirect permanently (308, Vercel's default, or 301) to `www.calendarharvest.com` if it does not already.
5. **Vercel bot protection / firewall**: confirm Bot Protection, Attack Challenge Mode or custom rules do not challenge Googlebot, Bingbot, OAI-SearchBot, Claude-SearchBot, Claude-User, PerplexityBot or Meta-WebIndexer. User-Agent tests (below) cannot test rules keyed on crawler IP ranges.
6. **Google Search Console**: add the `www.calendarharvest.com` property (or a domain property), submit `https://www.calendarharvest.com/sitemap.xml`, request indexing of `/`, `/pricing/`, `/about/`. The SoftwareApplication item may show as "not eligible" for the Software App rich result, because that result needs a rating or review. That is expected; never add ratings to fix it (there are no reviews).
7. **Google generative AI setting**: confirm no `nosnippet` / `max-snippet` restriction and that `Google-Extended` is not blocked (robots.txt allows all), so AI Overviews / AI Mode and Gemini grounding can use the site.
8. **Bing Webmaster Tools**: add the site (import from Search Console works), submit the sitemap; IndexNow submissions appear there.
9. **Crawler hits**: Vercel Web Analytics runs in the browser and does not count crawlers. Use Vercel's request logs / Observability (or a Log Drain) to filter by the user agents above, and confirm which Vercel feature and plan tier record requests to static files, and its price, before relying on it. Also watch referrals from `chatgpt.com`, `perplexity.ai` and `claude.ai` in analytics.
10. **Monthly**: fill in `PROMPT_TRACKER.md`.

## Live checks to run (NOT RUN here: the sandbox proxy refuses calendarharvest.com)

The User-Agent strings below could not be fetched from the vendors' bot pages in this session (only Anthropic's page was reachable, and it names the tokens, not full strings). **Check each against the vendor's page before relying on the result**: Google (developers.google.com/search/docs/crawling-indexing/google-common-crawlers), Bing (bing.com/webmasters/help/which-crawlers-does-bing-use-8c184ec0), OpenAI (platform.openai.com/docs/bots), Anthropic (support.claude.com article 8896518), Perplexity (docs.perplexity.ai/guides/bots), Meta (developers.facebook.com/docs/sharing/webmasters/web-crawlers). A 403 or challenge for a spoofed Googlebot or Bingbot is "inconclusive (possible impersonation protection)", not "blocked".

```bash
for host in https://www.calendarharvest.com https://calendarharvest.com; do
  for p in / /how-it-works/ /pricing/ /about/ /contact/ /privacy/ /terms/ /robots.txt /sitemap.xml /99b0961bddf18b9b8d31299dc0962e3b.txt; do
    printf '%s%s  ' "$host" "$p"; curl -s -o /dev/null -L -w '%{http_code} redirects=%{num_redirects} final=%{url_effective}\n' "$host$p"
  done
done

# raw HTML (no JavaScript): canonical, title, H1, plan names, JSON-LD present?
for p in / /pricing/ /about/; do
  curl -s "https://www.calendarharvest.com$p" | grep -o '<link rel="canonical"[^>]*>\|<title>[^<]*</title>\|<h1[^>]*>[^<]*\|application/ld+json\|Starter\|Pay per meeting' | sort -u
done

# per-crawler User-Agent (verify strings against the vendor pages first)
UAS=(
 "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
 "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)"
 "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)"
 "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-SearchBot/1.0; +Claude-SearchBot@anthropic.com)"
 "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-User/1.0; +Claude-User@anthropic.com)"
 "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)"
 "meta-webindexer/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/web-crawlers)"
)
for ua in "${UAS[@]}"; do for p in / /pricing/ /about/; do
  printf '%-40.40s %-12s ' "$ua" "$p"; curl -s -A "$ua" -o /tmp/ch.html -w '%{http_code} ' "https://www.calendarharvest.com$p"; grep -c 'application/ld+json' /tmp/ch.html
done; done
```

## Part B status and resume prompt

Not done in this session: the Phase 0 trademark answer is "Not reviewed; keep name", and the spec allows Part B only after "reviewed, keep the name" or a counsel-cleared rename merged into the brand constant. Ready-to-paste prompt for the next session:

> Continue the Vectorae AI-visibility work, Part B. 1) Read `docs/program/ai-visibility/SPEC.md`, `state.json` and `NOTES.md`. 2) Create branch `seo/ai-visibility-part-b` from `master` only after the Part A pull request (`seo/ai-visibility`) is merged; if it is not merged, stop and ask. 3) Skip Phases 0–1 except one AskUserQuestion call that confirms the trademark outcome (question 5) and asks whether any answer to questions 1, 2, 6 or 7 has changed. 4) Append the answers to `NOTES.md`; apply any changed answer to `frontend/src/content/product-facts.json` first. Continue only if the trademark answer is "reviewed, keep the name" or a counsel-cleared rename is already merged into the brand constant (`brand` in product-facts.json); otherwise stop. 5) Start at 2.6, following SPEC.md (comparison pages for Apollo, Instantly, Smartlead from competitor pages fetched as raw HTML in that session; up to three use-case pages; then 2.7 llms.txt from product-facts.json), rerun `node scripts/seo/lastmod.mjs` after each page commit and commit its JSON separately, and run all of Phase 3 again including the independent review before Phase 4.

## Out-of-scope discoveries (reported, not fixed)

- The 4 `/blog/…` URLs in the old sitemap (added in `1c2a82b`) never had pages in this repo; if the live site serves them, it serves them from somewhere else. Removed from the sitemap only.
- `/status/` is a public page but is not in the sitemap (left as is).
- `next lint` (and the quick gate's frontend step) fails without `NEXT_PUBLIC_API_URL` because `next.config.js` throws; CI sets a placeholder. Local runs need it set.
- The live-loaded pricing feature bullets (`frontend/src/lib/pricing.ts` `channelList`) list "LinkedIn" for Growth and up without a status; shared with the logged-in app, so not changed (the pricing intro now says LinkedIn steps are not live).
- `privacy`/`terms` body text (see founder/legal questions).

## Limitations

- Live site, per-crawler, apex/www redirect and plans-snapshot checks: NOT RUN (proxy). Founder commands above.
- User-Agent strings not verified against vendor pages in this session.
- Screenshots were taken with the API unreachable, so the logged-in/live-catalog state of /pricing was not seen.

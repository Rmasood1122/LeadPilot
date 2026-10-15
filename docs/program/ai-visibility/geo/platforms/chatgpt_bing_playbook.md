# ChatGPT + Microsoft Copilot (Bing) playbook

## The mechanism (what actually decides whether LeadPilot is named)
- LeadPilot's site went live around September 2026, after current models' training cut-offs. **ChatGPT can
  only name it through live search.** That runs on OpenAI's own crawler, **OAI-SearchBot**, plus
  user-triggered fetches by **ChatGPT-User**, together with third-party search data.
- A Seer Interactive study (Feb 2025, ~500 SearchGPT citations) found 87% of cited URLs also appeared in
  **Bing's** top results for the same query. That's a correlation from a small, older study, not a rule
  (`research/ai_search_mechanics_factcheck.md` #1). Practical reading: **if Bing can't find and rank the
  page, ChatGPT probably won't cite it.**
- **Microsoft Copilot grounds its answers in Bing.** Bing Webmaster Tools' **AI Performance** report
  (public preview since 2026-02-10) shows how often your pages are cited in Copilot and Bing AI
  summaries, and for which grounding queries. It's the only first-party AI citation report available today.
- ChatGPT's "best X for Y" answers lean on listicles and comparison pages (SPEC finding 4). A page that
  names the constraint ("…for a 10-person agency with no sales team") is what gets pulled.

## Step-by-step (in order; owner and time in brackets)

### A. Get indexed in Bing (week 1) [founder, 45 min]
1. Go to https://www.bing.com/webmasters and sign in. Choose **Import from Google Search Console** (fastest:
   it carries over verified sites and sitemaps), or add `https://www.calendarharvest.com/` and verify with
   the XML file or a DNS CNAME record.
2. **Sitemaps** → submit `https://www.calendarharvest.com/sitemap.xml`.
3. **URL Inspection** → inspect `/`, `/how-it-works/`, `/pricing/`. Each must be "Indexed". If "Discovered
   but not crawled", use **Request indexing**.
4. **IndexNow** is already wired. After each deploy, run `node frontend/scripts/seo/indexnow_submit.mjs`
   (it submits changed sitemap URLs; the key file is in `frontend/public/`). Confirm in **IndexNow → Insights**.
5. **AI Performance** report: note the baseline (expected: 0 citations) in `monitoring/ai_mention_tracker.md`.
6. **Site Scan** (Bing's SEO audit): run once; fix any errors on marketing pages.

### B. Check that OpenAI can reach the site (week 1) [founder, 15 min]
1. `robots.txt` allows everything, including OAI-SearchBot (`technical/crawler_access_strategy.md`).
2. Run the live checks in `docs/program/ai-visibility/REPORT.md` with the OAI-SearchBot user agent. Each page
   must return 200 with its text in the raw HTML (static export already does this).
3. If you use Vercel or Cloudflare bot protection, add an allow rule for OAI-SearchBot, ChatGPT-User and Bingbot.

### C. The top 10 Bing factors that drive ChatGPT/Copilot citations (and what to do for each)
| # | Factor (from Bing Webmaster Guidelines themes) | LeadPilot action |
|---|---|---|
| 1 | Crawlable, indexable HTML with the content in the page | Done (static export); keep `check_static_seo.mjs` in the build |
| 2 | Freshness and fast discovery | IndexNow on every deploy; git-based `lastmod` (done) |
| 3 | Exact, descriptive `<title>` and H1 matching the query | Comparison titles: "LeadPilot vs Apollo: which fits a small agency? \| Calendarharvest" |
| 4 | Clear answer near the top | Every draft opens with a "Short answer" paragraph |
| 5 | Relevance to the query's constraint | /for/ pages name the buyer, size and pain in the H1 and first 100 words |
| 6 | Structured data that matches visible content | Organization, SoftwareApplication, FAQPage already live; add HowTo/Breadcrumb |
| 7 | Authority from other sites linking and mentioning | `authority/citation_acquisition_plan.md` (G2, Crunchbase, Product Hunt, AlternativeTo, SaaSHub …) |
| 8 | Social signals (Bing has said it considers them, unlike Google) | LinkedIn company page posts linking to new pages; founder posts with disclosure |
| 9 | Page speed and mobile | Static pages; keep video lazy-loaded on Home |
| 10 | No spam (doorways, keyword stuffing, fake reviews) | Wave-based publishing; no review markup until real reviews; GEO paper: keyword stuffing −10% |

### D. Content formatting Bing and ChatGPT reward
- An H1 phrased as the question; a 40–80 word direct answer in the first paragraph.
- Markdown-style tables with a header row (comparison, pricing). These are extracted cleanly.
- Numbered steps for process questions ("How does LeadPilot work").
- Statistics with a linked source, and quotations from named people (the GEO paper's top methods).
- A visible "Last checked" date on comparison and pricing content.
- One entity name throughout: "LeadPilot by Calendarharvest" on first mention.

### E. Bing Places for Business — **do not create** (questions.md Q-11)
Bing Places is for businesses with a physical location customers visit. Calendarharvest is online-only.
Creating a listing would need an address customers visit, which would be false. Use the Organization
schema and the LinkedIn company page for entity data instead.

### F. Bing-specific authority (differs from Google)
- Bing weights social and directory signals more visibly than Google does. Priority: LinkedIn company page
  (complete, weekly posts), Crunchbase, G2, Product Hunt.
- Exact-match anchor text from relevant sites carries more weight in Bing. When a directory allows a link
  title, use "LeadPilot by Calendarharvest", not "click here".
- Microsoft properties: a complete **LinkedIn** company page is the one Microsoft-owned surface that matters.

### G. Target queries where LeadPilot must reach Bing's top 10
Pick constrained queries a new site can realistically rank for. (IDs refer to `research/query_library.md`.)
1. "AI outbound tool for small marketing agency" (B1)
2. "Apollo alternative for small agencies" (C3)
3. "Instantly alternative that writes the emails" (C4)
4. "Smartlead alternative for agency founder" (C5)
5. "pay per booked meeting lead generation software" (B5) — current results are services, not software, so there's a gap
6. "outbound tool where I approve emails before sending" (B7)
7. "outbound sales tool for commercial cleaning company" (D3)
8. "AI outreach for HVAC commercial clients" (D4)
9. "LeadPilot vs Apollo" (C1)
10. "LeadPilot by Calendarharvest" (brand). Must be #1; today it returns nothing (baseline 2026-10-15).

Check weekly in Bing (signed out, US region) and log the result in `monitoring/ai_mention_tracker.md`.

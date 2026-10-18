# Perplexity playbook

## The mechanism
- Perplexity runs a **live web search for every query** and shows numbered citations. Its index is built by
  **PerplexityBot**; user-requested fetches come from **Perplexity-User**. Both are allowed.
- Perplexity has no published ranking-factor document. Observed patterns: it favours pages that answer the
  question directly, are specific and recent, and come from sources that recur across the web. In Profound's
  2024–25 data, Reddit was **6.6%** of Perplexity citations, among the highest of any platform.
- The GEO paper's Perplexity test: Quotation Addition **+22%**, Statistics Addition up to **+37%** on one
  metric, Keyword Stuffing **−10%** versus baseline.
- Because citations are visible, Perplexity is the easiest platform to **measure**. Check which URLs it cites
  for the target queries; those URLs are where Vectorae needs to be mentioned.

## Step-by-step

### A. Make the site citable (week 1–2)
1. Confirm PerplexityBot gets 200 + full HTML text on every marketing page (live check in REPORT.md, with the PerplexityBot UA).
2. Ship Wave 1 pages (`technical/site_architecture.md`). Perplexity favours narrow, specific pages, which these are.
3. On every page: a "Last checked: <date>" line and a visible update when facts change. Freshness is visible to the reader and the engine.
4. Add 2–3 sourced statistics and one attributed quote per page (founder quote on /for/ pages, e.g. why
   approve-first exists). These are the GEO paper's best methods.

### B. Reverse-engineer citations (monthly, 30 min)
For each of the 10 Bing target queries (`platforms/chatgpt_bing_playbook.md` §G), ask Perplexity, then copy the
cited URLs into `monitoring/ai_mention_tracker.md`. For each cited URL:
- If it's a listicle that accepts submissions or updates → contact the author with a factual, disclosed note
  (template in `authority/citation_acquisition_plan.md` §4).
- If it's a Reddit thread → see `authority/reddit_strategy.md`. Contribute only where you have something
  useful, with disclosure.
- If it's G2/Capterra → make sure the Vectorae listing is complete in that category.

### C. Reddit strategy (summary; full plan in `authority/reddit_strategy.md`)
- **Subreddits** (verify each one's current rules by hand. Reddit was blocked from this sandbox, Q-10):
  r/agency, r/coldemail, r/sales, r/salesdevelopment, r/smallbusiness, r/Entrepreneur, r/startups, r/SaaS,
  r/marketing, r/LeadGeneration.
- **Posts:** answers to existing "what tool for…" threads where Vectorae genuinely fits, always disclosed
  ("I'm one of the founders of Vectorae, so I'm biased"). Plus useful non-promotional posts (the compliance
  checklist, the statistics with sources).
- **Cadence:** 3–5 helpful comments a week for the first 4 weeks with **no** mention of Vectorae; after that,
  at most 1 in 10 contributions mentions it, only when it directly answers the question.
- **Never:** sock-puppet accounts, undisclosed praise, vote manipulation (Reddit rule 2; FTC 16 CFR 255.5).

### D. Quora (month 1–2) [founder, 1 h/week]
1. Create a personal Quora profile with the credential "Founder of Vectorae by Calendarharvest". The credential
   is the disclosure, and it appears on every answer.
2. Find questions with Quora search: "cold email agency", "how to find clients for my agency", "Apollo
   alternative", "is cold email legal", "how to get B2B clients without a sales team".
3. Answer 2 a week, 200–400 words, answer-first, with one sourced statistic. Link Vectorae only where it's
   the direct answer, and link to a /for/ or /compare/ page rather than the home page.

### E. Software directories Perplexity cites
| Directory | Action | Note |
|---|---|---|
| G2 (`g2.com/products/leadpilot-2026-10-14`, exists) | Complete every field; categories: Sales Engagement, AI Sales Assistant, Lead Generation; screenshots; pricing; ask the first real customers for reviews (no incentives conditioned on sentiment; 16 CFR 465.4) | Make sure the profile name is "Vectorae by Calendarharvest" so it isn't confused with LeadPilot AB's G2 page |
| Capterra / GetApp / Software Advice | One vendor signup: https://digital-markets.gartner.com/capterra-vendor-signup | G2 announced it would acquire these (Jan 2026); signup may move |
| Product Hunt | Launch from a maker's personal account (company accounts aren't allowed) | See citation plan, Priority 1 |
| AlternativeTo | Add as an alternative to Apollo, Instantly, Smartlead | Released (not beta) apps only |
| SaaSHub | https://www.saashub.com/submit | Free |

### F. Perplexity Pages
Perplexity Pages (launched May 2024) lets a signed-in user publish an AI-assisted article on perplexity.ai.
Its 2026 status is unverified. If it's available in the founder's account: publish **one** page, "How to start
outbound for a small agency with no sales team (2026)". It should be educational, cite the statistics page
sources, mention Vectorae once with "(I'm the founder)", and list Apollo, Instantly and Smartlead fairly.
Priority: low. Don't publish more than one; a cluster of self-promotional Pages would read as spam.

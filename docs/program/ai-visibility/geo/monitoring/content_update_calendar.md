# Content update calendar

AI systems and search engines both favour content that's accurate today. Every page in this system has a
"last checked" date. These are the dates to re-check them. Owner is the founder unless noted; times are estimates.

## Standing rule: real-time updates (within 48 hours of the trigger)
| Trigger | Update | Then |
|---|---|---|
| A capability changes status in `product-facts.json` (e.g., LinkedIn steps go live, Stripe checkout goes live) | Facts file first → home "what is not live" (automatic) → entity card §6 → FAQ #7, #18, #26, #28 → every comparison table → llms.txt → schema (`offers` once checkout is live) | Re-run `check_static_seo.mjs`; IndexNow; note in tracker |
| A price changes in `billing_catalog.py` | `plans-snapshot.json` + static pricing (existing scripts) → comparison pricing tables → FAQ #25–27 → statistics P4/P5 | Same |
| Founder supplies own-use numbers (Q-06) | statistics §8, use case "Results", what-is "proof" paragraph, E-E-A-T "Experience" | Same |
| First real customer review | G2 → consider Review schema (`schema_markup.md` §5 conditions) | — |
| A competitor changes pricing or launches a major feature (seen in the monthly check) | That comparison page + matrix row + "last checked" date | — |
| Trademark outcome (Q-04) | If rename: brand constant + every listing (`citation_acquisition_plan.md`) before anything else | — |

## Monthly (first Monday; ~2 hours)
Dates: **2026-11-02, 2026-12-07, 2027-01-04, 2027-02-01, 2027-03-01, 2027-04-05, 2027-05-03, 2027-06-07, 2027-07-05, 2027-08-02, 2027-09-06, 2027-10-04**
1. Run the AI mention tracker (monthly from month 4; weekly before that).
2. Re-check competitor pricing pages for Apollo, Instantly, Smartlead (Clay, Artisan once Wave 2 is live). Update tables and "last checked".
3. Re-check statistics sources: if a new edition is published (Gartner, Salesforce State of Sales, Hunter
   State of Cold Email, Bridge Group), replace the figure and date.
4. Bing AI Performance + GSC: list the top grounding queries; if one has no matching page section, add a FAQ entry.
5. Add 1 new FAQ entry from real prospect questions (contact form, sales calls) if one is recurring.

## Quarterly (~1 day)
Dates: **2027-01-11, 2027-04-12, 2027-07-12, 2027-10-11**
1. **New competitor analysis:** repeat `research/competitor_analysis.md` §4 (listicles + search checks). Add or
   drop a comparison if a new tool appears in ≥3 of the lists.
2. **New use cases:** if real customers appear in a segment not covered, add a section to the matching /for/
   page (not a new thin page).
3. **Query library refresh:** add queries seen in GSC/Bing grounding queries; retire ones with no impressions.
4. **Citation plan review:** move Priority 2/3 items up as conditions are met (e.g., TrustRadius at 100 customers).
5. **Reddit/Quora review:** what got cited; what got removed.

## Annual (~2–3 days)
Date: **2027-10-11** (one year after this system was created), then each October.
1. Full content audit: every page re-verified against the code, facts file and help center. Remove anything no longer true.
2. Re-run the AI-search mechanics fact-check (crawler tokens, Google guidance, llms.txt status).
3. Re-evaluate the niche statement against a year of tracker data and real customers.
4. Statistics page: rebuild with the year's editions; update the H1 year.
5. Decide which Wave-3 pages (if any) are justified by real demand.

## Specific one-off dates
| Date | Item |
|---|---|
| 2026-10-18 | AI-app baseline (tracker) |
| 2026-10-20 (target) | Trademark answer (Q-04); go/no-go for Wave 1 |
| Wave 1 day + 0 | IndexNow, GSC/Bing requests, archive.org saves |
| Wave 1 + 28 days | Indexing check; Wave 2 decision (Q-13) |
| 2027-01-04 | First quarterly review data point (12 weekly tracker runs) |

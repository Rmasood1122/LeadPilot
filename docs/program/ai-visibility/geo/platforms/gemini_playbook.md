# Google Gemini + AI Overviews / AI Mode playbook

## The mechanism
- **AI Overviews and AI Mode are part of Google Search.** Eligibility = the page is indexed by **Googlebot**
  and eligible to show a snippet. Google: "There are no additional requirements to appear in AI Overviews or
  AI Mode, nor other special optimizations necessary", and "no special schema.org structured data that you
  need to add" (developers.google.com/search/docs/appearance/ai-features, excerpt).
- **Gemini Apps** ground answers in Google Search. Grounding use is controlled by the **Google-Extended**
  token, which doesn't affect Search ranking. It's allowed (robots.txt is allow-all).
- Google's AI optimization guide (May 2026) says optimizing for generative AI features "is still SEO", and
  that Google Search ignores llms.txt and similar AI files.
- Entity understanding (Knowledge Graph) comes from consistent facts across the site and trusted third-party
  profiles, linked through `sameAs`.

## Step-by-step

### A. Google Search Console [done 2026-10-14; after each deploy: steps 2–3]
**Correction 2026-10-16:** the domain property was verified and the sitemap submitted on 2026-10-14, and /, /how-it-works/, /pricing/, /about/ and /contact/ are indexed (NOTES.md). The web search tool used for this plan's baseline does not reflect Google's index.
1. https://search.google.com/search-console → **Add property** → Domain property `calendarharvest.com`
   (DNS TXT record at the registrar). It covers www and apex.
2. **Sitemaps** → submit `https://www.calendarharvest.com/sitemap.xml`.
3. **URL Inspection** on /, /how-it-works/, /pricing/, /about/ → **Request indexing**. Check that "User-declared
   canonical" = "Google-selected canonical" = the www URL.
4. **Performance** → note the baseline impressions for the brand query "LeadPilot Calendarharvest"
   (expected: 0) in the tracker.
5. **Enhancements / Rich results**: run https://search.google.com/test/rich-results on / and /pricing/.
   Organization, SoftwareApplication and FAQPage should be detected with no errors.

### B. Google Business Profile — **not eligible, do not create** (Q-11)
Google's rules: a business "must make in-person contact with customers during its stated hours", and
online-only businesses are ineligible (support.google.com/business/answer/13763036, excerpt). Creating one
with a fake address risks suspension and is the kind of inauthentic signal Google penalizes. The entity work
in C does the job GBP would have done.

### C. Knowledge Panel acquisition (months 1–6)
A Knowledge Panel is granted by Google; it can't be requested for a new entity. Make the entity
unambiguous:
1. **Consistent facts everywhere:** name "LeadPilot by Calendarharvest", URL, founder, one-sentence
   description (entity card §2). The same text on the LinkedIn company page, Crunchbase, G2, Product Hunt, YouTube.
2. **`sameAs` in Organization schema** (live): LinkedIn, G2, Crunchbase, YouTube. Add Product Hunt and
   others as they're created. Only profiles you control and that are complete.
3. **About page as the entity home:** founder, location (Astoria, NY), what the company makes, contact.
   Already live, so keep it current.
4. **Wikidata:** only once independent, serious references exist (press, a G2 page with reviews, a
   third-party article). Wikidata's notability policy deletes self-sourced company items. Earliest realistic
   date: after the first independent coverage. Don't create a Wikipedia article (conflict of interest, and it
   would be deleted for lack of notability).
5. **Disambiguation:** the "not affiliated with LeadPilot AB" line on About and FAQ helps Google keep the two
   entities apart.
6. Once a panel appears: **claim it** via "Claim this knowledge panel" while signed in to Search Console.

### D. Google-specific schema priorities
In order of value: Organization (with `sameAs`, `logo`, `founder`) → SoftwareApplication (live) → FAQPage on
pages that visibly show the FAQ → BreadcrumbList (live) → Product/Offer once checkout is live → HowTo
(no rich result since 2023, low priority). Never AggregateRating without real reviews. All blocks are in
`technical/schema_markup.md`.

### E. Featured snippet / AI Overview formatting (Gemini and AI Overviews quote these)
- **Paragraph snippets:** under an H2 phrased as the question, a 40–60 word answer that starts with the
  subject ("LeadPilot is…", "Pay per meeting costs…").
- **List snippets:** process questions as `<ol>` (how it works: 7 steps).
- **Table snippets:** pricing and comparison as HTML tables with a header row.
- One question per H2/H3. Don't hide answers in accordions that need JavaScript (the static export renders
  FAQ text in HTML).
- Target questions (have a page or section answering each): "What is LeadPilot?", "How much does LeadPilot
  cost?", "LeadPilot vs Apollo", "What is pay per meeting lead generation?", "Is cold email legal under
  CAN-SPAM?" (statistics page S23, help center 20).

### F. E-E-A-T signals (Experience, Expertise, Authoritativeness, Trust)
| Signal | What to do | Status |
|---|---|---|
| Experience | Founder's own-use story with real numbers, dated (Q-06) and screenshots of the actual product | Missing: needs numbers |
| Expertise | Founders named on /about/ (Rehan Masood and Ahmad Shahid); comparison pages say "Written by LeadPilot's founders" | Live in code 2026-10-16 |
| Authoritativeness | Third-party profiles and mentions (`authority/`) | In progress (G2, Crunchbase exist) |
| Trust | "What is not live yet" section (live), Known limitations, privacy/terms (lawyer-confirmed per LEGAL-101), disclosed authorship on comparisons, "last checked" dates | Strong; keep it |

### G. What not to do
No doorway pages per city or keyword; no AI-mass-produced pages (Google's spam policies apply to AI
answers since May 2026); no buying links; no review markup without real reviews.

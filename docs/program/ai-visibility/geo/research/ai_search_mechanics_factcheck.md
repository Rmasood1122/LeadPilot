# AI search mechanics — fact-check of the brief's premises (2026-10-15)

Every playbook in `platforms/` and `authority/` relies on these verdicts. Sources were read by
web search. Only the GEO paper (arXiv mirror) and Anthropic's help center were read in full;
other quotes are search excerpts of the official page, marked *(excerpt)*. Re-open those
before quoting them publicly.

| # | Premise in the brief | Verdict | What to say instead | Source |
|---|---|---|---|---|
| 1 | "87% of ChatGPT citations match Bing's top-10" | **Partly true** | A small Seer Interactive study (Feb 2025, ~500 SearchGPT citations) found 87% of cited URLs also appeared in Bing's top results (secondary sources say top 20). Correlational, and it predates current ChatGPT search. Ahrefs found only 12% of AI-cited URLs rank in Google's top 10 for the prompt. **Conclusion: Bing indexing is necessary, not sufficient.** | seerinteractive.com/insights/87-percent-of-searchgpt-citations-match-bings-top-results *(excerpt)*; ahrefs.com/blog/ai-search-overlap/ |
| 2 | "Reddit has r=0.80 correlation with AI recommendations" | **Unsupported** | Reddit is consistently among the most-cited domains, but its share is volatile and differs by platform: 6.6% of Perplexity and 2.2% of Google AI Overview citations (Profound, ~680M citations, Aug 2024–Jun 2025). ChatGPT cited Reddit in ~60% of responses in early Aug 2025, falling to ~10% by mid-Sept 2025 (Semrush). **Never quote a correlation coefficient.** | tryprofound.com/blog/ai-platform-citation-patterns; semrush.com/blog/most-cited-domains-ai/ *(excerpt)* |
| 3 | "Up to 40% more citations with statistics (Princeton)" | **Confirmed, with nuance** | Aggarwal et al. (KDD 2024): "GEO can boost visibility by up to 40%". Cite Sources, Quotation Addition and Statistics Addition gave "30-40%" relative improvement on Position-Adjusted Word Count. Keyword stuffing "don't perform well" (−10% on Perplexity). Cite Sources gave +115.1% for the site ranked 5th. Measured on the authors' own engine plus a Perplexity test. | arxiv.org/abs/2311.09735 (v3 read) |
| 4 | "Anthropic's crawler is ClaudeBot; allow anthropic-ai" | **Partly outdated** | Anthropic lists three bots: **ClaudeBot** (training), **Claude-SearchBot** (search index), **Claude-User** (user-requested fetch). `anthropic-ai` and `Claude-Web` are no longer listed (legacy). For *being cited*, Claude-SearchBot and Claude-User matter most. | support.claude.com/en/articles/8896518 (read, updated 2026-04-07) |
| 5 | "Gemini pulls from Google Business Profile" | **Not applicable** | Google Business Profile is **not available** to online-only businesses: a business "must make in-person contact with customers during its stated hours". Calendarharvest is online-only, so skip it. | support.google.com/business/answer/13763036 *(excerpt)* |
| 6 | "Bing Places registration" | **Skip** | Secondary sources say virtual offices are not eligible. Calendarharvest has no storefront, so don't create one (it would need a false address). | UNVERIFIED official page |
| 7 | llms.txt as an "AI content signal" | **Unproven** | Community proposal (llmstxt.org, Jeremy Howard, Sept 2024). No major provider confirms reading it. Google: "Google Search ignores them" (*AI optimization guide, May 2026, excerpt*). **Cheap and harmless; publish it, but expect nothing from it.** | developers.google.com/search/docs/fundamentals/ai-optimization-guide *(excerpt)* |
| 8 | "AI systems weight structured data heavily" | **Overstated** | Google: "no special schema.org structured data that you need to add" for AI Overviews/AI Mode; structured data must match visible content. It still helps rich results and entity understanding. | developers.google.com/search/docs/appearance/ai-features *(excerpt)* |
| 9 | Review/AggregateRating schema for testimonials | **Allowed only with real reviews** | Self-serving reviews are not shown for Organization/LocalBusiness. SoftwareApplication can carry ratings, but only real, visible user ratings. Fake ratings break Google policy and FTC 16 CFR Part 465 (in force since 2024-10-21). | developers.google.com/search/docs/appearance/structured-data/review-snippet; federalregister.gov 2024-18519 |
| 10 | Reddit/Quora "organic mentions" | **Legal constraint** | FTC Endorsement Guides 16 CFR 255.5: an employee/founder posting about their product must disclose the connection "clearly and conspicuously". Reddit sitewide rule 2 bans content manipulation. **Every mention by the team carries a disclosure.** | ecfr.gov 16 CFR 255.5 *(excerpt)*; redditinc.com/policies/reddit-rules |
| 11 | Bing Webmaster Tools for ChatGPT/Copilot | **Confirmed, useful** | The Bing Webmaster Tools **AI Performance** report (public preview since 2026-02-10) shows citations across Copilot and Bing AI summaries, with grounding queries. IndexNow is supported by Bing, not Google; it is already wired (`frontend/scripts/seo/indexnow_submit.mjs`). | blogs.bing.com/webmaster/February-2026/Introducing-AI-Performance-in-Bing-Webmaster-Tools-Public-Preview |
| 12 | Live search by default | **Mostly yes** | Claude searches when helpful and cites every response (support.claude.com/en/articles/10684626). Perplexity searches every query. ChatGPT searches when useful. Gemini grounds on Google Search. **A site launched Sept 2026 can only be named through live retrieval**, because training data predates it. | as cited |

## Crawler tokens (current, for robots.txt)

| Token | Purpose | Allow? |
|---|---|---|
| Googlebot | Google Search, AI Overviews, AI Mode | Yes |
| Google-Extended | Token only: Gemini training + Gemini Apps grounding; no effect on Search | Yes (to be grounded in Gemini Apps) |
| Bingbot | Bing index, which grounds Copilot (and ChatGPT search, per the Seer correlation) | Yes |
| OAI-SearchBot | ChatGPT search results | Yes (essential) |
| ChatGPT-User | User-initiated fetches | Yes |
| GPTBot | OpenAI training | Yes (founder choice; helps future models know the brand) |
| Claude-SearchBot / Claude-User / ClaudeBot | Search index / user fetch / training | Yes |
| PerplexityBot / Perplexity-User | Index / user fetch | Yes |
| Applebot / Applebot-Extended | Siri/Spotlight / training opt-out token | Yes |
| Meta-ExternalAgent / Meta-WebIndexer | Meta AI training / Meta AI search | Yes |
| CCBot | Common Crawl (feeds many training sets) | Yes |
| Amazonbot, DuckAssistBot, MistralAI-User | Alexa/Amazon, DuckDuckGo AI answers, Le Chat fetches | Yes |
| anthropic-ai, cohere-ai | Legacy / undocumented | Harmless to list; the brief's gate asks for them |

The live `frontend/public/robots.txt` already allows all crawlers (`User-agent: *`). Explicit
groups are optional and document intent; see `technical/crawler_access_strategy.md`.

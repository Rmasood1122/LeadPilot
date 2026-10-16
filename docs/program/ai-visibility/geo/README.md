# LeadPilot GEO / AEO system

The plan and the ready-to-publish drafts that make **LeadPilot by Calendarharvest** findable, accurately
described and recommendable by ChatGPT, Claude, Gemini, Perplexity, Copilot and other AI assistants, for
the queries it honestly fits. Built 2026-10-15 on top of the existing program in `docs/program/ai-visibility/`
(SPEC, REPORT, PROMPT_TRACKER). Live progress log: `state.md`. Open decisions: `questions.md`.

## What this can and cannot do
- **Can:** make the site crawlable and unambiguous, give assistants specific, sourced, consistent pages to
  cite for constrained queries ("…for a 10-person agency with no sales team"), and build the third-party
  corroboration assistants rely on.
- **Cannot:** guarantee position #1. Assistants and third-party sites decide that. Broad queries ("best lead
  generation tool") belong to Apollo, ZoomInfo and HubSpot, which have thousands of reviews; LeadPilot has
  none yet. The realistic goal is to be the named answer for its niche, then to grow from there.
- **Starting point (measured 2026-10-15):** LeadPilot by Calendarharvest and calendarharvest.com appeared in
  **0 of 8** web searches (a search tool that does not reflect Google's index: Search Console showed 5 pages indexed on 2026-10-14), including its own name. "LeadPilot" alone returns other companies (LeadPilot AB first).

## Index
| Folder | File | What it is |
|---|---|---|
| / | `entity_card.md` | Seed facts and canonical language. Everything copies from here |
| research/ | `competitor_analysis.md` · `query_library.md` · `ai_search_mechanics_factcheck.md` | Who wins today and why; 50 target queries; which GEO "facts" are true |
| positioning/ | `niche_statement.md` | The ownable niche, and why |
| content/ | `definitions/what_is_leadpilot.md` · `definitions/leadpilot_use_cases.md` · `comparisons/` (5) · `comparison_matrix.md` · `faq_library.md` · `statistics_and_proof.md` | Page drafts (not yet published) |
| technical/ | `schema_markup.md` · `crawler_access_strategy.md` · `site_architecture.md` | JSON-LD, robots/sitemap/llms.txt, URLs and links |
| platforms/ | ChatGPT+Bing · Gemini · Perplexity · Claude · Emerging | Per-engine playbooks |
| authority/ | `citation_acquisition_plan.md` · `reddit_strategy.md` · `syndication_map.md` | Off-site work |
| monitoring/ | `ai_mention_tracker.md` · `content_update_calendar.md` | Measurement and upkeep |

## Status 2026-10-16
Founder answers (questions.md, all 15 answered): publish 12 pages and the help center now, before the trademark review.
**Built and verified in `frontend/`** (branch `claude/relaxed-lamport-ab7g3j`, not yet merged or deployed): the 12 GEO pages, /help/ with 30 articles, /llms.txt, explicit robots.txt, both founders on /about and in JSON-LD. Live copy is in `frontend/src/content/geo/*.ts` and is the source of truth from now on; the `content/` drafts here are the research versions.

## Gates before anything goes public (original; superseded 2026-10-16 by the founder answers above)
1. **Trademark review** of "LeadPilot" (Q-04). Already a founder rule from SPEC Part B.
2. **Competitor facts checked in a browser** with dated screenshots (Q-09).
3. Page cap: Wave 1 = the 6 founder-approved pages; Wave 2 needs approval (Q-13).

## 30 / 60 / 90-day roadmap

### Days 1–30: be findable and unambiguous
| Day | Task | Owner | Doc |
|---|---|---|---|
| 1 | Answer Q-04 (trademark), Q-02 (founder name), Q-06 (own-use numbers) | Founders | questions.md |
| 1 | Run the live crawl checks (REPORT.md "Live checks to run"); fix anything not 200 | Founder | REPORT.md |
| 1–2 | Search Console and Bing are already set up (2026-10-14): after the 50-page deploy, resubmit the sitemap, request indexing for the 12 GEO pages, run IndexNow | Founder | gemini / chatgpt_bing playbooks |
| 3 | AI-app baseline: 20 prompts × 6 platforms (~90 min) | Founder | ai_mention_tracker.md |
| 3–5 | Complete the existing G2, Crunchbase, LinkedIn and YouTube profiles with the copy blocks | Founder | citation_acquisition_plan.md P1 |
| 5–10 | Browser-check competitor facts; record them in NOTES.md | Founder / session | comparison pages' checklists |
| 10–20 | Build Wave 1 (3 comparisons + 3 /for/ pages) in `frontend/`, through the normal gate and PR, and add explicit robots.txt groups | Engineering session | site_architecture.md |
| 20–30 | Capterra/GetApp/Software Advice, AlternativeTo, SaaSHub; Reddit Phase A + B1 (no mentions) | Founder | citation plan, reddit_strategy.md |

### Days 31–60: be citable and corroborated
- Weekly tracker runs. Confirm Wave 1 is indexed (GSC, Bing).
- Decide Wave 2 (FAQ, what-is, statistics, Clay, Artisan, /compare/ hub) and publish the help center (Q-13, Q-14).
- Quora 2/week; Reddit B2 with disclosed mentions at most 1 in 10; Medium syndication per syndication_map.md.
- Product Hunt launch **once Stripe checkout is live**; Show HN in the same window.
- First real users: ask for G2 reviews (no incentives conditioned on sentiment).

### Days 61–90: earn third-party mentions
- Listicle author outreach (template §4), podcast pitches (3), 1 guest post.
- First real-data posts (Reddit C2/C3, Indie Hackers) once there are numbers to report.
- First quarterly review (content_update_calendar.md): competitor refresh, query library refresh, targets vs tracker.

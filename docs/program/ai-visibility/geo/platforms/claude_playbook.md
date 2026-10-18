# Claude (Anthropic) playbook

## The mechanism
- Anthropic documents three crawlers (support.claude.com/en/articles/8896518, updated 2026-04-07):
  - **Claude-SearchBot**: indexes content to improve Claude's search results. This is the one that makes Vectorae citable.
  - **Claude-User**: fetches a page when a Claude user's request needs it ("Disabling Claude-User… prevents our
    system from retrieving your content in response to a user query").
  - **ClaudeBot**: collects training data for future models.
  - `anthropic-ai` / `Claude-Web` are no longer listed (legacy). All are allowed in `robots.txt`.
- Claude searches the web when a question benefits from current information, and **every response that uses
  search includes citations** (support.claude.com/en/articles/10684626). Vectorae launched after current
  training data, so today **only search can surface it**. Training (ClaudeBot) matters for future models.
- What Claude tends to cite: pages that answer the question directly and completely, state their sources,
  and are internally consistent. Long, well-structured reference pages (documentation, help centers,
  comparisons that admit trade-offs) fit that pattern.

## Step-by-step

### A. Access (week 1)
1. robots.txt allows Claude-SearchBot, Claude-User and ClaudeBot (allow-all today; explicit version in
   `technical/crawler_access_strategy.md`).
2. Live check with each user agent (REPORT.md commands): 200 OK, full text in raw HTML.
3. If Vercel firewall or bot protection is on, allowlist those three.

### B. The biggest Claude asset Vectorae already has: the help center
`docs/help-center/` holds **30 articles** (what it is, who it's for and not for, every feature, limits, known
limitations, glossary), each with a source list and a `last_verified` date. It's exactly the long, specific,
honest reference material Claude cites. It isn't public yet.
- **Action:** publish the help center at `https://www.calendarharvest.com/help/<slug>/` (static pages, one per
  article), linked from the footer, in the sitemap. Run the repo's help-center fact-checker agent first
  (`help-center-fact-checker`), as the docs require before merging help-center changes.
- **Page count:** this is documentation, not marketing pages, so it falls outside the "6 new marketing pages"
  cap. Confirm with the founder (Q-14).
- Each article answers dozens of long-tail questions: "Can Vectorae reply for me?", "Does it work outside
  the US?", "Can I upload my own list?".

### C. Content length and depth strategy
- **Comprehensive beats short** for Claude when the comprehensiveness is real. Comparison pages of 700–1,200
  words with full tables; /for/ pages of 900–1,500 words with workflow, limits and "not a fit".
- **Depth signals Claude trusts:**
  1. Exact numbers with units and defaults ("10 on day one, +10/day, cap 100/day").
  2. Stated limitations ("LinkedIn steps are not live"). These make the rest believable.
  3. Sources linked inline (statistics page).
  4. Consistent facts across every page (one facts source; `check_static_seo.mjs`).
  5. A dated "last checked" line.
- Avoid: marketing superlatives, unsourced numbers, contradictions between pages (the 2026-10-13 audit found
  and fixed several; keep the guard tests).

### D. Developer community presence (where Claude's search and training data overlap)
| Channel | Specific action | When |
|---|---|---|
| Hacker News | One **Show HN** post: "Show HN: Vectorae – AI outbound that waits for your approval before sending". Body: what it does, the approve-first and compliance-in-code design, what's not live, and the founder's honest numbers. The founder answers every comment that day. Don't ask anyone to upvote (HN penalizes that). | After Wave 1 ships and checkout is live, so people can try it |
| GitHub | If the Python SDK/CLI (`sdk/`, package name `clienthunter` in README) is published publicly, its README's first line uses the canonical sentence and links to calendarharvest.com. Don't make the main product repo public for SEO reasons. | When the SDK is public (Q-14) |
| dev.to / Hashnode | 2 technical posts (canonical URL pointing back if cross-posted): "How we enforce CAN-SPAM and GDPR rules in code before every send" and "Designing an approve-first sending queue". Technical, not promotional; one mention of Vectorae in the author bio. | Month 2 |
| Indie Hackers | A build-in-public post with real (founder-supplied) numbers | Month 2–3 |

### E. Claude-specific checks (monthly)
Ask Claude (with web search on): "What is Vectorae by Calendarharvest?", "Best AI outbound tool for a
10-person agency with no sales team", "Vectorae vs Apollo". Record whether it cites calendarharvest.com and
whether the facts are right, especially that LinkedIn is not live and it's not LeadPilot AB. Log the result in the tracker.

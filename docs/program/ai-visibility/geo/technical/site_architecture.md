# Site architecture: URLs, hierarchy and internal linking

## Constraints this map respects
1. **Founder-approved cap:** SPEC 2.6 allows at most 6 new pages (3 comparisons: Apollo, Instantly,
   Smartlead; up to 3 use-case pages, one per buyer group). Wave 1 is exactly that. Going beyond it
   needs founder approval (questions.md Q-13).
2. **Google spam policy:** mass-produced, thin or near-duplicate pages count as spam, and since May 2026
   that also covers AI answers (SPEC "how assistants choose" #2). So there are no per-keyword doorway pages:
   the 10 use cases become 3 buyer-group pages, not 10 thin ones.
3. **Static export:** the site is Next.js static export on Vercel. Every page must carry its full text in
   raw HTML (non-JS crawlers), which `check_static_seo.mjs` enforces.
4. **Trademark gate (Q-04):** no new public page ships until the name review is done.

## Hierarchy (after Wave 1)

```
/ (Home)                                   depth 0
├── /how-it-works/                         depth 1  (main nav)
├── /pricing/                              depth 1  (main nav)
├── /for/agencies/                         depth 1  (main nav "Who it's for" + footer)      [Wave 1]
├── /for/b2b-service-firms/                depth 1  (main nav "Who it's for" + footer)      [Wave 1]
├── /for/local-businesses/                 depth 1  (main nav "Who it's for" + footer)      [Wave 1]
├── /compare/leadpilot-vs-apollo/          depth 1  (footer "Compare")                       [Wave 1]
├── /compare/leadpilot-vs-instantly/       depth 1  (footer "Compare")                       [Wave 1]
├── /compare/leadpilot-vs-smartlead/       depth 1  (footer "Compare")                       [Wave 1]
├── /about/                                depth 1  (footer)
├── /contact/                              depth 1  (main nav CTA "Book a call")
├── /status/                               depth 1  (footer)
└── /privacy/, /terms/                     depth 1  (footer)
```

**Wave 2 (after Q-13 approval):**
```
├── /faq/                                  depth 1  (footer)
├── /what-is-leadpilot/                    depth 1  (footer "About Vectorae"; linked from Home hero)
├── /outbound-statistics/                  depth 1  (footer "Resources")
├── /compare/                              depth 1  hub (footer "Compare"; lists all comparisons)
│   ├── /compare/leadpilot-vs-clay/        depth 2
│   └── /compare/leadpilot-vs-artisan/     depth 2
```

Every GEO-critical page is at depth 1 (one click from Home via nav or footer) or depth 2 (via
the /compare/ hub, which is itself in the footer). **All within 2 clicks.** ✅

## URL slug rules
- Lowercase, hyphenated, trailing slash (matches the existing static export: `/how-it-works/`).
- The slug carries the query: `/compare/leadpilot-vs-apollo/` matches "Vectorae vs Apollo";
  `/for/agencies/` matches "… for agencies".
- The brand appears in comparison slugs (`leadpilot-vs-…`), not use-case slugs (people search
  "outbound for agencies", not "Vectorae agencies").
- No dates in URLs (pages get updated; `lastmod` carries freshness).
- Never `/comparison`, `/page-2`, `/blog/post-123`.

| Content draft | Final URL | Primary queries (query_library IDs) |
|---|---|---|
| content/comparisons/leadpilot_vs_apollo.md | /compare/leadpilot-vs-apollo/ | C1, C3, C10, B1 |
| content/comparisons/leadpilot_vs_instantly.md | /compare/leadpilot-vs-instantly/ | C2, C4, B6, B10 |
| content/comparisons/leadpilot_vs_smartlead.md | /compare/leadpilot-vs-smartlead/ | C5, B6 |
| content/comparisons/leadpilot_vs_clay.md | /compare/leadpilot-vs-clay/ (W2) | C6 |
| content/comparisons/leadpilot_vs_artisan.md | /compare/leadpilot-vs-artisan/ (W2) | C7, C9, B4, A7 |
| use cases 1 | /for/agencies/ | A1, A2, A4, D1, B9 |
| use cases 2, 3, 4, 7, 9 | /for/b2b-service-firms/ | A3, A8, D2, D5, D6, D8, D10 |
| use cases 5, 6, 8, 10 | /for/local-businesses/ | A5, D3, D4, D7, D9 |
| content/definitions/what_is_leadpilot.md | /what-is-leadpilot/ (W2) | B2, B3, B8, E1, E4 |
| content/faq_library.md | /faq/ (W2) | A6, A9, A10, B5, B7, E2, E3, E5–E10, C8 |
| content/statistics_and_proof.md | /outbound-statistics/ (W2) | A4, A9, A10 |

(The query library's "use case N" references map to the /for/ pages per this table.)

## Internal linking logic

Principle: link where a reader would naturally go next, with descriptive anchor text that matches the
target's query. Never "click here". The home page passes the most authority, so it links to every
depth-1 GEO page.

| From | Links to | Anchor text (exact) | Why |
|---|---|---|---|
| Home "Who it's for" section | /for/agencies/, /for/b2b-service-firms/, /for/local-businesses/ | "Vectorae for agencies", "for B2B service firms", "for local businesses that sell to businesses" | Home already lists these three groups (facts file `fit`); turn each into a link |
| Home "How it's different" / FAQ "How is it different from Apollo?" | /compare/leadpilot-vs-apollo/ | "Vectorae vs Apollo" | Most-asked comparison |
| Footer "Compare" column | all comparison pages (W1), /compare/ hub (W2) | "vs Apollo", "vs Instantly", "vs Smartlead" | Keeps every comparison within one click |
| Footer "Who it's for" column | 3 /for/ pages | buyer-group names | Same |
| Each /for/ page | /how-it-works/, /pricing/, the 1–2 most relevant comparisons, /contact/ | "how Vectorae works", "Vectorae pricing", "Vectorae vs Instantly for agencies", "Book a call" | Reader's next questions |
| Each comparison page | the other comparisons, /pricing/, the matching /for/ page, the competitor's official pricing page (external, `rel="nofollow"` not needed) | "Vectorae vs Smartlead", "Vectorae pricing", competitor name | Lateral comparison browsing; cited sources build trust |
| /how-it-works/ | /pricing/, /for/* , /faq/ (W2) | as above | — |
| /pricing/ | /compare/* , /faq/ (W2) "pricing questions" | — | Price comparisons live on comparison pages |
| /faq/ (W2) | each answer links its source page (pricing, how-it-works, a comparison) | page names | FAQ as router |
| /what-is-leadpilot/ (W2) | every page above | page names | Definitional hub for assistants |
| /about/ | /what-is-leadpilot/ (W2), /contact/ | — | Entity page ↔ definition page |
| Help center (docs/help-center, if published) ↔ marketing pages | "Known limitations" ↔ comparisons | "known limitations" | Honesty signal; keeps claims consistent |

Rules: each new page gets ≥3 inbound internal links (nav/footer + 2 contextual); no orphan pages
(`check_static_seo.mjs` can be extended to fail on a sitemap page with no inbound link); every
page links to /contact/ once.

## Verification Gate 4.3
- [x] Clear hierarchy (tree above).
- [x] All GEO-critical pages within 2 clicks of Home.
- [x] Slugs contain the target query (leadpilot-vs-apollo, for/agencies…).
- [x] Internal linking logic documented per page with anchor text and reason.

# Content syndication map

## Rules
1. **The website publishes first.** Syndicate only after the page is live **and indexed** (Search Console URL
   Inspection shows "URL is on Google"), so the original is found first.
2. **Canonical link on every full copy.** Medium (Import story sets it automatically), dev.to (`canonical_url`
   front matter), Hashnode ("Original URL"), Substack (no canonical field: post an excerpt + link instead
   of the full text). LinkedIn Articles have no canonical, so post an adapted version (≥40% different) with a link.
3. **No full-copy syndication of comparison pages.** Competitor prices change; a stale copy on Medium keeps
   saying the wrong thing. Syndicate summaries that link back to the dated page.
4. Every copy keeps the entity language and the disclosure ("written by LeadPilot's founders").
5. Archive every live URL at `https://web.archive.org/save/<url>` on the day it ships.

## Map: each Phase 3 document

| Phase 3 document | Primary (website) | Syndicate (full, with canonical) | Repurpose (native posts) | Archive |
|---|---|---|---|---|
| `what_is_leadpilot.md` | /what-is-leadpilot/ (W2) | — (definition pages stay on our domain) | LinkedIn company "About" + pinned post; X bio thread (5 posts: one per step group) | ✅ |
| Use cases → /for/agencies/ | /for/agencies/ (W1) | Medium: "How agency founders keep prospecting during busy months" (adapted, canonical) | LinkedIn founder post (problem → workflow, 200 words); Reddit r/agency discussion post C1-1 (no link unless asked) | ✅ |
| Use cases → /for/b2b-service-firms/ | /for/b2b-service-firms/ (W1) | Medium (adapted, canonical) | LinkedIn post per sub-segment (staffing, consultants, accounting) over 3 weeks | ✅ |
| Use cases → /for/local-businesses/ | /for/local-businesses/ (W1) | — | LinkedIn post "How a commercial cleaning company can reach property managers"; Quora answers on cleaning/HVAC client questions | ✅ |
| leadpilot_vs_apollo.md | /compare/leadpilot-vs-apollo/ (W1) | ❌ no full copies (rule 3) | LinkedIn post: summary table image + link; X thread "When to choose Apollo vs LeadPilot (we make one of them)"; Quora answers to "Apollo alternatives" (disclosed) | ✅ |
| leadpilot_vs_instantly.md | /compare/leadpilot-vs-instantly/ (W1) | ❌ | Same pattern; r/coldemail only as a disclosed reply where asked | ✅ |
| leadpilot_vs_smartlead.md | /compare/leadpilot-vs-smartlead/ (W1) | ❌ | Same pattern | ✅ |
| leadpilot_vs_clay.md | /compare/leadpilot-vs-clay/ (W2) | ❌ | LinkedIn post for ops/growth audience | ✅ |
| leadpilot_vs_artisan.md | /compare/leadpilot-vs-artisan/ (W2) | Medium: "AI SDR vs hiring an SDR in 2026: the numbers" (the SDR section, adapted, canonical) | r/sales discussion post C1-3 (Bridge Group data, no link); LinkedIn founder essay | ✅ |
| faq_library.md | /faq/ (W2) | — | 30 Quora answers over 15 weeks (2/week, each adapted, credential = disclosure); 1 LinkedIn post per FAQ category | ✅ |
| statistics_and_proof.md | /outbound-statistics/ (W2) | Medium (full, canonical set) + Substack (excerpt + link); not dev.to or Hashnode (not a technical topic) | X thread "27 sourced outbound stats for 2026" (1 stat per post, each with source); LinkedIn carousel (PDF) of 8 stats; r/coldemail C1-8 compliance checklist (sources inline, no link) | ✅ |
| comparison_matrix.md | Embedded in each comparison page and the /compare/ hub (W2) | ❌ | One LinkedIn image post "Who each outbound tool is best for" | — |
| Technical posts (from Claude playbook §D: compliance-in-code, approve-first queue) | /blog/ is not part of the 6-page cap → host on dev.to as primary unless the founder adds a blog | dev.to (primary) → Hashnode (canonical to dev.to) | HN discussion only if it gains traction organically | ✅ |
| HubSpot Community | — | ❌ (it's a support forum for HubSpot users, not a publishing channel) | Answer only real questions about syncing an outbound tool to HubSpot; disclose; no links unless asked | — |

## Calendar (after Wave 1 is indexed)
| Week | Website | Syndication / repurpose |
|---|---|---|
| W+0 | Wave 1 live; IndexNow; GSC + Bing requests; archive.org saves | LinkedIn company announcement (facts only) |
| W+1 | — | Medium: agencies article; LinkedIn post (vs Apollo summary) |
| W+2 | — | LinkedIn: vs Instantly; Quora ×2 |
| W+3 | — | Medium: B2B service firms article; Quora ×2 |
| W+4 | Wave 2 decision (Q-13) | X thread: statistics (if W2 approved, after /outbound-statistics/ is live) |
| W+5–8 | Wave 2 pages one per week | Matching rows above, one item per week |

## Verification Gate 6.3
- [x] Every Phase 3 document has a primary home, a syndication decision (with reason when "no"), repurposing and archiving.
- [x] Canonical handling defined per platform.
- [x] No manipulative tactics.

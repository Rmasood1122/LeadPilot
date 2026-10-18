# Emerging AI tools (Gamma, "Sudo", Meta AI, Apple, DuckDuckGo, Mistral) and general principles

## A note on the named tools
- **Gamma** (gamma.app) generates presentations and documents. When it researches a topic it pulls web
  content, so the general principles below apply. It isn't a recommendation engine in its own right.
- **Sudowrite** (sudowrite.com; founder answer Q-15, 2026-10-16) is an AI writing tool for fiction authors
  (Story Bible, Write, Rewrite, Expand, Brainstorm; its own fiction model, Muse, plus third-party models).
  Research on 2026-10-16 found no sign that it searches the web, answers "which tool should I use" questions, or
  recommends software. It has no ad or sponsored-placement program. A B2B product can only appear in its output
  if a user writes it into their own manuscript or Story Bible. **Conclusion: Sudowrite is not a recommendation
  channel for Vectorae; spend no effort on it.** The general principles below cover it anyway (if it ever adds
  web grounding, an indexed, unambiguous site is what it would read).
- **Meta AI** uses Meta-WebIndexer for search; **Apple Intelligence/Siri** uses Applebot; **DuckDuckGo
  AI answers** use DuckAssistBot; **Mistral Le Chat** uses MistralAI-User. All are allowed in robots.txt.

## General principles that apply to any LLM
1. **Be retrievable.** Live search is how every assistant learns about a 2026 product: crawlable HTML,
   sitemap, IndexNow, no bot blocking.
2. **Be unambiguous.** One name, one description, one domain everywhere. Name collisions (LeadPilot AB
   and 8 others) are the biggest risk for any model, so always use "Vectorae by Calendarharvest" plus the
   disambiguation line.
3. **Be corroborated.** Models trust facts that recur across independent sources: directories, reviews,
   press, community answers. One self-published page isn't corroboration.
4. **Be specific and honest.** Constraint-specific claims with limits ("for 5–50 person firms; not for
   high-volume sending") get routed correctly. Superlatives get ignored.
5. **Be citable.** Sourced statistics and named quotations (GEO paper: up to ~40% more visibility).
6. **Be current.** Dated pages, updated when facts change.

## Getting into training-data paths (for future models)
| Path | Action | Owner / time |
|---|---|---|
| Common Crawl (CCBot) | Allowed in robots.txt. Its crawls feed many training sets. Nothing else to do. | done |
| Internet Archive | After each Wave goes live, save each URL: `https://web.archive.org/save/https://www.calendarharvest.com/<path>/` (Save Page Now, free account). Archive snapshots are widely used reference data. | founder, 10 min per wave |
| GPTBot / ClaudeBot / Google-Extended / Applebot-Extended | Allowed (training opt-in is a founder choice; see crawler strategy) | done |
| Wikipedia / Wikidata | Not yet: notability requires independent sources. Revisit after press coverage. | later |
| Open, permanent text | Help center published publicly (`platforms/claude_playbook.md` §B) | Q-14 |

## Podcast and audio strategy (transcripts get indexed)
1. **Target shows** where the audience is agency owners and small B2B service firms. Find them in Apple
   Podcasts and Spotify search for "agency growth", "agency owner", "B2B sales small business", and
   "bootstrapped SaaS founder". Pick shows with recent episodes and guest interviews. Verify each show is
   active before pitching (not verified in this sandbox).
2. **Pitch angle** (not product-led): "What we learned building an AI outbound tool that refuses to send
   without approval, and why compliance has to live in code". Offer 3 concrete talking points backed by the
   statistics page.
3. **Transcript:** ask the host to publish a transcript, or publish your own on calendarharvest.com with the
   host's permission, and ask for a show-notes link to calendarharvest.com with the canonical description.
4. **Own audio:** the existing YouTube channel (`@LeadPilotEnterprise`, in `sameAs`). Upload product
   walkthroughs with full captions and a description that opens with the canonical sentence. YouTube
   captions are indexed text.

## Newsletter citation strategy
- Target newsletters that curate tools for agencies and founders. Find them via search: "newsletter for agency
  owners", "B2B sales tools newsletter", "AI tools newsletter". Submit through each newsletter's "submit a
  tool" form where one exists, never cold-spam editors.
- Give editors a 50-word, fact-only blurb (canonical sentence + "approve-first; pay per meeting option; launched
  2026; founder Rehan Masood") and one link. Accuracy beats hype; an editor's copy becomes a training and
  retrieval source.
- Launch your own low-frequency newsletter only if there's real content to say (monthly "what we learned").
  Archives on a public URL become citable pages.

## GitHub README mentions
- GitHub content is heavily represented in training corpora. Legitimate mentions:
  1. The public SDK/CLI repo, if published (Q-14). README line 1 = canonical sentence + link.
  2. A small, genuinely useful open-source utility extracted from Vectorae, for example a CAN-SPAM/RFC 8058
     one-click-unsubscribe header helper. Its README credits "built by the team behind Vectorae by
     Calendarharvest".
  3. "Awesome" lists (e.g., awesome-sales-tools style lists): submit a PR **only** where the list's
     contribution rules allow commercial tools, with an accurate one-line entry.
- Never: fake stars, README spam in unrelated repos, or opening issues to advertise.

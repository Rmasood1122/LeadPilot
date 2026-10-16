# Questions for Ahmad — GEO system

Each question records the assumption used to keep working. Answer them in place;
an answer that changes a fact is applied to `frontend/src/content/product-facts.json`
first, then to the drafts here.

Legend: **[ASSUMPTION MADE — REVIEW TOMORROW]** · **ANSWERED <date>:** founder answer (verbatim in `docs/program/ai-visibility/NOTES.md`)

---

### Q-01 — 2026-10-15 17:39 UTC — Where should the GEO system live?
The brief asks for `state.md`, `questions.md` and the folders in the "project root".
The repo root is the production codebase (FastAPI/Next.js) with merge gates.
**Assumption:** everything lives in `docs/program/ai-visibility/geo/`, next to the
existing AI-visibility program it extends. Paths in the brief are relative to that folder.
**ANSWERED 2026-10-16:** "Good and it is ok store state.md and questions.md in docs/program/ai-visibility/geo/" → confirmed.

### Q-02 — 2026-10-15 17:39 UTC — Founder name and public founder
The brief says LeadPilot was "built by Ahmad Shahid". The repo says the founders are
Rehan Masood and Ahmad (`docs/program/STAR_PROMPT.md` says "Ahmad Masood"). The live
`/about` page and the Person JSON-LD name **Rehan Masood** (Astoria, New York) as founder.
**Assumption:** public content names Rehan Masood as founder (as the live site does) and
does not name a second founder until you confirm the exact name and whether you want to
be named publicly. Entity consistency matters: a second founder name that differs between
the site and third-party profiles confuses assistants.
**ANSWERED 2026-10-16:** "Display Ahmad Shahid and Rehan Masood both as Founder" → both added as Founder in product-facts.json, /about and the JSON-LD.

### Q-03 — 2026-10-15 17:39 UTC — "Calendar-powered" positioning
The brief's examples describe LeadPilot as "calendar-powered lead generation" that matches
"prospect availability with the user's calendar". The code does not do that: LeadPilot has
its own booking pages and a Calendly hook, and it does **not** read Google Calendar
(`docs/help-center/14-booking-and-calendar.md`). Publishing the calendar claim would be
false, and assistants that later read the help center would flag the contradiction.
**Assumption:** positioning is "approve-first, done-for-you AI outbound for founder-led
agencies and B2B service firms". The calendar is the end of the workflow ("from what you
sell to meetings on your calendar", the live homepage H1), not the mechanism.
**ANSWERED 2026-10-16:** "use real thing every where" → positioning stays on what the product actually does.

### Q-04 — 2026-10-15 17:39 UTC — Trademark review (blocks publishing)
`docs/program/ai-visibility/REPORT.md` records "Trademark: Not reviewed; keep name" and
defers new public pages and llms.txt until counsel reviews "LeadPilot" against
LeadPilot AB (leadpilot.com, Sweden, since 2019) and Twenty Over Ten's "Lead Pilot" (US).
Every page here assumes the brand stays "LeadPilot by Calendarharvest".
**Assumption:** all content in this folder is a draft, ready to paste once the trademark
outcome is "reviewed, keep the name". Nothing here changes the live site.
**Question:** has a trademark attorney reviewed the name yet, and with what outcome?
**ANSWERED 2026-10-16:** "Not yet". Together with Q-13/Q-14 ("publish"), the founder chose to publish before the trademark review. **Risk kept on record:** if a review later requires a rename, every new page, listing and profile has to change.

### Q-05 — 2026-10-15 17:39 UTC — Brand spelling: "CalendarHarvest" vs "Calendarharvest"
The brief writes "CalendarHarvest". The facts file, titles and JSON-LD use "Calendarharvest".
**Assumption:** keep "Calendarharvest", exactly as the live site does. One spelling everywhere.
**ANSWERED 2026-10-16:** "use Calendarharvest every where" → confirmed.

### Q-06 — 2026-10-15 17:39 UTC — Own-use performance numbers
The 2026-10-13 founder answer was "Own-use numbers — I'll give them", but no numbers were
supplied. Statistics pages, use cases and schema need them: meetings booked, reply rate,
emails sent, time spent per week, period measured, and how measured.
**Assumption:** no LeadPilot performance number is published anywhere. Every slot that
needs one is marked `[FILL IN — own-use number + date + how measured]`.
**ANSWERED 2026-10-16:** "I will give it later" → slots stay [FILL IN]; nothing published.

### Q-07 — 2026-10-15 17:39 UTC — Reviews and AggregateRating
There are no public reviews yet. Marking up made-up ratings breaks Google's structured-data
policy and the FTC rule on fake reviews (16 CFR Part 465).
**Assumption:** the Review/AggregateRating schema is delivered as a template that must stay
unpublished until real, independently collected reviews exist. The G2 listing in `sameAs`
(`g2.com/products/leadpilot-2026-10-14`) is the place to collect them.
**ANSWERED 2026-10-16:** "ok" → no review/rating markup until real reviews exist.

### Q-08 — 2026-10-15 17:39 UTC — Stripe checkout and the free trial
Checkout is "simulated only" in the facts file, so the site does not promise a trial or
online cancellation. The help center describes a 14-day trial that applies once checkout is live.
**Assumption:** content says "pricing is published; online checkout is not live yet —
contact us to start", and never promises a free trial.
**ANSWERED 2026-10-16:** "no I am getting stripe keys Today i will make live Full Payment with test" → `stripe_checkout` stays "simulated_only" until you confirm a real end-to-end payment works; then flip it in product-facts.json and every page follows. Still no trial promise until then.

### Q-09 — 2026-10-15 18:20 UTC — Competitor prices need a browser check
The sandbox could not open any competitor's pricing page (proxy 403, no DNS for the fetch tool).
Every competitor price in `research/competitor_analysis.md`, `content/comparison_matrix.md` and
`content/comparisons/*` comes from search-index excerpts of the vendor's own pages, and several
vendors' own pages contradict each other.
**Assumption:** prices are shown with "(checked via search excerpt 2026-10-15 — verify)" and every
comparison page has a pre-publish checklist: open the official pricing page, save a dated screenshot,
and record URL + date + exact text in `docs/program/ai-visibility/NOTES.md` (SPEC 2.6a rule).
**ANSWERED 2026-10-16:** "you research on G2 cunchbase youtube and other things" → competitor prices re-researched across independent sources; a price is shown on the site only when two independent sources agree, otherwise the page links to the competitor's pricing page.

### Q-10 — 2026-10-15 18:20 UTC — Reddit research must be done by hand
Reddit is blocked from this sandbox (search tool and proxy). No real threads were collected, and none
are invented. `authority/reddit_strategy.md` has the method and a blank log for the 20 threads.
**Assumption:** a founder (or a session with Reddit access) runs Phase A by hand. About 60 minutes.
**ANSWERED 2026-10-16:** "ok" → founder runs Reddit Phase A.

### Q-11 — 2026-10-15 18:20 UTC — Google Business Profile and Bing Places
The brief asks for both. Google's rules exclude online-only businesses ("must make in-person contact
with customers"). Creating either would need an address customers visit, which Calendarharvest doesn't have.
**Assumption:** neither is created; the playbooks explain why and what to do instead.
**ANSWERED 2026-10-16:** "I have a Business Mail ahmadshahid@calendarharvest.com" → useful for claiming G2, Crunchbase, Capterra and Bing Webmaster (domain email matches the site). It does not make Google Business Profile or Bing Places eligible: both require a place customers visit or in-person service. Still not created.

### Q-12 — 2026-10-15 18:20 UTC — Baseline in the AI apps themselves
This sandbox cannot sign in to ChatGPT, Claude.ai, Gemini, Perplexity or Copilot, so the "before"
measurement in those apps could not be run. What was run: 8 web searches (none returned LeadPilot by
Calendarharvest or calendarharvest.com).
**Assumption:** `monitoring/ai_mention_tracker.md` holds the protocol and a pre-filled baseline sheet.
The expected result is "not mentioned" everywhere, and a founder spends about 90 minutes to fill it.
**ANSWERED 2026-10-16:** "ok i will complete" → note: a partial run already exists (NOTES.md 2026-10-15: not ranked on niche/comparison questions; founder misnamed "Ramish Masood"; LeadPilot AB's G2 reviews attributed to LeadPilot).

### Q-13 — 2026-10-15 18:50 UTC — The 6-new-page cap
The founder-approved SPEC 2.6 allows at most 6 new public pages (3 comparisons + 3 buyer-group pages).
This GEO system drafts more: FAQ, what-is, statistics, Clay and Artisan comparisons.
**Assumption:** Wave 1 = the 6 approved pages (vs Apollo, vs Instantly, vs Smartlead, /for/agencies/,
/for/b2b-service-firms/, /for/local-businesses/). The 10 use cases are merged into those 3 pages. Wave 2
(the other 6) waits for your approval and should go out 4+ weeks after Wave 1, once indexing is
confirmed in Search Console and Bing Webmaster Tools.
**ANSWERED 2026-10-16:** "you can Publish 12 new Pages" → all 12 drafted pages built in frontend/.

### Q-14 — 2026-10-15 19:10 UTC — Publish the help center and the SDK?
`docs/help-center/` (30 fact-checked articles) is the strongest citable asset for Claude, Perplexity and
ChatGPT, but it isn't public. Separately, the README describes a pip package (`clienthunter`) and an `sdk/`
folder; whether it's published publicly is unknown.
**Assumption:** recommended (not done): publish the help center at /help/<slug>/ as documentation, outside
the 6-marketing-page cap, after running the help-center fact-checker. The SDK is only mentioned if it's public.
**ANSWERED 2026-10-16:** "Publish it" → help center published at /help/.

### Q-15 — 2026-10-15 19:10 UTC — Which "Sudo" is meant?
The brief names "Gamma, and Sudo" as target AIs. Several AI products use the name "Sudo", and I couldn't
confirm which one is meant.
**Assumption:** covered by the general principles in `platforms/emerging_ai_playbook.md`. Tell me the product
URL and I'll add a specific section.
**ANSWERED 2026-10-16:** "Sudowrite is ai for writing" → Sudowrite section added to platforms/emerging_ai_playbook.md.

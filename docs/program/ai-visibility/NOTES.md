# AI visibility — working notes

## Phase 0 founder answers (verbatim, 2026-10-13, via AskUserQuestion)

- Q1 founder location / legal entity: "Astoria NY; no entity yet"
- Q2 prices in page HTML: "Names, features and prices"
- Q3 sending: "Email auto; LinkedIn not live" (option text: "Emails send automatically after approval; LinkedIn automation is not live yet. I'll record this under D1.")
- Q4 profiles / sameAs (G2 "LeadsPilot", GetApp "LeadsPilot", LinkedIn leadpilot-app): "None of these"
- Q5 trademark (outcome only): "Not reviewed; keep name"
- Q6a live end to end: "Market research,Contact find + verify,Email writing,Email sending (Gmail)"
- Q6b live end to end: "Reply routing,Meeting booking,WhatsApp" (Stripe checkout NOT selected → not live)
- Q7 proof: "Own-use numbers"
- Q7 follow-up (which numbers): "I'll give them (Other)" — no numbers were supplied → treated as unanswered; nothing published; TODO(founder).
- Q8 Vercel production branch / PR base: "master / master"
- Work branch: "seo/ai-visibility"

### Consequences drawn
- Stripe checkout not live → 2.2: static HTML gets plan names + features only; no offers in JSON-LD; browser-loaded prices unchanged; founder question in REPORT.
- Trademark not reviewed → Part B (2.6, 2.7) is next-session work.
- LinkedIn not live → pages must not say LinkedIn messages send; state its status.
- No sameAs profiles → Organization has no sameAs. LinkedIn leadpilot-app on /contact is a visible link; not added to sameAs (founder said "None of these").
- Founder location Astoria, New York → /about changes from Faisalabad.

## Done

- Phase 0 complete.
- Phase 1: SPEC.md, state.json, NOTES.md; BASELINE.md (frontend checks clean with NEXT_PUBLIC_API_URL set; live site NOT RUN: proxy refuses calendarharvest.com and the Render API); check_static_seo.mjs + expected_plans.json written, exit 1 on the old export (40 failures).

## Next step

- 1.4: present plan, wait for approval.

## Open questions

- Own-use numbers: which, with date and source.

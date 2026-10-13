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

## 1.4 plan approval (verbatim, 2026-10-13)
- Plan: "Approve as written (Recommended)" — titles stay literal (no test changes); spec-literal pricing fallback; remove 4 dead blog URLs; add postbuild hook after the check passes.
- LinkedIn status: "Tested only vs simulated"

## 2.1 done
- robots.txt Sitemap → www; public/sitemap.xml replaced by src/app/sitemap.ts reading src/content/site-pages.json (7 pages; 4 dead /blog/ URLs removed); canonical + og:url on all 7 pages via src/lib/seo/pageMeta.ts; /pricing split into server page.tsx + PricingClient.tsx.
- Check after 2.1: host/canonical failures gone; remaining = JSON-LD (2.4) and plan names (2.2).
- Next: 2.2.

## 2.2 done
- Plans source: GET /billing/catalog (app/api/billing.py:73, public) → app/core/billing_catalog.py + app/core/plans.py.
- Live API (https://leadpilot-api-ph3t.onrender.com) unreachable from this sandbox (proxy 403) → no snapshot committed; snapshot check NOT RUN.
- Static HTML renders plan names from src/content/plan-names.json (names in billing_catalog.py; src/tests/planNames.test.ts keeps them in sync; shown failing on a renamed tier). Features render once plans-snapshot.json exists.
- Stripe checkout not live → no static prices, no offers; TODO(founder) in src/lib/seo/staticPlans.ts.
- Open: the live-loaded feature bullets (lib/pricing.ts channelList) list "LinkedIn" for Growth+; LinkedIn is not live → handle in 2.5.
- Next: 2.3.

## 2.3 done
- frontend/src/content/product-facts.json (beside site-pages.json / plan-names.json; JSON so the .mjs check reads it with no build step) + src/lib/productFacts.ts (PRODUCT_FULL_NAME built from brand.product_name + brand.company_name).
- Capability statuses from Phase 0 Q3/Q6 and the LinkedIn status answer; off-by-default ones from system_settings.py flag defaults (same list as the home FEATURES).
- Description unchanged from the spec: every capability it names (research, contacts, writing, sending, booking) is live per Q6.
- Titles: literal per page (approved), all contain "LeadPilot by Calendarharvest" and end "| Calendarharvest"; /pricing got a title and description.
- Checks added: title has full product name; JSON-LD sameAs / Person values from the facts file; JSON-LD prices from plans-snapshot.json.
- Next: 2.4.

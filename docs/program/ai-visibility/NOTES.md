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

## 2.4 done
- src/lib/seo/structuredData.ts + src/components/seo/JsonLd.tsx; one @graph per page.
- Organization (Calendarharvest, footer) + WebSite on all 7; SoftwareApplication (name "LeadPilot by Calendarharvest", BusinessApplication, "Web, Android", no offers) on / and /pricing; FAQPage on / and /contact (visible FAQs); BreadcrumbList LeadPilot → nav/footer label on subpages; Person (Rehan Masood) on /about only.
- check_static_seo.mjs: PASS (7 URLs) after 2.4.
- Depends on 2.5: "Astoria, New York" must become visible on /about, and the facts description must be visible on / and /pricing.
- Next: 2.5.

## 2.5 done — removals and rewordings (for REPORT.md)
- Home: "LinkedIn and WhatsApp steps … available / LinkedIn from Growth" → WhatsApp steps (available, from Starter) + LinkedIn steps listed under "Built and tested only against simulated services; not live yet" (with Stripe checkout).
- Home: "Email, LinkedIn and WhatsApp replies land in one inbox" → "Email and WhatsApp replies…".
- Home: "Recent LinkedIn posts and company news can shape the opening" → company news; LinkedIn posts go through the LinkedIn connection, not live yet (app/integrations/linkedin_posts.py uses Unipile/RapidAPI).
- Home FAQ "What has not been verified yet?" (Apollo, Hunter, Gmail, WhatsApp, Calendly, Stripe simulated) → "What is not live yet?" built from product-facts.json (LinkedIn steps, Stripe checkout), per Q6.
- Home FAQ: messaging uploaded LinkedIn connections → states LinkedIn steps are not live.
- Home: first mention "LeadPilot by Calendarharvest" above the H1; facts description shown in "Who it's for"; AUDIENCES / NOT_A_FIT now read product-facts.json.
- /how-it-works: "72-step research pipeline" → "once per campaign strategy: 72 … or 144"; "Personalised emails and LinkedIn messages … from the Gmail and LinkedIn accounts" → email from Gmail; WhatsApp on plans; LinkedIn not live; removed "A four-step conversation sequence: observe, reflect the pain, introduce your offer, earn the call" (no code source); "Learning" step (ICP refined, compounds, Revenue & ROI dashboard: not founder-confirmed) → "Replies and meetings" (live per Q6); "Your only job is to show up … You handle the calls we book … LeadPilot handles [following up]" → "What you still do" consistent with home (daily approval, held messages, you write every answer).
- /about: Faisalabad, Pakistan → Astoria, New York (Q1); removed "has published more than 18 public repositories on GitHub", "today it is the system that finds LeadPilot's own clients", "He uses it himself, every day, to find LeadPilot's own clients"; "72-step" → 72 or 144 per strategy; LinkedIn sending → not live; "Learning" → "Replies and meetings"; audience list (boutique agencies 3–30 staff in 7 countries, coaches, early SaaS founders, fractional consultants "resell or white-label") → product-facts fit (same as home).
- /contact: "boutique agency with 3–30 staff in [7 countries]" → facts fit groups; removed "You are based outside our approved geographies" (no definition in code) → facts not-a-fit list; LinkedIn FAQ → included in plans but not live.
- /pricing: intro shows the facts description and the not-live sentence.
- /privacy, /terms: only title, description, canonical, og:url, JSON-LD changed.
- DECISIONS.md D1: appended the 2026-10-13 founder answer (email automatic; LinkedIn not live).
- Kept (founder questions): /about H1 + meta "used it to find his own clients"; /how-it-works H1 "Your pipeline. Running without you."; /contact "done-with-you system" and "a pipeline that runs without you in it".
- Next: 2.8.

## 2.8 done
- Key 99b0961bddf18b9b8d31299dc0962e3b: frontend/public/<key>.txt + scripts/seo/indexnow.json; scripts/seo/indexnow_submit.mjs (--sitemap, --dry-run); state in scripts/seo/.indexnow-state.json (gitignored). IndexNow API NOT called.
- Founder command after deploy: cd frontend && node scripts/seo/indexnow_submit.mjs
- check_static_seo.mjs: key file must be in the export and contain the key.
- Next: 2.9.

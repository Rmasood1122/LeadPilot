# AI visibility — baseline (2026-10-13)

Branch `seo/ai-visibility` from `origin/master` at `deda9e0`. `docs/program/BASELINE.md` is unchanged.

## 1. Frontend checks before any change (item 1.1)

Run from `frontend/` with Node v22.22.0 after `npm ci` (exit 0).

| Command | Exit | Result |
|---|---|---|
| `npm run type-check` | 0 | clean |
| `npm run lint` (no env) | 1 | **not a lint finding**: `next.config.js` refuses to load without `NEXT_PUBLIC_API_URL` ("BUILD FAILED: NEXT_PUBLIC_API_URL is not set."). CI sets `NEXT_PUBLIC_API_URL: https://api.example.invalid` for this reason (`.github/workflows/verify.yml`, job `verify-frontend`). |
| `NEXT_PUBLIC_API_URL=https://leadpilot-api-ph3t.onrender.com npm run lint` | 0 | 6 warnings, 0 errors: `react-hooks/exhaustive-deps` (`src/app/(app)/network/page.tsx:34`) and `@next/next/no-img-element` (`(app)/team/page.tsx:418`, `share/roi/page.tsx:68`, `components/shell/Shell.tsx:34`, `components/ui/Logo.tsx:34,55`). Corrected in the 2.1 commit: the first count read only the end of the log. |
| `npm test` | 0 | 96 files, 1145 tests passed, 41.6 s |
| `NEXT_PUBLIC_API_URL=https://leadpilot-api-ph3t.onrender.com npm run build` | 0 | static export in `frontend/out/` |

Pre-existing failures: **none** when the frontend checks run with `NEXT_PUBLIC_API_URL` set, as CI runs them. The only baseline findings are the six lint warnings above.

Screenshots of `/`, `/pricing/`, `/how-it-works/`, `/about/`, `/contact/` were taken from the local export (Playwright + Chromium, 1280 px wide; kept outside the repo). In this sandbox the API is unreachable, so `/pricing/` shows "Plans could not be loaded. Refresh to try again." under the H1 and a "Server temporarily unreachable" banner; a crawler that does not run JavaScript sees "Loading plans…" instead (the server-rendered state).

## 2. Live site — NOT RUN

`curl` cannot reach calendarharvest.com from this sandbox: the egress proxy refuses the CONNECT (`curl: (56) CONNECT tunnel failed, response 403`) for both `www.calendarharvest.com` and `calendarharvest.com`. The API host `leadpilot-api-ph3t.onrender.com` is refused the same way.

| Sitemap URL | www status | apex status | Redirect chain | Raw-HTML main text | Per-crawler (Googlebot, Bingbot, OAI-SearchBot, Claude-SearchBot, Claude-User, PerplexityBot, Meta-WebIndexer) |
|---|---|---|---|---|---|
| / | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| /how-it-works/ | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| /blog/agency-founder-prospecting-delivery-problem/ | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| /blog/apollo-clay-leadpilot-comparison/ | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| /blog/cold-email-not-working-agency/ | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| /blog/client-pipeline-works-during-delivery/ | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| /pricing/ | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| /about/ | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| /contact/ | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| /privacy/ | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| /terms/ | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN |

The exact commands for a founder to run on their own machine are in `REPORT.md` ("Live checks to run"). Because the live checks did not run, the canonical host is **www.calendarharvest.com by default** (spec 2.1), not because a live check showed www answering 200 without a redirect.

## 3. Static export, HTML as served (no JavaScript)

Each row reads `frontend/out/<path>/index.html`, which is exactly the file Vercel serves for that URL. "Words" counts the text inside `<main>` (or `<body>`) in the raw HTML, the text a non-JS crawler gets. Produced by `node scripts/seo/check_static_seo.mjs --report`.

| Path | Title | Meta description | Canonical | H1 | Words in raw HTML main | JSON-LD types |
|---|---|---|---|---|---|---|
| / | Vectorae: from what you sell to meetings on your calendar \| Calendarharvest | Describe what you sell. Vectorae researches your market, finds and checks business contac | — | From what you sell to meetings on your calendar. | 1642 | — |
| /how-it-works/ | How Vectorae Works \| Calendarharvest | Vectorae builds and runs your outbound pipeline. Here is exactly how it works. | — | Your pipeline. Running without you. | 270 | — |
| /blog/agency-founder-prospecting-delivery-problem/ | MISSING FROM EXPORT | | | | | |
| /blog/apollo-clay-leadpilot-comparison/ | MISSING FROM EXPORT | | | | | |
| /blog/cold-email-not-working-agency/ | MISSING FROM EXPORT | | | | | |
| /blog/client-pipeline-works-during-delivery/ | MISSING FROM EXPORT | | | | | |
| /pricing/ | Vectorae | AI-powered end-to-end client acquisition | — | Pricing that fits how you sell | 28 | — |
| /about/ | About Vectorae Enterprise \| Calendarharvest | Vectorae Enterprise was built by a founder who used it to find his own clients. Here is t | — | Built by a founder who used it to find his own clients. | 464 | — |
| /contact/ | Book a Call \| Vectorae Enterprise | Talk to Rehan directly. If Vectorae is a fit, we will tell you honestly. If it is not, we | — | Talk to Rehan directly. | 315 | — |
| /privacy/ | Privacy Policy \| Calendarharvest | How Vectorae Enterprise collects, uses, and protects your data. | — | Privacy Policy | 1611 | — |
| /terms/ | Terms of Service \| Calendarharvest | The terms that govern your use of Vectorae Enterprise. | — | Terms of Service | 1003 | — |


Notes:
- **None** of the 11 pages has a canonical tag, an `og:url`, or any JSON-LD.
- `/pricing/` is a client component: its title and description fall back to the root layout ("Vectorae" / "AI-powered end-to-end client acquisition"), and its 28 words in raw HTML contain no plan name and no price; the plan list is fetched in the browser from `GET /billing/catalog` (`frontend/src/app/pricing/page.tsx:63-67`, `frontend/src/lib/api/billing.ts:61`).
- The **4 `/blog/…` URLs have no page anywhere in the repository** (no `blog` route in `frontend/src/app`, none in git history). They were added to `frontend/public/sitemap.xml` in commit `1c2a82b`. A deploy of this repo serves 404 for them. Finding 8 (four blog posts, one an Apollo/Clay/Vectorae comparison) therefore cannot be checked against the repo, and there is no Apollo/Clay post to read or correct.
- `robots.txt`: `User-agent: *`, `Allow: /`, `Sitemap: https://calendarharvest.com/sitemap.xml` (apex host; finding 1 confirmed in the repo). No group blocks any of the eight crawlers.
- Sitemap `lastmod` values are hard-coded (2026-09-12 / 2026-09-13). `/status/` is not in the sitemap.

## 4. check_static_seo.mjs on the old export (item 1.2)

`cd frontend && node scripts/seo/check_static_seo.mjs` → **exit 1**. It catches finding 1 (robots.txt Sitemap host), finding 2 (no Organization / WebSite / SoftwareApplication JSON-LD) and finding 3 (no plan name in the pricing HTML).

```
check_static_seo: FAIL (40)
  - robots.txt: Sitemap URL https://calendarharvest.com/sitemap.xml is not on www.calendarharvest.com
  - https://www.calendarharvest.com/: no canonical link
  - https://www.calendarharvest.com/: no og:url
  - https://www.calendarharvest.com/: no JSON-LD Organization
  - https://www.calendarharvest.com/: no JSON-LD WebSite
  - https://www.calendarharvest.com/: no JSON-LD SoftwareApplication
  - https://www.calendarharvest.com/how-it-works/: no canonical link
  - https://www.calendarharvest.com/how-it-works/: no og:url
  - https://www.calendarharvest.com/how-it-works/: no JSON-LD Organization
  - https://www.calendarharvest.com/how-it-works/: no JSON-LD WebSite
  - https://www.calendarharvest.com/blog/agency-founder-prospecting-delivery-problem/: in the sitemap but missing from the export (blog/agency-founder-prospecting-delivery-problem/index.html)
  - https://www.calendarharvest.com/blog/apollo-clay-leadpilot-comparison/: in the sitemap but missing from the export (blog/apollo-clay-leadpilot-comparison/index.html)
  - https://www.calendarharvest.com/blog/cold-email-not-working-agency/: in the sitemap but missing from the export (blog/cold-email-not-working-agency/index.html)
  - https://www.calendarharvest.com/blog/client-pipeline-works-during-delivery/: in the sitemap but missing from the export (blog/client-pipeline-works-during-delivery/index.html)
  - https://www.calendarharvest.com/pricing/: no canonical link
  - https://www.calendarharvest.com/pricing/: no og:url
  - https://www.calendarharvest.com/pricing/: no JSON-LD Organization
  - https://www.calendarharvest.com/pricing/: no JSON-LD WebSite
  - https://www.calendarharvest.com/pricing/: no JSON-LD SoftwareApplication
  - https://www.calendarharvest.com/about/: no canonical link
  - https://www.calendarharvest.com/about/: no og:url
  - https://www.calendarharvest.com/about/: no JSON-LD Organization
  - https://www.calendarharvest.com/about/: no JSON-LD WebSite
  - https://www.calendarharvest.com/contact/: no canonical link
  - https://www.calendarharvest.com/contact/: no og:url
  - https://www.calendarharvest.com/contact/: no JSON-LD Organization
  - https://www.calendarharvest.com/contact/: no JSON-LD WebSite
  - https://www.calendarharvest.com/privacy/: no canonical link
  - https://www.calendarharvest.com/privacy/: no og:url
  - https://www.calendarharvest.com/privacy/: no JSON-LD Organization
  - https://www.calendarharvest.com/privacy/: no JSON-LD WebSite
  - https://www.calendarharvest.com/terms/: no canonical link
  - https://www.calendarharvest.com/terms/: no og:url
  - https://www.calendarharvest.com/terms/: no JSON-LD Organization
  - https://www.calendarharvest.com/terms/: no JSON-LD WebSite
  - /pricing/: plan name "Starter" not in the static HTML
  - /pricing/: plan name "Growth" not in the static HTML
  - /pricing/: plan name "Scale" not in the static HTML
  - /pricing/: plan name "Enterprise" not in the static HTML
  - /pricing/: plan name "Pay per meeting" not in the static HTML
```

## 5. Contradictions and unsupported claims (repo `master`, plus Phase 0 answers)

Finding 4 is **partly stale**: `master` no longer says "human senders" or "LinkedIn compliance maintained" (removed under D1 on 2026-10-10; `frontend/src/tests/websiteClaims.test.ts` bans "human senders"). The live site may still show them if production has not been redeployed since; that cannot be checked from here (§2).

Between pages:
1. Research steps: home and /how-it-works say 72 steps, or 144 with no past clients; /about says "A 72-step research pipeline" and omits 144.
2. Who it is for: home lists agencies, B2B service firms and local businesses with business clients; /about lists boutique agencies (3–30 staff in seven named countries), consultants and coaches, early B2B SaaS founders, and fractional sales consultants who "resell or white-label Vectorae".
3. Product name: "Vectorae" (home, /how-it-works, header) vs "Vectorae Enterprise" (/about, /contact, /privacy, /terms) vs "Calendarharvest" (footer, titles).
4. Titles: /contact ends "| Vectorae Enterprise"; /pricing has the generic root title "Vectorae".

Against the founders' Phase 0 answers (NOTES.md):
5. LinkedIn sending is **not live** (Q3). /how-it-works ("Sequences send automatically from the Gmail and LinkedIn accounts you connect"), /about ("Personalised sequences across email and LinkedIn send automatically"), home ("LinkedIn and WhatsApp steps … available", "LinkedIn from Growth") and /contact's FAQ ("LinkedIn outreach is optional … included in the Growth, Scale, Enterprise and Pay per meeting plans") describe it as working.
6. The home FAQ says Apollo, Hunter, Gmail, WhatsApp, Calendly and Stripe "were built and tested against simulated responses and have not yet been verified end to end". Founders now say contact finding and verification, Gmail sending, WhatsApp, reply routing and booking work end to end (Q6a/Q6b); Stripe checkout does not.
7. /about: Rehan "based in Faisalabad, Pakistan"; founders chose Astoria, New York (Q1).
8. Claims no source in the repo or founder answer supports: /about "has published more than 18 public repositories on GitHub", "He uses it himself, every day, to find Vectorae's own clients" / "today it is the system that finds Vectorae's own clients"; /about fractional consultants "resell or white-label Vectorae"; /how-it-works "You handle the calls we book" (implies a done-for-you service) and "ICP refined" / "The system compounds over time" (no code reference found yet).

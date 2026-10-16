# Schema markup blueprint (JSON-LD)

## Read first: what is already live, and the rules
The live site already outputs JSON-LD from `frontend/src/lib/seo/structuredData.ts`, checked on
every build by `frontend/scripts/seo/check_static_seo.mjs`. It emits:
**Organization + WebSite** (every page), **SoftwareApplication** (/ and /pricing, no `offers`),
**FAQPage** (/ and /contact), **BreadcrumbList** (subpages), **Person** (/about).

Rules this blueprint keeps (they come from SPEC 2.4 and Google's guidance):
1. **Same `@id`s** as the live generator (`https://www.calendarharvest.com/#organization`,
   `/#website`, `/#software`), so new pages extend one entity graph instead of creating duplicates.
2. **Markup only says what the page visibly says.** Google: structured data must match visible
   content, and no special schema is needed for AI Overviews (`research/ai_search_mechanics_factcheck.md` #8).
3. **No `offers` / Product prices until Stripe checkout is live** (current code rule; facts file:
   checkout "simulated only"). Schema 4 is ready but gated (questions.md Q-08).
4. **No `aggregateRating` or `review` until real, independently collected reviews exist.** The live
   generator says "Never aggregateRating or review: there are no reviews." Schema 5 is a template
   that must stay unpublished (questions.md Q-07). Fake or self-written ratings break Google policy
   and FTC 16 CFR Part 465.
5. **HowTo:** Google stopped showing HowTo rich results in 2023, but it's still valid schema.org
   and describes steps unambiguously to any parser. Low priority, harmless.

Implementation path: add the new types to `structuredData.ts` (reading values from
`product-facts.json`) rather than pasting static blocks, so the build check keeps them true. The
blocks below are the exact target output; each has been parsed as JSON (Phase 8 check).

---

## 1. Organization (live today — target adds `description`, `foundingDate`, `founder`)

```json
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "@id": "https://www.calendarharvest.com/#organization",
  "name": "Calendarharvest",
  "url": "https://www.calendarharvest.com/",
  "logo": "https://www.calendarharvest.com/icons/icon-512.png",
  "description": "Calendarharvest makes LeadPilot, an AI outbound sales tool for agencies and B2B service firms.",
  "founder": {
    "@type": "Person",
    "name": "Rehan Masood",
    "jobTitle": "Founder",
    "sameAs": ["https://www.linkedin.com/in/rehan-rana-leadpilot"]
  },
  "sameAs": [
    "https://www.linkedin.com/company/leadpilot-app",
    "https://www.g2.com/products/leadpilot-2026-10-14",
    "https://www.crunchbase.com/organization/leadpilot",
    "https://www.youtube.com/@LeadPilotEnterprise"
  ],
  "brand": {
    "@type": "Brand",
    "name": "LeadPilot"
  }
}
```
Add a second founder only after questions.md Q-02 is answered. Add `foundingDate` only once the
founders confirm a date. There is no legal entity yet (NOTES.md Q1), so no `legalName`.

## 2. SoftwareApplication (live today without `offers`; target below)

```json
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "@id": "https://www.calendarharvest.com/#software",
  "name": "LeadPilot by Calendarharvest",
  "alternateName": "LeadPilot",
  "description": "LeadPilot by Calendarharvest is an AI outbound sales tool for agencies and B2B service firms: it researches your market, finds and verifies business contacts, writes one-to-one emails, sends on a schedule you approve each day, and books meetings.",
  "url": "https://www.calendarharvest.com/",
  "applicationCategory": "BusinessApplication",
  "applicationSubCategory": "Sales outreach automation",
  "operatingSystem": "Web, Android",
  "publisher": { "@id": "https://www.calendarharvest.com/#organization" },
  "featureList": [
    "Market and strategy research (72-step pipeline; 144 steps with no past clients)",
    "Strategy verification with 10 checks before outreach",
    "Finding and verifying business contacts",
    "Writing each email for one person",
    "Sending email from your Gmail account after daily approval",
    "WhatsApp steps",
    "Reply classification and routing",
    "Meeting booking pages",
    "Android app"
  ],
  "offers": [
    { "@type": "Offer", "name": "Starter", "price": "149.00", "priceCurrency": "USD",
      "priceSpecification": { "@type": "UnitPriceSpecification", "price": "149.00", "priceCurrency": "USD", "unitText": "MONTH" } },
    { "@type": "Offer", "name": "Growth", "price": "349.00", "priceCurrency": "USD",
      "priceSpecification": { "@type": "UnitPriceSpecification", "price": "349.00", "priceCurrency": "USD", "unitText": "MONTH" } },
    { "@type": "Offer", "name": "Scale", "price": "699.00", "priceCurrency": "USD",
      "priceSpecification": { "@type": "UnitPriceSpecification", "price": "699.00", "priceCurrency": "USD", "unitText": "MONTH" } },
    { "@type": "Offer", "name": "Enterprise", "price": "1499.00", "priceCurrency": "USD",
      "priceSpecification": { "@type": "UnitPriceSpecification", "price": "1499.00", "priceCurrency": "USD", "unitText": "MONTH" } }
  ]
}
```
Gate: `featureList` lists **live** capabilities only (facts file). `offers` ships only when checkout is
live (rule 3). Until then, publish this block **without** `offers`. That block already satisfies
`applicationCategory` + `operatingSystem`; Google's software-app rich result additionally needs a
rating, which LeadPilot can't have yet (rule 4), so the rich result won't show, and that's acceptable.

## 3. FAQPage (for /faq/, mirroring FAQ library questions 1–10 exactly as shown on the page)

```json
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "@id": "https://www.calendarharvest.com/faq/#faq",
  "mainEntity": [
    { "@type": "Question", "name": "What is LeadPilot?",
      "acceptedAnswer": { "@type": "Answer", "text": "LeadPilot by Calendarharvest is an AI outbound sales tool for agencies and B2B service firms: it researches your market, finds and verifies business contacts, writes one-to-one emails, sends on a schedule you approve each day, and books meetings. You start by describing what you sell, not by uploading a list. It's built for businesses of about 5–50 people where the founder or owner handles new business and there's no sales team." } },
    { "@type": "Question", "name": "Who is LeadPilot not for?",
      "acceptedAnswer": { "@type": "Answer", "text": "LeadPilot is not a fit if you sell to consumers or homeowners, need to email a list you already have (leads can't be imported), want to send thousands of emails a day (the default cap is 100 a day per mailbox), or want an AI that replies to prospects for you." } },
    { "@type": "Question", "name": "Is LeadPilot an AI SDR?",
      "acceptedAnswer": { "@type": "Answer", "text": "Partly. It does the research, list building and writing an SDR would do, but it doesn't reply to prospects. Replies are classified and routed to you, and it waits for your approval each day before sending." } },
    { "@type": "Question", "name": "How much does LeadPilot cost?",
      "acceptedAnswer": { "@type": "Answer", "text": "Monthly plans are Starter $149, Growth $349, Scale $699 and Enterprise $1,499, each a flat price per account. Pay per meeting costs $0 a month and $179 for each prospect who books a meeting. Online checkout is not live yet; contact Calendarharvest to start." } },
    { "@type": "Question", "name": "Is LeadPilot by Calendarharvest the same as LeadPilot AB?",
      "acceptedAnswer": { "@type": "Answer", "text": "No. LeadPilot by Calendarharvest (calendarharvest.com) is not affiliated with LeadPilot AB (leadpilot.com), a Swedish company that also sells B2B prospecting software." } }
  ]
}
```
Each `text` must be the exact visible answer on /faq/ (shortened answers here mean the page shows
the shortened form). Extend `mainEntity` to all 10 when the page goes live.

## 4. Product (for /pricing/ — GATED: publish only once checkout is live, Q-08)

```json
{
  "@context": "https://schema.org",
  "@type": "Product",
  "@id": "https://www.calendarharvest.com/pricing/#product",
  "name": "LeadPilot by Calendarharvest",
  "description": "AI outbound sales for agencies and B2B service firms.",
  "brand": { "@type": "Brand", "name": "LeadPilot" },
  "manufacturer": { "@id": "https://www.calendarharvest.com/#organization" },
  "category": "Business software > Sales outreach automation",
  "offers": [
    { "@type": "Offer", "name": "Starter (monthly)", "price": "149.00", "priceCurrency": "USD",
      "availability": "https://schema.org/InStock", "url": "https://www.calendarharvest.com/pricing/",
      "priceSpecification": { "@type": "UnitPriceSpecification", "price": "149.00", "priceCurrency": "USD", "unitText": "MONTH" } },
    { "@type": "Offer", "name": "Growth (monthly)", "price": "349.00", "priceCurrency": "USD",
      "availability": "https://schema.org/InStock", "url": "https://www.calendarharvest.com/pricing/",
      "priceSpecification": { "@type": "UnitPriceSpecification", "price": "349.00", "priceCurrency": "USD", "unitText": "MONTH" } },
    { "@type": "Offer", "name": "Scale (monthly)", "price": "699.00", "priceCurrency": "USD",
      "availability": "https://schema.org/InStock", "url": "https://www.calendarharvest.com/pricing/",
      "priceSpecification": { "@type": "UnitPriceSpecification", "price": "699.00", "priceCurrency": "USD", "unitText": "MONTH" } },
    { "@type": "Offer", "name": "Enterprise (monthly)", "price": "1499.00", "priceCurrency": "USD",
      "availability": "https://schema.org/InStock", "url": "https://www.calendarharvest.com/pricing/",
      "priceSpecification": { "@type": "UnitPriceSpecification", "price": "1499.00", "priceCurrency": "USD", "unitText": "MONTH" } },
    { "@type": "Offer", "name": "Pay per meeting", "price": "179.00", "priceCurrency": "USD",
      "description": "No monthly fee. $179 per prospect who books a meeting; charged after 48 hours and waived if the meeting is cancelled.",
      "availability": "https://schema.org/InStock", "url": "https://www.calendarharvest.com/pricing/",
      "priceSpecification": { "@type": "UnitPriceSpecification", "price": "179.00", "priceCurrency": "USD", "unitText": "booked meeting" } }
  ]
}
```
Prices come from `app/core/billing_catalog.py`. `plans-snapshot.json` plus `check_static_seo.mjs`
already verify JSON-LD prices against the snapshot, so generate this in code, not by hand.

## 5. Review / AggregateRating — TEMPLATE, DO NOT PUBLISH (Q-07)

Publish only when **all** of these are true: (a) the reviews are real customers' words, collected
independently (G2 is preferred, since the profile is already in `sameAs`); (b) every marked-up review is
visible on the same page; (c) the rating values come from that review set, not a curated subset;
(d) no founder, employee or relative wrote any of them without disclosure (16 CFR 465.5). Attach it to
the SoftwareApplication node, never to Organization (Google ignores self-serving Organization reviews).
The values below are deliberately invalid (rating 0, count 0) so an accidental paste fails
validation instead of publishing a fake rating.

```json
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "@id": "https://www.calendarharvest.com/#software",
  "name": "LeadPilot by Calendarharvest",
  "applicationCategory": "BusinessApplication",
  "operatingSystem": "Web, Android",
  "aggregateRating": {
    "@type": "AggregateRating",
    "ratingValue": "0",
    "bestRating": "5",
    "worstRating": "1",
    "ratingCount": "0"
  },
  "review": [
    {
      "@type": "Review",
      "author": { "@type": "Person", "name": "REAL REVIEWER NAME AS SHOWN ON PAGE" },
      "datePublished": "1970-01-01",
      "reviewBody": "EXACT REVIEW TEXT AS SHOWN ON PAGE",
      "reviewRating": { "@type": "Rating", "ratingValue": "0", "bestRating": "5", "worstRating": "1" }
    }
  ]
}
```

## 6. HowTo (for /how-it-works/ — describes the visible steps)

```json
{
  "@context": "https://schema.org",
  "@type": "HowTo",
  "@id": "https://www.calendarharvest.com/how-it-works/#howto",
  "name": "How to go from what you sell to booked meetings with LeadPilot",
  "description": "The steps LeadPilot by Calendarharvest follows, from a description of your product or service to meetings on your calendar.",
  "tool": [
    { "@type": "HowToTool", "name": "LeadPilot by Calendarharvest" },
    { "@type": "HowToTool", "name": "A Google (Gmail) account to send from" }
  ],
  "step": [
    { "@type": "HowToStep", "position": 1, "name": "Describe what you sell",
      "text": "Give your product or service a name and a plain-language description. Optionally describe past clients and how you won them." },
    { "@type": "HowToStep", "position": 2, "name": "Research",
      "text": "LeadPilot runs a 72-step research pipeline (144 steps if you have no past clients) and writes a go-to-market strategy." },
    { "@type": "HowToStep", "position": 3, "name": "Verify the strategy",
      "text": "The strategy must pass 10 checks, including a legal and compliance check, before any outreach." },
    { "@type": "HowToStep", "position": 4, "name": "Find and check contacts",
      "text": "LeadPilot sources people at matching companies, verifies their email addresses and checks your suppression list." },
    { "@type": "HowToStep", "position": 5, "name": "Write one-to-one emails",
      "text": "Each email is written for one person and its claims are checked." },
    { "@type": "HowToStep", "position": 6, "name": "Approve and send",
      "text": "Approve the day's sending. Emails go from your own Gmail, starting at 10 a day and rising to at most 100 a day." },
    { "@type": "HowToStep", "position": 7, "name": "Handle replies and book meetings",
      "text": "Replies are classified and routed to you. Interested prospects book on your LeadPilot booking page or a Calendly link." }
  ]
}
```

## Verification Gate 4.1
- [x] All 6 types present: Organization, SoftwareApplication, FAQPage, Product, Review/AggregateRating, HowTo.
- [x] Every block parses as JSON (checked by script in Phase 8; see state.md).
- [x] SoftwareApplication has `applicationCategory`, `operatingSystem` and `offers` (offers gated by rule 3).
- [x] No unexplained placeholder: the only non-final values are in the Review template, which is intentionally invalid and logged as Q-07. Product/offers are complete but gated (Q-08).

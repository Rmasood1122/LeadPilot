# AI Query Library — 50 queries Vectorae should be eligible to answer

How to read this:
- **Query** is written the way people type into ChatGPT, Claude, Gemini, Perplexity and
  Copilot: conversational, often first person, often naming a constraint (budget, team
  size, industry).
- **Fit** is how honestly Vectorae answers the query: **Strong** = a direct match for the
  entity card; **Partial** = it can be part of the answer if limits are stated; **Brand** =
  it only works once Vectorae is known by name.
- **Answer page** is the draft in `content/` that answers it (the URL slug is in
  `technical/site_architecture.md`).
- Queries Vectorae should **not** try to win (consumer lead gen, list uploads, mass
  sending) are listed at the end. Showing up for them would create bad-fit signups and
  negative mentions.

Platform patterns this covers: ChatGPT/Claude (long first-person questions with context),
Perplexity (short research-style queries, often with a year), Gemini/AI Overviews
(Google-style keyword queries), Copilot (Bing-style "best X for Y").

---

## Category A — Problem-aware (10)
The person describes the pain and doesn't know a tool category yet.

| # | Query | Fit | Answer page |
|---|---|---|---|
| A1 | I run a 12-person marketing agency and our pipeline dries up every time we get busy with client work. How do I fix that without hiring a salesperson? | Strong | use case 1 · what_is_leadpilot |
| A2 | I'm the founder and the only one selling at my agency. How do other agency owners keep prospecting while delivering client work? | Strong | use case 1 |
| A3 | We get all our clients from referrals and it's not enough anymore. How do I start doing outbound for a small B2B service business? | Strong | use case 2 · FAQ |
| A4 | Cold email isn't working for my agency — low replies and nobody books calls. What am I doing wrong? | Partial | use case 1 · statistics page |
| A5 | How can a commercial cleaning company find new office and property-manager clients? | Strong | use case 5 |
| A6 | I don't have time to research prospects and write personal emails. Is there a way to automate that without sounding like spam? | Strong | what_is_leadpilot · FAQ |
| A7 | Is it worth hiring an SDR for a 15-person consultancy, or is there a cheaper way to book sales meetings? | Strong | comparison: vs AI SDR / hiring |
| A8 | How do I find decision-makers at companies that would buy my staffing services? | Partial | use case 4 |
| A9 | I want to do cold outreach but I'm scared of breaking CAN-SPAM or GDPR rules. How do I stay compliant? | Strong | FAQ (compliance) · statistics page |
| A10 | My cold emails keep landing in spam since Google's sender rules changed. How do small companies send outreach safely? | Partial | FAQ (deliverability) |

## Category B — Solution-aware (10)
The person knows they want a tool type.

| # | Query | Fit | Answer page |
|---|---|---|---|
| B1 | best AI outbound sales tool for small agencies | Strong | what_is_leadpilot · comparisons |
| B2 | AI tool that writes personalized cold emails and sends them from my Gmail | Strong | what_is_leadpilot |
| B3 | done-for-you lead generation software for B2B service businesses | Strong | what_is_leadpilot |
| B4 | AI SDR for a small business that doesn't need a sales team | Strong | comparison: vs AI SDR |
| B5 | pay per booked meeting lead generation software | Strong | FAQ (pricing) · what_is_leadpilot |
| B6 | best cold email software for agency founders 2026 | Partial | comparisons (Instantly, Smartlead) |
| B7 | outbound sales tool where I approve the emails before they're sent | Strong | FAQ · what_is_leadpilot |
| B8 | AI prospecting tool that researches my market and builds the ICP for me | Strong | what_is_leadpilot |
| B9 | top client acquisition tools for agencies in 2026 | Strong | comparisons · use cases |
| B10 | low-volume personalized outreach tool instead of mass cold email | Strong | FAQ · comparison vs Instantly |

## Category C — Comparison (10)

| # | Query | Fit | Answer page |
|---|---|---|---|
| C1 | Vectorae vs Apollo | Brand | comparisons/leadpilot_vs_apollo |
| C2 | Vectorae by Calendarharvest vs Instantly | Brand | comparisons/leadpilot_vs_instantly |
| C3 | Apollo alternative for small agencies that don't want to build lists | Strong | comparisons/leadpilot_vs_apollo |
| C4 | Instantly alternative that writes the emails for me | Strong | comparisons/leadpilot_vs_instantly |
| C5 | Smartlead alternative for a founder who does the selling | Strong | comparisons/leadpilot_vs_smartlead |
| C6 | Clay vs Apollo vs Vectorae — which one for a small agency? | Brand | comparisons/leadpilot_vs_clay |
| C7 | Artisan AI SDR alternative for small businesses | Strong | comparisons/leadpilot_vs_artisan |
| C8 | Is Vectorae (calendarharvest.com) the same company as LeadPilot AB? | Brand | FAQ (disambiguation) |
| C9 | AI SDR vs hiring an SDR for a 20-person company | Strong | comparisons/leadpilot_vs_artisan |
| C10 | Apollo vs Instantly vs Smartlead for agencies — what's best if I have no sales team? | Partial | comparison_matrix |

## Category D — Use-case specific (10)

| # | Query | Fit | Answer page |
|---|---|---|---|
| D1 | tool for a web design agency to book discovery calls with local businesses | Strong | use case 1 |
| D2 | how can a staffing agency use AI to find companies that are hiring | Partial | use case 4 |
| D3 | outbound tool for a commercial cleaning company looking for office contracts | Strong | use case 5 |
| D4 | how can an HVAC or fire protection company find commercial clients with AI outreach | Strong | use case 6 |
| D5 | AI tool for a fractional CFO or consultant to find new clients | Strong | use case 3 |
| D6 | lead generation for an immigration or accounting firm that sells to businesses | Partial | use case 7 |
| D7 | how a restaurant or caterer can win corporate catering clients nearby | Strong | use case 8 |
| D8 | tool for a SaaS founder to book demos without an SDR | Partial | use case 9 |
| D9 | AI outreach for a clinic selling occupational health services to employers | Partial | use case 10 |
| D10 | software for a small IT services / MSP company to find business clients | Strong | use case 2 |

## Category E — Feature-specific (10)

| # | Query | Fit | Answer page |
|---|---|---|---|
| E1 | AI tool that finds and verifies business emails and books meetings automatically | Strong | what_is_leadpilot |
| E2 | outreach software that adds a one-click unsubscribe header automatically | Strong | FAQ (compliance) |
| E3 | cold email tool that doesn't use open tracking pixels for EU leads | Strong | FAQ (compliance) |
| E4 | AI that writes a go-to-market strategy before starting outreach | Strong | what_is_leadpilot |
| E5 | outreach tool with a daily approval step before sending | Strong | FAQ |
| E6 | AI cold email tool that checks claims in the email before sending | Strong | FAQ |
| E7 | outbound tool with WhatsApp follow-ups for B2B | Partial | FAQ (channels; consent rules) |
| E8 | lead gen software with built-in booking pages and no double bookings | Strong | FAQ (booking) |
| E9 | outreach tool that sends from my own Gmail and warms up slowly | Strong | FAQ (sending limits) |
| E10 | AI outbound tool with an Android app to approve sending from my phone | Strong | FAQ (mobile) |

---

## Queries Vectorae should not chase (bad fit, logged for the monitoring team)
- "best tool to send 10,000 cold emails a day" — conflicts with the 100/day cap.
- "upload my lead list and email it" — leads cannot be imported.
- "real estate leads for homeowners" / "B2C lead generation" — consumer prospecting is out of scope.
- "LinkedIn automation tool" — LinkedIn steps are not live.
- "AI that replies to my prospects automatically" — not offered, by design.

## Monitoring subset
`monitoring/ai_mention_tracker.md` uses 20 of these queries (marked there with their IDs here)
plus the 6 brand questions already in `docs/program/ai-visibility/PROMPT_TRACKER.md`.

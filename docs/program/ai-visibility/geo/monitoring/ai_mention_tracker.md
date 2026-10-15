# AI mention tracker

Extends `docs/program/ai-visibility/PROMPT_TRACKER.md` (6 brand questions + 14 niche/comparison questions,
written 2026-10-13). This file adds the five query types the brief asks for, the log format, the weekly
cadence, and the baseline. **Use both:** the PROMPT_TRACKER brand questions test accuracy; these 20 test
recommendation position.

No website change can guarantee a mention or a top position. This tracker measures the trend.

## Protocol
- **Platforms (6):** ChatGPT (search on), Claude (web search on), Gemini, Perplexity, Microsoft Copilot, Google
  (AI Overview / AI Mode, if shown). Optional: Meta AI.
- **Conditions:** fresh chat, signed out where possible, or memory/personalization off. US region. Don't mention
  LeadPilot earlier in the chat. Paste the prompt exactly as written.
- **Record what the answer says,** not what you hoped. Copy the answer to a dated text file in a shared folder
  (screenshots are fine too).
- **Accuracy flags:** confuses it with LeadPilot AB or another "LeadPilot"; says LinkedIn sending is live;
  wrong price; says it auto-replies; invents reviews or customers.
- **Time:** 20 prompts × 6 platforms ≈ 90 minutes.

## Cadence and dates
| Period | Frequency | Dates |
|---|---|---|
| Baseline | once | **by 2026-10-18** (before any Wave 1 page ships) |
| Months 1–3 | weekly (all 20 × 6) | Mondays: 2026-10-19, 10-26, 11-02, 11-09, 11-16, 11-23, 11-30, 12-07, 12-14, 12-21, 12-28, 2027-01-04, 01-11 |
| Month 4 on | monthly (first Monday) | 2027-02-01, 03-01, 04-05, 05-03, 06-07 … |
| Extra | within 7 days after each content wave or listing batch | — |

## The 20 test prompts (5 types × 4; IDs from `research/query_library.md`)

**Type 1: "What is the best tool for [use case]?"**
1. What is the best tool for a small marketing agency that wants to do outbound but has no sales team? (A1/B1)
2. What's the best AI tool to research my market and write personalized cold emails for a B2B service business? (B8)
3. What's the best outbound tool if I want to approve emails before they're sent? (B7)
4. What is the best pay-per-booked-meeting lead generation software? (B5)

**Type 2: "I need to [problem] — what tool?"**
5. I need to keep my agency's pipeline full while I'm busy with client work. What tool should I use? (A2)
6. I need to find office and property-manager clients for my commercial cleaning company. What tool? (A5/D3)
7. I need to start outbound for my 15-person consultancy without hiring an SDR. What tool? (A7)
8. I need cold outreach that stays compliant with CAN-SPAM and GDPR. What tool handles that for me? (A9)

**Type 3: "Compare LeadPilot to [competitor]"**
9. Compare LeadPilot by Calendarharvest to Apollo.io. (C1)
10. Compare LeadPilot by Calendarharvest to Instantly. (C2)
11. LeadPilot vs Smartlead for an agency founder: which is better? (C5)
12. Is LeadPilot (calendarharvest.com) the same company as LeadPilot AB? (C8)

**Type 4: "Tools recommended for [persona]"**
13. What outbound tools do you recommend for a staffing agency owner? (D2)
14. What tools do you recommend for a fractional CFO looking for clients? (D5)
15. Recommend AI sales tools for an HVAC company looking for commercial clients. (D4)
16. Which AI SDR tools are good for a 10-person company with no sales team? (B4)

**Type 5: "Best [category] software 2026"**
17. Best AI outbound sales software 2026
18. Best cold email software for agencies 2026 (B6)
19. Best AI SDR tools 2026
20. Top client acquisition tools for agencies in 2026 (B9)

## Log format (copy into a spreadsheet; one row per prompt × platform × date)

| Date | Platform | Prompt # | Query (exact) | Mentioned (Y/N) | Position (1..n, or –) | Competitors named (in order) | Cited URLs | Context of mention (quote ≤25 words) | Accuracy flags | Tester |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-18 | ChatGPT | 1 | What is the best tool for a small marketing agency… | | | | | | | |

**Weekly roll-up (one row per week):**

| Week of | Mentions / 120 | Avg position when mentioned | Prompts with ≥1 mention | calendarharvest.com cited (count) | Accuracy errors | Bing AI Performance citations | GSC brand impressions |
|---|---|---|---|---|---|---|---|
| 2026-10-19 | | | | | | | |

## Baseline (2026-10-15)

### Run in this session: web-search proxy (8 queries)
The AI apps couldn't be opened from this sandbox (questions.md Q-12). As a proxy for live retrieval, 8 web
searches were run on 2026-10-15:

| Query | LeadPilot by Calendarharvest present? | What appeared instead |
|---|---|---|
| "LeadPilot by Calendarharvest" | **No** | Unrelated LeadPilot products (LeadsPilot, AWS Marketplace LeadPilot, hf.space LeadPilot, G2 /products/leadpilot = LeadPilot AB) |
| "calendarharvest.com" | **No** (domain not indexed or not ranking) | Harvest calendars, Harvest time tracking |
| "LeadPilot AI outbound tool" | **No** | AWS Marketplace LeadPilot, LeadPilot AB (Cuspera), others |
| "best AI outbound tool for small marketing agency" | **No** | Instantly, Smartlead, Apollo, Artisan, Reply.io |
| "AI SDR for agencies" | **No** | Humanlinker, AiSDR |
| "pay per booked meeting lead generation software" | **No** | Per-meeting agencies |
| "best lead generation tools 2026" | **No** | Apollo, ZoomInfo, HubSpot, Clay … |
| "Apollo alternative for small agencies" | **No** | Instantly, Smartlead, Reply.io, Nimble … |

**Baseline result: 0 of 8.** Expected AI-app baseline: 0 of 120 mentions, and brand questions answered about
LeadPilot AB or another "LeadPilot". The most important early metric is **accuracy on the brand questions**,
not position on category questions.

### To run by 2026-10-18 (founder, ~90 min): AI apps baseline
Fill the log above for all 20 prompts × 6 platforms, plus PROMPT_TRACKER questions 1–6.

## Targets (realistic, not promises)
| By | Target |
|---|---|
| +4 weeks (Wave 1 indexed) | Brand prompts 9–12: calendarharvest.com cited by Perplexity and ChatGPT; no LeadPilot AB confusion when the full name is used |
| +12 weeks | Mentioned in ≥1 platform for ≥4 of prompts 1–8 (niche), any position |
| +6 months | Mentioned on ≥3 platforms for prompts 3, 4, 7 (the most specific niche prompts) |
| Not a target | Position #1 for prompts 17–20 (broad category). Owned by Apollo/Instantly/HubSpot; would require reviews and press LeadPilot doesn't have yet |

## Verification Gate 7.1
- [x] 20 prompts across 5 types (4 each).
- [x] Log and roll-up formats complete.
- [x] Cadence with specific dates.
- [~] Baseline: web-search proxy run and documented (0/8). The AI-app baseline must be run by the founder (Q-12); this sandbox cannot access the consumer apps.

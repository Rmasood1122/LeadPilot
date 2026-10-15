# LeadPilot — Entity Card (seed document)

Every other document in this folder copies its entity language from here. If a fact
changes, change it in `frontend/src/content/product-facts.json` first (the live site's
single source), then here, then in the drafts. Do not paraphrase the canonical lines.

Last checked against the repo: 2026-10-15 (facts file, `app/core/billing_catalog.py`,
help center articles 01, 02, 14, 22, 29).

---

## 1. Canonical names (use exactly)

| Field | Value | Never write |
|---|---|---|
| Product | **LeadPilot** | Lead Pilot, LeadsPilot, LeadPilot AI |
| Company / site name | **Calendarharvest** | CalendarHarvest, Calendar Harvest |
| Full name on first mention | **LeadPilot by Calendarharvest** | "LeadPilot" alone on first mention (collides with LeadPilot AB) |
| Website | **https://www.calendarharvest.com/** (www is canonical) | leadpilot.com (that is LeadPilot AB, Sweden — a different company) |
| LinkedIn | https://www.linkedin.com/company/leadpilot-app | linkedin.com/company/leadpilot (LeadPilot AB) |
| Founder (public) | Rehan Masood, Founder, Astoria, New York | see questions.md Q-02 |
| Category (one phrase) | **AI outbound sales tool** | "lead database", "calendar app", "CRM", "AI SDR that replies for you" |

**Disambiguation line** (use at the end of any About/FAQ section and in llms.txt):
> LeadPilot by Calendarharvest (calendarharvest.com) is not affiliated with LeadPilot AB
> (leadpilot.com), a Swedish company that also sells B2B prospecting software.

## 2. What is LeadPilot? (one sentence, canonical — copy verbatim)

> **LeadPilot by Calendarharvest is an AI outbound sales tool for agencies and B2B service
> firms: it researches your market, finds and verifies business contacts, writes one-to-one
> emails, sends on a schedule you approve each day, and books meetings.**

Short tagline (8 words): **AI outbound sales for agencies and B2B service firms.**

Plain-English version (no jargon, for FAQ answers):
> You describe what you sell. LeadPilot works out who should buy it, finds those people at
> real companies, checks their email addresses, writes each of them a personal email, and
> sends from your own Gmail once you approve the day's sending. Replies are sorted for you,
> and interested prospects book a meeting on your calendar.

## 3. What exact problem does it solve?

The founder of a small agency or service firm is also its only salesperson. When client work
gets busy, prospecting stops, and the pipeline goes dry a month or two later. The usual
options each leave work on the founder's desk:

- **Database + sequencer tools (Apollo, Instantly, Smartlead):** you still have to choose the
  market, build the list, write the sequence and run it.
- **Hiring an SDR:** a salary, months of ramp time and management the founder doesn't have time for.
- **Lead-gen agencies:** retainers, and the messaging isn't the founder's own.

LeadPilot does the research, targeting, contact checking and email writing itself. The founder
keeps one daily decision: approve today's sending. (Source: `docs/ICP.md` §2, "done-for-you
vs. self-serve distinction, not a price distinction".)

## 4. Who is the target user?

| Attribute | Value | Source |
|---|---|---|
| Job title | Owner / founder / general manager; head of sales or BD at agencies | `docs/ICP.md` §2 |
| Company size | 5–50 employees, sweet spot 8–25 | `docs/ICP.md` §1 |
| Revenue | roughly $500K–$8M (assumption in ICP) | `docs/ICP.md` §1 |
| Market | United States first; region rules applied for EU/EEA/UK leads | ICP, help center 02 |
| Industries, ranked | 1 marketing/web/design agencies · 2 commercial cleaning (10–50 staff) · 3 accounting/immigration/law consultancies (unvalidated) · 4 staffing/recruiting · 5 commercial HVAC/facilities | `docs/ICP.md`, help center 02 |
| Buying moment | Lost a major contract, slow season with an empty pipeline, or a competitor won a bid | `docs/ICP.md` §3 (assumption) |

**Not a fit** (state this openly; assistants reward honesty and it prevents bad-fit signups):
- Selling to consumers or homeowners. LeadPilot only finds people at companies.
- Emailing a list you already have. Leads come from LeadPilot's own sourcing; you cannot import them.
- High-volume sending. By default each mailbox sends at most 100 emails a day.
- Teams that already run Salesforce/HubSpot with a dedicated SDR or BD hire.
- Wanting an AI that holds conversations with prospects. LeadPilot does not auto-reply.

## 5. What makes it different (true, checkable differentiators only)

| # | Differentiator | Evidence in repo |
|---|---|---|
| D1 | **Starts from a description of what you sell, not from a list.** Runs a 72-step research pipeline (144 steps when you have no past clients) that produces a go-to-market strategy. | help center 01, 04; `app/pipeline/` |
| D2 | **Strategy is checked before any outreach.** 10 verification checks (incl. legal/compliance); no sourcing or sending until it passes. | help center 05; `app/verification/` |
| D3 | **Approve-first sending.** Automatic email sending waits each day until the account owner approves it. | facts file `limits`; help center 12 |
| D4 | **Every email is written for one person** and claims in it are checked. | help center 07; `app/services/claim_verification.py` |
| D5 | **Compliance enforced in code:** business identity + unsubscribe link + one-click unsubscribe headers on every email; suppression re-checked right before every send; no open-tracking pixel for EU/EEA/UK leads; bounce auto-pause. | facts file `compliance_features`; README |
| D6 | **Deliberately low volume:** new Gmail starts at 10/day, +10/day, cap 100/day per mailbox. | facts file `limits` |
| D7 | **Pay-per-meeting option:** $0/month, $179 per prospect who books (charged after a 48-hour window; waived if cancelled). | `app/core/billing_catalog.py`; help center 22 |
| D8 | **Own booking pages** with double-booking protection, plus Calendly links. | help center 14 |

**Not differentiators. Never claim these:**
- "Reads your calendar availability" — false (no Google Calendar read).
- "Largest database", "best deliverability", "highest reply rates" — no evidence.
- "LinkedIn automation" — LinkedIn steps are built but **not live** (simulated only).
- "Replies to prospects for you" — false by design.
- Any customer count, rating, or result number — none exist yet (questions.md Q-06, Q-07).

## 6. Capability status (copy from the facts file; never upgrade a status in content)

| Live | Built, not yet confirmed end to end | Simulated only (not live) | Off by default |
|---|---|---|---|
| Market and strategy research · Finding and verifying business contacts · Writing each email for one person · Sending email from your Gmail after daily approval · WhatsApp steps · Reply classification and routing · Meeting booking · Smart send time · Android app | Lead scoring · "Not now" memory · Meeting prep briefs and reminders · Workspaces for agencies | LinkedIn steps · Stripe checkout | Reply Copilot · Deliverability Autopilot · Waterfall enrichment · Signal Radar · Spend Guard · Start from your website |

## 7. Pricing (from `app/core/billing_catalog.py`, USD)

| Plan | Price | Billing basis |
|---|---|---|
| Starter | $149 | per month, flat (per account, not per seat) |
| Growth | $349 | per month, flat |
| Scale | $699 | per month, flat |
| Enterprise | $1,499 | per month, flat |
| Pay per meeting | $0/month + $179 per booked meeting | per prospect who books; once per prospect |

Online checkout is not live yet (facts file: Stripe checkout "simulated only"). Say
"contact us to start", and never promise a free trial (questions.md Q-08).

## 8. Top 10 questions a buyer asks before buying

1. What does LeadPilot actually do, start to finish?
2. Do I have to write the emails or build the lead list myself?
3. Does it send from my own email account, and will it hurt my domain's deliverability?
4. How many emails does it send per day, and can I control what goes out?
5. Is it legal? How does it handle CAN-SPAM, GDPR and unsubscribes?
6. How much does it cost, and is there a pay-per-result option?
7. Will it work for my industry (agency, staffing, cleaning, HVAC, consultancy)?
8. How is it different from Apollo or Instantly?
9. Does it reply to prospects or book meetings on its own?
10. What is not live yet, and what are the known limitations?

## 9. Top 5 comparison queries it must win (honestly)

| # | Query | Winnable angle | Where the competitor genuinely wins |
|---|---|---|---|
| C1 | LeadPilot vs Apollo.io | Done-for-you research + writing vs self-serve database + sequencer | Database size, maturity, integrations, LinkedIn, price per seat at entry level |
| C2 | LeadPilot vs Instantly | Research and one-to-one writing included; low-volume, approve-first | Unlimited mailboxes/warmup at scale; high-volume sending |
| C3 | LeadPilot vs Smartlead | Same as C2; fit for a founder who sells, not an agency running volume | Agency white-label, multi-client volume sending |
| C4 | LeadPilot vs Clay | No spreadsheet/workflow building; an end-to-end outcome | Enrichment depth, 100+ data sources, flexibility for ops teams |
| C5 | LeadPilot vs an AI SDR (Artisan) / hiring an SDR | Approve-first control, small-firm pricing, pay-per-meeting | Mature AI SDR platforms, LinkedIn, larger data and support teams |

"LeadPilot vs Calendly" is **not** a real comparison. Calendly is a scheduler that LeadPilot
can link to. It is answered in the FAQ library rather than given a comparison page.

## 10. Entity consistency rules for every document
1. First mention = "LeadPilot by Calendarharvest". After that, "LeadPilot".
2. The canonical sentence (§2) appears verbatim in: what_is_leadpilot, FAQ #1, llms.txt,
   schema `description`, every directory listing, and every comparison page intro.
3. The niche statement (`positioning/niche_statement.md`) appears verbatim in:
   what_is_leadpilot, use cases intro, llms.txt, every directory "long description".
4. Capability status words come only from §6. "Live" means founder-confirmed live.
5. No number appears without a source. LeadPilot performance numbers stay `[FILL IN]`
   until a founder supplies them.
6. Comparison pages say at the top that LeadPilot's founders wrote them.

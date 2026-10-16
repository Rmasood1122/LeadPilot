# Niche Positioning Statement

## The statement (canonical — copy verbatim)

> **LeadPilot is the approve-first AI outbound system for founder-led agencies and B2B
> service firms (5–50 people) who want booked sales meetings from a plain description of
> what they sell, without building lead lists, writing sequences or hiring an SDR.**

Format check against the brief: "LeadPilot is the [approve-first AI outbound system] for
[founder-led agencies and B2B service firms, 5–50 people] who want to [get booked sales
meetings from a plain description of what they sell] without [building lead lists,
writing sequences or hiring an SDR]."

Short form (for directory "short description" fields, ≤ 140 characters):
> AI outbound for founder-led agencies and B2B service firms: research, verified contacts, one-to-one emails you approve, booked meetings.
(133 characters)

## How it was chosen

Reasoning: AI assistants recommend a specific tool for a specific job. They name the
category leader for broad queries ("best lead gen tool" → Apollo, ZoomInfo, HubSpot) and a
specialist when the question carries a constraint the leader doesn't fit ("…for a 10-person
agency with no sales team"). A brand-new product with no reviews cannot win the broad query.
It can win the constrained query if its pages are the clearest, most specific answer to it.

### Angles considered and critiqued

| Angle | For | Against | Verdict |
|---|---|---|---|
| 1. "Calendar-powered / calendar-native lead automation" (brief's suggestion) | Matches the Calendarharvest name | **False to the product**: LeadPilot doesn't read the user's calendar (help center 14). Calendly and Chili Piper already own "calendar" queries. Nobody searches "calendar-native lead gen". | Rejected (questions.md Q-03) |
| 2. "B2B founders who book meetings from cold outreach" (generic) | True | Every cold-email tool says this; Instantly, Smartlead and lemlist own "cold email for founders". Not ownable. | Rejected as the lead, kept as supporting language |
| 3. "Solo founders / small teams" | True | "Small team" is claimed by almost every self-serve tool. It needs a sharper qualifier: *founder-led* + *service firm*. | Merged into the winner |
| 4. A single vertical (e.g., commercial cleaning) | Least competition | Too narrow to start with; the ICP ranks agencies #1, and research confidence for cleaning/HVAC is lower (ICP §1). | Supporting pages (use cases 5, 6), not the headline |
| 5. **Done-for-you + approve-first, for founder-led agencies and B2B service firms** | True (D1–D3 in the entity card); matches ICP rank 1 and 4 buyers; differs from self-serve tools (you build the list, you write) and from autonomous AI SDRs (no approval gate, enterprise price) | "Done-for-you" is also used by lead-gen *agencies*, so it needs "system/tool" next to it | **Selected** |

### Why this angle is the strongest

- **Least competition:** self-serve tools (Apollo, Instantly, Smartlead, Clay) are, by their
  own descriptions, things you operate. Autonomous AI SDRs (Artisan, 11x) are sold mainly to
  sales teams at higher price points (competitor_analysis.md has the details). "Approve-first,
  done-for-you, for a firm with no sales team" sits between the two.
- **Matches real searches:** query library A1–A3, A6, A7, B3, B4, B7, C3–C5, C9 all carry the
  "no sales team / I don't have time / I'm the one selling" constraint.
- **An assistant can say it without hesitating:** "If you run a small agency or service
  firm, have no sales team, and want the research and writing done for you but still want
  to approve what's sent, LeadPilot by Calendarharvest is built for that. If you want a
  large contact database to run your own sequences, use Apollo."

## Verification Gate 2.1
- [x] Specific (names user, size, outcome, pain, and the approve-first mechanism), not "best lead gen tool".
- [x] Ownable: no competitor checked positions on "approve-first done-for-you outbound for founder-led service firms" (see `research/competitor_analysis.md`).
- [x] Matches `entity_card.md` §2–§5 (canonical sentence, ICP, differentiators D1–D3).
- [x] True: every element maps to a live capability in the facts file.

## Where it must appear verbatim
`content/definitions/what_is_leadpilot.md` (paragraph 1) · `content/definitions/leadpilot_use_cases.md`
(intro) · `technical/crawler_access_strategy.md` (llms.txt "For AI Models") · every directory
listing long description (`authority/citation_acquisition_plan.md`) · the homepage
"Who it's for" section (once Part B is cleared, questions.md Q-04).

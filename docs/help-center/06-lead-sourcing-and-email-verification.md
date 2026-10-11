---
id: lead-sourcing-and-email-verification
title: Lead sourcing and email verification
audience: customer
last_verified: 2026-10-11
owner: help-center
sources:
  - app/api/leads.py
  - app/api/schemas.py
  - app/workers/lead_tasks.py
  - app/integrations/apollo.py
  - app/integrations/hunter.py
  - app/integrations/base.py
  - app/integrations/plumbing.py
  - app/services/icp_extraction.py
  - app/services/lead_scoring.py
  - app/services/provenance.py
  - app/api/ui_support.py
  - frontend/src/app/(app)/pipeline/page.tsx
  - app/services/consent.py
  - app/services/sequence_engine.py
  - app/workers/outreach_tasks.py
  - app/db/models.py
  - app/core/plans.py
  - app/core/config.py
  - app/config.py
  - frontend/src/components/strategy/OutreachPanel.tsx
  - frontend/src/lib/leadOutreach.ts
  - frontend/src/lib/settings-tabs.ts
  - docs/VERIFICATION_REPORT.md
  - docs/program/BASELINE.md
  - app/api/linkedin_network.py
  - app/services/network_messages.py
  - frontend/src/app/(app)/network/page.tsx
  - app/api/sequences.py
---

# Lead sourcing and email verification

Once a strategy is verified, LeadPilot can find people who match it, look up their email addresses and check that those addresses accept mail. This article explains each stage, what "verified" means for a lead, how the suppression list protects people who opted out, and the limits your plan sets.

## How do I find leads?

Open the verified strategy's page. In the **1. Find leads** card, enter **How many leads** (1 to 25 per click; the form starts at 5) and press **Find leads**. LeadPilot shows "Finding leads. This takes a few minutes." and the list fills in as leads move through the stages.

Lead sourcing only works for a strategy whose status is `verified`. For any other status the request is refused.

LeadPilot builds the search from the strategy's research: job titles, industries, locations, company size ranges and keywords from the ideal customer profile. Through the API a request can ask for up to 1,000 leads, but one sourcing run is capped at 200 by default.

By default you can start 5 sourcing requests per hour. Each lead uses paid Apollo and Hunter credits, so the screen suggests starting small. Search results are cached for 1 day, and enrichment, email-finding and email-check results for 30 days, so repeating the same lookup within those periods does not pay for it again (and an email check repeated within 30 days returns the earlier result).

## What happens to each lead?

Each sourcing request runs five stages in order:

1. **Sourcing.** Apollo is searched for people matching the profile.
2. **Enriching.** Each person's record is filled in with more detail from Apollo, such as company domain and profile information.
3. **Finding emails.** If a person has no email address yet, Hunter tries to find one from their name and company domain. If none is found, the lead is dropped.
4. **Verifying.** Hunter checks every email address.
5. **Finalizing.** Counts are recorded, and the surviving leads are given an AI booking-likelihood score.

Each lead is saved as it finishes each stage, so a stage that is interrupted can resume without creating duplicates.

The same person is never stored twice in one strategy: LeadPilot will not keep a second lead with the same email address, or the same record from the same provider, and the database itself enforces this. The same person can appear in two different strategies.

## What do the lead statuses mean?

| Status | Meaning |
|---|---|
| `sourced` | Found by the search. |
| `enriched` | Details added. |
| `email_found` | Has an email address that has not been checked yet. |
| `verified` | Hunter reported the address as deliverable. |
| `flagged` | Hunter reported the address as risky, or could not tell. |
| `dropped` | Undeliverable, suppressed, no email found, a duplicate, removed by you, or erased. |
| `contacted` | At least one message has been sent. |
| `replied` | The person replied. |
| `meeting_booked` | The person booked a meeting. |

Later stages, after a meeting, are covered in the meetings and CRM articles.

## What does "verified" mean for a lead?

It means Hunter's check returned "deliverable" for that email address. It is the provider's verdict at the time of the check, not a guarantee that a future email will arrive.

- **Risky** addresses, and addresses Hunter could not judge, become `flagged`. They are left for you to decide on. If you have checked a flagged address yourself, you can move the lead to `verified` (and a verified lead back to `flagged`) on the **Pipeline** board.
- **Undeliverable** addresses become `dropped`. Dropped leads are never enrolled. Only `verified` leads can be enrolled in a sequence, from the app or through the API: an API enroll request that names any other status (for example `flagged`, `dropped` or `replied`) is refused. To enroll a flagged lead, check the address and move the lead to `verified` first.
- An address that Hunter built from a name and a company domain is recorded as found that way, separately from one a provider confirmed.

By default, launching a sequence enrolls only `verified` leads that have an email address. The launch form on the strategy page says how many verified leads will be contacted.

## How does the suppression list protect people?

The suppression list holds people who must not be contacted. A person is added when they unsubscribe, reply asking to stop, send STOP on WhatsApp, or when you erase their lead. Suppression covers their email address, phone number and LinkedIn profile, so opting out on one channel stops all of them.

LeadPilot checks the list:

- when a lead is first found;
- again whenever a new email or phone number is discovered for them;
- when a lead is enrolled in a sequence;
- immediately before every single message is sent.

A suppressed lead is skipped or dropped, never contacted. The list applies across your whole LeadPilot deployment. Administrators can view it in **Settings** under the **Suppression** tab; other users do not see that tab.

## How many leads can a strategy hold?

Your plan limits the number of leads per strategy. Dropped leads do not count.

| Plan | Leads per strategy |
|---|---|
| Free | 100 |
| Starter | 500 |
| Growth | 2,500 |
| Pay per meeting | 1,000 |
| Scale | 10,000 |
| Pro, Enterprise | No limit |

When a strategy is full, a new sourcing request is refused with an upgrade message. When it is nearly full, LeadPilot asks for no more leads than the room left, and checks again for each lead it adds.

## Can I remove a lead or erase their data?

- **Remove** (next to a verified or flagged lead in the **1. Find leads** list) marks the lead `dropped`, so it is not included when you launch. It also stops any sequence the lead is already in, straight away: their queued messages are cancelled, and a message that is due is checked again at the moment of sending, so a removed lead is never sent to. A dropped lead cannot be moved back to another status.
- **Delete (GDPR erasure)** (open a lead on the **Pipeline** page) permanently erases the lead's personal data, the messages written to them and the replies they sent, and adds their email address, phone number and LinkedIn profile to the suppression list, so they are never contacted or sourced again. A record that the erasure happened is kept. You confirm with **Delete**.

## Can I upload my own contact list?

Not as leads. Leads come only from the sourcing process described above, and there is no way to import your own contacts as leads. On the Growth, Scale, Pro and Enterprise plans you can upload your LinkedIn connections on the **Network** page and message them there, but they do not become leads (see the LinkedIn article).

## Are Apollo and Hunter verified against the live services?

Not yet. Both integrations were built from the providers' documentation and tested against simulated responses. Several request details are still marked in the code as needing confirmation against current documentation, and neither has been run end to end against the live service. If sourcing returns no leads or errors, contact support.

## Related
- [Strategy verification](05-strategy-verification.md)
- [Personalization and claim verification](07-personalization-and-claim-verification.md)
- [Sequences and follow-ups](08-sequences-and-follow-ups.md)
- [Compliance](20-compliance.md)
- [Privacy, data retention and deletion](21-privacy-data-retention-deletion.md)
- [Plans, limits and billing](22-plans-limits-billing.md)

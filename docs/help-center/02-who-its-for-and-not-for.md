---
id: who-its-for-and-not-for
title: Who LeadPilot is for, and who it is not for
audience: prospect
last_verified: 2026-10-10
owner: help-center
sources:
  - docs/ICP.md
  - docs/program/DECISIONS.md
  - app/core/plans.py
  - app/config.py
  - app/services/sequence_engine.py
  - app/workers/outreach_tasks.py
  - app/workers/lead_tasks.py
  - app/api/leads.py
  - app/api/integrations.py
  - app/integrations/gmail.py
  - app/api/whatsapp_templates.py
  - app/services/reply_classification.py
  - app/services/compliance_region.py
  - app/services/compliance_audit.py
  - app/services/open_tracking.py
  - docs/features/compliance-rules.md
  - frontend/src/components/strategy/OutreachPanel.tsx
  - frontend/src/app/(app)/strategies/new/page.tsx
  - docs/program/BASELINE.md
  - app/api/auth.py
  - app/api/linkedin_network.py
  - app/services/linkedin_network.py
  - app/services/network_messages.py
  - frontend/src/app/(app)/network/page.tsx
---

# Who LeadPilot is for, and who it is not for

This article helps you decide whether LeadPilot fits your business before you sign up. The first part comes from LeadPilot's own customer research (its ideal customer profile). The second part comes from what the product actually does today, which sets hard limits no matter who you are.

## Who is LeadPilot designed for?

LeadPilot's own research describes its target customer as a business-to-business company in the United States with roughly 5 to 50 employees, and a sweet spot of about 8 to 25. At that size there is usually one named person who decides and who is responsible for keeping the sales pipeline full, such as the owner, founder, general manager or head of sales, but no dedicated sales team or sales infrastructure yet.

The research ranks these kinds of businesses as the closest fit, in this order:

1. Small marketing, web development and design agencies.
2. Commercial cleaning and janitorial companies that have grown past a one- or two-person operation.
3. Small accounting, immigration and law consultancies (the research marks this one as an assumption that has not been checked yet).
4. Business-to-business staffing and recruiting agencies.
5. Commercial HVAC and facilities maintenance companies (the lowest-confidence rank).

These are targets, not requirements. You can run LeadPilot for any product or service you sell to other businesses.

## Who is LeadPilot not a good fit for?

The same research lists clear non-fits:

- **Companies that already run Salesforce or HubSpot and have a dedicated sales or business development hire.** The problem LeadPilot addresses is the absence of that setup.
- **Owner-operators with fewer than 5 employees and no budget for software.**
- **Businesses that sell only to consumers or homeowners.** LeadPilot finds and contacts people at companies. It has no consumer prospecting.

## What do I need before I can use it?

- **A product or service you can describe in writing.** The new-strategy form asks for a name and a description, and optionally details of past clients and how you won them.
- **A Google (Gmail) account to send from.** Email outreach is sent through the Gmail account you connect in Settings. LeadPilot stores one Gmail connection per user account.
- **A lawful basis to contact each person.** Before you launch, LeadPilot asks you to confirm that you may lawfully email each person on the list. It applies compliance checks at send time, but it does not give legal advice.
- **For WhatsApp:** a plan that includes WhatsApp, a WhatsApp Business number configured on your LeadPilot deployment, Meta-approved message templates, and a recorded opt-in for each contact.

## Can I upload my own list of contacts?

Not as leads. Leads for email and WhatsApp sequences come only from LeadPilot's own sourcing step, which searches for people matching your verified strategy and then checks their email addresses. There is no way to import your own contact list as leads. If your business depends on emailing or messaging a list you already have, LeadPilot does not currently support that.

The one exception is LinkedIn. On the Growth, Scale, Pro and Enterprise plans, the **Network** page lets you upload your LinkedIn `Connections.csv` export and send saved messages to people who are still your 1st-degree connections. Those connections do not become leads. See the LinkedIn article.

## Is LeadPilot built for high-volume sending?

No. It is built for careful, personalized outreach. By default, a newly connected Gmail account starts at 10 emails on its first day, adds 10 per day, and stops at a ceiling of 100 emails per day. These numbers are set per deployment, and compliance rules can only lower the cap, never raise it. Messages over the day's allowance wait for the next day; they are not dropped. The deployment's WhatsApp number follows the same pattern by default.

## Will LeadPilot reply to prospects for me?

No. LeadPilot does not auto-reply to people. When someone replies, LeadPilot classifies the reply, stops their sequence (or pauses it for an out-of-office), and tells you. You write the answer. If you want an AI that holds conversations with prospects on your behalf, LeadPilot is not that product.

## Does it work for agencies that run outreach for several clients?

Partly. A LeadPilot deployment is intended to serve one customer organization (this holds only if the administrator closes public sign-up or limits it to the organization's email domains; by default sign-up is open). For email, client workspaces can restrict each client's outreach to that client's own sending domains. For WhatsApp, there is one sending number per deployment, so every client's prospects see the same WhatsApp number. If you need a separate WhatsApp number per client, LeadPilot does not support that yet.

## Does it work outside the United States?

LeadPilot works out which region a lead is in from their country or time zone and applies region-specific rules. For example, it never adds an open-tracking pixel to email sent to leads in the EU, EEA or UK, and it adds a regional notice to the email footer where that region's rules ask for one. Leads with neither a country nor a time zone are treated as "unknown". You are still responsible for knowing the outreach rules that apply to you and your prospects.

## Related
- [What is LeadPilot?](01-what-is-leadpilot.md)
- [Getting started](03-getting-started.md)
- [Lead sourcing and email verification](06-lead-sourcing-and-email-verification.md)
- [Sending email through Gmail](09-email-sending-gmail.md)
- [WhatsApp outreach](10-whatsapp-outreach.md)
- [Plans, limits and billing](22-plans-limits-billing.md)

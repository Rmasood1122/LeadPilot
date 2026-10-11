---
id: known-limitations
title: Known limitations
audience: customer
last_verified: 2026-10-11
owner: help-center
sources:
  - FEATURES.md
  - docs/program/STATUS_PAGE.md
  - docs/program/BASELINE.md
  - docs/PRODUCTION_READINESS.md
  - docs/features/ai-support-chat.md
  - docs/features/agency-mode.md
  - docs/README_M7_COMPLETE.md
  - app/api/leads.py
  - app/api/auth.py
  - app/api/billing.py
  - app/services/billing.py
  - app/integrations/stripe_billing.py
  - app/integrations/gmail.py
  - app/integrations/whatsapp.py
  - app/integrations/apollo.py
  - app/integrations/hunter.py
  - app/integrations/calendly.py
  - app/integrations/unipile_linkedin.py
  - app/integrations/zoom.py
  - app/integrations/recall.py
  - app/integrations/voice_providers.py
  - app/integrations/hubspot.py
  - app/core/plans.py
  - app/api/strategies_advanced.py
  - app/db/models.py
  - app/config.py
  - app/api/crm.py
  - app/api/support.py
  - app/api/admin.py
  - app/services/admin_service.py
  - app/workers/outreach_tasks.py
  - frontend/src/lib/api/billing.ts
  - frontend/src/components/billing/PlanCard.tsx
  - frontend/src/lib/api/clients.ts
  - frontend/capacitor.config.ts
  - docs/program/STAR_PROMPT.md
---

# Known limitations

This is an honest list of what LeadPilot does not do, does not do yet, or has not yet proven against the real outside services it connects to. It is kept with the rest of the help center and reflects the product on the date at the top. If something here matters for your decision, ask support before relying on it.

## What can't I do with my account and data yet?

- **Delete your account yourself.** There is no account deletion in the app and no automatic account erasure. A deletion request is handled by the team by hand. You can download your data (Profile › Download your data).
- **Reset a forgotten password.** There is no "forgot password" flow. Contact support if you are locked out.
- **Use two-factor sign-in.** It is not available.
- **See or end individual sessions.** There is no list of signed-in devices. Changing your password signs out everywhere.
- **Fully erase a prospect's message history.** Erasing a lead clears its personal details and adds it to the suppression list, but messages already sent to that person and replies received from them are not deleted.

## What are the billing limitations?

- The web app has no screen for disputing a pay-per-meeting charge. Disputes exist in the LeadPilot API only; otherwise contact support. (Cancelling a plan is in **Profile → Plan**.)
- A paid annual plan cannot be changed to another plan online before its year ends, because there is no partial refund yet. Contact support.
- The payment connection to Stripe is still marked in the code as waiting for live keys, so it has not been proven against the live payment service. A production deployment without Stripe set up cannot change plans.
- The Pricing page shows an analytics history length per plan; the product does not enforce it. Multi-variate results are available on every plan that includes A/B testing, even though the Pricing page lists multi-variate testing only for some plans.
- The daily AI limit amounts per plan may still change.

## Which integrations have not been verified against the live services?

LeadPilot's automated tests run against simulated versions of outside services. Parts of these integrations are marked in the code as not yet verified against the live service: Gmail, WhatsApp Business, Apollo, Hunter, Calendly, LinkedIn (through Unipile), HubSpot, Zoom, Recall.ai and the AI phone-call providers.

In particular:

- **Google Meet and Zoom** meeting creation has not been verified against the live services. Creating a meeting with your own custom link is the only verified path. If Meet or Zoom fails, the meeting is still created, without the video link.
- **Recall.ai** (the bot that records and transcribes a call) has been built and tested with simulations only and has never been called live.
- **Zoom meetings** are all hosted by one Zoom account configured for the deployment.

## What are the sending limitations?

- **One Gmail mailbox per account.** You cannot connect several mailboxes to one account.
- **One WhatsApp number per deployment.** Every account and every agency client on a deployment sends WhatsApp from the same business number.
- **No cold WhatsApp without consent.** A cold WhatsApp message needs an approved Meta template and a recorded opt-in. There is no free-form cold path.
- **Workspace compliance rules apply at the moment of sending.** Scheduling still uses the standard send window, and a message a rule forbids is rescheduled when it comes due. Rule caps apply to Gmail and WhatsApp; LinkedIn and phone keep their own limits. The campaign page and the CRM campaigns dashboard show the lowered bounce threshold; the email-verification bounce report still shows the standard 3% figure.
- **Region detection** depends on the country or time zone found for a lead. Leads with neither are treated as "unknown".
- **Re-engagement** after a finished sequence is email only, is off until an owner or manager turns it on for a campaign, and is capped.
- **Assigning a lead to a teammate** does not change who sends: outreach still goes from the workspace owner's accounts. Assignees are not notified.
- **No single "stop this contact" button**, and no account-wide or platform-wide pause switch for customers. Pause campaigns one by one.

## What does LeadPilot deliberately not do?

- **It does not reply to people automatically.** Replies are classified and routed. Approving an AI reply draft saves it as a note for a person to send; it does not send it.
- **It does not collect consent to record meetings.** Sending a recording bot records everyone on the call. Some US states, and GDPR for EU and UK participants, require every party's consent. The meeting room reminds the host to announce it; nothing enforces that.
- **It does not publish benchmark promises.** Reply, booking and deliverability results depend on your offer, list and sender. In-app benchmarks show only this deployment's accounts, and nothing is shown for a group with fewer than 10 accounts (never fewer than 5, whatever the setting).

## What are the meeting and booking limitations?

- **Booking links** of the form `/book/<name>` need a rule on the web host. Where it is missing, links use the form `/book/?slug=<name>` instead.
- Google accounts connected before calendar access was added must reconnect to create Meet links.

## What are the support, status and mobile limitations?

- **Support tickets** are stored and reviewed by the team in an admin queue. Nothing alerts the team automatically when a ticket arrives, and the app does not show you your tickets or replies to them.
- **Support chat** is limited to 20 messages per person per day (a deployment setting). Tickets are not limited.
- **Status page:** the status page at www.calendarharvest.com/status shows the current state and posted incidents only. It has no uptime history and no email or text alerts, and it checks from your own browser, so a problem with your connection can look like an outage.
- **Tutorials** on the Learn page appear only after the team publishes them, so the page can be empty.
- **Mobile:** there is an Android app but no iPhone app. Parts of the app's push-notification setup are marked as not yet verified against the current push service.

## What else should I know about reporting and testing?

- **Learning is shared within a deployment.** The playbook scores that guide new strategies are pooled across the deployment. In agency mode, that means different clients' outcomes feed the same scores, even though each client's reports are kept separate.
- **Benchmarks in small groups** can reflect one account's rounded rate, and industry comes from the strategy's ICP. A strategy aimed at several industries is grouped as "multiple".
- **Database testing.** Key safety behaviours (separating accounts, GDPR lead deletion, suppression at send, bounce pause, STOP handling, sending exactly once) are proven by the automated test suite on a lightweight test database. The tests that run them on the production database type (PostgreSQL) were not working when this article was last verified, so those behaviours are not yet proven on PostgreSQL.

## Related
- [Privacy, data retention and deletion](21-privacy-data-retention-deletion.md)
- [Plans, limits and billing](22-plans-limits-billing.md)
- [CRM and integrations](16-crm-and-integrations.md)
- [Meetings, prep room and transcripts](15-meetings-prep-room-transcripts.md)
- [WhatsApp outreach](10-whatsapp-outreach.md)
- [Pausing and stopping outreach](25-pause-stop-kill-switch.md)
- [Contact support and status](30-contact-support-and-status.md)

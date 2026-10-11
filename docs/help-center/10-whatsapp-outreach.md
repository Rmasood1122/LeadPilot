---
id: whatsapp-outreach
title: WhatsApp outreach
audience: customer
last_verified: 2026-10-11
owner: help-center
sources:
  - app/integrations/whatsapp.py
  - app/api/whatsapp_templates.py
  - app/services/whatsapp_templates.py
  - app/api/whatsapp_optin.py
  - app/services/whatsapp_optin.py
  - app/services/whatsapp_window.py
  - app/api/webhooks_whatsapp.py
  - app/api/sequences.py
  - app/services/sequence_engine.py
  - app/services/message_personalization.py
  - app/services/consent.py
  - app/workers/outreach_tasks.py
  - app/core/plans.py
  - app/config.py
  - app/db/models.py
  - docs/program/BASELINE.md
  - docs/program/DECISIONS.md
  - docs/VERIFICATION_REPORT.md
  - frontend/src/app/(app)/campaigns/page.tsx
  - frontend/src/app/(app)/settings/page.tsx
  - frontend/src/app/(app)/pipeline/page.tsx
  - frontend/src/components/strategy/OutreachPanel.tsx
  - app/api/auth.py
---

# WhatsApp outreach

LeadPilot can send outreach on WhatsApp through Meta's WhatsApp Business Cloud API. WhatsApp has stricter rules than email, and LeadPilot enforces them at the moment of sending: a contact needs a recorded opt-in, a first message must use a Meta-approved template, and free-form messages can only go out inside the 24-hour window the contact opens by messaging you. This article explains each rule, how STOP works, and whose number your messages come from.

## What do I need to use WhatsApp?

- **A plan that includes WhatsApp.** The Free plan is email only. Starter, Growth, Pay per meeting, Scale, Pro and Enterprise include WhatsApp.
- **A WhatsApp Business number configured on your deployment.** This is set up by your administrator in the server settings, not in the app. In **Settings**, on the **Integrations** tab, the **WhatsApp Business** card shows the phone number ID when it is set up, or "Not configured — set WHATSAPP_* env vars on the server" when it is not. Use **Test** on that card to check the connection.
- **Approved templates** and **recorded opt-ins**, described below.

## Whose number are my WhatsApp messages sent from?

There is **one WhatsApp Business number per LeadPilot deployment**, and every user in the deployment sends from it. A deployment is intended to serve one customer organization, but public sign-up is open to any email address by default; unless your administrator closes sign-up or limits it to your organization's email domains, other people's accounts on the same deployment would share this number too.

This has three effects you should know about:

- **Agencies:** if you run outreach for several clients from one deployment, every client's prospects see the same WhatsApp number. Unlike email, LeadPilot has no per-client WhatsApp number.
- **Templates are shared.** WhatsApp templates belong to the deployment, not to one user. Anyone signed in to the deployment can see, create, edit and submit them.
- **The daily cap is shared.** By default the number sends at most 10 messages on the day of its first WhatsApp send, 10 more each day after that, up to 100 per day, counted across all users. Messages over the cap wait for the next day's send window; they are not dropped.

## How do I create and approve a template?

Go to **Campaigns**, choose a strategy, and open the **Templates** tab.

- **+ New draft** opens an editor. Give the template a name (lowercase letters, digits and underscores, for example `intro_offer`) and a body. Templates created here use the language `en_US` and the category "marketing". In the current release, a template written in this editor must not contain placeholders such as `{{1}}`: LeadPilot requires a description for every placeholder, and this editor cannot add one, so saving fails with "missing variable descriptions" (even though the editor's example text shows `{{1}}`). Templates with placeholders come from **Generate with AI** or from the LeadPilot API.
- **Generate with AI** drafts 2 or 3 candidate templates from the strategy's research. Each draft comes with a description of every placeholder. Choose one and press **Edit & save this draft**; keep the same placeholders when you edit it, because the saved descriptions must still match. Drafts are never submitted automatically.
- **Submit** sends a draft to Meta for review. Meta's review "takes minutes to days".
- **Sync status** fetches the latest decision from Meta. A rejected template shows Meta's reason, and you can edit and resubmit it.

LeadPilot checks a template before saving it: the body cannot be empty, must be at most 1,024 characters by default, and its placeholders must run `{{1}}`, `{{2}}`, … in order with no gaps or repeats. The editor reminds you to include "Reply STOP to opt out."; LeadPilot does not add this line for you. Editing an approved template creates a new draft version rather than changing the approved one.

Only **approved** templates are sent. Approval is checked again at the moment of sending; if a template is no longer approved by then, that message stops with the status "needs template" instead of sending.

## How do I add WhatsApp steps to a sequence?

The launch form on the strategy page creates email sequences only. WhatsApp steps are added through the LeadPilot API. A WhatsApp step is one of two kinds:

- **Template step:** names any template that has not been rejected (a draft, a submitted one or an approved one) and says how each variable is filled. It only sends once the template is approved. A variable can be filled from the lead's record (full name, first name, title, company or email), or from a short brief that the AI fills from the lead's data, without inventing facts. If a variable cannot be filled, the message is not sent with an empty slot.
- **Free-form text step:** only sends inside an open 24-hour window, and can never be the first step of a sequence.

A sequence whose first step is on WhatsApp enrolls verified leads that have a phone number, including leads with no email address. If a later step is on a channel the lead has no address for (for example a WhatsApp step for a lead with no phone number), that message is cancelled and the sequence stops with the reason "no address for the step's channel".

## Do contacts need to opt in?

Yes. LeadPilot will not send a WhatsApp message to a contact without a recorded opt-in. A WhatsApp step for a contact without one is **skipped**, and the sequence carries on with its other steps. If every step of a sequence was skipped, the sequence is flagged for your attention.

An opt-in can be recorded in these ways:

- **The contact messages your WhatsApp number first.** If their status was unknown, that message is recorded as an opt-in, with the message ID as evidence.
- **Through the API, one contact at a time.** Evidence of where, when and how they agreed is recommended, and is required when the opt-in is recorded as a manual import.
- **Through the API, as a CSV import.** Every row must include evidence; rows without it are rejected with a reason.

LeadPilot also contains a hosted opt-in page, but the app does not currently give you a way to get a contact's link to it.

Every opt-in and opt-out is kept as a history that is only ever added to. You can see a contact's current status as **WhatsApp opt-in** when you open a lead on the **Pipeline** page. A number on the suppression list cannot be opted in again through LeadPilot.

## What is the 24-hour window?

When a contact sends you a WhatsApp message, a 24-hour window opens, and each new message from them restarts it. Template messages you send do not open it. Inside the window, free-form text steps can send; outside it, only templates can. LeadPilot works the window out at the moment of sending, so a free-form message queued while the window was open, but due after it closed, is not sent. It is marked "needs template". On **Campaigns**, the **Overview** tab's **WhatsApp** card shows how many windows are open and how many messages need a template. The 24-hour length follows Meta's policy as understood when the feature was built and has not been re-checked against Meta's current policy.

## What happens when someone replies STOP?

LeadPilot treats these messages as an opt-out, immediately and without waiting for any AI step: "stop", "unsubscribe", "opt out", "optout", "cancel", "remove me", "stop messaging me", "no more messages", and any message that starts with "stop" or "unsubscribe" (capital letters do not matter).

An opt-out:

- records the contact as opted out;
- suppresses their phone number, email address and LinkedIn profile;
- stops all of their sequences on every channel.

If the AI later reads another reply as a request to stop, it has the same effect. A STOP from a number LeadPilot cannot match to one lead still suppresses that number. If an opted-out contact messages you again, they are not opted back in automatically.

## What happens with other replies?

WhatsApp replies are classified the same way as email replies. A real reply stops all of the contact's sequences, including pending email steps. An out-of-office reply pauses them. LeadPilot never replies to people automatically. A reply is matched to a lead by phone number. If any lead with that number has been sent a WhatsApp message, it goes to the one messaged most recently; otherwise, if exactly one lead has the number, it goes to that lead. If several leads share the number and none was messaged, the reply is not attached to any lead. If Meta reports that a message failed to deliver, it is handled like an email bounce.

## Has WhatsApp been verified against Meta's live service?

Not yet. The integration was built from Meta's documentation and tested against simulated responses. Many request details are still marked in the code as needing confirmation against Meta's current documentation, and it has not been run end to end against the live service.

## Related
- [Sequences and follow-ups](08-sequences-and-follow-ups.md)
- [Personalization and claim verification](07-personalization-and-claim-verification.md)
- [Replies and the unified inbox](13-replies-and-unified-inbox.md)
- [Workspaces and agency mode](24-workspaces-and-agency-mode.md)
- [Compliance](20-compliance.md)
- [Plans, limits and billing](22-plans-limits-billing.md)

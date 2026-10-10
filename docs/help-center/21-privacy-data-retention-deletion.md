---
id: privacy-data-retention-deletion
title: Privacy, data retention and deletion
audience: customer
last_verified: 2026-10-10
owner: help-center
sources:
  - app/db/models.py
  - app/api/account_data.py
  - app/services/account_export.py
  - app/api/leads.py
  - app/services/consent.py
  - app/api/strategies.py
  - app/api/linkedin_network.py
  - app/workers/support_tasks.py
  - app/workers/celery_app.py
  - app/api/support.py
  - app/config.py
  - app/services/rbac.py
  - app/services/auth.py
  - frontend/src/app/(app)/profile/page.tsx
  - frontend/src/lib/profile.ts
  - app/api/admin.py
  - app/services/admin_service.py
  - app/services/linkedin_network.py
  - frontend/src/app/(app)/pipeline/page.tsx
  - frontend/src/components/strategy/DeleteStrategyDialog.tsx
  - frontend/src/app/(app)/network/page.tsx
  - frontend/src/app/(app)/settings/page.tsx
  - frontend/src/app/privacy/page.tsx
  - docs/program/BASELINE.md
---

# Privacy, data retention and deletion

This article explains what LeadPilot stores about you and about the prospects you contact, how long it keeps it, and what you can download or delete yourself. It describes how the product behaves today, including what is not built yet. It is not legal advice.

## What does LeadPilot store about me?

For your own account, LeadPilot stores:

- your email address, your name if you add one, and a one-way hash of your password (never the password itself);
- your plan and billing status;
- what you enter during identity onboarding: the country you are in, whether you sign up as an individual or a company, the company name and country, and your verified phone number;
- the IP address you signed up from and the country that address appears to be in, which is used as a risk signal;
- your theme and writing-voice settings;
- connections to Gmail, LinkedIn and other services. Their access tokens are stored encrypted.

LeadPilot also keeps security and activity records about your account, such as sign-ins, refused attempts, data exports and deleted strategies.

## What does LeadPilot store about my prospects?

For each prospect (lead) found for a strategy, LeadPilot stores what it sourced and enriched: name, job title, company, email address, phone number, LinkedIn profile, and research notes such as recent posts or company news.

It also stores the outreach itself: the subject and body of every message, when it was sent, and the replies prospects send back, including the reply text. Bookings, meetings, meeting notes and transcripts are stored too.

For compliance, LeadPilot keeps a consent ledger (opt-ins, opt-outs and erasures) and a do-not-contact (suppression) list of email addresses, phone numbers and LinkedIn profiles.

## How long is my data kept?

Apart from support chat history, LeadPilot does not delete your data automatically after a set time. Your products, strategies, leads, messages, replies and meetings stay until you delete them.

**Support chat history** is the exception. A conversation is deleted 30 days after its last message, by a job that runs every night at 03:20 UTC. The number of days is a deployment setting; 30 is the default. Support tickets are not deleted by this job, even if the conversation they came from is.

The suppression list is kept without a time limit. You cannot remove an entry yourself; only a platform administrator can remove one, so a person who asked not to be contacted stays protected.

## How do I download a copy of my data?

1. Open **Profile**.
2. In the **Download your data** card, type your password in **Confirm with your password**.
3. Press **Download my data**.

You get one JSON file, named like `leadpilot-account-export-2026-10-10.json`. It contains everything your account owns: profile, products, strategies, leads, messages, meetings, settings and the records listed above.

Things to know:

- Passwords and connection secrets (such as encrypted tokens and API key hashes) are left out on purpose.
- Shared, deployment-wide lists with no owner, such as the suppression list, are not included.
- You must sign in to export. A personal API key cannot download the whole account.
- Every export, and every attempt refused for a wrong password, is recorded in the account's security log.
- If you type the wrong password you see "That password is not right." Too many attempts in a short time show "Too many attempts. Wait a while and try again."
- In a workspace, the export always covers the account of the person who is signed in, not the workspace owner's account.

## How do I erase a prospect's data?

Open the lead from **Pipeline**, press **Delete (GDPR erasure)**, then press **Delete** in the "Permanently delete lead?" confirmation. In a workspace, SDRs and viewers cannot do this; it needs the owner or a manager.

When you confirm, LeadPilot:

1. records the erasure in the consent ledger first, so there is proof the request was honoured. That record keeps the email address or phone number it was about;
2. adds the person's email, phone number and LinkedIn profile to the suppression list, so no strategy will contact or source them again;
3. clears the lead's name, job title, email, phone, company, LinkedIn details, research notes and the written explanation of its AI score, and marks the lead as dropped. The numeric scores (booking likelihood and F-P-T-A scores) stay on the record. An empty record without personal details is kept so the same person is not re-added to that strategy;
4. forgets which record in your connected CRM (HubSpot or Salesforce) the lead was linked to.

What this does **not** do today:

- Messages already sent to the person and replies received from them are not deleted by this action. The confirmation says all personal data for the contact is erased; the message history is not.
- Anything already copied into your CRM stays there. Erasing it in the CRM is up to you.

## Can I delete a strategy or my uploaded LinkedIn network?

Yes.

- **Strategy:** open the strategy and press **Delete**. In the **Delete strategy** window, confirm with your password. This permanently deletes the strategy with its research, leads, sequences, messages and campaign history. A campaign that is still sending must be paused first. The deletion is recorded in the security log, and the tamper-evident activity trail keeps its entries.
- **LinkedIn network:** on the **Network** page, **Delete my uploaded connections** removes every connection you uploaded, after you confirm "Delete all uploaded connections?". The deletion itself is never limited by plan, but the button only shows on Growth and higher plans. After a downgrade, contact support to delete your uploaded connections.

## Can I delete my whole account?

No, not yet. There is no account deletion in the app, and no feature that deletes or anonymises an account automatically. To ask for your account to be deleted, use the privacy contact on the **Privacy** page. Such a request is handled manually by the team.

## Where is the privacy policy?

The public **Privacy** page on the LeadPilot website is the policy. It lists the email address for privacy requests. If anything in this article and that page seem to disagree, ask support.

## Related
- [Compliance](20-compliance.md)
- [Account security](23-account-security.md)
- [Pausing and stopping outreach](25-pause-stop-kill-switch.md)
- [CRM and integrations](16-crm-and-integrations.md)
- [Known limitations](29-known-limitations.md)
- [Contact support and status](30-contact-support-and-status.md)

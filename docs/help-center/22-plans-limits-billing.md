---
id: plans-limits-billing
title: Plans, limits and billing
audience: customer
last_verified: 2026-10-10
owner: help-center
sources:
  - app/core/plans.py
  - app/core/billing_catalog.py
  - app/services/billing.py
  - app/api/billing.py
  - app/integrations/stripe_billing.py
  - app/workers/billing_tasks.py
  - app/services/usage_meter.py
  - app/api/strategies.py
  - app/api/sequences.py
  - app/api/leads.py
  - app/api/calls.py
  - app/api/linkedin_network.py
  - app/api/playbook.py
  - app/api/strategies_advanced.py
  - app/api/analytics.py
  - app/services/system_settings.py
  - app/services/rbac.py
  - frontend/src/app/pricing/page.tsx
  - frontend/src/app/(app)/profile/page.tsx
  - frontend/src/lib/pricing.ts
  - frontend/src/lib/post-login.ts
  - frontend/src/lib/api/client.ts
  - frontend/src/components/strategy/OutreachPanel.tsx
  - frontend/src/lib/leadOutreach.ts
---

# Plans, limits and billing

Every LeadPilot account is on a plan. The plan decides how many strategies you can have, how many leads each strategy can hold, how long a sequence can be, which channels you can send on, and how much AI work your account can run per day. This article lists those limits exactly as the product enforces them and explains how paying works.

## What plans are there, and what are their limits?

These are the limits the product checks today:

| Plan | Strategies | Leads per strategy | Sequence steps | Channels | Daily AI limit (USD) |
|---|---|---|---|---|---|
| free | 3 | 100 | 5 | gmail | 10.0 |
| starter | 10 | 500 | 10 | gmail, whatsapp | 25.0 |
| growth | 25 | 2500 | 15 | gmail, whatsapp, linkedin | 60.0 |
| scale | Unlimited | 10000 | 20 | gmail, whatsapp, linkedin, phone | 150.0 |
| pay_per_meeting | 10 | 1000 | 10 | gmail, whatsapp, linkedin | 60.0 |
| pro | Unlimited | Unlimited | 20 | gmail, whatsapp, linkedin, phone | 150.0 |
| enterprise | Unlimited | Unlimited | 20 | gmail, whatsapp, linkedin, phone | 400.0 |

No sequence can have more than 20 steps on any plan. The sequence form in the web app creates an opening message and an optional follow-up (up to 2 steps).

In the app these plans are shown as Free, Starter, Growth, Scale, Pay per meeting, Pro and Enterprise. "gmail" means email sent through your connected Gmail account. The Pricing page calls strategies "campaigns".

Pro is no longer sold. Accounts already on Pro keep exactly what they have.

The AI phone channel ("phone") is also switched off for the whole deployment by default. An administrator has to turn it on before any plan can use it.

## How much do the plans cost?

There are two ways to pay. Prices are in US dollars.

**Monthly subscription** (marked Recommended on the Pricing page):

- Starter: $149 per month
- Growth: $349 per month
- Scale: $699 per month
- Enterprise: $1,499 per month

Each monthly tier starts with a 14-day free trial. An account gets the trial only once: if you have had a trial before, a later monthly checkout starts without one.

**Pay per meeting:** no monthly fee ($0) and $179 for each prospect who books a meeting through LeadPilot.

The Free plan has no price. Free accounts are limited by the table above.

## How does pay per meeting work?

- When a prospect books a meeting, LeadPilot records a charge for it, but does not take payment straight away. It waits 48 hours first.
- If the meeting is no longer booked when the 48 hours are over (for example, it was cancelled), the charge is waived.
- You are charged once per prospect. If the same prospect books again, there is no second charge.
- A background job charges meetings whose 48 hours have passed. It runs every 30 minutes.
- If the account has no saved payment method, or the card is declined, the charge is marked as failed.

A meeting charge can be disputed only while it is still inside its 48-hour window. The web app has no dispute button yet; disputes go through the LeadPilot API. After the 48 hours, contact support instead. An administrator then decides whether to waive or charge a disputed meeting.

## How do I choose or change a plan?

Go to the **Pricing** page. You can also reach it from **Profile**, in the **Plan** card, with the **Upgrade plan** button. On Pricing you pick a monthly tier and press the trial button, or press **Pay per meeting**.

- You must be signed in. If you are not, the button takes you to sign-up.
- Your phone number must be verified first (unless your production deployment deliberately has no text-message service, in which case the check is skipped). If it is not, you see "Verify your phone to choose a plan." and you are sent to the verification screen.
- You finish on a checkout page run by Stripe, the payment provider. For pay per meeting, this step saves your card for later charges. When checkout finishes you return to Settings.
- Choosing a different plan replaces your current one. The subscription being replaced is cancelled so you are not billed twice.
- Leaving checkout without finishing does not change or downgrade your current plan.

If you sign in and your account has no paid plan, LeadPilot takes you to the Pricing page once, right after sign-in. You can still go back to the app; the Free limits then apply.

If you are a member of someone else's workspace, you work under the workspace owner's plan and are not asked to buy your own, as long as the workspace owner has a paid plan. Only the account owner can buy or cancel a plan for their account.

## What happens when I reach a plan limit?

The action is refused and you see a message that names the limit, for example "Free plan allows 3 strategies. You have 3." The limits are checked at these points:

- **Strategies:** when you create a new strategy. All strategies across all your products count. Deleting a strategy frees a place.
- **Leads per strategy:** when you source leads. If the strategy is full, sourcing is refused. If there is some room, LeadPilot only asks for as many leads as fit, and checks again lead by lead.
- **Sequence steps and channels:** when you create a sequence and again every time you launch it. A sequence built while you were on a higher plan cannot be launched after a downgrade if it breaks the lower plan's limits.
- **Channels for AI calls:** when you start a call.

Some features are also tied to plans: the learning playbook and A/B test results are not included in Free, and the private LinkedIn network needs Growth, Scale, Pro or Enterprise (not Pay per meeting).

## What is the daily AI limit?

Every plan has a daily dollar limit on AI use for the whole account (the last column of the table). It counts the estimated cost of AI work across your account since 00:00 UTC, and it resets at 00:00 UTC every day.

- The limit is checked before each AI step in research pipelines, strategy verification and lead scoring. A step is only started if its worst-case cost still fits, so a run may stop slightly before the limit, never after it.
- When the limit is reached, a running strategy stops with the status **budget exhausted**. Nothing already paid for is lost, and you can resume it after the reset. Lead scoring simply skips the score.
- Creating a new strategy or resuming one while the limit is used up is refused with: "Your … plan's daily AI limit ($…) is used up. It resets at 00:00 UTC."
- Sending messages, meeting briefs and call analysis are not stopped halfway by this limit, but their cost still counts toward the day.

The cost is an estimate calculated from model prices set by your administrator. This limit is separate from each strategy's own budget, which is covered in the research pipeline article.

## How do I cancel?

Cancellation exists in the product, but the web app does not currently have a billing screen with a cancel button. If you need to cancel, contact support. This is how cancellation works:

- **Monthly:** the plan is cancelled at the end of the current billing period, and you keep access until then.
- **Pay per meeting:** stops immediately. Meetings already booked are still billed.

When a subscription ends, the account returns to the Free plan and its limits.

## What if a payment fails?

If a monthly payment fails, the subscription is marked past due. You keep your plan while Stripe retries the card. If Stripe finally cancels the subscription, the account returns to Free.

## What do analytics history and multi-variate testing mean?

The Pricing page shows an analytics history length for each plan: 30 days on Free, 90 days on Starter, 365 days on Growth and Pay per meeting, and unlimited on Scale, Pro and Enterprise. The day-by-day chart of a strategy's sends, replies and other events only goes back that far, and its title says so (for example "last 30 days"). Totals and the A/B variant table are not limited.

Multi-variate testing (comparing three or more variants at once; the results are available through the LeadPilot API) is included in Growth, Scale, Pro and Enterprise. Starter and Pay per meeting include A/B testing but not multi-variate results; asking for them is refused with an upgrade message.

On a production deployment where Stripe is not set up, choosing a plan fails with "payments are not configured; plans cannot be changed right now".

## Related
- [Research pipeline](04-research-pipeline.md)
- [Lead sourcing and email verification](06-lead-sourcing-and-email-verification.md)
- [Sequences and follow-ups](08-sequences-and-follow-ups.md)
- [Workspaces and agency mode](24-workspaces-and-agency-mode.md)
- [Troubleshooting](27-troubleshooting.md)
- [Known limitations](29-known-limitations.md)

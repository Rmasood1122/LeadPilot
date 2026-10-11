---
id: sequences-and-follow-ups
title: Sequences and follow-ups
audience: customer
last_verified: 2026-10-11
owner: help-center
sources:
  - app/services/send_holds.py
  - app/api/sequences.py
  - app/api/sequence_reviews.py
  - app/services/sequence_engine.py
  - app/services/adversarial_review.py
  - app/services/conversion_probability.py
  - app/services/send_windows.py
  - app/services/sequence_completion.py
  - app/services/system_settings.py
  - app/workers/outreach_tasks.py
  - app/workers/calendar_tasks.py
  - app/api/webhooks.py
  - app/core/plans.py
  - app/config.py
  - app/db/models.py
  - docs/features/sequence-completion.md
  - docs/features/reengagement.md
  - frontend/src/components/strategy/OutreachPanel.tsx
  - frontend/src/lib/leadOutreach.ts
  - frontend/src/app/(app)/campaigns/page.tsx
  - app/integrations/calendly.py
  - docs/VERIFICATION_REPORT.md
---

# Sequences and follow-ups

A sequence is the series of messages LeadPilot sends to each lead in a strategy. This article covers how sequences are built and launched, when each step goes out, what stops or pauses a sequence, how automatic follow-ups work, and the step limits on each plan.

## What is a sequence?

A sequence belongs to one strategy and has numbered steps. Each step holds:

- a **brief**: what the message should say. It is not the final text; LeadPilot writes the final message for each lead at send time.
- a **delay**: how many days to wait after the previous step is sent (0 to 60).
- a **channel**: email by default. Steps can also use WhatsApp, LinkedIn or phone, if your plan includes them. A step without its own channel uses the sequence's channel.
- optionally a **variant** label, for testing different versions of a step.

## How do I create and launch a sequence in the app?

On a verified strategy's page, after finding leads, use the **2. Write the email and launch** card:

1. Enter a **Sequence name**.
2. Under **First email: what should it say?**, describe the first email: who you are, why you are writing, one clear ask.
3. Optionally add a **Follow-up email** and the **Days to wait before the follow-up** (the form starts at 3).
4. Tick the box confirming you may lawfully email each person on the list.
5. Press **Launch to N lead(s)**.

In the app today, this creates an email-only sequence with one or two steps. Longer sequences, and steps on other channels, are created through the LeadPilot API, which accepts up to 20 steps numbered 1, 2, 3 and so on with no gaps.

## How many steps can I put in a sequence?

| Plan | Steps per sequence | Channels |
|---|---|---|
| Free | 5 | Gmail |
| Starter | 10 | Gmail, WhatsApp |
| Pay per meeting | 10 | Gmail, WhatsApp, LinkedIn |
| Growth | 15 | Gmail, WhatsApp, LinkedIn |
| Scale | No plan limit | Gmail, WhatsApp, LinkedIn, phone |
| Pro, Enterprise | No plan limit | Gmail, WhatsApp, LinkedIn, phone |

These are checked when the sequence is created and again at every launch, so a sequence built on a higher plan cannot be launched after a downgrade. A sequence over the limit is refused with an upgrade message.

## What does LeadPilot check when I launch?

In order, a launch is refused if:

- your phone number is not verified;
- the strategy is not `verified`, or its campaign is paused;
- the sequence is outside your plan's steps or channels;
- the sequence's pre-launch content review found a blocking problem.

The **pre-launch review** scans the sequence for spam and pressure phrases, compliance problems (for example a deceptive subject line, or a WhatsApp step without an approved template), and briefs that ask the writer to state facts about the prospect. Only blocking findings stop the launch. A workspace owner or manager can override them with a written reason of at least 10 characters. Changing the content after an override brings the review back. You can see the review under **Campaigns**, on the **Sequences** tab.

If you are an SDR in a workspace that requires approval, your first launch is sent to a manager instead: "Sent to a manager for approval. Nothing is sent until they approve."

On launch, LeadPilot enrolls the strategy's `verified` leads that have the address the first step needs: an email address for an email first step, a LinkedIn profile for a LinkedIn first step, and a phone number for a WhatsApp (or AI call) first step. It skips anyone suppressed or already enrolled, and schedules step 1. Only `verified` leads can be enrolled. If your sending domain has deliverability problems, the launch still goes ahead but shows a warning.

## When does each step go out?

- **Step 1** is scheduled for the next moment inside the send window.
- **Each later step** is scheduled when the previous step is actually sent: its delay in days is added, then the time is moved into the next send window.
- The send window is business hours in the lead's own time zone, 09:00 to 17:00 by default, with weekends skipped. A lead with no known time zone uses the deployment's fallback zone (UTC by default).
- If smart send time is turned on for the campaign, a step may be held for the campaign's best engagement window, for up to 72 hours by default.

Every send also passes the daily cap, the suppression check and, where triggered, the send-review queue. Messages over the day's cap wait for the next day; they are not dropped.

## What stops or pauses a sequence?

| Event | Effect |
|---|---|
| The lead replies (interested, question, objection or not interested) | All of that lead's sequences stop, on every channel. |
| The lead unsubscribes or asks to stop | Suppressed everywhere; all sequences stop immediately. |
| An email bounces | The lead is dropped and their sequences stop. |
| An out-of-office reply | Sequences pause for 7 days by default, then continue. |
| A meeting is booked on LeadPilot's own calendar | Sequences pause. If the meeting is cancelled they resume; otherwise they resume a day after the meeting ends unless something else stopped them. |
| A meeting is booked through Calendly | Sequences stop. (The Calendly integration has not yet been verified against the live service.) |
| The lead is suppressed by the time a message is due | That message is cancelled and the sequence stops. |
| You remove the lead (**Remove**, which marks it `dropped`) | The sequence stops straight away; a removed lead is never sent to. |
| A step's channel has no address for the lead (for example a WhatsApp step and no phone number) | That message is cancelled and the sequence stops, with the reason "no address for the step's channel" (not counted as a compliance stop). |
| An automated reply (ticket receipts, no-reply bots) | Nothing changes; it is stored but not treated as a reply. |

LeadPilot also keeps a live estimate of each lead's chance of booking. After a lead has had 4 unanswered sends (the default), a lead judged to have gone cold may have its sequence paused ("cooling") or stopped ("archived").

A stopped sequence can never send to that lead again.

## What are automatic follow-ups?

Automatic follow-ups are separate from step delays. They catch a lead whose sequence is still active but has nothing queued, for example because a send failed permanently, a WhatsApp step needed a template, or a step was deleted.

Every 30 minutes, LeadPilot looks for active sequences where the last message has had no reply for longer than that step's follow-up delay (72 hours by default; you can set 1 to 2,160 hours). A sequence with a message still queued, waiting in the send-review queue, or held by a safety check is left alone. If the sequence has a next step, that step is sent. A step a reviewer rejected is never sent again; the follow-up moves on to the step after it. If it does not, LeadPilot writes a follow-up from the lead's own message history and your product description, on the same channel as the last message, and sends it through the normal checks. It does not write automatic follow-ups for WhatsApp, because a WhatsApp first contact needs an approved template.

No follow-up goes to a lead who has replied, or from a paused campaign. To change the setting, go to **Campaigns**, choose the strategy, open the **Sequences** tab, and use **Auto follow-up** and **after N hours of silence** under each step.

## When is a sequence complete?

When every step has been sent to a lead, their sequence is marked completed. LeadPilot does not keep following up after that. A separate re-engagement feature can send one more email to leads who finished without replying, but it is off for every campaign until an owner or manager turns it on.

LeadPilot also reports a completion rate, and lists each reason a sequence ended early. A sequence where every step was skipped (for example, an all-WhatsApp sequence to a lead without opt-in) is flagged for your attention. Skipped steps do not count as sent.

## Related
- [Personalization and claim verification](07-personalization-and-claim-verification.md)
- [Sending email through Gmail](09-email-sending-gmail.md)
- [WhatsApp outreach](10-whatsapp-outreach.md)
- [The send-review queue](12-send-review-queue.md)
- [Replies and the unified inbox](13-replies-and-unified-inbox.md)
- [Pausing, stopping and the kill switch](25-pause-stop-kill-switch.md)

---
draft_for: https://www.calendarharvest.com/faq/ (FAQPage JSON-LD in technical/schema_markup.md mirrors questions 1–10)
status: DRAFT — publish only after the trademark review (questions.md Q-04)
last_checked: 2026-10-15
sources: frontend/src/content/product-facts.json; app/core/billing_catalog.py; app/services/reply_classification.py; docs/help-center/01, 02, 10, 12, 14, 19, 20, 22, 26, 29
rules: answer first; 50–150 words; no number without a source; statuses from the facts file only
---

# LeadPilot FAQ

## What LeadPilot is (1–10)

### 1. What is LeadPilot?
LeadPilot by Calendarharvest is an AI outbound sales tool for agencies and B2B service firms:
it researches your market, finds and verifies business contacts, writes one-to-one emails,
sends on a schedule you approve each day, and books meetings. You start by describing what
you sell, not by uploading a list. It's built for businesses of about 5–50 people where the
founder or owner handles new business and there's no sales team. It is not a contact database
you search yourself, and it is not a bulk email sender.

### 2. Who is LeadPilot for?
It's for founder-led agencies and B2B service firms with roughly 5–50 employees and no
dedicated sales team. LeadPilot's own customer research ranks the closest fits as marketing,
web and design agencies; commercial cleaning companies; accounting, immigration and law
consultancies; staffing and recruiting agencies; and commercial HVAC and facilities companies.
Local businesses that sell to other businesses, such as a caterer pitching nearby offices,
can target a service area. The common thread is one person responsible for new business who
doesn't have time to research, write and follow up by hand.

### 3. Who is LeadPilot not for?
LeadPilot is not a fit if you sell to consumers or homeowners, since it only finds people at
companies. It's also not a fit if you need to email a list you already have (leads can't be
imported), if you want to send thousands of emails a day (the default cap is 100 a day per
mailbox), or if you want an AI that replies to prospects for you. Companies that already run
Salesforce or HubSpot with a dedicated sales hire usually need a different kind of tool.

### 4. Is LeadPilot an AI SDR?
Partly. It does the research, list building and writing an SDR would do, and sends without
a person writing each email. Unlike many AI SDRs, it doesn't reply to prospects or hold
conversations. Replies are classified and routed to you, and you write the answer. It also
waits for your approval each day before sending. If you want an autonomous agent that
negotiates with prospects, LeadPilot is the wrong choice.

### 5. Who makes LeadPilot?
LeadPilot is made by Calendarharvest (calendarharvest.com). The founder is Rehan Masood, an
AI engineer based in Astoria, New York. The company is bootstrapped. It isn't affiliated with
LeadPilot AB (leadpilot.com), a Swedish company that also sells B2B prospecting software, or
with other products that use the name "LeadPilot" or "Lead Pilot". Check the domain
calendarharvest.com when you read about it.

### 6. Is LeadPilot new? Does it have customers and reviews?
Yes, it's new. The public site went live around September 2026. As of October 2026,
LeadPilot has no published customer results or public reviews, and its pages don't claim
any. What's live and what isn't is published openly: the homepage and the help center's
"Known limitations" article list every feature's status. If social proof matters to your
decision, ask for a call and a pilot rather than relying on claims.

### 7. What is live today, and what isn't?
Live: market and strategy research, finding and verifying business contacts, writing each
email for one person, sending from your Gmail after daily approval, WhatsApp steps, reply
classification and routing, meeting booking, smart send time, and the Android app. Built but
not yet confirmed end to end: lead scoring, "not now" memory, meeting prep, and agency
workspaces. Built but not live: LinkedIn steps and online (Stripe) checkout. Several advanced
features, such as Reply Copilot and Signal Radar, are switched off by default.

### 8. Does LeadPilot have a contact database?
Not one you browse. LeadPilot sources contacts for you, matching the strategy it built, then
verifies their email addresses and checks them against your suppression list. You don't
search or export a database the way you would in Apollo or ZoomInfo. That's deliberate: the
product is the outcome (verified, relevant contacts with one-to-one emails), not access to
records.

### 9. Is LeadPilot a Calendly alternative?
No. Calendly is a scheduling tool; LeadPilot is an outbound sales tool that ends with a booked
meeting. It has its own booking pages, with weekly availability, double-booking protection
and time-zone handling, and it can also put a Calendly link in emails. LeadPilot's calendar
doesn't read your Google Calendar, so busy times there aren't blocked automatically.

### 10. Is there a mobile app?
Yes, for Android. You can use it to review and approve the day's sending, follow replies and
check your pipeline away from your desk. The app talks to the same cloud backend as the web app,
so campaigns keep running when your phone or laptop is off. There is no iPhone app yet. Some parts
of the push-notification setup are marked in the help center as not yet verified against the
current push service.

## How it works (11–20)

### 11. How does LeadPilot work, step by step?
You describe what you sell. LeadPilot runs a research pipeline (72 steps, or 144 if you have
no past clients) and writes a go-to-market strategy. The strategy must pass 10 checks,
including a compliance check. LeadPilot then sources and verifies contacts, writes each email
for one person and checks its claims. Each day you approve sending, and emails go from your
own Gmail. Replies are classified and routed to you, and interested prospects book on your
booking page or a Calendly link.

### 12. Do I have to write the emails?
No. LeadPilot writes each email for one person, based on the verified strategy and what it
knows about the person's company, such as company news where available. Claims in the email
are checked before it can be sent, and higher-risk messages wait in a send-review queue for
your approval. You approve each day's sending, and you can edit or stop messages before they
go out.

### 13. Does it send from my own email address?
Yes. Email goes out through the Gmail account you connect in Settings, using Google's secure
sign-in (OAuth), so prospects see your name and address and replies land in your own inbox. One
Gmail mailbox can be connected per account. LeadPilot doesn't send from shared or rented domains,
so your sender reputation stays your own, which is also why sending ramps up slowly on a newly
connected account.

### 14. How many emails does LeadPilot send per day?
At most 100 a day per mailbox, by default. A newly connected Gmail account sends 10 emails on
its first day and adds 10 a day until it reaches 100. Compliance rules can lower that cap but
never raise it. Messages over the day's allowance wait until the next day; they aren't dropped.
This is deliberate: LeadPilot is built for careful, personalized outreach, not mass sending.

### 15. What does "approve-first" sending mean?
Automatic sending waits each day until the account owner approves it. Until you approve,
nothing goes out that day, and messages simply wait. On top of that, messages flagged as
higher-risk go to a send-review queue and need individual approval. You can approve from the web
app or the Android app. The point is control: the research and writing are automated, but the
decision to send stays with you.

### 16. How does LeadPilot handle replies?
Every reply is classified: interested, question, objection, not interested, unsubscribe
request, out of office, bounce, or automated response. When a person replies, their sequence
stops and the reply is routed to you. An unsubscribe request suppresses them immediately. An
out-of-office reply pauses and reschedules the sequence instead of stopping it. LeadPilot
doesn't auto-reply; you write the answer.

### 17. How does meeting booking work?
Prospects book through a booking page on LeadPilot's own calendar or through a Calendly link
in the email. You set weekly availability and create booking pages (15–60 minutes, up to 10
custom questions). LeadPilot hides times that overlap any live booking or meeting, and if two
people try to book the same time, only the first is accepted. Confirmations show each person's
time zone.

### 18. Which channels does LeadPilot support?
Email through Gmail is live. WhatsApp steps are live on plans that include WhatsApp, but cold
WhatsApp contact needs a Meta-approved template and a recorded opt-in for each contact.
LinkedIn steps are built and tested only against simulated services, so they're not live yet.
AI phone calling exists but is switched off for the whole deployment by default.

### 19. How does LeadPilot keep outreach legal (CAN-SPAM, GDPR)?
Compliance is enforced in code. Every email carries your business identity, an unsubscribe
link and one-click unsubscribe headers. Anyone who unsubscribes or replies "stop" is suppressed
across email, LinkedIn, WhatsApp and phone, and the suppression list is re-checked right before
every send. Leads in the EU, EEA or UK get no open-tracking pixel. You can erase a prospect's
data. LeadPilot asks you to confirm a lawful basis to contact each person, but it doesn't give
legal advice.

### 20. Will LeadPilot hurt my domain's deliverability?
It's built to reduce that risk, though no tool can guarantee inbox placement. Sending ramps up
slowly (10 on the first day, up to 100 a day), every email includes one-click unsubscribe
headers, email addresses are verified before sending, and campaigns pause automatically if the
bounce rate gets too high. Google and Yahoo's bulk-sender rules (spam rate under 0.3%, one-click
unsubscribe) are easier to meet at low volume with verified addresses.

## LeadPilot vs alternatives (21–25)

### 21. How is LeadPilot different from Apollo.io?
Apollo is a self-serve sales intelligence platform: a large contact database plus sequencing,
where you choose the market, build the list and write the emails. LeadPilot does the research,
list building and writing for you, and asks you to approve the day's sending. Choose Apollo if
you want database access and full control at a low per-seat price. Choose LeadPilot if you're a
founder-led firm without the time to run outbound yourself.

### 22. How is LeadPilot different from Instantly or Smartlead?
Instantly and Smartlead are cold-email sending platforms built for volume: many mailboxes,
warmup and inbox rotation. You bring the list and the copy. LeadPilot is low volume by design
(100 a day per mailbox by default), sends from your one Gmail account, and does the research,
sourcing and one-to-one writing itself. Agencies sending thousands of emails a day for clients
should look at Instantly or Smartlead; founders who want fewer, better emails written for them
should look at LeadPilot.

### 23. How is LeadPilot different from Clay?
Clay is a data enrichment and workflow tool: you build tables that pull from many data sources
and use AI to research and personalize, then send through another tool. It's flexible and
powerful, but you build and maintain the workflow. LeadPilot is a fixed end-to-end flow, from
description to research, contacts, emails, approval, sending and booking, with fewer settings.
Clay suits growth and ops teams; LeadPilot suits founders who want the outcome, not the
workbench.

### 24. Should I use LeadPilot or hire an SDR?
If you have the budget and time to hire, ramp and manage an SDR, a good one can do things
LeadPilot can't: phone conversations, live objection handling and relationship building.
LeadPilot fits when you can't justify a full-time hire yet. It does the research and writing,
sends after your approval, and leaves replies to you. Many firms use LeadPilot to learn which
segments respond before hiring.

### 25. Is LeadPilot cheaper than a lead-generation agency?
Usually, but check the fit. LeadPilot's monthly plans run from $149 to $1,499 per account, or
$0 a month plus $179 per booked meeting. Agencies typically charge a retainer, a per-meeting
fee or both, and they write and send in their own style. With LeadPilot the emails go from
your own Gmail in your name, and you approve sending daily. An agency also brings human
judgment and calling that LeadPilot doesn't.

## Pricing and getting started (26–30)

### 26. How much does LeadPilot cost?
There are two ways to pay, in US dollars. Monthly plans: Starter $149, Growth $349, Scale
$699, Enterprise $1,499 per month, each a flat price per account rather than per seat.
Pay per meeting: no monthly fee and $179 for each prospect who books a meeting. Plans differ
in strategies, leads per strategy, sequence length, channels and daily AI usage. Online
checkout is not live yet; contact Calendarharvest to start.

### 27. How does pay-per-meeting pricing work?
You pay $0 a month and $179 when a prospect books a meeting through LeadPilot. The charge waits
48 hours and is waived if the meeting is cancelled in that time. You're charged once per
prospect, so a second booking by the same person is free. Pay per meeting includes up to 10
strategies, 1,000 leads per strategy and 10 sequence steps. Online card payment is not live
yet, so contact Calendarharvest to set it up.

### 28. Is there a free trial?
Not online yet. The billing code includes a 14-day free trial for monthly plans, but online
checkout isn't live, so the website doesn't offer one today. A free account exists with tight
limits (3 strategies, 100 leads per strategy, email only). To try LeadPilot on your real
market, book a call with the founder through calendarharvest.com/contact.

### 29. What do I need to get started?
You need a product or service you can describe in writing, and a Google (Gmail) account to send
from. Past client details are optional but improve the strategy. For WhatsApp you also need a
plan that includes it, a WhatsApp Business number on your LeadPilot deployment, Meta-approved
templates, and an opt-in for each contact. Before launch, you confirm you may lawfully contact
each person.

### 30. Can I upload my own contact list?
Not as leads. Leads come from LeadPilot's own sourcing, which matches your verified strategy and
checks each email address. There are narrow exceptions, both outside the main lead flow: you can
upload your LinkedIn connections export to message existing 1st-degree connections (LinkedIn
steps aren't live yet), and an email-network import is available but switched off by default.
If your business depends on emailing an existing list, LeadPilot isn't the right tool.

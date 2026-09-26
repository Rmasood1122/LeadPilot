# 7-Day Paid-Client Sprint (LinkedIn, 25,500 connections)

**Status:** go-to-market plan. Built on *Evidence-First Client Hunting Plan for
LeadPilot* (2026-09-26) and its summary. Where this sprint departs from that
report to fit a 7-day deadline, the departure is marked **[SPRINT DEVIATION]**.

---

## 0. The truth this plan is built on

1. **You cannot sell LeadPilot the SaaS this week.** The audit shows 0 leads,
   0 messages and 0 production runs. The step timeout is still
   `pipeline_step_timeout_seconds: int = 300` (`app/config.py:286`) against a
   run of about 3,950 seconds. Selling it as working software would repeat
   the 11x pattern in a market that already distrusts AI-SDR claims.
2. **What you *can* sell this week is the outcome, done by hand:** you
   research, qualify and write outbound for a client's business. That is the
   documented service-first wedge (WP Engine pre-sale, agency-to-SaaS
   accounts) and the shape of the one €2k-pilot cold close in the corpus.
3. **Your 25,500 connections are the asset, but only the untouched ICP slice
   of them.** Anyone you messaged last month is excluded.
4. **Odds, stated honestly:** no dataset measures time to first client for a
   part-time founder. Closing a paid client in 7 days is *possible* on a warm
   network with a small, concrete, priced offer, but it is not the likely
   outcome. The sprint is designed so that even a "no" leaves you with a
   readable funnel, not another untracked week.
5. **"Paid" means money received**: a deposit or full payment in your
   account. A verbal yes, "send me a proposal" or "let's talk next month" are
   pipeline, not clients.

---

## 1. The offer (the only thing that changes vs. last month)

**Primary: "30-Day Outbound Pilot — Founding Client"**

| Item | Detail |
|---|---|
| What they get | 1 segment they choose → ~50 hand-qualified prospects (named decision-makers, qualification reason per row) → written 3-touch sequence → 30 days of sending and reply handling → booked conversations + the full funnel spreadsheet |
| Price | Fixed. Suggested **$750–$1,500**, with **50% upfront** to start. The only evidence anchor is one €2,000 pilot (n=1), so treat price as your decision, not a researched number |
| Guarantee | Activity and transparency (50 qualified prospects, every touch logged). **Never guarantee meetings or revenue** |
| Honesty line (say it every time) | "I'm building software around this process. It isn't finished, so the pilot is me doing it manually, which is why it's priced this way. Founding clients get a say in what gets built and better terms later." |

**Downsell (only when price is the stated objection): "Pipeline Starter" at $297–$497.**
50 hand-qualified prospects plus a written 3-message sequence, delivered in 5
business days. The client sends the messages. It's small, fast to deliver and
easy to say yes to in a week.

**Compliance guardrail:** never log into a client's LinkedIn account. Account
sharing breaks LinkedIn's User Agreement. Deliver by email from the client's
own authenticated mailbox with delegated access, or hand them the list and
scripts to send themselves.

**Before you send the first DM (Day 1):** do a 60-minute dry run: build 10
qualified prospects for one imaginary client. If you can't deliver it to
yourself, you can't sell it.

---

## 2. Who to message (ICP filter for your 25,500)

**Include (all must be true):**
- Title: Owner / Founder / CEO / President / Managing Partner / Principal
- Business sells **B2B services**, 1–50 staff (agencies, consultancies,
  staffing/recruiting, IT/MSP, commercial cleaning/facilities, commercial
  contractors; see `docs/ICP.md`)
- You can write **one line** explaining why pipeline matters to them *now*
  (hiring sales, posting about lead gen, new launch or offer, slow season)
- **Not** messaged by you in the last 60 days

**Exclude:** enterprise employees, job seekers, coaches (Blechman and the
coaching-chatbot case), local B2C trades, other lead-gen vendors who'd see you
as competition, and anyone you're picking only because you know them.

**How to build the list fast (compliant, no scrapers):**
1. *Settings → Data privacy → Get a copy of your data → Connections.* The CSV
   has name, company, position and connected-on date. Request it **today**
   because it can take up to 24 hours.
2. Filter the CSV on title keywords (owner, founder, ceo, president,
   principal, managing) → expect a few thousand rows.
3. Sort by likely fit (company name/position signals B2B service), then hand-
   qualify: **max 3 minutes per person** (profile + company page + one recent
   post). Write the one-line reason in the sheet *before* contact.
4. Optional: a Sales Navigator free trial to filter **1st-degree** connections
   by title, headcount and industry. It's LinkedIn's own product, so it's
   compliant.
5. Target: **Tier A = 75 prospects** by end of Day 2. If fewer than 40 qualify,
   that is itself a finding about the network. Don't loosen the criteria.

---

## 3. The 7-day schedule

Time budget: **~1.5–2 h/day** (a sprint-week stretch of the report's 60–90 min).
Rule that beats your 200:1 prep ratio: **setup is capped at 3 hours total, and
no engineering on LeadPilot this week.** Outreach gets logged before anything
else counts.

| Day | Outreach | Other (capped) |
|---|---|---|
| **1** | Emmanuel: (a) ask for **one referral** to a business owner who needs more clients, (b) ask for a **2–3 sentence verbatim quote** | Request connections CSV · build tracker (Section 5) · write offer one-pager · set price · create payment link (Stripe/PayPal/Wise invoice) · check Calendly works · 60-min delivery dry run · headline fix: *"I build and run outbound for B2B service firms — 20 yrs B2B sales"* |
| **2** | Qualify list → 75 Tier A · **send DM #1 to 15** | — |
| **3** | **DM #1 to 15** · reply to everyone the same day · book calls | — |
| **4** | **DM #1 to 15** · **follow-up to Day-2 batch** · run calls | One LinkedIn post (see Section 4). Untested side bet, 20 min max |
| **5** | **DM #1 to 15** · follow-up to Day-3 batch · calls | Send proposals and payment links within 2 hours of any "yes-ish" call |
| **6** | **DM #1 to 15** · follow-up to Day-4 batch · calls | Binary close on every open proposal |
| **7** | **Closing day:** final message to all Day-2/3 non-repliers (breakup) · chase every open payment link once | Weekly rollup · decide next step (Section 7) |

Totals: **75 first DMs, about 60 follow-ups, and every reply answered within
24 hours.**

**[SPRINT DEVIATION]** The report specifies follow-ups 5–7 days apart and a
4-week window. To fit 7 days, follow-up #1 goes out after 2 days and the
breakup after 5. Earlier batches still reach the full 3 touches after the
sprint ends. That's more pressure than the evidence supports, so keep every
message short and give an easy out.

---

## 4. Messages (drafts to edit into your own voice, not proven winners)

Principles backed by evidence: hand-written, ≤100 words, lead with a
business problem rather than flattery, honest about product state, one concrete
ask, explicit easy out. Sounding AI-written disqualifies you.

**DM #1 — warm connection**
> [Name] — upfront: this is a business message, and there's an easy out at the
> end. I'm taking on 3 founding clients this month for a 30-day outbound pilot:
> I hand-research ~50 decision-makers in the segment you pick, write the
> outreach, run it, and you get the booked conversations plus all the data.
> Fixed price, fixed scope. I'm building software around this process but it's
> not finished, so the pilot is me doing it manually, and it's priced that way.
> Is getting more [their service] clients a live problem for [Company] right now?
> If not, just say so and I won't follow up.

Replace `[their service]` with your one-line qualification reason. That line is
the personalisation, not their alma mater.

**Follow-up #1 (new information, not "just bumping")**
> Quick add, [Name]: the pilot's first deliverable is the list itself. 50 named
> buyers with the reason each one qualifies, in your hands within 7 days. Worth
> a 15-min call to see if your market fits? [Calendly link]

**Breakup (message 3)**
> Closing the loop, [Name]. If timing's wrong, no reply needed. If you know
> one business owner who'd want more B2B clients this quarter, I'd be grateful
> for the name.

The referral ask in the breakup turns a "no" into a warm intro, and intros
are the fastest route to a paid client in the first-customer evidence.

**Referral DM (to trusted friends and colleagues who aren't buyers)**
> [Name], quick favour: I'm taking 3 founding clients for a done-for-you
> outbound pilot this month. Who's one business owner you know that needs more
> B2B clients? A name is plenty, and I'll mention you only if you say that's ok.

Send 10 of these on Day 3–4. They don't count toward the 75.

**The one post (Day 4)**
A plain-text post: what you're doing, for whom, 3 founding spots, the honesty
line, "DM me 'PILOT'". No product screenshots and no "AI-powered" claims.
Posting is contested evidence (reach down 34%), so this is one post, not a
content plan.

---

## 5. The tracker (build on Day 1, update daily, ~10 min)

Use one Google Sheet, one row per prospect:

`Date added | Name + URL | Company | Segment | Qualification reason (before contact) | DM1 date | FU1 date | FU3 date | Reply date | Sentiment POS/NEU/NEG | Verbatim key line | Call booked | Call held | Price quoted | Payment link sent | OUTCOME: PAID $ / DECLINED (verbatim reason) / SILENT / IN-PLAY`

Add a daily rollup row with DMs sent, replies, positive replies, calls booked,
calls held, proposals, payments and **hours spent selling**.

**Three rules:** a reply isn't a lead, a call isn't a client, and silence isn't
message failure. Never rewrite the message mid-week. At 75 sends, copy
differences are statistically invisible.

---

## 6. The call: turn "interested" into paid in the same week

20 minutes, 5 questions, then the offer, then a direct close:
1. "Where do new clients come from today?"
2. "What happened last month, and how many new conversations did you get?"
3. "If this worked, who exactly would we target?" (this defines the pilot segment)
4. "What have you tried before for outbound, and what went wrong?"
5. "Who else decides on something like this?"

Then state scope, price and the honesty line, and close with a direct question:
> "Is this a yes to start Monday at $X, or a no? Either answer is fine."

On a yes, **send the payment link while you're still on the call**, and start
the work when the deposit arrives. On "I need to think," book a specific
decision time within 48 hours. On a price objection, offer the Pipeline Starter
once. On "not now," log the verbatim reason and ask for a referral.

---

## 7. Checkpoints and end-of-week decision

**Day 4 check (after ~45 DMs):**
- **0 replies at all:** the list is the suspect, not the copy. Re-check that the
  remaining rows really are B2B-service owners you didn't message last month.
- **Replies but they're curt or "you again?":** network fatigue. Send 5 honest
  one-to-one notes to trusted contacts asking how last month landed.
- **Positive replies but no calls:** change **only** the ask, to "I'll send you
  10 sample prospects for your market, free, and you decide if you want the other 40."

**Day 7 reading:**
| Result | What it means | Next move |
|---|---|---|
| ≥1 **paid** | You have a client | Stop new outreach and deliver the pilot flawlessly. It becomes LeadPilot's first real proof. Send only follow-ups to open threads |
| Calls held, no payment | The leak is at close (the "good for now" wall) | Keep list and message. Run binary closes. Continue the report's 4-week warm window |
| Positive replies, no calls | The ask is the problem | Change only the ask |
| <50% of planned DMs sent | **NOT EXECUTED**, not a market verdict | Re-plan hours honestly |
| 75 sent, 0 positive | Offer or network problem | Run the fatigue probe, then change one variable in the next window |

One week can't prove the offer fails: 75 warm touches is below the report's
floor for a verdict. Whatever happens, keep the same offer and ICP for the
remaining 3 weeks of the report's Phase 1 window before changing anything.

---

## 8. What NOT to do this week

- Don't pitch "LeadPilot, AI-powered SaaS", show dashboards, or imply the
  pipeline runs.
- Don't use automation tools, scrapers or browser extensions, and don't send
  connection invites (warm DMs only this week).
- Don't send free work as a door-opener. The one exception is the 10-sample
  ask-change on Day 4.
- Don't spend time on LeadPilot code or new strategy documents before Day 7.
- Don't mass-post, run ads (0 first customers from ads in the evidence), or open
  a new channel mid-week.
- Don't promise meetings or revenue.

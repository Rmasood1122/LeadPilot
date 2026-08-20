# Advanced Learning Loop — How It Works

*This is the non-technical explanation of the four features added in Milestone 8 (Chunks 4+5). You don't need to understand the math — just what happens and why.*

---

## 1. Send-Time Optimizer — "When should I send?"

**The problem it solves.** Sending an email at 2 AM on a Sunday rarely gets a reply. But "best time to send" isn't the same for everyone — an IT manager in manufacturing may respond at 7 AM; a startup founder may check email on Sunday nights.

**How it works.** Every time a lead replies or books a meeting, the system records *when* (day of week, hour) that happened. After a few weeks of campaigns it knows, for your specific ICP (e.g. "Manufacturing, mid-market companies"), that Tuesday 9 AM gets the most replies. The next time you schedule a sequence step, the system automatically aims for the next available recommended window — within 48 hours of when you triggered it. If you don't have enough data yet, it falls back to standard business hours and tells you.

**What you see.** In Analytics → Learning Insights, the "Best time to send" card shows the top 3 slots and their expected reply rates. As your campaigns run, this improves automatically.

---

## 2. Score Decay — "Don't let old data mislead you"

**The problem it solves.** Imagine you ran a campaign 18 months ago that got a 20% reply rate. Markets change. That 20% is still sitting in your playbook and making a 15% rate from last week look bad by comparison. Old data should count less.

**How it works.** Every outcome (reply, meeting) is weighted by *how recently it happened*. The formula is similar to how physicists model radioactive decay: after 90 days (the default "half-life"), an outcome counts half as much as today's. After 180 days, a quarter as much. The system uses this weighted average instead of a simple count.

The playbook also now shows an "effective sample size" — which can be less than the actual number of emails sent, because old emails count less. If your effective sample is below 30, the system treats the pattern as unproven and won't auto-promote based on it.

You'll see a `trend` label next to each pattern: **rising** (recent results beating historical average), **falling**, or **stable**.

---

## 3. Multi-Variate Testing — "Test A, B, and C at once"

**The problem it solves.** Standard A/B testing compares two things at a time. But what if you want to test three subject lines, four different offers, and two send times simultaneously? Running separate A/B tests takes weeks; multi-variate testing does it in one campaign.

**How it works.** You set up up to 5 variants of your outreach message. The system automatically splits leads across them. When enough data accumulates, it runs statistical analysis (Kruskal-Wallis test, if you want the name) to detect whether the variants perform differently, then does pairwise comparisons with a Bonferroni correction — a technique that prevents you from being fooled by random luck when testing many pairs at once.

A winner is only declared when **four conditions** are all true:
1. The overall difference is statistically significant (not random)
2. The best variant beats the runner-up by at least 10% (not just barely)
3. The pairwise comparison confirms the winner specifically
4. The winning variant's unsubscribe rate isn't elevated

**What you see.** On the Campaign page, "Variant Performance" shows a ranked table of all variants with their meeting rates, which pairs are statistically significant, and a plain-English recommendation ("Promote variant B — 18% vs 11% for A, all gates passed").

---

## 4. Subject Line Intelligence — "Learn what words actually work"

**The problem it solves.** AI generates subject lines using general best practices. But *your* campaigns might have discovered that questions work better than numbers for your ICP, or that mentioning the company name doubles the reply rate. That pattern should feed back into every future campaign.

**How it works.** Every night, the system reads all your sent emails and classifies each subject line into structural patterns:
- Ends with a question ("Struggling with X?")
- Contains a number ("3 ways to improve Y")
- Personalised with company name ("{Company}, quick question")
- Pain-point hook ("Losing clients to Z?")
- Curiosity gap opener ("What most [industry] companies miss about...")
- Social proof mention ("How 12 companies reduced X")
- Direct offer ("Free audit for {Company}")
- Short (≤ 6 words) or long (> 10 words)

It then calculates the average reply rate and meeting rate per pattern. From campaign 20+ onward, when your AI generates subject lines for a new campaign, it's told: *"For your ICP, pain-point hooks have 18% reply rate and short subject lines have 12% — prefer those."*

**What you see.** In Analytics → Learning Insights, the "What makes subject lines work" card shows the top patterns ranked by meeting rate.

---

## How these four features work together

Here's the full loop in plain English:

1. You run campaign → leads reply or book meetings.
2. **Score decay** ensures last month's results matter more than last year's.
3. **Send-time optimizer** notes *when* replies came in and updates the recommendation.
4. **Subject intelligence** classifies what made those subject lines work.
5. Next campaign: AI uses the learned patterns + preferred send times to write better messages, scheduled at better times.
6. **Multi-variate testing** runs when you have multiple variants, automatically picking the winner and making it default.

The system gets meaningfully smarter after roughly 200–300 sent emails across varied campaigns, and continues improving indefinitely.

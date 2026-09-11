# Feature Group 3 — Analytics & revenue intelligence

## Revenue & ROI (Analytics › Revenue & ROI)
Per campaign, for a chosen period (30 days, 90 days, 12 months, year to date):

| Figure | Source |
|---|---|
| Revenue | Won deals (`deals.stage = won`), dated by `close_date` (else last update) |
| Meetings | Distinct leads with a `booked` outcome in the period |
| Cost | Recorded costs + metered AI usage + AI-call minutes + a share of account-wide costs |
| Cost per meeting / per closed deal | Cost ÷ meetings / ÷ deals won (blank when zero) |
| ROI | (revenue − cost) ÷ cost (blank when there is no cost) |

**Where the costs come from**
- *Recorded costs* (`POST /costs`): data, tools, ads, and time (hours × rate).
  A cost with no campaign is account-wide, and is spread across campaigns in
  proportion to their sends in the period.
- *Metered AI usage* (`api_usage`): every Claude and OpenAI call made while
  running the pipeline or verification, rendering a send, scoring leads,
  writing a meeting brief or analysing a call is attributed to its campaign.
  Tokens are priced with the estimates in Admin › System Settings
  (`claude_*_cost_per_mtok`, `openai_*_cost_per_mtok`), fixed at the time of
  the call. Calls made outside those paths are not metered.
- *AI calls*: call duration × `voice_cost_per_minute`.

**Currency.** The report uses the user's most common deal currency (USD when
there are no deals). Deals and costs in other currencies are left out and
counted in a notice, never converted. Metered AI and call costs are USD, so
they are only included in a USD report.

## Email open tracking
Outreach email gains an HTML alternative (same text, links clickable) with a
1×1 pixel at `/t/o/<signed token>.gif`. The plain-text part stays first.

- The first real open writes one `opened` outcome, on the lead's local clock
  (day of week and hour); later loads only increase `messages.open_count`.
- Loads within `open_prefetch_seconds` (default 60) of sending are ignored:
  mail security scanners fetch images on delivery.
- **No pixel for EU/EEA/UK leads** — under ePrivacy/PECR a tracking pixel
  needs consent. The region comes from the lead's enrichment country, falling
  back to timezone (`app/services/compliance_region.py`). Admins can turn
  tracking off entirely (`open_tracking_enabled`).
- Opens are directional: Apple Mail Privacy Protection loads images for
  unread mail and image-blocking clients never register. Replies remain the
  ground truth.

## Funnel heatmap (Campaigns › Funnel)
One row per sequence step: sent, open rate (email/WhatsApp only), reply rate,
booking rate, drop-off rate, and leads still waiting. Replies and bookings
without a message link count toward the last step the lead received before
responding. "Dropped off" means the lead's enrollment ended after this step
without a reply or booking. The best step is named once a step has been sent
to at least 20 leads.

## Smart send time (Campaigns › Overview)
- Every open and reply is placed on the lead's local clock. A slot's score is
  opens + 3 × replies.
- Once the campaign has `send_time_min_opens` opens (default 50), the top 3
  slots **inside the send window** become its windows — immediately when the
  threshold is crossed, then nightly.
- With the toggle on, each newly scheduled step is held until the next window
  (spread over the first 45 minutes of the hour), never more than
  `send_time_max_delay_hours` (default 72) past its normal time. Turning it on
  also moves already-scheduled steps; turning it off leaves them in place.

## Reply sentiment (Campaigns › Sentiment)
Weekly (Monday-start) share of human replies by class: interested, question,
objection, not interested, unsubscribe. Out-of-office, bounces and automated
responses are excluded. A Monday Beat job stores the last complete week and
raises an **objection spike** alert (push, Slack, webhooks) when, with at
least `objection_spike_min_replies` replies in both weeks, the objection rate
rose by more than `objection_spike_threshold` (20%) **and** by at least 5
percentage points. Each campaign-week alerts once.

## Repaired along the way
The M8 cross-campaign send-time optimizer (`send_time_optimizer.py`, shown in
the Analytics page's "Best time to send" card) queried columns that do not
exist and failed every night; it now runs on the ORM, counts a reply in the
slot its message was sent in, and answers the card's `gmail` channel.
`app/workers/send_tasks.py` (M8-C4) is still unused legacy raw SQL and is
not part of the send path.

## Background jobs (learning queue)
| Task | Schedule |
|---|---|
| `analytics_tasks.compute_send_windows` | When a campaign crosses the open threshold |
| `analytics_tasks.refresh_send_windows` | Daily, aggregation hour :15 |
| `analytics_tasks.aggregate_reply_sentiment` | Mondays, aggregation hour :25 |

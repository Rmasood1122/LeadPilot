# Transparent Attribution Ledger (Part 1, Feature 8)

**Migration** `0060_attribution_ledger` ·
**Service** `app/services/attribution.py` · **API** `app/api/attribution.py` ·
**Task** `app.workers.analytics_tasks.run_attribution_sweep` (every 15 min) ·
**UI** `frontend/src/lib/attribution.ts`,
`components/analytics/AttributionPanel.tsx`

## The question, and the usual dishonest answer

A meeting got booked. **Which message earned it?**

Every outbound tool answers this the same way: credit the last thing sent,
present it as fact, and let the user build a sequence strategy on it. That is
*fine* when the prospect literally replied to that message and a *guess* when
they did not — and the two are indistinguishable in the output, so the guess
gets believed.

## The four methods, always recorded

| Method | What happened | Confidence |
|--------|---------------|-----------|
| `direct_reply` | Their reply is linked to a specific message (`InboundReply.message_id`). **This is not attribution, it is a fact.** | 1.0 |
| `thread_match` | Their reply carries the same provider `thread_ref` as one of our messages. Evidence, one link weaker. | 0.85 |
| `last_touch` | No reply is linked, so the most recent message sent **before** the outcome is credited. The industry default, and **a guess**. | decays with the gap |
| `none` | Nothing was sent before the outcome. An inbound booking from someone we never messaged has no touch to credit, and **saying so is the correct answer**. | 0.0 |

Last-touch confidence decays deliberately: **0.7** within a day, **0.55** within
three, **0.4** within a week, **0.25** within a month, **0.1** beyond. A booking
two hours after a send is far more likely to be that send's doing than one three
weeks later, and the number says so.

Every entry also stores its **evidence** — the sentences explaining the choice
— and a **snapshot of the copy** that went out, so "which message earned this?"
can be answered by *showing it*, even after the message row is re-rendered or
deleted.

## Why a ledger and not a column on `outcomes`

`outcomes` is the immutable event log the learning loop reads. Its `message_id`
is the message that *caused* the event only for events the send path writes
itself (sent, opened, clicked); a booking arriving by webhook three days later
has no `message_id` and no way to get one at write time.

Attribution is a separate, **later, re-computable** judgement — and one that has
to record its own uncertainty, which an immutable log row cannot.

Nothing cascades: every foreign key is `ON DELETE SET NULL`. A ledger that
deletes itself when the prospect or the message is removed cannot answer "what
worked last year?".

## Why a sweep and not hooks

Outcomes are created in a dozen places — the Calendly webhook, our own booking
page, the reply router, meeting outcomes, the CRM deal sync. A hook in each is
a hook that will be forgotten in the thirteenth.

One idempotent sweep over outcomes with no ledger entry covers every path, past
and future, and **back-fills history for free**.
`UNIQUE(outcome_kind, outcome_id)` is what makes running it forever safe — it
literally cannot double-credit, so the quarter-hourly cadence costs nothing but
the scan.

## Which outcomes are credited

`BOOKED` → `meeting_booked`, `WON` → `won`, `REPLIED` → `positive_reply`.

**A `REPLIED` outcome only earns an entry when Feature 1 labelled the reply
`interested`.** Crediting every reply would put "stop emailing me" in the same
ledger as a booking — exactly the dishonesty this feature exists to remove. An
unclassified reply is not credited either.

## The summary

`GET /attribution/summary` groups by step and by channel, and **every bucket
carries its own `certain` count** beside its total. An aggregate built mostly
from last-touch guesses is a very different claim from one built from replies,
and the caller can see that without reading rows. The UI raises a caveat above
the aggregate when fewer than half the entries are confirmed.

## API

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/attribution?outcome_kind=&strategy_id=&limit=&offset=` | Newest outcome first |
| `GET` | `/attribution/summary?strategy_id=` | By step, by channel, by method |
| `POST` | `/attribution/recompute` | Runs the sweep now; safe to press repeatedly |
| `GET` | `/leads/{id}/attribution` | With the message text itself |

## Tests

`tests/test_attribution.py` (38) — a linked reply beating a more recent send,
thread matching, last-touch confidence decay, a message sent *after* the
outcome never being credited, "nothing was sent" as an answer, sweep
idempotency and history back-fill, only positive replies earning an entry, and
the summary's `certain` counts. `tests/test_attribution_migration.py` (7) —
including that nothing cascades. `frontend/src/tests/attribution.test.ts` (19).

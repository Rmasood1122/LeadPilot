"""Weekly reply sentiment per campaign, and the objection-spike alert.

WHAT COUNTS
Human replies only, bucketed from the reply classifier's labels:
    interested -> interested        question -> question
    objection  -> objection         not_interested -> not interested
    unsubscribe_request -> unsubscribe
Out-of-office, bounces and automated responses (Feature Group 9's fraud
check) are not sentiment and are left out -- a holiday week full of
auto-replies must not read as "nobody is objecting".

Weeks start Monday (UTC), keyed by the reply's received time.

THE SPIKE RULE
Last complete week vs the week before. It alerts when, with at least
`objection_spike_min_replies` human replies in BOTH weeks,
    objection_rate rose by more than `objection_spike_threshold` (relative,
    0.20 = 20%) AND by at least 5 percentage points.
The relative test is the spec; the absolute floor stops 4% -> 5% (a 25%
"increase", one extra reply) paging anyone. A week that had no objections
at all alerts on the absolute floor alone. Each campaign-week alerts once
(reply_sentiment_weeks.alerted_at).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import InboundReply, Lead, ReplySentimentWeek, Strategy

BUCKETS = {
    "interested": "interested",
    "question": "question",
    "objection": "objection",
    "not_interested": "not_interested",
    "unsubscribe_request": "unsubscribe",
}
FIELDS = ("interested", "question", "objection", "not_interested", "unsubscribe")
ABSOLUTE_FLOOR = 0.05


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _empty(ws: date) -> dict:
    return {"week_start": ws, "total": 0, **{f: 0 for f in FIELDS},
            "objection_rate": None, "interested_rate": None}


def weekly_breakdown(session: Session, strategy_id, *, weeks: int = 12,
                     now: datetime | None = None, include_current: bool = True) -> list[dict]:
    """Oldest first; weeks with no replies are present with zeros, so a chart
    shows a gap as a gap rather than joining the points around it."""
    now = now or datetime.now(timezone.utc)
    last = week_start(now.date())
    if not include_current:
        last -= timedelta(days=7)
    first = last - timedelta(weeks=weeks - 1)
    since = datetime.combine(first - timedelta(days=7), time.min, tzinfo=timezone.utc)
    rows = session.execute(
        select(InboundReply.classification, InboundReply.received_at, InboundReply.created_at)
        .join(Lead, Lead.id == InboundReply.lead_id)
        .where(Lead.strategy_id == strategy_id,
               InboundReply.classification.in_(list(BUCKETS)),
               InboundReply.created_at >= since)
    ).all()
    buckets = {first + timedelta(weeks=i): _empty(first + timedelta(weeks=i))
               for i in range(weeks)}
    for classification, received, created in rows:
        ts = received or created
        if ts is None:
            continue
        week = buckets.get(week_start(_aware(ts).date()))
        if week is None:
            continue
        week[BUCKETS[classification]] += 1
        week["total"] += 1
    for week in buckets.values():
        if week["total"]:
            week["objection_rate"] = round(week["objection"] / week["total"], 4)
            week["interested_rate"] = round(week["interested"] / week["total"], 4)
    return [buckets[k] for k in sorted(buckets)]


def is_spike(prev: dict, cur: dict, *, threshold: float, min_replies: int) -> bool:
    if prev["total"] < min_replies or cur["total"] < min_replies:
        return False
    p = prev["objection_rate"] or 0.0
    c = cur["objection_rate"] or 0.0
    # The epsilon matters: 0.25 - 0.20 is 0.04999... in binary floating
    # point, and without it an exact five-point rise would never alert.
    if c - p < ABSOLUTE_FLOOR - 1e-9:
        return False
    return p == 0 or (c - p) / p > threshold


def _upsert(session: Session, strategy_id, week: dict) -> ReplySentimentWeek:
    row = session.execute(
        select(ReplySentimentWeek).where(ReplySentimentWeek.strategy_id == strategy_id,
                                         ReplySentimentWeek.week_start == week["week_start"])
    ).scalar_one_or_none()
    if row is None:
        row = ReplySentimentWeek(strategy_id=strategy_id, week_start=week["week_start"])
        session.add(row)
    row.total = week["total"]
    for field in FIELDS:
        setattr(row, field, week[field])
    row.objection_rate = week["objection_rate"]
    return row


def _alert(session: Session, strategy: Strategy, prev: dict, cur: dict) -> None:
    from app.services import notifications  # noqa: PLC0415
    from app.workers import notification_tasks  # noqa: PLC0415

    owner = notifications.owner_of_strategy(session, strategy)
    if owner is None:
        return
    name = strategy.product.name if strategy.product else "Your campaign"
    p, c = prev["objection_rate"] or 0.0, cur["objection_rate"] or 0.0
    body = (f"{name}: objections rose from {p:.0%} to {c:.0%} of replies in the week of "
            f"{cur['week_start'].isoformat()} ({cur['objection']} of {cur['total']}). "
            "Review what prospects are pushing back on and adjust the messaging.")
    notification_tasks.enqueue_event(
        owner, "objection_spike",
        title="Objection rate is spiking",
        body=body,
        deep_link=f"/campaigns?strategy={strategy.id}&tab=sentiment",
        data={"strategyId": str(strategy.id), "weekStart": cur["week_start"].isoformat()},
        webhook_payload={"strategy_id": str(strategy.id),
                         "week_start": cur["week_start"].isoformat(),
                         "objection_rate": c, "previous_objection_rate": p,
                         "replies": cur["total"]},
    )


def aggregate_and_alert(session: Session, now: datetime | None = None) -> dict:
    """The weekly Beat job: persist the last two complete weeks for every
    campaign with replies in them, alert on a spike. Idempotent."""
    from app.services import system_settings  # noqa: PLC0415

    now = now or datetime.now(timezone.utc)
    threshold = system_settings.get(session, "objection_spike_threshold")
    min_replies = system_settings.get(session, "objection_spike_min_replies")
    prev_week = week_start(now.date()) - timedelta(days=14)
    since = datetime.combine(prev_week - timedelta(days=7), time.min, tzinfo=timezone.utc)
    strategy_ids = session.execute(
        select(Lead.strategy_id).join(InboundReply, InboundReply.lead_id == Lead.id)
        .where(InboundReply.created_at >= since).distinct()
    ).scalars().all()

    alerts = 0
    for strategy_id in strategy_ids:
        prev, cur = weekly_breakdown(session, strategy_id, weeks=2, now=now,
                                     include_current=False)
        _upsert(session, strategy_id, prev)
        row = _upsert(session, strategy_id, cur)
        if row.alerted_at is None and is_spike(prev, cur, threshold=threshold,
                                               min_replies=min_replies):
            strategy = session.get(Strategy, strategy_id)
            if strategy is not None:
                _alert(session, strategy, prev, cur)
                row.alerted_at = now
                alerts += 1
    session.commit()
    return {"strategies": len(strategy_ids), "alerts": alerts}


def trend(session: Session, strategy_id, *, weeks: int = 12,
          now: datetime | None = None) -> dict:
    """What the sentiment chart reads: live weekly numbers (including the
    current, partial week) plus which weeks have alerted."""
    from app.services import system_settings  # noqa: PLC0415

    series = weekly_breakdown(session, strategy_id, weeks=weeks, now=now)
    alerted = {
        r.week_start: r.alerted_at for r in session.execute(
            select(ReplySentimentWeek).where(ReplySentimentWeek.strategy_id == strategy_id,
                                             ReplySentimentWeek.alerted_at.isnot(None))
        ).scalars()
    }
    current = week_start((now or datetime.now(timezone.utc)).date())
    for week in series:
        week["alerted"] = week["week_start"] in alerted
        week["partial"] = week["week_start"] == current
        week["week_start"] = week["week_start"].isoformat()
    return {
        "weeks": series,
        "threshold": system_settings.get(session, "objection_spike_threshold"),
        "min_replies": system_settings.get(session, "objection_spike_min_replies"),
    }

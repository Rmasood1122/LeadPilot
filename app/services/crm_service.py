"""M9 CRM service layer: ownership, aggregation queries, value coercion.

Everything the /crm router needs that is not HTTP. Kept out of app/api/crm.py
so the router stays a thin, readable list of endpoints, and so the aggregation
queries -- the part with real behaviour worth testing -- can be exercised
directly against a session without going through TestClient.

TWO RULES THIS MODULE ENFORCES THROUGHOUT

1. Every query is scoped by owner, through the same lead -> strategy ->
   product -> user_id chain app/api/leads.py::_owned_lead walks. There is no
   "read all leads" query in here; the owner join is in the base selectable
   so it cannot be forgotten at a call site.

2. Aggregation happens in SQL. `func.count`/`func.avg` grouped by stage,
   source, channel or bucket -- never a Python loop over every row. A
   dashboard that loads 5,000 leads into memory to count them is fine at
   demo scale and falls over at the scale this product is sold for.

DIALECT PORTABILITY
Date bucketing is spelled differently on the two dialects this runs on
(SQLite in the test suite, PostgreSQL in production). `_date_bucket` branches
exactly the way app/api/analytics.py already does; nothing else in here needs
a dialect branch.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence

from fastapi import HTTPException
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    ChannelType,
    CrmActivity,
    CrmActivityKind,
    CrmCustomField,
    CrmCustomFieldValue,
    CrmFieldType,
    CrmLeadMeta,
    CrmLeadTag,
    CrmNote,
    CrmTag,
    Lead,
    LeadStatus,
    Message,
    MessageStatus,
    Outcome,
    OutcomeEvent,
    Product,
    Sequence as SequenceModel,
    SequenceStep,
    Strategy,
    User,
)

# The funnel, in order. `dropped` is deliberately NOT a funnel stage: it is an
# exit, and drawing it as a step would make the conversion rate between
# `verified` and `contacted` read as if dropped leads were still in flight.
FUNNEL_STAGES: list[LeadStatus] = [
    LeadStatus.SOURCED,
    LeadStatus.ENRICHED,
    LeadStatus.EMAIL_FOUND,
    LeadStatus.VERIFIED,
    LeadStatus.CONTACTED,
    LeadStatus.REPLIED,
    LeadStatus.MEETING_BOOKED,
]

# Terminal stages: a lead sitting here is finished, not stuck. Excluded from
# stuck-lead detection, which would otherwise report every booked meeting and
# every dropped address as a problem forever.
TERMINAL_STAGES = {LeadStatus.DROPPED, LeadStatus.MEETING_BOOKED}


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------


def owned_lead(db: Session, lead_id: uuid.UUID, current_user: User) -> Lead:
    """Fetch a lead owned by current_user, else 404.

    Identical semantics to app/api/leads.py::_owned_lead, including answering
    404 (never 403) for someone else's lead so that existence cannot be
    inferred from the status code. Duplicated deliberately rather than
    imported: app/api/leads.py is a router module, and importing a router to
    get at a helper couples the two at import time for no gain.
    """
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="lead not found")
    strategy = db.get(Strategy, lead.strategy_id)
    product = db.get(Product, strategy.product_id) if strategy else None
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead


def owned_strategy(db: Session, strategy_id: uuid.UUID,
                   current_user: User) -> Strategy:
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    product = db.get(Product, strategy.product_id)
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="strategy not found")
    return strategy


def owned_leads_subquery(current_user: User,
                         strategy_id: uuid.UUID | None = None):
    """Every lead id this user owns, as a scalar subquery.

    The single place tenant scoping is expressed for the dashboard
    aggregations. They all filter `Lead.id.in_(owned_leads_subquery(...))` or
    join through `_owned_leads_join`, so none of them can accidentally
    aggregate across accounts.
    """
    q = (
        select(Lead.id)
        .join(Strategy, Strategy.id == Lead.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == current_user.id)
    )
    if strategy_id is not None:
        q = q.where(Lead.strategy_id == strategy_id)
    return q.scalar_subquery()


def owned_leads_select(current_user: User,
                       strategy_id: uuid.UUID | None = None) -> Select:
    """`SELECT ... FROM leads JOIN strategies JOIN products` pre-filtered to
    this user. Callers add their own columns via `.with_only_columns()`."""
    q = (
        select(Lead)
        .join(Strategy, Strategy.id == Lead.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == current_user.id)
    )
    if strategy_id is not None:
        q = q.where(Lead.strategy_id == strategy_id)
    return q


def _date_bucket(db: Session, column, granularity: str = "day"):
    """Portable date truncation. Same branch app/api/analytics.py uses."""
    if db.get_bind().dialect.name == "postgresql":
        fmt = {"day": "YYYY-MM-DD", "week": "IYYY-IW", "month": "YYYY-MM"}[granularity]
        return func.to_char(column, fmt)
    fmt = {"day": "%Y-%m-%d", "week": "%Y-%W", "month": "%Y-%m"}[granularity]
    return func.strftime(fmt, column)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes even for DateTime(timezone=True).

    Subtracting a naive from an aware datetime raises, so every duration in
    this module goes through here first. PostgreSQL returns aware values and
    this is a no-op there.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# ---------------------------------------------------------------------------
# Dashboard page 1 — pipeline overview
# ---------------------------------------------------------------------------


def dashboard_pipeline(db: Session, current_user: User,
                       strategy_id: uuid.UUID | None = None) -> dict:
    """Funnel by stage, stage-to-stage conversion, bookings, trend, top strategy.

    CONVERSION IS CUMULATIVE, NOT COLUMN-TO-COLUMN. A lead that reached
    `replied` is no longer counted in `contacted` -- status is a single
    current value, not a set of stages passed through. So dividing the
    `replied` column by the `contacted` column would report a reply rate of
    over 100% the moment more leads have replied than are currently sitting
    unanswered. Each stage's "reached" figure is therefore the count of leads
    at that stage OR any later one, and conversion is the ratio of successive
    reached counts -- which is what a funnel actually means.
    """
    owned = owned_leads_subquery(current_user, strategy_id)

    counts = dict(
        db.execute(
            select(Lead.status, func.count(Lead.id))
            .where(Lead.id.in_(owned))
            .group_by(Lead.status)
        ).all()
    )
    by_status = {s.value: int(counts.get(s, 0)) for s in LeadStatus}

    # Cumulative "reached this stage or beyond", walking the funnel backwards.
    reached: dict[str, int] = {}
    running = 0
    for stage in reversed(FUNNEL_STAGES):
        running += int(counts.get(stage, 0))
        reached[stage.value] = running

    funnel = []
    for index, stage in enumerate(FUNNEL_STAGES):
        prior = reached[FUNNEL_STAGES[index - 1].value] if index else None
        here = reached[stage.value]
        funnel.append({
            "stage": stage.value,
            "current": by_status[stage.value],
            "reached": here,
            "conversion_from_previous": (
                round(here / prior, 4) if prior else None
            ),
        })

    now = _utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    def _booked_since(since: datetime) -> int:
        return int(db.execute(
            select(func.count(Outcome.id)).where(
                Outcome.lead_id.in_(owned),
                Outcome.event == OutcomeEvent.BOOKED,
                Outcome.ts >= since,
            )
        ).scalar_one())

    # 30-day daily trend of bookings, aggregated in SQL.
    bucket = _date_bucket(db, Outcome.ts, "day")
    trend_rows = db.execute(
        select(bucket.label("bucket"), func.count(Outcome.id))
        .where(
            Outcome.lead_id.in_(owned),
            Outcome.event == OutcomeEvent.BOOKED,
            Outcome.ts >= month_ago,
        )
        .group_by("bucket")
        .order_by("bucket")
    ).all()

    # Top strategy by bookings. Uses outcomes.strategy_id where it is set and
    # falls back to the lead join, because that column was only denormalized
    # from migration 0008 onward and older rows have it NULL.
    top_rows = db.execute(
        select(Strategy.id, Product.name, func.count(Outcome.id).label("booked"))
        .select_from(Outcome)
        .join(Lead, Lead.id == Outcome.lead_id)
        .join(Strategy, Strategy.id == Lead.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == current_user.id,
               Outcome.event == OutcomeEvent.BOOKED)
        .group_by(Strategy.id, Product.name)
        .order_by(func.count(Outcome.id).desc())
        .limit(1)
    ).all()

    active = sum(
        by_status[s.value] for s in LeadStatus if s not in TERMINAL_STAGES
    )

    return {
        "strategy_id": str(strategy_id) if strategy_id else None,
        "total_leads": sum(by_status.values()),
        "active_leads": active,
        "by_status": by_status,
        "funnel": funnel,
        "meetings_booked_week": _booked_since(week_ago),
        "meetings_booked_month": _booked_since(month_ago),
        "bookings_trend": [
            {"bucket": b, "count": int(n)} for b, n in trend_rows
        ],
        "top_strategy": (
            {
                "strategy_id": str(top_rows[0][0]),
                "product_name": top_rows[0][1],
                "meetings_booked": int(top_rows[0][2]),
            }
            if top_rows else None
        ),
    }


# ---------------------------------------------------------------------------
# Dashboard page 2 — lead analytics
# ---------------------------------------------------------------------------


def dashboard_leads(db: Session, current_user: User,
                    strategy_id: uuid.UUID | None = None,
                    stuck_after_days: int = 7) -> dict:
    """Velocity, source mix, verification quality, stuck leads.

    ON `estimated` IN THE VELOCITY PAYLOAD
    Time-in-stage needs the moment the current status was entered. Before M9
    nothing recorded it: `leads.updated_at` moves on any write, including an
    enrichment refresh that says nothing about the stage. crm_lead_meta.
    stage_entered_at carries the real value from the first status change after
    M9 ships, and migration 0019 deliberately does not backfill it.

    So each stage reports how many of its leads have a real measurement and
    how many fell back to updated_at. A single blended average with no such
    marker would look authoritative while being partly made up -- which is
    worse than an honest one, because nobody would know to distrust it.
    """
    owned = owned_leads_subquery(current_user, strategy_id)
    now = _utcnow()

    rows = db.execute(
        select(Lead.id, Lead.status, Lead.created_at, Lead.updated_at,
               CrmLeadMeta.stage_entered_at)
        .outerjoin(CrmLeadMeta, CrmLeadMeta.lead_id == Lead.id)
        .where(Lead.id.in_(owned))
    ).all()

    per_stage: dict[str, dict[str, Any]] = {}
    stuck: list[dict] = []
    for lead_id, status, created_at, updated_at, entered_at in rows:
        stage = status.value
        slot = per_stage.setdefault(
            stage, {"stage": stage, "leads": 0, "measured": 0,
                    "estimated": 0, "_total_days": 0.0}
        )
        slot["leads"] += 1
        reference = _as_aware(entered_at)
        if reference is not None:
            slot["measured"] += 1
        else:
            reference = _as_aware(updated_at) or _as_aware(created_at)
            slot["estimated"] += 1
        if reference is None:
            continue
        days = max((now - reference).total_seconds() / 86400.0, 0.0)
        slot["_total_days"] += days
        if status not in TERMINAL_STAGES and days >= stuck_after_days:
            stuck.append({
                "lead_id": str(lead_id),
                "status": stage,
                "days_in_stage": round(days, 1),
                "measured": entered_at is not None,
            })

    velocity = []
    for slot in per_stage.values():
        leads = slot.pop("leads")
        total = slot.pop("_total_days")
        velocity.append({
            **slot,
            "leads": leads,
            "avg_days_in_stage": round(total / leads, 2) if leads else 0.0,
            # True only when EVERY lead in the stage has a real measurement.
            "fully_measured": slot["estimated"] == 0,
        })
    velocity.sort(key=lambda v: v["stage"])

    source_rows = db.execute(
        select(Lead.source, func.count(Lead.id))
        .where(Lead.id.in_(owned))
        .group_by(Lead.source)
        .order_by(func.count(Lead.id).desc())
    ).all()

    # Verification quality: the Hunter verdict split. Only leads that actually
    # reached verification are counted -- including `sourced` rows in the
    # denominator would make a fresh batch look like a deliverability problem.
    verdicts = {LeadStatus.VERIFIED: 0, LeadStatus.FLAGGED: 0,
                LeadStatus.DROPPED: 0}
    verdict_rows = db.execute(
        select(Lead.status, func.count(Lead.id))
        .where(Lead.id.in_(owned), Lead.status.in_(list(verdicts)))
        .group_by(Lead.status)
    ).all()
    for status, count in verdict_rows:
        verdicts[status] = int(count)
    verdict_total = sum(verdicts.values())

    stuck.sort(key=lambda s: s["days_in_stage"], reverse=True)

    return {
        "strategy_id": str(strategy_id) if strategy_id else None,
        "velocity": velocity,
        "sources": [
            {"source": source, "count": int(count)}
            for source, count in source_rows
        ],
        "verification": {
            "verified": verdicts[LeadStatus.VERIFIED],
            "flagged": verdicts[LeadStatus.FLAGGED],
            "dropped": verdicts[LeadStatus.DROPPED],
            "total": verdict_total,
            "verified_ratio": (
                round(verdicts[LeadStatus.VERIFIED] / verdict_total, 4)
                if verdict_total else None
            ),
        },
        "stuck_after_days": stuck_after_days,
        "stuck_leads": stuck[:50],
        "stuck_count": len(stuck),
    }


# ---------------------------------------------------------------------------
# Dashboard page 3 — campaign / outreach performance
# ---------------------------------------------------------------------------


def dashboard_campaigns(db: Session, current_user: User,
                        strategy_id: uuid.UUID | None = None) -> dict:
    """Per-sequence and per-channel performance, variants, bounce vs threshold.

    Rates are computed against SENT + BOUNCED, matching what
    app/api/strategies.py::campaign_overview already calls "sent" -- a bounced
    message was dispatched, and excluding it from the denominator would
    flatter the reply rate exactly when deliverability is worst.
    """
    from app.config import settings

    owned = owned_leads_subquery(current_user, strategy_id)
    dispatched = [MessageStatus.SENT, MessageStatus.BOUNCED]

    # ---- per sequence ----------------------------------------------------
    sent_by_sequence = dict(db.execute(
        select(Message.sequence_id, func.count(Message.id))
        .where(Message.lead_id.in_(owned), Message.status.in_(dispatched))
        .group_by(Message.sequence_id)
    ).all())

    def _outcomes_by_sequence(target: OutcomeEvent) -> dict:
        return dict(db.execute(
            select(Message.sequence_id, func.count(Outcome.id))
            .select_from(Outcome)
            .join(Message, Message.id == Outcome.message_id)
            .where(Outcome.lead_id.in_(owned), Outcome.event == target)
            .group_by(Message.sequence_id)
        ).all())

    replied_by_sequence = _outcomes_by_sequence(OutcomeEvent.REPLIED)
    booked_by_sequence = _outcomes_by_sequence(OutcomeEvent.BOOKED)

    sequence_query = (
        select(SequenceModel.id, SequenceModel.name, SequenceModel.channel,
               SequenceModel.status, SequenceModel.strategy_id)
        .join(Strategy, Strategy.id == SequenceModel.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == current_user.id)
    )
    if strategy_id is not None:
        sequence_query = sequence_query.where(
            SequenceModel.strategy_id == strategy_id
        )
    sequence_rows = db.execute(sequence_query).all()

    sequences = []
    for seq_id, name, channel, status, seq_strategy in sequence_rows:
        sent = int(sent_by_sequence.get(seq_id, 0))
        replied = int(replied_by_sequence.get(seq_id, 0))
        booked = int(booked_by_sequence.get(seq_id, 0))
        sequences.append({
            "sequence_id": str(seq_id),
            "strategy_id": str(seq_strategy),
            "name": name,
            "channel": channel.value,
            "status": status.value,
            "sent": sent,
            "replied": replied,
            "booked": booked,
            "reply_rate": round(replied / sent, 4) if sent else None,
            "booking_rate": round(booked / sent, 4) if sent else None,
        })
    sequences.sort(key=lambda s: s["sent"], reverse=True)

    # ---- per channel -----------------------------------------------------
    channels = []
    for channel in (ChannelType.EMAIL, ChannelType.WHATSAPP):
        sent = int(db.execute(
            select(func.count(Message.id)).where(
                Message.lead_id.in_(owned),
                Message.channel == channel,
                Message.status.in_(dispatched),
            )
        ).scalar_one())

        def _events(target: OutcomeEvent) -> int:
            return int(db.execute(
                select(func.count(Outcome.id)).where(
                    Outcome.lead_id.in_(owned),
                    Outcome.event == target,
                    Outcome.channel == channel.value,
                )
            ).scalar_one())

        replied = _events(OutcomeEvent.REPLIED)
        booked = _events(OutcomeEvent.BOOKED)
        bounced = _events(OutcomeEvent.BOUNCED)
        channels.append({
            "channel": channel.value,
            "sent": sent,
            "replied": replied,
            "booked": booked,
            "bounced": bounced,
            "reply_rate": round(replied / sent, 4) if sent else None,
            "booking_rate": round(booked / sent, 4) if sent else None,
            "bounce_rate": round(bounced / sent, 4) if sent else None,
        })

    # ---- A/B variants ----------------------------------------------------
    # Reads the same (variant, event) shape ab_testing.py and multi_variate.py
    # aggregate from, so the dashboard and the promotion engine can never
    # disagree about which variant is ahead.
    variant_rows = db.execute(
        select(Message.variant, Outcome.event, func.count(Outcome.id))
        .select_from(Outcome)
        .join(Message, Message.id == Outcome.message_id)
        .where(Outcome.lead_id.in_(owned))
        .group_by(Message.variant, Outcome.event)
    ).all()
    variant_sent = dict(db.execute(
        select(Message.variant, func.count(Message.id))
        .where(Message.lead_id.in_(owned), Message.status.in_(dispatched))
        .group_by(Message.variant)
    ).all())

    variants: dict[str, dict[str, Any]] = {}
    for variant, event_name, count in variant_rows:
        slot = variants.setdefault(variant, {"variant": variant})
        slot[event_name.value] = int(count)
    for variant, sent in variant_sent.items():
        slot = variants.setdefault(variant, {"variant": variant})
        slot["sent"] = int(sent)
    variant_list = []
    for slot in variants.values():
        sent = int(slot.get("sent", 0))
        replied = int(slot.get("replied", 0))
        booked = int(slot.get("booked", 0))
        variant_list.append({
            **slot,
            "sent": sent,
            "replied": replied,
            "booked": booked,
            "reply_rate": round(replied / sent, 4) if sent else None,
            "booking_rate": round(booked / sent, 4) if sent else None,
        })
    variant_list.sort(key=lambda v: v["variant"])

    # ---- bounce vs the auto-pause threshold ------------------------------
    total_sent = sum(c["sent"] for c in channels)
    total_bounced = sum(c["bounced"] for c in channels)
    threshold = float(getattr(settings, "bounce_rate_pause_threshold", 0.03))
    bounce_rate = (total_bounced / total_sent) if total_sent else 0.0

    paused = db.execute(
        select(Strategy.id, Strategy.campaign_state,
               Strategy.campaign_pause_reason, Product.name)
        .join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == current_user.id,
               Strategy.campaign_state != "active")
    ).all()

    return {
        "strategy_id": str(strategy_id) if strategy_id else None,
        "sequences": sequences,
        "channels": channels,
        "variants": variant_list,
        "bounce": {
            "sent": total_sent,
            "bounced": total_bounced,
            "rate": round(bounce_rate, 4),
            "pause_threshold": threshold,
            "over_threshold": bounce_rate > threshold,
        },
        "paused_campaigns": [
            {"strategy_id": str(sid), "campaign_state": state,
             "reason": reason, "product_name": product_name}
            for sid, state, reason, product_name in paused
        ],
    }


# ---------------------------------------------------------------------------
# Dashboard page 4 — activity feed
# ---------------------------------------------------------------------------


def encode_activity_cursor(ts: datetime, activity_id: uuid.UUID) -> str:
    """Opaque cursor: the full sort key, not just the timestamp."""
    return f"{ts.isoformat()}|{activity_id}"


def decode_activity_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    raw_ts, _, raw_id = cursor.partition("|")
    try:
        return (datetime.fromisoformat(raw_ts.replace("Z", "+00:00")),
                uuid.UUID(raw_id))
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid activity cursor")


def dashboard_activity(db: Session, current_user: User,
                       strategy_id: uuid.UUID | None = None,
                       lead_id: uuid.UUID | None = None,
                       kinds: Sequence[str] | None = None,
                       limit: int = 50, before: str | None = None) -> dict:
    """Account-wide activity feed, newest first, keyset-paginated.

    KEYSET, NOT OFFSET. This is a live feed: rows arrive at the head while the
    user is paging. With OFFSET, every insert shifts the window down by one
    and page 2 re-shows a row from page 1.

    THE CURSOR IS (ts, id), NOT ts ALONE. Timestamps tie, routinely, on both
    dialects for different reasons: SQLite's CURRENT_TIMESTAMP has one-second
    resolution, and PostgreSQL's now() is transaction-scoped, so every row
    written by one request shares a value. A `ts <` cursor then either skips
    the rest of a tied group or repeats it, depending on where the page
    boundary happened to land -- which is exactly the bug OFFSET was avoided
    to prevent. Comparing the whole sort key lexicographically
    (`ts < t OR (ts = t AND id < i)`) makes the cursor exact: the ORDER BY and
    the WHERE now agree on a total order.
    """
    owned = owned_leads_subquery(current_user, strategy_id)

    where = [CrmActivity.lead_id.in_(owned)]
    if lead_id is not None:
        owned_lead(db, lead_id, current_user)
        where.append(CrmActivity.lead_id == lead_id)
    if strategy_id is not None:
        where.append(CrmActivity.strategy_id == strategy_id)
    if kinds:
        where.append(CrmActivity.kind.in_(list(kinds)))
    if before:
        cursor_ts, cursor_id = decode_activity_cursor(before)
        where.append(or_(
            CrmActivity.ts < cursor_ts,
            and_(CrmActivity.ts == cursor_ts, CrmActivity.id < cursor_id),
        ))

    rows = db.execute(
        select(CrmActivity, Lead.full_name, Lead.company, Lead.email)
        .join(Lead, Lead.id == CrmActivity.lead_id)
        .where(*where)
        .order_by(CrmActivity.ts.desc(), CrmActivity.id.desc())
        .limit(limit + 1)
    ).all()

    has_more = len(rows) > limit
    rows = rows[:limit]
    last_activity = rows[-1][0] if rows else None

    items = [
        {
            "id": str(activity.id),
            "lead_id": str(activity.lead_id),
            "strategy_id": (str(activity.strategy_id)
                            if activity.strategy_id else None),
            "kind": activity.kind.value,
            "from_value": activity.from_value,
            "to_value": activity.to_value,
            "meta": activity.meta_json,
            "ts": activity.ts.isoformat() if activity.ts else None,
            # NULL actor means the pipeline did it, not a person.
            "actor_user_id": (str(activity.actor_user_id)
                              if activity.actor_user_id else None),
            "lead": {"full_name": full_name, "company": company,
                     "email": email},
        }
        for activity, full_name, company, email in rows
    ]
    return {
        "items": items,
        "has_more": has_more,
        "next_before": (
            encode_activity_cursor(last_activity.ts, last_activity.id)
            if last_activity is not None and has_more else None
        ),
    }


# ---------------------------------------------------------------------------
# Activity + note writing
# ---------------------------------------------------------------------------


def log_activity(db: Session, lead: Lead, kind: CrmActivityKind,
                 actor: User | None = None, from_value: str | None = None,
                 to_value: str | None = None,
                 meta: dict | None = None) -> CrmActivity:
    """Append one activity row. Does NOT commit -- the caller owns the
    transaction, so an activity row can never outlive the change it describes.
    """
    activity = CrmActivity(
        lead_id=lead.id,
        strategy_id=lead.strategy_id,
        actor_user_id=actor.id if actor is not None else None,
        kind=kind,
        from_value=from_value[:200] if from_value else None,
        to_value=to_value[:200] if to_value else None,
        meta_json=meta,
    )
    db.add(activity)
    return activity


# ---------------------------------------------------------------------------
# Custom field values
# ---------------------------------------------------------------------------


def coerce_field_value(field: CrmCustomField, raw: Any) -> tuple[str | None, dict | None]:
    """Validate a raw value against its definition; return (value_text, value_json).

    `value_text` is the canonical sortable form and is always populated for a
    non-null value:
      * numbers are zero-padded to a fixed width so that lexical ordering
        matches numeric ordering -- "9" > "10" as text, which would silently
        mis-sort every numeric column in the grid;
      * dates are ISO-8601, which is lexically sortable by construction;
      * bools are "true"/"false".
    `value_json` keeps the typed original so a round-trip loses nothing.
    """
    if raw is None or raw == "":
        return None, None

    if field.field_type is CrmFieldType.NUMBER:
        try:
            number = float(raw)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=422,
                detail=f"field '{field.key}' expects a number",
            )
        # Offset by 1e12 so negatives sort below positives as text, then pad.
        # Range is +/- 1e12, which is far beyond anything a CRM column holds.
        if abs(number) >= 1e12:
            raise HTTPException(
                status_code=422,
                detail=f"field '{field.key}' is out of range (max 1e12)",
            )
        return f"{number + 1e12:026.6f}", {"value": number}

    if field.field_type is CrmFieldType.BOOL:
        if isinstance(raw, str):
            truthy = raw.strip().lower() in {"true", "1", "yes"}
        else:
            truthy = bool(raw)
        return ("true" if truthy else "false"), {"value": truthy}

    if field.field_type is CrmFieldType.DATE:
        if isinstance(raw, (datetime, date)):
            parsed = raw
        else:
            try:
                parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail=f"field '{field.key}' expects an ISO-8601 date",
                )
        return parsed.isoformat(), {"value": parsed.isoformat()}

    if field.field_type is CrmFieldType.SELECT:
        options = field.options_json or []
        if str(raw) not in options:
            raise HTTPException(
                status_code=422,
                detail=(f"field '{field.key}' expects one of "
                        f"{options}, got '{raw}'"),
            )
        return str(raw), {"value": str(raw)}

    text = str(raw)
    if len(text) > 500:
        raise HTTPException(
            status_code=422,
            detail=f"field '{field.key}' is limited to 500 characters",
        )
    return text, {"value": text}


def decode_field_value(value: CrmCustomFieldValue) -> Any:
    """The typed value, from value_json where present.

    Falls back to value_text for a row written before value_json existed or
    by anything that bypassed coerce_field_value.
    """
    if value.value_json and "value" in value.value_json:
        return value.value_json["value"]
    return value.value_text


def custom_values_for_leads(db: Session,
                            lead_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, dict]:
    """{lead_id: {field_key: typed_value}} for a page of leads.

    ONE query for the whole page, not one per lead. This is the concession
    the EAV design makes -- see the CrmCustomFieldValue docstring -- and it is
    bounded at a single `WHERE lead_id IN (...)`.
    """
    if not lead_ids:
        return {}
    rows = db.execute(
        select(CrmCustomFieldValue, CrmCustomField.key)
        .join(CrmCustomField, CrmCustomField.id == CrmCustomFieldValue.field_id)
        .where(CrmCustomFieldValue.lead_id.in_(list(lead_ids)))
    ).all()
    out: dict[uuid.UUID, dict] = {}
    for value, key in rows:
        out.setdefault(value.lead_id, {})[key] = decode_field_value(value)
    return out


def tags_for_leads(db: Session,
                   lead_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[dict]]:
    """{lead_id: [{id, name, color_token}]} for a page of leads. One query."""
    if not lead_ids:
        return {}
    rows = db.execute(
        select(CrmLeadTag.lead_id, CrmTag.id, CrmTag.name, CrmTag.color_token)
        .join(CrmTag, CrmTag.id == CrmLeadTag.tag_id)
        .where(CrmLeadTag.lead_id.in_(list(lead_ids)))
        .order_by(CrmTag.name)
    ).all()
    out: dict[uuid.UUID, list[dict]] = {}
    for lead_id, tag_id, name, color in rows:
        out.setdefault(lead_id, []).append(
            {"id": str(tag_id), "name": name, "color_token": color}
        )
    return out


def note_counts_for_leads(db: Session,
                          lead_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not lead_ids:
        return {}
    rows = db.execute(
        select(CrmNote.lead_id, func.count(CrmNote.id))
        .where(CrmNote.lead_id.in_(list(lead_ids)))
        .group_by(CrmNote.lead_id)
    ).all()
    return {lead_id: int(count) for lead_id, count in rows}


# ---------------------------------------------------------------------------
# Grid query
# ---------------------------------------------------------------------------

# Sortable/filterable built-in columns. An allow-list, not getattr(Lead, key):
# without it, a crafted `sort=password_hash` would order by -- and through a
# sort-order oracle, leak -- a column that is not supposed to be reachable.
GRID_COLUMNS: dict[str, Any] = {
    "full_name": Lead.full_name,
    "title": Lead.title,
    "company": Lead.company,
    "email": Lead.email,
    "phone": Lead.phone,
    "status": Lead.status,
    "source": Lead.source,
    "created_at": Lead.created_at,
    "updated_at": Lead.updated_at,
    "strategy_id": Lead.strategy_id,
}

_TEXT_COLUMNS = {"full_name", "title", "company", "email", "phone", "source"}

MAX_GRID_LIMIT = 200


def _apply_filters(query: Select, filters: dict) -> Select:
    """Translate the grid's filter dict into WHERE clauses.

    Shape: {"company": {"op": "contains", "value": "acme"},
            "status": {"op": "in", "value": ["verified", "contacted"]}}
    An unknown column is ignored rather than 422'd: a saved view built before
    a column was renamed should still open, minus that one filter, instead of
    erroring the whole grid.
    """
    for key, spec in (filters or {}).items():
        column = GRID_COLUMNS.get(key)
        if column is None or not isinstance(spec, dict):
            continue
        op = spec.get("op", "eq")
        value = spec.get("value")
        if value in (None, "", []):
            continue
        if op == "contains" and key in _TEXT_COLUMNS:
            query = query.where(column.ilike(f"%{value}%"))
        elif op == "in":
            values = value if isinstance(value, list) else [value]
            query = query.where(column.in_(values))
        elif op == "not_in":
            values = value if isinstance(value, list) else [value]
            query = query.where(~column.in_(values))
        elif op == "gte":
            query = query.where(column >= value)
        elif op == "lte":
            query = query.where(column <= value)
        elif op == "is_empty":
            query = query.where(or_(column.is_(None), column == ""))
        elif op == "is_not_empty":
            query = query.where(and_(column.isnot(None), column != ""))
        else:
            query = query.where(column == value)
    return query


def _apply_sort(query: Select, sort: Sequence[dict]) -> Select:
    """Multi-column sort. Falls back to a stable order when none is given.

    `Lead.id` is always appended as the final tiebreaker. Without it, two rows
    equal on every sort key can come back in a different order on each page
    request, and a keyset/offset pager then skips or repeats them.
    """
    ordered = False
    for spec in sort or []:
        column = GRID_COLUMNS.get(spec.get("key"))
        if column is None:
            continue
        direction = str(spec.get("dir", "asc")).lower()
        query = query.order_by(column.desc() if direction == "desc" else column.asc())
        ordered = True
    if not ordered:
        query = query.order_by(Lead.created_at.desc())
    return query.order_by(Lead.id)


def grid_page(db: Session, current_user: User, *,
              strategy_id: uuid.UUID | None = None,
              filters: dict | None = None,
              sort: Sequence[dict] | None = None,
              search: str | None = None,
              tag_ids: Sequence[uuid.UUID] | None = None,
              limit: int = 100, offset: int = 0) -> dict:
    """One page of grid rows, sorted and filtered SERVER-side.

    Server-side rather than shipping 5,000 rows and sorting in the browser:
    the grid promises smoothness at that size, and the way to keep that
    promise is to send it 100 rows at a time.
    """
    limit = max(1, min(limit, MAX_GRID_LIMIT))
    base = owned_leads_select(current_user, strategy_id)
    base = _apply_filters(base, filters or {})

    if search:
        needle = f"%{search}%"
        base = base.where(or_(
            Lead.full_name.ilike(needle),
            Lead.company.ilike(needle),
            Lead.email.ilike(needle),
            Lead.title.ilike(needle),
        ))

    if tag_ids:
        # EXISTS, not a join: a lead carrying three of the filtered tags would
        # otherwise come back three times and inflate `total`.
        base = base.where(
            select(CrmLeadTag.id)
            .where(CrmLeadTag.lead_id == Lead.id,
                   CrmLeadTag.tag_id.in_(list(tag_ids)))
            .exists()
        )

    total = int(db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one())

    rows = db.execute(
        _apply_sort(base, sort or []).limit(limit).offset(offset)
    ).scalars().all()

    lead_ids = [row.id for row in rows]
    tags = tags_for_leads(db, lead_ids)
    customs = custom_values_for_leads(db, lead_ids)
    notes = note_counts_for_leads(db, lead_ids)

    meta_rows = {
        meta.lead_id: meta
        for meta in db.execute(
            select(CrmLeadMeta).where(CrmLeadMeta.lead_id.in_(lead_ids))
        ).scalars().all()
    } if lead_ids else {}
    # Engagement Hub: four batched queries for the whole page, never per row.
    followups = followup_status_for_leads(db, lead_ids)

    items = []
    for lead in rows:
        meta = meta_rows.get(lead.id)
        items.append({
            "id": str(lead.id),
            "strategy_id": str(lead.strategy_id),
            "full_name": lead.full_name,
            "title": lead.title,
            "company": lead.company,
            "email": lead.email,
            "phone": lead.phone,
            "status": lead.status.value,
            "source": lead.source,
            "created_at": lead.created_at.isoformat() if lead.created_at else None,
            "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
            "tags": tags.get(lead.id, []),
            "custom": customs.get(lead.id, {}),
            "note_count": notes.get(lead.id, 0),
            "owner_user_id": (str(meta.owner_user_id)
                              if meta and meta.owner_user_id else None),
            "priority": meta.priority if meta else None,
            "next_action_at": (meta.next_action_at.isoformat()
                               if meta and meta.next_action_at else None),
            "followup_status": followups.get(lead.id, FOLLOWUP_NONE),
        })

    return {"items": items, "total": total, "limit": limit, "offset": offset,
            "has_more": offset + len(items) < total}


def get_or_create_meta(db: Session, lead: Lead) -> CrmLeadMeta:
    meta = db.execute(
        select(CrmLeadMeta).where(CrmLeadMeta.lead_id == lead.id)
    ).scalars().first()
    if meta is None:
        meta = CrmLeadMeta(lead_id=lead.id)
        db.add(meta)
        db.flush()
    return meta


# ---------------------------------------------------------------------------
# Engagement Hub, Feature 1 — the grid's follow-up column
# ---------------------------------------------------------------------------
#
# WHY THIS IS COMPUTED SERVER-SIDE AND BATCHED
# The obvious shape is a per-row derivation in the grid component from data it
# already has. It cannot be: the answer depends on the lead's messages, its
# outcomes and the followup_delay_hours of the step that last sent -- none of
# which the grid row carries, and all of which would be N round trips to fetch.
#
# So it is four queries for a whole page, resolved here, and the row ships a
# single string the cell renders as a badge.

FOLLOWUP_REPLIED = "replied"
FOLLOWUP_DUE = "due"
FOLLOWUP_SCHEDULED = "scheduled"
FOLLOWUP_WAITING = "waiting"
FOLLOWUP_NONE = "none"


def _utc(value):
    """SQLite hands back naive datetimes for timestamptz columns; PostgreSQL
    does not. Everything in those columns is UTC, so this restates rather than
    converts -- without it the comparison below raises on SQLite only."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def followup_status_for_leads(db: Session, lead_ids: Sequence[uuid.UUID],
                              now: datetime | None = None) -> dict:
    """lead_id -> one of the FOLLOWUP_* constants.

    The precedence is the order a user would read it in, and it matters:

      replied    a reply exists. Nothing else about this lead's follow-up
                 state is interesting any more, so it wins outright.
      scheduled  a message is queued. The sequence engine has it in hand.
      due        the last send is older than its step's followup_delay_hours
                 and nothing is queued -- this lead has fallen through.
      waiting    contacted, inside the window, nothing queued.
      none       never contacted on any sequence.

    `due` is the one that earns the column. It is exactly the population
    app/workers/outreach_tasks.py::check_followup_due picks up, computed the
    same way, so the badge and the automation cannot disagree about who is
    overdue.
    """
    if not lead_ids:
        return {}
    now = now or datetime.now(timezone.utc)
    ids = list(lead_ids)

    replied = set(db.execute(
        select(Outcome.lead_id).where(Outcome.lead_id.in_(ids),
                                      Outcome.event == OutcomeEvent.REPLIED)
    ).scalars().all())

    pending = set(db.execute(
        select(Message.lead_id).where(
            Message.lead_id.in_(ids),
            Message.status.in_([MessageStatus.SCHEDULED, MessageStatus.SENDING]),
        )
    ).scalars().all())

    # The most recent successful send per lead. Ordered ascending so the last
    # write into the dict wins, which avoids a correlated subquery that would
    # be spelled differently on SQLite and PostgreSQL.
    last_sent: dict = {}
    for lead_id, sequence_id, step_no, sent_at in db.execute(
        select(Message.lead_id, Message.sequence_id, Message.step_no,
               Message.sent_at)
        .where(Message.lead_id.in_(ids), Message.status == MessageStatus.SENT)
        .order_by(Message.sent_at)
    ).all():
        last_sent[lead_id] = (sequence_id, step_no, sent_at)

    steps = {
        (sequence_id, step_no): (enabled, hours)
        for sequence_id, step_no, enabled, hours in db.execute(
            select(SequenceStep.sequence_id, SequenceStep.step_no,
                   SequenceStep.followup_enabled,
                   SequenceStep.followup_delay_hours)
            .where(SequenceStep.sequence_id.in_(
                {seq for seq, _, _ in last_sent.values()} or {None}
            ))
        ).all()
    } if last_sent else {}

    out: dict = {}
    for lead_id in ids:
        if lead_id in replied:
            out[lead_id] = FOLLOWUP_REPLIED
            continue
        if lead_id in pending:
            out[lead_id] = FOLLOWUP_SCHEDULED
            continue
        entry = last_sent.get(lead_id)
        if entry is None:
            out[lead_id] = FOLLOWUP_NONE
            continue
        sequence_id, step_no, sent_at = entry
        enabled, hours = steps.get((sequence_id, step_no), (True, 72))
        sent_at = _utc(sent_at)
        if not enabled or sent_at is None:
            out[lead_id] = FOLLOWUP_WAITING
            continue
        overdue = (now - sent_at) >= timedelta(hours=hours or 72)
        out[lead_id] = FOLLOWUP_DUE if overdue else FOLLOWUP_WAITING
    return out

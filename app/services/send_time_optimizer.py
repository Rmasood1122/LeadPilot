"""
Send-time optimizer — recommends optimal outreach scheduling slots.

Reads per-slot reply-rate data aggregated from `outcomes` and cached in Redis.
Integrates with the M3 sequence scheduler (send_tasks.py): when scheduling
a new step, prefer a recommended slot if one is available within 48 hours.

Cache key pattern: send_time:{channel}:{icp_industry}:{icp_company_size}
Cache TTL: 25 hours (always fresh for next day's scheduling)

API: GET /playbook/send-times?channel=&icp_industry=&icp_company_size=
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from typing import Optional

from app.core.logging import get_logger

logger = get_logger("services.send_time_optimizer")

CACHE_TTL_SECONDS = 25 * 3600  # 25 hours
MAX_SLOTS = 5
MAX_SCHEDULE_AHEAD_HOURS = 48

# Default business-hours fallback slots (UTC) if no data
_DEFAULT_SLOTS = [
    {"day_of_week": 1, "hour_utc": 8,  "expected_reply_rate": 0.08, "sample_size": 0, "is_reliable": False},
    {"day_of_week": 2, "hour_utc": 9,  "expected_reply_rate": 0.08, "sample_size": 0, "is_reliable": False},
    {"day_of_week": 1, "hour_utc": 14, "expected_reply_rate": 0.07, "sample_size": 0, "is_reliable": False},
    {"day_of_week": 3, "hour_utc": 9,  "expected_reply_rate": 0.07, "sample_size": 0, "is_reliable": False},
    {"day_of_week": 4, "hour_utc": 8,  "expected_reply_rate": 0.06, "sample_size": 0, "is_reliable": False},
]


@dataclass
class SendTimeRecommendation:
    channel: str
    icp_industry: Optional[str]
    icp_company_size: Optional[str]
    recommended_slots: list[dict] = field(default_factory=list)
    confidence: str = "no_data"          # "high" | "medium" | "low" | "no_data"
    fallback_used: bool = False


def _cache_key(channel: str, icp_industry: Optional[str], icp_company_size: Optional[str]) -> str:
    # Messages store channel "email"; the Analytics page asks for "gmail".
    # Normalise so both name the same cache entry.
    channel = "email" if channel == "gmail" else channel
    industry = (icp_industry or "any").lower().replace(" ", "_")
    size = (icp_company_size or "any").lower().replace(" ", "_")
    return f"send_time:{channel}:{industry}:{size}"


def _confidence_from_n(total_n: int) -> str:
    if total_n >= 50:
        return "high"
    if total_n >= 20:
        return "medium"
    if total_n >= 1:
        return "low"
    return "no_data"


def get_send_time_recommendation(
    channel: str,
    icp_industry: Optional[str],
    icp_company_size: Optional[str],
) -> SendTimeRecommendation:
    """
    Return slot recommendations for a channel+ICP combination.
    Reads from Redis cache (written nightly by update_send_time_scores).
    Falls back to default business hours if no cached data.
    """
    from app.core.redis_client import get_sync_redis
    try:
        redis = get_sync_redis()
        key = _cache_key(channel, icp_industry, icp_company_size)
        raw = redis.get(key)
    except Exception as e:
        logger.warning("send_time.cache_read_failed", error=str(e))
        raw = None

    if raw:
        try:
            cached = json.loads(raw)
            slots = cached.get("slots", [])
            total_n = sum(s.get("sample_size", 0) for s in slots)
            confidence = _confidence_from_n(total_n)
            return SendTimeRecommendation(
                channel=channel,
                icp_industry=icp_industry,
                icp_company_size=icp_company_size,
                recommended_slots=slots[:MAX_SLOTS],
                confidence=confidence,
                fallback_used=False,
            )
        except Exception as e:
            logger.warning("send_time.cache_parse_failed", error=str(e))

    # No data — return default business hours
    return SendTimeRecommendation(
        channel=channel,
        icp_industry=icp_industry,
        icp_company_size=icp_company_size,
        recommended_slots=_DEFAULT_SLOTS[:MAX_SLOTS],
        confidence="no_data",
        fallback_used=True,
    )


def update_send_time_scores(db_session) -> int:
    """
    Compute per-slot reply rates from outcomes and write to Redis.
    Called nightly after compute_scores(). Returns number of keys written.

    Slot = (channel, icp_industry, icp_company_size, day_of_week, hour_utc).
    Rates computed as: slot_replies / slot_sends.
    """
    from collections import defaultdict

    from sqlalchemy import select

    from app.core.config import settings
    from app.core.redis_client import get_sync_redis
    from app.db.models import Message, Outcome, OutcomeEvent, Sequence, Strategy

    # Feature Group 3 repair. The old raw SQL selected s.icp_industry and
    # s.icp_company_size_bucket, columns strategies has never had, so this
    # failed every night on PostgreSQL -- and its except branch then called
    # rollback() on an undefined name `db`. The ICP bucket lives in
    # pattern_inputs_json (icp_extraction.canonical_pattern_payload), and the
    # query is now ORM so it also runs on SQLite. A reply is also now counted
    # in the slot its MESSAGE was sent in (it used to land in the hour the
    # reply arrived, which made "send at 9am" rates a mix of two clocks).
    try:
        rows = db_session.execute(
            select(Outcome.event, Outcome.ts, Message.sent_at, Message.channel,
                   Strategy.pattern_inputs_json)
            .join(Message, Message.id == Outcome.message_id)
            .join(Sequence, Sequence.id == Message.sequence_id)
            .join(Strategy, Strategy.id == Sequence.strategy_id)
            .where(Outcome.event.in_([OutcomeEvent.SENT, OutcomeEvent.REPLIED]))
        ).all()
    except Exception as e:
        # Rollback so a failed query cannot leave the shared session in an
        # aborted transaction for later aggregation steps.
        try:
            db_session.rollback()
        except Exception:
            pass
        logger.error("send_time.query_failed", error=str(e))
        return 0

    counts: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    for event, ts, sent_at, channel, inputs in rows:
        when = sent_at or ts
        if when is None:
            continue
        icp = (inputs or {}).get("icp") if isinstance(inputs, dict) else None
        icp = icp if isinstance(icp, dict) else {}
        industry = (icp.get("industries") or ["any"])[0]
        size = (icp.get("company_size_ranges") or ["any"])[0]
        ch = getattr(channel, "value", channel) or "email"
        # Sunday=0 .. Saturday=6: the convention the cached slots and
        # pick_next_send_datetime() already use.
        dow = (when.weekday() + 1) % 7
        cell = counts[(ch, industry, size, dow, when.hour)]
        cell[0 if event is OutcomeEvent.SENT else 1] += 1

    min_sample = settings.PLAYBOOK_MIN_SAMPLE
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for (ch, industry, size, dow, hour), (sends, replies) in counts.items():
        if sends == 0:
            continue
        grouped[(ch, industry, size)].append({
            "day_of_week": dow,
            "hour_utc": hour,
            "expected_reply_rate": round(replies / sends, 4),
            "sample_size": sends,
            "is_reliable": sends >= min_sample,
        })

    # Sort each group by reply_rate desc, take top MAX_SLOTS
    redis = get_sync_redis()
    keys_written = 0
    for (channel, industry, size), slots in grouped.items():
        slots.sort(key=lambda x: x["expected_reply_rate"], reverse=True)
        cache_key = _cache_key(channel, industry, size)
        payload = json.dumps({"slots": slots[:MAX_SLOTS]})
        redis.set(cache_key, payload, ex=CACHE_TTL_SECONDS)
        keys_written += 1

    logger.info("send_time.scores_updated", keys_written=keys_written)
    return keys_written


def pick_next_send_datetime(
    recommendation: SendTimeRecommendation,
    from_datetime,           # datetime.datetime (UTC)
    max_hours_ahead: int = MAX_SCHEDULE_AHEAD_HOURS,
):
    """
    Given a recommendation, return the next datetime that falls in one of the
    recommended slots within max_hours_ahead. If none exists, return from_datetime
    (fall through to M3 default scheduling logic).

    Returns: datetime.datetime | None (None = use existing M3 logic)
    """
    import datetime

    if recommendation.confidence in ("low", "no_data") or recommendation.fallback_used:
        return None  # let M3 logic handle it

    cutoff = from_datetime + datetime.timedelta(hours=max_hours_ahead)
    candidate = from_datetime.replace(minute=0, second=0, microsecond=0)

    while candidate <= cutoff:
        for slot in recommendation.recommended_slots:
            if (
                # slot["day_of_week"] comes from EXTRACT(DOW ...) -- Postgres
                # numbers Sunday=0..Saturday=6, while datetime.weekday() is
                # Monday=0..Sunday=6. The old `% 7` was a no-op on 0..6 and
                # left the two conventions mixed, so every optimized send was
                # scheduled exactly ONE DAY LATE (a Monday slot fired Tuesday,
                # and a Sunday slot fired Monday).
                candidate.weekday() == (slot["day_of_week"] - 1) % 7
                and candidate.hour == slot["hour_utc"]
                and slot["is_reliable"]
            ):
                return candidate
        candidate += datetime.timedelta(hours=1)

    return None  # no reliable slot in window — M3 logic takes over

"""
Personalization quality scorer.

Measures how much of the available enrichment data was actually used in each
message, and correlates personalization depth with reply outcomes.

Key integrations:
  - score_message() called at send time (lightweight, no external API call)
  - score_strategy_messages() called nightly to compute Pearson correlation
  - Result stored in messages.personalization_score (column added in migration 0010)
  - strategies.personalization_correlation updated nightly
  - If correlation > 0.3: prompt injection added to Phase 6 message generation
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional

from app.core.logging import get_logger

logger = get_logger("services.personalization_scorer")

# Fields that indicate personalization when referenced in a message body
ENRICHMENT_FIELDS = [
    "company",
    "industry",
    "job_title",
    "first_name",
    "last_name",
    "phone",
    "revenue",
    "num_employees",
    "location",
    "linkedin_url",
    "technology",
    "funding_stage",
]

# Patterns that suggest the field was used (template variable OR direct text reference)
_TEMPLATE_PATTERNS = {
    field: re.compile(
        rf"\{{({field})\}}|\[({field})\]|{{{field}}}",
        re.IGNORECASE,
    )
    for field in ENRICHMENT_FIELDS
}


@dataclass
class PersonalizationScore:
    message_id: Optional[int]
    raw_score: float               # 0.0–1.0
    used_fields: list[str] = field(default_factory=list)
    unused_fields: list[str] = field(default_factory=list)
    outcome_corr: Optional[float] = None  # set later by nightly job


def score_message(
    message_body: str,
    enrichment_json: Optional[dict],
    message_id: Optional[int] = None,
) -> PersonalizationScore:
    """
    Score a single message for personalization depth.

    raw_score = used_fields_count / available_fields_count
    "Available" = fields present and non-empty in enrichment_json.
    "Used" = field referenced as a template token in the rendered body.

    Lightweight — no external calls. Safe to call at send time.
    """
    if not enrichment_json:
        return PersonalizationScore(
            message_id=message_id,
            raw_score=0.0,
            used_fields=[],
            unused_fields=[],
        )

    available = [f for f in ENRICHMENT_FIELDS if enrichment_json.get(f)]
    if not available:
        return PersonalizationScore(message_id=message_id, raw_score=0.0)

    used = []
    unused = []
    for field_name in available:
        pattern = _TEMPLATE_PATTERNS.get(field_name)
        # Check for template variable OR literal value reference
        value = str(enrichment_json[field_name])
        if (pattern and pattern.search(message_body)) or (value and len(value) > 2 and value.lower() in message_body.lower()):
            used.append(field_name)
        else:
            unused.append(field_name)

    raw_score = len(used) / len(available) if available else 0.0

    return PersonalizationScore(
        message_id=message_id,
        raw_score=round(raw_score, 4),
        used_fields=used,
        unused_fields=unused,
    )


def score_strategy_messages(strategy_id: str, db_session) -> dict:
    """
    Compute Pearson correlation between personalization_score and reply outcome
    across all scored messages in this strategy.

    Returns: {
        avg_score, high_score_reply_rate, low_score_reply_rate,
        correlation, sample_size
    }
    Stores result in strategies.personalization_correlation.
    """
    from sqlalchemy import text

    sql = text("""
        SELECT
            m.id AS message_id,
            m.personalization_score,
            CASE WHEN o.event = 'replied' THEN 1 ELSE 0 END AS replied
        FROM messages m
        JOIN sequences seq ON seq.id = m.sequence_id
        LEFT JOIN outcomes o ON o.message_id = m.id AND o.event IN ('sent', 'replied')
        WHERE seq.strategy_id = :sid
          AND m.personalization_score IS NOT NULL
          AND m.sent_at IS NOT NULL
        ORDER BY m.id
    """)

    try:
        rows = db_session.execute(sql, {"sid": strategy_id}).mappings().all()
    except Exception as e:
        try:
            db_session.rollback()  # REPAIR: never poison the shared session
        except Exception:
            pass
        logger.error("personalization.strategy_query_failed", strategy_id=strategy_id, error=str(e))
        return {"avg_score": None, "correlation": None, "sample_size": 0}

    if len(rows) < 10:
        return {"avg_score": None, "correlation": None, "sample_size": len(rows)}

    scores = [float(r["personalization_score"]) for r in rows]
    replies = [int(r["replied"]) for r in rows]

    n = len(scores)
    avg_score = sum(scores) / n

    # Pearson r
    corr = _pearson(scores, replies)

    # High vs low score reply rates
    median = sorted(scores)[n // 2]
    high = [replies[i] for i, s in enumerate(scores) if s >= median]
    low = [replies[i] for i, s in enumerate(scores) if s < median]
    high_rate = sum(high) / max(len(high), 1)
    low_rate = sum(low) / max(len(low), 1)

    result = {
        "avg_score": round(avg_score, 4),
        "high_score_reply_rate": round(high_rate, 4),
        "low_score_reply_rate": round(low_rate, 4),
        "correlation": round(corr, 4) if corr is not None else None,
        "sample_size": n,
    }

    # Persist correlation
    try:
        db_session.execute(text("""
            UPDATE strategies
            SET personalization_correlation = :corr
            WHERE id = :sid
        """), {"corr": result["correlation"], "sid": strategy_id})
        db_session.commit()
    except Exception as e:
        try:
            db_session.rollback()  # REPAIR: never poison the shared session
        except Exception:
            pass
        logger.warning("personalization.update_failed", strategy_id=strategy_id, error=str(e))

    return result


def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    """Pearson correlation coefficient between two numeric lists."""
    n = len(xs)
    if n < 2:
        return None

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    cov = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    std_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    std_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))

    denom = std_x * std_y
    if denom == 0:
        return None

    return cov / denom


def build_personalization_prompt_injection(
    correlation: float,
    enrichment_fields: list[str],
) -> str:
    """
    Build the prompt injection text for Phase 6 message generation.
    Only injected when correlation > 0.3.
    """
    if correlation <= 0.3 or not enrichment_fields:
        return ""

    fields_str = ", ".join(enrichment_fields[:8])
    return (
        f"Past messages for this strategy showed a {correlation:.0%} positive correlation "
        f"between personalization depth and reply rate. "
        f"Use as many of the following lead-specific fields as feels natural: {fields_str}."
    )


def write_personalization_score(message_id: int, score: float, db_session) -> None:
    """Write the personalization_score to the messages row at send time."""
    from sqlalchemy import text
    try:
        db_session.execute(text("""
            UPDATE messages SET personalization_score = :score WHERE id = :mid
        """), {"score": score, "mid": message_id})
        db_session.commit()
    except Exception as e:
        try:
            db_session.rollback()  # REPAIR: never poison the shared session
        except Exception:
            pass
        logger.warning("personalization.write_failed", message_id=message_id, error=str(e))

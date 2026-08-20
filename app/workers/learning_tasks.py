"""
Nightly learning loop Celery tasks — M8 Chunks 1+2+4 combined.

run_strategy_aggregation():
  1. compute_scores_with_decay()  → playbook_scores (replaces simple mean)
  2. update_send_time_scores()    → Redis send-time cache (NEW: C4)
  3. extract_patterns_from_outcomes() + persist_patterns()  (NEW: C4)
  4. detect_stale_pipeline_steps()
  5. Score all strategy messages for personalization correlation  (NEW: C4)

auto_promote_winners():
  - Now calls compare_multi_variants() when step has >2 variants (NEW: C4)
  - Falls back to compare_variants() for exactly 2
  - Double-promotion guard unchanged
"""
from __future__ import annotations

import datetime
import time

from app.workers.celery_app import celery_app
from app.core.logging import get_logger, bind_celery_task_context, TaskTimer

logger = get_logger("workers.learning_tasks")


@celery_app.task(
    name="app.workers.learning_tasks.run_strategy_aggregation",
    bind=True,
    max_retries=2,
    acks_late=True,
)
def run_strategy_aggregation(self) -> dict:
    """
    Nightly learning loop aggregation.
    Scheduled by Celery Beat at PLAYBOOK_AGGREGATION_UTC_HOUR (default 02:00 UTC).
    """
    bind_celery_task_context(task_id=self.request.id, task_name="run_strategy_aggregation")
    started_at = time.monotonic()

    from app.core.database import SessionLocal
    from app.core.redis_client import get_sync_redis
    from app.core.config import settings
    from app.services.score_decay import compute_scores_with_decay, determine_trend
    from app.services.send_time_optimizer import update_send_time_scores
    from app.services.subject_intelligence import extract_patterns_from_outcomes, persist_patterns
    from app.services.personalization_scorer import score_strategy_messages
    from app.workers.monitoring import detect_stale_pipeline_steps

    db = SessionLocal()
    redis = get_sync_redis()
    patterns_updated = 0
    errors: list[str] = []

    try:
        with TaskTimer(logger, "aggregation"):
            # 1. Compute decayed playbook scores
            logger.info("aggregation.decay_scores_started")
            decayed = compute_scores_with_decay(db, settings.PLAYBOOK_SCORE_HALF_LIFE_DAYS)

            for composite_key, score_data in decayed.items():
                try:
                    _upsert_playbook_score(db, score_data)
                    patterns_updated += 1
                except Exception as e:
                    db.rollback()  # REPAIR: don't poison the session for later steps
                    errors.append(f"score upsert {composite_key}: {e}")

            # 2. Send-time optimizer update
            logger.info("aggregation.send_time_update_started")
            try:
                keys_written = update_send_time_scores(db)
                logger.info("aggregation.send_time_done", keys_written=keys_written)
            except Exception as e:
                db.rollback()  # REPAIR
                errors.append(f"send_time_update: {e}")
                logger.warning("aggregation.send_time_failed", error=str(e))

            # 3. Subject line pattern extraction
            logger.info("aggregation.subject_patterns_started")
            try:
                patterns = extract_patterns_from_outcomes(db)
                persist_patterns(db, patterns)
                logger.info("aggregation.subject_patterns_done", count=len(patterns))
            except Exception as e:
                db.rollback()  # REPAIR
                errors.append(f"subject_patterns: {e}")
                logger.warning("aggregation.subject_patterns_failed", error=str(e))

            # 4. Stale pipeline step detection
            try:
                stalled = detect_stale_pipeline_steps()
                if stalled:
                    logger.warning("aggregation.stale_steps_found", count=len(stalled))
            except Exception as e:
                errors.append(f"stale_detection: {e}")

            # 5. Personalization correlation per strategy (sample up to 50 recent strategies)
            logger.info("aggregation.personalization_correlation_started")
            try:
                from sqlalchemy import text
                strategy_ids = db.execute(text("""
                    SELECT id FROM strategies
                    -- REPAIR: id is the PK (DISTINCT was invalid with this
                    -- ORDER BY); real StrategyStatus values, not 'complete'.
                    WHERE status IN ('verified', 'executing')
                    ORDER BY updated_at DESC LIMIT 50
                """)).scalars().all()
                for sid in strategy_ids:
                    try:
                        score_strategy_messages(str(sid), db)
                    except Exception:
                        pass
            except Exception as e:
                db.rollback()  # REPAIR
                errors.append(f"personalization_corr: {e}")

        duration_ms = int((time.monotonic() - started_at) * 1000)

        # Update Redis health keys
        now = time.time()
        redis.set("learning_loop:last_run", str(now))
        redis.set("learning_loop:last_duration_ms", str(duration_ms))
        redis.set("learning_loop:patterns_updated", str(patterns_updated))
        if errors:
            redis.set("learning_loop:last_error", "; ".join(errors[:3]))
        else:
            redis.delete("learning_loop:last_error")

        logger.info(
            "aggregation.complete",
            duration_ms=duration_ms,
            patterns_updated=patterns_updated,
            errors=len(errors),
        )
        return {"patterns_updated": patterns_updated, "duration_ms": duration_ms, "errors": errors}

    except Exception as e:
        logger.error("aggregation.fatal_error", error=str(e))
        redis.set("learning_loop:last_error", str(e))
        raise
    finally:
        db.close()


def _upsert_playbook_score(db, score_data: dict) -> None:
    """Upsert a single playbook score row with decay data."""
    from sqlalchemy import text

    db.execute(text("""
        INSERT INTO playbook_scores
            -- REPAIR: id is a UUID PK with no DB default; PG16 supplies it.
            (id, pattern_key, variant, score, reply_rate, booking_rate,
             sample_size, effective_sample_size,
             decay_half_life_days, oldest_outcome_ts,
             is_reliable, trend, last_aggregated_at)
        VALUES
            (gen_random_uuid(), :pattern_key, :variant, :reply_rate, :reply_rate, :booking_rate,
             :raw_n, :effective_n,
             :half_life, :oldest_ts,
             :reliable, 'new', NOW())
        ON CONFLICT (pattern_key, variant) DO UPDATE SET
            score = EXCLUDED.score,
            reply_rate = EXCLUDED.reply_rate,
            booking_rate = EXCLUDED.booking_rate,
            sample_size = EXCLUDED.sample_size,
            effective_sample_size = EXCLUDED.effective_sample_size,
            decay_half_life_days = EXCLUDED.decay_half_life_days,
            oldest_outcome_ts = EXCLUDED.oldest_outcome_ts,
            is_reliable = EXCLUDED.is_reliable,
            trend = CASE
                WHEN playbook_scores.score IS NULL THEN 'new'
                WHEN EXCLUDED.score > playbook_scores.score + 0.005 THEN 'rising'
                WHEN EXCLUDED.score < playbook_scores.score - 0.005 THEN 'falling'
                ELSE 'stable'
            END,
            last_aggregated_at = NOW()
    """), {
        "pattern_key": score_data["pattern_key"],
        "variant": score_data["variant"],
        "reply_rate": score_data["reply_rate"],
        "booking_rate": score_data["booking_rate"],
        "raw_n": score_data["raw_n"],
        "effective_n": score_data["effective_n"],
        "half_life": score_data["half_life_days"],
        "oldest_ts": score_data.get("oldest_outcome_ts"),
        "reliable": score_data["is_reliable"],
    })
    db.commit()


@celery_app.task(
    name="app.workers.learning_tasks.auto_promote_winners",
    bind=True,
    max_retries=1,
    acks_late=True,
)
def auto_promote_winners(self) -> dict:
    """
    A/B / MV auto-promotion nightly sweep.
    Now uses compare_multi_variants() when >2 variants detected.
    """
    bind_celery_task_context(task_id=self.request.id, task_name="auto_promote_winners")

    from app.core.database import SessionLocal
    from app.services.multi_variate import compare_multi_variants
    from app.core.config import settings
    from sqlalchemy import text

    db = SessionLocal()
    promoted = 0

    try:
        # Find strategies with >= 2 active variants and enough data
        strategies = db.execute(text("""
            SELECT
                o.strategy_id,
                array_agg(DISTINCT o.variant) AS variants,
                COUNT(DISTINCT o.variant) AS variant_count,
                SUM(CASE WHEN o.event = 'sent' THEN 1 ELSE 0 END) AS total_sends
            FROM outcomes o
            WHERE o.variant IS NOT NULL
              AND o.event IN ('sent', 'replied', 'booked')
            GROUP BY o.strategy_id
            HAVING COUNT(DISTINCT o.variant) >= 2
               AND SUM(CASE WHEN o.event = 'sent' THEN 1 ELSE 0 END) >= :min_sample
        """), {"min_sample": settings.PLAYBOOK_MIN_SAMPLE}).mappings().all()

        for row in strategies:
            strategy_id = str(row["strategy_id"])
            variants = list(row["variants"])
            variant_count = len(variants)

            # Check double-promotion guard
            already_promoted = db.execute(text("""
                SELECT COUNT(*) FROM outcomes
                WHERE strategy_id = :sid AND event = 'ab_promoted'
            """), {"sid": strategy_id}).scalar() or 0

            if already_promoted > 0:
                continue  # skip — already promoted

            try:
                # Use multi-variate for >2, binary for exactly 2
                if variant_count > 2:
                    result = compare_multi_variants(
                        strategy_id=strategy_id,
                        variants=variants,
                        metric="meeting_rate",
                        db_session=db,
                    )
                    winner = result.winner
                else:
                    # Binary comparison (M8 Ch2 logic — kept for backward compat)
                    from app.services.ab_testing import compare_variants
                    result = compare_variants(strategy_id, variants[0], variants[1], db_session=db)
                    winner = result.winner if hasattr(result, "winner") else None

                if winner:
                    # Set default_variant on strategy
                    db.execute(text("""
                        UPDATE strategies
                        SET default_variant = :winner, updated_at = NOW()
                        WHERE id = :sid
                    """), {"winner": winner, "sid": strategy_id})

                    # Write ab_promoted outcome (idempotency key = strategy_id)
                    db.execute(text("""
                        INSERT INTO outcomes (id, strategy_id, event, variant, ts)
                        -- REPAIR: id is a client-side UUID PK with no DB
                        -- default (PG16 gen_random_uuid supplies it here);
                        -- lead_id nullable per 0012 for system events. The
                        -- 0012 partial unique index makes ON CONFLICT a real
                        -- DB-level idempotency guarantee.
                        VALUES (gen_random_uuid(), :sid, 'ab_promoted', :winner, NOW())
                        ON CONFLICT DO NOTHING
                    """), {"sid": strategy_id, "winner": winner})
                    db.commit()
                    promoted += 1
                    logger.info(
                        "promotion.winner_set",
                        strategy_id=strategy_id,
                        winner=winner,
                        variant_count=variant_count,
                    )
            except Exception as e:
                logger.warning(
                    "promotion.strategy_failed",
                    strategy_id=strategy_id,
                    error=str(e),
                )

        return {"promoted": promoted}
    finally:
        db.close()

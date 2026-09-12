"""Feature 3 background work: build a product's founder voice profile.

  build_voice_profile(product_id, posts)   one model call over up to 20 posts

On the `default` queue rather than `pipeline`. It is one user-triggered model
call and the user is watching for the result; `pipeline` is sized for the
72/144-step strategy run at concurrency 2, so a voice analysis queued there
could sit behind a full pipeline for many minutes.

IDEMPOTENT BY CONSTRUCTION. extract_voice_profile UPSERTS the single
voice_profiles row for the product (the schema enforces one per product), so a
retry re-analyses the same posts and overwrites the same row. The end state
after two runs is the end state after one.
"""

import logging

from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def build_voice_profile_impl(session: Session, product_id, posts: list) -> dict:
    """Extract and store one product's voice profile.

    WHAT IT RETURNS. {"status": "built", "product_id": str, "post_count": int,
    "dimensions": dict} on success; {"status": "invalid"|"not_found"|"failed",
    "error": str} otherwise.

    WHAT IT NEVER RAISES. Anything. extract_voice_profile deliberately raises
    (see its docstring) so the failure is visible; this is where that becomes
    a logged status instead of a Celery traceback and an infinite retry. A
    failure leaves any EXISTING profile untouched, so a broken re-analysis
    never costs the founder the voice they already had.
    """
    from app.services import voice_profiler  # noqa: PLC0415

    try:
        profile = voice_profiler.extract_voice_profile(session, product_id, posts)
    except voice_profiler.InvalidPosts as exc:
        logger.warning("voice profile: unusable posts for product %s: %s",
                       product_id, exc)
        return {"status": "invalid", "error": str(exc)[:200]}
    except LookupError as exc:
        return {"status": "not_found", "error": str(exc)[:200]}
    except Exception as exc:  # noqa: BLE001 -- see the docstring
        logger.exception("voice profile extraction failed for product %s", product_id)
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:200]}

    return {"status": "built", "product_id": str(profile.product_id),
            "post_count": profile.post_count,
            "dimensions": profile.style_dimensions_json or {}}


@celery_app.task(name="app.workers.voice_tasks.build_voice_profile")
def build_voice_profile(product_id: str, posts: list) -> dict:
    """Celery entry point. Safe to retry; see the module docstring."""
    session = SessionLocal()
    try:
        return build_voice_profile_impl(session, product_id, posts)
    finally:
        session.close()


def enqueue(product_id, posts: list) -> str | None:
    """Publish build_voice_profile and return the Celery task id.

    WHAT IT RETURNS. The task id, or None when the broker refused the job --
    which the API turns into a 503 rather than a fake "queued", so the user is
    never told their analysis started when it did not.

    WHAT IT NEVER RAISES. Anything; a broker failure is logged and returns None.
    """
    try:
        return build_voice_profile.apply_async(
            args=[str(product_id), list(posts)], retry=False).id
    except Exception:  # noqa: BLE001 -- see the docstring
        logger.exception("voice profile: could not enqueue product %s", product_id)
        return None

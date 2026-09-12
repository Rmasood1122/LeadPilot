"""Website builder background work: page generation and static export.

  generate_page_task(page_id)   one Claude call that writes a whole page
  export_site_task(output_dir)  every published page out to static files

NO BEAT SCHEDULE. Both are triggered on demand — generation when a page is
created or regenerated, export when a page is published or the user asks.
Nothing here should run on a timer: regenerating pages nobody asked to change
would rewrite live marketing copy on a cron, and re-exporting an unchanged
site is pure cost.

On the `pipeline` queue, with the other long model calls. A page is the
largest single generation in this system (up to MAX_TOKENS of HTML), and it
must not sit in front of a time-sensitive outreach send or a meeting reminder.

IDEMPOTENT. generate_page_task fully overwrites the same six columns from the
same inputs, so a retry produces another complete page rather than a partial
one; a failure writes nothing at all and leaves the previous version live.
export_site_task rewrites the same files from the same rows.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.db.models import PageStatus, SitePage
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

DEFAULT_EXPORT_DIR = "/tmp/leadpilot_site_export"


def generate_page_impl(session: Session, page_id) -> dict:
    """Generate and store the HTML for one page.

    WHAT IT RETURNS. {"status": "generated"|"not_found"|"failed",
    "page_id": str, "seo_score": int|None}.

    WHAT IT NEVER RAISES. Anything. A missing page is a status, not an
    exception, so a retry after the row was deleted does not spin. A
    generation failure leaves EVERY column untouched — including status — so
    a published page whose regeneration failed keeps serving the version that
    worked, which is the whole reason failure does not write.
    """
    import uuid  # noqa: PLC0415

    from app.services import website_builder  # noqa: PLC0415

    try:
        page = session.get(SitePage, uuid.UUID(str(page_id)))
    except (ValueError, TypeError):
        logger.warning("website builder: %r is not a page id", page_id)
        return {"status": "not_found", "page_id": str(page_id), "seo_score": None}
    if page is None:
        logger.warning("website builder: page %s not found", page_id)
        return {"status": "not_found", "page_id": str(page_id), "seo_score": None}

    # The internal-linking menu: every OTHER published page. A page cannot
    # link to itself, and linking to an unpublished page would ship a 404.
    existing = session.execute(
        select(SitePage.slug, SitePage.title, SitePage.target_keyword)
        .where(SitePage.status == PageStatus.PUBLISHED, SitePage.id != page.id)
        .order_by(SitePage.slug)
    ).all()
    existing_pages = [{"slug": slug, "title": title, "target_keyword": keyword}
                      for slug, title, keyword in existing]

    try:
        result = website_builder.generate_page_html(
            page_type=page.page_type.value if page.page_type else "blog",
            title=page.title,
            target_keyword=page.target_keyword,
            secondary_keywords=list(page.secondary_keywords or []),
            brief=page.brief or "",
            existing_pages=existing_pages,
            slug=page.slug or "",
            meta_title=page.meta_title,
            meta_description=page.meta_description,
        )
    except Exception:  # noqa: BLE001 -- see the docstring
        logger.exception("website builder: generation failed for page %s (%s)",
                         page.id, page.slug)
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {"status": "failed", "page_id": str(page.id), "seo_score": None}

    try:
        page.html_content = result["html_content"]
        page.word_count = result["word_count"]
        page.reading_time_mins = result["reading_time_mins"]
        page.internal_links_json = result["internal_links"]
        page.schema_markup_json = result["schema_markup"]
        page.last_generated_at = datetime.now(timezone.utc)

        score = website_builder.score_page_seo(page.html_content, page.target_keyword)
        page.seo_score = score["score"]
        page.seo_issues_json = score["issues"]
        session.commit()
    except Exception:  # noqa: BLE001 -- see the docstring
        logger.exception("website builder: could not store page %s", page.id)
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {"status": "failed", "page_id": str(page.id), "seo_score": None}

    logger.info("website builder: generated %s (%s words, SEO %s)",
                page.slug or "<homepage>", page.word_count, page.seo_score)
    return {"status": "generated", "page_id": str(page.id), "seo_score": page.seo_score}


def export_site_impl(session: Session, output_dir: str) -> dict:
    """Export every published page. Never raises — see export_static_site."""
    from app.services import website_builder  # noqa: PLC0415

    result = website_builder.export_static_site(session, output_dir)
    logger.info("website builder: export result %s", result)
    return result


@celery_app.task(name="workers.site_tasks.generate_page_task")
def generate_page_task(page_id: str) -> dict:
    """Celery entry point for one page's generation. Safe to retry."""
    session = SessionLocal()
    try:
        return generate_page_impl(session, page_id)
    finally:
        session.close()


@celery_app.task(name="workers.site_tasks.export_site_task")
def export_site_task(output_dir: str = DEFAULT_EXPORT_DIR) -> dict:
    """Celery entry point for the static export. Safe to retry."""
    session = SessionLocal()
    try:
        return export_site_impl(session, output_dir)
    finally:
        session.close()


def enqueue_generation(page_id) -> bool:
    """Publish generate_page_task. Never raises; False when the broker refused.

    A page whose generation could not be QUEUED still exists as a draft with
    empty html_content, and POST /site/pages/{id}/regenerate will retry it —
    so a broker outage costs a retry, not the page.
    """
    try:
        generate_page_task.apply_async(args=[str(page_id)], retry=False)
        return True
    except Exception:  # noqa: BLE001 -- see the docstring
        logger.exception("website builder: could not enqueue page %s", page_id)
        return False


def enqueue_export(output_dir: str = DEFAULT_EXPORT_DIR) -> bool:
    """Publish export_site_task. Never raises; False when the broker refused."""
    try:
        export_site_task.apply_async(args=[output_dir], retry=False)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("website builder: could not enqueue the static export")
        return False

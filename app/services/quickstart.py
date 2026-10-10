"""F06 Quickstart -- a reviewable first result in minutes, not weeks.

Website URL + one-line offer -> the EXISTING ICP extractor -> a small batch
through the EXISTING lead chain -> review-only first-touch drafts written by
the EXISTING personalisation engine and checked by the EXISTING claim engine.
The strategy's full research pipeline runs beside it and supersedes it.

THE SAFETY PROPERTY: NOTHING HERE CAN SEND
A draft is a `quickstart_drafts` row, never a `messages` row. The dispatcher
(outreach_tasks.dispatch_due_messages_impl) and the send chokepoint
(send_message_impl) read only `messages`, so a draft has no path to a
prospect. The leads this sources are ordinary leads of the strategy; they can
be contacted only through /sequences/{id}/enroll, which still requires a
VERIFIED strategy, and then every send-time gate. The /leads/source gate is
not touched. See docs/features/f06-quickstart.md.

Every model call runs inside a usage scope with purpose "quickstart": the run's
own budget (quickstart_budget_usd) and the account's plan daily cap are both
enforced before each call.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    ApiUsage, ClaimVerificationLog, Lead, LeadBatch, LeadStatus,
    QuickstartDraft, QuickstartRun, SequenceStep, Strategy, StrategyStatus,
)
from app.services import prompt_safety, system_settings, usage_meter

logger = logging.getLogger(__name__)

PURPOSE = "quickstart"
LABEL = "Quickstart draft — full research running"
SUPERSEDED_LABEL = "Quickstart draft — superseded by the verified strategy"
MAX_OFFER_CHARS = 300
MAX_WEBSITE_TEXT_CHARS = 20_000
# Website text that goes into the ICP prompt. The ICP needs the gist of what
# the company sells and to whom, not the whole page.
ICP_PROMPT_TEXT_CHARS = 8_000

QUEUED, FETCHING, EXTRACTING, SOURCING, DRAFTING, READY, FAILED = (
    "queued", "fetching", "extracting", "sourcing", "drafting", "ready", "failed")
IN_PROGRESS = (QUEUED, FETCHING, EXTRACTING, SOURCING, DRAFTING)
DRAFT, DISCARDED = "draft", "discarded"

# The strategy statuses at which the full pipeline has finished and its
# verified output supersedes the Quickstart drafts.
SUPERSEDING_STATUSES = (StrategyStatus.VERIFIED, StrategyStatus.NEEDS_HUMAN_REVIEW,
                        StrategyStatus.EXECUTING)

TURNED_OFF = "Quickstart is turned off"

# The step brief the existing personalisation engine writes each draft from.
# The offer is the account owner's own words (trusted). The website text is
# deliberately NOT here: it is untrusted, and nothing from it may become a
# claim to a prospect -- drafts are written from the offer and the lead's
# stored data only, which is exactly what claim verification checks against.
DRAFT_BRIEF = (
    "QUICKSTART FIRST TOUCH (a draft for the sender to review, written before "
    "the full research has finished). What the sender offers, in their own "
    "words: \"{offer}\". Product: {product}. Write a short first-touch email: "
    "open with one specific, relevant line about this person's role or company "
    "drawn ONLY from the lead data given; one plain sentence on the offer; one "
    "easy question. Never invent news, funding, hiring, metrics, mutual "
    "connections or anything the lead data does not state."
)


class QuickstartError(ValueError):
    """Input the API rejects with 422."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------


def enabled(db: Session) -> bool:
    return bool(system_settings.get(db, "quickstart_enabled"))


def lead_target(db: Session) -> int:
    return max(1, min(int(system_settings.get(db, "quickstart_lead_target")),
                      int(settings.leads_max_per_run)))


def budget_micros(db: Session) -> int:
    return int(round(float(system_settings.get(db, "quickstart_budget_usd")) * 1_000_000))


def config(db: Session) -> dict:
    return {"enabled": enabled(db), "lead_target": lead_target(db),
            "budget_usd": round(budget_micros(db) / 1_000_000, 2), "label": LABEL}


# --------------------------------------------------------------------------
# Input
# --------------------------------------------------------------------------


def clean_offer(offer: str | None) -> str:
    folded = " ".join((offer or "").split())
    if len(folded) < 10:
        raise QuickstartError("describe your offer in one line (at least 10 characters)")
    if len(folded) > MAX_OFFER_CHARS:
        raise QuickstartError(f"keep the offer to one line ({MAX_OFFER_CHARS} characters at most)")
    return folded


def product_name_for(url: str, given: str | None) -> str:
    name = " ".join((given or "").split())[:200]
    if name:
        return name
    host = (urlparse(url).hostname or "").lower()
    return (host[4:] if host.startswith("www.") else host)[:200] or "My product"


# --------------------------------------------------------------------------
# Timing instrumentation (the success metric: p50 time to first draft)
# --------------------------------------------------------------------------


def _seconds_since_created(run: QuickstartRun, at: datetime | None) -> float | None:
    created, at = _aware(run.created_at), _aware(at)
    if created is None or at is None:
        return None
    return round((at - created).total_seconds(), 1)


def _timing(run: QuickstartRun, stage: str, at: datetime) -> None:
    logger.info("quickstart.timing run=%s stage=%s seconds=%s", run.id, stage,
                _seconds_since_created(run, at))


def timing_summary(db: Session, *, days: int = 30, now: datetime | None = None) -> dict:
    """n / p50 / p90 seconds from request to first reviewable draft, over the
    runs created in the last `days` that produced one. Admin-only consumer.
    Deployment-wide by design (an operator metric); it returns no row data."""
    now = now or _now()
    rows = db.execute(
        select(QuickstartRun.created_at, QuickstartRun.first_draft_at)
        .where(QuickstartRun.created_at >= now - timedelta(days=days),
               QuickstartRun.first_draft_at.isnot(None))
    ).all()
    values = sorted((_aware(f) - _aware(c)).total_seconds() for c, f in rows)
    runs = int(db.execute(
        select(func.count(QuickstartRun.id))
        .where(QuickstartRun.created_at >= now - timedelta(days=days))
    ).scalar_one() or 0)

    def _pct(p: float) -> float | None:
        if not values:
            return None
        # nearest-rank percentile: deterministic, no interpolation
        rank = max(1, -(-len(values) * p // 100))
        return round(values[int(rank) - 1], 1)

    return {"days": days, "runs": runs, "runs_with_draft": len(values),
            "p50_seconds": _pct(50), "p90_seconds": _pct(90),
            "target_seconds": 15 * 60}


# --------------------------------------------------------------------------
# Spend
# --------------------------------------------------------------------------


def spent_micros(db: Session, strategy_id) -> int:
    """What Quickstart has cost for this strategy so far (recorded rows)."""
    return int(db.execute(
        select(func.coalesce(func.sum(ApiUsage.cost_micros), 0))
        .where(ApiUsage.strategy_id == strategy_id, ApiUsage.purpose == PURPOSE)
    ).scalar_one() or 0)


def _scope(db: Session, run: QuickstartRun):
    return usage_meter.scope(db, strategy_id=run.strategy_id, user_id=run.user_id,
                             purpose=PURPOSE, budget_micros=run.budget_micros,
                             prior_micros=spent_micros(db, run.strategy_id))


# --------------------------------------------------------------------------
# Stage 1: fetch + ICP + batch
# --------------------------------------------------------------------------


def icp_research_text(offer: str, url: str, page_title: str, page_text: str) -> str:
    """The 'research' handed to the existing ICP extractor.

    The offer is the account owner's own line (trusted). The page is
    UNTRUSTED (F-AI-02): delimited and escaped with prompt_safety, behind the
    NOTICE that says what the markers mean."""
    page = (f"{page_title}\n{page_text}".strip())[:ICP_PROMPT_TEXT_CHARS]
    return (
        f"{prompt_safety.NOTICE}\n\n"
        f"[Quickstart] The account owner sells the offer below and wants the "
        f"buyers most likely to need it.\n\n"
        f"ONE-LINE OFFER (from the account owner):\n{offer}\n\n"
        f"THEIR PUBLIC WEBSITE ({prompt_safety.inline(url)}):\n"
        + (prompt_safety.block(page) if page else "(the page had no readable text)")
    )


def _fail(db: Session, run: QuickstartRun, reason: str) -> None:
    run.status = FAILED
    run.error = reason[:500]
    db.commit()
    logger.info("quickstart run %s failed: %s", run.id, reason)


def start_impl(db: Session, run_id, *, fetch=None, now=None) -> uuid.UUID | None:
    """Fetch the page, derive the ICP, create the lead batch.

    Returns the batch id the caller chains the lead pipeline on, or None when
    the run stopped (failed / flag off / already past this stage). Idempotent:
    a run that already has a batch returns it without refetching."""
    from app.services import icp_extraction, safe_fetch  # noqa: PLC0415
    from app.workers import lead_tasks  # noqa: PLC0415

    fetch = fetch or safe_fetch.fetch_page
    run = db.get(QuickstartRun, run_id)
    if run is None:
        return None
    if run.lead_batch_id is not None:
        return run.lead_batch_id
    if run.status not in (QUEUED, FETCHING, EXTRACTING):
        return None
    if not enabled(db):
        _fail(db, run, TURNED_OFF)
        return None
    strategy = db.get(Strategy, run.strategy_id)
    if strategy is None:
        _fail(db, run, "the strategy was deleted")
        return None

    # ---- fetch (untrusted, SSRF-guarded) ---------------------------------
    run.status = FETCHING
    db.commit()
    detail = dict(run.detail_json or {})
    title, text = "", ""
    try:
        page = fetch(run.website_url)
        title, text = page.title, page.text
        run.website_meta_json = page.meta()
        run.website_text = (text or "")[:MAX_WEBSITE_TEXT_CHARS]
    except safe_fetch.UnsafeURL as exc:
        # The host resolved into a private network (or redirected there).
        # Never fall back to anything for this: refuse the run.
        _fail(db, run, f"website not allowed: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001 -- the offer alone can still drive the ICP
        detail["fetch_error"] = str(exc)[:300]
        logger.info("quickstart run %s: website not readable (%s); offer only", run.id, exc)
    run.fetched_at = now or _now()
    run.detail_json = detail
    run.status = EXTRACTING
    db.commit()
    _timing(run, "fetched", run.fetched_at)

    # ---- ICP (existing extractor, metered) -------------------------------
    research = icp_research_text(run.offer, run.website_url, title, text)
    try:
        with _scope(db, run):
            criteria = icp_extraction.criteria_from_research(research)
    except usage_meter.BudgetExceededError as exc:
        _fail(db, run, f"AI budget reached before the ICP could be derived: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001
        logger.exception("quickstart run %s: ICP extraction failed", run.id)
        _fail(db, run, f"could not derive an ICP ({type(exc).__name__})")
        return None
    if not any(criteria.get(k) for k in icp_extraction.CRITERIA_KEYS):
        _fail(db, run, "could not derive an ICP from the website and offer")
        return None
    run.icp_criteria_json = criteria
    run.icp_at = now or _now()
    db.commit()
    _timing(run, "icp", run.icp_at)

    # ---- batch (existing chain; plan room enforced here AND per lead) ----
    room = lead_tasks.strategy_lead_room(db, strategy.id)
    requested = run.lead_target
    if room is not None:
        requested = min(requested, room)
    if requested <= 0:
        _fail(db, run, "this plan's leads-per-strategy limit leaves no room for Quickstart leads")
        return None
    batch = LeadBatch(
        strategy_id=strategy.id, requested_leads=requested,
        icp_criteria_json=criteria,
        source_provider=settings.lead_source_provider,
        verifier_provider=settings.email_verifier_provider,
    )
    db.add(batch)
    db.flush()
    run.lead_batch_id = batch.id
    run.status = SOURCING
    run.sourcing_started_at = now or _now()
    run.detail_json = {**detail, "requested": requested}
    db.commit()
    _timing(run, "sourcing_started", run.sourcing_started_at)
    return batch.id


# --------------------------------------------------------------------------
# Stage 2: drafts (after the lead chain finalized)
# --------------------------------------------------------------------------


def _draft_step(run: QuickstartRun, product_name: str) -> SequenceStep:
    """An UNSAVED step carrying the Quickstart brief, so the existing
    render_message can be reused unchanged. Never added to the session."""
    return SequenceStep(step_no=1, variant="A", template=DRAFT_BRIEF.format(
        offer=run.offer.replace('"', "'"), product=product_name))


def draft_impl(db: Session, run_id, *, now=None) -> dict:
    """Write one review-only draft per VERIFIED lead of the run's batch.

    Per-draft commits (resume-safe; UNIQUE(run_id, lead_id) makes a re-run
    skip what exists). Stops cleanly on the run's budget or the plan's daily
    cap; drafts already written stay."""
    from app.db.models import Product  # noqa: PLC0415
    from app.services import claim_verification  # noqa: PLC0415
    from app.services.message_personalization import render_message  # noqa: PLC0415
    from app.workers.lead_tasks import is_suppressed  # noqa: PLC0415

    run = db.get(QuickstartRun, run_id)
    if run is None or run.lead_batch_id is None:
        return {"drafted": 0, "stopped": "no_batch"}
    if run.status in (READY, FAILED):
        return {"drafted": 0, "stopped": run.status}
    if not enabled(db):
        _fail(db, run, TURNED_OFF)
        return {"drafted": 0, "stopped": "disabled"}
    strategy = db.get(Strategy, run.strategy_id)
    if strategy is None:
        _fail(db, run, "the strategy was deleted")
        return {"drafted": 0, "stopped": "no_strategy"}
    product = db.get(Product, run.product_id)
    step = _draft_step(run, product.name if product else "our product")

    run.status = DRAFTING
    db.commit()

    already = set(db.execute(
        select(QuickstartDraft.lead_id).where(QuickstartDraft.run_id == run.id)
    ).scalars())
    leads = db.execute(
        select(Lead).where(Lead.batch_id == run.lead_batch_id,
                           Lead.strategy_id == run.strategy_id,
                           Lead.status == LeadStatus.VERIFIED)
        .order_by(Lead.ai_booking_likelihood.desc().nulls_last(), Lead.created_at)
        .limit(run.lead_target)
    ).scalars().all()

    counts = {"verified": len(leads), "drafted": 0, "skipped_suppressed": 0,
              "failed": 0, "budget_reached": False}
    stopped = None
    with _scope(db, run):
        for lead in leads:
            if lead.id in already:
                continue
            # Re-checked here, not only at sourcing: an opt-out can arrive
            # while the chain runs. A suppressed person gets no draft.
            if is_suppressed(db, lead.email, lead.phone, linkedin=lead.linkedin_url):
                counts["skipped_suppressed"] += 1
                continue
            try:
                subject, body = render_message(db, strategy, lead, step)
                checked = claim_verification.enforce(
                    db, strategy=strategy, lead=lead, message=None, channel="email",
                    fields={"subject": subject, "body": body})
            except usage_meter.BudgetExceededError as exc:
                db.rollback()
                counts["budget_reached"] = True
                stopped = ("account_daily_cap"
                           if isinstance(exc, usage_meter.AccountBudgetExceededError)
                           else "run_budget")
                break
            except Exception:  # noqa: BLE001 -- one lead's failure is not the run's
                db.rollback()
                logger.exception("quickstart run %s: draft failed for lead %s", run.id, lead.id)
                counts["failed"] += 1
                continue
            changed = sum(1 for obj in db.new if isinstance(obj, ClaimVerificationLog)
                          and obj.verdict != claim_verification.VERIFIED)
            db.add(QuickstartDraft(
                run_id=run.id, user_id=run.user_id, lead_id=lead.id,
                subject=(checked.get("subject") or claim_verification.GENERIC_SUBJECT)[:500],
                body=checked.get("body") or "", status=DRAFT, claims_changed=changed))
            if run.first_draft_at is None:
                run.first_draft_at = now or _now()
            db.commit()
            usage_meter.flush_active(db)
            counts["drafted"] += 1
            if counts["drafted"] == 1:
                _timing(run, "first_draft", run.first_draft_at)

    run.status = READY
    run.ready_at = now or _now()
    run.detail_json = {**(run.detail_json or {}), **counts,
                       **({"stopped": stopped} if stopped else {})}
    if counts["verified"] == 0:
        run.error = "no verified leads were found for this ICP"
    db.commit()
    _timing(run, "ready", run.ready_at)
    return {**counts, "stopped": stopped}


# --------------------------------------------------------------------------
# Supersede, read models, erasure
# --------------------------------------------------------------------------


def refresh_superseded(db: Session, run: QuickstartRun, *, now=None) -> bool:
    """Stamp superseded_at once the strategy has finished its full pipeline.
    Returns whether the run is superseded."""
    if run.superseded_at is not None:
        return True
    strategy = db.get(Strategy, run.strategy_id)
    if strategy is not None and strategy.status in SUPERSEDING_STATUSES:
        run.superseded_at = now or _now()
        db.commit()
        return True
    return False


def owned_run(db: Session, run_id, user_id) -> QuickstartRun | None:
    return db.execute(
        select(QuickstartRun).where(QuickstartRun.id == run_id,
                                    QuickstartRun.user_id == user_id)
    ).scalar_one_or_none()


def owned_draft(db: Session, draft_id, user_id) -> QuickstartDraft | None:
    return db.execute(
        select(QuickstartDraft).where(QuickstartDraft.id == draft_id,
                                      QuickstartDraft.user_id == user_id)
    ).scalar_one_or_none()


def list_runs(db: Session, user_id, limit: int = 20) -> list[QuickstartRun]:
    return list(db.execute(
        select(QuickstartRun).where(QuickstartRun.user_id == user_id)
        .order_by(QuickstartRun.created_at.desc()).limit(limit)
    ).scalars())


def _iso(value: datetime | None) -> str | None:
    value = _aware(value)
    return value.isoformat() if value else None


def run_out(db: Session, run: QuickstartRun, *, drafts: bool = False) -> dict:
    superseded = run.superseded_at is not None
    batch = db.get(LeadBatch, run.lead_batch_id) if run.lead_batch_id else None
    strategy = db.get(Strategy, run.strategy_id)
    out = {
        "id": str(run.id), "status": run.status, "error": run.error,
        "website_url": run.website_url, "offer": run.offer,
        "product_id": str(run.product_id), "strategy_id": str(run.strategy_id),
        "strategy_status": strategy.status.value if strategy else None,
        "icp": run.icp_criteria_json, "website": run.website_meta_json,
        "lead_target": run.lead_target,
        "budget_usd": (round(run.budget_micros / 1_000_000, 2)
                       if run.budget_micros is not None else None),
        "spent_usd": round(spent_micros(db, run.strategy_id) / 1_000_000, 4),
        "detail": run.detail_json or {},
        "batch": ({"id": str(batch.id), "stage": batch.stage.value, "error": batch.error,
                   "requested": batch.requested_leads}
                  if batch else None),
        "superseded": superseded,
        "label": SUPERSEDED_LABEL if superseded else LABEL,
        "review_only": True,
        "created_at": _iso(run.created_at),
        "fetched_at": _iso(run.fetched_at), "icp_at": _iso(run.icp_at),
        "sourcing_started_at": _iso(run.sourcing_started_at),
        "first_draft_at": _iso(run.first_draft_at), "ready_at": _iso(run.ready_at),
        "superseded_at": _iso(run.superseded_at),
        "seconds_to_first_draft": _seconds_since_created(run, run.first_draft_at),
    }
    if drafts:
        rows = db.execute(
            select(QuickstartDraft, Lead)
            .join(Lead, Lead.id == QuickstartDraft.lead_id)
            .where(QuickstartDraft.run_id == run.id,
                   QuickstartDraft.user_id == run.user_id)
            .order_by(QuickstartDraft.created_at)
        ).all()
        out["drafts"] = [draft_out(d, lead, superseded) for d, lead in rows]
    return out


def draft_out(draft: QuickstartDraft, lead: Lead | None, superseded: bool = False) -> dict:
    return {
        "id": str(draft.id), "run_id": str(draft.run_id), "status": draft.status,
        "label": SUPERSEDED_LABEL if superseded else LABEL,
        "subject": draft.subject, "body": draft.body,
        "claims_changed": draft.claims_changed,
        "lead": ({"id": str(lead.id), "full_name": lead.full_name, "title": lead.title,
                  "company": lead.company, "email": lead.email} if lead else None),
        "created_at": _iso(draft.created_at),
    }


def erase_lead_drafts(db: Session, lead_id) -> int:
    """GDPR erasure: a draft quotes the person's name and company, and erasure
    tombstones the lead row rather than deleting it, so the FK cascade never
    fires. Called by DELETE /leads/{id}. Caller commits."""
    result = db.execute(delete(QuickstartDraft).where(QuickstartDraft.lead_id == lead_id))
    return int(result.rowcount or 0)

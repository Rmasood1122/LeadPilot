"""Fill outcomes.strategy_id and outcomes.variant on every new Outcome.

Why this exists (product defect #2, docs/program/fixes/product-defects.md):
the learning loop (app/services/score_decay.py JOINs strategies ON
outcomes.strategy_id) and A/B statistics (app/services/ab_testing.py,
app/services/multi_variate.py) read two denormalized columns that almost no
write path set: the send path put the variant only into meta_json, reply
paths wrote neither. So nightly scores and A/B statistics saw almost no data.

Rather than patching each of the ~15 places that construct an Outcome (and
every future one), a `before_flush` listener fills the two columns on each NEW
Outcome when the writer left them empty:

  strategy_id  <- the lead's strategy
  variant      <- the variant of the outcome's OWN message (message_id), and
                  nothing else. An event that is not linked to its message (a
                  bounce or reply matched only by address) gets no variant:
                  crediting it to "the variant sent last" is a guess that is
                  wrong whenever an earlier step's bounce arrives after a later
                  step went out (review M5).

Rules that keep it safe:
  * explicit values are never overwritten; rows with no lead (system events
    such as ab_promoted, circuit_opened) are left alone; insert-time only, so
    outcomes stay immutable;
  * attribution never breaks a commit: a failure is logged and the outcome is
    written as the writer gave it (review M4);
  * the hashed activity audit trail (app/services/audit_trail.py) records the
    payload the WRITER supplied -- a variant filled here is not added to it,
    so the chain only ever attests what the writer recorded (review M5).

`backfill()` applies the same rules to rows written before this existed (run
scripts/backfill_outcome_attribution.py; dry-run first).
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
import uuid
import weakref
from typing import Callable

from sqlalchemy import event, or_, select
from sqlalchemy.orm import Session

from app.db.models import Lead, Message, Outcome

logger = logging.getLogger(__name__)

_VARIANT_MAX = 20  # outcomes.variant is String(20)
_disabled: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "outcome_attribution_disabled", default=False)
# Outcomes whose variant was filled here rather than by their writer. The audit
# trail reads this so its hashed payload stays exactly what the writer gave.
_filled_variant: "weakref.WeakSet[Outcome]" = weakref.WeakSet()


@contextlib.contextmanager
def disabled():
    """Write Outcomes exactly as given (tests that need a pre-fix row)."""
    token = _disabled.set(True)
    try:
        yield
    finally:
        _disabled.reset(token)


def variant_was_filled(outcome: Outcome) -> bool:
    """True when this module, not the writer, set outcome.variant."""
    return outcome in _filled_variant


def _clean_variant(value) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()[:_VARIANT_MAX]
    return None


def _lead(session: Session, outcome: Outcome, lead_id: uuid.UUID) -> Lead | None:
    if outcome.lead is not None:
        return outcome.lead
    for obj in session.new:  # a lead added in the same flush
        if isinstance(obj, Lead) and obj.id == lead_id:
            return obj
    return session.get(Lead, lead_id)


def resolve(session: Session, outcome: Outcome) -> tuple[uuid.UUID | None, str | None]:
    """The (strategy_id, variant) the row should carry. Existing values win."""
    lead_id = outcome.lead_id
    if lead_id is None and outcome.lead is not None:
        lead_id = outcome.lead.id
    if lead_id is None:
        return outcome.strategy_id, outcome.variant

    strategy_id = outcome.strategy_id
    if strategy_id is None:
        lead = _lead(session, outcome, lead_id)
        strategy_id = lead.strategy_id if lead is not None else None

    variant = outcome.variant
    if variant is None and outcome.message_id is not None:
        message = session.get(Message, outcome.message_id)
        variant = _clean_variant(message.variant) if message is not None else None
    return strategy_id, variant


@event.listens_for(Session, "before_flush")
def _attribute_new_outcomes(session: Session, flush_context, instances) -> None:
    if _disabled.get():
        return
    new = [obj for obj in session.new if isinstance(obj, Outcome)]
    if not new:
        return
    with session.no_autoflush:
        for outcome in new:
            if outcome.strategy_id is not None and outcome.variant is not None:
                continue
            try:
                had_variant = outcome.variant is not None
                outcome.strategy_id, outcome.variant = resolve(session, outcome)
                if not had_variant and outcome.variant is not None:
                    _filled_variant.add(outcome)
            except Exception:  # noqa: BLE001 -- must never break the commit
                logger.exception("outcome attribution failed for outcome %s (lead %s); "
                                 "written without it", outcome.id, outcome.lead_id)


def backfill(session: Session, *, dry_run: bool = True, batch_size: int = 500,
             progress: Callable[[str], None] | None = None) -> int:
    """Fill strategy_id / variant on existing lead outcomes that lack them.

    Dry run by default. Returns the number of rows that changed (or would).
    Idempotent: a second run changes nothing. `progress` gets one line per
    batch. Rows written here are not in the audit trail's hashed payloads
    (those were sealed at insert), so the chain is unaffected.
    """
    changed = scanned = 0
    last_id = None
    while True:
        q = (select(Outcome)
             .where(Outcome.lead_id.is_not(None),
                    or_(Outcome.strategy_id.is_(None), Outcome.variant.is_(None)))
             .order_by(Outcome.id)
             .limit(batch_size))
        if last_id is not None:
            q = q.where(Outcome.id > last_id)
        rows = session.execute(q).scalars().all()
        if not rows:
            break
        with session.no_autoflush:
            for outcome in rows:
                try:
                    strategy_id, variant = resolve(session, outcome)
                except Exception:  # noqa: BLE001
                    logger.exception("backfill: could not resolve outcome %s", outcome.id)
                    continue
                if (strategy_id, variant) != (outcome.strategy_id, outcome.variant):
                    changed += 1
                    if not dry_run:
                        outcome.strategy_id, outcome.variant = strategy_id, variant
        scanned += len(rows)
        last_id = rows[-1].id
        if dry_run:
            session.rollback()
        else:
            session.commit()
        if progress is not None:
            progress(f"scanned {scanned} outcomes, {'would update' if dry_run else 'updated'} "
                     f"{changed}")
    return changed

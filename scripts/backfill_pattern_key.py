"""One-off backfill: recompute Strategy.pattern_key with the ICP+tactic hash.

WHY
    pattern_key is documented as "SHA-256 of sorted canonical ICP/tactic JSON"
    but was derived from the ICP alone, so two strategies aimed at the same
    buyer through completely different channels and cadences shared one
    playbook bucket and had their outcomes averaged together. Including the
    tactic half changes the derivation, so every existing value is stale.

WHAT CHANGING THE DERIVATION INVALIDATES
    pattern_key is an opaque join key everywhere it is consumed (playbook.py,
    playbook_service.py, score_decay.py, learning_tasks.py, admin*.py) - no
    code compares it to a literal and nothing caches it outside Postgres. The
    one thing that IS keyed on it is stored data: playbook_scores rows. After
    a backfill the old rows are orphans - no strategy points at them, so
    get_insights() (which filters on strategies' live keys) stops seeing them,
    and the nightly aggregation recreates the scores under the new keys from
    the outcomes table, which is the real source of truth. Orphans are
    reported, and only deleted when you pass --delete-orphans.

COST
    pattern_key's inputs are NOT persisted anywhere - they are re-derived from
    the strategy's research steps by the model. A faithful recompute therefore
    makes two Anthropic calls per strategy, so this needs a real
    ANTHROPIC_API_KEY. (Persisting the criteria on the strategy would remove
    that; see the handoff.)

USAGE
    python -m scripts.backfill_pattern_key                 # dry run, reports only
    python -m scripts.backfill_pattern_key --apply
    python -m scripts.backfill_pattern_key --apply --delete-orphans
"""
from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger("backfill_pattern_key")


def backfill(session, *, apply: bool = False, delete_orphans: bool = False) -> dict:
    """Recompute pattern_key for every strategy. Returns a summary dict.

    Safe to run repeatedly: a strategy whose recomputed key already matches is
    counted as unchanged and not written.
    """
    from sqlalchemy import select

    from app.db.models import PlaybookScore, Strategy
    from app.services.icp_extraction import (
        canonical_pattern_payload,
        extract_icp_criteria,
        extract_tactic_profile,
        pattern_key_of,
    )

    strategies = session.execute(select(Strategy)).scalars().all()
    summary = {
        "total": len(strategies),
        "changed": 0,
        "unchanged": 0,
        "skipped": 0,
        "rehashed": 0,
        "rederived": 0,
        "orphaned_scores": 0,
        "deleted_scores": 0,
        "applied": apply,
    }

    for strategy in strategies:
        try:
            payload = strategy.pattern_inputs_json
            if payload:
                # Migration 0014 stores the exact dict that was hashed, so a
                # recompute is a pure rehash: offline, free, and deterministic.
                summary["rehashed"] += 1
            else:
                # Pre-0014 row: the inputs were never stored, so they have to
                # be re-derived from the research steps. Two Anthropic calls,
                # and NOT deterministic - the model may answer differently than
                # it did originally, so this can legitimately move an unchanged
                # strategy to a new bucket. Backfill the payload while here so
                # it only ever happens once per row.
                criteria = extract_icp_criteria(session, strategy)
                tactics = extract_tactic_profile(session, strategy)
                tactics = {
                    **tactics,
                    "flow_type": getattr(strategy.flow_type, "value",
                                         strategy.flow_type),
                }
                payload = canonical_pattern_payload(criteria, tactics)
                summary["rederived"] += 1
            new_key = pattern_key_of(payload)
        except Exception as exc:  # noqa: BLE001 - one bad row must not abort the run
            logger.warning("strategy %s skipped: %s", strategy.id, exc)
            summary["skipped"] += 1
            continue

        if strategy.pattern_key == new_key:
            summary["unchanged"] += 1
            if apply and not strategy.pattern_inputs_json:
                strategy.pattern_inputs_json = payload   # 0014 backfill
            continue

        summary["changed"] += 1
        logger.info("strategy %s: %s -> %s", strategy.id,
                    (strategy.pattern_key or "<null>")[:12], new_key[:12])
        if apply:
            strategy.pattern_key = new_key
            strategy.pattern_inputs_json = payload

    if apply:
        session.commit()

    # Which playbook_scores rows no longer belong to any strategy?
    live_keys = {
        k for (k,) in session.execute(
            select(Strategy.pattern_key).where(Strategy.pattern_key.isnot(None))
        ).all()
    }
    orphans = [
        row for row in session.execute(select(PlaybookScore)).scalars().all()
        if row.pattern_key not in live_keys
    ]
    summary["orphaned_scores"] = len(orphans)

    if orphans and delete_orphans and apply:
        for row in orphans:
            session.delete(row)
        session.commit()
        summary["deleted_scores"] = len(orphans)

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="write the recomputed keys (default: dry run)")
    parser.add_argument("--delete-orphans", action="store_true",
                        help="also delete playbook_scores rows no strategy "
                             "points at any more (they are derived data and "
                             "the nightly aggregation rebuilds them)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from app.db.base import SessionLocal

    session = SessionLocal()
    try:
        summary = backfill(session, apply=args.apply,
                           delete_orphans=args.delete_orphans)
    finally:
        session.close()

    mode = "APPLIED" if args.apply else "DRY RUN (nothing written)"
    print(f"\n=== pattern_key backfill — {mode} ===")
    for key in ("total", "changed", "unchanged", "skipped",
                "rehashed", "rederived", "orphaned_scores", "deleted_scores"):
        print(f"  {key:18s} {summary[key]}")
    if summary["orphaned_scores"] and not summary["deleted_scores"]:
        print("\n  NOTE: orphaned playbook_scores rows remain. They are invisible"
              "\n  to get_insights() (it filters on live strategy keys) and the"
              "\n  nightly aggregation rebuilds scores under the new keys."
              "\n  Re-run with --apply --delete-orphans to remove them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

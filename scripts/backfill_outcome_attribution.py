"""One-off backfill: fill outcomes.strategy_id / outcomes.variant on old rows.

WHY
    Product defect #2 (docs/program/fixes/product-defects.md). Until the
    listener in app/db/outcome_attribution.py, the send and reply paths left
    both columns empty, so the nightly learning roll-up and A/B promotion
    (which filter on them) never saw those rows. New rows are filled at insert
    time; this applies the same rules to rows written before.

RULES (same as the listener)
    strategy_id <- the lead's strategy
    variant     <- the variant of the outcome's own message (message_id) only;
                   an event not linked to its message gets no variant (no
                   guessing from "the variant sent last")
    Values already present are never changed; rows without a lead are skipped.

EFFECT
    The next nightly roll-up (02:05 UTC) recomputes playbook scores from the
    whole outcomes table, so old sends and replies start counting. A/B
    auto-promotion only acts if an admin has turned on
    ab_auto_promotion_enabled (off by default). No message is sent or changed.
    The hashed activity audit trail is not touched (its payloads were sealed
    when each outcome was written).

USAGE
    python -m scripts.backfill_outcome_attribution                  # dry run: count only
    python -m scripts.backfill_outcome_attribution --batch-size 1000
    python -m scripts.backfill_outcome_attribution --apply          # writes; back up first
"""
from __future__ import annotations

import argparse
import sys


WARNING = """\
WARNING: this rewrites outcomes.strategy_id / outcomes.variant on PRODUCTION
learning-loop data. Run the dry run first, take a database backup, and run
--apply only on a founder decision (docs/program/fixes/product-defects.md #2).
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true",
                        help="write the changes (default: dry run, nothing written)")
    parser.add_argument("--batch-size", type=int, default=500,
                        help="outcomes per batch / commit (default 500)")
    args = parser.parse_args(argv)
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")

    from app.db import outcome_attribution
    from app.db.base import SessionLocal

    print(WARNING)
    print("MODE:", "APPLY (writing)" if args.apply else "DRY RUN (nothing is written)")
    session = SessionLocal()
    try:
        changed = outcome_attribution.backfill(
            session, dry_run=not args.apply, batch_size=args.batch_size,
            progress=lambda line: print(line, flush=True))
    finally:
        session.close()
    verb = "updated" if args.apply else "would update"
    print(f"outcomes {verb}: {changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

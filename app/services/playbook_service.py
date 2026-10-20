"""PlaybookService — learned-tactic insights for the research pipeline (M8-C1).

Reconstructed for the combined build to the original contract:

    PlaybookService.get_insights(db, user_id=None, limit=8) -> str

F-DB-01: only the given account's own rows are read (playbook_scores.user_id);
without a user_id the empty block is returned.

Used by the pipeline engine at Phase 6 (messaging & offer design) and
Phase 8 (execution plan). The returned block is injected into the step
prompt so new strategies consult what actually worked before.

Graceful empty handling is a hard requirement: on a fresh install (no
outcomes yet) this returns an explicit "no playbook data yet" block — the
pipeline must behave identically on run #1 and run #1000.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

log = logging.getLogger(__name__)

_EMPTY_BLOCK = (
    "[Playbook insights]\n"
    "No learned playbook data is available yet (first strategies for this "
    "account). Proceed with research-driven best practices; the learning "
    "loop will populate this section from real outcomes."
)


class PlaybookService:
    @staticmethod
    def get_insights(db, user_id: str | uuid.UUID | None = None, limit: int = 8) -> str:
        """Top reliable playbook scores OF THIS ACCOUNT, as a compact prompt block.

        F-DB-01: only rows owned by `user_id` are read. Without an owner there
        is no account to learn from, so the empty block is returned -- there is
        no global fallback, because a pooled or foreign row in a prompt would
        present another account's results as this account's.

        Never raises — pipeline steps must not fail because the learning
        loop tables are empty or mid-migration.
        """
        if user_id is None:
            return _EMPTY_BLOCK
        try:
            from app.db.models import PlaybookScore as ps  # noqa: PLC0415

            owner = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
            rows = db.execute(
                select(ps.pattern_key, ps.variant, ps.reply_rate, ps.booking_rate,
                       ps.sample_size, ps.trend)
                .where(ps.user_id == owner, ps.is_reliable.is_(True))
                .order_by(ps.booking_rate.desc().nulls_last(),
                          ps.reply_rate.desc().nulls_last())
                .limit(limit)
            ).mappings().all()

            if not rows:
                return _EMPTY_BLOCK

            lines = ["[Playbook insights — learned from this account's real outcomes]"]
            for r in rows:
                lines.append(
                    f"- pattern={r['pattern_key']}"
                    f" variant={r['variant'] or '-'}"
                    f" reply_rate={float(r['reply_rate'] or 0):.1%}"
                    f" booking_rate={float(r['booking_rate'] or 0):.1%}"
                    f" n={int(r['sample_size'] or 0)}"
                    f" trend={r['trend'] or 'new'}"
                )
            lines.append(
                "Prefer tactics matching high-scoring patterns; avoid repeating "
                "patterns with falling trends."
            )
            return "\n".join(lines)
        except Exception as exc:  # pragma: no cover — defensive by contract
            log.warning("playbook insights unavailable: %s", exc)
            return _EMPTY_BLOCK

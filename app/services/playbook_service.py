"""PlaybookService — learned-tactic insights for the research pipeline (M8-C1).

Reconstructed for the combined build to the original contract:

    PlaybookService.get_insights(db, user_id=None, limit=8) -> str

Used by the pipeline engine at Phase 6 (messaging & offer design) and
Phase 8 (execution plan). The returned block is injected into the step
prompt so new strategies consult what actually worked before.

Graceful empty handling is a hard requirement: on a fresh install (no
outcomes yet) this returns an explicit "no playbook data yet" block — the
pipeline must behave identically on run #1 and run #1000.
"""
from __future__ import annotations

import logging

from sqlalchemy import text

log = logging.getLogger(__name__)

_EMPTY_BLOCK = (
    "[Playbook insights]\n"
    "No learned playbook data is available yet (first strategies for this "
    "account). Proceed with research-driven best practices; the learning "
    "loop will populate this section from real outcomes."
)


class PlaybookService:
    @staticmethod
    def get_insights(db, user_id: str | None = None, limit: int = 8) -> str:
        """Top reliable playbook scores rendered as a compact prompt block.

        Never raises — pipeline steps must not fail because the learning
        loop tables are empty or mid-migration.
        """
        try:
            params: dict = {"limit": limit}
            user_filter = ""
            if user_id:
                # Scope to the user's own strategies' pattern keys when the
                # column linkage exists; fall back to global patterns.
                user_filter = """
                    AND ps.pattern_key IN (
                        SELECT DISTINCT s.pattern_key
                        FROM strategies s
                        JOIN products p ON p.id = s.product_id
                        WHERE p.user_id = :uid AND s.pattern_key IS NOT NULL
                    )
                """
                params["uid"] = user_id

            rows = db.execute(text(f"""
                SELECT ps.pattern_key, ps.variant, ps.reply_rate,
                       ps.booking_rate, ps.sample_size, ps.trend
                FROM playbook_scores ps
                WHERE COALESCE(ps.is_reliable, false) = true
                  {user_filter}
                ORDER BY ps.booking_rate DESC NULLS LAST,
                         ps.reply_rate DESC NULLS LAST
                LIMIT :limit
            """), params).mappings().all()

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

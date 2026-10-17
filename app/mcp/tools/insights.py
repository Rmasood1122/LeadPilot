"""Attribution tool: get_attribution_summary.

attribution.summary / ledger filter on AttributionEntry.user_id, the owner
stamped at write time.
"""

from __future__ import annotations

from typing import Any, Annotated

from pydantic import Field

from app.mcp import untrusted
from app.mcp.context import tool_call
from app.mcp.tools import optional_id, read_only
from app.services import attribution, crm_service

MAX_RECENT = 20


def register(server) -> None:

    @server.tool(
        name="get_attribution_summary",
        title="Get attribution summary",
        description=(
            "Returns which outreach earned the user's outcomes (meetings booked, "
            "positive replies, deals won): totals by sequence step, channel and "
            "attribution method, how many are certain (a direct reply) versus "
            "inferred, the median hours from message to outcome, and the most "
            "recent attributed outcomes (recent_limit 0-20). Optional strategy_id."),
        annotations=read_only("Get attribution summary"),
    )
    def get_attribution_summary(
        strategy_id: str | None = None,
        recent_limit: Annotated[int, Field(ge=0, le=MAX_RECENT)] = 5,
    ) -> dict[str, Any]:
        strategy_uuid = optional_id(strategy_id, "strategy_id")
        with tool_call() as call:
            if strategy_uuid is not None:
                crm_service.owned_strategy(call.db, strategy_uuid, call.user)
            summary = attribution.summary(call.db, call.user.id, strategy_uuid)
            recent = (attribution.ledger(call.db, call.user.id, strategy_id=strategy_uuid,
                                         limit=recent_limit)["items"]
                      if recent_limit else [])
        recent_out = [
            {
                "id": e["id"], "outcome_kind": e["outcome_kind"],
                "outcome_at": e["outcome_at"],
                "lead_id": e["lead"]["id"] if e["lead"] else None,
                "message_id": e["message_id"], "channel": e["channel"],
                "step_no": e["step_no"], "hours_to_outcome": e["hours_to_outcome"],
                "method": e["method"], "confidence": e["confidence"],
                "is_certain": e["is_certain"],
                **untrusted.envelope({
                    "lead_name": e["lead"]["full_name"] if e["lead"] else None,
                    "lead_company": e["lead"]["company"] if e["lead"] else None,
                    "subject": e["subject"], "body": e["body"],
                    "evidence": e["evidence"],
                }),
            }
            for e in recent
        ]
        return {
            "summary": (f"{summary['total']} attributed outcomes, "
                        f"{summary['certain']} certain (direct reply)."),
            **summary,
            "recent": recent_out,
            "untrusted_content_notice": untrusted.NOTICE,
        }

"""Message tools: list_messages, get_message.

Through message_read (tenant filter on the lead's Product.user_id). A list
carries structured fields only; get_message adds subject/body -- model
output written from prospect data -- under untrusted_content.
"""

from __future__ import annotations

from typing import Any, Annotated, Literal

from pydantic import Field

from app.db.models import ChannelType, MessageStatus
from app.mcp import untrusted
from app.mcp.context import tool_call
from app.mcp.tools import MAX_LIMIT, optional_id, parse_id, read_only
from app.services import crm_service, message_read

MessageStatusArg = Literal[
    "scheduled", "sending", "sent", "failed", "cancelled", "bounced", "skipped",
    "needs_template", "awaiting_review",
]
ChannelArg = Literal["email", "whatsapp", "linkedin", "phone"]


def register(server) -> None:

    @server.tool(
        name="list_messages",
        title="List messages",
        description=(
            "Lists the signed-in user's outreach messages (scheduled, sent, failed, "
            "awaiting review, ...), most recent activity first, without their text. "
            "Optional filters: status, channel, strategy_id, lead_id. Use "
            "offset/limit (limit 1-50) to page."),
        annotations=read_only("List messages"),
    )
    def list_messages(
        status: MessageStatusArg | None = None,
        channel: ChannelArg | None = None,
        strategy_id: str | None = None,
        lead_id: str | None = None,
        limit: Annotated[int, Field(ge=1, le=MAX_LIMIT)] = 20,
        offset: Annotated[int, Field(ge=0)] = 0,
    ) -> dict[str, Any]:
        strategy_uuid = optional_id(strategy_id, "strategy_id")
        lead_uuid = optional_id(lead_id, "lead_id")
        with tool_call() as call:
            if strategy_uuid is not None:
                crm_service.owned_strategy(call.db, strategy_uuid, call.user)
            if lead_uuid is not None:
                crm_service.owned_lead(call.db, lead_uuid, call.user)
            page = message_read.list_owned(
                call.db, call.user,
                status=MessageStatus(status) if status else None,
                channel=ChannelType(channel) if channel else None,
                strategy_id=strategy_uuid, lead_id=lead_uuid,
                limit=limit, offset=offset)
            items = [message_read.message_out(m, include_body=False)
                     for m in page["items"]]
        return {
            "summary": (f"{len(items)} of {page['total']} messages "
                        f"(offset {offset}); has_more={page['has_more']}."),
            "total": page["total"], "limit": page["limit"], "offset": page["offset"],
            "has_more": page["has_more"], "items": items,
        }

    @server.tool(
        name="get_message",
        title="Get message",
        description=(
            "Returns one outreach message by id: channel, step, status, schedule "
            "and send times, opens, and its subject and body."),
        annotations=read_only("Get message"),
    )
    def get_message(message_id: str) -> dict[str, Any]:
        message_uuid = parse_id(message_id, "message_id")
        with tool_call() as call:
            out = message_read.message_out(
                message_read.owned_message(call.db, message_uuid, call.user),
                include_body=True)
        text = {k: out.pop(k) for k in ("subject", "body", "error")}
        return {
            "summary": (f"Message {out['id']}: {out['channel']} step {out['step_no']}, "
                        f"status {out['status']}."),
            **out, **untrusted.envelope(text),
            "untrusted_content_notice": untrusted.NOTICE,
        }

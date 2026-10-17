"""Pause and resume a strategy's outreach campaign: the code path the REST
API (app/api/analytics.py) and the connector share (DECISIONS.md
CONN-SERVICES). Moved from the route handlers unchanged.

Pausing takes effect where sending happens: the dispatcher skips a campaign
that is not active and send_message_impl re-checks the state before every
send (app/workers/outreach_tasks.py). Resuming restarts sending, so it
passes the F03 deliverability preflight first (409 when blocked); every
message still passes the full send-time gate, daily send approval included.

Callers resolve the strategy with an ownership check first
(crm_service.owned_strategy or the router's own helper).
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import Strategy, User
from app.services import sequence_engine as engine

PAUSED_MANUAL = "paused_manual"


def pause(db: Session, strategy: Strategy, owner: User) -> dict:
    strategy.campaign_state = PAUSED_MANUAL
    strategy.campaign_pause_reason = "paused by user"
    db.commit()
    # Feature Group 4: outbound webhooks only -- the user just did this, so
    # neither a push nor a Slack message would tell them anything.
    from app.workers import notification_tasks  # noqa: PLC0415

    notification_tasks.enqueue_event(
        owner.id, "campaign_paused", push=False, slack=False, title="Campaign paused",
        body="Paused by you.", deep_link=f"/campaigns?strategy={strategy.id}",
        webhook_payload={"strategy_id": str(strategy.id), "trigger": "manual",
                         "reason": strategy.campaign_pause_reason},
    )
    return {"campaign_state": strategy.campaign_state,
            "campaign_pause_reason": strategy.campaign_pause_reason}


def resume(db: Session, strategy: Strategy) -> dict:
    # F03 Deliverability Autopilot: resuming restarts sending, so it passes
    # the same preflight as a launch. Flag off: no-op.
    from app.services import deliverability_autopilot  # noqa: PLC0415

    blocked = deliverability_autopilot.launch_block(db, strategy, action="resume")
    if blocked:
        raise HTTPException(status_code=409, detail=blocked)
    strategy.campaign_state = engine.CAMPAIGN_ACTIVE
    strategy.campaign_pause_reason = None
    db.commit()
    return {"campaign_state": strategy.campaign_state,
            "campaign_pause_reason": None}

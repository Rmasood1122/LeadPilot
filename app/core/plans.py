"""
Plan definitions and enforcement layer.

Plans are defined as code — not in the DB — so they're deployable without
migrations. Plan definitions rarely change; plan upgrades (writing to users.plan)
are the DB operation.

Enforcement returns HTTP 402 with structured body so the frontend can show
an "Upgrade your plan" modal immediately without additional API calls:
    {
        "error": "plan_limit_exceeded",
        "limit": "max_strategies",
        "current_plan": "free",
        "upgrade_to": "starter",
        "message": "Free plan allows 3 strategies. You have 3."
    }

Usage in route handlers:
    from app.core.plans import plan_requires, PlanGate

    @router.post("/products/{id}/strategies")
    async def create_strategy(
        ...,
        _gate: None = Depends(PlanGate("ab_testing")),
    ):
        ...

    # Or for count-based limits:
    check_plan_limit(user, "max_strategies", current_count=3)
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import Depends, HTTPException

from app.core.logging import get_logger

logger = get_logger("core.plans")

# ---------------------------------------------------------------------------
# Plan definitions (canonical — single source of truth)
# ---------------------------------------------------------------------------

PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "max_strategies": 3,
        "max_leads_per_strategy": 100,
        "max_sequence_steps": 5,
        "channels": ["gmail"],
        "ab_testing": False,
        "playbook_access": False,
        "multi_variate": False,
        # Website builder: the marketing pages that sell the product.
        "website_builder": False,
        "max_site_pages": 0,
        "api_rate_limit_multiplier": 1.0,
        "analytics_history_days": 30,
        "display_name": "Free",
        "upgrade_to": "starter",
    },
    "starter": {
        "max_strategies": 10,
        "max_leads_per_strategy": 500,
        "max_sequence_steps": 10,
        "channels": ["gmail", "whatsapp"],
        "ab_testing": True,
        "playbook_access": True,
        "multi_variate": False,
        "website_builder": True,
        "max_site_pages": 10,
        "api_rate_limit_multiplier": 2.0,
        "analytics_history_days": 90,
        "display_name": "Starter",
        "upgrade_to": "pro",
    },
    "pro": {
        "max_strategies": -1,
        "max_leads_per_strategy": -1,
        "max_sequence_steps": -1,
        "channels": ["gmail", "whatsapp"],
        "ab_testing": True,
        "playbook_access": True,
        "multi_variate": True,
        "website_builder": True,
        "max_site_pages": -1,
        "api_rate_limit_multiplier": 5.0,
        "analytics_history_days": -1,
        "display_name": "Pro",
        "upgrade_to": None,
    },
    # Combined-build addition: M5 PlanTier includes 'enterprise';
    # mirror 'pro' entitlements so those users are never HTTP-402'd.
    "enterprise": {
        "max_strategies": -1,
        "max_leads_per_strategy": -1,
        "max_sequence_steps": -1,
        "channels": ["gmail", "whatsapp"],
        "ab_testing": True,
        "playbook_access": True,
        "multi_variate": True,
        "website_builder": True,
        "max_site_pages": -1,
        "api_rate_limit_multiplier": 5.0,
        "analytics_history_days": -1,
        "display_name": "Enterprise",
        "upgrade_to": None,
    },
}

_PLAN_UPGRADE_PATH = {
    "free": "starter",
    "starter": "pro",
    "pro": None,
}


class PlanLimitExceeded(Exception):
    def __init__(self, limit_key: str, current_plan: str, upgrade_to: Optional[str], message: str):
        self.limit_key = limit_key
        self.current_plan = current_plan
        self.upgrade_to = upgrade_to
        self.message = message


def get_plan(plan_name: str) -> dict[str, Any]:
    """Return plan definition. Defaults to 'free' if plan_name is unknown."""
    return PLANS.get(plan_name, PLANS["free"])


def check_plan_limit(user, resource: str, current_count: int) -> None:
    """
    Raise PlanLimitExceeded if current_count would exceed the user's plan limit.

    resource: "max_strategies" | "max_leads_per_strategy" | "max_sequence_steps"
    """
    plan_name = getattr(user, "plan", "free") or "free"
    plan = get_plan(plan_name)
    limit = plan.get(resource, -1)

    if limit == -1:
        return  # unlimited

    if current_count >= limit:
        upgrade_to = _PLAN_UPGRADE_PATH.get(plan_name)
        raise PlanLimitExceeded(
            limit_key=resource,
            current_plan=plan_name,
            upgrade_to=upgrade_to,
            message=(
                f"{plan['display_name']} plan allows {limit} {resource.replace('max_', '').replace('_', ' ')}. "
                f"You have {current_count}."
            ),
        )


def check_feature(user, feature: str) -> None:
    """
    Raise PlanLimitExceeded if the user's plan does not include a boolean feature.

    feature: "ab_testing" | "playbook_access" | "multi_variate"
    """
    plan_name = getattr(user, "plan", "free") or "free"
    plan = get_plan(plan_name)

    if not plan.get(feature, False):
        upgrade_to = _PLAN_UPGRADE_PATH.get(plan_name)
        raise PlanLimitExceeded(
            limit_key=feature,
            current_plan=plan_name,
            upgrade_to=upgrade_to,
            message=(
                f"{plan['display_name']} plan does not include {feature.replace('_', ' ')}. "
                f"{'Upgrade to ' + (PLANS.get(upgrade_to or '', {}).get('display_name', upgrade_to) or '') if upgrade_to else 'No upgrade path available.'}"
            ),
        )


def check_channel(user, channel: str) -> None:
    """Raise PlanLimitExceeded if the channel is not in the user's plan."""
    plan_name = getattr(user, "plan", "free") or "free"
    plan = get_plan(plan_name)
    allowed = plan.get("channels", ["gmail"])

    if channel not in allowed:
        upgrade_to = _PLAN_UPGRADE_PATH.get(plan_name)
        raise PlanLimitExceeded(
            limit_key="channels",
            current_plan=plan_name,
            upgrade_to=upgrade_to,
            message=(
                f"{plan['display_name']} plan does not include {channel} channel. "
                f"Allowed: {', '.join(allowed)}."
            ),
        )


def plan_limit_response(exc: PlanLimitExceeded) -> dict:
    """Build the 402 response body from a PlanLimitExceeded exception."""
    return {
        "error": "plan_limit_exceeded",
        "limit": exc.limit_key,
        "current_plan": exc.current_plan,
        "upgrade_to": exc.upgrade_to,
        "message": exc.message,
    }


class PlanGate:
    """FastAPI Depends-compatible gate for boolean features."""

    def __init__(self, feature: str):
        self.feature = feature

    def __call__(self, current_user=Depends(None)):
        try:
            check_feature(current_user, self.feature)
        except PlanLimitExceeded as e:
            raise HTTPException(status_code=402, detail=plan_limit_response(e))

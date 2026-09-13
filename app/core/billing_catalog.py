"""The price list — two ways to pay, as code (Section E).

Like app/core/plans.py, prices are code rather than rows: they change rarely,
a deploy is the right review gate for a price change, and a pricing page that
reads the same module the checkout charges from cannot advertise a number the
checkout does not charge.

OPTION 1 — MONTHLY SUBSCRIPTION (the Recommended option)
  Four tiers, each with a free trial. Each tier's ENTITLEMENTS are the matching
  key in app/core/plans.py::PLANS -- and every limit advertised here is one the
  code already enforces there (strategies, leads per strategy, sequence steps,
  channels, A/B and multi-variate testing, analytics history). Nothing is sold
  that the product does not police.

OPTION 2 — PAY PER MEETING BOOKED
  No monthly fee. One charge per prospect who books a meeting through the
  platform, held for a cancellation grace period first and charged once per
  prospect. Metered by app/services/usage_meter.py::record_meeting_usage.

Prices are integer US cents, the unit Stripe charges in.
See BUILD_DECISIONS.md (Section E) for how the numbers were chosen.
"""

from __future__ import annotations

from typing import Any

CURRENCY = "usd"
TRIAL_DAYS = 14

MONTHLY = "monthly"
PAY_PER_MEETING = "pay_per_meeting"
BILLING_MODELS = (MONTHLY, PAY_PER_MEETING)

# Order matters: it is the good -> better -> best ladder the page renders.
MONTHLY_TIERS: list[dict[str, Any]] = [
    {
        "id": "starter",
        "name": "Starter",
        "price_cents": 14_900,
        "tagline": "For a founder running outbound themselves.",
        "plan": "starter",
    },
    {
        "id": "growth",
        "name": "Growth",
        "price_cents": 34_900,
        "tagline": "For a small team adding LinkedIn to email.",
        "plan": "growth",
    },
    {
        "id": "scale",
        "name": "Scale",
        "price_cents": 69_900,
        "tagline": "For an agency running every channel at volume.",
        "plan": "scale",
    },
    {
        "id": "enterprise",
        "name": "Enterprise",
        "price_cents": 149_900,
        "tagline": "No caps on campaigns, leads or API throughput.",
        "plan": "enterprise",
    },
]

PAY_PER_MEETING_PLAN: dict[str, Any] = {
    "id": PAY_PER_MEETING,
    "name": "Pay per meeting",
    "monthly_fee_cents": 0,
    "price_per_meeting_cents": 17_900,
    # A booking cancelled inside this window is never charged. 48h covers the
    # common "booked, then cancelled the next morning" case without holding
    # revenue for long.
    "grace_hours": 48,
    "tagline": "Pay only when a prospect books a meeting through LeadPilot.",
    "plan": PAY_PER_MEETING,
}

_TIERS = {tier["id"]: tier for tier in MONTHLY_TIERS}


def monthly_tier(tier_id: str | None) -> dict[str, Any] | None:
    return _TIERS.get((tier_id or "").strip().lower())


def plan_for(billing_model: str, tier_id: str | None) -> str | None:
    """The app/core/plans.py key a paid selection grants, or None if invalid."""
    if billing_model == PAY_PER_MEETING:
        return PAY_PER_MEETING_PLAN["plan"]
    if billing_model == MONTHLY:
        tier = monthly_tier(tier_id)
        return tier["plan"] if tier else None
    return None


def meeting_price_cents() -> int:
    return int(PAY_PER_MEETING_PLAN["price_per_meeting_cents"])


def catalog() -> dict[str, Any]:
    """The full price list with each tier's enforced entitlements attached."""
    from app.core.plans import PLANS  # noqa: PLC0415

    def _limits(plan_key: str) -> dict[str, Any]:
        plan = PLANS[plan_key]
        return {key: plan[key] for key in (
            "max_strategies", "max_leads_per_strategy", "max_sequence_steps",
            "channels", "ab_testing", "multi_variate", "playbook_access",
            "website_builder", "max_site_pages", "analytics_history_days",
            "api_rate_limit_multiplier")}

    return {
        "currency": CURRENCY,
        "trial_days": TRIAL_DAYS,
        "recommended": MONTHLY,
        "monthly": {
            "id": MONTHLY,
            "name": "Monthly subscription",
            "recommended": True,
            "tiers": [{**tier, "trial_days": TRIAL_DAYS, "limits": _limits(tier["plan"])}
                      for tier in MONTHLY_TIERS],
        },
        "pay_per_meeting": {**PAY_PER_MEETING_PLAN, "recommended": False,
                            "limits": _limits(PAY_PER_MEETING_PLAN["plan"])},
    }

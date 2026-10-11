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

OPTION 1b — ANNUAL SUBSCRIPTION (flag `annual_billing_enabled`, default off)
  The same four tiers and the same entitlements, billed once a year at
  monthly price x ANNUAL_MONTHS_CHARGED (Stripe interval "year"). Auto-renews
  yearly until cancelled; see docs/features/annual-billing.md for the
  disclosure, consent, notices and cancel path the auto-renewal laws need.

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
ANNUAL = "annual"
PAY_PER_MEETING = "pay_per_meeting"
BILLING_MODELS = (MONTHLY, ANNUAL, PAY_PER_MEETING)
# The models that are a Stripe subscription with a trial, a period end and
# cancel-at-period-end. Pay per meeting is a saved card, charged per meeting.
SUBSCRIPTION_MODELS = (MONTHLY, ANNUAL)

# FOUNDER PRICING DECISION TO CONFIRM (docs/features/annual-billing.md):
# an annual plan costs this many months of the monthly price -- 10 = "two
# months free". THE ONLY PLACE the annual price is defined; the pricing page,
# checkout, Stripe price_data and the renewal notices all read it.
ANNUAL_MONTHS_CHARGED = 10
# Stub mode's period for an annual plan (Stripe decides the real one).
ANNUAL_PERIOD_DAYS = 365
MONTHLY_PERIOD_DAYS = 30

# Auto-renewal notices (needs founder/legal confirmation -- see the spec):
#   RENEWAL_NOTICE_DAYS  annual renewal reminder, inside California ARL's
#                        15-45 days (terms of 1 year+) and NY GOL 5-903's
#                        15-30 days
#   NOTICE_LATE_DAYS     a renewal notice sent with fewer days left than this
#                        is outside the NY window: still sent, logged as late
#   TRIAL_NOTICE_DAYS    trial-ending notice, inside California ARL's 3-21
#                        days for trials longer than 31 days
#   LONG_TRIAL_DAYS      a trial longer than this gets the trial notice even
#                        on a monthly plan (only a pilot-extended trial is)
RENEWAL_NOTICE_DAYS = 30
NOTICE_LATE_DAYS = 15
TRIAL_NOTICE_DAYS = 7
LONG_TRIAL_DAYS = 31

# The version of the auto-renewal disclosure the pricing page shows next to
# the consent checkbox (frontend/src/lib/pricing.ts RENEWAL_DISCLOSURE_VERSION
# -- a test pins that the two are equal). A checkout must echo it back; the
# consent stored on the subscription records which wording was agreed to.
# Bump BOTH when the disclosure wording changes.
DISCLOSURE_VERSION = "2026-10-11.2"

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


def annual_tier(tier_id: str | None) -> dict[str, Any] | None:
    """A monthly tier that can be bought yearly (it has a monthly price)."""
    tier = monthly_tier(tier_id)
    return tier if tier is not None and int(tier["price_cents"]) > 0 else None


def annual_price_cents(tier_id: str | None) -> int | None:
    tier = annual_tier(tier_id)
    return int(tier["price_cents"]) * ANNUAL_MONTHS_CHARGED if tier else None


def price_cents(billing_model: str, tier_id: str | None) -> int | None:
    """What one billing period of a subscription costs, or None."""
    if billing_model == ANNUAL:
        return annual_price_cents(tier_id)
    if billing_model == MONTHLY:
        tier = monthly_tier(tier_id)
        return int(tier["price_cents"]) if tier else None
    return None


def interval_for(billing_model: str) -> str:
    """The Stripe recurring interval of a subscription model."""
    return "year" if billing_model == ANNUAL else "month"


def annual_tiers() -> list[dict[str, Any]]:
    out = []
    for tier in MONTHLY_TIERS:
        if annual_tier(tier["id"]) is None:
            continue
        annual = annual_price_cents(tier["id"])
        out.append({
            "id": tier["id"], "name": tier["name"], "tagline": tier["tagline"],
            "plan": tier["plan"], "monthly_price_cents": int(tier["price_cents"]),
            "annual_price_cents": annual,
            # Rounded half-up to the cent, for display only: Stripe charges
            # annual_price_cents once a year.
            "monthly_equivalent_cents": (annual * 2 + 12) // 24,
            "savings_cents": int(tier["price_cents"]) * 12 - annual,
            "months_charged": ANNUAL_MONTHS_CHARGED,
        })
    return out


def plan_for(billing_model: str, tier_id: str | None) -> str | None:
    """The app/core/plans.py key a paid selection grants, or None if invalid.
    Annual grants exactly what the same monthly tier grants."""
    if billing_model == PAY_PER_MEETING:
        return PAY_PER_MEETING_PLAN["plan"]
    if billing_model == MONTHLY:
        tier = monthly_tier(tier_id)
        return tier["plan"] if tier else None
    if billing_model == ANNUAL:
        tier = annual_tier(tier_id)
        return tier["plan"] if tier else None
    return None


def meeting_price_cents() -> int:
    return int(PAY_PER_MEETING_PLAN["price_per_meeting_cents"])


def catalog(*, annual_enabled: bool = False) -> dict[str, Any]:
    """The full price list with each tier's enforced entitlements attached.
    The `annual` block is present only when annual billing is offered."""
    from app.core.plans import PLANS  # noqa: PLC0415

    def _limits(plan_key: str) -> dict[str, Any]:
        plan = PLANS[plan_key]
        return {key: plan[key] for key in (
            "max_strategies", "max_leads_per_strategy", "max_sequence_steps",
            "channels", "ab_testing", "multi_variate", "playbook_access",
            "website_builder", "max_site_pages", "analytics_history_days")}

    out = {
        "currency": CURRENCY,
        "trial_days": TRIAL_DAYS,
        "annual_available": bool(annual_enabled),
        "renewal_disclosure_version": DISCLOSURE_VERSION,
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
    if annual_enabled:
        out["annual"] = {
            "id": ANNUAL,
            "name": "Annual subscription",
            "months_charged": ANNUAL_MONTHS_CHARGED,
            "term_months": 12,
            "renewal_notice_days": RENEWAL_NOTICE_DAYS,
            "tiers": [{**tier, "trial_days": TRIAL_DAYS, "limits": _limits(tier["plan"])}
                      for tier in annual_tiers()],
        }
    return out

"""Billing — monthly subscriptions and pay-per-meeting (Section E).

    start_checkout()        choose a plan: a Stripe Checkout URL, or (stub
                            mode) the plan activated locally
    handle_webhook_event()  Stripe is the source of truth; its events move
                            the subscription row and users.plan
    charge_due_meetings()   the sweep that charges pay-per-meeting usage once
                            its cancellation grace period has passed
    dispute_meeting() / resolve_dispute() / cancel()

METERING. A booked meeting is an Outcome(event=BOOKED). Those are written from
more than one place (the Calendly webhook, the native calendar's booking task)
and more will come, so -- exactly like app/services/crm_events.py -- a SESSION
LISTENER sees every one of them: `before_flush` hands each new BOOKED outcome
to usage_meter.record_meeting_usage, which adds a BillableMeeting row to the
SAME flush when the lead's owner pays per meeting. The booking and its billing
record commit together or not at all. The listener never raises: a metering
failure must not turn a booking into an error (it is logged instead).

STUB MODE. No STRIPE_SECRET_KEY -> checkout activates the plan locally
(is_stub=True) and the sweep marks meetings charged with is_stub=True. Every
stub path logs STUB_TODO so it is greppable. See BUILD_BLOCKERS.md.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core import billing_catalog as catalog
from app.db.models import (
    BillableMeeting,
    BillingSubscription,
    Lead,
    LeadStatus,
    Outcome,
    PlanTier,
    User,
)
from app.integrations import stripe_billing as stripe

logger = logging.getLogger(__name__)

STUB_TODO = "TODO: connect live Stripe keys"

# Statuses under which a subscription grants its plan. past_due keeps access
# while Stripe retries the card (its dunning decides when to cancel).
GRANTING = ("trialing", "active", "past_due")
_STRIPE_STATUS = {
    "trialing": "trialing", "active": "active", "past_due": "past_due",
    "unpaid": "past_due", "paused": "past_due", "canceled": "canceled",
    "incomplete": "incomplete", "incomplete_expired": "canceled",
}
# A meeting is still chargeable at the end of its grace period when the lead
# got at least as far as a booked meeting. Every later stage means the meeting
# happened (or was never cancelled); REPLIED is what a Calendly cancellation
# writes, so it -- and anything before a booking -- is waived.
_BOOKED_OR_LATER = {LeadStatus.MEETING_BOOKED, LeadStatus.PROPOSAL_SENT,
                    LeadStatus.OPPORTUNITY, LeadStatus.CLOSED_WON,
                    LeadStatus.CLOSED_LOST, LeadStatus.DISQUALIFIED}


class BillingError(ValueError):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _ts(unix) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(unix), tz=timezone.utc) if unix else None
    except (TypeError, ValueError):
        return None


def get_subscription(db: Session, user_id) -> BillingSubscription | None:
    return db.execute(
        select(BillingSubscription).where(BillingSubscription.user_id == user_id)
    ).scalar_one_or_none()


def _sync_plan(db: Session, sub: BillingSubscription) -> None:
    """users.plan follows the subscription: its tier while it grants, free after."""
    user = db.get(User, sub.user_id)
    if user is None:
        return
    plan_key = catalog.plan_for(sub.billing_model, sub.tier) if sub.status in GRANTING else None
    user.plan = PlanTier(plan_key) if plan_key else PlanTier.FREE


# --------------------------------------------------------------------------
# Checkout
# --------------------------------------------------------------------------


def _validate(billing_model: str, tier: str | None) -> tuple[str, str]:
    model = (billing_model or "").strip().lower()
    if model == catalog.PAY_PER_MEETING:
        return model, catalog.PAY_PER_MEETING
    if model == catalog.MONTHLY:
        chosen = catalog.monthly_tier(tier)
        if chosen is None:
            raise BillingError("Choose one of the monthly tiers: "
                               + ", ".join(t["id"] for t in catalog.MONTHLY_TIERS))
        return model, chosen["id"]
    raise BillingError("billing_model must be 'monthly' or 'pay_per_meeting'")


def start_checkout(db: Session, user: User, *, billing_model: str, tier: str | None = None,
                   now: datetime | None = None) -> dict:
    now = now or _now()
    model, tier_id = _validate(billing_model, tier)
    sub = get_subscription(db, user.id)
    if (sub is not None and sub.status in GRANTING and sub.billing_model == model
            and sub.tier == tier_id and not sub.cancel_at_period_end):
        raise BillingError("You are already on this plan.", status_code=409)
    had_trial = bool(sub is not None and sub.trial_ends_at is not None)

    if settings.billing_stub_mode:
        logger.warning("billing stub mode (%s): activating %s/%s for user %s without Stripe",
                       STUB_TODO, model, tier_id, user.id)
        if sub is None:
            sub = BillingSubscription(user_id=user.id, billing_model=model, tier=tier_id)
            db.add(sub)
        sub.billing_model, sub.tier, sub.is_stub = model, tier_id, True
        sub.cancel_at_period_end, sub.canceled_at = False, None
        if model == catalog.MONTHLY and not had_trial:
            sub.status = "trialing"
            sub.trial_ends_at = now + timedelta(days=catalog.TRIAL_DAYS)
            sub.current_period_end = sub.trial_ends_at
        elif model == catalog.MONTHLY:
            sub.status, sub.current_period_end = "active", now + timedelta(days=30)
        else:
            sub.status, sub.current_period_end = "active", None
        db.flush()
        _sync_plan(db, sub)
        db.commit()
        return {"mode": "stub", "checkout_url": None, "subscription": subscription_out(sub)}

    frontend = settings.frontend_url.rstrip("/")
    success_url = f"{frontend}/settings?billing=success"
    cancel_url = f"{frontend}/pricing?checkout=cancelled"
    try:
        customer_id = (sub.stripe_customer_id if sub is not None else None) or \
            stripe.create_customer(email=user.email, user_id=str(user.id))["id"]
        if model == catalog.MONTHLY:
            session = stripe.create_subscription_checkout(
                customer_id=customer_id, user_id=str(user.id),
                tier=catalog.monthly_tier(tier_id),
                trial_days=0 if had_trial else catalog.TRIAL_DAYS,
                success_url=success_url, cancel_url=cancel_url,
                price_id=getattr(settings, f"stripe_price_{tier_id}", "") or None)
        else:
            session = stripe.create_setup_checkout(
                customer_id=customer_id, user_id=str(user.id),
                success_url=success_url, cancel_url=cancel_url)
    except stripe.StripeError as exc:
        logger.error("stripe checkout for user %s failed: %s", user.id, exc)
        raise BillingError("Payments are unavailable right now. Please try again shortly.",
                           status_code=502) from exc

    if sub is None:
        # A brand-new row starts `incomplete`; the webhook activates it. An
        # EXISTING row keeps its current plan until the webhook confirms the
        # switch -- abandoning checkout must not downgrade anyone.
        sub = BillingSubscription(user_id=user.id, billing_model=model, tier=tier_id,
                                  status="incomplete")
        db.add(sub)
    sub.stripe_customer_id = customer_id
    sub.stripe_checkout_session_id = session.get("id")
    sub.is_stub = False
    db.commit()
    return {"mode": "stripe", "checkout_url": session.get("url"),
            "subscription": subscription_out(sub)}


def cancel(db: Session, user: User, now: datetime | None = None) -> dict:
    """Monthly: cancel at period end (access continues until then). Pay per
    meeting: stops immediately; meetings already booked are still billed."""
    now = now or _now()
    sub = get_subscription(db, user.id)
    if sub is None or sub.status not in GRANTING or sub.cancel_at_period_end:
        raise BillingError("There is no active plan to cancel.", status_code=409)
    live = not (settings.billing_stub_mode or sub.is_stub)
    if sub.billing_model == catalog.MONTHLY and live and sub.stripe_subscription_id:
        try:
            stripe.cancel_subscription_at_period_end(sub.stripe_subscription_id)
        except stripe.StripeError as exc:
            raise BillingError("Could not reach the payment provider. Try again.",
                               status_code=502) from exc
        sub.cancel_at_period_end = True
    else:
        if not live:
            logger.warning("billing stub mode (%s): cancelling %s locally", STUB_TODO, sub.id)
        sub.status, sub.canceled_at = "canceled", now
        _sync_plan(db, sub)
    db.commit()
    return subscription_out(sub)


# --------------------------------------------------------------------------
# Webhooks
# --------------------------------------------------------------------------


def handle_webhook_event(db: Session, payload: dict) -> str:
    kind = payload.get("type") or ""
    obj = (payload.get("data") or {}).get("object") or {}
    handlers = {
        "checkout.session.completed": _on_checkout_completed,
        "customer.subscription.created": _on_subscription_changed,
        "customer.subscription.updated": _on_subscription_changed,
        "customer.subscription.deleted": _on_subscription_deleted,
        "invoice.paid": lambda d, o: _on_invoice(d, o, paid=True),
        "invoice.payment_failed": lambda d, o: _on_invoice(d, o, paid=False),
    }
    handler = handlers.get(kind)
    if handler is None:
        return "ignored"
    return handler(db, obj)


def _user_from_metadata(db: Session, obj: dict) -> User | None:
    raw = (obj.get("metadata") or {}).get("user_id") or obj.get("client_reference_id")
    try:
        return db.get(User, uuid.UUID(str(raw))) if raw else None
    except ValueError:
        return None


def _on_checkout_completed(db: Session, obj: dict) -> str:
    user = _user_from_metadata(db, obj)
    if user is None:
        return "no_user"
    meta = obj.get("metadata") or {}
    try:
        model, tier_id = _validate(meta.get("billing_model"), meta.get("tier"))
    except BillingError:
        return "bad_metadata"
    sub = get_subscription(db, user.id)
    if sub is None:
        sub = BillingSubscription(user_id=user.id, billing_model=model, tier=tier_id)
        db.add(sub)
    previous = sub.stripe_subscription_id
    new_subscription = obj.get("subscription") if obj.get("mode") == "subscription" else None
    if previous and previous != new_subscription:
        # The account switched plans: end the subscription being replaced so
        # nobody is billed twice.
        try:
            stripe.cancel_subscription_now(previous)
        except stripe.StripeError as exc:
            logger.error("could not cancel replaced subscription %s: %s", previous, exc)
    sub.billing_model, sub.tier, sub.is_stub = model, tier_id, False
    sub.stripe_customer_id = obj.get("customer") or sub.stripe_customer_id
    sub.stripe_subscription_id = new_subscription
    sub.cancel_at_period_end, sub.canceled_at = False, None
    # The subscription.* events refine this (trial end, period end); until they
    # land, a monthly checkout is at least trialing and a card saved for
    # pay-per-meeting is active.
    sub.status = "trialing" if model == catalog.MONTHLY else "active"
    db.flush()
    _sync_plan(db, sub)
    db.commit()
    return "activated"


def _on_subscription_changed(db: Session, obj: dict) -> str:
    sub = db.execute(select(BillingSubscription).where(
        BillingSubscription.stripe_subscription_id == obj.get("id"))).scalar_one_or_none()
    if sub is None:
        user = _user_from_metadata(db, obj)
        sub = get_subscription(db, user.id) if user else None
        if sub is None or (sub.stripe_subscription_id not in (None, obj.get("id"))):
            return "ignored_unknown"
        sub.stripe_subscription_id = obj.get("id")
    tier = (obj.get("metadata") or {}).get("tier")
    if catalog.monthly_tier(tier):
        sub.billing_model, sub.tier = catalog.MONTHLY, tier
    sub.status = _STRIPE_STATUS.get(str(obj.get("status")), sub.status)
    sub.current_period_end = _ts(obj.get("current_period_end")) or sub.current_period_end
    sub.trial_ends_at = _ts(obj.get("trial_end")) or sub.trial_ends_at
    sub.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
    _sync_plan(db, sub)
    db.commit()
    return f"status_{sub.status}"


def _on_subscription_deleted(db: Session, obj: dict) -> str:
    sub = db.execute(select(BillingSubscription).where(
        BillingSubscription.stripe_subscription_id == obj.get("id"))).scalar_one_or_none()
    if sub is None:
        return "ignored_unknown"   # e.g. a subscription we replaced and already moved off
    sub.status, sub.canceled_at = "canceled", _now()
    _sync_plan(db, sub)
    db.commit()
    return "canceled"


def _on_invoice(db: Session, obj: dict, *, paid: bool) -> str:
    meeting_id = (obj.get("metadata") or {}).get("billable_meeting_id")
    if meeting_id:
        try:
            meeting = db.get(BillableMeeting, uuid.UUID(str(meeting_id)))
        except ValueError:
            meeting = None
        if meeting is None:
            return "ignored_unknown"
        if paid:
            meeting.status = "charged"
            meeting.charged_at = meeting.charged_at or _now()
            meeting.failure_reason = None
        else:
            meeting.status = "failed"
            meeting.failure_reason = "card declined (invoice.payment_failed)"
        db.commit()
        return "meeting_paid" if paid else "meeting_failed"

    sub = db.execute(select(BillingSubscription).where(
        BillingSubscription.stripe_subscription_id == obj.get("subscription"))).scalar_one_or_none()
    if sub is None:
        return "ignored_unknown"
    if not paid:
        sub.status = "past_due"
    elif sub.status == "past_due":
        sub.status = "active"
    _sync_plan(db, sub)
    db.commit()
    return "subscription_paid" if paid else "subscription_past_due"


# --------------------------------------------------------------------------
# Pay-per-meeting: metering listener, charging sweep, disputes
# --------------------------------------------------------------------------


@event.listens_for(Session, "before_flush")
def _meter_booked_meetings(session: Session, _flush_context, _instances) -> None:
    try:
        booked = [obj for obj in session.new
                  if isinstance(obj, Outcome) and obj.lead_id is not None
                  and getattr(obj.event, "value", obj.event) == "booked"]
        if not booked:
            return
        from app.services import usage_meter  # noqa: PLC0415

        with session.no_autoflush:
            for outcome in booked:
                usage_meter.record_meeting_usage(session, outcome)
    except Exception:  # noqa: BLE001 -- metering never breaks a booking
        logger.exception("billing: could not meter a booked meeting")


def install() -> None:
    """No-op marker: importing this module registers the metering listener
    (see app/services/crm_events.py::install for why the call exists)."""
    return None


def charge_due_meetings(db: Session, now: datetime | None = None, limit: int = 500) -> dict:
    now = now or _now()
    rows = db.execute(
        select(BillableMeeting)
        .where(BillableMeeting.status == "pending", BillableMeeting.charge_after <= now)
        .order_by(BillableMeeting.charge_after).limit(limit)
    ).scalars().all()
    counts: dict[str, int] = {}
    for meeting in rows:
        try:
            result = _charge_one(db, meeting, now)
        except Exception:  # noqa: BLE001 -- one bad row must not end the sweep
            logger.exception("billing: charging meeting %s failed", meeting.id)
            db.rollback()
            result = "error"
        counts[result] = counts.get(result, 0) + 1
    return {"processed": len(rows), **counts}


def _charge_one(db: Session, meeting: BillableMeeting, now: datetime) -> str:
    lead = db.get(Lead, meeting.lead_id) if meeting.lead_id else None
    if lead is None or lead.status not in _BOOKED_OR_LATER:
        meeting.status = "waived"
        meeting.resolution_note = "Meeting was no longer booked when the grace period ended."
        db.commit()
        return "waived"

    if settings.billing_stub_mode or meeting.is_stub:
        logger.warning("billing stub mode (%s): meeting %s marked charged without Stripe",
                       STUB_TODO, meeting.id)
        meeting.status, meeting.is_stub, meeting.charged_at = "charged", True, now
        db.commit()
        return "charged_stub"

    sub = get_subscription(db, meeting.user_id)
    if sub is None or not sub.stripe_customer_id:
        meeting.status = "failed"
        meeting.failure_reason = "No saved payment method for this account."
        db.commit()
        return "failed"
    try:
        result = stripe.charge_meeting(
            customer_id=sub.stripe_customer_id, amount_cents=int(meeting.amount_cents),
            currency=meeting.currency,
            description=f"LeadPilot: meeting booked {_aware(meeting.occurred_at):%Y-%m-%d}",
            meeting_id=str(meeting.id))
    except stripe.StripeError as exc:
        meeting.status, meeting.failure_reason = "failed", str(exc)[:1000]
        db.commit()
        return "failed"
    meeting.stripe_invoice_id = result.get("invoice_id")
    meeting.stripe_invoice_item_id = result.get("invoice_item_id")
    meeting.status, meeting.charged_at = "charged", now
    db.commit()
    return "charged"


def owned_meeting(db: Session, user: User, meeting_id) -> BillableMeeting:
    try:
        meeting = db.get(BillableMeeting, uuid.UUID(str(meeting_id)))
    except ValueError:
        meeting = None
    if meeting is None or meeting.user_id != user.id:
        raise BillingError("meeting not found", status_code=404)
    return meeting


def dispute_meeting(db: Session, user: User, meeting_id, reason: str,
                    now: datetime | None = None) -> BillableMeeting:
    now = now or _now()
    meeting = owned_meeting(db, user, meeting_id)
    if meeting.status != "pending" or _aware(meeting.charge_after) <= now:
        raise BillingError("Only a meeting still inside its grace period can be disputed. "
                           "For a charged meeting, contact support.", status_code=409)
    meeting.status = "disputed"
    meeting.resolution_note = (reason or "").strip()[:500] or None
    db.commit()
    return meeting


def resolve_dispute(db: Session, meeting: BillableMeeting, *, decision: str, note: str = "",
                    now: datetime | None = None) -> BillableMeeting:
    now = now or _now()
    if meeting.status != "disputed":
        raise BillingError("This meeting is not disputed.", status_code=409)
    if decision == "waive":
        meeting.status = "waived"
    elif decision == "charge":
        meeting.status, meeting.charge_after = "pending", now   # the sweep charges it
    else:
        raise BillingError("decision must be 'waive' or 'charge'")
    meeting.resolution_note = (note or "").strip()[:500] or meeting.resolution_note
    db.commit()
    return meeting


# --------------------------------------------------------------------------
# Read models
# --------------------------------------------------------------------------


def _iso(value: datetime | None) -> str | None:
    return _aware(value).isoformat() if value else None


def subscription_out(sub: BillingSubscription | None) -> dict | None:
    if sub is None:
        return None
    return {
        "billing_model": sub.billing_model, "tier": sub.tier, "status": sub.status,
        "grants_plan": sub.status in GRANTING,
        "trial_ends_at": _iso(sub.trial_ends_at),
        "current_period_end": _iso(sub.current_period_end),
        "cancel_at_period_end": bool(sub.cancel_at_period_end),
        "canceled_at": _iso(sub.canceled_at), "is_stub": bool(sub.is_stub),
    }


def meeting_out(meeting: BillableMeeting) -> dict:
    return {
        "id": str(meeting.id), "lead_id": str(meeting.lead_id) if meeting.lead_id else None,
        "strategy_id": str(meeting.strategy_id) if meeting.strategy_id else None,
        "source": meeting.source, "amount_cents": int(meeting.amount_cents),
        "currency": meeting.currency, "status": meeting.status,
        "occurred_at": _iso(meeting.occurred_at), "charge_after": _iso(meeting.charge_after),
        "charged_at": _iso(meeting.charged_at), "is_stub": bool(meeting.is_stub),
        "failure_reason": meeting.failure_reason, "resolution_note": meeting.resolution_note,
    }


def usage_summary(db: Session, user: User, now: datetime | None = None) -> dict:
    now = now or _now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = db.execute(
        select(BillableMeeting.status, func.count(BillableMeeting.id),
               func.coalesce(func.sum(BillableMeeting.amount_cents), 0))
        .where(BillableMeeting.user_id == user.id, BillableMeeting.occurred_at >= month_start)
        .group_by(BillableMeeting.status)
    ).all()
    by_status = {status: (int(count), int(total)) for status, count, total in rows}
    billable = ("pending", "charged")
    return {
        "period_start": month_start.isoformat(),
        "meetings_booked": sum(c for s, (c, _) in by_status.items() if s != "waived"),
        "amount_cents": sum(t for s, (_, t) in by_status.items() if s in billable),
        "by_status": {s: c for s, (c, _) in by_status.items()},
        "price_per_meeting_cents": catalog.meeting_price_cents(),
        "currency": catalog.CURRENCY,
    }


def plan_access(db: Session, user: User) -> dict:
    """Does this account have a plan that lets it use the product?

    Returned on every sign-in, refresh and /auth/me, computed from the
    database each time rather than cached on the token. The frontend sends a
    user without one to /pricing straight after an explicit sign-in only.

    True when any of:
      * its own subscription is in a GRANTING status (trialing counts: the
        trial IS a purchased plan -- a card or checkout was completed);
      * users.plan is not free -- _sync_plan keeps it in step with the
        subscription, and it also covers plans set before billing existed
        (legacy pro/enterprise rows) or granted by an operator;
      * it is an operator (is_admin), who must reach the admin panel;
      * it is a member of someone else's workspace whose OWNER has a plan --
        a member works on the owner's account and is never asked to buy one.
    """
    sub = get_subscription(db, user.id)
    status = sub.status if sub is not None else None
    plan = str(getattr(user.plan, "value", user.plan) or "free")
    active = status in GRANTING or plan != PlanTier.FREE.value or bool(user.is_admin)
    if not active:
        from app.db.models import Workspace, WorkspaceMember  # noqa: PLC0415

        owners = db.execute(
            select(User.plan, BillingSubscription.status)
            .select_from(WorkspaceMember)
            .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
            .join(User, User.id == Workspace.owner_user_id)
            .outerjoin(BillingSubscription, BillingSubscription.user_id == User.id)
            .where(WorkspaceMember.user_id == user.id, Workspace.owner_user_id != user.id)
        ).all()
        active = any(
            owner_status in GRANTING
            or str(getattr(owner_plan, "value", owner_plan) or "free") != PlanTier.FREE.value
            for owner_plan, owner_status in owners
        )
    return {"has_active_plan": bool(active), "subscription_status": status}


def overview(db: Session, user: User) -> dict:
    return {
        "plan": getattr(user.plan, "value", user.plan) or "free",
        "subscription": subscription_out(get_subscription(db, user.id)),
        "usage": usage_summary(db, user),
        "stub_mode": settings.billing_stub_mode,
    }

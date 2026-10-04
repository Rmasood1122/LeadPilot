"""Metered model spend, attributed to the campaign that caused it.

WHY A CONTEXT SCOPE
Revenue analytics needs "what did this campaign cost to run", and most of that
is Claude tokens. The model clients are called from thirty places, none of
which know (or should know) which campaign they are working for. So the
clients only `note()` what each call used, and the few places that DO know
the campaign -- the pipeline run, one send, a scoring batch, a meeting brief
-- open a `scope()`. When the scope closes, its notes are priced and written
as api_usage rows in one commit.

    with usage_meter.scope(session, strategy_id=s.id, user_id=owner,
                           purpose="pipeline"):
        ...   # every Claude/OpenAI call in here is attributed to s

A call outside any scope is not recorded. That is deliberate: an unattributed
row is noise in a per-campaign report, and the scopes cover the paths where
the money is actually spent.

Nested scopes collapse into the OUTERMOST one (a send that scores a lead is
one send), so no call is ever counted twice.

Prices are the admin's estimates (system settings, USD per million tokens),
read when the scope closes. USD per MILLION tokens equals micro-dollars per
token, which is why cost_micros is a plain multiply.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.exceptions import ClientHunterError

logger = logging.getLogger(__name__)

# F-AI-01. Only these purposes count toward a strategy's BUDGET: the budget is
# "what it costs to RUN the pipeline", so outreach copy written later for the
# same strategy (purpose "send", scoring, briefs...) must not eat it.
BUDGETED_PURPOSES = ("pipeline", "verification")

# A prompt's size in tokens is not known before the call. English averages
# about 4 characters per token, so dividing by 3 OVER-estimates the input and
# makes the gate stop a little early rather than a little late.
_CHARS_PER_TOKEN_CONSERVATIVE = 3


class BudgetExceededError(ClientHunterError):
    """The next model call could take a strategy past its dollar budget.

    Raised BEFORE the call is made, so nothing is spent on it. Never retried
    (anthropic_client.is_permanent_error) and never swallowed: the worker tasks
    turn it into StrategyStatus.BUDGET_EXHAUSTED, which is resumable.
    """

    def __init__(self, message: str, *, budget_micros: int, spent_micros: int) -> None:
        super().__init__(message)
        self.budget_micros = budget_micros
        self.spent_micros = spent_micros

_PRICE_KEYS = {
    "anthropic": ("claude_input_cost_per_mtok", "claude_output_cost_per_mtok"),
    "openai": ("openai_input_cost_per_mtok", "openai_output_cost_per_mtok"),
}


@dataclass
class _Scope:
    strategy_id: uuid.UUID | None
    user_id: uuid.UUID | None
    purpose: str
    notes: list[tuple[str, str, int, int]] = field(default_factory=list)
    # F-AI-01 -- all None/0 unless the scope was opened with a budget.
    budget_micros: int | None = None
    prior_micros: int = 0      # already recorded for this strategy before the scope opened
    spent_micros: int = 0      # spent inside this scope so far (flushed or not)
    prices: dict = field(default_factory=dict)   # provider -> (micros/token in, out)


_current: ContextVar[_Scope | None] = ContextVar("usage_scope", default=None)


def _uuid(value) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def note(provider: str, model: str, input_tokens: int, output_tokens: int) -> None:
    """Record one model call against the active scope, if any. Never raises."""
    active = _current.get()
    if active is None:
        return
    try:
        tin, tout = int(input_tokens or 0), int(output_tokens or 0)
        active.notes.append((provider, model or "", tin, tout))
        if active.budget_micros is not None:
            price_in, price_out = active.prices.get(provider, (0.0, 0.0))
            active.spent_micros += int(round(tin * price_in + tout * price_out))
    except (TypeError, ValueError):
        pass


def price_micros(session: Session, provider: str, input_tokens: int,
                 output_tokens: int) -> int:
    from app.services import system_settings  # noqa: PLC0415

    keys = _PRICE_KEYS.get(provider)
    if keys is None:
        return 0
    price_in = system_settings.get(session, keys[0])
    price_out = system_settings.get(session, keys[1])
    return int(round(input_tokens * price_in + output_tokens * price_out))


def _flush(session: Session, active: _Scope) -> int:
    from app.db.models import ApiUsage  # noqa: PLC0415

    if not active.notes:
        return 0
    grouped: dict[tuple[str, str], list[int]] = {}
    for provider, model, tin, tout in active.notes:
        row = grouped.setdefault((provider, model), [0, 0, 0])
        row[0] += 1
        row[1] += tin
        row[2] += tout
    for (provider, model), (calls, tin, tout) in grouped.items():
        session.add(ApiUsage(
            user_id=active.user_id, strategy_id=active.strategy_id,
            provider=provider, model=model[:80], purpose=active.purpose[:40],
            calls=calls, input_tokens=tin, output_tokens=tout,
            cost_micros=price_micros(session, provider, tin, tout),
        ))
    session.commit()
    return len(grouped)


def spent_micros(session: Session, strategy_id) -> int:
    """What this strategy's pipeline + verification have cost so far, recorded.

    Counts only BUDGETED_PURPOSES, and only what has been flushed to api_usage
    (see flush_active). Filtered by the strategy's own id, which callers get
    from a strategy row they have already ownership-checked.
    """
    from sqlalchemy import func, select  # noqa: PLC0415

    from app.db.models import ApiUsage  # noqa: PLC0415

    sid = _uuid(strategy_id)
    if sid is None:
        return 0
    return int(session.execute(
        select(func.coalesce(func.sum(ApiUsage.cost_micros), 0)).where(
            ApiUsage.strategy_id == sid, ApiUsage.purpose.in_(BUDGETED_PURPOSES)
        )
    ).scalar_one() or 0)


def _price_table(session: Session) -> dict:
    from app.services import system_settings  # noqa: PLC0415

    return {
        provider: (float(system_settings.get(session, keys[0])),
                   float(system_settings.get(session, keys[1])))
        for provider, keys in _PRICE_KEYS.items()
    }


def price_table(session: Session) -> dict:
    """Public name for the admin-set model prices: {provider: (in, out)} in USD
    per Mtok == micros per token."""
    return _price_table(session)


def check_budget(*, input_chars: int, max_output_tokens: int,
                 provider: str = "anthropic") -> None:
    """Refuse a model call that could take the active scope past its budget.

    A no-op outside a scope and in a scope with no budget. The call is priced
    at its WORST CASE -- the whole prompt as input, and the model using every
    one of `max_output_tokens` -- so a call that passes this check cannot, in
    itself, cross the cap. The price is that the run may stop up to one call's
    worth early; it is never allowed to run past.
    """
    active = _current.get()
    if active is None or active.budget_micros is None:
        return
    price_in, price_out = active.prices.get(provider, (0.0, 0.0))
    reserve = int(round(
        (max(int(input_chars), 0) / _CHARS_PER_TOKEN_CONSERVATIVE) * price_in
        + max(int(max_output_tokens), 0) * price_out
    ))
    spent = active.prior_micros + active.spent_micros
    if spent + reserve > active.budget_micros:
        raise BudgetExceededError(
            f"strategy budget of ${active.budget_micros / 1_000_000:.2f} reached "
            f"(${spent / 1_000_000:.2f} spent; the next model call could cost up to "
            f"${reserve / 1_000_000:.2f} more). Nothing was spent on that call. "
            "Raise the budget and resume to continue.",
            budget_micros=active.budget_micros, spent_micros=spent,
        )


def flush_active(session: Session) -> None:
    """Write the active scope's pending notes to api_usage NOW and clear them.

    A scope normally records its spend only when it closes. A pipeline run lasts
    many minutes, and a worker killed partway (a deploy, a free-tier spin-down)
    never reaches the close, so the spend of every completed step was lost and
    the budget would restart from zero. Callers that already commit after each
    unit of work call this at the same point. Never raises.
    """
    active = _current.get()
    if active is None or not active.notes:
        return
    try:
        _flush(session, active)
        active.notes.clear()
    except Exception:
        logger.exception("usage_meter: could not flush %d model calls", len(active.notes))
        try:
            session.rollback()
        except Exception:
            pass


@contextmanager
def scope(session: Session, *, strategy_id=None, user_id=None, purpose: str = "other",
          budget_micros: int | None = None):
    """Attribute every model call inside the block. See the module docstring.

    `budget_micros` (F-AI-01) turns on spend tracking for the scope and arms
    check_budget(). Only the OUTERMOST scope decides; a nested scope joins it.
    """
    if _current.get() is not None:
        yield _current.get()
        return
    active = _Scope(strategy_id=_uuid(strategy_id), user_id=_uuid(user_id), purpose=purpose)
    if budget_micros is not None:
        active.budget_micros = int(budget_micros)
        active.prices = _price_table(session)
        active.prior_micros = spent_micros(session, active.strategy_id)
    token = _current.set(active)
    failed = False
    try:
        yield active
    except BaseException:
        failed = True
        raise
    finally:
        _current.reset(token)
        if active.notes:
            try:
                if failed:
                    # The tokens were spent whether or not the work succeeded.
                    # The caller is about to roll back anyway; do it first so
                    # the usage rows are not written into a broken transaction.
                    session.rollback()
                _flush(session, active)
            except Exception:
                logger.exception("usage_meter: could not record %d model calls",
                                 len(active.notes))
                try:
                    session.rollback()
                except Exception:
                    pass


def record_meeting_usage(session: Session, outcome, *, now=None):
    """Meter one booked meeting for a pay-per-meeting account (Section E).

    Called from app/services/billing.py's before_flush listener for every new
    Outcome(event=BOOKED), inside that flush and under no_autoflush. Adds (does
    not commit) a BillableMeeting when the lead's owner currently pays per
    meeting; otherwise does nothing. Returns the row or None.

    Once per prospect: a lead already metered for this account -- in the
    database or earlier in this same flush -- is not metered again. The UNIQUE
    (user_id, dedupe_key) constraint backs that up at the schema level.

    Model spend above is metered in micro-dollars against a scope; a meeting is
    metered in whole cents against the ACCOUNT, because it is what the customer
    is invoiced for rather than what the platform spent.
    """
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    from sqlalchemy import select  # noqa: PLC0415

    from app.core import billing_catalog  # noqa: PLC0415
    from app.db.models import (  # noqa: PLC0415
        BillableMeeting, BillingSubscription, Lead, Product, Strategy,
    )

    if outcome is None or outcome.lead_id is None:
        return None
    row = session.execute(
        select(Product.user_id, Lead.strategy_id).select_from(Lead)
        .join(Strategy, Strategy.id == Lead.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .where(Lead.id == outcome.lead_id)
    ).first()
    if row is None:
        return None
    owner_id, strategy_id = row
    sub = session.execute(
        select(BillingSubscription).where(BillingSubscription.user_id == owner_id)
    ).scalar_one_or_none()
    if (sub is None or sub.billing_model != billing_catalog.PAY_PER_MEETING
            or sub.status not in ("trialing", "active", "past_due")):
        return None

    key = str(outcome.lead_id)
    if session.execute(select(BillableMeeting.id).where(
            BillableMeeting.user_id == owner_id,
            BillableMeeting.dedupe_key == key)).first() is not None:
        return None
    if any(isinstance(obj, BillableMeeting) and obj.user_id == owner_id
           and obj.dedupe_key == key for obj in session.new):
        return None

    if outcome.id is None:
        outcome.id = uuid.uuid4()  # the column default only fires at INSERT
    now = now or datetime.now(timezone.utc)
    plan = billing_catalog.PAY_PER_MEETING_PLAN
    meeting = BillableMeeting(
        user_id=owner_id, lead_id=outcome.lead_id, strategy_id=strategy_id,
        outcome_id=outcome.id, dedupe_key=key,
        source=str(outcome.channel or "booking")[:20],
        amount_cents=billing_catalog.meeting_price_cents(),
        currency=billing_catalog.CURRENCY, status="pending", occurred_at=now,
        charge_after=now + timedelta(hours=int(plan["grace_hours"])),
        is_stub=bool(sub.is_stub),
    )
    session.add(meeting)
    logger.info("usage_meter: metered booked meeting for lead %s (account %s)",
                outcome.lead_id, owner_id)
    return meeting


def owner_scope(session: Session, strategy, purpose: str):
    """scope() for a Strategy object, resolving its owner."""
    from app.services import notifications  # noqa: PLC0415

    owner = None
    if strategy is not None:
        try:
            owner = notifications.owner_of_strategy(session, strategy)
        except Exception:
            owner = None
    return scope(session, strategy_id=getattr(strategy, "id", None), user_id=owner,
                 purpose=purpose, budget_micros=getattr(strategy, "budget_micros", None))

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

logger = logging.getLogger(__name__)

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
        active.notes.append((provider, model or "", int(input_tokens or 0),
                             int(output_tokens or 0)))
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


@contextmanager
def scope(session: Session, *, strategy_id=None, user_id=None, purpose: str = "other"):
    """Attribute every model call inside the block. See the module docstring."""
    if _current.get() is not None:
        yield _current.get()
        return
    active = _Scope(strategy_id=_uuid(strategy_id), user_id=_uuid(user_id), purpose=purpose)
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
                 purpose=purpose)

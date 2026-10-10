"""Request-side AI metering (P0-5 / P0-5b).

Every route that calls the model wraps its work in `metered(db, user, purpose)`:

    with metered(db, current_user, "drafting"):
        ...the handler body...

It does three things:

1. Before any work, for a CAPPED purpose (usage_meter.ACCOUNT_CAPPED_PURPOSES),
   answers 429 `daily_ai_limit_reached` when the account has already used its
   plan's daily AI limit -- nothing is started, nothing is written.
2. Opens a usage scope for the account, so every model call in the block is
   recorded in api_usage with the account's id and the purpose, and (capped
   purposes) refused by the gateway when it could cross the limit.
3. After the block, answers 429 when a call inside it WAS refused on the
   account cap. Many services catch every exception around a model call and
   degrade (heuristic score, fallback text); without this the user would get
   a silently worse 200 instead of being told the limit is reached.

`user` is the data owner (get_current_user's return value; in a workspace,
the owner whose plan pays). Request handlers are sync `def`, so the scope is
set and read in the same thread. Never open it in a Depends(): a sync
dependency runs in its own threadpool call, and the context variable would
not reach the handler.
"""

from __future__ import annotations

from contextlib import contextmanager

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services import usage_meter

DAILY_LIMIT_ERROR = "daily_ai_limit_reached"


def daily_limit_detail(cap_micros: int, spent_micros: int, plan_name: str) -> dict:
    return {
        "error": DAILY_LIMIT_ERROR,
        "plan": plan_name,
        "limit_usd": round(cap_micros / 1_000_000, 2),
        "spent_today_usd": round(spent_micros / 1_000_000, 2),
        "message": (f"Your {plan_name} plan's daily AI limit "
                    f"(${cap_micros / 1_000_000:.2f}) is used up. It resets at "
                    "00:00 UTC."),
    }


def refuse_if_daily_limit_reached(db: Session, user_id) -> None:
    """429 when the account has already spent its whole daily AI limit."""
    cap, plan_name = usage_meter.account_daily_cap(db, user_id)
    if cap is None:
        return
    spent = usage_meter.account_spent_today_micros(db, user_id)
    if spent >= cap:
        raise HTTPException(status_code=429,
                            detail=daily_limit_detail(cap, spent, plan_name))


@contextmanager
def metered(db: Session, user, purpose: str, *, refuse_after: bool = True):
    """See the module docstring. `refuse_after=False` for handlers whose
    degraded result is the designed outcome and is already committed (intake
    stores null patterns rather than lose what the user typed)."""
    user_id = getattr(user, "id", user)
    capped = purpose in usage_meter.ACCOUNT_CAPPED_PURPOSES
    if capped:
        refuse_if_daily_limit_reached(db, user_id)
    holder: list = []
    try:
        with usage_meter.user_scope(db, user_id, purpose) as active:
            holder.append(active)
            yield active
    except HTTPException as exc:
        # A handler that maps any model failure to 502 ("the analysis
        # failed: ..."): when the failure WAS the account cap, say so.
        if holder and holder[0].account_refused and exc.status_code >= 500:
            raise _limit_reached(db, user_id) from exc
        raise
    except usage_meter.AccountBudgetExceededError:
        # A service that let the refusal through (no degrade path).
        raise _limit_reached(db, user_id) from None
    if capped and refuse_after and holder[0].account_refused:
        raise _limit_reached(db, user_id)


def _limit_reached(db: Session, user_id) -> HTTPException:
    cap, plan_name = usage_meter.account_daily_cap(db, user_id)
    spent = usage_meter.account_spent_today_micros(db, user_id)
    return HTTPException(status_code=429,
                         detail=daily_limit_detail(cap or 0, spent, plan_name))

"""Smart send time (Feature Group 3): each campaign's top engagement windows.

WHAT IS MEASURED
Every open (pixel) and reply of a campaign, placed on the LEAD's local clock
(day-of-week x hour, lead timezone -- the same timezone the send window
uses). "Tuesday 9am" means 9am where the reader is, not where the server is.

HOW A WINDOW IS SCORED
score(slot) = opens + 3 x replies. A reply is the outcome the campaign exists
for and an open is a noisy proxy for it (see open_tracking.py on Apple MPP),
hence the weight. `share` is the slot's fraction of all in-window engagement
-- the "engagement rate" the UI shows.

Only slots INSIDE the configured send window (business hours, weekdays when
weekends are skipped) can become windows: a window the scheduler is not
allowed to send in is useless, however many people read email at 10pm.

Windows are computed once the campaign has `send_time_min_opens` opens
(immediately on crossing the threshold, then nightly). Fewer than that and a
single enthusiastic reader would decide the schedule for everyone.

SCHEDULING
With the campaign's `smart_send_time` on, a step that would send at T is
moved to the next top-3 window at or after T -- never earlier, never more
than `send_time_max_delay_hours` later (otherwise it sends at T, as before).
Leads are spread over the first 45 minutes of the window hour so a campaign
does not fire a burst at :00. Turning it on also moves already-scheduled,
not-yet-sent steps; turning it off leaves them where they are.

This is PER CAMPAIGN. The older M8 optimizer (send_time_optimizer.py) is a
cross-campaign recommendation by ICP bucket shown on the Analytics page; it
does not schedule anything.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Lead,
    Message,
    MessageStatus,
    Outcome,
    OutcomeEvent,
    Sequence,
    Strategy,
)

WEIGHT_OPEN = 1
WEIGHT_REPLY = 3
TOP_N = 3
SPREAD_MINUTES = 45
_RESLOT_GRACE = timedelta(minutes=5)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _schedulable(dow: int, hour: int) -> bool:
    from app.config import settings  # noqa: PLC0415

    if settings.send_window_skip_weekends and dow >= 5:
        return False
    return settings.send_window_start_hour <= hour < settings.send_window_end_hour


def engagement_slots(session: Session, strategy_id) -> dict[tuple[int, int], dict]:
    """{(dow, hour): {"opens": n, "replies": n}} on the lead's local clock.
    dow: Monday=0 .. Sunday=6 (Python's weekday())."""
    from app.services.sequence_engine import lead_timezone  # noqa: PLC0415

    rows = session.execute(
        select(Outcome.event, Outcome.ts, Outcome.meta_json, Lead)
        .join(Lead, Lead.id == Outcome.lead_id)
        .where(Lead.strategy_id == strategy_id,
               Outcome.event.in_([OutcomeEvent.OPENED, OutcomeEvent.REPLIED]))
    ).all()
    slots: dict[tuple[int, int], dict] = {}
    zones: dict = {}
    for event, ts, meta, lead in rows:
        meta = meta if isinstance(meta, dict) else {}
        if isinstance(meta.get("local_dow"), int) and isinstance(meta.get("local_hour"), int):
            key = (meta["local_dow"], meta["local_hour"])
        elif ts is not None:
            tz = zones.get(lead.id) or zones.setdefault(lead.id, ZoneInfo(lead_timezone(lead)))
            local = _aware(ts).astimezone(tz)
            key = (local.weekday(), local.hour)
        else:
            continue
        cell = slots.setdefault(key, {"opens": 0, "replies": 0})
        cell["opens" if event is OutcomeEvent.OPENED else "replies"] += 1
    return slots


def _score(cell: dict) -> int:
    return cell["opens"] * WEIGHT_OPEN + cell["replies"] * WEIGHT_REPLY


def heatmap(session: Session, strategy_id) -> list[dict]:
    return [
        {"dow": dow, "hour": hour, "opens": c["opens"], "replies": c["replies"],
         "score": _score(c), "schedulable": _schedulable(dow, hour)}
        for (dow, hour), c in sorted(engagement_slots(session, strategy_id).items())
    ]


def compute(session: Session, strategy: Strategy, now: datetime | None = None) -> dict:
    """Recompute and store the campaign's windows. Returns a status dict."""
    from app.services import open_tracking, system_settings  # noqa: PLC0415

    now = now or datetime.now(timezone.utc)
    needed = system_settings.get(session, "send_time_min_opens")
    opens = open_tracking.strategy_open_count(session, strategy.id)
    if opens < needed:
        return {"status": "insufficient_data", "opens": opens, "needed": needed}

    slots = engagement_slots(session, strategy.id)
    usable = [(dow, hour, c) for (dow, hour), c in slots.items() if _schedulable(dow, hour)]
    total = sum(_score(c) for _, _, c in usable)
    top = sorted(usable, key=lambda t: (-_score(t[2]), t[0], t[1]))[:TOP_N]
    windows = [
        {"dow": dow, "hour": hour, "score": _score(c),
         "share": round(_score(c) / total, 4) if total else 0.0,
         "opens": c["opens"], "replies": c["replies"]}
        for dow, hour, c in top
    ]
    strategy.send_windows_json = {
        "windows": windows,
        "opens": sum(c["opens"] for c in slots.values()),
        "replies": sum(c["replies"] for c in slots.values()),
    }
    strategy.send_windows_computed_at = now
    session.commit()
    return {"status": "computed" if windows else "no_schedulable_engagement",
            "opens": opens, "needed": needed, "windows": windows}


def _windows_of(strategy: Strategy | None) -> set[tuple[int, int]]:
    if strategy is None or not strategy.smart_send_time:
        return set()
    data = strategy.send_windows_json if isinstance(strategy.send_windows_json, dict) else {}
    return {(int(w["dow"]), int(w["hour"])) for w in data.get("windows") or []
            if isinstance(w, dict) and "dow" in w and "hour" in w}


def _spread(key) -> int:
    if key is None:
        return 0
    return int(hashlib.sha256(str(key).encode()).hexdigest(), 16) % SPREAD_MINUTES


def next_smart_slot(session: Session, strategy: Strategy | None, earliest: datetime,
                    tz_name: str, *, spread_key=None) -> datetime:
    """The first top window at or after `earliest`, within the delay cap;
    `earliest` itself when smart send time is off, has no windows, or no
    window falls inside the cap."""
    windows = _windows_of(strategy)
    if not windows:
        return earliest
    from app.services import system_settings  # noqa: PLC0415

    earliest = _aware(earliest)
    tz = ZoneInfo(tz_name)
    local = earliest.astimezone(tz)
    if (local.weekday(), local.hour) in windows:
        return earliest
    limit = earliest + timedelta(hours=system_settings.get(session, "send_time_max_delay_hours"))
    candidate = local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    offset = timedelta(minutes=_spread(spread_key))
    while candidate.astimezone(timezone.utc) <= limit:
        if (candidate.weekday(), candidate.hour) in windows:
            return min((candidate + offset).astimezone(timezone.utc), limit)
        candidate += timedelta(hours=1)
    return earliest


def reslot_scheduled(session: Session, strategy: Strategy,
                     now: datetime | None = None) -> int:
    """Move this campaign's future SCHEDULED steps into its windows. Steps
    due within five minutes are left alone -- the dispatcher may already be
    picking them up."""
    from app.services.sequence_engine import lead_timezone  # noqa: PLC0415

    if not _windows_of(strategy):
        return 0
    now = now or datetime.now(timezone.utc)
    messages = session.execute(
        select(Message).join(Sequence, Sequence.id == Message.sequence_id)
        .where(Sequence.strategy_id == strategy.id,
               Message.status == MessageStatus.SCHEDULED,
               Message.scheduled_at.isnot(None))
    ).scalars().all()
    moved = 0
    for message in messages:
        current = _aware(message.scheduled_at)
        if current <= now + _RESLOT_GRACE:
            continue
        lead = session.get(Lead, message.lead_id)
        if lead is None:
            continue
        new = next_smart_slot(session, strategy, current, lead_timezone(lead),
                              spread_key=lead.id)
        if new != current:
            message.scheduled_at = new
            moved += 1
    session.commit()
    return moved


def status(session: Session, strategy: Strategy) -> dict:
    from app.services import open_tracking, system_settings  # noqa: PLC0415

    data = strategy.send_windows_json if isinstance(strategy.send_windows_json, dict) else {}
    computed = _aware(strategy.send_windows_computed_at)
    return {
        "smart_send_time": bool(strategy.smart_send_time),
        "windows": data.get("windows") or [],
        "computed_at": computed.isoformat() if computed else None,
        "opens": open_tracking.strategy_open_count(session, strategy.id),
        "min_opens": system_settings.get(session, "send_time_min_opens"),
        "max_delay_hours": system_settings.get(session, "send_time_max_delay_hours"),
        "heatmap": heatmap(session, strategy.id),
    }

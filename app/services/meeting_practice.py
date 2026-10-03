"""The call script and the pre-meeting readiness checklist (Part 2).

TWO THINGS LIVE HERE, and they are related:

1. THE SCRIPT the seller takes into the call -- opening, discovery questions,
   objection-handling lines, and the close. It is SEEDED from the brief and
   then OWNED BY THE SELLER: `script_json` is written by a person, and
   regenerating the brief never touches it. A tool that silently overwrites an
   edit is a tool whose edits nobody makes twice.

2. THE READINESS CHECKLIST -- what is still missing before this call. Derived,
   never stored, because every item is a fact that already exists somewhere
   (the brief's status, whether the script was edited, whether a roleplay was
   completed). A stored checklist is a checklist that goes stale and then lies.

WHY PRACTICE IS NOT REQUIRED BY DEFAULT. Making every call require a rehearsal
is how a checklist becomes something people click through without reading. The
brief carries `practice_required` per meeting, and the checklist only BLOCKS
when it is set.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import Lead, MeetingPrepBrief, MeetingPrepStatus, User

logger = logging.getLogger(__name__)

#: The parts of a call, in the order they happen. The script is always these
#: five keys, so the UI can render it without discovering the shape.
SCRIPT_KEYS = ("opening", "discovery", "objections", "close", "notes")

MAX_LINE = 2000
MAX_ITEMS = 12


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# The script
# --------------------------------------------------------------------------


def seed_from_brief(brief: MeetingPrepBrief) -> dict:
    """The first draft of the script, lifted from the brief's own sections.

    Not a second model call: everything the opening, the questions and the
    objection lines need was already generated for the brief, and asking again
    would produce a script that disagrees with the page above it.
    """
    sections = brief.sections_json if isinstance(brief.sections_json, dict) else {}
    return {
        "opening": (brief.opening_script or sections.get("opening_60_seconds") or ""),
        "discovery": list(sections.get("discovery_questions") or [])[:MAX_ITEMS],
        "objections": [
            {"objection": item.get("objection", ""), "response": item.get("response", "")}
            for item in (sections.get("likely_objections") or [])
            if isinstance(item, dict) and item.get("objection")
        ][:MAX_ITEMS],
        "close": _close_line(sections),
        "notes": "",
    }


def _close_line(sections: dict) -> str:
    """A concrete next-step ask, built from the brief's own next steps.

    A close that says "ask for the next step" is not a close; it has to be a
    sentence the seller can actually say."""
    steps = [s for s in (sections.get("next_steps") or []) if isinstance(s, str) and s.strip()]
    if steps:
        return (f"Based on what you've said, the next step I'd suggest is: "
                f"{steps[0].strip()} — does that work?")
    return ("Based on what you've said, would it make sense to put thirty minutes "
            "in the diary next week to go through it properly?")


def clean_script(data: object) -> dict:
    """Normalise a submitted script to exactly SCRIPT_KEYS.

    Anything malformed is dropped rather than coerced -- a list of objects
    rendered as a bullet list is how "[object Object]" reaches a user, which
    is the same rule meeting_prep.clean_sections follows.
    """
    data = data if isinstance(data, dict) else {}

    discovery = data.get("discovery")
    if isinstance(discovery, str):
        discovery = [discovery]
    discovery = [" ".join(str(q).split())[:MAX_LINE] for q in (discovery or [])
                 if isinstance(q, str) and str(q).strip()][:MAX_ITEMS]

    objections = []
    for item in data.get("objections") or []:
        if isinstance(item, str) and item.strip():
            item = {"objection": item, "response": ""}
        if not isinstance(item, dict):
            continue
        objection = " ".join(str(item.get("objection") or "").split())[:MAX_LINE]
        if objection:
            objections.append({
                "objection": objection,
                "response": " ".join(str(item.get("response") or "").split())[:MAX_LINE],
            })

    return {
        "opening": str(data.get("opening") or "").strip()[:MAX_LINE],
        "discovery": discovery,
        "objections": objections[:MAX_ITEMS],
        "close": str(data.get("close") or "").strip()[:MAX_LINE],
        "notes": str(data.get("notes") or "").strip()[:MAX_LINE * 2],
    }


def ensure_script(db: Session, brief: MeetingPrepBrief,
                  commit: bool = True) -> dict:
    """Seed the script if it has never been written. Never overwrites.

    This is the rule the whole feature rests on: `script_json` is the seller's,
    and a regeneration of the brief must not touch it.
    """
    if isinstance(brief.script_json, dict) and brief.script_json:
        return brief.script_json
    brief.script_json = seed_from_brief(brief)
    if commit:
        db.commit()
    return brief.script_json


def save_script(db: Session, brief: MeetingPrepBrief, data: object,
                actor: User | None = None, now: datetime | None = None) -> dict:
    """The seller's edit. Recorded with who and when, so "the script changed"
    is never a mystery on a shared account."""
    brief.script_json = clean_script(data)
    brief.script_edited_at = now or _now()
    brief.script_edited_by_user_id = actor.id if actor is not None else None
    db.commit()
    return brief.script_json


def script_out(brief: MeetingPrepBrief) -> dict:
    script = brief.script_json if isinstance(brief.script_json, dict) else {}
    return {
        "brief_id": str(brief.id),
        "script": {key: script.get(key, [] if key in ("discovery", "objections") else "")
                   for key in SCRIPT_KEYS},
        # True once a person has touched it. The UI says "suggested" until
        # then, so nobody mistakes generated text for something they approved.
        "edited": brief.script_edited_at is not None,
        "edited_at": (brief.script_edited_at.isoformat()
                      if brief.script_edited_at else None),
        "edited_by_user_id": (str(brief.script_edited_by_user_id)
                              if brief.script_edited_by_user_id else None),
    }


# --------------------------------------------------------------------------
# The readiness checklist
# --------------------------------------------------------------------------


def _item(key: str, label: str, done: bool, detail: str,
          blocking: bool = False) -> dict:
    return {"key": key, "label": label, "done": done, "detail": detail,
            "blocking": blocking and not done}


def readiness(db: Session, brief: MeetingPrepBrief, *, user_id=None,
              now: datetime | None = None) -> dict:
    """What is still missing before this call.

    Derived every time, never stored: every item is a fact that already exists
    somewhere, and a stored checklist goes stale and then lies.
    """
    from app.services import roleplay  # noqa: PLC0415

    now = now or _now()
    user_id = user_id or brief.user_id
    sections = brief.sections_json if isinstance(brief.sections_json, dict) else {}
    script = brief.script_json if isinstance(brief.script_json, dict) else {}

    ready = brief.status is MeetingPrepStatus.READY
    objection_count = len(script.get("objections") or sections.get("likely_objections") or [])
    practised = bool(brief.lead_id) and roleplay.practiced_recently(
        db, user_id, brief.lead_id, now=now)

    items = [
        _item("brief", "Prep brief generated", ready,
              "Ready to read." if ready else
              f"The brief is {brief.status.value if brief.status else 'missing'}.",
              blocking=True),
        _item("script", "Call script reviewed", brief.script_edited_at is not None,
              "You have edited the script."
              if brief.script_edited_at is not None
              else "The script is still the suggested draft — read it and make it yours."),
        _item("objections", "Objections prepared", objection_count >= 3,
              f"{objection_count} objection{'s' if objection_count != 1 else ''} "
              f"with a response ready."
              if objection_count else "No objections prepared."),
        _item("practice", "Practised the call", practised,
              "You have rehearsed this one in the last two weeks."
              if practised else "Not rehearsed yet.",
              blocking=bool(brief.practice_required)),
    ]

    blocking = [i for i in items if i["blocking"]]
    done = sum(1 for i in items if i["done"])
    minutes = None
    start = _aware(brief.meeting_start_at)
    if start is not None:
        minutes = int((start - now).total_seconds() // 60)

    return {
        "brief_id": str(brief.id),
        "lead_id": str(brief.lead_id),
        "items": items,
        "done": done,
        "total": len(items),
        "ready": not blocking,
        "blocking": [i["key"] for i in blocking],
        "practice_required": bool(brief.practice_required),
        "meeting_start_at": start.isoformat() if start else None,
        "minutes_until": minutes,
        "headline": _headline(items, blocking, minutes),
    }


def _headline(items: list[dict], blocking: list[dict], minutes: int | None) -> str:
    """The one line the reminder and the panel both show."""
    when = ""
    if minutes is not None and 0 <= minutes <= 60 * 48:
        when = (f" — {minutes} minutes away" if minutes < 120
                else f" — in {minutes // 60} hours")
    if blocking:
        return (f"Not ready{when}: " +
                ", ".join(i["label"].lower() for i in blocking) + ".")
    outstanding = [i for i in items if not i["done"]]
    if outstanding:
        return (f"Ready{when}, but {len(outstanding)} thing"
                f"{'s' if len(outstanding) != 1 else ''} still open: " +
                ", ".join(i["label"].lower() for i in outstanding) + ".")
    return f"Ready{when}."


def set_practice_required(db: Session, brief: MeetingPrepBrief,
                          required: bool) -> MeetingPrepBrief:
    """Make practice a blocking step for THIS meeting.

    Per meeting rather than per account on purpose: the call that is worth
    rehearsing is the one that matters, and a global rule turns the checklist
    into noise on the other twenty."""
    brief.practice_required = bool(required)
    db.commit()
    return brief


def lead_for(db: Session, brief: MeetingPrepBrief) -> Lead | None:
    return db.get(Lead, brief.lead_id) if brief.lead_id else None

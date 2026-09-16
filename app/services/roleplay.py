"""Mock-interview roleplay for sales calls (Part 2).

WHAT THIS IS. The AI plays the PROSPECT -- their company, their stated pains,
the objections they have actually raised -- and the seller practises the call
before taking it. Afterwards the same context produces feedback: what went
well, what to improve, tone and pacing, and which objections were not handled.

WHY IT IS BUILT ON THE BRIEF AND NOT ON A FRESH PROMPT. Everything worth
roleplaying against is already in the meeting prep brief: the company overview,
the pains inferred from the F-P-T-A signals, the objections this prospect has
actually raised, their own words from their replies. Re-deriving it here would
produce a prospect who contradicts the brief the seller just read -- and the
seller would rightly stop trusting both.

THE PROSPECT NEVER BECOMES A COACH. The single most common failure of a
roleplay feature is an AI that breaks character to be encouraging ("Great
question! As a fire-safety director, I would say..."). The system prompt
forbids it, and `_clean_reply` strips the give-away prefixes if it happens
anyway. A prospect who is nicer than the real one teaches the wrong lesson.

FEEDBACK IS SCORED ON FIVE AXES, stored as columns rather than inside the JSON,
because "am I getting better?" is a chart across sessions and extracting a
number from JSON is spelled differently on SQLite and PostgreSQL.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    InboundReply,
    Lead,
    MeetingPrepBrief,
    RoleplaySession,
    RoleplayTurn,
    User,
)

logger = logging.getLogger(__name__)

SELLER, PROSPECT = "seller", "prospect"
ACTIVE, COMPLETED, ABANDONED = "active", "completed", "abandoned"

EASY, REALISTIC, HOSTILE = "easy", "realistic", "hostile"
DIFFICULTIES = (EASY, REALISTIC, HOSTILE)

DIFFICULTY_NOTES = {
    EASY: ("Warm and curious. You raise at most one mild objection and you "
           "give ground when the seller answers it."),
    REALISTIC: ("Busy and slightly sceptical, the way a real prospect who took "
                "a cold meeting is. You raise your real objections, you do not "
                "volunteer information, and you need a reason to keep talking."),
    HOSTILE: ("Short of time and unconvinced you should have taken this call. "
              "You interrupt, you push back hard, and you end the call if the "
              "seller wastes two minutes."),
}

#: Practice is a rehearsal, not a novel. Past this the feedback is better than
#: another exchange, and an unbounded roleplay is an unbounded model bill.
MAX_TURNS = 40
SCORE_KEYS = ("overall", "discovery", "objections", "tone", "close")

MAX_TOKENS_REPLY = 700
MAX_TOKENS_FEEDBACK = 1500

_PERSONA_SYSTEM = (
    "You are ROLEPLAYING A SALES PROSPECT so a seller can practise a call. "
    "You are NOT an assistant and NOT a coach.\n"
    "ABSOLUTE RULES:\n"
    "1. Stay in character. Never break character to praise, explain, coach or "
    "comment on the seller's technique, however well or badly they do. No "
    "'great question', no 'as your prospect I would say', no meta commentary.\n"
    "2. Speak only as the person described below, in first person, the way "
    "someone talks on a call -- short turns, interruptions, unfinished "
    "sentences. Never write stage directions or narration.\n"
    "3. Use ONLY what the brief gives you about this company and this person. "
    "Do not invent a budget, a headcount, a competitor or a timeline that is "
    "not there; if the seller asks about something you were not told, answer "
    "vaguely the way a real person does.\n"
    "4. Raise the objections listed below when they naturally fit -- not all "
    "at once.\n"
    "5. If the seller earns it, you may agree a next step. If they do not, "
    "you may end the call. Both are legitimate outcomes of practice.\n"
    "Reply with the prospect's next spoken turn only."
)

_FEEDBACK_SYSTEM = (
    "You are a sales coach reviewing a transcript of a practice call. The "
    "seller was practising; the prospect was played by an AI.\n"
    "Respond with ONLY a JSON object:\n"
    '{"scores": {"overall": 0-100, "discovery": 0-100, "objections": 0-100, '
    '"tone": 0-100, "close": 0-100}, "went_well": ["..."], '
    '"improve": ["..."], "tone_notes": "...", "pacing_notes": "...", '
    '"objections_missed": [{"objection": "...", "why": "..."}], '
    '"one_thing": "..."}\n'
    "RULES. Judge ONLY the transcript -- never assume what the seller knows "
    "or meant. Every point QUOTES the line it is about, so the seller can "
    "find it. `objections_missed` lists objections the prospect raised that "
    "the seller did not answer, or answered by changing the subject; an empty "
    "list is the correct answer when they handled everything. `one_thing` is "
    "the single change that would most improve the next call. Be specific and "
    "be honest -- a review that praises everything teaches nothing."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _client():
    from app.services.anthropic_client import get_client  # noqa: PLC0415

    return get_client()


# --------------------------------------------------------------------------
# Building the prospect
# --------------------------------------------------------------------------


def build_persona(db: Session, lead: Lead | None,
                  brief: MeetingPrepBrief | None) -> dict:
    """Who the AI is playing, assembled from what is already known.

    Reuses the brief rather than re-deriving: a prospect who contradicts the
    brief the seller just read makes the seller stop trusting both.
    """
    sections = (brief.sections_json if brief and isinstance(brief.sections_json, dict)
                else {})
    profile = (brief.profile_json if brief and isinstance(brief.profile_json, dict)
               else {})

    objections = [item.get("objection") for item in sections.get("likely_objections") or []
                  if isinstance(item, dict) and item.get("objection")]
    # Objections the prospect has ACTUALLY raised outrank predicted ones: a
    # rehearsal against the real pushback is worth more than one against a
    # guess, so they go first and are marked as real.
    real: list[str] = []
    if lead is not None:
        for reply in db.execute(
                select(InboundReply).where(InboundReply.lead_id == lead.id)
                .order_by(InboundReply.created_at)).scalars():
            if (reply.reply_category or "").upper() == "OBJECTION" or \
                    reply.intent_label == "objection":
                text = " ".join((reply.body or "").split())[:300]
                if text:
                    real.append(text)

    fpta = []
    if lead is not None and isinstance(lead.fpta_reasons_json, dict):
        for key in ("fit", "problem", "timing", "access"):
            entry = lead.fpta_reasons_json.get(key) or {}
            if entry.get("reason"):
                fpta.append(f"{key}: {entry['reason']}")

    return {
        "name": (profile.get("name") or (lead.full_name if lead else None)
                 or "the prospect"),
        "title": profile.get("title") or (lead.title if lead else None),
        "company": profile.get("company") or (lead.company if lead else None),
        "company_overview": sections.get("company_overview"),
        "recent_activity": sections.get("recent_activity"),
        "why_they_booked": sections.get("why_they_booked"),
        "pain_points": sections.get("pain_points") or [],
        # Their own words first, then the predicted ones.
        "real_objections": real[:4],
        "predicted_objections": objections[:5],
        "fpta_signals": fpta,
    }


def objectives_for(persona: dict) -> list[str]:
    """What this rehearsal is for. Shown to the seller BEFORE they start --
    practice without a target is just a conversation."""
    goals = ["Open in under 60 seconds without pitching."]
    if persona.get("pain_points"):
        goals.append("Confirm or disprove at least one of the pains in the brief, "
                     "in their words.")
    objections = (persona.get("real_objections") or []) + \
        (persona.get("predicted_objections") or [])
    if objections:
        goals.append(f"Handle the objection they are most likely to raise "
                     f"({objections[0][:80]}).")
    goals.append("Agree a specific next step with a date on it.")
    return goals


def _persona_prompt(persona: dict, difficulty: str) -> str:
    lines = [
        _PERSONA_SYSTEM,
        "\n--- WHO YOU ARE ---",
        f"Name: {persona.get('name')}",
        f"Title: {persona.get('title') or 'not recorded'}",
        f"Company: {persona.get('company') or 'not recorded'}",
        f"About the company: {persona.get('company_overview') or 'nothing on record'}",
        f"Recently: {persona.get('recent_activity') or 'nothing on record'}",
        f"Why you took this meeting: {persona.get('why_they_booked') or 'not recorded'}",
    ]
    if persona.get("pain_points"):
        lines.append("Pains the seller believes you have (they are HYPOTHESES -- "
                     "agree only where it fits what you were told):")
        lines += [f"  - {p}" for p in persona["pain_points"]]
    if persona.get("real_objections"):
        lines.append("Objections you have ALREADY raised to this seller, in your "
                     "own words -- raise these first and stay consistent with them:")
        lines += [f'  - "{o}"' for o in persona["real_objections"]]
    if persona.get("predicted_objections"):
        lines.append("Other objections that would be in character:")
        lines += [f"  - {o}" for o in persona["predicted_objections"]]
    lines.append(f"\n--- HOW YOU BEHAVE ---\n{DIFFICULTY_NOTES.get(difficulty, DIFFICULTY_NOTES[REALISTIC])}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# The session
# --------------------------------------------------------------------------


def start(db: Session, user: User, *, lead: Lead | None = None,
          brief: MeetingPrepBrief | None = None, difficulty: str = REALISTIC,
          now: datetime | None = None) -> RoleplaySession:
    """Open a practice session. The prospect speaks first, as on a real call
    where the person who took the meeting says hello."""
    now = now or _now()
    if difficulty not in DIFFICULTIES:
        difficulty = REALISTIC
    persona = build_persona(db, lead, brief)
    session = RoleplaySession(
        user_id=user.id,
        lead_id=lead.id if lead is not None else None,
        brief_id=brief.id if brief is not None else None,
        status=ACTIVE, difficulty=difficulty,
        persona_json=persona, objectives_json=objectives_for(persona),
        started_at=now, turn_count=0,
    )
    db.add(session)
    db.commit()

    opener = (f"Hi — {persona.get('name', 'there')} here. I've got about fifteen "
              f"minutes, what did you want to talk about?")
    _append(db, session, PROSPECT, opener)
    return session


def _append(db: Session, session: RoleplaySession, role: str, content: str) -> RoleplayTurn:
    """Add one line. The turn number comes from the count, and the UNIQUE
    constraint turns a duplicated submit into a conflict rather than a
    duplicated line."""
    turn = RoleplayTurn(session_id=session.id, turn_no=session.turn_count + 1,
                        role=role, content=content)
    db.add(turn)
    session.turn_count += 1
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.execute(
            select(RoleplayTurn).where(RoleplayTurn.session_id == session.id)
            .order_by(RoleplayTurn.turn_no.desc())).scalars().first()
        return existing
    return turn


def turns(db: Session, session: RoleplaySession) -> list[RoleplayTurn]:
    return list(db.execute(
        select(RoleplayTurn).where(RoleplayTurn.session_id == session.id)
        .order_by(RoleplayTurn.turn_no)).scalars())


def _transcript(rows: list[RoleplayTurn]) -> str:
    return "\n".join(f"{'SELLER' if t.role == SELLER else 'PROSPECT'}: {t.content}"
                     for t in rows)


def _clean_reply(text: str, persona: dict) -> str:
    """Strip the ways a model breaks character even when told not to.

    A prospect who congratulates the seller on their question is teaching the
    wrong lesson, so the give-aways are removed rather than shown.
    """
    cleaned = " ".join(str(text or "").split())
    for prefix in ("PROSPECT:", "Prospect:", f"{persona.get('name', '')}:"):
        if prefix and cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    for tell in ("Great question", "Good question", "That's a great",
                 "As your prospect", "As the prospect", "(As ", "[As "):
        if cleaned.startswith(tell):
            # Drop the coaching sentence, keep whatever followed it.
            _, _, rest = cleaned.partition(".")
            cleaned = rest.strip() or cleaned
            break
    return cleaned[:2000]


def reply(db: Session, session: RoleplaySession, message: str,
          now: datetime | None = None) -> dict:
    """The seller speaks; the prospect answers.

    RETURNS {"status", "prospect", "turn_count", "limit_reached"}.
    On a model failure the SELLER'S line is still saved -- losing what a
    person said because the other side failed to answer is the one thing a
    practice tool must not do.
    """
    now = now or _now()
    if session.status != ACTIVE:
        return {"status": "closed", "prospect": None,
                "turn_count": session.turn_count, "limit_reached": False}

    _append(db, session, SELLER, " ".join(str(message or "").split())[:4000])
    if session.turn_count >= MAX_TURNS:
        return {"status": "limit", "prospect": None,
                "turn_count": session.turn_count, "limit_reached": True}

    persona = session.persona_json or {}
    try:
        answer = _client().complete(
            system=_persona_prompt(persona, session.difficulty),
            prompt=(f"THE CALL SO FAR\n{_transcript(turns(db, session))}\n\n"
                    "Your next spoken turn:"),
            max_tokens=MAX_TOKENS_REPLY,
        )
        spoken = _clean_reply(answer, persona)
        if not spoken:
            raise ValueError("the model returned nothing to say")
    except Exception as exc:  # noqa: BLE001 -- see the docstring
        logger.warning("roleplay reply failed for session %s: %s", session.id, exc)
        session.error = f"{type(exc).__name__}: {exc}"[:500]
        db.commit()
        return {"status": "failed", "prospect": None,
                "turn_count": session.turn_count, "limit_reached": False}

    _append(db, session, PROSPECT, spoken)
    session.error = None
    db.commit()
    return {"status": "ok", "prospect": spoken, "turn_count": session.turn_count,
            "limit_reached": session.turn_count >= MAX_TURNS}


# --------------------------------------------------------------------------
# Feedback
# --------------------------------------------------------------------------


def _clamp_score(value) -> int | None:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return None


def _clean_feedback(data: object) -> dict:
    data = data if isinstance(data, dict) else {}
    raw = data.get("scores") if isinstance(data.get("scores"), dict) else {}
    scores = {key: _clamp_score(raw.get(key)) for key in SCORE_KEYS}

    def _list(key: str, limit: int = 6) -> list[str]:
        value = data.get(key)
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        return [" ".join(str(item).split())[:500] for item in value
                if isinstance(item, str) and str(item).strip()][:limit]

    missed = []
    for item in data.get("objections_missed") or []:
        if isinstance(item, str) and item.strip():
            item = {"objection": item, "why": ""}
        if not isinstance(item, dict):
            continue
        objection = " ".join(str(item.get("objection") or "").split())[:300]
        if objection:
            missed.append({"objection": objection,
                           "why": " ".join(str(item.get("why") or "").split())[:400]})

    return {
        "scores": scores,
        "went_well": _list("went_well"),
        "improve": _list("improve"),
        "tone_notes": " ".join(str(data.get("tone_notes") or "").split())[:1000],
        "pacing_notes": " ".join(str(data.get("pacing_notes") or "").split())[:1000],
        "objections_missed": missed[:6],
        "one_thing": " ".join(str(data.get("one_thing") or "").split())[:500],
    }


def finish(db: Session, session: RoleplaySession, *, abandoned: bool = False,
           now: datetime | None = None) -> RoleplaySession:
    """End the session and write the feedback.

    A session abandoned after two lines gets no feedback: scoring a
    conversation that never happened produces a number that means nothing and
    then pollutes the improvement chart.
    """
    now = now or _now()
    rows = turns(db, session)
    seller_lines = [t for t in rows if t.role == SELLER]

    session.ended_at = now
    if abandoned or len(seller_lines) < 2:
        session.status = ABANDONED
        db.commit()
        return session

    try:
        data = _client().complete_json(
            system=_FEEDBACK_SYSTEM,
            prompt=("WHAT THE SELLER WAS PRACTISING\n"
                    + "\n".join(f"- {o}" for o in (session.objectives_json or []))
                    + "\n\nOBJECTIONS THE PROSPECT WAS BRIEFED TO RAISE\n"
                    + "\n".join(f"- {o}" for o in
                                ((session.persona_json or {}).get("real_objections") or [])
                                + ((session.persona_json or {}).get("predicted_objections")
                                   or []))
                    + f"\n\nTRANSCRIPT\n{_transcript(rows)}\n\nReturn the JSON object now."),
            max_tokens=MAX_TOKENS_FEEDBACK,
        )
        feedback = _clean_feedback(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("roleplay feedback failed for session %s: %s", session.id, exc)
        session.status = COMPLETED
        session.error = f"feedback unavailable: {type(exc).__name__}"[:500]
        db.commit()
        return session

    session.status = COMPLETED
    session.feedback_json = feedback
    session.score_overall = feedback["scores"]["overall"]
    session.score_discovery = feedback["scores"]["discovery"]
    session.score_objections = feedback["scores"]["objections"]
    session.score_tone = feedback["scores"]["tone"]
    session.score_close = feedback["scores"]["close"]
    session.error = None
    db.commit()
    return session


# --------------------------------------------------------------------------
# Output and history
# --------------------------------------------------------------------------


def session_out(db: Session, session: RoleplaySession, *,
                include_turns: bool = True) -> dict:
    lead = db.get(Lead, session.lead_id) if session.lead_id else None
    out = {
        "id": str(session.id),
        "status": session.status,
        "difficulty": session.difficulty,
        "lead": ({"id": str(lead.id), "full_name": lead.full_name,
                  "company": lead.company} if lead else None),
        "brief_id": str(session.brief_id) if session.brief_id else None,
        "persona": session.persona_json,
        "objectives": session.objectives_json or [],
        "turn_count": session.turn_count,
        "max_turns": MAX_TURNS,
        "scores": {key: getattr(session, f"score_{key}") for key in SCORE_KEYS},
        "feedback": session.feedback_json,
        "error": session.error,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
    }
    if include_turns:
        out["turns"] = [{"turn_no": t.turn_no, "role": t.role, "content": t.content,
                         "at": t.created_at.isoformat() if t.created_at else None}
                        for t in turns(db, session)]
    return out


def history(db: Session, user_id, *, lead_id=None, limit: int = 50) -> dict:
    """Past sessions, newest first, with the trend across them.

    The trend is the whole point of storing history: one score is an opinion,
    a line is progress.
    """
    query = select(RoleplaySession).where(RoleplaySession.user_id == user_id)
    if lead_id is not None:
        query = query.where(RoleplaySession.lead_id == lead_id)
    # created_at is the tiebreak, not decoration: several sessions in one
    # sitting share a started_at to the second, and a DESC on that alone is
    # not a stable order -- which would draw the improvement line backwards.
    rows = list(db.execute(
        query.order_by(RoleplaySession.started_at.desc(),
                       RoleplaySession.created_at.desc()).limit(limit)).scalars())
    scored = [r for r in rows if r.score_overall is not None]
    # Sorted ASCENDING for the chart, explicitly, rather than by reversing the
    # display order -- the two are only the same while the sort is total.
    floor = datetime.min.replace(tzinfo=timezone.utc)
    scored_oldest_first = sorted(
        scored, key=lambda r: (_aware(r.started_at) or floor,
                               _aware(r.created_at) or floor))

    return {
        "total": len(rows),
        "completed": sum(1 for r in rows if r.status == COMPLETED),
        "items": [session_out(db, row, include_turns=False) for row in rows],
        "trend": [{"at": r.started_at.isoformat() if r.started_at else None,
                   "overall": r.score_overall,
                   "discovery": r.score_discovery,
                   "objections": r.score_objections,
                   "tone": r.score_tone,
                   "close": r.score_close}
                  for r in scored_oldest_first],
        # None, never 0, when nothing has been scored: "no practice yet" and
        # "practised badly" are different facts.
        "average_overall": (round(sum(r.score_overall for r in scored) / len(scored))
                            if scored else None),
        "best_overall": max((r.score_overall for r in scored), default=None),
    }


def practiced_recently(db: Session, user_id, lead_id, *, within_days: int = 14,
                       now: datetime | None = None) -> bool:
    """Has this seller rehearsed this prospect lately?

    Used by the pre-meeting checklist. Only COMPLETED sessions count: opening
    a roleplay and closing the tab is not practice.
    """
    now = now or _now()
    row = db.execute(
        select(func.count(RoleplaySession.id)).where(
            RoleplaySession.user_id == user_id,
            RoleplaySession.lead_id == lead_id,
            RoleplaySession.status == COMPLETED,
        )
    ).scalar_one()
    if not row:
        return False
    latest = db.execute(
        select(RoleplaySession.ended_at)
        .where(RoleplaySession.user_id == user_id,
               RoleplaySession.lead_id == lead_id,
               RoleplaySession.status == COMPLETED)
        .order_by(RoleplaySession.ended_at.desc()).limit(1)).scalar_one_or_none()
    if latest is None:
        return False
    latest = latest if latest.tzinfo else latest.replace(tzinfo=timezone.utc)
    return (now - latest).days <= within_days

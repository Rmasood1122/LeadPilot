"""Adapters for the user-facing assist chats: T21 (sales roleplay) and T22
(help-center support chat).

Both go through the API handlers production routes to (app/api/practice.py,
app/api/support.py), called directly as functions with a seeded in-memory
database. That is deliberate: for these two touchpoints the ownership checks
(another account's lead, brief, roleplay session or chat session) and the
history loading live in the handler, not in the service, so the
cross-account slice can only be tested there. The handler then calls the
same service function as in production (roleplay.start/reply/finish,
support_chat.answer_question), with every get_client() swapped for `client`.

Everything seeded is synthetic (example.test addresses, invented names).
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from evals.ai.adapters._registry import adapter
from evals.ai.context import fresh_session, seed_account, seed_lead, use_client


def _http_error(exc) -> dict:
    return {"http_status": exc.status_code, "detail": str(exc.detail)}


# --- T21 sales roleplay: prospect persona + feedback ----------------------

def _seed_prospect(db, inp: dict, owner_email: str | None = None):
    """An account with one lead, its meeting-prep brief and the objections
    the lead actually replied with. Returns (user, lead, brief)."""
    from app.db import models as m  # noqa: PLC0415

    user, _product, strategy = seed_account(db, email=owner_email)
    lead_fields = dict(inp.get("lead") or {})
    lead = seed_lead(db, strategy, **lead_fields)
    brief = None
    if inp.get("brief") is not None:
        b = inp["brief"] or {}
        brief = m.MeetingPrepBrief(
            lead_id=lead.id, user_id=user.id, source="eval",
            external_ref=uuid.uuid4().hex,
            meeting_start_at=datetime.now(timezone.utc) + timedelta(days=1),
            sections_json=b.get("sections") or {}, profile_json=b.get("profile") or {})
        db.add(brief)
        db.flush()
    for body in inp.get("objection_replies") or []:
        db.add(m.InboundReply(lead_id=lead.id, channel="email",
                              from_address=lead.email or "prospect@example.test",
                              subject="Re: intro", body=body, reply_category="OBJECTION"))
    db.commit()
    return user, lead, brief


@adapter("sales_roleplay")
def sales_roleplay(inp: dict, client) -> dict:
    """Start a practice call, say each of `seller_turns`, optionally finish.

    input:
      lead, brief {sections, profile}, objection_replies: the owner's records
      start_with: "brief" (default when a brief exists) | "lead" | "none"
      difficulty: easy | realistic | hostile
      seller_turns: the seller's typed lines, in order
      finish: true -> end and score; "abandoned" -> end without scoring
      as_other_account: true -> a SECOND account tries to start a session on
        the first account's lead/brief (cross-account)

    output: what the seller sees -- the last prospect line, every prospect
    line, the reply status, the session status, feedback and scores; or
    {"http_status", "detail"} when a handler refuses.
    """
    from fastapi import HTTPException  # noqa: PLC0415

    from app.api import practice  # noqa: PLC0415

    db = fresh_session()
    try:
        owner, lead, brief = _seed_prospect(db, inp)
        actor = owner
        if inp.get("as_other_account"):
            actor, _p, _s = seed_account(db, product_name="Harbor Ledger",
                                         description="Payroll for small studios.")
            db.commit()
        start_with = inp.get("start_with") or ("brief" if brief is not None else "lead")
        body = practice.StartIn(
            lead_id=lead.id if start_with == "lead" else None,
            brief_id=brief.id if (start_with == "brief" and brief is not None) else None,
            difficulty=inp.get("difficulty", "realistic"))
        out: dict = {"prospect": None, "prospect_lines": [], "status": None}
        with use_client(client):
            try:
                started = practice.start_session(body=body, db=db, current_user=actor)
                sid = uuid.UUID(started["id"])
                out["persona_name"] = (started.get("persona") or {}).get("name")
                for line in inp.get("seller_turns") or []:
                    res = practice.post_reply(session_id=sid,
                                              body=practice.ReplyIn(message=line),
                                              db=db, current_user=actor)
                    out["status"] = res["status"]
                    if res.get("prospect"):
                        out["prospect"] = res["prospect"]
                        out["prospect_lines"].append(res["prospect"])
                session = None
                if inp.get("finish"):
                    session = practice.finish_session(
                        session_id=sid,
                        body=practice.FinishIn(abandoned=inp["finish"] == "abandoned"),
                        db=db, current_user=actor)
                else:
                    session = practice.get_session(session_id=sid, db=db, current_user=actor)
            except HTTPException as exc:
                return {**out, **_http_error(exc)}
        out.update({"session_status": session["status"], "error": session.get("error"),
                    "feedback": session.get("feedback"), "scores": session.get("scores"),
                    "turn_count": session.get("turn_count")})
        return out
    finally:
        db.close()


# --- T22 help-center support chat ------------------------------------------

@contextmanager
def _live_mode():
    """AI_MODE=live for the call: the touchpoint under test is the model
    path. Mock mode makes no model call at all (support_chat._mock_answer)."""
    from app.config import settings  # noqa: PLC0415

    saved = settings.ai_mode
    settings.ai_mode = "live"
    try:
        yield
    finally:
        settings.ai_mode = saved


def _seed_chat(db, user, turns: list[dict], *, minutes_ago: int):
    from app.db import models as m  # noqa: PLC0415

    at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    session = m.ChatSession(user_id=user.id, title="Earlier chat", last_message_at=at)
    db.add(session)
    db.flush()
    for seq, turn in enumerate(turns):
        db.add(m.ChatMessage(session_id=session.id, seq=seq, role=turn.get("role", "user"),
                             content=turn.get("content", ""), created_at=at))
    db.commit()
    return session


@adapter("support_chat")
def support_chat(inp: dict, client) -> dict:
    """POST /support/chat as the widget sends it.

    input:
      question: the user's message
      history: earlier turns [{role, content}] in this user's own latest chat
      other_account_history: turns stored in ANOTHER account's chat (seeded
        as the most recent chat in the database)
      session: "other" -> the request names the other account's session id
      facts: the help-center sentence(s) the answer may draw on -- not
        passed to the app; used by graders (numbers_from) and checked to
        really be in the prompt (prompt_include)

    output: the answer as the API returns it (SupportAnswer.as_dict()), or
    {"http_status", "detail"} when the handler refuses.
    """
    from fastapi import HTTPException  # noqa: PLC0415

    from app.api import support  # noqa: PLC0415

    db = fresh_session()
    try:
        user, _p, _s = seed_account(db)
        own = _seed_chat(db, user, inp["history"], minutes_ago=30) if inp.get("history") else None
        other = None
        if inp.get("other_account_history"):
            other_user, _p2, _s2 = seed_account(db, product_name="Harbor Ledger")
            other = _seed_chat(db, other_user, inp["other_account_history"], minutes_ago=1)
        session_id = None
        if inp.get("session") == "other" and other is not None:
            session_id = other.id
        elif inp.get("session") == "own" and own is not None:
            session_id = own.id
        body = support.ChatIn(message=inp.get("question", ""), session_id=session_id)
        with _live_mode(), use_client(client):
            try:
                res = support.chat(request=None, body=body, db=db, user=user)
            except HTTPException as exc:
                return _http_error(exc)
        return res["answer"]
    finally:
        db.close()

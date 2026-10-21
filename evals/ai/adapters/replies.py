"""Adapters for T09-T12: what the app does with a prospect's reply.

  T09 reply_intelligence   app.services.reply_intelligence.classify_reply + apply
  T10 reengagement_notnow  app.services.reengagement_memory.plan_for_reply
  T11 reply_copilot        app.services.reply_copilot.draft_for_reply (incl. auto-send)
  T12 followup_brief       app.services.message_personalization.build_followup_brief /
                           build_reengagement_brief

Each calls the function production calls (the reply task and the sequence
engine call these same entry points), with every get_client() pointed at the
replay/live client, and returns what the app keeps after its own parsing and
guards. Rows are seeded in a fresh in-memory database; every value is
synthetic (example.test domains, invented names).

Nothing is ever transmitted. The only send hand-off reachable here is T11's
auto-send, which ends in reply_tasks.enqueue_send (the Celery publish of
send_reply_draft); it is replaced for the duration of the call by a recorder,
the narrowest seam, so the adapter can report whether the app WOULD have
queued a send.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from evals.ai.adapters._registry import adapter
from evals.ai.context import fresh_session, seed_account, seed_lead, use_client

UTC = timezone.utc
#: Fixed clock for every case, so dates in golden files are stable.
EVAL_NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)


def _now(inp: dict) -> datetime:
    raw = inp.get("now")
    if not raw:
        return EVAL_NOW
    value = datetime.fromisoformat(str(raw))
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _sequence_and_message(db, strategy, lead, *, sent_body: str, booking_url=None,
                          stop_reason: str | None = "replied_interested",
                          enrollment_status=None, sent_at=None, current_step: int = 2):
    """One sequence (3 steps), an enrollment and the step-2 message we sent."""
    from app.db import models as m  # noqa: PLC0415

    sequence = m.Sequence(strategy_id=strategy.id, channel=m.ChannelType.EMAIL,
                          name="cold", status=m.SequenceStatus.ACTIVE,
                          booking_url=booking_url)
    db.add(sequence)
    db.flush()
    for step_no in (1, 2, 3):
        db.add(m.SequenceStep(sequence_id=sequence.id, step_no=step_no,
                              template=f"brief {step_no}"))
    enrollment = m.SequenceEnrollment(
        sequence_id=sequence.id, lead_id=lead.id,
        status=enrollment_status or (m.EnrollmentStatus.STOPPED if stop_reason
                                     else m.EnrollmentStatus.ACTIVE),
        stop_reason=stop_reason, current_step=current_step, steps_sent=2)
    message = m.Message(sequence_id=sequence.id, lead_id=lead.id,
                        channel=m.ChannelType.EMAIL, step_no=2, template="brief 2",
                        subject="Quick question", body=sent_body,
                        status=m.MessageStatus.SENT,
                        sent_at=sent_at or (EVAL_NOW - timedelta(days=1)), thread_ref="th-1")
    db.add_all([enrollment, message])
    db.flush()
    return sequence, enrollment, message


# --- T09 reply intelligence (category + human draft) ------------------------

@adapter("reply_intelligence")
def reply_intelligence(inp: dict, client) -> dict:
    """classify_reply() then apply(), exactly as reply_tasks does; returns the
    fields stored on the reply row plus the side effects (reschedule date,
    enrollments moved to step 3)."""
    from app.db import models as m  # noqa: PLC0415
    from app.services import reply_intelligence as ri  # noqa: PLC0415

    db = fresh_session()
    try:
        _user, _product, strategy = seed_account(db)
        lead = seed_lead(db, strategy, full_name=inp.get("full_name", "Dana Whitfield"),
                         company=inp.get("company", "Northwind Studio"),
                         title=inp.get("title", "Founder"),
                         email=inp.get("from_address", "dana@northwind.example.test"))
        message = None
        enrollment = None
        if inp.get("with_sequence", True):
            _seq, enrollment, message = _sequence_and_message(
                db, strategy, lead,
                sent_body=inp.get("sent_body", "Saw your studio is hiring producers."),
                stop_reason=inp.get("stop_reason", "replied_interested"),
                current_step=int(inp.get("enrollment_step", 2)))
        reply = m.InboundReply(lead_id=lead.id, message_id=message.id if message else None,
                               channel=inp.get("channel", "email"),
                               from_address=inp.get("from_address", lead.email),
                               subject=inp.get("subject", "Re: Quick question"),
                               body=inp.get("body", ""),
                               classification=inp.get("classification"),
                               intent_label=inp.get("intent_label"))
        db.add(reply)
        db.commit()
        with use_client(client):
            result = ri.classify_reply(db, reply.id, today=_now(inp).date())
            ri.apply(db, reply, result)
        db.refresh(reply)
        return {
            "error": bool(result.get("error")),
            "category": reply.reply_category,
            "confidence": reply.category_confidence,
            "next_action": reply.ai_next_action,
            "draft_response": reply.ai_draft_response,
            "reschedule_date": _iso(reply.reschedule_date),
            "enrollments_advanced": result.get("enrollments_advanced", 0),
            "current_step": enrollment.current_step if enrollment is not None else None,
            "enrollment_status": (enrollment.status.value
                                  if enrollment is not None and enrollment.status else None),
        }
    finally:
        db.close()


# --- T10 re-engagement "not now" extraction ----------------------------------

@adapter("reengagement_notnow")
def reengagement_notnow(inp: dict, client) -> dict | None:
    """plan_for_reply() on a reply with the given Feature 1 label, as the reply
    task calls it. Returns the plan the way the API shows it (plan_out) plus
    the step brief the return touch would carry (brief_for), or None when no
    plan was made."""
    from app.db import models as m  # noqa: PLC0415
    from app.services import reengagement_memory as rm  # noqa: PLC0415
    from app.services import system_settings  # noqa: PLC0415

    db = fresh_session()
    try:
        for key, value in (inp.get("settings") or {}).items():
            system_settings.set(db, key, value)
        _user, _product, strategy = seed_account(db)
        lead = seed_lead(db, strategy, full_name=inp.get("full_name", "Dana Whitfield"),
                         email=inp.get("from_address", "dana@northwind.example.test"))
        reply = m.InboundReply(lead_id=lead.id, channel="email",
                               from_address=inp.get("from_address", lead.email),
                               subject=inp.get("subject", "Re: Quick question"),
                               body=inp.get("body", ""),
                               classification=inp.get("classification", "question"),
                               intent_label=inp.get("intent_label", "not_now"))
        db.add(reply)
        db.commit()
        with use_client(client):
            plan = rm.plan_for_reply(db, reply, now=_now(inp))
        if plan is None:
            return None
        out = rm.plan_out(db, plan)
        return {
            "reason_kind": out["reason_kind"],
            "reason_text": out["reason_text"],
            "stated_return_on": out["stated_return_on"],
            "date_from_prospect": out["date_from_prospect"],
            "due_on": _iso(plan.due_at),
            "interval_days": out["interval_days"],
            "status": out["status"],
            "brief": rm.brief_for(plan, lead),
        }
    finally:
        db.close()


# --- T11 Reply Copilot draft + auto-send decision ----------------------------

@contextmanager
def _recorded_sends():
    """Replace the Celery publish of an approved answer with a recorder (the
    narrowest seam: approve() calls reply_tasks.enqueue_send by attribute)."""
    from app.workers import reply_tasks  # noqa: PLC0415

    queued: list[str] = []
    original = reply_tasks.enqueue_send
    reply_tasks.enqueue_send = lambda message_id: queued.append(str(message_id)) or True
    try:
        yield queued
    finally:
        reply_tasks.enqueue_send = original


@adapter("reply_copilot")
def reply_copilot(inp: dict, client) -> dict:
    """draft_for_reply() -- eligibility, the draft, its guards, claim
    verification and the auto-send decision -- on a seeded conversation.

    Flags that are off by default (reply_copilot_enabled, and for auto-send
    reply_copilot_auto_send_allowed + the account opt-in) are switched on in
    the throwaway database only, as the input says."""
    from app.db import models as m  # noqa: PLC0415
    from app.services import reply_copilot as rc  # noqa: PLC0415
    from app.services import system_settings  # noqa: PLC0415

    db = fresh_session()
    try:
        system_settings.set(db, "reply_copilot_enabled", inp.get("copilot_enabled", True))
        for key, value in (inp.get("settings") or {}).items():
            system_settings.set(db, key, value)
        user, product, strategy = seed_account(db, product_name="Brightline Bookkeeping")
        if inp.get("playbook", True):
            db.add(m.ResearchStep(
                strategy_id=strategy.id, pipeline=m.PipelineKind.STRATEGY, phase=7,
                step_no=63, step_id="s7.63", name="Phase synthesis: objection playbook",
                output=inp.get("playbook_text",
                               "If they say it is too expensive: compare it with the cost "
                               "of one missed payroll deadline."),
                model="fake"))
        if inp.get("approved_claims") or inp.get("forbidden_phrases"):
            # F05 library (guardrails_enabled is off by default; on here only).
            from app.services import guardrails  # noqa: PLC0415

            system_settings.set(db, "guardrails_enabled", True)
            for text in inp.get("approved_claims") or []:
                guardrails.add_library_entry(db, user.id, guardrails.APPROVED_CLAIM, text,
                                             product_id=product.id)
            for text in inp.get("forbidden_phrases") or []:
                guardrails.add_library_entry(db, user.id, guardrails.FORBIDDEN_PHRASE, text,
                                             product_id=product.id)
        lead = seed_lead(db, strategy, full_name=inp.get("full_name", "Sara Lindqvist"),
                         company=inp.get("company", "Fernhill Design"),
                         title=inp.get("title", "Owner"),
                         email=inp.get("from_address", "sara@fernhill.example.test"),
                         status=m.LeadStatus[inp.get("lead_status", "REPLIED")])
        booking = inp.get("booking_url", "https://book.brightline.example.test/intro")
        _seq, enrollment, message = _sequence_and_message(
            db, strategy, lead, sent_body="Saw your studio took on three new clients.",
            booking_url=booking, stop_reason=inp.get("stop_reason", "replied_interested"))
        if inp.get("suppressed"):
            db.add(m.SuppressionEntry(email=lead.email.lower(), reason="unsubscribe"))
        if inp.get("other_account_secret"):
            # Another tenant's research and booking page: must never reach this prompt.
            other, _p, other_strategy = seed_account(db, product_name="Other Tenant Co")
            db.add(m.ResearchStep(
                strategy_id=other_strategy.id, pipeline=m.PipelineKind.STRATEGY, phase=7,
                step_no=63, step_id="s7.63", name="Phase synthesis: objection playbook",
                output=inp["other_account_secret"], model="fake"))
            if inp.get("other_account_claim"):
                from app.services import guardrails  # noqa: PLC0415

                guardrails.add_library_entry(db, other.id, guardrails.APPROVED_CLAIM,
                                             inp["other_account_claim"], product_id=_p.id)
        reply = m.InboundReply(lead_id=lead.id, message_id=message.id,
                               channel=inp.get("channel", "email"),
                               from_address=inp.get("from_address", lead.email),
                               subject=inp.get("subject", "Re: Quick question"),
                               body=inp.get("body", ""),
                               classification=inp.get("classification", "interested"),
                               intent_label=inp.get("intent_label"),
                               authenticity_kind=inp.get("authenticity_kind"),
                               thread_ref="th-1",
                               received_at=EVAL_NOW - timedelta(hours=2))
        db.add(reply)
        db.commit()
        if enrollment.stop_reason is not None:
            # Routing stops the enrollment right after it stores the reply.
            enrollment.stopped_at = datetime.now(UTC) + timedelta(seconds=1)
            db.commit()
        if inp.get("deployment_auto_send"):
            system_settings.set(db, rc.AUTO_SEND_SETTING, True)
        if inp.get("account_auto_send"):
            row = m.ReplyCopilotSettings(user_id=user.id, auto_send_meeting_time=True)
            db.add(row)
            db.commit()

        with _recorded_sends() as queued, use_client(client):
            result = rc.draft_for_reply(db, reply)
        draft = db.execute(
            select(m.ReplyDraft).where(m.ReplyDraft.reply_id == reply.id)).scalar_one_or_none()
        return {
            "status": result["status"],
            "reason": result["reason"],
            "auto": result["auto"],
            "sends_queued": len(queued),
            "body": draft.draft_body if draft is not None else None,
            "meeting_time_request": draft.meeting_time_request if draft is not None else None,
            "draft_status": draft.status if draft is not None else None,
            "auto_sent": draft.auto_sent if draft is not None else None,
            "claim_flags": len(draft.claim_flags_json or []) if draft is not None else 0,
        }
    finally:
        db.close()


# --- T12 follow-up brief / re-engagement brief --------------------------------

@adapter("followup_brief")
def followup_brief(inp: dict, client) -> str:
    """build_followup_brief() (mode=followup) or build_reengagement_brief()
    (mode=reengagement) for a seeded lead with its sent history; returns the
    brief that becomes the next step's template."""
    from app.db import models as m  # noqa: PLC0415
    from app.services import message_personalization as mp  # noqa: PLC0415

    db = fresh_session()
    try:
        _user, _product, strategy = seed_account(db)
        if inp.get("playbook", True):
            db.add(m.ResearchStep(
                strategy_id=strategy.id, pipeline=m.PipelineKind.STRATEGY, phase=6,
                step_no=54, step_id="s6.54", name="Phase synthesis: messaging",
                output=inp.get("playbook_text",
                               "Lead with month-end close taking too long; one question."),
                model="fake"))
        lead = seed_lead(db, strategy, full_name=inp.get("full_name", "Dana Whitfield"),
                         title=inp.get("title", "Founder"),
                         company=inp.get("company", "Northwind Studio"),
                         email=f"dana-{uuid.uuid4().hex[:6]}@northwind.example.test")
        sequence = m.Sequence(strategy_id=strategy.id, channel=m.ChannelType.EMAIL,
                              name="cold", status=m.SequenceStatus.ACTIVE)
        db.add(sequence)
        db.flush()
        for i, body in enumerate(inp.get("history") or [], start=1):
            db.add(m.Message(sequence_id=sequence.id, lead_id=lead.id,
                             channel=m.ChannelType.EMAIL, step_no=i, template=f"brief {i}",
                             subject=f"Step {i}", body=body, status=m.MessageStatus.SENT,
                             sent_at=EVAL_NOW - timedelta(days=30 - i)))
        for i, event in enumerate(inp.get("outcomes") or []):
            db.add(m.Outcome(lead_id=lead.id, strategy_id=strategy.id,
                             event=m.OutcomeEvent(event), channel="email",
                             ts=EVAL_NOW - timedelta(days=20 - i)))
        if inp.get("other_account_secret"):
            # Another tenant's lead and messages: must never reach this prompt.
            _o, _p, other_strategy = seed_account(db, product_name="Other Tenant Co")
            other_lead = seed_lead(db, other_strategy, full_name="Other Person",
                                   email="other@elsewhere.example.test")
            other_seq = m.Sequence(strategy_id=other_strategy.id, channel=m.ChannelType.EMAIL,
                                   name="cold", status=m.SequenceStatus.ACTIVE)
            db.add(other_seq)
            db.flush()
            db.add(m.Message(sequence_id=other_seq.id, lead_id=other_lead.id,
                             channel=m.ChannelType.EMAIL, step_no=1, template="brief 1",
                             subject="Other", body=inp["other_account_secret"],
                             status=m.MessageStatus.SENT, sent_at=EVAL_NOW))
        db.commit()
        build = (mp.build_reengagement_brief if inp.get("mode") == "reengagement"
                 else mp.build_followup_brief)
        with use_client(client):
            return build(db, strategy, lead, channel=inp.get("channel", "email"))
    finally:
        db.close()

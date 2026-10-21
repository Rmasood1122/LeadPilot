"""Adapters for T14, T15, T17, T18 and T19 (AI calls and meetings).

Each adapter calls the function production calls, with every get_client()
pointed at the replay (or live) client, and returns what the app keeps after
its own parsing and guards. Nothing here dials, sends or notifies:

  * T14 stops at phone_calls.prepare_call -- the script, the disclosure
    guards and the live assistant's system prompt -- which by design "does
    not dial and does not commit". voice_providers.get_clients is stubbed to
    (None, None) so no provider client is ever built (no Vapi, no TTS).
  * T15 runs the end-of-call path the webhook runs (record_end_of_call, the
    deterministic post-call check, then the analysis the Celery task runs,
    with its two retries), with event_bus.emit stubbed: push/Slack/webhook
    fan-out is not what is under test and would reach the network.
  * T17 runs meeting_prep.generate_brief with event_bus.emit stubbed (the
    "brief ready" push/Slack).
  * T18 runs meeting_followup.log_outcome + draft_followup. gmail.create_draft
    is stubbed to record the draft (the app only ever saves a DRAFT; a human
    sends it) and notification_tasks.enqueue_event is stubbed for closed_won.
  * T19 runs calendar_tasks.generate_summary_impl (the one implementation the
    endpoint and the Celery task share).

Every record is synthetic (example.test addresses, +1-555 numbers).
"""

from __future__ import annotations

import uuid
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest import mock

from evals.ai.adapters._registry import adapter
from evals.ai.context import fresh_session, seed_account, seed_lead, use_client

_NOW = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)

# Modules that do `from app.services.anthropic_client import get_client`. If one
# is imported for the FIRST time inside use_client (the code under test
# imports lazily, e.g. phone_calls.write_script -> message_personalization),
# it binds the patched lambda and keeps this case's client after use_client
# restores the others -- poisoning every later case in the process, including
# other touchpoints'. Importing them up front makes use_client patch them.
_BY_NAME_IMPORTERS = (
    "app.services.message_personalization", "app.services.meeting_ai",
    "app.services.reply_classification", "app.services.reply_intent",
    "app.services.reply_intelligence", "app.services.reply_fraud",
    "app.services.send_time", "app.services.reengagement_memory",
    "app.services.roleplay", "app.services.autopilot",
)


def _preload() -> None:
    import importlib  # noqa: PLC0415

    for name in _BY_NAME_IMPORTERS:
        importlib.import_module(name)


def _posts(inp: dict) -> list[dict]:
    return [{"text": t, "posted_at": "2026-10-01", "url": f"https://www.linkedin.example/p/{i}"}
            for i, t in enumerate(inp.get("posts") or [])]


def _news(inp: dict) -> list[dict]:
    """News items with `days_ago` turned into a published_at relative to now,
    because personalization_context only uses news from the last 30 days."""
    out = []
    now = datetime.now(timezone.utc)
    for item in inp.get("news") or []:
        item = dict(item)
        item["published_at"] = (now - timedelta(days=int(item.pop("days_ago", 3)))).isoformat()
        item.setdefault("url", "https://news.example.test/a")
        out.append(item)
    return out


def _other_account(db, other: dict | None):
    """A second account with its own lead and data, for cross-account cases.
    Returns (user, strategy, lead) or None."""
    if not other:
        return None
    user, _product, strategy = seed_account(
        db, product_name=other.get("product_name", "Quillmark Ledger"),
        description=other.get("product_description", "Ledger tooling for studios."))
    strategy.strategy_document = other.get("strategy_document")
    lead = seed_lead(db, strategy, full_name=other.get("full_name", "Osric Vantablue"),
                     company=other.get("company", "Vantablue Holdings"),
                     phone=other.get("phone", "+1 555 010 9999"),
                     email=other.get("email", "osric@vantablue.example.test"))
    return user, strategy, lead


# --- T14 AI phone call script (offline: script + guards, never the call) ---

@adapter("call_script")
def call_script(inp: dict, client) -> dict:
    from app.core.exceptions import ComplianceError  # noqa: PLC0415
    from app.db import models as m  # noqa: PLC0415
    from app.services import phone_calls  # noqa: PLC0415

    _preload()
    db = fresh_session()
    try:
        user, _product, strategy = seed_account(
            db, email=inp.get("owner_email", "maren@example.test"),
            product_name=inp.get("product_name", "Brightline Bookkeeping"))
        user.full_name = inp.get("owner_name", "Maren Holt")
        strategy.pattern_inputs_json = inp.get("icp")
        if inp.get("playbook"):
            db.add(m.ResearchStep(strategy_id=strategy.id, pipeline=m.PipelineKind.STRATEGY,
                                  phase=6, step_no=54, step_id="6.9", name="Messaging synthesis",
                                  output=inp["playbook"], model="eval"))
        other = _other_account(db, inp.get("other_account"))
        if other and inp["other_account"].get("playbook"):
            db.add(m.ResearchStep(strategy_id=other[1].id, pipeline=m.PipelineKind.STRATEGY,
                                  phase=6, step_no=54, step_id="6.9", name="Messaging synthesis",
                                  output=inp["other_account"]["playbook"], model="eval"))
        lead = seed_lead(db, strategy, full_name=inp.get("full_name", "Dana Whitfield"),
                         title=inp.get("title", "Founder"),
                         company=inp.get("company", "Northwind Studio"),
                         phone=inp.get("phone", "+1 555 010 2000"),
                         linkedin_posts_json=_posts(inp), company_news_json=_news(inp))
        db.commit()
        # Narrowest seam: no provider client is built, so nothing can dial or
        # render audio. prepare_call itself never dials.
        with mock.patch("app.integrations.voice_providers.get_clients",
                        lambda *a, **k: (None, None)), use_client(client):
            try:
                call, meta = phone_calls.prepare_call(db, strategy, lead,
                                                      inp.get("brief", "Intro call"),
                                                      owner_id=user.id)
            except ComplianceError as exc:
                return {"status": "refused", "code": getattr(exc, "compliance_code", None)}
            except ValueError as exc:
                return {"status": "failed", "error": str(exc)}
            except RuntimeError as exc:  # the replayed outage
                return {"status": "failed", "error": str(exc)}
        script = call.script_json or {}
        return {"status": "prepared",
                "first_message": script.get("first_message"),
                "voicemail": call.voicemail_text,
                "talking_points": script.get("talking_points"),
                "close": script.get("close"),
                "system_prompt": meta.get("system_prompt"),
                "dialled": False}
    finally:
        db.close()


# --- T15 call transcript analysis (consent-relevant) ----------------------

_CELERY_ATTEMPTS = 3   # workers/call_tasks.py analyze_call: max_retries=2


@adapter("call_analysis")
def call_analysis(inp: dict, client) -> dict:
    """The end-of-call path: record_end_of_call -> the post-call check the
    webhook runs (app/api/calls.py _safe_post_call_check) -> the analysis the
    Celery task runs, retried as Celery would (3 attempts, then give up).
    Returns what was decided and whether a stop request was RECORDED."""
    from app.api.calls import _safe_post_call_check  # noqa: PLC0415
    from app.db import models as m  # noqa: PLC0415
    from app.services import phone_calls  # noqa: PLC0415
    from app.workers.lead_tasks import is_suppressed  # noqa: PLC0415

    _preload()
    db = fresh_session()
    try:
        user, _product, strategy = seed_account(db)
        direction = inp.get("direction", "outbound")
        lead = None
        if inp.get("has_lead", True):
            lead = seed_lead(db, strategy, full_name=inp.get("full_name", "Dana Whitfield"),
                             company=inp.get("company", "Northwind Studio"),
                             phone=inp.get("phone", "+1 555 010 2000"),
                             phone_consent_at=_NOW)
        from_number = inp.get("from_number", "+1 555 010 3000")
        call = m.Call(lead_id=lead.id if lead else None, strategy_id=strategy.id,
                      user_id=user.id, provider="vapi", provider_call_id=uuid.uuid4().hex,
                      to_number="+15550102000" if direction == "outbound" else "+15550100001",
                      from_number=from_number if direction == "inbound" else None,
                      status="in_progress", direction=direction,
                      voicemail_text=inp.get("voicemail_text"))
        db.add(call)
        db.commit()

        attempts, failed = 0, False
        analysis: dict = {}
        with mock.patch("app.services.event_bus.emit", lambda *a, **k: {}), use_client(client):
            needs = phone_calls.record_end_of_call(
                db, call, ended_reason=inp.get("ended_reason", "customer-ended-call"),
                transcript=inp.get("transcript"), recording_url=None,
                duration_seconds=inp.get("duration_seconds", 95))
            _safe_post_call_check(db, call, None)
            if needs:
                while attempts < _CELERY_ATTEMPTS:
                    attempts += 1
                    try:
                        analysis = phone_calls.analyze(db, call)
                        break
                    except Exception:  # noqa: BLE001 -- Celery retries, then gives up
                        db.rollback()
                else:
                    failed = True
        db.refresh(call)
        number = lead.phone if lead is not None else from_number
        return {"outcome": call.outcome.value if call.outcome else None,
                "stop_request": bool(analysis.get("stop_request")),
                "stop_recorded": bool(is_suppressed(db, phone=number)),
                "analysis_failed": failed, "attempts": attempts,
                "summary": analysis.get("summary", ""),
                "objections": analysis.get("objections", []),
                "interest_signals": analysis.get("interest_signals", [])}
    finally:
        db.close()


# --- T17 meeting prep brief ------------------------------------------------

@adapter("meeting_prep_brief")
def meeting_prep_brief(inp: dict, client) -> dict:
    from app.db import models as m  # noqa: PLC0415
    from app.services import meeting_prep  # noqa: PLC0415

    _preload()
    db = fresh_session()
    try:
        user, product, strategy = seed_account(db, product_name=inp.get("product_name",
                                                                           "Brightline Bookkeeping"))
        strategy.strategy_document = inp.get("strategy_document")
        strategy.pattern_inputs_json = inp.get("icp")
        other = _other_account(db, inp.get("other_account"))
        if other:
            for body in inp["other_account"].get("replies") or []:
                db.add(m.InboundReply(lead_id=other[2].id, channel="email",
                                      from_address=other[2].email, body=body))
        lead = seed_lead(db, strategy, full_name=inp.get("full_name", "Dana Whitfield"),
                         title=inp.get("title", "Founder"),
                         company=inp.get("company", "Northwind Studio"),
                         source=inp.get("source", "manual"),
                         enrichment_json=inp.get("enrichment") or {},
                         linkedin_posts_json=_posts(inp), company_news_json=_news(inp))
        for body in inp.get("replies") or []:
            db.add(m.InboundReply(lead_id=lead.id, channel="email", from_address=lead.email,
                                  body=body, classification="interested"))
        brief = meeting_prep.upsert_brief(db, lead, user_id=user.id,
                                          source=meeting_prep.SOURCE_MANUAL,
                                          external_ref=None,
                                          meeting_start_at=_NOW + timedelta(days=1))
        db.commit()
        with mock.patch("app.services.event_bus.emit", lambda *a, **k: {}), use_client(client):
            status = meeting_prep.generate_brief(db, brief.id, now=_NOW)
        db.refresh(brief)
        return {"status": status, "error": brief.error,
                "sections": brief.sections_json or {}, "content_md": brief.content_md or ""}
    finally:
        db.close()


# --- T18 post-meeting follow-up email (saved as a Gmail DRAFT) ------------

@adapter("meeting_followup")
def meeting_followup(inp: dict, client) -> dict:
    from app.db import models as m  # noqa: PLC0415
    from app.services import meeting_followup as mf  # noqa: PLC0415

    _preload()
    db = fresh_session()
    drafts: list[dict] = []
    try:
        user, _product, strategy = seed_account(db, product_name=inp.get("product_name",
                                                                            "Brightline Bookkeeping"))
        strategy.strategy_document = inp.get("strategy_document")
        other = _other_account(db, inp.get("other_account"))
        if other and inp["other_account"].get("summary"):
            db.add(m.Meeting(host_user_id=other[0].id, lead_id=other[2].id, title="Call",
                             start_at=_NOW - timedelta(hours=1), end_at=_NOW,
                             summary=inp["other_account"]["summary"]))
        lead = seed_lead(db, strategy, full_name=inp.get("full_name", "Dana Whitfield"),
                         title=inp.get("title", "Founder"),
                         company=inp.get("company", "Northwind Studio"),
                         email=inp.get("email", "dana@northwind.example.test"))
        if inp.get("suppressed"):
            db.add(m.SuppressionEntry(email=lead.email.lower(), reason="unsubscribed_eval"))
        meeting = m.Meeting(host_user_id=user.id, lead_id=lead.id, title="Intro call",
                            start_at=_NOW - timedelta(hours=1), end_at=_NOW,
                            transcript=inp.get("transcript"), summary=inp.get("summary"))
        db.add(meeting)
        db.add(m.GmailAccount(user_id=user.id, email_address=user.email,
                              token_ciphertext="eval-not-a-token"))
        db.commit()

        def _fake_draft(_db, _account, **kwargs):
            drafts.append(kwargs)
            return {"id": f"draft-{len(drafts)}", "message": {"id": f"msg-{len(drafts)}"}}

        outcome = m.MeetingOutcomeKind(inp.get("outcome", "interested"))
        with ExitStack() as stack:
            # Narrowest seams: the draft is recorded, never created at Google;
            # the closed_won announcement is not queued.
            stack.enter_context(mock.patch("app.integrations.gmail.create_draft", _fake_draft))
            stack.enter_context(mock.patch("app.workers.notification_tasks.enqueue_event",
                                           lambda *a, **k: None))
            stack.enter_context(use_client(client))
            # link_meeting: false leaves meeting_id empty, so build_prompt
            # LOOKS UP the lead's latest summarised meeting (cross-account cases).
            row = mf.log_outcome(db, user=user, lead=lead, outcome=outcome,
                                 notes=inp.get("notes"),
                                 meeting_id=meeting.id if inp.get("link_meeting", True) else None,
                                 deal_value=inp.get("deal_value"), now=_NOW)
            row = mf.draft_followup(db, row, user=user)
        return {"draft_status": row.draft_status, "subject": row.followup_subject,
                "body": row.followup_body, "drafts_saved": len(drafts), "sent": False}
    finally:
        db.close()


# --- T19 meeting transcript summary ---------------------------------------

@adapter("meeting_summary")
def meeting_summary(inp: dict, client) -> dict:
    from app.db import models as m  # noqa: PLC0415
    # Imported BEFORE use_client: meeting_ai binds get_client by name at import
    # time, so a first import inside use_client would capture this case's
    # client and keep it after use_client restores the others.
    from app.services import meeting_ai  # noqa: F401,PLC0415
    from app.workers import calendar_tasks  # noqa: PLC0415

    _preload()
    db = fresh_session()
    try:
        user, _product, strategy = seed_account(db, product_name=inp.get("product_name",
                                                                            "Brightline Bookkeeping"))
        other = _other_account(db, inp.get("other_account"))
        if other and inp["other_account"].get("transcript"):
            db.add(m.Meeting(host_user_id=other[0].id, lead_id=other[2].id, title="Other call",
                             start_at=_NOW - timedelta(hours=2), end_at=_NOW - timedelta(hours=1),
                             transcript=inp["other_account"]["transcript"]))
        lead = seed_lead(db, strategy, full_name=inp.get("full_name", "Dana Whitfield"),
                         title=inp.get("title", "Founder"),
                         company=inp.get("company", "Northwind Studio"))
        meeting = m.Meeting(host_user_id=user.id, lead_id=lead.id,
                            title=inp.get("meeting_title", "Intro call"),
                            start_at=_NOW - timedelta(minutes=30), end_at=_NOW,
                            actual_start_at=_NOW - timedelta(minutes=28),
                            actual_end_at=_NOW - timedelta(minutes=2),
                            transcript=inp.get("transcript"), raw_notes=inp.get("notes"))
        db.add(meeting)
        db.commit()
        with use_client(client):
            status = calendar_tasks.generate_summary_impl(db, meeting.id)
        db.refresh(meeting)
        return {"status": status, "summary": meeting.summary,
                "key_points": meeting.key_points, "action_items": meeting.action_items,
                "next_steps": meeting.next_steps, "sentiment": meeting.sentiment}
    finally:
        db.close()

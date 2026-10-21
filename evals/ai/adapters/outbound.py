"""Adapters for T03 (outbound personalization), T04 (WhatsApp template
variables) and T33 (WhatsApp template drafting).

T03 and T04 produce text that is SENT, so each adapter follows the send path
in app/workers/outreach_tasks.py as far as the text that would be handed to
the provider, and stops there:

  T03 email  (_render_email_outbound, outreach_tasks.py:1114-1131)
      render_message -> claim_verification.enforce -> build_compliant_email
  T03 WA text (_render_whatsapp_outbound, outreach_tasks.py:1269-1274)
      render_message -> claim_verification.enforce
  T04        (_render_whatsapp_outbound, outreach_tasks.py:1294-1310)
      render_whatsapp_variables -> claim_verification.enforce -> preview

The outreach_tasks render functions themselves are not called: the email one
first runs personalization_context.ensure_fresh, which fetches LinkedIn posts
(a network call) when the lead has a profile URL, and both need Sequence /
Message rows that only the scheduler creates. Everything the send path does
to the TEXT after the model call is reproduced by calling the same app
functions in the same order. No send provider is touched.

claim_verification.enforce makes its own model call (the T05 extraction
pass), so a T03/T04 case whose render succeeds records TWO outputs: the
personalization output, then the claim-extraction output.

When the app raises (empty body, unfilled variable, malformed JSON, outage,
no valid template), production sends / saves nothing; the adapter returns
None so a case can assert that with `expect.none: true`.
"""

from __future__ import annotations

from types import SimpleNamespace

from evals.ai.adapters._registry import adapter
from evals.ai.context import fresh_session, seed_account, seed_lead, use_client
from evals.ai.framework import ReplayExhausted

_LEAD_KEYS = ("full_name", "title", "company", "email", "phone", "enrichment_json",
              "linkedin_posts_json", "company_news_json")


def _research(db, strategy, phase: int, step_no: int, output: str) -> None:
    from app.db import models as m  # noqa: PLC0415

    db.add(m.ResearchStep(strategy_id=strategy.id, pipeline=m.PipelineKind.STRATEGY,
                          phase=phase, step_no=step_no, step_id=f"s{phase}.{step_no:02d}",
                          name=f"phase {phase} step {step_no}", output=output,
                          model="replay"))


def _seed(db, inp: dict):
    """The case's account (strategy research, sender style) and lead, plus an
    optional SECOND account whose data must never reach this account's prompts."""
    user, _product, strategy = seed_account(db)
    if inp.get("style_profile"):
        user.style_profile_json = inp["style_profile"]
    if inp.get("playbook"):
        # phase-6 synthesis: step_no % 9 == 0 (message_personalization._playbook)
        _research(db, strategy, 6, 54, inp["playbook"])
    if inp.get("persona"):
        _research(db, strategy, 2, 10, inp["persona"])
    if inp.get("messaging"):
        _research(db, strategy, 6, 46, inp["messaging"])
    other = inp.get("other_account")
    if other:
        o_user, _o_product, o_strategy = seed_account(db, product_name="Other Tenant Co")
        o_user.style_profile_json = other.get("style_profile")
        for phase, step_no in ((6, 54), (2, 10), (6, 46)):
            _research(db, o_strategy, phase, step_no, other.get("research", ""))
        seed_lead(db, o_strategy, full_name="Other Tenant Lead", company="Other Tenant Lead Co",
                  enrichment_json={"note": other.get("research", "")})
    fields = {k: v for k, v in (inp.get("lead") or {}).items() if k in _LEAD_KEYS}
    lead = seed_lead(db, strategy, **fields)
    db.commit()
    return strategy, lead


def _produce(fn):
    """Run the production function; None when it raises (nothing is sent).
    A replay that ran out of recorded outputs is a broken CASE, not a refusal."""
    try:
        return fn()
    except ReplayExhausted:
        raise
    except Exception:  # noqa: BLE001 -- the send fails closed; graded as `none`
        return None


# --- T03 outbound email / WhatsApp free-text personalization ---------------

@adapter("outbound_personalization")
def outbound_personalization(inp: dict, client) -> dict | None:
    from app.services import claim_verification, sequence_engine  # noqa: PLC0415
    from app.services.message_personalization import render_message  # noqa: PLC0415

    channel = inp.get("channel", "email")
    db = fresh_session()
    try:
        strategy, lead = _seed(db, inp)
        # render_message reads only step_no / variant / template from the step.
        step = SimpleNamespace(step_no=int(inp.get("step_no", 1)), variant=inp.get("variant", "A"),
                               template=inp.get("brief", "Open with one specific detail about "
                                                         "their business and ask one question."))
        booking_url = inp.get("booking_url") if channel == "email" else None
        with use_client(client):
            rendered = _produce(lambda: render_message(db, strategy, lead, step, booking_url))
            if rendered is None:
                return None
            subject, body = rendered
            if channel == "email":
                checked = claim_verification.enforce(
                    db, strategy=strategy, lead=lead, message=None, channel="email",
                    fields={"subject": subject, "body": body})
            else:
                checked = claim_verification.enforce(
                    db, strategy=strategy, lead=lead, message=None, channel="whatsapp",
                    fields={"body": body})
        if channel != "email":
            return {"body": checked["body"]}
        subject, sent_body, headers, _token = sequence_engine.build_compliant_email(
            lead, checked["subject"], checked["body"])
        return {"subject": subject, "body": checked["body"], "sent_body": sent_body,
                "list_unsubscribe": headers.get("List-Unsubscribe", "")}
    finally:
        db.close()


# --- T04 WhatsApp template variable filling ---------------------------------

@adapter("whatsapp_variables")
def whatsapp_variables(inp: dict, client) -> dict | None:
    from app.services import claim_verification  # noqa: PLC0415
    from app.services.message_personalization import (  # noqa: PLC0415
        preview_whatsapp_body, render_whatsapp_variables,
    )

    db = fresh_session()
    try:
        strategy, lead = _seed(db, inp)
        body = inp.get("template_body", "")
        with use_client(client):
            values = _produce(lambda: render_whatsapp_variables(
                db, strategy, lead, template_body=body,
                variable_descriptions=inp.get("variable_descriptions") or {},
                variable_mapping=inp.get("variable_mapping")))
            if values is None:
                return None
            if values:
                checked = claim_verification.enforce(
                    db, strategy=strategy, lead=lead, message=None, channel="whatsapp",
                    fields={f"variable:{n}": v for n, v in values.items()})
                values = {n: checked[f"variable:{n}"] for n in values}
        return {"values": values, "preview": preview_whatsapp_body(body, values)}
    finally:
        db.close()


# --- T33 WhatsApp template drafting -----------------------------------------

@adapter("whatsapp_template_drafts")
def whatsapp_template_drafts(inp: dict, client) -> dict | None:
    """The drafts the app saved (never submitted to Meta), by name."""
    from app.services import whatsapp_templates as wt  # noqa: PLC0415

    db = fresh_session()
    try:
        strategy, _lead = _seed(db, inp)
        with use_client(client):
            rows = _produce(lambda: wt.generate_drafts(db, strategy))
        if rows is None:
            return None
        saved = [wt.serialize(r) for r in rows]
        return {
            "count": len(saved),
            "statuses": sorted({t["status"] for t in saved}),
            "by_name": {t["name"]: t["body"] for t in saved},
            "categories": {t["name"]: t["category"] for t in saved},
            "variables": {t["name"]: t["variable_descriptions"] for t in saved},
        }
    finally:
        db.close()

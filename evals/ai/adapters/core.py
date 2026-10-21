"""Adapters for T05-T08 (claim verification, reply routing), T23 and T35."""

from __future__ import annotations

from evals.ai.adapters._registry import adapter
from evals.ai.context import fresh_session, seed_account, seed_lead, use_client


# --- T06 inbound reply routing (consent-critical) -------------------------

@adapter("reply_classification")
def reply_classification(inp: dict, client) -> str:
    from app.services import reply_classification as rc  # noqa: PLC0415

    with use_client(client):
        return rc.classify_reply(inp.get("from_address", "prospect@example.test"),
                                 inp.get("subject"), inp.get("body", ""), session=None)


# --- T07 automated-reply detector ------------------------------------------

@adapter("automated_reply")
def automated_reply(inp: dict, client) -> dict:
    from app.services import reply_fraud  # noqa: PLC0415

    with use_client(client):
        automated, reason = reply_fraud.is_automated(
            inp.get("from_address"), inp.get("subject"), inp.get("body", ""))
    return {"automated": automated, "reason": reason}


# --- T08 reply intent label --------------------------------------------------

@adapter("reply_intent")
def reply_intent(inp: dict, client) -> dict | None:
    from app.db import models as m  # noqa: PLC0415
    from app.services import reply_intent as ri  # noqa: PLC0415

    db = fresh_session()
    try:
        _user, _product, strategy = seed_account(db)
        lead = seed_lead(db, strategy)
        reply = m.InboundReply(lead_id=lead.id, channel="email",
                               from_address=inp.get("from_address", lead.email),
                               subject=inp.get("subject"), body=inp.get("body", ""),
                               classification=inp.get("classification"))
        db.add(reply)
        db.commit()
        with use_client(client):
            result = ri.classify(db, reply.id)
        if not result:
            return None
        return {k: result.get(k) for k in ("label", "confidence", "reason")}
    finally:
        db.close()


# --- T05 claim extraction (model pass of claim verification) -------------

@adapter("claim_extraction")
def claim_extraction(inp: dict, client) -> dict:
    from app.services import claim_verification as cv  # noqa: PLC0415

    db = fresh_session()
    try:
        with use_client(client):
            return cv._model_claims(db, [inp.get("message", "")])
    finally:
        db.close()


# --- T23 displacement-monitor Day 0 DM -----------------------------------

@adapter("displacement_dm")
def displacement_dm(inp: dict, client) -> str | None:
    from types import SimpleNamespace  # noqa: PLC0415

    from app.services import displacement_monitor as dm  # noqa: PLC0415

    lead = SimpleNamespace(id="lead-eval", full_name=inp.get("full_name", "Sara Khan"),
                           title=inp.get("title", "Founder"),
                           company=inp.get("company", "Lumen Creative"))
    with use_client(client):
        return dm.generate_displacement_dm(lead, inp.get("post", ""),
                                           list(inp.get("matched") or []))


# --- T35 SEO website page builder -----------------------------------------

@adapter("website_page")
def website_page(inp: dict, client) -> dict:
    from app.services import website_builder as wb  # noqa: PLC0415

    # The app raises (ValueError on an unusable reply, the gateway's own
    # errors otherwise) so the worker leaves the stored page untouched; the
    # exception's type is that outcome, so it is returned for grading.
    try:
        with use_client(client):
            return wb.generate_page_html(
                inp.get("page_type", "blog"), inp.get("title", "Agency pipelines"),
                inp.get("target_keyword", "agency pipeline"), list(inp.get("secondary") or []),
                inp.get("brief", "A page about keeping an agency's pipeline full every month."),
                list(inp.get("existing_pages") or []), slug=inp.get("slug", "page"),
                brand_name=inp.get("brand_name"))
    except Exception as exc:  # noqa: BLE001 -- graded, see above
        return {"raised": type(exc).__name__}


# --- T05 claim verification: model extraction + the rules that act on it ---

@adapter("claim_verification")
def claim_verification(inp: dict, client) -> dict:
    """The outreach text after claim verification, as a send would get it:
    `text` with unsupported claims about the prospect removed or rewritten,
    and the decisions taken."""
    from app.services import claim_verification as cv  # noqa: PLC0415

    db = fresh_session()
    try:
        _user, _product, strategy = seed_account(db)
        lead = seed_lead(db, strategy, full_name=inp.get("full_name", "Dana Whitfield"),
                         title=inp.get("title", "Founder"),
                         company=inp.get("company", "Northwind Studio"),
                         enrichment_json=inp.get("enrichment") or {},
                         linkedin_posts_json=inp.get("posts") or [])
        db.commit()
        text = inp.get("message", "")
        with use_client(client):
            claims = cv._model_claims(db, [text])
        out, decisions = cv.verify_text(text, field_name="body", lead=lead,
                                        evidence=cv.build_evidence(lead), sender_vocab="",
                                        model_claims=claims)
        return {"text": out, "decisions": [{"claim": d.claim_text, "verdict": d.verdict,
                                            "category": d.category} for d in decisions]}
    finally:
        db.close()

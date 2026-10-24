"""Adapters for the outreach-copy touchpoints: T13 (LinkedIn connect note /
message / InMail), T24 (personal video script), T25 (network message drafts,
LinkedIn connections and email contacts) and T26 (style profile and founder
voice profile).

Each adapter calls the function production calls, with get_client() pointed
at the eval client, and returns what the app hands on after its own parsing
and guards. Nothing is sent: T13 stops where the send path would hand the
checked text to the channel, T25 stops at the user's save.

When the app raises (an outage, an empty or malformed model answer, a
refused draft), the adapter returns {"error": <exception class name>} plus
the HTTP status the app attached, so a case can assert the app failed
closed and HOW. Only the app call itself is wrapped; a seeding error is an
adapter bug and still crashes the case.

CROSS-ACCOUNT. An input `other_account` seeds a second, unrelated account
(its own user, product, strategy, style profile, voice profile, research
playbook and records) in the same database before the call, so prompt-level
graders can prove nothing of it reaches the first account's prompts.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from evals.ai.adapters._registry import adapter
from evals.ai.context import fresh_session, seed_account, seed_lead, use_client


def _failed(exc: Exception) -> dict:
    out = {"error": type(exc).__name__}
    status = getattr(exc, "status", None)
    if status is not None:
        out["status"] = status
    return out


def _playbook_row(db, strategy, text: str):
    """A phase-6 synthesis step: what message_personalization._playbook reads."""
    from app.db import models as m  # noqa: PLC0415

    db.add(m.ResearchStep(strategy_id=strategy.id, pipeline=m.PipelineKind.STRATEGY,
                          phase=6, step_no=54, step_id="s6.09", name="Messaging synthesis",
                          output=text, model="synthetic"))


def _voice_row(db, product, data: dict):
    from app.db import models as m  # noqa: PLC0415

    db.add(m.VoiceProfile(product_id=product.id,
                          style_dimensions_json=data.get("dimensions") or {},
                          sample_phrases=list(data.get("phrases") or []),
                          raw_posts_json=list(data.get("posts") or []),
                          post_count=len(data.get("posts") or [])))


def _seed_other_account(db, other: dict | None):
    """The second account of a cross-account case, with everything that could
    leak: style profile, voice profile, playbook, a lead, connections and
    contacts. Returns (user, product, strategy) or None."""
    if not other:
        return None
    from app.db import models as m  # noqa: PLC0415

    user, product, strategy = seed_account(
        db, email=other.get("email", "owner@other-sender.example.test"),
        product_name=other.get("product_name", "Quayside Payroll"),
        description=other.get("product_description", "Payroll for marine suppliers."))
    user.style_profile_json = other.get("style")
    user.style_samples_json = other.get("samples")
    if other.get("playbook"):
        _playbook_row(db, strategy, other["playbook"])
    if other.get("voice"):
        _voice_row(db, product, other["voice"])
    lead = other.get("lead")
    if lead:
        seed_lead(db, strategy, **lead)
    if other.get("connection"):
        db.add(m.LinkedInConnection(user_id=user.id, dedupe_key="other-1",
                                    **other["connection"]))
    if other.get("contact"):
        c = other["contact"]
        db.add(m.EmailContact(user_id=user.id, email=c["email"],
                              domain=c["email"].rsplit("@", 1)[1],
                              full_name=c.get("full_name"), company=c.get("company"),
                              title=c.get("title"), sent_to_count=3, received_from_count=3,
                              two_way=True, last_seen=datetime.now(timezone.utc) - timedelta(days=20),
                              source_counts_json={}))
    db.flush()
    return user, product, strategy


def _lead_fields(inp: dict) -> dict:
    fields = {k: inp[k] for k in ("full_name", "title", "company") if k in inp}
    if "posts" in inp:
        fields["linkedin_posts_json"] = inp["posts"]
    if "news" in inp:
        fields["company_news_json"] = _fresh_news(inp["news"])
    if "enrichment" in inp:
        fields["enrichment_json"] = inp["enrichment"]
    return fields


def _fresh_news(news: list | None) -> list | None:
    """Stamp synthetic news items `days_ago` relative to now, so the 30-day
    window in personalization_context does not make a case rot with time."""
    if not news:
        return news
    now = datetime.now(timezone.utc)
    out = []
    for item in news:
        item = dict(item)
        if "days_ago" in item:
            item["published_at"] = (now - timedelta(days=int(item.pop("days_ago")))).isoformat()
        out.append(item)
    return out


# --- T13 LinkedIn outreach copy (SEND via the LinkedIn sequence) ----------

@adapter("linkedin_outreach")
def linkedin_outreach(inp: dict, client) -> dict:
    """outreach_tasks._render_linkedin_outbound minus the channel call:
    linkedin_outreach.render() (model call, length trim) then
    claim_verification.enforce(channel="linkedin") on the body (and the
    InMail subject), exactly as the send path does. Returns the text and
    subject that would be handed to Unipile."""
    from app.services import claim_verification, linkedin_outreach as lo  # noqa: PLC0415

    db = fresh_session()
    try:
        user, _product, strategy = seed_account(db, email="owner@sender-one.example.test")
        user.style_profile_json = inp.get("style")
        if inp.get("playbook"):
            _playbook_row(db, strategy, inp["playbook"])
        _seed_other_account(db, inp.get("other_account"))
        lead = seed_lead(db, strategy, **_lead_fields(inp))
        db.commit()
        step = SimpleNamespace(template=inp.get("brief", "Introduce yourself and give one reason to connect."))
        with use_client(client):
            try:
                rendered = lo.render(db, strategy, lead, step, inp.get("action", "connect"))
                checked_fields = {"body": rendered["text"]}
                if rendered.get("subject"):
                    checked_fields["subject"] = rendered["subject"]
                checked = claim_verification.enforce(
                    db, strategy=strategy, lead=lead, message=None, channel="linkedin",
                    fields=checked_fields)
            except Exception as exc:  # noqa: BLE001 -- the app failing closed is the result
                return _failed(exc)
        out = {"text": checked["body"]}
        if checked.get("subject"):
            out["subject"] = checked["subject"]
        return out
    finally:
        db.close()


# --- T24 personal video (Loom) script --------------------------------------

@adapter("loom_script")
def loom_script(inp: dict, client) -> dict | None:
    """mode "suggest" (default): loom_video.suggest(), the automatic path after
    scoring -- returns the stored loom_video_json, or None when no script was
    stored (below threshold, already handled, or the writer failed; suggest
    never raises). mode "on_demand": loom_video.write_script(), what the API
    route calls -- its exceptions become the 502 the route answers."""
    from app.services import loom_video  # noqa: PLC0415

    db = fresh_session()
    try:
        _user, _product, strategy = seed_account(db, email="owner@sender-one.example.test")
        _seed_other_account(db, inp.get("other_account"))
        fields = _lead_fields(inp)
        fields["ai_booking_likelihood"] = inp.get("likelihood", 90)
        if "loom_state" in inp:
            fields["loom_video_json"] = inp["loom_state"]
        lead = seed_lead(db, strategy, **fields)
        db.commit()
        with use_client(client):
            if inp.get("mode") == "on_demand":
                try:
                    return loom_video.write_script(db, lead)
                except Exception as exc:  # noqa: BLE001
                    return _failed(exc)
            stored = loom_video.suggest(db, lead)
        if not stored:
            return None
        state = loom_video.state(lead)
        return {k: state.get(k) for k in ("status", "title", "script", "on_screen")}
    finally:
        db.close()


# --- T25 network message drafts -------------------------------------------

def _network_linkedin(db, inp: dict, user, product) -> dict:
    from app.db import models as m  # noqa: PLC0415
    from app.services import network_messages as nm  # noqa: PLC0415

    conn = m.LinkedInConnection(user_id=user.id, dedupe_key="eval-1",
                                full_name=inp.get("full_name", "Ines Calloway"),
                                position=inp.get("title"), company=inp.get("company"),
                                profile_url="https://www.linkedin.com/in/ines-calloway-eval/")
    db.add(conn)
    db.flush()
    if inp.get("match_reasons") is not None:
        db.add(m.LinkedInConnectionMatch(user_id=user.id, connection_id=conn.id,
                                         product_id=product.id, score=70, segment="fit",
                                         reasons_json=list(inp["match_reasons"]),
                                         analyzed_at=datetime.now(timezone.utc)))
    db.commit()
    try:
        msg = nm.draft(db, user, conn.id, product.id)
        draft_text = msg.text
        # The user approves the draft unchanged: the only check before send.
        saved = nm.save(db, user, msg.id, msg.text)
    except nm.MessageError as exc:
        return _failed(exc)
    return {"text": draft_text, "status": saved.status}


def _network_email(db, inp: dict, user, product) -> dict:
    from app.db import models as m  # noqa: PLC0415
    from app.services import email_network_messages as enm  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    email = inp.get("email", "ines@harbourline.example.test")
    contact = m.EmailContact(
        user_id=user.id, email=email, domain=email.rsplit("@", 1)[1],
        full_name=inp.get("full_name", "Ines Calloway"), title=inp.get("title"),
        company=inp.get("company"), sent_to_count=inp.get("sent", 4),
        received_from_count=inp.get("received", 4), two_way=inp.get("two_way", True),
        last_seen=(now - timedelta(days=int(inp["last_seen_days"])))
        if inp.get("last_seen_days") is not None else None,
        source_counts_json={})
    db.add(contact)
    db.flush()
    if inp.get("match_reasons") is not None:
        db.add(m.EmailContactMatch(user_id=user.id, contact_id=contact.id,
                                   product_id=product.id, score=70, segment="fit",
                                   reasons_json=list(inp["match_reasons"]),
                                   analyzed_at=now))
    if inp.get("suppressed"):
        db.add(m.SuppressionEntry(email=email, reason="unsubscribed"))
    db.commit()
    try:
        msg = enm.draft(db, user, contact.id, product.id)
    except enm.MessageError as exc:
        return _failed(exc)
    out = {"subject": msg.subject, "body": msg.body}
    try:
        # The user approves the draft unchanged: save() is where the
        # relationship over-claim check refuses wording the counts do not support.
        out["status"] = enm.save(db, user, msg.id, msg.subject, msg.body).status
    except enm.MessageError as exc:
        out.update({"status": "refused", "save_status": exc.status})
    return out


@adapter("network_message")
def network_message(inp: dict, client) -> dict:
    """channel "linkedin": network_messages.draft() then save() unchanged.
    channel "email": email_network_messages.draft() then save() unchanged.
    Returns the draft and whether saving it (the step before any send) was
    accepted; MessageError becomes {"error", "status"}."""
    db = fresh_session()
    try:
        user, product, _strategy = seed_account(
            db, email="owner@sender-one.example.test",
            product_name=inp.get("product_name", "Brightline Bookkeeping"),
            description=inp.get("product_description",
                                "Monthly bookkeeping and payroll for small UK agencies."))
        user.style_profile_json = inp.get("style")
        _seed_other_account(db, inp.get("other_account"))
        db.commit()
        with use_client(client):
            if inp.get("channel", "linkedin") == "email":
                return _network_email(db, inp, user, product)
            return _network_linkedin(db, inp, user, product)
    finally:
        db.close()


# --- T26 style profile and founder voice profile ----------------------------

@adapter("style_voice_profile")
def style_voice_profile(inp: dict, client) -> dict:
    """mode "style": style_profile.extract() on the user's samples; returns the
    stored profile and `outreach_suffix`, the text every outbound writer of
    that account then gets in its SYSTEM prompt (suffix_for_strategy).
    mode "voice": voice_profiler.extract_voice_profile() on the founder's
    posts; returns the dimensions, phrases and `outreach_brief`, what
    brief_for_strategy appends to a step brief.
    With `other_account`, `other_suffix` / `other_brief` is what the OTHER
    account's outreach gets after this extraction (must be untouched)."""
    from app.services import style_profile, voice_profiler  # noqa: PLC0415

    db = fresh_session()
    try:
        user, product, strategy = seed_account(db, email="owner@sender-one.example.test")
        if inp.get("existing_style"):
            user.style_profile_json = inp["existing_style"]
        if inp.get("existing_voice"):
            _voice_row(db, product, inp["existing_voice"])
        other = _seed_other_account(db, inp.get("other_account"))
        db.commit()
        mode = inp.get("mode", "style")
        out: dict = {}
        with use_client(client):
            try:
                if mode == "voice":
                    profile = voice_profiler.extract_voice_profile(db, product.id,
                                                                   inp.get("samples") or [])
                    out = {"dimensions": profile.style_dimensions_json,
                           "phrases": profile.sample_phrases,
                           "outreach_brief": voice_profiler.brief_for_strategy(
                               db, strategy, "STEP BRIEF.")[0]}
                else:
                    out = {"profile": style_profile.extract(db, user, inp.get("samples") or []),
                           "outreach_suffix": style_profile.suffix_for_strategy(db, strategy)}
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                out = _failed(exc)
                # What outreach gets after a failed extraction: the previous
                # profile, never a half-written one.
                if mode == "voice":
                    out["outreach_brief"] = voice_profiler.brief_for_strategy(
                        db, strategy, "STEP BRIEF.")[0]
                else:
                    out["outreach_suffix"] = style_profile.suffix_for_strategy(db, strategy)
        if other is not None:
            _ou, _op, other_strategy = other
            out["other_suffix"] = style_profile.suffix_for_strategy(db, other_strategy)
            out["other_brief"] = voice_profiler.brief_for_strategy(
                db, other_strategy, "STEP BRIEF.")[0]
        return out
    finally:
        db.close()

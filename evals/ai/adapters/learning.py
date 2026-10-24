"""Adapters for the learning-loop touchpoints: T20 (strategy mutation), T27
(F-P-T-A and booking-likelihood scoring), T28 (ICP criteria + tactic
classification) and T29 (past-client pattern extraction).

Each adapter seeds a fresh in-memory database, calls the SAME function
production calls with every get_client() pointed at the replay client, and
returns what the app persisted or returned after its own parsing, clamps and
guards. Two-account cases seed a second owner ("other_account") in the same
database so prompt_forbidden can prove that owner's rows never reach the
first owner's prompt. All data is synthetic.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from evals.ai.adapters._registry import adapter
from evals.ai.context import fresh_session, seed_account, seed_lead, use_client

# Scoring and outcome windows depend on "now"; a fixed clock keeps every
# case deterministic.
NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _uid(value) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"eval:{value}")


# ---------------------------------------------------------------------------
# T20 strategy mutation
# ---------------------------------------------------------------------------

def _seed_campaign(db, strategy, spec: dict) -> None:
    """Sequence briefs, sent messages and open events for one strategy."""
    from app.db import models as m  # noqa: PLC0415

    strategy.strategy_document = spec.get("strategy_document", "")
    strategy.pattern_inputs_json = spec.get("icp")
    strategy.campaign_state = "active"
    seq = m.Sequence(strategy_id=strategy.id, channel=m.ChannelType.EMAIL,
                     name=spec.get("sequence_name", "Main sequence"))
    db.add(seq)
    db.flush()
    for i, brief in enumerate(spec.get("briefs") or [], start=1):
        db.add(m.SequenceStep(sequence_id=seq.id, step_no=i, template=brief))
    sent = int(spec.get("sent", 0))
    opened = int(spec.get("opened", 0))
    if sent:
        lead = seed_lead(db, strategy, full_name=spec.get("lead_name", "Robin Ashby"),
                         email=f"robin-{uuid.uuid4().hex[:6]}@example.test")
        for i in range(sent):
            db.add(m.Message(sequence_id=seq.id, lead_id=lead.id, channel=m.ChannelType.EMAIL,
                             step_no=1, template="brief", status=m.MessageStatus.SENT,
                             sent_at=NOW - timedelta(days=int(spec.get("days", 10)))))
        for _ in range(opened):
            db.add(m.Outcome(lead_id=lead.id, strategy_id=strategy.id,
                             event=m.OutcomeEvent.OPENED, ts=NOW - timedelta(days=2)))
    db.flush()


@adapter("strategy_mutation")
def strategy_mutation(inp: dict, client) -> dict | None:
    """The PROPOSED StrategyVersion mutate() persisted, read back from the
    database, or None when it persisted nothing (mutate raised: the sweep
    logs and moves on, the API answers 502)."""
    from sqlalchemy import func, select  # noqa: PLC0415

    from app.db import models as m  # noqa: PLC0415
    from app.services import strategy_mutation as sm  # noqa: PLC0415

    db = fresh_session()
    try:
        _user, _product, strategy = seed_account(db)
        _seed_campaign(db, strategy, inp)
        other = None
        if inp.get("other_account"):
            _u2, _p2, other = seed_account(db, product_name="Harbour Ledger Co",
                                           description="Fractional finance for clinics.")
            _seed_campaign(db, other, inp["other_account"])
        db.commit()
        with use_client(client):
            try:
                sm.mutate(db, strategy, trigger=inp.get("trigger", "manual"), now=NOW)
            except Exception:  # noqa: BLE001 -- the caller's behaviour: roll back
                db.rollback()
        version = db.execute(
            select(m.StrategyVersion).where(m.StrategyVersion.strategy_id == strategy.id,
                                            m.StrategyVersion.status == "proposed")
        ).scalars().first()
        if version is None:
            return None
        other_versions = 0
        if other is not None:
            other_versions = db.execute(
                select(func.count(m.StrategyVersion.id))
                .where(m.StrategyVersion.strategy_id == other.id)
            ).scalar_one()
        return {"status": version.status, "version_no": version.version_no,
                "trigger": version.trigger, "change_summary": version.change_summary,
                "changes": version.changes_json, "document": version.document,
                "other_account_versions": other_versions}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# T27 F-P-T-A scoring and booking-likelihood scoring
# ---------------------------------------------------------------------------

def _seed_scoring_account(db, spec: dict, *, product_name: str):
    from app.db import models as m  # noqa: PLC0415

    user, product, strategy = seed_account(db, product_name=product_name,
                                           pattern_key=spec.get("pattern_key"))
    strategy.pattern_inputs_json = spec.get("icp")
    for rate in spec.get("playbook") or []:
        db.add(m.PlaybookScore(user_id=user.id, pattern_key=spec.get("pattern_key"),
                               booking_rate=rate, is_reliable=True, sample_size=200))
    leads = {}
    for raw in spec.get("leads") or []:
        fields = {"full_name": raw.get("full_name", "Dana Whitfield"),
                  "title": raw.get("title"), "company": raw.get("company", "Northwind Studio"),
                  "email": raw.get("email", f"lead-{uuid.uuid4().hex[:6]}@example.test"),
                  "status": m.LeadStatus(raw.get("status", "verified")),
                  "enrichment_json": raw.get("enrichment") or {},
                  "linkedin_posts_json": raw.get("posts") or [],
                  "company_news_json": raw.get("news") or [],
                  "linkedin_url": raw.get("linkedin_url"),
                  "source": raw.get("source", "manual")}
        if raw.get("id"):
            fields["id"] = _uid(raw["id"])
        leads[raw.get("key", "lead")] = seed_lead(db, strategy, **fields)
    db.flush()
    return strategy, leads


def _fpta_out(lead) -> dict:
    reasons = lead.fpta_reasons_json if isinstance(lead.fpta_reasons_json, dict) else {}
    return {"overall": lead.fpta_overall, "fit": lead.fpta_fit, "problem": lead.fpta_problem,
            "timing": lead.fpta_timing, "access": lead.fpta_access, "method": lead.fpta_method,
            "reasons": {k: (v or {}).get("reason") for k, v in reasons.items()},
            "baselines": {k: (v or {}).get("baseline") for k, v in reasons.items()},
            "signals": {k: (v or {}).get("signals") for k, v in reasons.items()}}


def _booking_out(lead) -> dict:
    factors = lead.ai_score_factors if isinstance(lead.ai_score_factors, dict) else {}
    return {"score": lead.ai_booking_likelihood, "reason": lead.ai_score_reason,
            "method": factors.get("method"), "baseline": factors.get("heuristic"),
            "industry_match": factors.get("industry_match"),
            "playbook_booking_rate": factors.get("playbook_booking_rate")}


@adapter("lead_scoring")
def lead_scoring(inp: dict, client) -> dict:
    """Per lead key, the scores the app persisted on the Lead row.
    `scorer: fpta` runs fpta_scoring.score_leads (F-P-T-A); `scorer:
    booking` runs lead_scoring.score_leads (ai_booking_likelihood)."""
    from app.services import fpta_scoring  # noqa: PLC0415
    from app.services import lead_scoring as ls  # noqa: PLC0415

    db = fresh_session()
    try:
        strategy, leads = _seed_scoring_account(db, inp, product_name="Brightline Bookkeeping")
        other_leads = {}
        if inp.get("other_account"):
            _s2, other_leads = _seed_scoring_account(db, inp["other_account"],
                                                     product_name="Harbour Ledger Co")
        db.commit()
        scorer = fpta_scoring if inp.get("scorer", "fpta") == "fpta" else ls
        with use_client(client):
            scorer.score_leads(db, strategy, list(leads.values()), now=NOW)
        out = {}
        for key, lead in leads.items():
            db.refresh(lead)
            out[key] = _fpta_out(lead) if scorer is fpta_scoring else _booking_out(lead)
        for key, lead in other_leads.items():
            db.refresh(lead)
            out[f"other_{key}"] = {"fpta_scored": lead.fpta_scored_at is not None,
                                   "booking_scored": lead.ai_scored_at is not None}
        return out
    finally:
        db.close()


# ---------------------------------------------------------------------------
# T28 ICP criteria extraction + tactic classification
# ---------------------------------------------------------------------------

def _seed_research(db, strategy, steps: list[dict]) -> None:
    from app.db import models as m  # noqa: PLC0415

    for i, step in enumerate(steps, start=1):
        db.add(m.ResearchStep(strategy_id=strategy.id, pipeline=m.PipelineKind.STRATEGY,
                              phase=int(step["phase"]), step_no=int(step.get("step_no", i)),
                              step_id=f"s{step['phase']}.{i:02d}",
                              name=step.get("name", f"Step {i}"), output=step["output"],
                              model="replay"))
    db.flush()


@adapter("icp_extraction")
def icp_extraction(inp: dict, client) -> dict | None:
    """mode criteria:   extract_icp_criteria over phase 2/3 research (lead
                        sourcing; leads.py:115). None when it raised.
    mode quickstart:    quickstart.icp_research_text + criteria_from_research,
                        the Quickstart path (quickstart.py:281-286). None when
                        it raised (the run fails).
    mode tactic:        extract_tactic_profile over phase 5/8 research.
    mode pattern:       extract_icp_criteria + ensure_pattern_key, as
                        leads.py:115-120 runs them, then the persisted
                        pattern_inputs_json and what the lead scorers read
                        from it for a lead in a matching industry."""
    from app.services import icp_extraction as ie  # noqa: PLC0415

    mode = inp.get("mode", "criteria")
    if mode == "quickstart":
        from app.services import quickstart  # noqa: PLC0415

        research = quickstart.icp_research_text(inp.get("offer", ""), inp.get("url", ""),
                                                inp.get("page_title", ""),
                                                inp.get("page_text", ""))
        with use_client(client):
            try:
                return ie.criteria_from_research(research)
            except Exception:  # noqa: BLE001 -- the run fails, no criteria
                return None

    db = fresh_session()
    try:
        _user, _product, strategy = seed_account(db)
        _seed_research(db, strategy, inp.get("research") or [])
        if inp.get("other_account"):
            _u2, _p2, other = seed_account(db, product_name="Harbour Ledger Co")
            _seed_research(db, other, inp["other_account"].get("research") or [])
        db.commit()
        with use_client(client):
            if mode == "tactic":
                return ie.extract_tactic_profile(db, strategy)
            try:
                criteria = ie.extract_icp_criteria(db, strategy)
            except Exception:  # noqa: BLE001 -- the caller gets an error, no criteria
                return None
            if mode == "criteria":
                return criteria
            ie.ensure_pattern_key(db, strategy, criteria)
        from app.services import fpta_scoring, lead_scoring  # noqa: PLC0415

        db.refresh(strategy)
        lead = seed_lead(db, strategy, title="Practice Owner",
                         enrichment_json={"organization": {
                             "industry": inp.get("lead_industry", "accounting")}})
        # Score through the real scorers (heuristic path, no model call), so
        # the case measures what they read from the stored column.
        lead_scoring.score_leads(db, strategy, [lead], now=NOW, use_model=False)
        fpta_scoring.score_leads(db, strategy, [lead], now=NOW, use_model=False)
        db.refresh(lead)
        return {"pattern_key": strategy.pattern_key,
                "pattern_inputs": strategy.pattern_inputs_json or {},
                "industry_match": _booking_out(lead)["industry_match"],
                "fit_signals": _fpta_out(lead)["signals"].get("fit")}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# T29 past-client pattern extraction (intake)
# ---------------------------------------------------------------------------

@adapter("pattern_extraction")
def pattern_extraction(inp: dict, client) -> dict:
    """The intake route (api/products.add_past_clients) called as the
    request would call it, then the stored extracted_patterns_json read back.
    One client -> its patterns; several -> {"client_1": ..., ...}. A refused
    request -> {"status": <http status>, "past_clients_on_target": n}."""
    from fastapi import HTTPException  # noqa: PLC0415
    from sqlalchemy import func, select  # noqa: PLC0415

    from app.api import products as api  # noqa: PLC0415
    from app.api.schemas import PastClientsCreate  # noqa: PLC0415
    from app.db import models as m  # noqa: PLC0415

    db = fresh_session()
    try:
        user, product, _strategy = seed_account(db)
        target = product
        other = inp.get("other_account")
        if other:
            _u2, other_product, _s2 = seed_account(db, product_name="Harbour Ledger Co")
            for c in other.get("clients") or []:
                db.add(m.PastClient(product_id=other_product.id, details=c["details"],
                                    acquisition_story=c["acquisition_story"],
                                    extracted_patterns_json=c.get("patterns")))
            if inp.get("post_to_other_account"):
                target = other_product
        db.commit()
        body = PastClientsCreate(clients=inp.get("clients") or [])
        with use_client(client):
            try:
                created = api.add_past_clients(target.id, body, db=db, current_user=user)
            except HTTPException as exc:
                count = db.execute(select(func.count(m.PastClient.id))
                                   .where(m.PastClient.product_id == target.id)).scalar_one()
                return {"status": exc.status_code, "past_clients_on_target": count}
        ids = [c.id for c in created]
        db.expire_all()
        rows = [db.get(m.PastClient, i).extracted_patterns_json for i in ids]
        if len(rows) == 1:
            return rows[0]
        return {f"client_{i}": r for i, r in enumerate(rows, start=1)}
    finally:
        db.close()

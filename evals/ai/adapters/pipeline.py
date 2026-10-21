"""Adapters for T01 (research pipeline step) and T02 (consensus judge).

Both drive app.pipeline.engine.run_step -- the function the Celery pipeline
calls for every step -- on a strategy seeded in a fresh in-memory database,
with every get_client() pointed at the replay (or live) client. What they
return is what the app persisted after its own guards: the research_steps
row, and for T02 the stored model outputs, uncertain zones and the
strategy's consensus_status.

T02's second model is OpenAI, not get_client(). It is stubbed at the
narrowest seam that keeps the app's own OpenAI code under test:
`app.integrations.openai_client.get_openai_client` is swapped for one that
returns the REAL OpenAIClient, built on an httpx.MockTransport that answers
from the case's `gpt` input (no network, no sleep between retries). So the
client's own guards (HTTP errors, retries, truncation, empty answer) run
unchanged. The OpenAI prompt is identical to Claude's step prompt, so the
prompt-level graders already see it through Claude's recorded call.
"""

from __future__ import annotations

from contextlib import contextmanager

from evals.ai.adapters._registry import adapter
from evals.ai.context import fresh_session, seed_account, use_client


def _spec(pipeline, step_no: int):
    from app.pipeline.registry import get_steps  # noqa: PLC0415

    for spec in get_steps(pipeline):
        if spec.step_no == step_no:
            return spec
    raise ValueError(f"no step {step_no} in {pipeline}")


def _pipeline(name: str | None):
    from app.db import models as m  # noqa: PLC0415

    return m.PipelineKind.GTM if (name or "strategy") == "gtm" else m.PipelineKind.STRATEGY


def _seed_research(db, strategy, rows: list[dict]) -> None:
    """Earlier research_steps rows: [{pipeline?, step_no, output}]."""
    from app.config import settings  # noqa: PLC0415
    from app.db import models as m  # noqa: PLC0415

    for row in rows or []:
        spec = _spec(_pipeline(row.get("pipeline")), int(row["step_no"]))
        db.add(m.ResearchStep(strategy_id=strategy.id, pipeline=spec.pipeline, phase=spec.phase,
                              step_no=spec.step_no, step_id=spec.id, name=spec.name,
                              inputs_json={}, output=row["output"],
                              model=settings.anthropic_model))


def _seed_playbook(db, user, rows: list[dict]) -> None:
    from app.db import models as m  # noqa: PLC0415

    for row in rows or []:
        db.add(m.PlaybookScore(user_id=user.id, pattern_key=row["pattern_key"],
                               variant=row.get("variant", "A"),
                               reply_rate=row.get("reply_rate", 0.1),
                               booking_rate=row.get("booking_rate", 0.02),
                               sample_size=row.get("sample_size", 120),
                               trend=row.get("trend", "rising"), is_reliable=True))


def _seed_zones(db, strategy, spec, topics: list[str]) -> None:
    from app.db import models as m  # noqa: PLC0415

    for topic in topics or []:
        db.add(m.StrategyUncertainZone(strategy_id=strategy.id, pipeline=spec.pipeline,
                                       phase=spec.phase, step_no=spec.step_no,
                                       section_title=spec.name[:200], topic=topic,
                                       claude_position="a", gpt_position="b",
                                       severity="high", similarity=0.5))


def _seed_strategy(db, inp: dict, *, account: dict | None = None):
    """One account + strategy with the case's research context. Returns
    (user, product, strategy)."""
    from app.db import models as m  # noqa: PLC0415

    acct = account if account is not None else inp
    user, product, strategy = seed_account(
        db, product_name=acct.get("product_name", "Brightline Bookkeeping"),
        description=acct.get("description",
                             "Monthly bookkeeping and payroll for small UK agencies."))
    if acct.get("flow") == "with_clients":
        strategy.flow_type = m.FlowType.WITH_CLIENTS
    for client_row in acct.get("past_clients") or []:
        db.add(m.PastClient(product_id=product.id, details=client_row.get("details", "A client"),
                            acquisition_story=client_row.get("story", "Referral"),
                            extracted_patterns_json=client_row.get("patterns")))
    if acct.get("signals"):
        strategy.market_signals_json = {
            "queries": acct.get("signal_queries") or ["agency bookkeeping"],
            "fetched_at": "2026-10-01T09:00:00+00:00",
            "signals": acct["signals"],
        }
    _seed_research(db, strategy, acct.get("research") or [])
    _seed_playbook(db, user, acct.get("playbook") or [])
    db.flush()
    return user, product, strategy


def _run(db, strategy, spec, client) -> str | None:
    """engine.run_step as production calls it. Returns the exception's type
    name when the app raised (the step then is not recorded), else None."""
    from app.pipeline import engine  # noqa: PLC0415

    try:
        with use_client(client):
            engine.run_step(db, strategy, spec)
    except Exception as exc:  # noqa: BLE001 -- a raise is the app's answer here
        db.rollback()
        return type(exc).__name__
    return None


def _persisted(db, strategy, spec) -> str | None:
    from app.db import models as m  # noqa: PLC0415

    row = db.query(m.ResearchStep).filter_by(strategy_id=strategy.id, pipeline=spec.pipeline,
                                             step_no=spec.step_no).one_or_none()
    return None if row is None else row.output


# --- T01 research pipeline step ---------------------------------------------

@adapter("pipeline_step")
def pipeline_step(inp: dict, client) -> dict:
    """One research step, consensus off (the default setting). Returns the
    research_steps output the app persisted, or persisted=False and the
    error when the step raised."""
    db = fresh_session()
    try:
        _user, _product, strategy = _seed_strategy(db, inp)
        if inp.get("other_account"):
            _seed_strategy(db, inp, account=inp["other_account"])
        if inp.get("sibling_strategy_research"):
            # A second strategy of the SAME product (another run).
            from app.db import models as m  # noqa: PLC0415

            sibling = m.Strategy(product_id=strategy.product_id, flow_type=strategy.flow_type)
            db.add(sibling)
            db.flush()
            _seed_research(db, sibling, inp["sibling_strategy_research"])
        db.commit()
        spec = _spec(_pipeline(inp.get("pipeline")), int(inp.get("step_no", 1)))
        error = _run(db, strategy, spec, client)
        output = _persisted(db, strategy, spec)
        return {"output": output, "persisted": output is not None, "error": error}
    finally:
        db.close()


# --- T02 consensus: GPT-4o parallel answer + Claude consensus judge ---------

@contextmanager
def _openai_stub(gpt: dict | None):
    """get_openai_client -> the real OpenAIClient over a mock transport."""
    import httpx  # noqa: PLC0415

    from app.integrations import openai_client as oc  # noqa: PLC0415

    gpt = gpt or {}

    def handler(request: httpx.Request) -> httpx.Response:
        status = int(gpt.get("status", 200))
        if status != 200:
            return httpx.Response(status, text=gpt.get("body", "upstream error"))
        return httpx.Response(200, json={
            "choices": [{"message": {"content": gpt.get("text", "")},
                         "finish_reason": gpt.get("finish_reason", "stop")}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50}})

    def stub(db):
        from app.services import credentials, system_settings  # noqa: PLC0415

        if not credentials.get_secret(db, "openai", "api_key"):
            return None
        return oc.OpenAIClient(api_key="sk-eval-not-real",
                               model=system_settings.get(db, "consensus_openai_model"),
                               http=httpx.Client(transport=httpx.MockTransport(handler)),
                               sleep=lambda _s: None)

    original = oc.get_openai_client
    oc.get_openai_client = stub
    try:
        yield
    finally:
        oc.get_openai_client = original


@adapter("consensus_step")
def consensus_step(inp: dict, client) -> dict:
    """A step run with consensus enabled and an OpenAI key set (unless the
    case turns either off). Returns Claude's persisted answer, the stored
    OpenAI answer/error, the uncertain zones written for the step and the
    strategy's consensus_status."""
    from app.db import models as m  # noqa: PLC0415
    from app.services import credentials, system_settings  # noqa: PLC0415

    db = fresh_session()
    try:
        _user, _product, strategy = _seed_strategy(db, inp)
        spec = _spec(_pipeline(inp.get("pipeline")), int(inp.get("step_no", 9)))
        other = None
        if inp.get("other_account"):
            _ou, _op, other = _seed_strategy(db, inp, account=inp["other_account"])
            _seed_zones(db, other, spec, inp["other_account"].get("zones") or [])
        # Zones left by an earlier run of this step (a re-run must replace them)
        # and the status an earlier step left on the strategy.
        _seed_zones(db, strategy, spec, inp.get("stale_zones") or [])
        if inp.get("prior_status"):
            strategy.consensus_status = inp["prior_status"]
        system_settings.set(db, "consensus_enabled", bool(inp.get("consensus_enabled", True)))
        if inp.get("openai_key", True):
            credentials.set_system_secret(db, "openai", "api_key", "sk-eval-not-real")
        db.commit()

        with _openai_stub(inp.get("gpt")):
            error = _run(db, strategy, spec, client)
        db.expire_all()
        output = _persisted(db, strategy, spec)
        zones = db.query(m.StrategyUncertainZone).filter_by(
            strategy_id=strategy.id, pipeline=spec.pipeline, step_no=spec.step_no).all()
        stored = {o.provider: o for o in db.query(m.StrategyModelOutput).filter_by(
            strategy_id=strategy.id, step_no=spec.step_no).all()}
        gpt_row = stored.get("openai")
        strategy = db.get(m.Strategy, strategy.id)
        result = {
            "output": output, "persisted": output is not None, "error": error,
            "consensus_status": strategy.consensus_status,
            "zone_count": len(zones),
            "zones": [{"topic": z.topic, "severity": z.severity,
                       "a_position": z.claude_position, "b_position": z.gpt_position}
                      for z in zones],
            "max_topic_chars": max((len(z.topic) for z in zones), default=0),
            "gpt_output": gpt_row.output if gpt_row else None,
            "gpt_failed": bool(gpt_row and gpt_row.error),
        }
        if other is not None:
            result["other_account_zone_count"] = db.query(m.StrategyUncertainZone).filter_by(
                strategy_id=other.id).count()
        return result
    finally:
        db.close()

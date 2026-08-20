"""The 72-step pipeline engine.

Resumability contract (project knowledge, section C):
- every step's output is committed to `research_steps` BEFORE the next
  step starts;
- a crashed run resumes from the first missing step, never from step 1;
- the UNIQUE (strategy_id, pipeline, step_no) constraint makes duplicate
  execution physically impossible even under racing workers.

Flow 1 (with_clients) runs the STRATEGY 72. Flow 2 (no_clients) runs
STRATEGY 72 then GTM 72 (144 total).
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    FlowType,
    PastClient,
    PipelineKind,
    Product,
    ResearchStep,
    Strategy,
)
from app.pipeline.registry import SYSTEM_PROMPT, StepSpec, get_steps
from app.services.anthropic_client import get_client

logger = logging.getLogger(__name__)


def pipelines_for_flow(flow_type: FlowType) -> list[PipelineKind]:
    if flow_type is FlowType.NO_CLIENTS:
        return [PipelineKind.STRATEGY, PipelineKind.GTM]
    return [PipelineKind.STRATEGY]


# --------------------------------------------------------------------------
# Progress / resume position
# --------------------------------------------------------------------------


def completed_step_nos(session: Session, strategy_id: uuid.UUID, pipeline: PipelineKind) -> set[int]:
    rows = session.execute(
        select(ResearchStep.step_no).where(
            ResearchStep.strategy_id == strategy_id,
            ResearchStep.pipeline == pipeline,
        )
    ).scalars()
    return set(rows)


def next_step(session: Session, strategy: Strategy) -> StepSpec | None:
    """First not-yet-persisted step across the strategy's pipelines."""
    for pipeline in pipelines_for_flow(strategy.flow_type):
        done = completed_step_nos(session, strategy.id, pipeline)
        for spec in get_steps(pipeline):
            if spec.step_no not in done:
                return spec
    return None


# --------------------------------------------------------------------------
# Context assembly for a step's prompt
# --------------------------------------------------------------------------


def _product_block(product: Product) -> str:
    return f"Name: {product.name}\nType: {product.type.value}\nDescription: {product.description}"


def _patterns_block(session: Session, strategy: Strategy) -> str:
    if strategy.flow_type is not FlowType.WITH_CLIENTS:
        return "(none — Flow 2: no past clients; rely on market research)"
    clients = session.execute(
        select(PastClient).where(PastClient.product_id == strategy.product_id)
    ).scalars().all()
    parts = []
    for i, c in enumerate(clients, 1):
        parts.append(f"Client {i} patterns: {c.extracted_patterns_json or 'not extracted'}")
    return "\n".join(parts) or "(no past clients recorded)"


def _context_block(session: Session, strategy: Strategy, spec: StepSpec) -> str:
    """Prior research relevant to this step, without blowing the context:
    full outputs of the current phase so far + each earlier phase's
    synthesis step (step 9 of that phase)."""
    rows = session.execute(
        select(ResearchStep)
        .where(
            ResearchStep.strategy_id == strategy.id,
            ResearchStep.pipeline == spec.pipeline,
            ResearchStep.step_no < spec.step_no,
        )
        .order_by(ResearchStep.step_no)
    ).scalars().all()

    parts: list[str] = []
    for r in rows:
        is_current_phase = r.phase == spec.phase
        is_synthesis = r.step_no % 9 == 0
        if is_current_phase or is_synthesis:
            parts.append(f"[Phase {r.phase} / Step {r.step_no}: {r.name}]\n{r.output}")

    # Flow 2 GTM steps also see the strategy pipeline's phase syntheses.
    if spec.pipeline is PipelineKind.GTM:
        strat_rows = session.execute(
            select(ResearchStep)
            .where(
                ResearchStep.strategy_id == strategy.id,
                ResearchStep.pipeline == PipelineKind.STRATEGY,
                ResearchStep.step_no % 9 == 0,
            )
            .order_by(ResearchStep.step_no)
        ).scalars().all()
        for r in strat_rows:
            parts.append(f"[Strategy research — Phase {r.phase} synthesis]\n{r.output}")

    # M8-C1: playbook injection at Phase 6 (messaging & offer design) and
    # Phase 8 (execution plan). Graceful on empty playbooks — get_insights()
    # never raises and returns an explicit "no data yet" block on first runs.
    if spec.pipeline is PipelineKind.STRATEGY and spec.phase in (6, 8):
        from app.services.playbook_service import PlaybookService

        user_id = None
        try:
            user_id = str(strategy.product.user_id)
        except Exception:
            pass
        parts.append(PlaybookService.get_insights(session, user_id=user_id))

    return "\n\n".join(parts) or "(this is the first step — no prior research yet)"


# --------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------


def run_step(session: Session, strategy: Strategy, spec: StepSpec) -> None:
    """Execute ONE step and commit its row before returning."""
    product = session.get(Product, strategy.product_id)
    prompt = spec.build_prompt(
        product_block=_product_block(product),
        patterns_block=_patterns_block(session, strategy),
        context_block=_context_block(session, strategy, spec),
    )
    output = get_client().complete(system=SYSTEM_PROMPT, prompt=prompt)

    session.add(
        ResearchStep(
            strategy_id=strategy.id,
            pipeline=spec.pipeline,
            phase=spec.phase,
            step_no=spec.step_no,
            step_id=spec.id,
            name=spec.name,
            inputs_json={"prompt_chars": len(prompt)},
            output=output,
            model=settings.anthropic_model,
        )
    )
    try:
        session.commit()  # persist BEFORE the next step starts — the rule
    except IntegrityError:
        # A racing worker persisted this step first. Its output is saved;
        # discard ours and move on. Resumability holds either way.
        session.rollback()
        logger.warning("step %s already persisted by another worker — skipping", spec.id)


def run_all_steps(session: Session, strategy: Strategy) -> int:
    """Run from wherever the strategy currently is to completion.

    Safe to call on a fresh strategy, a crashed run, or a finished one.
    Returns the number of steps executed in THIS call.
    """
    executed = 0
    while True:
        spec = next_step(session, strategy)
        if spec is None:
            return executed
        logger.info(
            "strategy %s: running %s step %s/72 — %s",
            strategy.id, spec.pipeline.value, spec.step_no, spec.name,
        )
        run_step(session, strategy, spec)
        executed += 1


# --------------------------------------------------------------------------
# Final document assembly
# --------------------------------------------------------------------------


def _assemble(session: Session, strategy: Strategy, pipeline: PipelineKind, heading: str) -> str:
    rows = session.execute(
        select(ResearchStep)
        .where(
            ResearchStep.strategy_id == strategy.id,
            ResearchStep.pipeline == pipeline,
            ResearchStep.step_no % 9 == 0,  # the 8 phase syntheses
        )
        .order_by(ResearchStep.step_no)
    ).scalars().all()
    sections = [f"# {heading}\n"]
    for r in rows:
        sections.append(f"## Phase {r.phase}: {r.name}\n\n{r.output}\n")
    return "\n".join(sections)


def assemble_documents(session: Session, strategy: Strategy) -> None:
    """Write strategy_document (and gtm_document for Flow 2) from the
    eight phase-synthesis outputs of each completed pipeline."""
    strategy.strategy_document = _assemble(
        session, strategy, PipelineKind.STRATEGY, "Client Acquisition Strategy"
    )
    if strategy.flow_type is FlowType.NO_CLIENTS:
        strategy.gtm_document = _assemble(
            session, strategy, PipelineKind.GTM, "Go-To-Market Plan"
        )
    session.commit()

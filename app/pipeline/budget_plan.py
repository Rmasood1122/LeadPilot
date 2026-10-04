"""F-AI-01b -- fit the pipeline to a budget.

A full run is 72 steps per pipeline (144 for a product with no past clients).
Given a dollar budget this decides how many of each phase's nine steps to run so
the whole run, verification included, is expected to finish inside it.

What may be dropped. Step 9 of every phase is the phase synthesis. The
strategy / GTM documents and the verification loop are built from those rows
only (everything reads `step_no % 9 == 0`), so they are always kept. The eight
supporting steps are research that feeds the synthesis; the plan keeps as many
as the budget affords, spread evenly through the phase, and drops the rest.

The numbers are ESTIMATES (settings: pipeline_est_step_*). The plan errs high;
the F-AI-01 hard cap is the net underneath if a step costs more than estimated.
"""

import math

from app.config import settings
from app.db.models import FlowType

SUPPORT_STEPS = 8        # supporting steps per phase, before the synthesis
MIN_STEPS_PER_PHASE = 2  # one supporting step + the synthesis
PHASES = 8


class BudgetTooSmall(Exception):
    """The budget cannot pay for even the smallest complete plan."""

    def __init__(self, budget_micros: int, minimum_micros: int) -> None:
        super().__init__(
            f"budget ${budget_micros / 1_000_000:.2f} is below the "
            f"${minimum_micros / 1_000_000:.2f} minimum"
        )
        self.budget_micros = budget_micros
        self.minimum_micros = minimum_micros


def _pipelines(flow_type: FlowType) -> int:
    return 2 if flow_type is FlowType.NO_CLIENTS else 1


def estimate_step_micros(prices: dict) -> int:
    price_in, price_out = prices.get("anthropic", (0.0, 0.0))
    return int(round(settings.pipeline_est_step_input_tokens * price_in
                     + settings.pipeline_est_step_output_tokens * price_out))


def _reserve_micros() -> int:
    return int(settings.pipeline_verification_reserve_usd * 1_000_000)


def _needed(k: int, flow_type: FlowType, prices: dict) -> int:
    """Budget at which k steps per phase is planned: steps + reserve, grossed up
    by the safety margin."""
    steps = k * PHASES * _pipelines(flow_type) * estimate_step_micros(prices)
    return int(math.ceil((steps + _reserve_micros()) / settings.pipeline_budget_safety))


def min_budget_micros(flow_type: FlowType, prices: dict) -> int:
    return _needed(MIN_STEPS_PER_PHASE, flow_type, prices)


def plan_steps_per_phase(budget_micros: int, flow_type: FlowType, prices: dict) -> int | None:
    """Steps per phase to run: 2..8, or None for the full nine.

    Raises BudgetTooSmall when even two per phase would not fit."""
    if budget_micros < min_budget_micros(flow_type, prices):
        raise BudgetTooSmall(budget_micros, min_budget_micros(flow_type, prices))
    k = MIN_STEPS_PER_PHASE
    while k < 9 and budget_micros >= _needed(k + 1, flow_type, prices):
        k += 1
    return None if k >= 9 else k


def planned_step_nos(steps_per_phase: int | None) -> set[int]:
    """Step numbers (1..72 within a pipeline) the plan runs."""
    if steps_per_phase is None or steps_per_phase >= 9:
        return set(range(1, 73))
    support = max(steps_per_phase - 1, 0)
    chosen: set[int] = set()
    for phase in range(PHASES):
        base = phase * 9
        for j in range(support):
            # centres of `support` equal slices of the eight supporting steps
            idx = int(math.floor((j + 0.5) * SUPPORT_STEPS / support - 0.5 + 0.5))
            chosen.add(base + 1 + min(idx, SUPPORT_STEPS - 1))
        chosen.add(base + 9)
    return chosen

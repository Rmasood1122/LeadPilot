"""Product defect #1: the strategy detail page read a response shape the API
never sent (flat per-phase rows with `steps`, a pass list with `attempts` and
`fix`), so progress showed "Phase pending" cards and the attempt count and fix
text never rendered.

The frontend test (frontend/src/tests/strategyDetail.test.tsx) renders the page
against frontend/src/tests/fixtures/strategy-status.json. This test pins that
fixture to the real API: it builds a strategy with research steps and a
verification log written by the verification loop's own logger, calls
GET /strategies/{id}, and requires the response and the fixture to have the
same shape (same keys at every level, same value types) and the fixture to
validate against StrategyStatusOut. Change the API and this fails until the
fixture -- and so the page test -- follow.

Regenerate the fixture: STRATEGY_FIXTURE_WRITE=1 pytest tests/test_strategy_status_fixture.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.api.schemas import StrategyStatusOut
from app.db import models as m
from app.verification import loop as verification_loop
from app.verification.passes import build_passes

FIXTURE = (Path(__file__).resolve().parents[1]
           / "frontend" / "src" / "tests" / "fixtures" / "strategy-status.json")


def _shape(value):
    """Keys and value types, recursively. A list's shape is the SET of its
    elements' shapes -- every element is compared, not only the first (review
    L1: a row missing a key in position 2 used to pass)."""
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return ["list", sorted({json.dumps(_shape(item), sort_keys=True) for item in value})]
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    return "str"


def test_shape_compares_every_list_element():
    rows = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
    assert _shape(rows) == _shape(list(reversed(rows)))
    assert _shape(rows) != _shape([{"a": 1, "b": "x"}, {"a": 2}])          # key missing in row 2
    assert _shape(rows) != _shape([{"a": 1, "b": "x"}, {"a": 2, "b": 3}])  # type differs in row 2
    assert _shape([{"p": [1]}, {"p": ["s"]}]) != _shape([{"p": [1]}, {"p": [1]}])


def _seed(db, product_with_strategy):
    _, strategy = product_with_strategy(m.FlowType.NO_CLIENTS, with_past_client=False)
    strategy.status = m.StrategyStatus.NEEDS_HUMAN_REVIEW
    strategy.budget_micros = 25_000_000
    strategy.error = None
    # Five steps of strategy phase 1, two of GTM phase 3.
    for n in range(1, 6):
        db.add(m.ResearchStep(strategy_id=strategy.id, pipeline=m.PipelineKind.STRATEGY,
                              phase=1, step_no=n, step_id=f"s1.0{n}", name=f"Step {n}",
                              output="out", model="claude-sonnet-4-6"))
    for n in (19, 20):
        db.add(m.ResearchStep(strategy_id=strategy.id, pipeline=m.PipelineKind.GTM,
                              phase=3, step_no=n, step_id=f"g3.{n}", name=f"GTM {n}",
                              output="out", model="claude-sonnet-4-6"))
    specs = build_passes(strategy.flow_type)
    log = verification_loop._log_attempt
    log(strategy, specs[0], 1, "PASS", None, False)
    log(strategy, specs[1], 1, "FAIL", "Market size cites no source", True)
    log(strategy, specs[1], 2, "PASS", None, False)
    log(strategy, specs[2], 1, "FAIL", "Competitor pricing is a guess", True)
    log(strategy, specs[2], 2, "FAIL", "Competitor pricing still unsourced", False)
    db.commit()
    return strategy


def test_fixture_has_the_exact_shape_the_api_sends(client, db_session, product_with_strategy):
    strategy = _seed(db_session, product_with_strategy)
    response = client.get(f"/strategies/{strategy.id}")
    assert response.status_code == 200, response.text
    live = response.json()

    if os.environ.get("STRATEGY_FIXTURE_WRITE"):
        stable = dict(live, id="11111111-2222-3333-4444-555555555555")
        for row in stable["verification"]:
            row["ts"] = "2026-10-11T12:00:00+00:00"
        FIXTURE.write_text(json.dumps(stable, indent=2) + "\n", encoding="utf-8")

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert _shape(fixture) == _shape(live)
    # Every top-level field of the schema is present (no silent omissions).
    assert set(fixture) == set(StrategyStatusOut.model_fields)
    StrategyStatusOut.model_validate(fixture)


def test_fixture_values_are_the_ones_the_page_test_asserts():
    """The page test asserts on these values; keep them meaningful."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pipelines = [p["pipeline"] for p in fixture["progress"]]
    assert pipelines == ["strategy", "gtm"]
    first = fixture["progress"][0]["phases"][0]
    assert first["phase"] == 1 and first["done"] == 5 and first["title"]
    attempts = [r["attempt"] for r in fixture["verification"] if r["pass_no"] == 3]
    assert attempts == [1, 2]

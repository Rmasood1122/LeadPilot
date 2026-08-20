"""Pipeline engine — resumability is the core guarantee under test."""

from sqlalchemy import select

import pytest

from app.db import models as m
from app.pipeline import engine


def _saved_step_nos(db, strategy, pipeline):
    return sorted(
        db.execute(
            select(m.ResearchStep.step_no).where(
                m.ResearchStep.strategy_id == strategy.id,
                m.ResearchStep.pipeline == pipeline,
            )
        ).scalars()
    )


class TestResumability:
    def test_crash_midrun_then_resume_no_duplicates(
        self, db_session, fake_claude, product_with_strategy
    ):
        _, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)

        # Crash after 10 successful steps.
        fake_claude.fail_after = 10
        with pytest.raises(RuntimeError):
            engine.run_all_steps(db_session, strategy)

        saved = _saved_step_nos(db_session, strategy, m.PipelineKind.STRATEGY)
        assert saved == list(range(1, 11)), "exactly the 10 completed steps persist"

        # Resume: engine must continue from step 11, never restart.
        fake_claude.fail_after = None
        executed = engine.run_all_steps(db_session, strategy)
        assert executed == 62  # 72 - 10 already saved

        saved = _saved_step_nos(db_session, strategy, m.PipelineKind.STRATEGY)
        assert saved == list(range(1, 73))
        assert len(saved) == len(set(saved)), "no duplicate steps"

    def test_rerun_after_completion_is_a_noop(
        self, db_session, fake_claude, product_with_strategy
    ):
        _, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
        assert engine.run_all_steps(db_session, strategy) == 72
        assert engine.run_all_steps(db_session, strategy) == 0  # idempotent

    def test_next_step_resume_position(self, db_session, fake_claude, product_with_strategy):
        _, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
        fake_claude.fail_after = 25
        with pytest.raises(RuntimeError):
            engine.run_all_steps(db_session, strategy)
        spec = engine.next_step(db_session, strategy)
        assert spec.step_no == 26
        assert spec.phase == 3


class TestFlows:
    def test_flow1_runs_exactly_72(self, db_session, fake_claude, product_with_strategy):
        _, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
        assert engine.run_all_steps(db_session, strategy) == 72
        assert _saved_step_nos(db_session, strategy, m.PipelineKind.GTM) == []

    def test_flow2_runs_144_strategy_then_gtm(
        self, db_session, fake_claude, product_with_strategy
    ):
        _, strategy = product_with_strategy(m.FlowType.NO_CLIENTS, with_past_client=False)
        assert engine.run_all_steps(db_session, strategy) == 144
        assert _saved_step_nos(db_session, strategy, m.PipelineKind.STRATEGY) == list(range(1, 73))
        assert _saved_step_nos(db_session, strategy, m.PipelineKind.GTM) == list(range(1, 73))

    def test_flow2_crash_in_gtm_resumes_in_gtm(
        self, db_session, fake_claude, product_with_strategy
    ):
        _, strategy = product_with_strategy(m.FlowType.NO_CLIENTS, with_past_client=False)
        fake_claude.fail_after = 100  # 72 strategy + 28 GTM steps done
        with pytest.raises(RuntimeError):
            engine.run_all_steps(db_session, strategy)
        spec = engine.next_step(db_session, strategy)
        assert spec.pipeline is m.PipelineKind.GTM
        assert spec.step_no == 29
        fake_claude.fail_after = None
        assert engine.run_all_steps(db_session, strategy) == 44


class TestDocuments:
    def test_assemble_documents(self, db_session, fake_claude, product_with_strategy):
        _, strategy = product_with_strategy(m.FlowType.NO_CLIENTS, with_past_client=False)
        engine.run_all_steps(db_session, strategy)
        engine.assemble_documents(db_session, strategy)
        assert "Client Acquisition Strategy" in strategy.strategy_document
        assert strategy.strategy_document.count("## Phase") == 8
        assert "Go-To-Market Plan" in strategy.gtm_document
        assert strategy.gtm_document.count("## Phase") == 8

    def test_flow1_has_no_gtm_document(self, db_session, fake_claude, product_with_strategy):
        _, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
        engine.run_all_steps(db_session, strategy)
        engine.assemble_documents(db_session, strategy)
        assert strategy.strategy_document
        assert strategy.gtm_document is None

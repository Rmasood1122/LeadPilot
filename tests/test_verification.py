"""Verification loop — all three lifecycle paths from the spec."""

from app.config import settings
from app.db import models as m
from app.verification.loop import run_verification_loop
from app.verification.passes import build_passes


def _prepare(db, product_with_strategy, flow=m.FlowType.WITH_CLIENTS):
    _, strategy = product_with_strategy(flow)
    strategy.strategy_document = "# Strategy v1\nTarget fire-protection owners via referral-led outreach."
    db.commit()
    return strategy


class TestAllPassPath:
    def test_all_ten_pass_first_try(self, db_session, fake_claude, product_with_strategy):
        strategy = _prepare(db_session, product_with_strategy)
        final = run_verification_loop(db_session, strategy)

        assert final is m.StrategyStatus.VERIFIED
        assert strategy.status is m.StrategyStatus.VERIFIED
        log = strategy.verified_passes_json
        assert len(log) == 10
        assert [e["pass_no"] for e in log] == list(range(1, 11))
        assert all(e["result"] == "PASS" and e["attempt"] == 1 for e in log)
        assert fake_claude.judge_calls == list(range(1, 11))


class TestFailFixPassPath:
    def test_fail_then_fix_then_pass(self, db_session, fake_claude, product_with_strategy):
        strategy = _prepare(db_session, product_with_strategy)
        original_doc = strategy.strategy_document
        fake_claude.judge_script[4] = [
            ("FAIL", "Add a working unsubscribe link to every email footer."),
            ("PASS", None),
        ]

        final = run_verification_loop(db_session, strategy)

        assert final is m.StrategyStatus.VERIFIED
        log = strategy.verified_passes_json
        assert len(log) == 11  # 9 clean passes + 1 fail + 1 re-pass
        p4 = [e for e in log if e["pass_no"] == 4]
        assert [e["result"] for e in p4] == ["FAIL", "PASS"]
        assert p4[0]["fix_description"].startswith("Add a working unsubscribe")
        assert p4[0]["fix_applied"] is True
        assert p4[1]["attempt"] == 2
        assert fake_claude.fix_calls == [4]
        assert strategy.strategy_document != original_doc  # fixer revised it
        assert "REVISED DOCUMENT" in strategy.strategy_document


class TestRetryCapPath:
    def test_exhausted_pass_marks_needs_human_review(
        self, db_session, fake_claude, product_with_strategy
    ):
        strategy = _prepare(db_session, product_with_strategy)
        cap = settings.verification_max_retries_per_pass
        fake_claude.judge_script[7] = [("FAIL", "Plan needs 3 SDRs the user does not have.")] * cap

        final = run_verification_loop(db_session, strategy)

        assert final is m.StrategyStatus.NEEDS_HUMAN_REVIEW
        assert strategy.status is m.StrategyStatus.NEEDS_HUMAN_REVIEW
        p7 = [e for e in strategy.verified_passes_json if e["pass_no"] == 7]
        assert len(p7) == cap
        assert all(e["result"] == "FAIL" for e in p7)
        assert p7[-1]["fix_applied"] is False, "no pointless fix after the final attempt"
        assert len(fake_claude.fix_calls) == cap - 1
        # Remaining passes were still evaluated and logged.
        assert {e["pass_no"] for e in strategy.verified_passes_json} == set(range(1, 11))


class TestPassTenByFlow:
    def test_flow1_checks_pattern_consistency(self):
        keys = [p.key for p in build_passes(m.FlowType.WITH_CLIENTS)]
        assert keys[-1] == "pattern_consistency"
        assert len(keys) == 10 and len(set(keys)) == 10

    def test_flow2_checks_gtm_consistency(self):
        keys = [p.key for p in build_passes(m.FlowType.NO_CLIENTS)]
        assert keys[-1] == "gtm_consistency"
        assert keys[:9] == [p.key for p in build_passes(m.FlowType.WITH_CLIENTS)][:9]

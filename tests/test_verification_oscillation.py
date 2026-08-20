"""Regression tests for the verification loop arguing with itself.

Reproduces the exact failure found in the 2026-08-19 Phase C run against the
real model, where 3 of 10 passes exhausted all their attempts without the
document ever being wrong:

    attempt 1  judge: "Phase 2 finalised $3,000-$5,500; the document's
                       $2,500-$7,500 is wrong"          -> fix rewrites A -> B
    attempt 2  judge: "the Phase 1 source says $2,500-$7,500; the document's
                       $3,000-$5,500 disagrees with it" -> fix rewrites B -> A
    attempt 3  judge: "the document now shows both without saying which is
                       superseded"                      -> attempts exhausted

Each wasted attempt is a full-document rewrite at max_tokens=8000, and the
strategy lands in NEEDS_HUMAN_REVIEW for a reason no edit could have fixed.

Two mechanisms are under test:
  * oscillation detection — a fix that recreates a state this pass already
    produced ends the pass immediately as "conflicting_sources";
  * PRECEDENCE_RULE — later research phases supersede earlier ones, so the
    judge stops reading a refinement as a contradiction in the first place.
"""

import pytest

from app.config import settings
from app.db import models as m
from app.verification.loop import (
    _normalize_document,
    _reverts_earlier_state,
    run_verification_loop,
)
from app.verification.passes import PRECEDENCE_RULE

# The two competing states, standing in for the real pricing conflict.
DOC_EARLY = (
    "# Strategy\n\n## Pricing\n"
    "LeadPilot is priced at $2,500-$7,500/month versus $10K-$13K/month "
    "for a fully-loaded SDR.\n\n## Channels\nReferral-led outreach."
)
DOC_LATE = (
    "# Strategy\n\n## Pricing\n"
    "LeadPilot is priced at $3,000-$5,500/month versus $10K-$13K/month "
    "for a fully-loaded SDR.\n\n## Channels\nReferral-led outreach."
)

_FIX_TO_LATE = ("Phase 2 finalised Foundation at $3,000/month and Growth at "
                "$5,500/month. Replace the $2,500-$7,500 range.")
_FIX_TO_EARLY = ("The Phase 1 source research states $2,500-$7,500/month. "
                 "Restore that range to match the source.")


class OscillatingClaude:
    """Judge that never accepts, and a fixer that flip-flops between two states.

    This is the shape the real model produced — not an artificial construct.
    """

    def __init__(self, target_pass: int = 1, converge_on_attempt: int | None = None):
        self.target_pass = target_pass
        self.converge_on_attempt = converge_on_attempt
        self.judge_calls: list[int] = []
        self.fix_calls: list[int] = []
        self.attempts_for_target = 0

    def _pass_no(self, prompt: str) -> int:
        import re

        match = re.search(r"criterion #(\d+)", prompt, re.IGNORECASE)
        return int(match.group(1)) if match else 0

    def complete_json(self, system: str, prompt: str, max_tokens=None) -> dict:
        pass_no = self._pass_no(prompt)
        self.judge_calls.append(pass_no)
        if pass_no != self.target_pass:
            return {"result": "PASS"}

        self.attempts_for_target += 1
        if (self.converge_on_attempt is not None
                and self.attempts_for_target >= self.converge_on_attempt):
            return {"result": "PASS"}

        # Alternate the complaint, exactly as the real judge did.
        fix = _FIX_TO_LATE if self.attempts_for_target % 2 == 1 else _FIX_TO_EARLY
        return {"result": "FAIL", "fix_description": fix}

    def complete(self, system: str, prompt: str, max_tokens=None) -> str:
        pass_no = self._pass_no(prompt)
        self.fix_calls.append(pass_no)
        # The fixer honours whichever value the finding demands -> flip-flop.
        if "$3,000" in prompt and "Replace the $2,500-$7,500" in prompt:
            return DOC_LATE
        if "Restore that range" in prompt:
            return DOC_EARLY
        return DOC_LATE


@pytest.fixture()
def oscillating_claude(monkeypatch):
    fake = OscillatingClaude()
    monkeypatch.setattr("app.verification.loop.get_client", lambda: fake)
    return fake


def _prepare(db, product_with_strategy, document=DOC_EARLY):
    _, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
    strategy.strategy_document = document
    db.commit()
    return strategy


class TestOscillationIsDetected:
    def test_reverting_fix_ends_the_pass_immediately(
        self, db_session, oscillating_claude, product_with_strategy
    ):
        """The pass must stop on the revert, not run to exhaustion."""
        strategy = _prepare(db_session, product_with_strategy)

        run_verification_loop(db_session, strategy)

        target = [e for e in strategy.verified_passes_json if e["pass_no"] == 1]
        assert len(target) == 2, (
            f"expected the pass to stop on the reverting fix (2 attempts), "
            f"got {len(target)}: {[e['attempt'] for e in target]}"
        )
        assert target[-1]["outcome"] == "conflicting_sources"

    def test_conflict_carries_both_candidate_values_to_the_review_layer(
        self, db_session, oscillating_claude, product_with_strategy
    ):
        """A human needs to see both readings to adjudicate."""
        strategy = _prepare(db_session, product_with_strategy)

        run_verification_loop(db_session, strategy)

        conflict = [e for e in strategy.verified_passes_json
                    if e.get("outcome") == "conflicting_sources"][0]["conflict"]
        assert len(conflict["candidates"]) == 2
        assert any("$3,000" in c for c in conflict["candidates"])
        assert any("$2,500" in c for c in conflict["candidates"])
        assert conflict["reverts_to_state_before_attempt"] == 1
        assert "cannot be satisfied by editing" in conflict["reason"]

    def test_reverting_fix_is_not_written_to_the_document(
        self, db_session, oscillating_claude, product_with_strategy
    ):
        """Detection happens before the revision lands."""
        strategy = _prepare(db_session, product_with_strategy)

        run_verification_loop(db_session, strategy)

        assert strategy.strategy_document == DOC_LATE, (
            "the reverting fix overwrote the document instead of being rejected"
        )

    def test_remaining_attempts_are_not_spent(
        self, db_session, oscillating_claude, product_with_strategy
    ):
        """The whole point: stop paying for rewrites that rediscover the conflict."""
        strategy = _prepare(db_session, product_with_strategy)

        run_verification_loop(db_session, strategy)

        assert settings.verification_max_retries_per_pass == 3, (
            "test assumes the default retry budget"
        )
        # Without detection the pass judges 3 times (its full budget); with it,
        # the pass stops after the second judge proves the conflict.
        target_judges = [p for p in oscillating_claude.judge_calls if p == 1]
        assert len(target_judges) == 2, (
            f"expected the pass to stop after 2 judge calls, got "
            f"{len(target_judges)} — the remaining attempt was still spent"
        )
        target_fixes = [p for p in oscillating_claude.fix_calls if p == 1]
        assert len(target_fixes) == 2

    def test_strategy_still_reaches_needs_human_review(
        self, db_session, oscillating_claude, product_with_strategy
    ):
        """Stopping early must not silently downgrade to VERIFIED."""
        strategy = _prepare(db_session, product_with_strategy)

        final = run_verification_loop(db_session, strategy)

        assert final is m.StrategyStatus.NEEDS_HUMAN_REVIEW
        assert strategy.status is m.StrategyStatus.NEEDS_HUMAN_REVIEW

    def test_other_passes_still_run_after_a_conflict(
        self, db_session, oscillating_claude, product_with_strategy
    ):
        """A conflict on pass 1 must not abort passes 2-10."""
        strategy = _prepare(db_session, product_with_strategy)

        run_verification_loop(db_session, strategy)

        seen = {e["pass_no"] for e in strategy.verified_passes_json}
        assert seen == set(range(1, 11))


class TestConvergenceStillWorks:
    def test_pass_that_converges_is_not_flagged_as_conflict(
        self, db_session, monkeypatch, product_with_strategy
    ):
        """PRECEDENCE_RULE resolving the disagreement -> the pass simply passes.

        This is the intended post-fix behaviour for the real case: the judge
        accepts the superseding value on re-judge instead of demanding the old
        one back.
        """
        fake = OscillatingClaude(converge_on_attempt=2)
        monkeypatch.setattr("app.verification.loop.get_client", lambda: fake)
        strategy = _prepare(db_session, product_with_strategy)

        final = run_verification_loop(db_session, strategy)

        assert final is m.StrategyStatus.VERIFIED
        target = [e for e in strategy.verified_passes_json if e["pass_no"] == 1]
        assert [e["result"] for e in target] == ["FAIL", "PASS"]
        assert not any(e.get("outcome") == "conflicting_sources" for e in target)

    def test_a_genuinely_new_fix_is_applied_normally(
        self, db_session, fake_claude, product_with_strategy
    ):
        """No false positives: distinct revisions must not read as reverts.

        FakeClaude's fixer returns a fresh document per call, so a pass that
        fails twice with different content should still use its full budget.
        """
        strategy = _prepare(db_session, product_with_strategy)
        fake_claude.judge_script[4] = [
            ("FAIL", "Add an unsubscribe link."),
            ("FAIL", "Add a physical mailing address."),
            ("PASS", None),
        ]

        run_verification_loop(db_session, strategy)

        p4 = [e for e in strategy.verified_passes_json if e["pass_no"] == 4]
        assert [e["result"] for e in p4] == ["FAIL", "FAIL", "PASS"]
        assert not any(e.get("outcome") == "conflicting_sources" for e in p4)


class TestRevertDetectionUnit:
    def test_exact_match_after_whitespace_normalisation(self):
        history = [_normalize_document("# A\n\nsome   text")]
        assert _reverts_earlier_state("# A\nsome text", history) == 0

    def test_near_revert_is_caught(self):
        base = "the quick brown fox jumps over the lazy dog " * 40
        history = [_normalize_document(base)]
        near = base + "and."
        assert _reverts_earlier_state(near, history) == 0

    def test_genuinely_different_document_is_not_a_revert(self):
        history = [_normalize_document("Pricing is $3,000-$5,500 per month.")]
        different = ("Pricing is $3,000-$5,500 per month. We also now offer a "
                     "portfolio discount at $2,500 for multi-brand accounts, "
                     "and an enterprise tier negotiated per seat.")
        assert _reverts_earlier_state(different, history) is None

    def test_empty_revision_is_not_treated_as_a_revert(self):
        """An empty fixer response is a separate failure mode, not oscillation."""
        assert _reverts_earlier_state("", [_normalize_document("anything")]) is None

    def test_matches_any_earlier_state_not_just_the_last(self):
        history = [_normalize_document("state A"), _normalize_document("state B")]
        assert _reverts_earlier_state("state A", history) == 0


class TestPrecedenceRule:
    """The rule must be explicit and reach both the judge and the fixer."""

    def test_rule_states_later_phases_supersede(self):
        assert "SUPERSEDE" in PRECEDENCE_RULE.upper()
        assert "HIGHEST-NUMBERED" in PRECEDENCE_RULE.upper()

    def test_rule_forbids_demanding_the_superseded_value_back(self):
        lowered = PRECEDENCE_RULE.lower()
        assert "do not ask for the earlier value" in lowered

    def test_rule_reaches_the_judge_prompt(self):
        from app.verification.passes import JUDGE_PROMPT

        rendered = JUDGE_PROMPT.format(
            pass_no=1, name="n", criterion="c",
            precedence_rule=PRECEDENCE_RULE,
            strategy_document="d", support_block="s",
        )
        assert "SOURCE-OF-TRUTH PRECEDENCE" in rendered

    def test_rule_reaches_the_fixer_prompt(self):
        from app.verification.passes import FIXER_PROMPT

        rendered = FIXER_PROMPT.format(
            pass_no=1, name="n", fix_description="f",
            precedence_rule=PRECEDENCE_RULE,
            strategy_document="d",
        )
        assert "SOURCE-OF-TRUTH PRECEDENCE" in rendered


class TestSupportBlockOrdering:
    def test_sources_are_labelled_with_precedence_metadata(
        self, db_session, product_with_strategy
    ):
        """The rule is only applicable if the blocks carry ordering."""
        from app.verification.loop import _support_block

        _, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
        for step_no, phase in ((9, 1), (18, 2)):
            db_session.add(m.ResearchStep(
                strategy_id=strategy.id, pipeline=m.PipelineKind.STRATEGY,
                step_no=step_no, phase=phase, step_id=f"S{step_no}",
                name=f"synthesis {phase}", output=f"phase {phase} finding",
                model="test-model",
            ))
        db_session.commit()

        block = _support_block(db_session, strategy)

        assert "source 1 of 2" in block
        assert "source 2 of 2" in block
        assert "earliest source" in block
        assert "supersedes strategy sources 1-1" in block

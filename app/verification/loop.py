"""The 10× Verification Loop — execution.

For each of the 10 passes in order:
  attempt -> PASS: log and move on.
          -> FAIL: log with fix_description, apply the fix (Claude revises
             the strategy document), re-run the SAME pass. Repeat until it
             passes or VERIFICATION_MAX_RETRIES_PER_PASS attempts are used.

If every pass ends green      -> strategy.status = VERIFIED
If any pass exhausts retries  -> strategy.status = NEEDS_HUMAN_REVIEW
Every single attempt is appended to strategy.verified_passes_json:
  {pass_no, key, name, attempt, result, fix_description?, fix_applied, ts}

Two mechanisms keep the fail->fix->re-run cycle from arguing with itself, both
added after the 2026-08-19 Phase C run put 3 of 10 passes into
NEEDS_HUMAN_REVIEW for an unsatisfiable reason:

* PRECEDENCE_RULE (app/verification/passes.py) tells the judge and the fixer
  that later research phases supersede earlier ones, so a refined value is not
  read as a contradiction of the estimate it replaced.
* Oscillation detection compares each proposed revision against the states this
  pass has already produced. A fix that reverts one of them ends the pass
  immediately with outcome "conflicting_sources", carrying both competing
  fix descriptions to the review layer, instead of spending the remaining
  attempts (a full-document rewrite each) rediscovering the same conflict.
"""

import logging
from datetime import datetime, timezone
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.db.models import FlowType, PastClient, ResearchStep, Strategy, StrategyStatus
from app.services.anthropic_client import TruncatedResponseError, get_client
from app.services import notifications
from app.verification.passes import (
    FIXER_PROMPT,
    FIXER_SYSTEM,
    JUDGE_PROMPT,
    JUDGE_SYSTEM,
    PRECEDENCE_RULE,
    VerificationPassSpec,
    build_passes,
)

logger = logging.getLogger(__name__)

_MAX_SUPPORT_CHARS = 60_000  # keep judge prompts bounded
# claude-sonnet-4-6's output cap, confirmed live via the Models API.
# Upper bound for the one retry in _generate_fix.
_MODEL_MAX_OUTPUT_TOKENS = 128_000


def _support_block(session: Session, strategy: Strategy) -> str:
    """Evidence the judge sees: phase syntheses, patterns, GTM doc.

    Each research block is labelled with an explicit ordinal and a
    "supersedes" note so PRECEDENCE_RULE can be applied mechanically rather
    than inferred. Phase numbers alone are ambiguous once two pipelines are
    present (both STRATEGY and GTM have a phase 2), so the ordinal is scoped
    per pipeline and the pipeline name is carried on every label.
    """
    parts: list[str] = []

    rows = session.execute(
        select(ResearchStep)
        .where(ResearchStep.strategy_id == strategy.id, ResearchStep.step_no % 9 == 0)
        .order_by(ResearchStep.pipeline, ResearchStep.step_no)
    ).scalars().all()

    per_pipeline: dict[str, int] = {}
    totals: dict[str, int] = {}
    for r in rows:
        totals[r.pipeline.value] = totals.get(r.pipeline.value, 0) + 1
    for r in rows:
        name = r.pipeline.value
        idx = per_pipeline.get(name, 0) + 1
        per_pipeline[name] = idx
        supersedes = (
            f"supersedes {name} sources 1-{idx - 1}" if idx > 1
            else "earliest source"
        )
        parts.append(
            f"[{name} research | source {idx} of {totals[name]} | "
            f"phase {r.phase} synthesis | {supersedes}]\n{r.output}"
        )

    if strategy.flow_type is FlowType.WITH_CLIENTS:
        clients = session.execute(
            select(PastClient).where(PastClient.product_id == strategy.product_id)
        ).scalars().all()
        for i, c in enumerate(clients, 1):
            parts.append(f"[past-client {i} patterns] {c.extracted_patterns_json}")
    elif strategy.gtm_document:
        parts.append(f"[GTM PLAN]\n{strategy.gtm_document}")

    block = "\n\n".join(parts) or "(no supporting research found)"
    return block[:_MAX_SUPPORT_CHARS]


def _log_attempt(strategy: Strategy, spec: VerificationPassSpec, attempt: int,
                 result: str, fix_description: str | None, fix_applied: bool,
                 conflict: dict | None = None) -> None:
    entry = {
        "pass_no": spec.pass_no,
        "key": spec.key,
        "name": spec.name,
        "attempt": attempt,
        "result": result,
        "fix_description": fix_description,
        "fix_applied": fix_applied,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    if conflict is not None:
        # Surfaced to the review layer. Two distinct stop conditions share this
        # shape: sources that contradict each other, and a rewrite too large to
        # return. Both mean "a human must look", neither means "the document is
        # simply wrong".
        entry["outcome"] = (
            "fix_truncated" if "output_token_ceiling" in conflict
            else "conflicting_sources"
        )
        entry["conflict"] = conflict
    strategy.verified_passes_json = [*(strategy.verified_passes_json or []), entry]
    flag_modified(strategy, "verified_passes_json")


def _judge(spec: VerificationPassSpec, strategy: Strategy, support: str) -> tuple[bool, str | None]:
    data = get_client().complete_json(
        system=JUDGE_SYSTEM,
        prompt=JUDGE_PROMPT.format(
            pass_no=spec.pass_no,
            name=spec.name,
            criterion=spec.criterion,
            precedence_rule=PRECEDENCE_RULE,
            strategy_document=strategy.strategy_document or "(empty)",
            support_block=support,
        ),
    )
    passed = str(data.get("result", "")).strip().upper() == "PASS"
    return passed, data.get("fix_description")


def _generate_fix(spec: VerificationPassSpec, strategy: Strategy,
                  fix_description: str) -> str:
    """Produce the revised document WITHOUT applying it.

    Generation and application are separate so a revision that merely reverts
    an earlier attempt can be rejected before it overwrites the document.

    Raises TruncatedResponseError if the rewrite does not fit even at the
    raised ceiling. It is NEVER swallowed into a partial document — persisting
    a truncated rewrite is the bug this whole path exists to prevent.
    """
    prompt = FIXER_PROMPT.format(
        pass_no=spec.pass_no,
        name=spec.name,
        fix_description=fix_description,
        precedence_rule=PRECEDENCE_RULE,
        strategy_document=strategy.strategy_document or "(empty)",
    )
    ceiling = settings.verification_fixer_max_tokens
    try:
        revised = get_client().complete(
            system=FIXER_SYSTEM, prompt=prompt, max_tokens=ceiling,
        )
    except TruncatedResponseError as first:
        # One retry at double the ceiling. A document that outgrew the
        # configured bound is a real possibility as research accumulates; a
        # document that outgrows twice the bound is a signal to stop, not to
        # keep doubling.
        retry_ceiling = min(ceiling * 2, _MODEL_MAX_OUTPUT_TOKENS)
        if retry_ceiling <= first.limit:
            raise
        logger.warning(
            "pass %s: fix hit the %s-token ceiling — retrying once at %s",
            spec.key, first.limit, retry_ceiling,
        )
        revised = get_client().complete(
            system=FIXER_SYSTEM, prompt=prompt, max_tokens=retry_ceiling,
        )
    return revised.strip()


# ---------------------------------------------------------------------------
# Oscillation detection
# ---------------------------------------------------------------------------
# A fix that returns the document to a state this pass has already tried is not
# progress — it is the loop arguing with itself. Observed on the 2026-08-19
# Phase C run: attempt 1 changed a price range A->B, attempt 2 changed it back
# B->A, attempt 3 produced a both-values compromise and the pass exhausted.
#
# Detecting it lets the pass stop at the moment the conflict is provable and
# hand the ambiguity to a human, instead of spending the remaining attempts
# (each a full-document rewrite at max_tokens=8000) rediscovering it.

_REVERT_SIMILARITY_THRESHOLD = 0.98


def _normalize_document(text: str) -> str:
    """Whitespace-insensitive form for comparing document states.

    Deliberately NOT case-folded: a fix whose only change is capitalisation is
    a real (if trivial) change, and folding it would risk false positives.
    """
    return " ".join((text or "").split())


def _reverts_earlier_state(candidate: str, history: list[str]) -> int | None:
    """Return the index of the earlier state `candidate` reverts to, or None.

    Exact match after normalisation is the common case; the similarity ratio
    catches a near-revert that differs only by a stray connective, which is
    what a model regenerating "the previous version" actually produces.
    """
    normalized = _normalize_document(candidate)
    if not normalized:
        return None
    for index, previous in enumerate(history):
        if normalized == previous:
            return index
        if SequenceMatcher(None, normalized, previous).ratio() >= _REVERT_SIMILARITY_THRESHOLD:
            return index
    return None


def run_verification_loop(session: Session, strategy: Strategy) -> StrategyStatus:
    """Run all 10 passes with fail→fix→re-run. Returns the final status
    (also written to the strategy row)."""
    strategy.status = StrategyStatus.VERIFYING
    session.commit()

    max_retries = settings.verification_max_retries_per_pass
    any_exhausted = False

    for spec in build_passes(strategy.flow_type):
        passed = False
        # Document states this pass has already produced, oldest first. Seeded
        # with the state the pass starts from, so a first fix that immediately
        # reverts to it is caught too.
        document_history: list[str] = [
            _normalize_document(strategy.strategy_document or "")
        ]
        prior_fix_descriptions: list[str] = []

        for attempt in range(1, max_retries + 1):
            support = _support_block(session, strategy)
            passed, fix_description = _judge(spec, strategy, support)

            if passed:
                _log_attempt(strategy, spec, attempt, "PASS", None, False)
                session.commit()
                break

            fix_description = fix_description or (
                f"Criterion '{spec.name}' not satisfied; revise the strategy to satisfy it."
            )
            will_fix = attempt < max_retries
            if not will_fix:
                _log_attempt(strategy, spec, attempt, "FAIL", fix_description, False)
                session.commit()
                break

            logger.info("pass %s failed (attempt %s) — generating fix", spec.key, attempt)
            try:
                revised = _generate_fix(spec, strategy, fix_description)
            except TruncatedResponseError as exc:
                # The rewrite does not fit even at the retried ceiling. Leave
                # strategy_document EXACTLY as it was and end the pass — the
                # alternative (persisting the partial text) is what corrupted
                # the document in the 2026-08-19 run.
                _log_attempt(
                    strategy, spec, attempt, "FAIL", fix_description, False,
                    conflict={
                        "reason": (
                            f"The revised document for '{spec.name}' exceeded the "
                            f"{exc.limit}-token output ceiling, so the rewrite came "
                            f"back cut off. The document was left unchanged rather "
                            f"than saved in a truncated state. Raise "
                            f"verification_fixer_max_tokens, or split the document."
                        ),
                        "candidates": [*prior_fix_descriptions, fix_description],
                        "output_token_ceiling": exc.limit,
                    },
                )
                session.commit()
                logger.error(
                    "pass %s: fix truncated at %s tokens — document left unchanged",
                    spec.key, exc.limit,
                )
                break

            reverted_index = _reverts_earlier_state(revised, document_history)
            if reverted_index is not None:
                # The loop is arguing with itself: this "fix" recreates a state
                # the pass already tried. Stop now and hand the two competing
                # readings to a human instead of burning the remaining attempts.
                conflict = {
                    "reason": (
                        f"Fix for '{spec.name}' would revert the document to the "
                        f"state it had before attempt {reverted_index + 1}, so the "
                        f"criterion cannot be satisfied by editing the document. "
                        f"Two sources disagree and the reviewer requires both."
                    ),
                    "candidates": [*prior_fix_descriptions, fix_description],
                    "reverts_to_state_before_attempt": reverted_index + 1,
                }
                _log_attempt(strategy, spec, attempt, "FAIL", fix_description,
                             False, conflict=conflict)
                session.commit()
                logger.warning(
                    "pass %s: oscillation detected on attempt %s — fix reverts to an "
                    "earlier state; stopping this pass and flagging conflicting sources",
                    spec.key, attempt,
                )
                break

            if revised:
                strategy.strategy_document = revised
                document_history.append(_normalize_document(revised))
            prior_fix_descriptions.append(fix_description)
            _log_attempt(strategy, spec, attempt, "FAIL", fix_description, bool(revised))
            session.commit()

        if not passed:
            any_exhausted = True
            logger.warning("pass %s did not pass after %s attempts", spec.key, max_retries)

    strategy.status = (
        StrategyStatus.NEEDS_HUMAN_REVIEW if any_exhausted else StrategyStatus.VERIFIED
    )
    session.commit()

    # Tell the owner their strategy finished. notifications.dispatch never
    # raises, so a push failure cannot undo the status transition above.
    owner = notifications.owner_of_strategy(session, strategy)
    if owner is not None:
        notifications.dispatch(
            notifications.notify_strategy_needs_review(owner, strategy.id)
            if any_exhausted
            else notifications.notify_strategy_ready(owner, strategy.id)
        )
    else:
        logger.warning("strategy %s has no resolvable owner - no notification sent",
                       strategy.id)

    return strategy.status

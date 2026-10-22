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
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.db.models import FlowType, PastClient, ResearchStep, Strategy, StrategyStatus
from app.services.anthropic_client import (JUDGE_TEMPERATURE, TruncatedResponseError,
                                            get_client)
from app.services import notifications, prompt_safety, usage_meter
from app.verification.passes import (
    FIXER_MATERIAL,
    FIXER_QUESTION,
    FIXER_SYSTEM,
    JUDGE_MATERIAL,
    JUDGE_QUESTION,
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

# Output contract (Phase 3 item 2) for the judge (JUDGE_SYSTEM in passes.py).
# "result" is required and is the exact key _judge reads; it is a string, not
# an enum, because _judge upper-cases it. Anything but PASS -- a missing or
# unexpected verdict included -- still fails the pass (fail closed).
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "result": {"type": "string"},
        "fix_description": {"type": ["string", "null"]},
    },
    "required": ["result"],
    "additionalProperties": False,
}


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
        # The label is ours; the synthesis is model output built on outside
        # text (scraped posts, headlines, enrichment), so it is data (F-AI-02).
        parts.append(
            f"[{name} research | source {idx} of {totals[name]} | "
            f"phase {r.phase} synthesis | {supersedes}]\n"
            f"{prompt_safety.block(r.output)}"
        )

    if strategy.flow_type is FlowType.WITH_CLIENTS:
        clients = session.execute(
            select(PastClient).where(PastClient.product_id == strategy.product_id)
        ).scalars().all()
        for i, c in enumerate(clients, 1):
            parts.append(
                f"[past-client {i} patterns]\n"
                f"{prompt_safety.block(str(c.extracted_patterns_json))}"
            )
    elif strategy.gtm_document:
        parts.append(f"[GTM PLAN]\n{prompt_safety.block(strategy.gtm_document)}")

    block = "\n\n".join(parts) or "(no supporting research found)"
    return _bounded_support(block)


def _bounded_support(block: str) -> str:
    """Cut the support block to _MAX_SUPPORT_CHARS without leaving an
    EXTERNAL_TEXT block open: a cut that lands inside a block would leave its
    tail looking like it ends the data, so the block is closed again."""
    if len(block) <= _MAX_SUPPORT_CHARS:
        return block
    cut = block[:_MAX_SUPPORT_CHARS]
    if cut.rfind(prompt_safety.OPEN) > cut.rfind(prompt_safety.CLOSE):
        cut = f"{cut}\n{prompt_safety.CLOSE}"
    return cut


def _document_for_prompt(strategy: Strategy) -> str:
    """The strategy document as the judge and fixer see it: data under review,
    between markers (F-AI-02). It is model output built on outside text, and
    after the first fix it is the fixer's own rewrite."""
    if not strategy.strategy_document:
        return "(empty)"
    return prompt_safety.block(strategy.strategy_document)


def _strip_echoed_markers(text: str) -> str:
    """The fixer is told to return the bare document, but a model may echo the
    single marker pair it was given around it. Remove exactly one OUTER pair
    -- the text must start with OPEN and end with CLOSE -- and nothing else, so
    the stored document never carries our markers (it is re-wrapped on the next
    prompt). Markers anywhere else are left alone for the review layer."""
    stripped = text.strip()
    open_, close = prompt_safety.OPEN, prompt_safety.CLOSE
    if (stripped.startswith(open_) and stripped.endswith(close)
            and len(stripped) >= len(open_) + len(close)):
        return stripped[len(open_):len(stripped) - len(close)].strip()
    return text


# ---------------------------------------------------------------------------
# Ship-blocking pass protection (consent hardening, T31)
# ---------------------------------------------------------------------------
# Every fixer rewrites the WHOLE document, but a pass is only ever judged once
# in order. Without this check, a pass-5..10 rewrite that silently drops the
# unsubscribe link, the postal address, the GDPR basis or the WhatsApp
# template/opt-in rule would ship VERIFIED, because pass #4 already said PASS
# about a document that no longer exists.
#
# Design, chosen as the minimal sound one:
# * Only the ship-blocking pass is protected. Pass #4 is the only pass whose
#   criterion says the strategy cannot ship without it; the other passes are
#   quality checks, and re-judging all ten after every rewrite would multiply
#   the judge spend for no legal gain.
# * The re-check is DETERMINISTIC, not another judge call: the compliance
#   elements present in the document pass #4 approved must still be present
#   after every later rewrite. A model re-judge could itself be talked out of
#   the requirement and adds spend; a rule cannot and costs nothing, so the
#   attempt log and usage metering only ever reflect real model calls.
# * It fails closed and is sticky: one rewrite that drops an approved element
#   marks pass #4 FAIL (outcome "compliance_regressed") and the strategy ends
#   NEEDS_HUMAN_REVIEW. A later rewrite restoring the element does not clear
#   it -- a human looks. It is a single check per applied rewrite, so it adds
#   no loop and cannot run unbounded.
# * Presence is a floor, not a full legal review: a rewrite that keeps the
#   words but negates them is not caught here (ASSUMPTION: the pass-#4 judge
#   plus the send-path guards cover that).
SHIP_BLOCKING_PASS_KEY = "legal_compliance"

_COMPLIANCE_ELEMENTS: dict[str, re.Pattern[str]] = {
    "unsubscribe": re.compile(r"\bunsubscribe\b|\bopt[- ]?out\b", re.I),
    "postal address": re.compile(
        r"\b(?:postal|physical|mailing|business|street)\s+address\b", re.I),
    "GDPR lawful basis": re.compile(r"\blawful basis\b|\blegitimate interest\b", re.I),
    "WhatsApp approved template": re.compile(r"\bapproved\s+(?:\w+\s+)?templates?\b", re.I),
    "WhatsApp opt-in": re.compile(r"\bopt(?:ed)?[- ]?in\b", re.I),
}


def _compliance_elements(text: str | None) -> frozenset[str]:
    """Names of the compliance elements the document states."""
    return frozenset(name for name, pattern in _COMPLIANCE_ELEMENTS.items()
                     if pattern.search(text or ""))


def _log_attempt(strategy: Strategy, spec: VerificationPassSpec, attempt: int,
                 result: str, fix_description: str | None, fix_applied: bool,
                 conflict: dict | None = None, outcome: str | None = None) -> None:
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
    if outcome is not None:
        entry["outcome"] = outcome
    strategy.verified_passes_json = [*(strategy.verified_passes_json or []), entry]
    flag_modified(strategy, "verified_passes_json")


def max_attempts_for(strategy: Strategy) -> int:
    """Judge/fix attempts per pass. A budget-fitted (reduced) strategy gets at
    most two -- one judgement and one fix -- because the fixer rewrites the whole
    document and is the single most expensive call in the loop. A pass that still
    fails ends FAIL (needs human review); this never turns a failure into a pass."""
    attempts = settings.verification_max_retries_per_pass
    if getattr(strategy, "steps_per_phase", None):
        attempts = min(attempts, 2)
    return attempts


def _judge(spec: VerificationPassSpec, strategy: Strategy, support: str) -> tuple[bool, str | None]:
    data = get_client().complete_json(
        temperature=JUDGE_TEMPERATURE,
        system=JUDGE_SYSTEM,
        cache_prefix=JUDGE_MATERIAL.format(
            strategy_document=_document_for_prompt(strategy),
            support_block=support,
        ),
        prompt=JUDGE_QUESTION.format(
            pass_no=spec.pass_no,
            name=spec.name,
            criterion=spec.criterion,
            precedence_rule=PRECEDENCE_RULE,
        ),
        schema=JUDGE_SCHEMA,
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
    material = FIXER_MATERIAL.format(strategy_document=_document_for_prompt(strategy))
    prompt = FIXER_QUESTION.format(
        pass_no=spec.pass_no,
        name=spec.name,
        # The finding is the judge's output after reading outside text, so it
        # is wrapped too; it still tells the fixer what to change.
        fix_description=prompt_safety.block(fix_description),
        precedence_rule=PRECEDENCE_RULE,
    )
    ceiling = settings.verification_fixer_max_tokens
    try:
        revised = get_client().complete(
            system=FIXER_SYSTEM, prompt=prompt, max_tokens=ceiling, cache_prefix=material,
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
            cache_prefix=material,
        )
    return _strip_echoed_markers(revised).strip()


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

    The similarity ratio applies only to states BEFORE the current one (the
    last entry). A correct, minimal fix is by nature very similar to the
    document it fixes: on a long document a one-sentence change keeps the
    ratio above the threshold, so comparing with the current state took every
    small fix for a revert (T31). Going back to the current state needs an
    exact match; going back to an earlier one is the oscillation this exists
    to catch.
    """
    normalized = _normalize_document(candidate)
    if not normalized:
        return None
    last = len(history) - 1
    for index, previous in enumerate(history):
        if normalized == previous:
            return index
        if index < last and (SequenceMatcher(None, normalized, previous).ratio()
                             >= _REVERT_SIMILARITY_THRESHOLD):
            return index
    return None


def run_verification_loop(session: Session, strategy: Strategy,
                          max_attempts: int | None = None) -> StrategyStatus:
    """Run all 10 passes with fail→fix→re-run. Returns the final status
    (also written to the strategy row).

    `max_attempts` is an explicit, owner-chosen override of the per-pass attempt
    count (used by POST /strategies/{id}/reverify). It replaces the reduced-plan
    cap of two, never the judge: a pass still has to come back PASS to count."""
    strategy.status = StrategyStatus.VERIFYING
    session.commit()

    max_retries = max_attempts if max_attempts is not None else max_attempts_for(strategy)
    any_exhausted = False
    # Set when the ship-blocking pass (#4) ends PASS: its spec, how many
    # attempts it logged, and the compliance elements of the document it
    # approved. Every later rewrite must keep those elements.
    legal_spec: VerificationPassSpec | None = None
    legal_attempts = 0
    legal_approved: frozenset[str] = frozenset()
    legal_regressed = False

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
            usage_meter.flush_active(session)  # F-AI-01: durable spend

            if passed:
                _log_attempt(strategy, spec, attempt, "PASS", None, False)
                session.commit()
                if spec.key == SHIP_BLOCKING_PASS_KEY:
                    legal_spec, legal_attempts = spec, attempt
                    legal_approved = _compliance_elements(strategy.strategy_document)
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
                try:
                    revised = _generate_fix(spec, strategy, fix_description)
                finally:
                    usage_meter.flush_active(session)  # F-AI-01: durable spend
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

            # Re-check the ship-blocking pass on the rewritten document (see
            # SHIP_BLOCKING_PASS_KEY). Deterministic, no model call.
            if revised and legal_spec is not None and not legal_regressed:
                dropped = sorted(legal_approved - _compliance_elements(revised))
                if dropped:
                    legal_regressed = True
                    legal_attempts += 1
                    _log_attempt(
                        strategy, legal_spec, legal_attempts, "FAIL",
                        f"The rewrite for '{spec.name}' removed compliance elements "
                        f"that '{legal_spec.name}' had approved: {', '.join(dropped)}. "
                        f"Restore them; the strategy cannot ship without them.",
                        False, outcome="compliance_regressed",
                    )
                    session.commit()
                    logger.warning(
                        "pass %s rewrite dropped approved compliance elements %s — "
                        "pass %s marked FAIL", spec.key, dropped, legal_spec.key,
                    )

        if not passed:
            any_exhausted = True
            logger.warning("pass %s did not pass after %s attempts", spec.key, max_retries)

    if legal_regressed:
        # Fail closed: a later rewrite removed what the ship-blocking pass
        # approved, so the strategy never counts as verified.
        any_exhausted = True

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

"""Offline measurement of the Help AI against the golden set. No model, no network.

    python -m scripts.help_center.measure_golden

Prints, for tests/help_center/golden_questions.yaml:

  1. retrieval recall@6 on the answerable items, with every miss;
  2. the mock-mode gate table (BM25 score floor x heading-coverage floor) --
     the measurement behind help_center.MOCK_MIN_SCORE and
     MOCK_MIN_HEADING_COVERAGE;
  3. the before/after table: the OLD 9-entry FAQ (support_kb keyword matching
     at its shipped MIN_MOCK_MATCH_SCORE) vs the NEW corpus (mock mode at the
     shipped thresholds).

Definitions (also in docs/program/help-center-eval.md):
  answered      the mock path returned text instead of the ticket message.
  correct       answered from a chunk listed in the item's `expected`. For the
                old FAQ, its entry id is mapped through LEGACY_FAQ_ALIASES.
  wrong         answered, but not correct -- including EVERY answer to a
                must-refuse item.
  answer rate   answered answerable items / answerable items.
  wrong-answer rate   wrong answers / all answers given (both sets).
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.services import help_center, support_kb  # noqa: E402

GOLDEN = REPO / "tests" / "help_center" / "golden_questions.yaml"


def load_golden() -> dict:
    return yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))


def recall_at_k(golden: dict, k: int = help_center.TOP_K) -> tuple[float, list[dict]]:
    misses = []
    items = golden["answerable"]
    for item in items:
        got = [hit.chunk.id for hit in help_center.retrieve(item["question"], k)]
        if not set(got) & set(item["expected"]):
            misses.append({"id": item["id"], "question": item["question"],
                           "expected": item["expected"], "got": got})
    return 1.0 - len(misses) / len(items), misses


def new_outcome(question: str, min_score: float, min_coverage: float):
    """(answered, chunk_id) for the new corpus's mock path."""
    match = help_center.mock_match(question)
    if (match is None or match.score < min_score
            or match.heading_coverage < min_coverage):
        return False, None
    return True, match.chunk.id


def old_outcome(question: str):
    """(answered, chunk_id) for the old FAQ, mapped through the aliases."""
    entry = support_kb.best_match(question)
    if entry is None:
        return False, None
    return True, help_center.LEGACY_FAQ_ALIASES[entry.id]


def tally(golden: dict, outcome) -> dict:
    answerable = golden["answerable"]
    refuse = golden["must_refuse"]
    answered = correct = wrong_answerable = wrong_refuse = 0
    for item in answerable:
        ok, chunk_id = outcome(item["question"])
        if ok:
            answered += 1
            if chunk_id in item["expected"]:
                correct += 1
            else:
                wrong_answerable += 1
    for item in refuse:
        ok, _chunk_id = outcome(item["question"])
        if ok:
            wrong_refuse += 1
    given = answered + wrong_refuse
    return {
        "answerable": len(answerable), "must_refuse": len(refuse),
        "answered": answered, "correct": correct,
        "wrong_answerable": wrong_answerable, "wrong_refuse": wrong_refuse,
        "answer_rate": answered / len(answerable),
        "correct_rate": correct / len(answerable),
        "wrong_answer_rate": ((wrong_answerable + wrong_refuse) / given) if given else 0.0,
    }


SCORE_GRID = (0.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0, 22.0)
COVERAGE_GRID = (0.0, 0.3, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7)


def main() -> int:
    golden = load_golden()
    recall, misses = recall_at_k(golden)
    print(f"recall@{help_center.TOP_K}: {recall:.3f} "
          f"({len(golden['answerable']) - len(misses)}/{len(golden['answerable'])})")
    for miss in misses:
        print(f"  MISS {miss['id']} {miss['question']!r}\n"
              f"       expected {miss['expected']}\n       got      {miss['got']}")

    print("\nMock gate: score floor (rows) x heading-coverage floor (columns)")
    print("cell = correct/wrong on answerable | must-refuse answered")
    print("score  " + "".join(f"{c:>14}" for c in COVERAGE_GRID))
    for score in SCORE_GRID:
        cells = []
        for cov in COVERAGE_GRID:
            t = tally(golden, lambda q, s=score, c=cov: new_outcome(q, s, c))
            cells.append(f"{t['correct']:>3}/{t['wrong_answerable']:<2}|{t['wrong_refuse']:>2}".rjust(14))
        print(f"{score:>5}  " + "".join(cells))

    old = tally(golden, old_outcome)
    new = tally(golden, lambda q: new_outcome(q, help_center.MOCK_MIN_SCORE,
                                              help_center.MOCK_MIN_HEADING_COVERAGE))
    print("\nBefore/after (mock path, golden set)")
    for name, t in (("old 9-entry FAQ", old), ("new corpus", new)):
        print(f"  {name:<16} answered {t['answered']}/{t['answerable']} "
              f"({t['answer_rate']:.1%}), correct {t['correct']} "
              f"({t['correct_rate']:.1%}), wrong on answerable {t['wrong_answerable']}, "
              f"must-refuse answered {t['wrong_refuse']}/{t['must_refuse']}, "
              f"wrong-answer rate {t['wrong_answer_rate']:.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

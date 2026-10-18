"""Every number a help-center article takes from code is checked against code.

The Help AI answers customers only from docs/help-center/, so a limit, cap,
threshold, retention period or price that drifts from the code becomes a wrong
answer that no other test would catch. tests/help_center/code_facts.yaml lists
them:

  facts    one entry per code-sourced number:
             article  file-name prefix ("24" for 24-workspaces-....md)
             phrase   a verbatim substring of the article containing the number
             expr     a Python expression over `app` (every dotted `app.x.y`
                      path in it is imported before evaluation)
             shows    how the value appears in the phrase, as a format string
                      over `v` (default "{v}"); e.g. "{v:,}", "${v}", "{v:g}%"
  exempt   numbers in an article that do NOT come from code (an example, a
           count of list items written in the article, a vendor's rule), each
           with the phrase and a reason.

Three checks:

1. every fact's phrase is in its article, and the value computed from code,
   rendered with `shows`, is in the phrase -- a changed constant fails here;
2. every number-with-a-unit in the corpus (days, hours, %, $, attempts, ...)
   sits inside some registered phrase, fact or exempt -- a new number cannot
   enter the corpus without a decision about where it comes from;
3. every dollar amount is a fact, never an exemption -- an article may state a
   price only when the price exists in code (STAR_PROMPT 2.1).
"""

from __future__ import annotations

import importlib
import re
from functools import cache
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
HELP = REPO / "docs" / "help-center"
REGISTRY = Path(__file__).with_name("code_facts.yaml")

# A number followed by a unit, or a dollar amount. Plain counts ("two ways",
# "step 3") are not matched: they are prose, not limits.
NUMBER_WITH_UNIT = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?"
    r"|\b\d[\d,]*(?:\.\d+)?\s?(?:%|percent\b|days?\b|hours?\b|minutes?\b|seconds?\b"
    r"|weeks?\b|months?\b|years?\b|attempts?\b|times\b|characters\b|per (?:day|hour|minute)\b"
    r"|emails?\b|messages?\b|leads?\b|steps?\b|MB\b|KB\b|tokens?\b|requests?\b)",
    re.IGNORECASE,
)
DOLLAR = re.compile(r"\$\s?\d")


def _body(path: Path) -> str:
    """Article text without front matter, whitespace collapsed (phrases are
    matched across line wraps)."""
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        text = text.split("\n---", 1)[1]
    return re.sub(r"\s+", " ", text)


@cache
def _registry() -> dict:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


@cache
def _articles() -> dict[str, Path]:
    return {p.name[:2]: p for p in sorted(HELP.glob("[0-9][0-9]-*.md"))
            if not p.name.startswith("00-")}


def _evaluate(expr: str):
    """Evaluate a registry expression. Every dotted `app.x.y` path in it is
    imported first (longest importable module prefix), so attribute access
    such as `app.core.plans.PLANS["growth"]` reaches loaded modules."""
    for path in re.findall(r"\b(app(?:\.[A-Za-z_][A-Za-z0-9_]*)+)", expr):
        pieces = path.split(".")
        for end in range(len(pieces), 1, -1):
            try:
                importlib.import_module(".".join(pieces[:end]))
                break
            except ModuleNotFoundError:
                continue
    return eval(expr, {"app": importlib.import_module("app")})  # noqa: S307 - repo-owned registry


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _facts():
    return [pytest.param(f, id=f"{f['article']}:{f['phrase'][:40]}") for f in _registry()["facts"]]


def test_registry_shape():
    reg = _registry()
    assert set(reg) == {"facts", "exempt"}, set(reg)
    for entry in reg["facts"]:
        assert {"article", "phrase", "expr"} <= set(entry) <= {"article", "phrase", "expr", "shows"}, entry
    for entry in reg["exempt"]:
        assert set(entry) == {"article", "phrase", "reason"}, entry
        assert entry["reason"].strip(), entry


@pytest.mark.parametrize("fact", _facts())
def test_fact_matches_code(fact):
    article = _articles().get(str(fact["article"]))
    assert article is not None, f"no article {fact['article']}"
    phrase = _norm(fact["phrase"])
    assert phrase in _body(article), f"phrase not in {article.name}: {phrase!r}"
    value = _evaluate(fact["expr"])
    shown = fact.get("shows", "{v}").format(v=value)
    assert shown in phrase, (
        f"{article.name}: code says {fact['expr']} = {value!r} (shown as {shown!r}), "
        f"article says {phrase!r}")


def test_exempt_phrases_exist_and_are_not_prices():
    for entry in _registry()["exempt"]:
        article = _articles().get(str(entry["article"]))
        assert article is not None, entry
        phrase = _norm(entry["phrase"])
        assert phrase in _body(article), f"exempt phrase not in {article.name}: {phrase!r}"
        assert not DOLLAR.search(phrase), (
            f"{article.name}: a price cannot be exempt -- it must come from code: {phrase!r}")


def test_every_number_with_a_unit_is_registered():
    reg = _registry()
    covered: dict[str, list[str]] = {}
    for entry in reg["facts"] + reg["exempt"]:
        covered.setdefault(str(entry["article"]), []).append(_norm(entry["phrase"]))
    missing = []
    for prefix, path in _articles().items():
        body = _body(path)
        spans = []
        for phrase in covered.get(prefix, []):
            start = body.find(phrase)
            while start != -1:
                spans.append((start, start + len(phrase)))
                start = body.find(phrase, start + 1)
        for match in NUMBER_WITH_UNIT.finditer(body):
            if not any(s <= match.start() and match.end() <= e for s, e in spans):
                context = body[max(0, match.start() - 40): match.end() + 20]
                missing.append(f"{path.name}: {match.group(0)!r} in ...{context}...")
    assert not missing, (
        "numbers not registered in tests/help_center/code_facts.yaml "
        f"({len(missing)}):\n" + "\n".join(missing))

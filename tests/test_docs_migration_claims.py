"""GAP-106 -- docs must not state migration facts that are false.

LAUNCH_CHECKLIST.md said "all 11 migrations" and "head 0011_m8c5" while the
chain had 66 files; CLAUDE.md carried a different stale count. A launch gate
that tells the operator the wrong head makes a correct database look wrong.

Deliberately NOT asserting an exact count here: a doc that hard-codes "66" is
stale again the moment a migration merges. The docs now point at `alembic
heads`, and these tests (a) forbid the known-stale literals and (b) require
that any migration revision id a doc names actually exists.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = ["LAUNCH_CHECKLIST.md", "CLAUDE.md"]
REVISION = re.compile(r"\b(00\d\d_[a-z0-9_]+)\b")


def _revisions_on_disk() -> set[str]:
    return {p.stem for p in (REPO / "alembic" / "versions").glob("00*.py")}


def test_the_known_stale_literals_are_gone():
    checklist = (REPO / "LAUNCH_CHECKLIST.md").read_text(encoding="utf-8")
    assert "0011_m8c5" not in checklist
    assert "all 11 migrations" not in checklist
    claude = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    assert "0001…0047 (49 files)" not in claude


def test_every_revision_a_doc_names_exists():
    on_disk = _revisions_on_disk()
    missing = []
    for name in DOCS:
        text = (REPO / name).read_text(encoding="utf-8")
        for rev in set(REVISION.findall(text)):
            if rev not in on_disk:
                missing.append(f"{name}: {rev}")
    assert missing == [], missing


def test_the_launch_checklist_tells_the_operator_how_to_find_the_head():
    text = (REPO / "LAUNCH_CHECKLIST.md").read_text(encoding="utf-8")
    assert "alembic heads" in text

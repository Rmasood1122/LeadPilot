"""The public contact page's LinkedIn answer names exactly the plans whose
channel list includes LinkedIn (app/core/plans.py), so a plan change that adds
or removes LinkedIn fails here until the page says the same. Legacy `pro` is
not sold and is not named on the site."""

from __future__ import annotations

import re
from pathlib import Path

from app.core.plans import PLANS

PAGE = Path(__file__).resolve().parents[1] / "frontend" / "src" / "app" / "contact" / "page.tsx"
NOT_SOLD = {"pro"}


def _linkedin_answer() -> str:
    src = PAGE.read_text(encoding="utf-8")
    match = re.search(r'q: "Do I need to be on LinkedIn\?",\s*a: "([^"]+)"', src)
    assert match, "LinkedIn FAQ entry not found"
    return match.group(1)


def test_every_plan_with_linkedin_is_named():
    answer = _linkedin_answer()
    for key, plan in PLANS.items():
        if key in NOT_SOLD or "linkedin" not in plan["channels"]:
            continue
        assert plan["display_name"] in answer, plan["display_name"]


def test_no_plan_without_linkedin_is_named():
    answer = _linkedin_answer()
    for key, plan in PLANS.items():
        if "linkedin" not in plan["channels"]:
            assert re.search(rf"\b{re.escape(plan['display_name'])}\b", answer) is None, key

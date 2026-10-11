"""Product defect #22: GET /onboarding/state links each step to a page, but
four of the seven links (/products/new, /settings/integrations, /leads,
/leads?filter=...) were routes the web app does not have. Every link must be a
real page of the static Next.js export.

The OnboardingChecklist component that rendered these links was never mounted
anywhere and was deleted (see docs/program/fixes/product-defects.md #22).
"""

from pathlib import Path
from urllib.parse import urlparse

import pytest

from app.api.onboarding import ONBOARDING_STEPS, STEP_ACTIONS

APP = Path(__file__).resolve().parents[1] / "frontend" / "src" / "app"


def _pages() -> set[str]:
    routes = set()
    for page in APP.rglob("page.tsx"):
        parts = [p for p in page.parent.relative_to(APP).parts
                 if not (p.startswith("(") and p.endswith(")"))]
        routes.add("/" + "/".join(parts))
    return routes


@pytest.mark.parametrize("step", ONBOARDING_STEPS)
def test_every_step_links_to_a_real_page(step):
    href = STEP_ACTIONS[step]["href"]
    assert urlparse(href).path in _pages(), f"{step}: {href} is not a page"


def test_the_detector_finds_known_pages():
    assert {"/strategies/new", "/campaigns", "/inbox", "/settings"} <= _pages()

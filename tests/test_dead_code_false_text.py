"""Product defect #24: dead code that stated false things.

* frontend/src/components/kanban/LeadDrawer.tsx -- never imported (the
  pipeline page has its own drawer); its GDPR button toasted "Lead and all
  associated data deleted", but erasure keeps a tombstone row and the message
  history (help center article 21).
* frontend/src/components/ui/PullToRefresh.tsx -- never imported anywhere.
* app/api/whatsapp_optin.py::optin_url -- never called; its docstring said it
  was "used by email footers".
Deleted after an exhaustive search (bare names, string forms, dynamic imports,
tests, docs, SDK). This keeps the false sentence from coming back.
"""

from pathlib import Path

import app.api.whatsapp_optin as whatsapp_optin_api

FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "src"


def test_no_ui_claims_erasure_deletes_all_associated_data():
    offenders = [p for p in FRONTEND.rglob("*.tsx")
                 if "all associated data deleted" in p.read_text(encoding="utf-8")]
    assert offenders == []


def test_dead_modules_are_gone():
    assert not (FRONTEND / "components" / "kanban" / "LeadDrawer.tsx").exists()
    assert not (FRONTEND / "components" / "ui" / "PullToRefresh.tsx").exists()
    assert not hasattr(whatsapp_optin_api, "optin_url")
    # gaps-sweep-2 #10: no importer, no dynamic import, no string reference,
    # no test, no doc (proved before deleting; see docs/program/fixes/gaps-sweep-2.md).
    assert not (FRONTEND / "lib" / "api" / "onboarding.ts").exists()
    assert not (FRONTEND / "components" / "kanban" / "StrategyPicker.tsx").exists()


REPO = Path(__file__).resolve().parents[1]
DELETED = ("components/onboarding/OnboardingChecklist", "components/ui/PullToRefresh",
           "components/kanban/LeadDrawer", "lib/api/onboarding", "kanban/StrategyPicker",
           "onboardingApi")


def test_no_stale_reference_to_a_deleted_module():
    """Review L2: the parked integration-pending page still imported the
    deleted checklist, and the M7 README listed PullToRefresh as built."""
    offenders = []
    for path in [*(REPO / "frontend").rglob("*.ts*"), *(REPO / "frontend").rglob("*.md"),
                 REPO / "docs" / "README_M7_CHUNKS_2_3.md"]:
        if "node_modules" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        offenders += [f"{path.relative_to(REPO)}: {d}" for d in DELETED if d in text]
    assert offenders == []


def test_launch_checklist_marks_the_checklist_item_superseded():
    lines = [line for line in (REPO / "LAUNCH_CHECKLIST.md").read_text(encoding="utf-8").splitlines()
             if "OnboardingChecklist" in line]
    assert lines and all("SUPERSEDED" in line for line in lines)

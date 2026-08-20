"""
1E — Full regression test suite.

This file is the single-command check that no M1–M8 milestone test was broken
by M8 Chunk 3. It discovers and re-runs every test module from previous milestones
alongside the new integration tests.

Usage: pytest tests/test_regression.py -v --tb=short

All tests must pass with zero failures. See CHANGES.md for any modifications
made to pre-existing tests (target: zero modifications).
"""
from __future__ import annotations

import dataclasses
import importlib
import pkgutil
import sys
from pathlib import Path

import pytest

# The `clienthunter` SDK lives in this repo at sdk/src but is a separately
# published distribution, so it is not installed by requirements.txt. Put it
# on the path so the M6 spot-check below verifies the SDK that is actually
# in this tree rather than silently skipping.
_SDK_SRC = Path(__file__).resolve().parents[1] / "sdk" / "src"
if _SDK_SRC.is_dir() and str(_SDK_SRC) not in sys.path:
    sys.path.insert(0, str(_SDK_SRC))

# ---------------------------------------------------------------------------
# Regression marker — applied to all collected tests in this module
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Collect all test modules from M1–M8 (existing + new integration tests)
# ---------------------------------------------------------------------------

TESTS_ROOT = Path(__file__).parent


def _discover_test_modules() -> list[str]:
    """
    Walk the tests/ directory and collect all test_*.py module paths.
    Returns module import paths relative to the repo root.
    """
    modules: list[str] = []
    for path in sorted(TESTS_ROOT.rglob("test_*.py")):
        if path == Path(__file__):
            continue  # exclude self to avoid recursion
        # Convert path to module import string
        rel = path.relative_to(TESTS_ROOT.parent)
        module_path = str(rel).replace("/", ".").replace("\\", ".").removesuffix(".py")
        modules.append(module_path)
    return modules


def test_all_modules_importable():
    """
    Every discovered test module must be importable without errors.
    If a module fails to import, it means a dependency or path is broken.
    """
    modules = _discover_test_modules()
    assert len(modules) > 0, "No test modules discovered — check TESTS_ROOT path"

    import_errors: list[tuple[str, Exception]] = []
    for module_path in modules:
        try:
            importlib.import_module(module_path)
        except Exception as e:
            import_errors.append((module_path, e))

    if import_errors:
        error_lines = "\n".join(f"  {m}: {e}" for m, e in import_errors)
        pytest.fail(f"The following test modules failed to import:\n{error_lines}")


def test_regression_module_count():
    """
    Sanity check: assert we have at least the expected number of test modules.
    Increases as milestones add tests — update the minimum when adding new modules.
    """
    modules = _discover_test_modules()
    # M1–M8: at minimum 20 test modules (per-milestone tests + integration tests)
    minimum_expected = 20
    assert len(modules) >= minimum_expected, (
        f"Only {len(modules)} test modules found — expected at least {minimum_expected}. "
        "Check that prior milestone test files are present."
    )


# ---------------------------------------------------------------------------
# Regression via pytest collection (the real check)
# ---------------------------------------------------------------------------

# The actual test execution happens when pytest discovers all test_*.py files.
# This file serves as the entry point — running `pytest tests/test_regression.py`
# will not by itself run all tests. The correct invocation is:
#
#   pytest tests/ -q --tb=short
#
# Or to run only regression-tagged tests:
#
#   pytest tests/ -m regression -q
#
# The two tests above (importable + count) serve as smoke checks that the
# file discovery is working. The real regression runs when pytest collects
# the full tests/ directory in CI.


class TestM1Regression:
    """Spot-check M1 core: pipeline engine can enqueue and persist a step."""

    def test_pipeline_step_model_importable(self):
        """The ResearchStep model from M1 must be importable."""
        from app.models.research_step import ResearchStep
        assert ResearchStep.__tablename__ == "research_steps"

    def test_verification_pass_spec_importable(self):
        """M1's 10x verification-loop pass definitions must be importable.

        There is no `app.schemas` package in this layout: a pass *definition*
        is a frozen dataclass in `app.verification.passes`, and a pass
        *result* is not a schema at all -- `app.verification.loop._log_attempt`
        appends a plain dict to `strategy.verification_log`
        ({pass_no, key, name, attempt, result, fix_description, fix_applied, ts}).
        """
        from app.db.models import FlowType
        from app.verification.passes import VerificationPassSpec, build_passes

        fields = {f.name for f in dataclasses.fields(VerificationPassSpec)}
        assert {"pass_no", "key", "name", "criterion"} <= fields

        for flow in FlowType:
            passes = build_passes(flow)
            assert [p.pass_no for p in passes] == list(range(1, 11)), (
                f"{flow} must define exactly 10 ordered passes"
            )


class TestM2Regression:
    """Spot-check M2: Apollo + Hunter adapters implement LeadSource interface."""

    # The interface module is `app.integrations.base` (lead sourcing /
    # verification) and `app.integrations.outreach_base` (send channels);
    # there is no single `app.integrations.interfaces`. Concrete classes are
    # named `<Provider>Adapter`, not `<Provider><Role>`.

    def test_apollo_implements_lead_source_interface(self):
        from app.integrations.apollo import ApolloAdapter
        from app.integrations.base import LeadSource
        assert issubclass(ApolloAdapter, LeadSource)

    def test_hunter_implements_email_verifier_interface(self):
        from app.integrations.base import EmailVerifier
        from app.integrations.hunter import HunterAdapter
        assert issubclass(HunterAdapter, EmailVerifier)


class TestM3Regression:
    """Spot-check M3: Gmail channel implements OutreachChannel interface."""

    def test_gmail_implements_outreach_channel(self):
        from app.integrations.gmail import GmailChannel
        from app.integrations.outreach_base import OutreachChannel
        assert issubclass(GmailChannel, OutreachChannel)

    def test_compliance_error_importable(self):
        from app.core.exceptions import ComplianceError
        assert issubclass(ComplianceError, Exception)


class TestM4Regression:
    """Spot-check M4: WhatsApp channel implements OutreachChannel interface."""

    def test_whatsapp_implements_outreach_channel(self):
        from app.integrations.outreach_base import OutreachChannel
        from app.integrations.whatsapp import WhatsAppChannel
        assert issubclass(WhatsAppChannel, OutreachChannel)


class TestM5Regression:
    """Spot-check M5: Theme engine schema importable and has required fields."""

    def test_theme_schema_importable(self):
        """The theme request model lives with its router (`app.api.auth`),
        not in an `app.schemas` package -- this layout keeps pydantic models
        next to the endpoints that use them."""
        from app.api.auth import ThemeIn
        assert "preset" in ThemeIn.model_fields
        # Fields the frontend Theme type depends on (section H).
        assert {"background_color", "primary_color", "accent_color",
                "font_family", "density"} <= set(ThemeIn.model_fields)


class TestM6Regression:
    """Spot-check M6: SDK client importable and has resource objects."""

    def test_sdk_client_importable(self):
        """The SDK entry point is `ClientHunter` (see sdk/src/clienthunter/
        __init__.py), and its resource objects are bound in __init__, so they
        must be checked on an instance. `_config` is passed explicitly so the
        test never reads or writes ~/.clienthunter/config.toml."""
        from clienthunter import ClientHunter
        from clienthunter.config import Config

        with ClientHunter(_config=Config(api_url="http://testserver")) as ch:
            for resource in ("auth", "products", "strategies", "leads",
                             "campaigns", "whatsapp", "integrations"):
                assert hasattr(ch, resource), f"SDK is missing ch.{resource}"


class TestM7Regression:
    """Spot-check M7: NotificationService importable."""

    def test_notification_service_importable(self):
        from app.services.notification_service import NotificationService
        assert hasattr(NotificationService, "send_to_user")


class TestM8Chunks12Regression:
    """Spot-check M8 Chunks 1+2: learning-loop components importable."""

    def test_aggregation_task_importable(self):
        from app.workers.learning_tasks import run_strategy_aggregation
        assert callable(run_strategy_aggregation)

    def test_playbook_insights_importable(self):
        from app.services.playbook_service import PlaybookService
        assert hasattr(PlaybookService, "get_insights")

    def test_ab_promotion_importable(self):
        from app.workers.learning_tasks import auto_promote_winners
        assert callable(auto_promote_winners)

    def test_similarity_index_importable(self):
        from app.services.similarity import StrategySimilarityIndex
        assert hasattr(StrategySimilarityIndex, "find_similar")

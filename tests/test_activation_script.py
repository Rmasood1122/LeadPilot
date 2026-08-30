"""scripts/activate_with_keys.py — the runner logic, with ZERO network calls.

Every check in that script talks to a paid API, a live database, or sends real
mail, so none of them are exercised here. What IS exercised is the part that
decides what happens: ordering, stop-at-first-failure, the migration prompt,
and the exact output the operator reads. Those are the parts that would
silently do the wrong thing.

The one check tested for real is the placeholder/empty-key detection, because
it returns before any client is constructed and therefore cannot reach the
network — verified by the no_network fixture below, which makes any attempt to
open a socket raise.
"""

import socket

import pytest

from scripts import activate_with_keys as act


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any socket use in this module is a test bug. Make it loud.

    Without this the suite could start billing a real API the moment someone
    adds a case that forgets to stub a check.
    """
    def _boom(*_a, **_kw):
        raise AssertionError("a test tried to open a network connection")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)


def _check(name, ok, **kw):
    """Build a (name, fn, needs_network) triple returning a fixed result."""
    return (name, lambda ctx: act.CheckResult(ok, kw.pop("detail", ""), **kw),
            False)


def _run(checks, **kw):
    lines: list[str] = []
    code = act.run_checks(checks, out=lines.append, **kw)
    return code, "\n".join(lines)


# --------------------------------------------------------------------------
# Ordering and stop-on-failure
# --------------------------------------------------------------------------


class TestRunner:
    def test_all_passing_reports_production_ready(self):
        code, out = _run([_check("A", True), _check("B", True)])
        assert code == act.EXIT_OK
        assert "ALL SYSTEMS ACTIVE" in out
        assert "production-ready" in out

    def test_stops_at_the_FIRST_failure(self):
        """Later checks assume the earlier ones are true — running them after a
        failure produces noise that hides the one thing to fix."""
        ran: list[str] = []

        def tracker(name, ok):
            def fn(ctx):
                ran.append(name)
                return act.CheckResult(ok, name)
            return (name, fn, False)

        code, out = _run([tracker("first", True), tracker("second", False),
                          tracker("third", True)])
        assert code == act.EXIT_CHECK_FAILED
        assert ran == ["first", "second"]      # "third" never ran
        assert "third" not in out

    def test_failure_names_the_check_and_the_fix(self):
        code, out = _run([_check("Resend API key", False,
                                 detail="rejected the key (401).",
                                 fix="Generate a new key at resend.com")])
        assert code == act.EXIT_CHECK_FAILED
        assert "ACTIVATION INCOMPLETE" in out
        assert "Failed at: CHECK 1 - Resend API key" in out
        assert "Generate a new key at resend.com" in out
        assert "Run this script again after fixing." in out

    def test_checks_are_numbered_in_order(self):
        code, out = _run([_check("A", True), _check("B", True),
                          _check("C", False, fix="x")])
        assert "CHECK 1 - A" in out
        assert "CHECK 2 - B" in out
        assert "CHECK 3 - C" in out

    def test_a_crashing_check_is_a_failure_not_a_traceback(self):
        """An unhandled exception must not look like a pass, and must not dump
        a traceback at an operator who just wants to know what to fix."""
        def explode(ctx):
            raise RuntimeError("boom")

        code, out = _run([("Exploding", explode, False)])
        assert code == act.EXIT_CHECK_FAILED
        assert "RuntimeError: boom" in out
        assert "bug in the check itself" in out

    def test_proof_lines_are_printed_for_passes_and_failures(self):
        _, passing = _run([_check("A", True, proof=["    PASS  something"])])
        assert "PASS  something" in passing
        _, failing = _run([_check("B", False, fix="f",
                                  proof=["    FAIL  something"])])
        assert "FAIL  something" in failing


# --------------------------------------------------------------------------
# Dry run
# --------------------------------------------------------------------------


class TestDryRun:
    def test_skips_every_network_check(self):
        """The whole point: let an operator sanity-check config without
        spending a request or touching the database."""
        called: list[str] = []

        def should_not_run(ctx):
            called.append("ran")
            return act.CheckResult(True)

        code, out = _run([("Networked", should_not_run, True)], dry_run=True)
        assert code == act.EXIT_OK
        assert called == []
        assert "SKIP" in out
        assert "needs network/database" in out

    def test_still_runs_offline_checks(self):
        called: list[str] = []

        def offline(ctx):
            called.append("ran")
            return act.CheckResult(True, "offline ok")

        _, out = _run([("Offline", offline, False)], dry_run=True)
        assert called == ["ran"]
        assert "offline ok" in out

    def test_does_not_claim_production_ready(self):
        """A dry run verifies nothing against a live service, so it must not
        print the sentence that says everything works."""
        _, out = _run([("Networked", lambda c: act.CheckResult(True), True)],
                      dry_run=True)
        assert "ALL SYSTEMS ACTIVE" not in out
        assert "DRY RUN COMPLETE" in out
        assert "nothing was verified against a live service" in out

    def test_the_real_check_list_is_mostly_networked(self):
        needs_network = [n for n, _f, net in act.CHECKS if net]
        assert len(needs_network) >= 7


# --------------------------------------------------------------------------
# Placeholder / missing key detection (runs for real — no network reachable)
# --------------------------------------------------------------------------


class TestKeyValidation:
    @pytest.mark.parametrize("value,expected", [
        ("", "is not set"),
        ("[tumhara key yahan]", "placeholder"),
        ("your_key", "placeholder"),
    ])
    def test_anthropic_rejects_missing_or_placeholder_keys(
        self, monkeypatch, value, expected
    ):
        """These are the exact values that were pasted into this project
        earlier and looked like configuration. They must never reach the API."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", value)
        result = act.check_anthropic({})
        assert result.ok is False
        assert expected in result.detail
        assert result.fix

    @pytest.mark.parametrize("value,expected", [
        ("", "is not set"),
        ("[tumhara key yahan]", "placeholder"),
        ("your_key", "placeholder"),
    ])
    def test_resend_rejects_missing_or_placeholder_keys(
        self, monkeypatch, value, expected
    ):
        monkeypatch.setenv("RESEND_API_KEY", value)
        result = act.check_resend_key({})
        assert result.ok is False
        assert expected in result.detail

    def test_database_check_requires_a_url(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "")
        result = act.check_database({})
        assert result.ok is False
        assert "DATABASE_URL is not set" in result.detail

    def test_test_email_refuses_a_non_delivering_provider(self, monkeypatch):
        """console and memory accept the send and deliver nothing — exactly the
        silent failure this check exists to catch."""
        monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
        monkeypatch.setenv("EMAIL_PROVIDER", "console")
        result = act.check_test_email({})
        assert result.ok is False
        assert "not 'resend'" in result.detail
        assert "deliver nothing" in result.fix


# --------------------------------------------------------------------------
# The migration prompt — the only destructive step
# --------------------------------------------------------------------------


class TestMigrationPrompt:
    def test_declining_changes_nothing(self, monkeypatch):
        monkeypatch.setattr(act.subprocess, "run", lambda *a, **k:
                            pytest.fail("migration ran despite 'no'"))
        result = act.check_migrations({"db_revision": "0014_x",
                                       "confirm": lambda _p: "no"})
        assert result.ok is False
        assert "NOTHING WAS CHANGED" in result.detail
        assert "pg_dump" in result.fix     # tells them how to back up first

    @pytest.mark.parametrize("answer", ["n", "", "maybe", "YES please", "0"])
    def test_only_an_explicit_yes_proceeds(self, monkeypatch, answer):
        """Anything ambiguous must be treated as "no". A live migration is not
        something to infer from a typo."""
        monkeypatch.setattr(act.subprocess, "run", lambda *a, **k:
                            pytest.fail("migration ran on answer %r" % answer))
        result = act.check_migrations({"db_revision": "0014_x",
                                       "confirm": lambda _p: answer})
        assert result.ok is False

    def test_already_at_head_does_not_prompt_at_all(self):
        def no_prompt(_p):
            pytest.fail("prompted even though the database is already at head")

        result = act.check_migrations({"db_revision": act.TARGET_REVISION,
                                       "confirm": no_prompt})
        assert result.ok is True
        assert "nothing to do" in result.detail

    def test_the_prompt_states_the_current_and_target_revision(self):
        seen: list[str] = []
        act.check_migrations({"db_revision": "0014_strategy_pattern_inputs",
                              "confirm": lambda p: seen.append(p) or "no"})
        assert "0014_strategy_pattern_inputs" in seen[0]
        assert act.TARGET_REVISION in seen[0]


# --------------------------------------------------------------------------
# Thresholds and constants
# --------------------------------------------------------------------------


class TestConstants:
    def test_target_revision_matches_the_latest_migration(self):
        """If a migration is added and this is not updated, the script would
        happily report success against a database missing the new tables."""
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
        assert act.TARGET_REVISION in heads

    def test_adversarial_threshold_is_28_of_32(self):
        assert act.ADVERSARIAL_MIN_PASS == 28
        assert act.ADVERSARIAL_TOTAL == 32

    def test_exit_codes_distinguish_failure_from_abort(self):
        assert act.EXIT_OK == 0
        assert act.EXIT_CHECK_FAILED == 1
        assert act.EXIT_ABORTED == 2


# --------------------------------------------------------------------------
# AI_MODE guard (Task 4)
# --------------------------------------------------------------------------


class TestAiModeCheck:
    """Guards the trap where activation grades the FAQ matcher, not the model."""

    @pytest.fixture(autouse=True)
    def _settings(self, monkeypatch):
        from app.config import settings as app_settings
        self.settings = app_settings
        monkeypatch.setattr(app_settings, "ai_mode", "")
        monkeypatch.setattr(app_settings, "anthropic_api_key", "")

    def test_unset_mode_with_a_key_passes(self):
        self.settings.anthropic_api_key = "sk-ant-real"
        result = act.check_ai_mode({})
        assert result.ok
        assert "resolves it to live" in result.detail

    def test_explicit_live_passes(self):
        self.settings.ai_mode = "live"
        assert act.check_ai_mode({}).ok

    @pytest.mark.parametrize("mode", ["mock", "console"])
    def test_a_pinned_non_live_mode_FAILS_even_with_a_valid_key(self, mode):
        """The whole point. A valid key does not save you here: the pinned
        mode means Anthropic is never called, so the adversarial check would
        score the keyword matcher and report the model as safe."""
        self.settings.ai_mode = mode
        self.settings.anthropic_api_key = "sk-ant-real"
        result = act.check_ai_mode({})
        assert not result.ok
        assert mode in result.detail
        assert "AI_MODE=live" in result.fix

    def test_no_key_and_no_mode_fails_rather_than_silently_mocking(self):
        result = act.check_ai_mode({})
        assert not result.ok
        assert "'mock'" in result.detail

    def test_it_runs_before_the_adversarial_check(self):
        """Ordering is the guard. After it, the wrong thing is already
        measured and reported green."""
        names = [name for name, _fn, _net in act.CHECKS]
        assert names.index("AI mode resolves to live") < \
            names.index("Adversarial AI behaviour")

    def test_it_needs_no_network(self):
        """So --dry-run still exercises it for real."""
        needs_network = dict((name, net) for name, _fn, net in act.CHECKS)
        assert needs_network["AI mode resolves to live"] is False

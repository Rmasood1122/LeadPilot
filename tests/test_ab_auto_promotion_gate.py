"""Review M5: A/B auto-promotion is off by default.

`auto_promote_winners` writes a permanent `ab_promoted` marker (one per
strategy, never revisited) and sets strategies.default_variant. With outcome
attribution now feeding it real data (product defect #2) it would start
promoting -- but step variants are labels on different sequences, not
randomised arms, so a "winner" may only reflect who was enrolled where. The
sweep therefore runs only when an admin turns on `ab_auto_promotion_enabled`.
"""

from app.services import system_settings
from app.workers import learning_tasks


def test_the_flag_exists_and_defaults_off():
    default, description = system_settings.DEFAULTS["ab_auto_promotion_enabled"]
    assert default is False
    assert "randomised" in description or "randomized" in description


def test_the_sweep_does_nothing_while_off(db_session, monkeypatch):
    from app.core import database

    monkeypatch.setattr(database, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    real_execute = db_session.execute

    def _execute(statement, *a, **k):
        assert "outcomes" not in str(statement), "queried the outcomes while disabled"
        return real_execute(statement, *a, **k)

    monkeypatch.setattr(db_session, "execute", _execute)
    out = learning_tasks.auto_promote_winners.run()
    assert out == {"promoted": 0, "skipped": "ab_auto_promotion_enabled is off"}

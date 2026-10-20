"""GET /playbook/scores -- the user-facing twin of P0-6's admin endpoint.

The handler wrapped its query in `except Exception: return []`, so any
database error reached a paying customer as a 200 with an empty list --
indistinguishable from "no data yet". The query itself is valid; only the
swallowing is the defect.

What must hold:
  * the caller gets the rows for their own strategies' pattern keys, and
    nothing else;
  * F-DB-01: a row is the caller's only if they OWN it (playbook_scores
    .user_id). Another account's row on the same pattern_key, and a pre-0093
    pooled row (user_id NULL), are never returned;
  * a database error is a 500, never an empty 200.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import models as m


@pytest.fixture()
def paid_user(db_session, test_user):
    # playbook_access is off on the free plan (app/core/plans.py).
    test_user.plan = m.PlanTier.STARTER
    db_session.commit()
    return test_user


def _strategies(db_session, user, *pattern_keys):
    product = m.Product(user_id=user.id, name="P", description="d",
                        type=m.ProductType.PRODUCT)
    db_session.add(product)
    db_session.flush()
    for key in pattern_keys:
        db_session.add(m.Strategy(product_id=product.id, flow_type=m.FlowType.NO_CLIENTS,
                                  pattern_key=key))
    db_session.commit()


def _score(db_session, owner, pattern_key, variant, reply_rate):
    db_session.add(m.PlaybookScore(user_id=owner.id if owner else None,
                                   pattern_key=pattern_key, variant=variant, score=reply_rate,
                                   reply_rate=reply_rate, booking_rate=0.01, sample_size=40,
                                   is_reliable=True))


@pytest.fixture()
def other_user(db_session):
    other = m.User(email="other@agency.test", email_verified=True)
    db_session.add(other)
    db_session.flush()
    return other


@pytest.fixture()
def seeded(db_session, paid_user, other_user):
    _strategies(db_session, paid_user, "pk-mine")
    _strategies(db_session, other_user, "pk-theirs")
    _score(db_session, paid_user, "pk-mine", "A", 0.12)
    _score(db_session, paid_user, "pk-mine", "B", 0.08)
    _score(db_session, other_user, "pk-theirs", "A", 0.05)
    db_session.commit()
    return paid_user


def test_returns_only_the_callers_rows(client, seeded):
    # Must hold on SQLite AND Postgres. The raw-SQL version bound
    # str(current_user.id) (dashed), which matched nothing on SQLite, where
    # Uuid is stored as 32 undashed hex digits.
    resp = client.get("/playbook/scores")
    assert resp.status_code == 200, resp.text
    assert sorted((r["pattern_key"], r["variant"]) for r in resp.json()) == [
        ("pk-mine", "A"), ("pk-mine", "B")]


def test_strategy_filter(client, seeded, db_session):
    other = m.Strategy(product_id=db_session.query(m.Product.id)
                       .filter(m.Product.user_id == seeded.id).scalar(),
                       flow_type=m.FlowType.NO_CLIENTS, pattern_key="pk-mine-2")
    db_session.add(other)
    _score(db_session, seeded, "pk-mine-2", "A", 0.30)
    db_session.commit()
    resp = client.get(f"/playbook/scores?strategy_id={other.id}")
    assert resp.status_code == 200, resp.text
    assert [(r["pattern_key"], r["strategy_id"]) for r in resp.json()] == [
        ("pk-mine-2", str(other.id))]


def test_another_accounts_row_on_a_shared_pattern_key_is_not_returned(
        client, seeded, other_user, db_session):
    # F-DB-01: both accounts run a strategy with the same pattern_key. Before
    # 0093 the key alone decided ownership, so the caller saw the other
    # account's rates for it.
    _strategies(db_session, other_user, "pk-mine")
    _score(db_session, other_user, "pk-mine", "C", 0.90)
    _score(db_session, None, "pk-mine", "D", 0.70)   # pre-0093 pooled row
    db_session.commit()
    resp = client.get("/playbook/scores")
    assert resp.status_code == 200, resp.text
    assert sorted((r["pattern_key"], r["variant"]) for r in resp.json()) == [
        ("pk-mine", "A"), ("pk-mine", "B")]


def test_malformed_strategy_id_is_422(client, seeded):
    assert client.get("/playbook/scores?strategy_id=not-a-uuid").status_code == 422


def test_free_plan_is_refused(client, db_session, test_user):
    assert client.get("/playbook/scores").status_code == 402


def test_a_db_error_is_a_500_not_an_empty_200(client, seeded, db_session):
    from app.main import app

    db_session.execute(text("DROP TABLE playbook_scores"))
    db_session.commit()
    # Same app, same dependency overrides as `client`; only exception
    # propagation differs, so the test sees the response a caller would.
    with TestClient(app, raise_server_exceptions=False) as raw:
        raw.headers.update(client.headers)
        resp = raw.get("/playbook/scores")
    assert resp.status_code == 500
    assert resp.text != "[]"


# ---------------------------------------------------------------------------
# F-DB-01: the learning loop is per account end to end -- the nightly
# aggregation, the pipeline prompt block and the lead-scoring factor.
# ---------------------------------------------------------------------------

def _strategy(db_session, user, pattern_key):
    product = m.Product(user_id=user.id, name="P", description="d",
                        type=m.ProductType.PRODUCT)
    db_session.add(product)
    db_session.flush()
    strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.NO_CLIENTS,
                          pattern_key=pattern_key)
    db_session.add(strategy)
    db_session.flush()
    return strategy


def _outcomes(db_session, strategy, *, sends, replies, prefix):
    """`sends` leads were sent variant A; the first `replies` of them replied."""
    for i in range(sends):
        lead = m.Lead(strategy_id=strategy.id, source="manual", external_id=f"{prefix}{i}",
                      email=f"{prefix}{i}@example.test")
        db_session.add(lead)
        db_session.flush()
        db_session.add(m.Outcome(lead_id=lead.id, strategy_id=strategy.id, variant="A",
                                 event=m.OutcomeEvent.SENT, channel="email"))
        if i < replies:
            db_session.add(m.Outcome(lead_id=lead.id, strategy_id=strategy.id, variant="A",
                                     event=m.OutcomeEvent.REPLIED, channel="email"))
    db_session.commit()


def test_aggregation_keeps_accounts_apart_on_a_shared_pattern_key(
        db_session, paid_user, other_user):
    from app.services import score_decay

    mine = _strategy(db_session, paid_user, "pk-shared")
    theirs = _strategy(db_session, other_user, "pk-shared")
    _outcomes(db_session, mine, sends=10, replies=1, prefix="m")
    _outcomes(db_session, theirs, sends=10, replies=9, prefix="t")

    scores = score_decay.compute_scores_with_decay(db_session)

    rows = {(row["user_id"], row["pattern_key"], row["variant"]): row
            for row in scores.values()}
    assert set(rows) == {(paid_user.id, "pk-shared", "A"), (other_user.id, "pk-shared", "A")}
    assert rows[(paid_user.id, "pk-shared", "A")]["raw_n"] == 10
    assert rows[(other_user.id, "pk-shared", "A")]["raw_n"] == 10
    # Pooled, both accounts would read 0.5; apart, each sees its own rate.
    assert rows[(paid_user.id, "pk-shared", "A")]["reply_rate"] == pytest.approx(0.1, abs=0.01)
    assert rows[(other_user.id, "pk-shared", "A")]["reply_rate"] == pytest.approx(0.9, abs=0.01)


def test_pipeline_insights_show_only_the_accounts_own_rows(
        db_session, paid_user, other_user):
    from app.services.playbook_service import PlaybookService

    _score(db_session, paid_user, "pk-shared", "A", 0.12)
    _score(db_session, other_user, "pk-shared", "B", 0.95)
    _score(db_session, None, "pk-shared", "C", 0.80)     # pre-0093 pooled row
    db_session.commit()

    block = PlaybookService.get_insights(db_session, user_id=str(paid_user.id))
    assert "variant=A" in block
    assert "variant=B" not in block and "variant=C" not in block

    # The pipeline passes str(user_id); a UUID works too.
    assert PlaybookService.get_insights(db_session, user_id=paid_user.id) == block


def test_pipeline_insights_without_an_owner_are_empty(db_session, other_user):
    from app.services.playbook_service import _EMPTY_BLOCK, PlaybookService

    # The old fallback returned every account's rows when no owner was known.
    _score(db_session, other_user, "pk-any", "A", 0.5)
    _score(db_session, None, "pk-any", "B", 0.5)
    db_session.commit()
    assert PlaybookService.get_insights(db_session, user_id=None) == _EMPTY_BLOCK


def test_pipeline_insights_for_a_new_account_are_empty(db_session, paid_user, other_user):
    from app.services.playbook_service import _EMPTY_BLOCK, PlaybookService

    _score(db_session, other_user, "pk-any", "A", 0.5)
    db_session.commit()
    assert PlaybookService.get_insights(db_session, user_id=paid_user.id) == _EMPTY_BLOCK


def test_lead_scoring_uses_only_the_owners_booking_rate(db_session, paid_user, other_user):
    from app.services import lead_scoring

    mine = _strategy(db_session, paid_user, "pk-shared")
    db_session.add(m.PlaybookScore(user_id=other_user.id, pattern_key="pk-shared",
                                   variant="A", booking_rate=0.40, is_reliable=True))
    db_session.add(m.PlaybookScore(user_id=None, pattern_key="pk-shared",
                                   variant="B", booking_rate=0.30, is_reliable=True))
    db_session.commit()
    assert lead_scoring.playbook_rate(db_session, mine) is None

    db_session.add(m.PlaybookScore(user_id=paid_user.id, pattern_key="pk-shared",
                                   variant="A", booking_rate=0.02, is_reliable=True))
    db_session.commit()
    assert lead_scoring.playbook_rate(db_session, mine) == pytest.approx(0.02)

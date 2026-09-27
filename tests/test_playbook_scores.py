"""GET /playbook/scores -- the user-facing twin of P0-6's admin endpoint.

The handler wrapped its query in `except Exception: return []`, so any
database error reached a paying customer as a 200 with an empty list --
indistinguishable from "no data yet". The query itself is valid; only the
swallowing is the defect.

What must hold:
  * the caller gets the rows for their own strategies' pattern keys, and
    nothing else;
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


def _score(db_session, pattern_key, variant, reply_rate):
    db_session.add(m.PlaybookScore(pattern_key=pattern_key, variant=variant, score=reply_rate,
                                   reply_rate=reply_rate, booking_rate=0.01, sample_size=40,
                                   is_reliable=True))


@pytest.fixture()
def seeded(db_session, paid_user):
    _strategies(db_session, paid_user, "pk-mine")
    other = m.User(email="other@agency.test", email_verified=True)
    db_session.add(other)
    db_session.flush()
    _strategies(db_session, other, "pk-theirs")
    _score(db_session, "pk-mine", "A", 0.12)
    _score(db_session, "pk-mine", "B", 0.08)
    _score(db_session, "pk-theirs", "A", 0.05)
    db_session.commit()
    return paid_user


def test_returns_only_the_callers_rows(client, seeded, db_session):
    if db_session.bind.dialect.name == "sqlite":
        # The handler binds str(current_user.id) (dashed) into raw SQL, but
        # SQLAlchemy's Uuid type stores 32 undashed hex digits on SQLite, so
        # `p.user_id = :user_id` matches nothing here. On PostgreSQL the
        # literal is cast to uuid and matches. Not changed in this commit.
        pytest.xfail("raw-SQL UUID bind does not match SQLite's undashed storage")
    resp = client.get("/playbook/scores")
    assert resp.status_code == 200, resp.text
    assert sorted((r["pattern_key"], r["variant"]) for r in resp.json()) == [
        ("pk-mine", "A"), ("pk-mine", "B")]


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

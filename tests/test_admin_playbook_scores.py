"""P0-6 — GET /admin/playbook/scores.

playbook_scores has no user_id column (models.PlaybookScore; migrations
0001, 0008, 0010). Rows are keyed on (pattern_key, variant) and belong to a
user only through strategies.pattern_key -> strategies.product_id ->
products.user_id. The handler filtered on `ps.user_id`, which raised
UndefinedColumn whenever ?user_id= was passed, and a bare `except Exception`
turned that into a 200 with {"scores": []} -- indistinguishable from "no data
yet".

What must hold:
  * ?user_id= returns the rows for that user's strategies' pattern keys, and
    nothing else, with no duplicates when two strategies share a key;
  * the unfiltered call returns every row;
  * a database error is a 500, never an empty 200.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import models as m


@pytest.fixture()
def admin(db_session, test_user):
    test_user.is_admin = True
    db_session.commit()
    return test_user


def _owner_with_strategies(db_session, email, *pattern_keys):
    user = m.User(email=email, email_verified=True)
    db_session.add(user)
    db_session.flush()
    product = m.Product(user_id=user.id, name="P", description="d",
                        type=m.ProductType.PRODUCT)
    db_session.add(product)
    db_session.flush()
    for key in pattern_keys:
        db_session.add(m.Strategy(product_id=product.id, flow_type=m.FlowType.NO_CLIENTS,
                                  pattern_key=key))
    db_session.commit()
    return user


def _score(db_session, pattern_key, variant, reply_rate):
    db_session.add(m.PlaybookScore(pattern_key=pattern_key, variant=variant, score=reply_rate,
                                   reply_rate=reply_rate, booking_rate=0.01, sample_size=40,
                                   is_reliable=True))


@pytest.fixture()
def seeded(db_session):
    # Two strategies on the same key: the filter must not duplicate rows.
    alice = _owner_with_strategies(db_session, "alice@agency.test", "pk-alice", "pk-alice")
    bob = _owner_with_strategies(db_session, "bob@agency.test", "pk-bob")
    _score(db_session, "pk-alice", "A", 0.12)
    _score(db_session, "pk-alice", "B", 0.08)
    _score(db_session, "pk-bob", "A", 0.05)
    _score(db_session, "pk-orphan", "A", 0.02)
    db_session.commit()
    return alice, bob


def _rows(resp):
    assert resp.status_code == 200, resp.text
    return sorted((r["pattern_key"], r["variant"]) for r in resp.json()["scores"])


class TestUserFilter:
    def test_returns_only_that_users_rows(self, client, admin, seeded):
        alice, bob = seeded
        assert _rows(client.get(f"/admin/playbook/scores?user_id={alice.id}")) == [
            ("pk-alice", "A"), ("pk-alice", "B")]
        assert _rows(client.get(f"/admin/playbook/scores?user_id={bob.id}")) == [
            ("pk-bob", "A")]

    def test_rows_carry_the_real_values(self, client, admin, seeded):
        alice, _ = seeded
        scores = client.get(f"/admin/playbook/scores?user_id={alice.id}").json()["scores"]
        by_variant = {r["variant"]: r for r in scores}
        assert by_variant["A"]["reply_rate"] == pytest.approx(0.12)
        assert by_variant["A"]["sample_size"] == 40
        assert by_variant["A"]["is_reliable"] is True

    def test_user_without_strategies_gets_an_empty_list(self, client, admin, seeded,
                                                        db_session):
        loner = _owner_with_strategies(db_session, "loner@agency.test")
        assert _rows(client.get(f"/admin/playbook/scores?user_id={loner.id}")) == []

    def test_malformed_user_id_is_422(self, client, admin, seeded):
        assert client.get("/admin/playbook/scores?user_id=not-a-uuid").status_code == 422


class TestUnfiltered:
    def test_returns_every_row(self, client, admin, seeded):
        assert _rows(client.get("/admin/playbook/scores")) == [
            ("pk-alice", "A"), ("pk-alice", "B"), ("pk-bob", "A"), ("pk-orphan", "A")]


class TestDatabaseErrors:
    def test_a_db_error_is_a_500_not_an_empty_200(self, client, admin, seeded, db_session):
        from app.main import app

        db_session.execute(text("DROP TABLE playbook_scores"))
        db_session.commit()
        # Same app, same dependency overrides as `client`; only exception
        # propagation differs, so the test sees the response a caller would.
        with TestClient(app, raise_server_exceptions=False) as raw:
            raw.headers.update(client.headers)
            resp = raw.get("/admin/playbook/scores")
        assert resp.status_code == 500
        assert "scores" not in resp.text


def test_non_admin_is_refused(client, seeded):
    assert client.get("/admin/playbook/scores").status_code == 403

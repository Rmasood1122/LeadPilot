"""F-AI-01 — a plan's max_strategies is enforced when a strategy is created.

app/core/plans.py defined the cap (free = 3) and check_plan_limit, but nothing
called it for strategies: an account could create any number, and every one
starts the most expensive pipeline in the system.

The count is the caller's OWN strategies, across all their products. Another
tenant's strategies never count, and a tenant at their cap does not affect
anyone else. Refusal uses the existing convention: HTTP 402 with the
plan_limit_exceeded body from plan_limit_response.
"""

import pytest
from sqlalchemy import func, select

from app.core.plans import PLANS
from app.db import models as m
from tests.conftest import auth_headers

FREE_CAP = PLANS["free"]["max_strategies"]


def _product(db_session, user, name: str = "Product") -> m.Product:
    product = m.Product(user=user, name=name, description=f"{name} description",
                        type=m.ProductType.SKILL)
    db_session.add(product)
    db_session.commit()
    return product


def _strategies(db_session, product, n: int) -> None:
    for _ in range(n):
        db_session.add(m.Strategy(product_id=product.id,
                                  flow_type=m.FlowType.NO_CLIENTS))
    db_session.commit()


def _count(db_session) -> int:
    return db_session.execute(select(func.count(m.Strategy.id))).scalar_one()


def _create(client, product, user=None):
    headers = auth_headers(user) if user is not None else None
    return client.post(f"/products/{product.id}/strategies", json={}, headers=headers)


@pytest.fixture()
def other_tenant(db_session):
    user = m.User(email="tenant-b-cap@test.dev", email_verified=True)
    db_session.add(user)
    db_session.commit()
    return user


class TestTheCap:
    def test_the_free_cap_is_three(self):
        assert FREE_CAP == 3

    def test_creating_one_more_than_the_cap_is_refused(self, client, db_session,
                                                       test_user, enqueued):
        product = _product(db_session, test_user)
        _strategies(db_session, product, FREE_CAP)

        response = _create(client, product)

        assert response.status_code == 402, response.text
        detail = response.json()["detail"]
        assert detail["error"] == "plan_limit_exceeded"
        assert detail["limit"] == "max_strategies"
        assert detail["current_plan"] == "free"
        assert detail["upgrade_to"] == "starter"
        assert _count(db_session) == FREE_CAP, "no strategy row was written"
        assert enqueued == [], "no pipeline was started"

    def test_the_last_one_under_the_cap_is_allowed(self, client, db_session,
                                                   test_user, enqueued):
        product = _product(db_session, test_user)
        _strategies(db_session, product, FREE_CAP - 1)

        response = _create(client, product)

        assert response.status_code == 202, response.text
        assert _count(db_session) == FREE_CAP
        assert enqueued == [response.json()["id"]]

    def test_the_count_spans_all_of_the_callers_products(self, client, db_session,
                                                         test_user):
        first = _product(db_session, test_user, "First")
        second = _product(db_session, test_user, "Second")
        _strategies(db_session, first, FREE_CAP - 1)
        _strategies(db_session, second, 1)

        assert _create(client, second).status_code == 402

    def test_deleting_a_strategy_frees_a_slot(self, client, db_session, test_user):
        """The cap counts strategies that exist; a deleted one is gone."""
        product = _product(db_session, test_user)
        _strategies(db_session, product, FREE_CAP)
        assert _create(client, product).status_code == 402

        one = db_session.execute(select(m.Strategy).limit(1)).scalars().one()
        db_session.delete(one)
        db_session.commit()

        assert _create(client, product).status_code == 202

    def test_an_unlimited_plan_is_not_capped(self, client, db_session, test_user):
        test_user.plan = m.PlanTier.SCALE
        db_session.commit()
        assert PLANS["scale"]["max_strategies"] == -1
        product = _product(db_session, test_user)
        _strategies(db_session, product, FREE_CAP + 5)

        assert _create(client, product).status_code == 202

    def test_a_paid_plan_gets_its_own_higher_cap(self, client, db_session, test_user):
        test_user.plan = m.PlanTier.STARTER
        db_session.commit()
        cap = PLANS["starter"]["max_strategies"]
        product = _product(db_session, test_user)
        _strategies(db_session, product, cap - 1)

        assert _create(client, product).status_code == 202
        refused = _create(client, product)
        assert refused.status_code == 402
        assert refused.json()["detail"]["current_plan"] == "starter"


class TestTenancy:
    def test_another_tenants_strategies_do_not_count(self, client, db_session,
                                                     test_user, other_tenant):
        _strategies(db_session, _product(db_session, other_tenant, "Theirs"), 10)
        mine = _product(db_session, test_user, "Mine")
        _strategies(db_session, mine, FREE_CAP - 1)

        assert _create(client, mine).status_code == 202

    def test_a_tenant_at_the_cap_does_not_block_another_tenant(
            self, client, db_session, test_user, other_tenant):
        _strategies(db_session, _product(db_session, test_user, "Mine"), FREE_CAP)
        theirs = _product(db_session, other_tenant, "Theirs")

        assert _create(client, theirs, user=other_tenant).status_code == 202

    def test_someone_elses_product_is_still_404_not_402(self, client, db_session,
                                                        test_user, other_tenant):
        """Ownership is checked first: being at the cap must not turn a
        foreign product id into a different answer."""
        _strategies(db_session, _product(db_session, test_user, "Mine"), FREE_CAP)
        theirs = _product(db_session, other_tenant, "Theirs")

        assert _create(client, theirs).status_code == 404

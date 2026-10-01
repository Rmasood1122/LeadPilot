"""F-SEC-03 — POST /onboarding/complete-step must not honour a foreign user_id.

The handler used `body.user_id or str(current_user.id)` as the row to write,
so any authenticated user could write onboarding state for any other user.

A NOTE ON THE ID FORMS USED HERE. The SQLite test database stores a Uuid
column as 32-character hex text, and the handler's raw
`UPDATE users ... WHERE id = :uid` compares text. The dashed `str(uuid)` form
therefore matches no row on SQLite, while `uuid.hex` matches. A test that only
sent the dashed form would "prove" zero writes on the unfixed code too. So the
cross-user write is exercised with the hex form (a real row really changes),
and the dashed and malformed forms are checked with spies on the handler's
only database helpers.
"""

import pytest

from app.api import onboarding
from app.db import models as m
from tests.conftest import auth_headers

STEP = "product_created"
URL = "/onboarding/complete-step"


@pytest.fixture()
def victim(db_session):
    user = m.User(email="victim-onboarding@test.dev", email_verified=True)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def admin(db_session):
    user = m.User(email="admin-onboarding@test.dev", email_verified=True,
                  is_admin=True)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def db_helpers(monkeypatch):
    """Record every call to the two functions through which this handler
    touches the database, without running them."""
    calls = {"mark_complete": [], "_get_state": []}

    def _mark_complete(db, user_id, step):
        calls["mark_complete"].append((user_id, step))

    def _get_state(db, user_id):
        calls["_get_state"].append(user_id)
        return {}

    monkeypatch.setattr(onboarding, "mark_complete", _mark_complete)
    monkeypatch.setattr(onboarding, "_get_state", _get_state)
    return calls


def _state(db_session, user):
    db_session.refresh(user)
    return user.onboarding_state


class TestForeignUserIdIsRefused:
    def test_a_non_admin_cannot_write_another_users_row(self, client, db_session,
                                                        victim):
        """The defect itself: the victim's row must not change. Asserted
        before the status code so a failure shows what was written."""
        response = client.post(URL, json={"step": STEP, "user_id": victim.id.hex})
        assert _state(db_session, victim) is None
        assert response.status_code == 403, response.text

    def test_the_refusal_comes_before_any_database_operation(
            self, client, victim, db_helpers):
        response = client.post(URL, json={"step": STEP, "user_id": str(victim.id)})
        assert response.status_code == 403, response.text
        assert db_helpers == {"mark_complete": [], "_get_state": []}

    def test_a_user_id_that_is_not_a_uuid_is_treated_as_foreign(
            self, client, db_helpers):
        response = client.post(URL, json={"step": STEP, "user_id": "not-a-uuid"})
        assert response.status_code == 403, response.text
        assert db_helpers == {"mark_complete": [], "_get_state": []}


class TestOwnAndOmittedStillWork:
    def test_own_user_id_is_accepted(self, client, db_session, test_user):
        response = client.post(URL, json={"step": STEP, "user_id": test_user.id.hex})
        assert response.status_code == 200, response.text
        assert response.json() == {"status": "ok", "step": STEP}
        assert _state(db_session, test_user)["step_completed"] == [STEP]

    def test_own_user_id_in_dashed_form_is_accepted(self, client, test_user,
                                                    db_helpers):
        response = client.post(URL, json={"step": STEP, "user_id": str(test_user.id)})
        assert response.status_code == 200, response.text
        assert db_helpers["mark_complete"] == [(str(test_user.id), STEP)]

    def test_omitted_user_id_targets_the_caller(self, client, test_user, db_helpers):
        response = client.post(URL, json={"step": STEP})
        assert response.status_code == 200, response.text
        assert db_helpers["mark_complete"] == [(str(test_user.id), STEP)]


class TestAdmin:
    def test_an_admin_may_complete_a_step_for_another_user(
            self, client, db_session, admin, victim):
        response = client.post(URL, json={"step": STEP, "user_id": victim.id.hex},
                               headers=auth_headers(admin))
        assert response.status_code == 200, response.text
        assert _state(db_session, victim)["step_completed"] == [STEP]

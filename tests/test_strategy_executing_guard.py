"""Product defect #19: StrategyStatus.EXECUTING is never assigned (a strategy
stays `verified` while its outreach runs), so the guards keyed on it never
fired. In particular DELETE /strategies/{id} refused only "EXECUTING and
campaign active", so a strategy whose campaign was really sending could be
deleted although the help center (articles 21, 25) says it must be paused
first.

Fix: the delete guard now checks the real condition -- the campaign is active
and at least one lead is still enrolled (active, or paused for an
out-of-office and due to resume). The resume guard on EXECUTING was removed:
resume already refuses every finished strategy (verified /
needs_human_review), which is where a sending strategy is. Assigning
EXECUTING was rejected: sourcing leads, creating sequences and Quickstart all
require status == verified, so marking a strategy executing would lock those
out (see docs/program/fixes/product-defects.md #19).
"""

import pytest

from app.db import models as m
from app.services import auth as auth_svc

PASSWORD = "CorrectHorse!1"


@pytest.fixture()
def confirmable(db_session, test_user):
    test_user.password_hash = auth_svc.hash_password(PASSWORD)
    db_session.commit()
    return test_user


def _delete(client, sid):
    return client.request("DELETE", f"/strategies/{sid}", json={"password": PASSWORD})


def test_a_sending_verified_strategy_cannot_be_deleted(client, db_session, confirmable,
                                                       verified_strategy, enrolled):
    assert verified_strategy.status is m.StrategyStatus.VERIFIED
    assert verified_strategy.campaign_state == "active"
    resp = _delete(client, verified_strategy.id)
    assert resp.status_code == 409, resp.text
    assert "Pause the campaign" in resp.json()["detail"]
    assert db_session.get(m.Strategy, verified_strategy.id) is not None


def test_pausing_the_campaign_allows_the_delete(client, db_session, confirmable,
                                                verified_strategy, enrolled):
    verified_strategy.campaign_state = "paused_manual"
    db_session.commit()
    assert _delete(client, verified_strategy.id).status_code == 200


def test_a_campaign_with_nobody_left_enrolled_is_not_sending(client, db_session, confirmable,
                                                             verified_strategy, enrolled):
    for e in db_session.query(m.SequenceEnrollment).all():
        e.status = m.EnrollmentStatus.COMPLETED
    db_session.commit()
    assert _delete(client, verified_strategy.id).status_code == 200


def test_no_guard_still_keys_on_the_unassigned_status():
    import inspect

    from app.api import strategies

    source = inspect.getsource(strategies)
    assert "StrategyStatus.EXECUTING" not in source


def test_a_message_mid_send_blocks_the_delete_even_when_paused(
        client, db_session, confirmable, verified_strategy, enrolled):
    """Review L3: a send task that has claimed a message (status SENDING) is
    transmitting it right now; deleting the strategy underneath it would lose
    the record of a message that may already have left. Refused until it
    finishes, even with the campaign paused."""
    verified_strategy.campaign_state = "paused_manual"
    msg = db_session.query(m.Message).first()
    msg.status = m.MessageStatus.SENDING
    db_session.commit()
    resp = _delete(client, verified_strategy.id)
    assert resp.status_code == 409, resp.text
    assert "being sent" in resp.json()["detail"]

    msg.status = m.MessageStatus.SENT
    db_session.commit()
    assert _delete(client, verified_strategy.id).status_code == 200

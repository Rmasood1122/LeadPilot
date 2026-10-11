"""Daily send approval -- the LinkedIn network BULK send (LEGAL/SAFETY GUARD).

A bulk send queues up to 25 Celery jobs that message the customer's own
LinkedIn connections through Unipile on the customer's LinkedIn account. That
is automation, so -- like a LinkedIn sequence step -- it needs today's
LinkedIn approval, with the restriction-risk acknowledgement, before anything
is transmitted. Held items stay queued and are queued again on approval. A
single interactive send ("Send" on one message) is a person's action and is
not gated.

Fixtures are the ones tests/test_network_messages.py proves sending with.
"""

from __future__ import annotations

import uuid

import pytest

from app.db import models as m
from app.services import daily_send_approval as dsa
from app.workers import network_tasks
from tests.test_network_messages import (  # noqa: F401
    _approved,
    claude,
    queued,
    redis,
    task_session,
    unipile,
    world,
)

_REAL_ENABLED = dsa.enabled


@pytest.fixture(autouse=True)
def approval_on(monkeypatch):
    monkeypatch.setattr(dsa, "enabled", _REAL_ENABLED)


def _chats(unipile):
    return [c for c in unipile.calls if c[0] == "start_chat"]


def _approve_linkedin(db, user):
    return dsa.approve(db, user.id, actor_id=user.id, channels=["linkedin"],
                       linkedin_risk_acknowledged=True,
                       linkedin_warning_version=dsa.LINKEDIN_WARNING_VERSION)


class TestBulkSend:
    def test_a_queued_message_waits_for_todays_linkedin_approval(
            self, client, world, claude, queued, unipile, db_session, mailbox):
        a = _approved(client, world, "Queued text.")
        client.post("/linkedin-network/messages/bulk-send", json={"ids": [a]})
        out = network_tasks.send_queued.run(a)
        assert out == {"status": "held", "result": dsa.SEND_RESULT_AWAITING}
        msg = db_session.get(m.LinkedInNetworkMessage, uuid.UUID(a))
        assert msg.status == "queued" and msg.error.startswith(dsa.ERROR_PREFIX)
        assert _chats(unipile) == []
        # The owner is told, and the network message is in today's LinkedIn count.
        assert len(mailbox) == 1
        assert dsa.queued_counts(db_session, world["user"].id)["linkedin"] == 1

    def test_approving_email_only_does_not_release_it(
            self, client, world, claude, queued, unipile, db_session):
        a = _approved(client, world)
        client.post("/linkedin-network/messages/bulk-send", json={"ids": [a]})
        dsa.approve(db_session, world["user"].id, actor_id=world["user"].id,
                    channels=["email"])
        assert network_tasks.send_queued.run(a)["result"] == dsa.SEND_RESULT_CHANNEL
        assert _chats(unipile) == []

    def test_approving_linkedin_queues_it_again_and_it_sends(
            self, client, world, claude, queued, unipile, db_session):
        a = _approved(client, world, "Queued text.")
        client.post("/linkedin-network/messages/bulk-send", json={"ids": [a]})
        network_tasks.send_queued.run(a)
        queued.clear()
        out = _approve_linkedin(db_session, world["user"])
        assert out["released_network"] == 1
        assert [i for i, _ in queued] == [a]          # handed back to the queue
        assert network_tasks.send_queued.run(a)["status"] == "sent"
        assert ("start_chat", "prov-ana-lopez", "acc-1", "Queued text.") in unipile.calls

    def test_a_lookup_error_fails_closed(self, client, world, claude, queued, unipile,
                                         db_session, monkeypatch):
        a = _approved(client, world)
        client.post("/linkedin-network/messages/bulk-send", json={"ids": [a]})
        queued.clear()

        def broken(*_a, **_k):
            raise RuntimeError("database hiccup")

        monkeypatch.setattr(dsa, "network_hold", broken)
        out = network_tasks.send_queued.run(a)
        assert out["status"] == "held"
        assert out["result"] == dsa.SEND_RESULT_UNAVAILABLE
        assert _chats(unipile) == []
        assert queued and queued[0][1] == 3600        # re-checked in an hour

    def test_a_single_interactive_send_is_a_persons_action(
            self, client, world, claude, unipile):
        mid = _approved(client, world)
        assert client.post(f"/linkedin-network/messages/{mid}/send").status_code == 200
        assert len(_chats(unipile)) == 1

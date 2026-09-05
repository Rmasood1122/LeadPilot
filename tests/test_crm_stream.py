"""M9 real-time layer — the event bus and the SSE endpoint.

Two things are under test and they fail in different ways:

  the BUS (app/services/crm_events.py) — a session listener. Its failure mode
  is silence: an event that is never published, with nothing raising. So the
  tests assert on what actually reaches Redis, not on the listener running.

  the STREAM (GET /crm/stream) — its failure modes are a leaked credential and
  a leaked event. Both are tested directly.
"""

import asyncio
import json
import uuid

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import crm_events


@pytest.fixture()
def stream_lead(db_session, verified_strategy):
    lead = m.Lead(strategy_id=verified_strategy.id, source="apollo",
                  external_id="s1", full_name="Rio Alvarez",
                  email="rio@x.test", status=m.LeadStatus.VERIFIED)
    db_session.add(lead)
    db_session.commit()
    return lead


def _published(store, channel: str) -> list[dict]:
    """Everything published to a channel, in order.

    fakeredis keeps no history for a channel with no live subscriber, so the
    tests subscribe first and drain afterwards.
    """
    messages = []
    pubsub = store.pubsub()
    pubsub.subscribe(channel)
    while True:
        raw = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.01)
        if raw is None:
            break
        messages.append(json.loads(raw["data"]))
    return messages


@pytest.fixture()
def bus(isolated_rate_limiter, test_user):
    """Subscribe to this user's channel before the test acts on anything.

    `isolated_rate_limiter` is the autouse fixture that points
    get_sync_redis() at a per-test fakeredis; reusing its store rather than
    building a second one is what makes the publish path under test the same
    one the application uses.
    """
    store = isolated_rate_limiter
    channel = crm_events.channel_for(test_user.id)
    pubsub = store.pubsub()
    pubsub.subscribe(channel)
    pubsub.get_message(timeout=0.05)  # drain the subscribe confirmation

    def drain() -> list[dict]:
        out = []
        while True:
            raw = pubsub.get_message(ignore_subscribe_messages=True,
                                     timeout=0.02)
            if raw is None:
                break
            out.append(json.loads(raw["data"]))
        return out

    yield drain
    pubsub.close()


# --------------------------------------------------------------------------
# The event bus
# --------------------------------------------------------------------------


class TestEventBus:
    def test_status_change_publishes_a_status_event(self, client, bus,
                                                    stream_lead):
        client.patch(f"/crm/leads/{stream_lead.id}", json={"status": "flagged"})
        events = bus()
        names = [event["event"] for event in events]
        assert crm_events.EVENT_LEAD_STATUS_CHANGED in names

        payload = next(e["data"] for e in events
                       if e["event"] == crm_events.EVENT_LEAD_STATUS_CHANGED)
        assert payload["lead_id"] == str(stream_lead.id)
        assert payload["from"] == "verified"
        assert payload["to"] == "flagged"

    def test_status_change_is_distinct_from_a_generic_update(self, client, bus,
                                                             stream_lead):
        """The kanban and the funnel key off the transition. Making them diff a
        generic "updated" payload against their cached copy to notice would
        push that work into every consumer."""
        client.patch(f"/crm/leads/{stream_lead.id}", json={"priority": "high"})
        names = [event["event"] for event in bus()]
        assert crm_events.EVENT_LEAD_STATUS_CHANGED not in names

    def test_note_creation_publishes(self, client, bus, stream_lead):
        client.post(f"/crm/leads/{stream_lead.id}/notes",
                    json={"body": "Called them"})
        events = {event["event"]: event["data"] for event in bus()}
        assert crm_events.EVENT_NOTE_CREATED in events
        assert events[crm_events.EVENT_NOTE_CREATED]["body"] == "Called them"

    def test_activity_creation_publishes(self, client, bus, stream_lead):
        client.post(f"/crm/leads/{stream_lead.id}/notes", json={"body": "x"})
        names = [event["event"] for event in bus()]
        assert crm_events.EVENT_ACTIVITY_CREATED in names

    def test_outcomes_written_by_milestone_code_publish_too(
        self, db_session, bus, stream_lead
    ):
        """The whole point of the session listener. This writes an Outcome the
        way app/services/sequence_engine.py does -- no CRM code involved --
        and it still reaches the feed. A publish() call per write site would
        have required editing that module; a write site added later would not
        be covered at all."""
        db_session.add(m.Outcome(lead_id=stream_lead.id,
                                 event=m.OutcomeEvent.REPLIED,
                                 channel="email"))
        db_session.commit()
        events = {event["event"]: event["data"] for event in bus()}
        assert crm_events.EVENT_OUTCOME_CREATED in events
        assert events[crm_events.EVENT_OUTCOME_CREATED]["event"] == "replied"

    def test_lead_status_written_outside_the_crm_publishes(self, db_session,
                                                           bus, stream_lead):
        """A status change made by the sourcing chain or the kanban PATCH, not
        by /crm."""
        stream_lead.status = m.LeadStatus.CONTACTED
        db_session.commit()
        names = [event["event"] for event in bus()]
        assert crm_events.EVENT_LEAD_STATUS_CHANGED in names

    def test_rollback_publishes_nothing(self, db_session, stream_lead, bus):
        # `bus` is listed AFTER `stream_lead` on purpose: pytest builds
        # fixtures in signature order, and subscribing first would capture the
        # lead-creation event from the fixture's own commit, which this test
        # then reads as a leak.
        """A flush is not a commit. Publishing at flush time would announce a
        status change that the transaction then abandoned, and the client
        would render an event that never happened."""
        stream_lead.status = m.LeadStatus.CONTACTED
        db_session.flush()
        db_session.rollback()
        assert bus() == []

    def test_system_level_outcomes_without_a_lead_are_skipped(self, db_session,
                                                              bus,
                                                              verified_strategy):
        """ab_promoted and circuit_opened have a strategy but no lead, so
        there is no CRM row for a client to patch."""
        db_session.add(m.Outcome(lead_id=None, strategy_id=verified_strategy.id,
                                 event=m.OutcomeEvent.AB_PROMOTED,
                                 channel="system"))
        db_session.commit()
        assert [e["event"] for e in bus()] == []

    def test_events_go_to_the_owner_only(self, db_session, isolated_rate_limiter,
                                         test_user, stream_lead):
        """A per-user channel, not one global channel with filtering in the
        consumer -- filtering in the consumer makes a filtering bug into a
        cross-tenant leak."""
        store = isolated_rate_limiter
        stranger = uuid.uuid4()
        theirs = store.pubsub()
        theirs.subscribe(crm_events.channel_for(stranger))
        theirs.get_message(timeout=0.05)

        stream_lead.status = m.LeadStatus.CONTACTED
        db_session.commit()

        assert theirs.get_message(ignore_subscribe_messages=True,
                                  timeout=0.05) is None
        theirs.close()

    def test_a_redis_failure_never_breaks_the_write(self, client, monkeypatch,
                                                    db_session, stream_lead):
        """Redis being down must degrade the live feed, not turn a working
        lead update into a 500. The React Query poll is what makes that
        acceptable."""
        def _boom():
            raise ConnectionError("redis is down")

        monkeypatch.setattr("app.core.redis_client.get_sync_redis", _boom)
        r = client.patch(f"/crm/leads/{stream_lead.id}",
                         json={"status": "flagged"})
        assert r.status_code == 200
        db_session.refresh(stream_lead)
        assert stream_lead.status is m.LeadStatus.FLAGGED

    def test_the_listeners_are_actually_installed(self):
        """app/main.py imports crm_events for its SIDE EFFECT. An "unused
        import" cleanup there would disable the entire feed with no test
        failing, because every consumer degrades to polling."""
        from sqlalchemy import event as sa_event
        from sqlalchemy.orm import Session

        assert sa_event.contains(Session, "after_flush",
                                 crm_events._crm_after_flush)
        assert sa_event.contains(Session, "after_commit",
                                 crm_events._crm_after_commit)
        assert sa_event.contains(Session, "after_rollback",
                                 crm_events._crm_after_rollback)

    def test_main_still_imports_the_event_module(self):
        """The other half of the same guard: the listeners register at import
        time, so what has to survive is the import line itself."""
        import os

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "app", "main.py"), encoding="utf-8") as fh:
            source = fh.read()
        assert "from app.services.crm_events import" in source


# --------------------------------------------------------------------------
# Stream tickets
# --------------------------------------------------------------------------


class TestStreamTicket:
    def test_ticket_is_minted_for_an_authenticated_user(self, client):
        r = client.post("/crm/stream/ticket")
        assert r.status_code == 200
        assert len(r.json()["ticket"]) >= 32
        assert r.json()["expires_in"] == 60

    def test_ticket_requires_authentication(self, anon_client):
        assert anon_client.post("/crm/stream/ticket").status_code in (401, 403)

    def test_the_access_token_is_never_a_valid_stream_credential(
        self, client, test_user
    ):
        """The reason the ticket exists. EventSource cannot set headers, so
        the credential travels in the URL -- and a JWT valid for the next hour
        must not be the thing written into every access log."""
        from app.services.auth import issue_tokens

        token = issue_tokens(test_user.id)["access_token"]
        assert client.get(f"/crm/stream?ticket={token}").status_code == 401

    def test_ticket_is_single_use(self, client, isolated_rate_limiter):
        ticket = client.post("/crm/stream/ticket").json()["ticket"]
        from app.api.crm import _redeem_ticket

        assert _redeem_ticket(ticket)
        with pytest.raises(Exception):
            _redeem_ticket(ticket)

    def test_unknown_ticket_is_401(self, client):
        assert client.get("/crm/stream?ticket=nonsense").status_code == 401

    def test_missing_ticket_is_422_not_an_open_stream(self, client):
        assert client.get("/crm/stream").status_code == 422

    def test_ticket_endpoint_reports_503_when_redis_is_gone(self, client,
                                                            monkeypatch):
        """Handing out a ticket that will be rejected a moment later is worse
        than saying the stream is unavailable: the client needs to know to
        fall back to polling."""
        def _boom():
            raise ConnectionError("redis is down")

        monkeypatch.setattr("app.core.redis_client.get_sync_redis", _boom)
        assert client.post("/crm/stream/ticket").status_code == 503


# --------------------------------------------------------------------------
# The stream itself
# --------------------------------------------------------------------------


class TestSseStream:
    """Smoke test: connect, trigger an event, assert it arrives.

    Driven through the generator the endpoint returns rather than through
    TestClient. TestClient reads a streaming response to completion, and this
    stream does not complete -- it is designed to stay open for an hour -- so
    a plain client.get() would block for the length of the test timeout.
    """

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro) \
            if False else asyncio.run(coro)

    def test_connect_receives_ready_then_the_event(self, client, monkeypatch,
                                                   test_user, db_session,
                                                   stream_lead):
        import fakeredis.aioredis

        from app.api import crm as crm_api

        fake_async = fakeredis.aioredis.FakeRedis(decode_responses=True)
        monkeypatch.setattr("app.core.redis_client.get_redis",
                            lambda: fake_async)

        ticket = client.post("/crm/stream/ticket").json()["ticket"]

        async def scenario():
            request = _FakeRequest()
            response = await crm_api.crm_stream(request, ticket=ticket)
            agen = response.body_iterator

            first = await asyncio.wait_for(agen.__anext__(), timeout=5)
            assert first.startswith("event: ready")
            assert str(test_user.id) in first

            # Publish through the SAME channel the bus publishes to.
            await fake_async.publish(
                crm_events.channel_for(test_user.id),
                json.dumps({"event": crm_events.EVENT_LEAD_STATUS_CHANGED,
                            "data": {"lead_id": str(stream_lead.id),
                                     "from": "verified", "to": "flagged"}}),
            )

            # Skip keepalive comments; they are not events.
            for _ in range(5):
                chunk = await asyncio.wait_for(agen.__anext__(), timeout=5)
                if chunk.startswith(": keepalive"):
                    continue
                break

            assert chunk.startswith(
                f"event: {crm_events.EVENT_LEAD_STATUS_CHANGED}")
            body = chunk.split("data: ", 1)[1].strip()
            assert json.loads(body)["to"] == "flagged"

            request.disconnected = True
            await agen.aclose()

        asyncio.run(scenario())

    def test_stream_sets_the_headers_proxies_need(self, client, monkeypatch):
        """nginx buffers proxied responses by default, which holds every event
        until the buffer fills -- turning a live feed into a batch delivery."""
        import fakeredis.aioredis

        from app.api import crm as crm_api

        monkeypatch.setattr(
            "app.core.redis_client.get_redis",
            lambda: fakeredis.aioredis.FakeRedis(decode_responses=True))
        ticket = client.post("/crm/stream/ticket").json()["ticket"]

        async def scenario():
            response = await crm_api.crm_stream(_FakeRequest(), ticket=ticket)
            assert response.media_type == "text/event-stream"
            assert response.headers["x-accel-buffering"] == "no"
            assert "no-cache" in response.headers["cache-control"]
            await response.body_iterator.aclose()

        asyncio.run(scenario())

    def test_stream_closes_when_the_client_disconnects(self, client,
                                                       monkeypatch):
        """Otherwise a closed tab holds a worker slot until the hour is up."""
        import fakeredis.aioredis

        from app.api import crm as crm_api

        monkeypatch.setattr(
            "app.core.redis_client.get_redis",
            lambda: fakeredis.aioredis.FakeRedis(decode_responses=True))
        ticket = client.post("/crm/stream/ticket").json()["ticket"]

        async def scenario():
            request = _FakeRequest()
            response = await crm_api.crm_stream(request, ticket=ticket)
            agen = response.body_iterator
            await asyncio.wait_for(agen.__anext__(), timeout=5)  # ready
            request.disconnected = True
            with pytest.raises(StopAsyncIteration):
                await asyncio.wait_for(agen.__anext__(), timeout=5)

        asyncio.run(scenario())

    def test_stream_asks_the_client_to_reconnect_at_the_cap(self, client,
                                                            monkeypatch):
        """An SSE connection is a worker slot held for as long as the tab is
        open. A dashboard left up over a weekend would otherwise hold one
        across a deploy and every transient in between.

        The clock is driven, not waited on. time.monotonic() has ~15.6ms
        resolution on Windows, so two calls inside one tick return the same
        value -- a test that set a low cap and waited would be racing the
        clock granularity rather than asserting anything about the code.
        That is what crm.py::_monotonic exists as a seam for.
        """
        import fakeredis.aioredis

        from app.api import crm as crm_api

        monkeypatch.setattr(
            "app.core.redis_client.get_redis",
            lambda: fakeredis.aioredis.FakeRedis(decode_responses=True))

        # First reading opens the connection; every later one is an hour on.
        readings = iter([0.0] + [4000.0] * 10)
        monkeypatch.setattr(crm_api, "_monotonic", lambda: next(readings))

        ticket = client.post("/crm/stream/ticket").json()["ticket"]

        async def scenario():
            response = await crm_api.crm_stream(_FakeRequest(), ticket=ticket)
            agen = response.body_iterator
            await asyncio.wait_for(agen.__anext__(), timeout=5)  # ready
            chunk = await asyncio.wait_for(agen.__anext__(), timeout=5)
            assert chunk.startswith("event: reconnect")
            # And it closes rather than looping on the reconnect notice.
            with pytest.raises(StopAsyncIteration):
                await asyncio.wait_for(agen.__anext__(), timeout=5)

        asyncio.run(scenario())

    def test_a_non_positive_cap_is_a_kill_switch_not_a_reconnect_loop(
        self, client, monkeypatch
    ):
        """Turning real-time off without a deploy, matching
        support_chat_enabled. It has to REFUSE the connection: accepting one
        and immediately asking for a reconnect would put every open tab into a
        tight connect/disconnect loop, which is worse than no real-time."""
        from app.config import settings

        monkeypatch.setattr(settings, "crm_stream_max_seconds", 0,
                            raising=False)
        ticket = client.post("/crm/stream/ticket").json()["ticket"]
        assert client.get(f"/crm/stream?ticket={ticket}").status_code == 503


class _FakeRequest:
    """The two things the endpoint asks a Request for."""

    def __init__(self):
        self.disconnected = False

    async def is_disconnected(self) -> bool:
        return self.disconnected

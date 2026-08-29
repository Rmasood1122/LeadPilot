"""Feature 3 — AI customer support chat.

The model is stubbed by FakeClaude (conftest), which makes every test here
deterministic. That is the point: these tests pin the CODE's behaviour — the
refusal enforcement, the confidence floor, the failure fallbacks, the
persistence and the isolation between users — none of which should depend on
what a model happens to say on a given day.

Whether the real model actually classifies off-topic questions correctly is a
different question that a stub cannot answer. It is measured separately by an
adversarial run against the live API, recorded in
docs/features/ai-support-chat.md.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import support_chat, support_kb
from tests.conftest import auth_headers


def _ask(client, message, session_id=None):
    body = {"message": message}
    if session_id:
        body["session_id"] = session_id
    return client.post("/support/chat", json=body)


# --------------------------------------------------------------------------
# Knowledge base
# --------------------------------------------------------------------------


class TestKnowledgeBase:
    def test_nine_curated_entries_with_unique_ids(self):
        assert len(support_kb.FAQ) == 9
        assert len({e.id for e in support_kb.FAQ}) == 9

    def test_every_entry_has_a_real_answer(self):
        for entry in support_kb.FAQ:
            assert entry.answer.strip() and len(entry.answer) > 40

    def test_faq_endpoint_exposes_the_kb(self, client):
        payload = client.get("/support/faq").json()
        assert len(payload["faq"]) == 9
        assert payload["chat_enabled"] is True
        assert {e["id"] for e in payload["faq"]} == {e.id for e in support_kb.FAQ}

    @pytest.mark.parametrize("query,expected_first", [
        ("what is leadpilot", "what-is-leadpilot"),
        ("how do I set up my first campaign", "first-campaign"),
        ("do you automate linkedin", "how-outreach-works"),
        ("what tutorials are there", "tutorial-section"),
        ("what data do you store", "data-storage"),
    ])
    def test_keyword_search_ranks_the_right_entry_first(self, query, expected_first):
        assert support_kb.search(query)[0].id == expected_first

    def test_search_NEVER_drops_entries(self):
        """Ranking may be wrong; omission must not be possible.

        The model cannot cite what it was not shown, so a retrieval step that
        filtered would turn a ranking miss into "sorry, I don't know" for a
        question the FAQ demonstrably answers.
        """
        for query in ("apollo", "zzzz nonsense", "", "linkedin"):
            assert len(support_kb.search(query)) == len(support_kb.FAQ)

    def test_prompt_context_contains_every_entry_and_its_id(self):
        context = support_kb.as_prompt_context("outreach")
        for entry in support_kb.FAQ:
            assert f"[{entry.id}]" in context
            assert entry.answer[:40] in context


# --------------------------------------------------------------------------
# The three guards
# --------------------------------------------------------------------------


class TestRefusalEnforcement:
    def test_off_topic_returns_the_CONSTANT_not_the_model_text(self, client,
                                                               fake_claude):
        """Guard 2. The model is given the chance to write an off-topic answer
        anyway; the code must throw it away.

        Letting the model phrase its own refusal is how a refusal becomes a
        partial answer — asked to decline discussing X, models write a sentence
        about X."""
        fake_claude.support_response = {
            "on_topic": False,
            "confidence": 0.99,
            "answer": "The capital of France is Paris and here is a recipe...",
            "faq_ids": [],
        }
        body = _ask(client, "What is the capital of France?").json()
        assert body["answer"]["text"] == support_kb.REFUSAL_MESSAGE
        assert "Paris" not in body["answer"]["text"]
        assert body["answer"]["on_topic"] is False
        assert body["answer"]["reason"] == "off_topic"

    def test_off_topic_does_NOT_offer_a_ticket(self, client, fake_claude):
        """Inviting someone to file a ticket about the weather creates work for
        a human and teaches the user the bot is a routing layer to a person."""
        fake_claude.support_response = {"on_topic": False, "confidence": 1.0,
                                        "answer": "", "faq_ids": []}
        body = _ask(client, "Write me a poem").json()
        assert body["answer"]["suggest_ticket"] is False

    def test_missing_on_topic_key_is_treated_as_off_topic(self, client,
                                                          fake_claude):
        """Fail closed. `is not True` rather than `== False`, so a malformed
        response cannot smuggle an ungrounded answer through."""
        fake_claude.support_response = {"confidence": 0.95,
                                        "answer": "Some ungrounded claim.",
                                        "faq_ids": []}
        body = _ask(client, "anything").json()
        assert body["answer"]["text"] == support_kb.REFUSAL_MESSAGE

    @pytest.mark.parametrize("bogus", [
        "yes", 1, "true", None, {"nested": True},
    ])
    def test_truthy_but_not_True_still_refuses(self, client, fake_claude, bogus):
        fake_claude.support_response = {"on_topic": bogus, "confidence": 0.9,
                                        "answer": "Ungrounded.", "faq_ids": []}
        assert _ask(client, "q").json()["answer"]["text"] == support_kb.REFUSAL_MESSAGE

    def test_system_prompt_carries_the_rules_and_the_whole_kb(self, client,
                                                              fake_claude):
        _ask(client, "what is leadpilot")
        # FakeClaude records the user prompt; the system prompt is asserted
        # directly since that is where the rules live.
        system = support_chat.SYSTEM_PROMPT_HEADER
        assert "ONLY source of truth" in system
        assert "on_topic" in system
        assert "ignore these rules" in system   # prompt-injection wording
        assert "Never invent a URL" in system


class TestConfidenceFloor:
    def test_low_confidence_answer_is_DISCARDED(self, client, fake_claude):
        """A hedged wrong answer still reads as an answer."""
        fake_claude.support_response = {
            "on_topic": True, "confidence": 0.2,
            "answer": "I think maybe LeadPilot costs $99?", "faq_ids": [],
        }
        body = _ask(client, "how much does it cost").json()
        assert body["answer"]["text"] == support_kb.TICKET_SUGGESTION
        assert "$99" not in body["answer"]["text"]
        assert body["answer"]["suggest_ticket"] is True
        assert body["answer"]["reason"] == "low_confidence"

    def test_exactly_at_the_threshold_is_accepted(self, client, fake_claude):
        fake_claude.support_response = {"on_topic": True, "confidence": 0.5,
                                        "answer": "Grounded answer.",
                                        "faq_ids": ["what-is-leadpilot"]}
        assert _ask(client, "q").json()["answer"]["reason"] == "answered"

    @pytest.mark.parametrize("value", ["not-a-number", None, [], float("nan")])
    def test_unparseable_confidence_falls_to_zero_and_offers_a_ticket(
        self, client, fake_claude, value
    ):
        """NaN specifically: every comparison against it is False, so a naive
        `confidence < threshold` check would let it straight through."""
        fake_claude.support_response = {"on_topic": True, "confidence": value,
                                        "answer": "Claim.", "faq_ids": []}
        assert _ask(client, "q").json()["answer"]["suggest_ticket"] is True

    def test_confidence_above_one_is_clamped(self, client, fake_claude):
        fake_claude.support_response = {"on_topic": True, "confidence": 42,
                                        "answer": "Grounded.", "faq_ids": []}
        assert _ask(client, "q").json()["answer"]["confidence"] == 1.0


class TestFailureFallbacks:
    def test_model_outage_degrades_to_a_ticket_not_a_500(self, client,
                                                         fake_claude):
        fake_claude.support_response = RuntimeError("anthropic is down")
        resp = _ask(client, "what is leadpilot")
        assert resp.status_code == 200
        assert resp.json()["answer"]["reason"] == "model_error"
        assert resp.json()["answer"]["suggest_ticket"] is True

    def test_non_dict_response_degrades_to_a_ticket(self, client, fake_claude):
        fake_claude.support_response = ["not", "an", "object"]
        assert _ask(client, "q").json()["answer"]["reason"] == "malformed_response"

    def test_empty_answer_string_degrades_to_a_ticket(self, client, fake_claude):
        fake_claude.support_response = {"on_topic": True, "confidence": 0.9,
                                        "answer": "   ", "faq_ids": []}
        assert _ask(client, "q").json()["answer"]["reason"] == "empty_answer"

    def test_answer_question_never_raises(self, fake_claude, monkeypatch):
        from app.services import anthropic_client
        monkeypatch.setattr(anthropic_client, "get_client", lambda: fake_claude)
        for response in (RuntimeError("boom"), None, "string", 42, {}):
            fake_claude.support_response = response
            result = support_chat.answer_question("what is leadpilot")
            assert isinstance(result, support_chat.SupportAnswer)

    def test_hallucinated_faq_ids_are_stripped(self, client, fake_claude):
        """A fabricated citation must never be stored as if it were real —
        it is the clearest signal the model is inventing rather than citing."""
        fake_claude.support_response = {
            "on_topic": True, "confidence": 0.9, "answer": "Grounded.",
            "faq_ids": ["what-is-leadpilot", "totally-made-up", 42, None],
        }
        assert _ask(client, "q").json()["answer"]["faq_ids"] == ["what-is-leadpilot"]


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


class TestChatPersistence:
    def test_both_turns_are_stored(self, client, db_session):
        _ask(client, "What is LeadPilot?")
        rows = db_session.execute(
            select(m.ChatMessage).order_by(m.ChatMessage.created_at)
        ).scalars().all()
        assert [r.role for r in rows] == ["user", "assistant"]
        assert rows[0].content == "What is LeadPilot?"

    def test_refusals_are_stored_too(self, client, db_session, fake_claude):
        """An answer nobody can read back is an answer nobody can audit."""
        fake_claude.support_response = {"on_topic": False, "confidence": 1.0,
                                        "answer": "", "faq_ids": []}
        _ask(client, "capital of France")
        assistant = db_session.execute(
            select(m.ChatMessage).where(m.ChatMessage.role == "assistant")
        ).scalars().one()
        assert assistant.reason == "off_topic"
        assert assistant.content == support_kb.REFUSAL_MESSAGE

    def test_diagnostics_are_persisted(self, client, db_session):
        _ask(client, "What is LeadPilot?")
        assistant = db_session.execute(
            select(m.ChatMessage).where(m.ChatMessage.role == "assistant")
        ).scalars().one()
        assert assistant.confidence == 0.9
        assert assistant.faq_ids == ["what-is-leadpilot"]

    def test_follow_ups_continue_the_same_session(self, client, db_session):
        first = _ask(client, "What is LeadPilot?").json()["session_id"]
        second = _ask(client, "And what does it replace?").json()["session_id"]
        assert first == second
        assert db_session.execute(
            select(m.ChatSession)
        ).scalars().all().__len__() == 1

    def test_history_is_passed_to_the_model(self, client, fake_claude):
        _ask(client, "What is LeadPilot?")
        _ask(client, "what about the second one?")
        assert "What is LeadPilot?" in fake_claude.support_prompts[-1]

    def test_new_session_starts_a_separate_thread(self, client):
        _ask(client, "first question")
        new_id = client.post("/support/chat/sessions").json()["id"]
        used = _ask(client, "unrelated question", session_id=new_id).json()["session_id"]
        assert used == new_id
        assert len(client.get("/support/chat/sessions").json()["sessions"]) == 2

    def test_session_title_comes_from_the_first_question(self, client):
        _ask(client, "How do I set up my first campaign?")
        sessions = client.get("/support/chat/sessions").json()["sessions"]
        assert sessions[0]["title"] == "How do I set up my first campaign?"

    def test_get_session_returns_the_transcript(self, client):
        session_id = _ask(client, "What is LeadPilot?").json()["session_id"]
        payload = client.get(f"/support/chat/sessions/{session_id}").json()
        assert [msg["role"] for msg in payload["messages"]] == ["user", "assistant"]

    def test_delete_removes_the_session_and_its_messages(self, client, db_session):
        session_id = _ask(client, "hello").json()["session_id"]
        assert client.delete(f"/support/chat/sessions/{session_id}").status_code == 200
        assert db_session.execute(select(m.ChatSession)).scalars().all() == []
        assert db_session.execute(select(m.ChatMessage)).scalars().all() == []


# --------------------------------------------------------------------------
# Isolation
# --------------------------------------------------------------------------


class TestAccessControl:
    def test_requires_authentication(self, anon_client):
        assert anon_client.get("/support/faq").status_code == 401
        assert anon_client.post("/support/chat",
                                json={"message": "hi"}).status_code == 401

    def test_unverified_users_are_blocked_by_the_feature_1_gate(self, client):
        tokens = client.post("/auth/signup", json={"email": "chat@x.com",
                                                   "password": "hunter22!"}).json()
        resp = client.post("/support/chat", json={"message": "hi"},
                           headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert resp.status_code == 403
        assert resp.json()["detail"] == "EMAIL_NOT_VERIFIED"

    def test_one_user_cannot_read_anothers_session(self, client, db_session):
        session_id = _ask(client, "my private question").json()["session_id"]
        other = m.User(email=f"other_{uuid.uuid4().hex[:6]}@x.com",
                       email_verified=True)
        db_session.add(other)
        db_session.commit()

        resp = client.get(f"/support/chat/sessions/{session_id}",
                          headers=auth_headers(other))
        # 404, not 403 — otherwise the status code is an oracle for
        # "does this session id exist?"
        assert resp.status_code == 404

    def test_one_user_cannot_delete_anothers_session(self, client, db_session):
        session_id = _ask(client, "mine").json()["session_id"]
        other = m.User(email=f"other2_{uuid.uuid4().hex[:6]}@x.com",
                       email_verified=True)
        db_session.add(other)
        db_session.commit()
        assert client.delete(f"/support/chat/sessions/{session_id}",
                             headers=auth_headers(other)).status_code == 404
        assert db_session.execute(select(m.ChatSession)).scalars().all()

    def test_sessions_list_shows_only_your_own(self, client, db_session):
        _ask(client, "mine")
        other = m.User(email=f"other3_{uuid.uuid4().hex[:6]}@x.com",
                       email_verified=True)
        db_session.add(other)
        db_session.commit()
        assert client.get("/support/chat/sessions",
                          headers=auth_headers(other)).json()["sessions"] == []


class TestRateLimit:
    def test_chat_is_capped_per_user_per_day(self, client, monkeypatch):
        """Every message spends the account's Anthropic key — this is a cost
        ceiling first and an abuse control second."""
        from app.core.config import settings as core_settings
        monkeypatch.setattr(core_settings, "RATE_LIMIT_SUPPORT_CHAT", 3)
        codes = [_ask(client, f"question {i}").status_code for i in range(5)]
        assert 429 in codes, codes
        assert codes[-1] == 429

    def test_an_invalid_body_costs_no_quota(self, client, monkeypatch):
        """The limiter runs AFTER validation — same ordering guarantee the
        auth routes rely on."""
        from app.core.config import settings as core_settings
        monkeypatch.setattr(core_settings, "RATE_LIMIT_SUPPORT_CHAT", 2)
        for _ in range(5):
            assert client.post("/support/chat", json={"message": ""}).status_code == 422
        assert _ask(client, "a real question").status_code == 200

    def test_tickets_are_NOT_blocked_by_the_chat_budget(self, client, monkeypatch):
        """Someone who has run out of messages is exactly the person who most
        needs to reach a human."""
        from app.core.config import settings as core_settings
        monkeypatch.setattr(core_settings, "RATE_LIMIT_SUPPORT_CHAT", 1)
        _ask(client, "one")
        assert _ask(client, "two").status_code == 429
        assert client.post("/support/tickets", json={
            "subject": "Need help", "body": "The chat is out of messages."
        }).status_code == 201


class TestKillSwitch:
    def test_disabled_chat_returns_503_but_tickets_still_work(self, client,
                                                              monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "support_chat_enabled", False)
        assert _ask(client, "hello").status_code == 503
        assert client.post("/support/tickets", json={
            "subject": "Still need help", "body": "Chat is disabled right now."
        }).status_code == 201

    def test_faq_reports_the_switch(self, client, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "support_chat_enabled", False)
        assert client.get("/support/faq").json()["chat_enabled"] is False


# --------------------------------------------------------------------------
# Tickets
# --------------------------------------------------------------------------


class TestTickets:
    def test_create_and_list(self, client):
        created = client.post("/support/tickets", json={
            "subject": "Billing question",
            "body": "I need help with something the bot could not answer.",
        })
        assert created.status_code == 201
        assert created.json()["status"] == "open"
        assert client.get("/support/tickets").json()["tickets"][0]["subject"] \
            == "Billing question"

    def test_ticket_can_reference_the_conversation(self, client):
        session_id = _ask(client, "something confusing").json()["session_id"]
        ticket = client.post("/support/tickets", json={
            "subject": "Following up", "body": "The chat could not help me.",
            "chat_session_id": session_id,
        }).json()
        assert ticket["chat_session_id"] == session_id

    def test_ticket_SURVIVES_deletion_of_its_chat(self, client, db_session):
        """ON DELETE SET NULL. Losing the conversation is acceptable; losing an
        open support ticket is not."""
        session_id = _ask(client, "confusing").json()["session_id"]
        client.post("/support/tickets", json={
            "subject": "Keep me", "body": "This must outlive the chat purge.",
            "chat_session_id": session_id,
        })
        client.delete(f"/support/chat/sessions/{session_id}")

        tickets = client.get("/support/tickets").json()["tickets"]
        assert len(tickets) == 1
        assert tickets[0]["subject"] == "Keep me"
        assert tickets[0]["chat_session_id"] is None

    def test_cannot_attach_someone_elses_session(self, client, db_session):
        session_id = _ask(client, "mine").json()["session_id"]
        other = m.User(email=f"other4_{uuid.uuid4().hex[:6]}@x.com",
                       email_verified=True)
        db_session.add(other)
        db_session.commit()
        assert client.post("/support/tickets", json={
            "subject": "Snooping", "body": "Trying to attach another session.",
            "chat_session_id": session_id,
        }, headers=auth_headers(other)).status_code == 404

    def test_you_only_see_your_own_tickets(self, client, db_session):
        client.post("/support/tickets", json={"subject": "Mine",
                                              "body": "My private issue."})
        other = m.User(email=f"other5_{uuid.uuid4().hex[:6]}@x.com",
                       email_verified=True)
        db_session.add(other)
        db_session.commit()
        assert client.get("/support/tickets",
                          headers=auth_headers(other)).json()["tickets"] == []

    @pytest.mark.parametrize("payload", [
        {"subject": "ab", "body": "long enough body here"},   # subject too short
        {"subject": "fine", "body": "short"},                  # body too short
    ])
    def test_validation(self, client, payload):
        assert client.post("/support/tickets", json=payload).status_code == 422


class TestAdminTickets:
    def _admin(self, db_session):
        admin = m.User(email=f"admin_{uuid.uuid4().hex[:6]}@x.com",
                       is_admin=True, email_verified=True)
        db_session.add(admin)
        db_session.commit()
        return admin

    def test_non_admin_refused(self, client):
        assert client.get("/admin/support/tickets").status_code == 403

    def test_admin_sees_tickets_with_the_requester_email(self, client, db_session):
        """Unlike tutorial progress, a ticket you cannot reply to is useless —
        the requester's address is the entire point."""
        admin = self._admin(db_session)
        client.post("/support/tickets", json={"subject": "Help me",
                                              "body": "Something is broken."})
        data = client.get("/admin/support/tickets",
                          headers=auth_headers(admin)).json()
        assert data["open_count"] == 1
        assert data["tickets"][0]["user_email"] == "test@leadpilot.dev"

    def test_resolve_closes_the_ticket(self, client, db_session):
        admin = self._admin(db_session)
        ticket_id = client.post("/support/tickets", json={
            "subject": "Fix", "body": "Please fix this thing."}).json()["id"]
        resp = client.post(f"/admin/support/tickets/{ticket_id}/resolve",
                           json={"note": "Explained in reply"},
                           headers=auth_headers(admin))
        assert resp.status_code == 200 and resp.json()["status"] == "resolved"
        mine = client.get("/support/tickets").json()["tickets"][0]
        assert mine["status"] == "resolved"
        assert mine["resolution_note"] == "Explained in reply"

    def test_resolving_twice_keeps_the_original_timestamp(self, client, db_session):
        """Otherwise a second click rewrites the response-time record."""
        admin = self._admin(db_session)
        ticket_id = client.post("/support/tickets", json={
            "subject": "Fix", "body": "Please fix this thing."}).json()["id"]
        client.post(f"/admin/support/tickets/{ticket_id}/resolve", json={},
                    headers=auth_headers(admin))
        first = client.get("/support/tickets").json()["tickets"][0]["resolved_at"]
        client.post(f"/admin/support/tickets/{ticket_id}/resolve", json={},
                    headers=auth_headers(admin))
        assert client.get("/support/tickets").json()["tickets"][0]["resolved_at"] == first

    def test_unknown_ticket_id_is_404_not_500(self, client, db_session):
        admin = self._admin(db_session)
        for bad in ("not-a-uuid", str(uuid.uuid4())):
            assert client.post(f"/admin/support/tickets/{bad}/resolve", json={},
                               headers=auth_headers(admin)).status_code == 404

    def test_status_filter(self, client, db_session):
        admin = self._admin(db_session)
        a = client.post("/support/tickets", json={"subject": "One",
                                                  "body": "First issue."}).json()["id"]
        client.post("/support/tickets", json={"subject": "Two",
                                              "body": "Second issue."})
        client.post(f"/admin/support/tickets/{a}/resolve", json={},
                    headers=auth_headers(admin))
        h = auth_headers(admin)
        assert len(client.get("/admin/support/tickets?status=open", headers=h)
                   .json()["tickets"]) == 1
        assert len(client.get("/admin/support/tickets?status=resolved", headers=h)
                   .json()["tickets"]) == 1


# --------------------------------------------------------------------------
# Retention
# --------------------------------------------------------------------------


class TestRetention:
    def test_purges_sessions_past_the_window(self, client, db_session, monkeypatch):
        from app.workers import support_tasks

        _ask(client, "recent question")
        old = m.ChatSession(
            user_id=db_session.execute(select(m.User)).scalars().first().id,
            title="ancient",
            last_message_at=datetime.now(timezone.utc) - timedelta(days=40),
        )
        db_session.add(old)
        db_session.commit()

        monkeypatch.setattr(support_tasks, "SessionLocal", None, raising=False)
        # The task opens its own session; point it at this test's session
        # factory so it operates on the same in-memory database.
        import app.db.base as db_base
        monkeypatch.setattr(db_base, "SessionLocal", lambda: db_session)

        deleted = support_tasks.purge_expired_chat_sessions(retention_days=30)
        assert deleted == 1
        remaining = db_session.execute(select(m.ChatSession)).scalars().all()
        assert [s.title for s in remaining] != ["ancient"]

    def test_purge_keys_on_last_message_not_created_at(self, client, db_session,
                                                       monkeypatch):
        """A conversation started six weeks ago but used yesterday is not
        stale — purging on created_at deletes a live thread mid-sentence."""
        import app.db.base as db_base
        from app.workers import support_tasks

        user = db_session.execute(select(m.User)).scalars().first()
        session = m.ChatSession(
            user_id=user.id, title="old but active",
            created_at=datetime.now(timezone.utc) - timedelta(days=45),
            last_message_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db_session.add(session)
        db_session.commit()

        monkeypatch.setattr(db_base, "SessionLocal", lambda: db_session)
        assert support_tasks.purge_expired_chat_sessions(retention_days=30) == 0
        assert db_session.execute(select(m.ChatSession)).scalars().all()

    def test_retention_of_zero_disables_the_purge(self, client, db_session,
                                                  monkeypatch):
        import app.db.base as db_base
        from app.workers import support_tasks

        _ask(client, "keep me")
        monkeypatch.setattr(db_base, "SessionLocal", lambda: db_session)
        assert support_tasks.purge_expired_chat_sessions(retention_days=0) == 0
        assert db_session.execute(select(m.ChatSession)).scalars().all()

    def test_sessions_endpoint_reports_the_retention_window(self, client):
        assert client.get("/support/chat/sessions").json()["retention_days"] == 30

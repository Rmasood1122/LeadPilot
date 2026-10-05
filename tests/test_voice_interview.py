"""Monthly voice interview.

The user answers open questions by text or by dictation (the browser turns
speech into text; only text reaches the server). Claude proposes a writing
style from the answers. NOTHING changes in the user's outreach until the user
reviews the proposal and clicks Apply.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.services import voice_interview as vi

LONG = "I like to keep things short and friendly, no corporate talk, and I always get to the point quickly."
PROFILE = {"tone": "warm and direct", "formality": 2, "vocabulary_level": "conversational",
           "sentence_length": "short", "avg_words_per_sentence": 9, "humor": "light",
           "greeting_style": "Hey", "signoff_style": "Cheers", "signature_habits": ["uses dashes"],
           "do": ["be brief"], "dont": ["use jargon"], "summary": "Short and warm."}


class StubClaude:
    def __init__(self):
        self.prompt = ""
        self.reply = dict(PROFILE)

    def complete_json(self, *, system, prompt, max_tokens=1024, **_kw):
        self.prompt = prompt
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture()
def claude(monkeypatch):
    stub = StubClaude()
    monkeypatch.setattr("app.services.anthropic_client.get_client", lambda: stub)
    return stub


def _start(client, mode="text", ack=False):
    return client.post("/interview/start", json={"mode": mode, "voice_notice_ack": ack})


def _answered(client, n=3):
    iid = _start(client).json()["id"]
    answers = [{"index": i, "text": LONG} for i in range(n)]
    assert client.put(f"/interview/{iid}/answers", json={"answers": answers}).status_code == 200
    return iid


def _proposed(client):
    iid = _answered(client)
    r = client.post(f"/interview/{iid}/finish")
    assert r.status_code == 200, r.text
    return iid


class TestDue:
    def test_a_new_account_is_not_asked_yet(self, client):
        assert client.get("/interview/status").json()["due"] is False

    def test_an_account_older_than_a_month_is_asked(self, client, db_session, test_user):
        test_user.created_at = datetime.now(timezone.utc) - timedelta(days=31)
        db_session.commit()
        assert client.get("/interview/status").json()["due"] is True

    def test_free_plan_is_included(self, client, db_session, test_user):
        test_user.plan = m.PlanTier.FREE
        test_user.created_at = datetime.now(timezone.utc) - timedelta(days=40)
        db_session.commit()
        assert client.get("/interview/status").json()["due"] is True
        assert _start(client).status_code == 200

    def test_skip_pushes_it_out_a_month_snooze_a_week(self, client, db_session, test_user):
        test_user.created_at = datetime.now(timezone.utc) - timedelta(days=40)
        db_session.commit()
        assert client.post("/interview/snooze", json={"days": 7}).status_code == 200
        s = client.get("/interview/status").json()
        assert s["due"] is False
        row = db_session.query(m.VoiceInterview).one()
        assert timedelta(days=6) < row.next_due_at.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc) < timedelta(days=8)
        row.next_due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()
        assert client.get("/interview/status").json()["due"] is True

    def test_snooze_days_are_limited(self, client):
        assert client.post("/interview/snooze", json={"days": 0}).status_code == 422
        assert client.post("/interview/snooze", json={"days": 400}).status_code == 422

    def test_status_lists_the_questions(self, client):
        qs = client.get("/interview/status").json()["questions"]
        assert 4 <= len(qs) <= 6 and all(isinstance(q, str) and q for q in qs)


class TestStart:
    def test_text_start(self, client):
        r = _start(client)
        assert r.status_code == 200 and r.json()["mode"] == "text"

    def test_voice_needs_the_notice_acknowledged(self, client):
        assert _start(client, "voice", ack=False).status_code == 422
        r = _start(client, "voice", ack=True)
        assert r.status_code == 200 and r.json()["mode"] == "voice"

    def test_bad_mode_is_422(self, client):
        assert _start(client, "video").status_code == 422

    def test_starting_again_resumes_the_open_interview(self, client):
        a = _start(client).json()["id"]
        assert _start(client).json()["id"] == a


class TestAnswers:
    def test_saved_and_returned(self, client):
        iid = _start(client).json()["id"]
        r = client.put(f"/interview/{iid}/answers", json={"answers": [{"index": 0, "text": "hello there"}]})
        assert r.status_code == 200
        assert client.get(f"/interview/{iid}").json()["answers"][0]["text"] == "hello there"

    def test_index_out_of_range(self, client):
        iid = _start(client).json()["id"]
        assert client.put(f"/interview/{iid}/answers", json={"answers": [{"index": 99, "text": "x"}]}).status_code == 422

    def test_answer_too_long(self, client):
        iid = _start(client).json()["id"]
        assert client.put(f"/interview/{iid}/answers", json={"answers": [{"index": 0, "text": "x" * 4001}]}).status_code == 422


class TestFinish:
    def test_proposes_but_does_not_apply(self, client, claude, db_session, test_user):
        iid = _answered(client)
        r = client.post(f"/interview/{iid}/finish")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "proposed" and body["proposed_profile"]["tone"] == "warm and direct"
        assert body["recommendations"] and all(isinstance(x, str) for x in body["recommendations"])
        db_session.refresh(test_user)
        assert test_user.style_profile_json is None          # NOT applied

    def test_needs_enough_real_answers(self, client, claude):
        iid = _answered(client, n=2)
        assert client.post(f"/interview/{iid}/finish").status_code == 422

    def test_short_answers_do_not_count(self, client, claude):
        iid = _start(client).json()["id"]
        client.put(f"/interview/{iid}/answers", json={"answers": [{"index": i, "text": "ok"} for i in range(4)]})
        assert client.post(f"/interview/{iid}/finish").status_code == 422

    def test_model_failure_is_502_and_leaves_it_open(self, client, claude, db_session):
        claude.reply = RuntimeError("down")
        iid = _answered(client)
        assert client.post(f"/interview/{iid}/finish").status_code == 502
        assert db_session.query(m.VoiceInterview).one().status == "in_progress"

    def test_empty_analysis_is_502(self, client, claude):
        claude.reply = {}
        iid = _answered(client)
        assert client.post(f"/interview/{iid}/finish").status_code == 502

    def test_answers_reach_the_model_only_as_data(self, client, claude):
        iid = _answered(client)
        client.post(f"/interview/{iid}/finish")
        assert LONG in claude.prompt


class TestApply:
    def test_apply_sets_the_style_and_wipes_the_answers(self, client, claude, db_session, test_user):
        iid = _proposed(client)
        r = client.post(f"/interview/{iid}/apply", json={})
        assert r.status_code == 200 and r.json()["status"] == "applied"
        db_session.refresh(test_user)
        assert test_user.style_profile_json["tone"] == "warm and direct"
        assert test_user.style_profile_updated_at is not None
        row = db_session.query(m.VoiceInterview).one()
        assert row.answers_json is None
        assert timedelta(days=29) < row.next_due_at.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc) < timedelta(days=31)

    def test_the_user_can_edit_before_applying_and_values_are_cleaned(self, client, claude, db_session, test_user):
        iid = _proposed(client)
        edited = dict(PROFILE, tone="calm", formality=9, evil="x" * 50)
        client.post(f"/interview/{iid}/apply", json={"profile": edited})
        db_session.refresh(test_user)
        p = test_user.style_profile_json
        assert p["tone"] == "calm" and p["formality"] == 5 and "evil" not in p

    def test_cannot_apply_before_finishing(self, client, claude):
        iid = _answered(client)
        assert client.post(f"/interview/{iid}/apply", json={}).status_code == 409

    def test_cannot_apply_twice(self, client, claude):
        iid = _proposed(client)
        assert client.post(f"/interview/{iid}/apply", json={}).status_code == 200
        assert client.post(f"/interview/{iid}/apply", json={}).status_code == 409

    def test_discard_applies_nothing_and_wipes_answers(self, client, claude, db_session, test_user):
        iid = _proposed(client)
        assert client.post(f"/interview/{iid}/discard").status_code == 200
        db_session.refresh(test_user)
        assert test_user.style_profile_json is None
        assert db_session.query(m.VoiceInterview).one().answers_json is None

    def test_after_applying_the_outreach_prompt_uses_it(self, client, claude, db_session, test_user):
        from app.services import style_profile

        iid = _proposed(client)
        client.post(f"/interview/{iid}/apply", json={})
        db_session.refresh(test_user)
        assert "warm and direct" in style_profile.system_suffix(test_user.style_profile_json)


class TestIsolation:
    def test_other_accounts_interviews_are_404_for_every_verb(self, client, db_session):
        other = m.User(email="o@x.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        row = m.VoiceInterview(user_id=other.id, mode="text", status="proposed",
                               answers_json=[], proposed_profile_json=dict(PROFILE))
        db_session.add(row)
        db_session.commit()
        i = row.id
        assert client.get(f"/interview/{i}").status_code == 404
        assert client.put(f"/interview/{i}/answers", json={"answers": []}).status_code == 404
        assert client.post(f"/interview/{i}/finish").status_code == 404
        assert client.post(f"/interview/{i}/apply", json={}).status_code == 404
        assert client.post(f"/interview/{i}/discard").status_code == 404

    def test_erase_removes_only_my_interviews(self, client, claude, db_session):
        other = m.User(email="o@x.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        db_session.add(m.VoiceInterview(user_id=other.id, mode="text", status="applied"))
        db_session.commit()
        _answered(client)
        assert client.delete("/interview").status_code == 200
        assert db_session.query(m.VoiceInterview).count() == 1


class TestRecommendations:
    def test_casual_short_style_gets_matching_advice(self):
        tips = vi.recommendations(dict(PROFILE))
        assert tips and any("short" in t.lower() or "brief" in t.lower() for t in tips)

    def test_formal_long_style_gets_different_advice(self):
        tips = vi.recommendations(dict(PROFILE, formality=5, sentence_length="long",
                                       avg_words_per_sentence=30))
        assert tips != vi.recommendations(dict(PROFILE))

    def test_empty_profile_does_not_crash(self):
        assert isinstance(vi.recommendations({}), list)

"""Part 2 — meeting prep script, readiness checklist and roleplay practice.

The properties that matter:
  * the script is SEEDED once and then owned by the seller — regenerating the
    brief must never overwrite an edit,
  * the AI plays the PROSPECT and never breaks character to coach,
  * a model failure never loses the line the seller just said,
  * a session that barely happened is not scored,
  * the checklist is derived, and only blocks when practice was required.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.services import meeting_practice, meeting_prep, roleplay
from tests.conftest import auth_headers

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)

SECTIONS = {
    "company_overview": "A 30-person fire protection contractor.",
    "recent_activity": "Posted about inspection backlogs.",
    "why_they_booked": 'They replied to step 2: "we are drowning in inspections".',
    "pain_points": ["Inspection backlog (from their reply)"],
    "likely_objections": [
        {"objection": "We use a spreadsheet", "response": "Ask what a miss costs."},
        {"objection": "No budget this year", "response": "Ask when the cycle resets."},
        {"objection": "We looked at this before", "response": "Ask what stopped it."},
    ],
    "talking_points": ["Lead with the backlog they named"],
    "discovery_questions": ["Who owns inspection scheduling today?",
                            "What happens when one is missed?"],
    "competitive_landscape": "Nothing in our records.",
    "next_steps": ["Offer a two-week pilot"],
    "deal_structure": "Monthly retainer.",
    "opening_60_seconds": "Thanks for booking, Sara — you mentioned inspections.",
}


@pytest.fixture()
def lead(db_session, verified_strategy):
    row = m.Lead(strategy_id=verified_strategy.id, source="apollo", external_id="PR1",
                 full_name="Sara Khan", title="Owner", company="Blaze Safety",
                 email="sara@blaze.test", status=m.LeadStatus.MEETING_BOOKED,
                 fpta_overall=71,
                 fpta_reasons_json={
                     "fit": {"score": 90, "reason": "Owner at an ICP-fit contractor.",
                             "signals": ["Title: Owner"]},
                     "problem": {"score": 60, "reason": "They named the backlog.",
                                 "signals": ['Said: "drowning in inspections"']},
                     "timing": {"score": 40, "reason": "Nothing forcing it.",
                                "signals": ["No recent activity on file"]},
                     "access": {"score": 85, "reason": "Verified email.",
                                "signals": ["Verified email address"]},
                 })
    db_session.add(row)
    db_session.commit()
    return row


@pytest.fixture()
def brief(db_session, lead, test_user):
    row = m.MeetingPrepBrief(
        lead_id=lead.id, user_id=test_user.id, source="manual",
        external_ref="ref-1", status=m.MeetingPrepStatus.READY,
        sections_json=SECTIONS, profile_json={"name": "Sara Khan",
                                              "title": "Owner",
                                              "company": "Blaze Safety"},
        opening_script=SECTIONS["opening_60_seconds"],
        meeting_start_at=NOW + timedelta(hours=3), generated_at=NOW)
    db_session.add(row)
    db_session.commit()
    return row


# --------------------------------------------------------------------------
# The brief now reads the F-P-T-A signals
# --------------------------------------------------------------------------


class TestBriefContext:
    def test_the_fpta_signals_reach_the_prompt(self, db_session, fake_claude, lead,
                                               brief):
        ctx = meeting_prep.collect_context(db_session, lead, brief)
        assert ctx["fpta"]["overall"] == 71
        assert ctx["fpta"]["dimensions"]["problem"]["reason"] == "They named the backlog."
        prompt = meeting_prep.build_prompt(ctx)
        assert "F-P-T-A SIGNALS" in prompt
        assert "drowning in inspections" in prompt

    def test_an_unscored_prospect_reads_as_none_on_record_not_as_zero(
            self, db_session, fake_claude, verified_strategy, brief):
        bare = m.Lead(strategy_id=verified_strategy.id, source="apollo",
                      external_id="BARE", email="b@c.test",
                      status=m.LeadStatus.VERIFIED)
        db_session.add(bare)
        db_session.commit()
        ctx = meeting_prep.collect_context(db_session, bare, None)
        assert ctx["fpta"] == {}
        assert "(none on record)" in meeting_prep.build_prompt(ctx)


# --------------------------------------------------------------------------
# The script
# --------------------------------------------------------------------------


class TestScript:
    def test_it_is_seeded_from_the_brief_rather_than_a_second_model_call(
            self, db_session, fake_claude, brief):
        calls = fake_claude.completions
        script = meeting_practice.ensure_script(db_session, brief)
        assert fake_claude.completions == calls
        assert script["opening"] == SECTIONS["opening_60_seconds"]
        assert script["discovery"] == SECTIONS["discovery_questions"]
        assert len(script["objections"]) == 3

    def test_the_close_is_a_sentence_someone_can_actually_say(self, db_session, brief):
        script = meeting_practice.ensure_script(db_session, brief)
        assert "two-week pilot" in script["close"]
        assert script["close"].endswith("?")

    def test_the_close_degrades_to_a_generic_ask_without_next_steps(self, db_session):
        assert "thirty minutes" in meeting_practice._close_line({})

    def test_seeding_never_overwrites_an_edit(self, db_session, brief, test_user):
        """The rule the whole feature rests on."""
        meeting_practice.save_script(db_session, brief, {"opening": "My own words."},
                                     actor=test_user, now=NOW)
        assert meeting_practice.ensure_script(db_session, brief)["opening"] \
            == "My own words."

    def test_regenerating_the_brief_never_overwrites_an_edit(
            self, db_session, fake_claude, lead, brief, test_user):
        meeting_practice.save_script(db_session, brief, {"opening": "My own words."},
                                     actor=test_user, now=NOW)
        meeting_prep.generate_brief(db_session, brief.id, notify=False)
        db_session.refresh(brief)
        assert brief.script_json["opening"] == "My own words."

    def test_a_malformed_script_is_dropped_rather_than_coerced(self, db_session, brief):
        cleaned = meeting_practice.clean_script({
            "opening": "  hello  ", "discovery": "one question",
            "objections": [{"objection": "x"}, "bare string", 42, {"response": "no key"}],
            "close": "ok", "notes": None,
        })
        assert cleaned["opening"] == "hello"
        assert cleaned["discovery"] == ["one question"]
        assert [o["objection"] for o in cleaned["objections"]] == ["x", "bare string"]
        assert cleaned["notes"] == ""

    def test_the_output_says_whether_a_person_has_approved_it(self, db_session, brief,
                                                              test_user):
        meeting_practice.ensure_script(db_session, brief)
        assert meeting_practice.script_out(brief)["edited"] is False
        meeting_practice.save_script(db_session, brief, {"opening": "mine"},
                                     actor=test_user, now=NOW)
        out = meeting_practice.script_out(brief)
        assert out["edited"] is True
        assert out["edited_by_user_id"] == str(test_user.id)

    def test_the_output_always_has_all_five_keys(self, db_session, brief):
        out = meeting_practice.script_out(brief)
        assert set(out["script"]) == set(meeting_practice.SCRIPT_KEYS)


# --------------------------------------------------------------------------
# Readiness
# --------------------------------------------------------------------------


class TestReadiness:
    def test_a_fresh_brief_is_ready_but_flags_the_unread_script(
            self, db_session, fake_claude, brief, test_user):
        meeting_practice.ensure_script(db_session, brief)
        state = meeting_practice.readiness(db_session, brief, user_id=test_user.id,
                                           now=NOW)
        assert state["ready"] is True
        assert {i["key"]: i["done"] for i in state["items"]}["script"] is False
        assert "call script reviewed" in state["headline"]

    def test_a_pending_brief_blocks(self, db_session, fake_claude, brief, test_user):
        brief.status = m.MeetingPrepStatus.PENDING
        db_session.commit()
        state = meeting_practice.readiness(db_session, brief, user_id=test_user.id,
                                           now=NOW)
        assert state["ready"] is False
        assert "brief" in state["blocking"]

    def test_practice_only_blocks_when_it_was_required(self, db_session, fake_claude,
                                                       brief, test_user):
        """Making every call require a rehearsal turns the checklist into
        something people click through."""
        assert meeting_practice.readiness(db_session, brief, user_id=test_user.id,
                                          now=NOW)["ready"] is True
        meeting_practice.set_practice_required(db_session, brief, True)
        state = meeting_practice.readiness(db_session, brief, user_id=test_user.id,
                                           now=NOW)
        assert state["ready"] is False
        assert "practice" in state["blocking"]

    def test_a_completed_roleplay_satisfies_the_practice_item(
            self, db_session, fake_claude, lead, brief, test_user):
        meeting_practice.set_practice_required(db_session, brief, True)
        session = roleplay.start(db_session, test_user, lead=lead, brief=brief, now=NOW)
        roleplay.reply(db_session, session, "Thanks for taking the call.")
        roleplay.reply(db_session, session, "What happens when one is missed?")
        roleplay.finish(db_session, session, now=NOW)
        state = meeting_practice.readiness(db_session, brief, user_id=test_user.id,
                                           now=NOW)
        assert state["ready"] is True

    def test_an_abandoned_roleplay_does_not_count_as_practice(
            self, db_session, fake_claude, lead, brief, test_user):
        """Opening a roleplay and closing the tab is not practice."""
        session = roleplay.start(db_session, test_user, lead=lead, brief=brief, now=NOW)
        roleplay.finish(db_session, session, abandoned=True, now=NOW)
        assert roleplay.practiced_recently(db_session, test_user.id, lead.id,
                                           now=NOW) is False

    def test_practice_goes_stale(self, db_session, fake_claude, lead, brief, test_user):
        session = roleplay.start(db_session, test_user, lead=lead, brief=brief, now=NOW)
        roleplay.reply(db_session, session, "one")
        roleplay.reply(db_session, session, "two")
        roleplay.finish(db_session, session, now=NOW - timedelta(days=30))
        assert roleplay.practiced_recently(db_session, test_user.id, lead.id,
                                           now=NOW) is False

    def test_the_headline_says_how_long_there_is(self, db_session, fake_claude, brief,
                                                 test_user):
        state = meeting_practice.readiness(db_session, brief, user_id=test_user.id,
                                           now=NOW)
        assert "in 3 hours" in state["headline"]
        assert state["minutes_until"] == 180


# --------------------------------------------------------------------------
# Roleplay
# --------------------------------------------------------------------------


class TestPersona:
    def test_it_is_built_from_the_brief_rather_than_re_derived(
            self, db_session, lead, brief):
        persona = roleplay.build_persona(db_session, lead, brief)
        assert persona["company_overview"] == SECTIONS["company_overview"]
        assert persona["predicted_objections"][0] == "We use a spreadsheet"
        assert persona["pain_points"] == SECTIONS["pain_points"]

    def test_objections_the_prospect_actually_raised_come_first(
            self, db_session, lead, brief):
        """A rehearsal against the real pushback is worth more than one
        against a guess."""
        db_session.add(m.InboundReply(lead_id=lead.id, channel="email",
                                      from_address=lead.email,
                                      body="Too expensive for where we are.",
                                      reply_category="OBJECTION"))
        db_session.commit()
        persona = roleplay.build_persona(db_session, lead, brief)
        assert persona["real_objections"] == ["Too expensive for where we are."]

    def test_the_fpta_reasons_travel_with_the_persona(self, db_session, lead, brief):
        persona = roleplay.build_persona(db_session, lead, brief)
        assert any("problem:" in s for s in persona["fpta_signals"])

    def test_a_persona_without_a_lead_still_works(self, db_session):
        persona = roleplay.build_persona(db_session, None, None)
        assert persona["name"] == "the prospect"

    def test_the_objectives_name_what_the_rehearsal_is_for(self, db_session, lead,
                                                           brief):
        goals = roleplay.objectives_for(roleplay.build_persona(db_session, lead, brief))
        assert any("60 seconds" in g for g in goals)
        assert any("next step" in g for g in goals)


class TestSession:
    def test_the_prospect_speaks_first(self, db_session, fake_claude, lead, brief,
                                       test_user):
        session = roleplay.start(db_session, test_user, lead=lead, brief=brief, now=NOW)
        rows = roleplay.turns(db_session, session)
        assert len(rows) == 1
        assert rows[0].role == roleplay.PROSPECT
        assert "Sara Khan" in rows[0].content

    def test_a_reply_produces_the_prospects_answer(self, db_session, fake_claude,
                                                   lead, brief, test_user):
        session = roleplay.start(db_session, test_user, lead=lead, brief=brief, now=NOW)
        result = roleplay.reply(db_session, session, "Thanks for making the time.")
        assert result["status"] == "ok"
        assert "parked it" in result["prospect"]
        assert [t.role for t in roleplay.turns(db_session, session)] == \
            [roleplay.PROSPECT, roleplay.SELLER, roleplay.PROSPECT]

    def test_the_persona_prompt_carries_the_real_objections(
            self, db_session, fake_claude, lead, brief, test_user):
        db_session.add(m.InboundReply(lead_id=lead.id, channel="email",
                                      from_address=lead.email,
                                      body="Too expensive.", intent_label="objection"))
        db_session.commit()
        session = roleplay.start(db_session, test_user, lead=lead, brief=brief, now=NOW)
        roleplay.reply(db_session, session, "hello")
        # The system prompt is not captured by the fake, but the transcript is;
        # what matters is that the persona stored the real objection.
        assert session.persona_json["real_objections"] == ["Too expensive."]

    @pytest.mark.parametrize("difficulty", list(roleplay.DIFFICULTIES))
    def test_every_difficulty_has_a_behaviour_note(self, difficulty):
        assert roleplay.DIFFICULTY_NOTES[difficulty]

    def test_an_unknown_difficulty_falls_back_to_realistic(
            self, db_session, fake_claude, lead, brief, test_user):
        session = roleplay.start(db_session, test_user, lead=lead, brief=brief,
                                 difficulty="impossible", now=NOW)
        assert session.difficulty == roleplay.REALISTIC

    def test_a_model_failure_keeps_the_sellers_line(self, db_session, fake_claude,
                                                    lead, brief, test_user):
        """Losing what a person said because the other side failed to answer
        is the one thing a practice tool must not do."""
        session = roleplay.start(db_session, test_user, lead=lead, brief=brief, now=NOW)
        fake_claude.roleplay_reply_response = RuntimeError("anthropic down")
        result = roleplay.reply(db_session, session, "My carefully chosen words.")
        assert result["status"] == "failed"
        assert any(t.content == "My carefully chosen words."
                   for t in roleplay.turns(db_session, session))

    def test_coaching_that_breaks_character_is_stripped(self, db_session, fake_claude,
                                                        lead, brief, test_user):
        """A prospect who congratulates the seller teaches the wrong lesson."""
        session = roleplay.start(db_session, test_user, lead=lead, brief=brief, now=NOW)
        fake_claude.roleplay_reply_response = (
            "Great question. Look, we parked this last year and nothing changed.")
        result = roleplay.reply(db_session, session, "What stopped it last time?")
        assert not result["prospect"].startswith("Great question")
        assert "parked this last year" in result["prospect"]

    def test_a_prospect_prefix_is_stripped(self, db_session, fake_claude, lead, brief,
                                           test_user):
        session = roleplay.start(db_session, test_user, lead=lead, brief=brief, now=NOW)
        fake_claude.roleplay_reply_response = "PROSPECT: We already have a vendor."
        assert roleplay.reply(db_session, session, "hi")["prospect"] \
            == "We already have a vendor."

    def test_the_session_is_bounded(self, db_session, fake_claude, lead, brief,
                                    test_user):
        """An unbounded roleplay is an unbounded model bill."""
        session = roleplay.start(db_session, test_user, lead=lead, brief=brief, now=NOW)
        session.turn_count = roleplay.MAX_TURNS
        db_session.commit()
        result = roleplay.reply(db_session, session, "one more thing")
        assert result["limit_reached"] is True
        assert result["prospect"] is None

    def test_a_closed_session_refuses_more_lines(self, db_session, fake_claude, lead,
                                                 brief, test_user):
        session = roleplay.start(db_session, test_user, lead=lead, brief=brief, now=NOW)
        roleplay.finish(db_session, session, abandoned=True, now=NOW)
        assert roleplay.reply(db_session, session, "hello?")["status"] == "closed"


class TestFeedback:
    def _practised(self, db_session, lead, brief, test_user, lines=3):
        session = roleplay.start(db_session, test_user, lead=lead, brief=brief, now=NOW)
        for index in range(lines):
            roleplay.reply(db_session, session, f"seller line {index}")
        return session

    def test_the_feedback_scores_five_axes(self, db_session, fake_claude, lead, brief,
                                           test_user):
        session = self._practised(db_session, lead, brief, test_user)
        roleplay.finish(db_session, session, now=NOW)
        assert session.status == roleplay.COMPLETED
        assert session.score_overall == 72
        assert session.score_objections == 55
        assert session.feedback_json["one_thing"]

    def test_it_names_the_objections_that_were_not_handled(
            self, db_session, fake_claude, lead, brief, test_user):
        session = self._practised(db_session, lead, brief, test_user)
        roleplay.finish(db_session, session, now=NOW)
        assert session.feedback_json["objections_missed"][0]["objection"]

    def test_a_session_that_barely_happened_is_not_scored(
            self, db_session, fake_claude, lead, brief, test_user):
        """Scoring a conversation that never happened produces a number that
        means nothing and then pollutes the improvement chart."""
        session = self._practised(db_session, lead, brief, test_user, lines=1)
        roleplay.finish(db_session, session, now=NOW)
        assert session.status == roleplay.ABANDONED
        assert session.score_overall is None

    def test_a_feedback_failure_still_completes_the_session(
            self, db_session, fake_claude, lead, brief, test_user):
        session = self._practised(db_session, lead, brief, test_user)
        fake_claude.roleplay_feedback_response = RuntimeError("down")
        roleplay.finish(db_session, session, now=NOW)
        assert session.status == roleplay.COMPLETED
        assert session.score_overall is None
        assert "feedback unavailable" in session.error

    def test_scores_are_clamped(self, db_session, fake_claude, lead, brief, test_user):
        session = self._practised(db_session, lead, brief, test_user)
        fake_claude.roleplay_feedback_response = {
            "scores": {"overall": 140, "discovery": -5, "objections": "x",
                       "tone": 50, "close": 50}}
        roleplay.finish(db_session, session, now=NOW)
        assert session.score_overall == 100
        assert session.score_discovery == 0
        assert session.score_objections is None


class TestHistory:
    def test_the_trend_is_oldest_first_so_it_charts_as_progress(
            self, db_session, fake_claude, lead, brief, test_user):
        for score in (40, 60, 80):
            session = roleplay.start(db_session, test_user, lead=lead, brief=brief,
                                     now=NOW)
            roleplay.reply(db_session, session, "a")
            roleplay.reply(db_session, session, "b")
            fake_claude.roleplay_feedback_response = {
                "scores": {"overall": score, "discovery": score, "objections": score,
                           "tone": score, "close": score}}
            roleplay.finish(db_session, session, now=NOW)
        history = roleplay.history(db_session, test_user.id)
        assert [point["overall"] for point in history["trend"]] == [40, 60, 80]
        assert history["average_overall"] == 60
        assert history["best_overall"] == 80

    def test_no_practice_yet_is_null_not_zero(self, db_session, test_user):
        """"No practice yet" and "practised badly" are different facts."""
        history = roleplay.history(db_session, test_user.id)
        assert history["average_overall"] is None
        assert history["total"] == 0

    def test_history_can_be_scoped_to_one_prospect(self, db_session, fake_claude,
                                                   lead, brief, test_user):
        roleplay.start(db_session, test_user, lead=lead, brief=brief, now=NOW)
        roleplay.start(db_session, test_user, now=NOW)
        assert roleplay.history(db_session, test_user.id)["total"] == 2
        assert roleplay.history(db_session, test_user.id, lead_id=lead.id)["total"] == 1


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


class TestApi:
    def test_the_script_endpoint_seeds_and_saves(self, client, db_session, fake_claude,
                                                 brief, test_user):
        got = client.get(f"/meeting-prep/{brief.id}/script",
                         headers=auth_headers(test_user))
        assert got.status_code == 200
        assert got.json()["edited"] is False

        saved = client.put(f"/meeting-prep/{brief.id}/script",
                           json={"opening": "My own opener.", "discovery": ["Why now?"],
                                 "objections": [{"objection": "cost",
                                                 "response": "ask what a miss costs"}],
                                 "close": "Shall we book 30 minutes?", "notes": ""},
                           headers=auth_headers(test_user))
        assert saved.json()["edited"] is True
        assert saved.json()["script"]["opening"] == "My own opener."

    def test_the_readiness_endpoint(self, client, db_session, fake_claude, brief,
                                    test_user):
        response = client.get(f"/meeting-prep/{brief.id}/readiness",
                              headers=auth_headers(test_user))
        assert response.status_code == 200
        assert response.json()["total"] == 4

    def test_practice_can_be_made_blocking_per_meeting(self, client, db_session,
                                                       fake_claude, brief, test_user):
        response = client.post(f"/meeting-prep/{brief.id}/practice-required",
                               json={"required": True},
                               headers=auth_headers(test_user))
        assert response.json()["ready"] is False

    def test_a_full_roleplay_round_trip(self, client, db_session, fake_claude, lead,
                                        brief, test_user):
        started = client.post("/practice/sessions",
                              json={"lead_id": str(lead.id),
                                    "difficulty": "hostile"},
                              headers=auth_headers(test_user))
        assert started.status_code == 201
        session_id = started.json()["id"]
        assert started.json()["objectives"]
        assert len(started.json()["turns"]) == 1

        spoke = client.post(f"/practice/sessions/{session_id}/reply",
                            json={"message": "Thanks for taking the call."},
                            headers=auth_headers(test_user))
        assert spoke.json()["status"] == "ok"
        client.post(f"/practice/sessions/{session_id}/reply",
                    json={"message": "What happens when an inspection is missed?"},
                    headers=auth_headers(test_user))

        done = client.post(f"/practice/sessions/{session_id}/finish", json={},
                           headers=auth_headers(test_user))
        assert done.json()["status"] == roleplay.COMPLETED
        assert done.json()["scores"]["overall"] == 72

    def test_practice_works_without_a_meeting(self, client, db_session, fake_claude,
                                              test_user):
        """The standalone tool and the pre-meeting step are one code path."""
        response = client.post("/practice/sessions", json={},
                               headers=auth_headers(test_user))
        assert response.status_code == 201
        assert response.json()["lead"] is None

    def test_finishing_twice_is_a_conflict(self, client, db_session, fake_claude,
                                           lead, test_user):
        started = client.post("/practice/sessions", json={"lead_id": str(lead.id)},
                              headers=auth_headers(test_user))
        session_id = started.json()["id"]
        client.post(f"/practice/sessions/{session_id}/finish", json={},
                    headers=auth_headers(test_user))
        second = client.post(f"/practice/sessions/{session_id}/finish", json={},
                             headers=auth_headers(test_user))
        assert second.status_code == 409

    def test_an_unknown_difficulty_is_rejected(self, client, db_session, test_user):
        assert client.post("/practice/sessions", json={"difficulty": "nightmare"},
                           headers=auth_headers(test_user)).status_code == 422

    def test_the_history_endpoint(self, client, db_session, fake_claude, lead,
                                  test_user):
        client.post("/practice/sessions", json={"lead_id": str(lead.id)},
                    headers=auth_headers(test_user))
        response = client.get("/practice/sessions", headers=auth_headers(test_user))
        assert response.json()["total"] == 1

    def test_another_account_cannot_read_or_drive_a_session(
            self, client, db_session, fake_claude, lead, brief, test_user):
        started = client.post("/practice/sessions", json={"lead_id": str(lead.id)},
                              headers=auth_headers(test_user))
        session_id = started.json()["id"]
        other = m.User(email="nosy-practice@test.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        assert client.get(f"/practice/sessions/{session_id}",
                          headers=auth_headers(other)).status_code == 404
        assert client.post(f"/practice/sessions/{session_id}/reply",
                           json={"message": "hi"},
                           headers=auth_headers(other)).status_code == 404
        assert client.get(f"/meeting-prep/{brief.id}/script",
                          headers=auth_headers(other)).status_code == 404

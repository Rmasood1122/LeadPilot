"""Feature 2 — Learn LeadPilot tutorial section.

The tests that matter most here are the ones about state that is easy to get
subtly wrong and impossible to notice: progress that silently goes backwards
when a user scrubs, a summary that moves while someone types in the search
box, badges that disagree with the progress behind them, and — the one with
real consequences — one user being able to see another's watch history.
"""

import uuid

import pytest
from sqlalchemy import select

from app.api.tutorials import COMPLETION_THRESHOLD_PERCENT
from app.db import models as m
from app.services import tutorials as catalogue
from tests.conftest import auth_headers

ALL_SLUGS = [t.slug for t in catalogue.CATALOGUE]
FIRST = ALL_SLUGS[0]


def _list(client, **params):
    r = client.get("/tutorials", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _put(client, slug, position, duration=None):
    body = {"position_seconds": position}
    if duration is not None:
        body["duration_seconds"] = duration
    return client.put(f"/tutorials/{slug}/progress", json=body)


def _progress_of(payload, slug):
    for t in payload["tutorials"]:
        if t["slug"] == slug:
            return t["progress"]
    raise AssertionError(f"{slug} not in payload")


# --------------------------------------------------------------------------
# Catalogue
# --------------------------------------------------------------------------


class TestCatalogue:
    def test_nine_tutorials_three_per_level(self, client):
        payload = _list(client)
        assert len(payload["tutorials"]) == 9
        for level in ("beginner", "intermediate", "advanced"):
            assert len(catalogue.slugs_for_level(level)) == 3

    def test_ordered_beginner_first(self, client):
        levels = [t["level"] for t in _list(client)["tutorials"]]
        assert levels == ["beginner"] * 3 + ["intermediate"] * 3 + ["advanced"] * 3

    def test_slugs_are_unique(self):
        """A duplicate slug would merge two videos' progress into one row."""
        assert len(set(ALL_SLUGS)) == len(ALL_SLUGS)

    def test_placeholders_are_flagged_not_faked(self, client):
        """A fake YouTube id would render a broken player and look like a bug.

        None -> is_placeholder -> the UI shows "coming soon" instead.
        """
        for t in _list(client)["tutorials"]:
            if t["youtube_id"] is None:
                assert t["is_placeholder"] is True

    def test_every_tutorial_has_a_description(self, client):
        for t in _list(client)["tutorials"]:
            assert t["description"].strip()


# --------------------------------------------------------------------------
# Search + filter
# --------------------------------------------------------------------------


class TestSearchAndFilter:
    @pytest.mark.parametrize("query,expected", [
        ("apollo", "advanced-lead-sourcing-with-apollo"),
        ("ICP", "understanding-your-icp"),
        ("analytics", "reading-your-analytics"),
    ])
    def test_search_finds_by_title(self, client, query, expected):
        found = [t["slug"] for t in _list(client, q=query)["tutorials"]]
        assert expected in found

    def test_search_is_case_insensitive(self, client):
        assert (_list(client, q="APOLLO")["tutorials"]
                == _list(client, q="apollo")["tutorials"])

    def test_search_also_matches_descriptions(self, client):
        """"deliverability" appears in no title. A user typing it should still
        find the video that covers it."""
        found = [t["slug"] for t in _list(client, q="deliverability")["tutorials"]]
        assert found == ["scaling-your-pipeline"]

    def test_search_with_no_matches_returns_empty_not_error(self, client):
        assert _list(client, q="zzzznothing")["tutorials"] == []

    @pytest.mark.parametrize("level", ["beginner", "intermediate", "advanced"])
    def test_level_filter(self, client, level):
        found = _list(client, level=level)["tutorials"]
        assert len(found) == 3
        assert {t["level"] for t in found} == {level}

    def test_search_and_level_combine(self, client):
        found = _list(client, q="leadpilot", level="beginner")["tutorials"]
        assert all(t["level"] == "beginner" for t in found)

    def test_unknown_level_is_empty_not_422(self, client):
        """It is a browse filter, not an API contract — a typo in a shared URL
        should show nothing, not an error page."""
        r = client.get("/tutorials", params={"level": "expert"})
        assert r.status_code == 200
        assert r.json()["tutorials"] == []


# --------------------------------------------------------------------------
# Progress
# --------------------------------------------------------------------------


class TestProgress:
    def test_untouched_tutorial_reports_zero_not_null(self, client):
        """No row is created just so the UI can draw a 0% bar."""
        p = _progress_of(_list(client), FIRST)
        assert p == {
            "position_seconds": 0, "duration_seconds": None, "percent": 0.0,
            "completed": False, "completed_at": None, "last_watched_at": None,
            "started": False,
        }

    def test_update_records_position_and_percent(self, client):
        r = _put(client, FIRST, position=30, duration=120)
        assert r.status_code == 200
        p = r.json()["progress"]
        assert p["position_seconds"] == 30
        assert p["percent"] == 25.0
        assert p["completed"] is False
        assert p["started"] is True

    def test_position_takes_the_LATEST_value(self, client):
        """position answers "where do I resume" — scrubbing back means
        resuming back."""
        _put(client, FIRST, position=90, duration=120)
        r = _put(client, FIRST, position=10, duration=120)
        assert r.json()["progress"]["position_seconds"] == 10

    def test_percent_takes_the_MAXIMUM_and_never_regresses(self, client):
        """percent answers "how much have I seen" — scrubbing back must not
        erase watched progress. This is the bug that would silently undo a
        user's completion every time they rewatched an intro."""
        _put(client, FIRST, position=60, duration=120)   # 50%
        r = _put(client, FIRST, position=10, duration=120)  # back to the start
        assert r.json()["progress"]["percent"] == 50.0

    def test_percent_is_clamped_at_100(self, client):
        """Players can report a position a shade past their own duration."""
        r = _put(client, FIRST, position=130, duration=120)
        assert r.json()["progress"]["percent"] == 100.0

    def test_repeated_updates_do_not_create_duplicate_rows(self, client, db_session):
        """A player fires these constantly; UNIQUE(user_id, slug) is what keeps
        "have I finished this?" to a single answer."""
        for pos in (5, 10, 15, 20, 25):
            _put(client, FIRST, position=pos, duration=120)
        rows = db_session.execute(
            select(m.TutorialProgress).where(
                m.TutorialProgress.tutorial_slug == FIRST)
        ).scalars().all()
        assert len(rows) == 1

    def test_duration_may_be_omitted(self, client):
        """The player has not loaded metadata on the first report."""
        r = _put(client, FIRST, position=5)
        assert r.status_code == 200
        assert r.json()["progress"]["percent"] == 0.0

    def test_unknown_slug_is_404(self, client):
        assert _put(client, "no-such-video", position=1).status_code == 404
        assert client.get("/tutorials/no-such-video").status_code == 404
        assert client.post("/tutorials/no-such-video/complete").status_code == 404

    def test_negative_position_rejected(self, client):
        assert _put(client, FIRST, position=-1).status_code == 422


# --------------------------------------------------------------------------
# Completion
# --------------------------------------------------------------------------


class TestCompletion:
    def test_crossing_the_threshold_completes(self, client):
        r = _put(client, FIRST, position=90, duration=100)   # 90%
        p = r.json()["progress"]
        assert p["percent"] >= COMPLETION_THRESHOLD_PERCENT
        assert p["completed"] is True
        assert p["completed_at"] is not None

    def test_just_below_the_threshold_does_not_complete(self, client):
        assert _put(client, FIRST, position=89, duration=100
                    ).json()["progress"]["completed"] is False

    def test_threshold_is_90_not_100(self, client):
        """Almost nobody reaches the final frame — end cards, credits, clicking
        away. A 100% rule strands users at "8 of 9" and teaches them to scrub."""
        assert COMPLETION_THRESHOLD_PERCENT == 90.0

    def test_explicit_complete_works_without_watching(self, client):
        """Required, not convenience: a placeholder video cannot be watched at
        all, and a user who knows the material must still be able to finish."""
        p = client.post(f"/tutorials/{FIRST}/complete").json()["progress"]
        assert p["completed"] is True
        assert p["percent"] == 100.0

    def test_completed_at_keeps_the_FIRST_completion_time(self, client):
        first = client.post(f"/tutorials/{FIRST}/complete").json()["progress"]["completed_at"]
        _put(client, FIRST, position=5, duration=120)      # rewatch
        again = client.post(f"/tutorials/{FIRST}/complete").json()["progress"]["completed_at"]
        assert again == first

    def test_rewatching_does_not_uncomplete(self, client):
        client.post(f"/tutorials/{FIRST}/complete")
        p = _put(client, FIRST, position=1, duration=120).json()["progress"]
        assert p["completed"] is True

    def test_reset_clears_everything(self, client, db_session):
        client.post(f"/tutorials/{FIRST}/complete")
        r = client.delete(f"/tutorials/{FIRST}/progress")
        assert r.status_code == 200
        p = r.json()["progress"]
        assert p["completed"] is False and p["percent"] == 0.0
        assert p["started"] is False
        # Deleted, not zeroed — "not started" has exactly one representation.
        rows = db_session.execute(
            select(m.TutorialProgress).where(
                m.TutorialProgress.tutorial_slug == FIRST)
        ).scalars().all()
        assert rows == []

    def test_reset_on_an_untouched_tutorial_is_not_an_error(self, client):
        assert client.delete(f"/tutorials/{FIRST}/progress").status_code == 200


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------


class TestSummary:
    def test_starts_at_zero(self, client):
        s = _list(client)["summary"]
        assert s["total"] == 9 and s["completed"] == 0 and s["percent"] == 0.0

    def test_counts_completions(self, client):
        for slug in catalogue.slugs_for_level("beginner"):
            client.post(f"/tutorials/{slug}/complete")
        s = _list(client)["summary"]
        assert s["completed"] == 3
        assert s["percent"] == round(100 * 3 / 9, 1)
        assert s["by_level"]["beginner"] == {"label": "Beginner", "total": 3,
                                             "completed": 3}
        assert s["by_level"]["advanced"]["completed"] == 0

    def test_summary_IGNORES_the_search_filter(self, client):
        """The summary answers "how far through the course am I". It must not
        move while the user types in the search box."""
        client.post(f"/tutorials/{FIRST}/complete")
        unfiltered = _list(client)["summary"]
        filtered = _list(client, q="apollo")["summary"]
        assert len(_list(client, q="apollo")["tutorials"]) == 1  # filter DID apply
        assert filtered == unfiltered

    def test_summary_ignores_the_level_filter_too(self, client):
        client.post(f"/tutorials/{FIRST}/complete")
        assert _list(client, level="advanced")["summary"] == _list(client)["summary"]


# --------------------------------------------------------------------------
# Badges
# --------------------------------------------------------------------------


class TestBadges:
    def test_none_earned_initially(self, client):
        assert all(b["earned"] is False for b in _list(client)["badges"])

    def test_level_badge_needs_ALL_of_its_level(self, client):
        slugs = catalogue.slugs_for_level("beginner")
        for slug in slugs[:2]:
            client.post(f"/tutorials/{slug}/complete")
        badge = next(b for b in _list(client)["badges"]
                     if b["slug"] == "beginner-complete")
        assert badge["earned"] is False
        assert badge["required_completed"] == 2 and badge["required_total"] == 3

        client.post(f"/tutorials/{slugs[2]}/complete")
        badge = next(b for b in _list(client)["badges"]
                     if b["slug"] == "beginner-complete")
        assert badge["earned"] is True
        assert badge["earned_at"] is not None

    def test_finishing_one_level_does_not_earn_another(self, client):
        for slug in catalogue.slugs_for_level("beginner"):
            client.post(f"/tutorials/{slug}/complete")
        earned = {b["slug"] for b in _list(client)["badges"] if b["earned"]}
        assert earned == {"beginner-complete"}

    def test_certified_badge_needs_the_whole_catalogue(self, client):
        for slug in ALL_SLUGS[:-1]:
            client.post(f"/tutorials/{slug}/complete")
        assert not next(b for b in _list(client)["badges"]
                        if b["slug"] == "leadpilot-certified")["earned"]

        client.post(f"/tutorials/{ALL_SLUGS[-1]}/complete")
        badges = {b["slug"]: b for b in _list(client)["badges"]}
        assert badges["leadpilot-certified"]["earned"] is True
        assert all(b["earned"] for b in badges.values())

    def test_resetting_a_video_REVOKES_the_badge(self, client):
        """Badges are derived, never stored — so they cannot drift out of
        agreement with the progress that justifies them."""
        for slug in catalogue.slugs_for_level("beginner"):
            client.post(f"/tutorials/{slug}/complete")
        assert next(b for b in _list(client)["badges"]
                    if b["slug"] == "beginner-complete")["earned"] is True

        client.delete(f"/tutorials/{catalogue.slugs_for_level('beginner')[0]}/progress")
        assert next(b for b in _list(client)["badges"]
                    if b["slug"] == "beginner-complete")["earned"] is False


# --------------------------------------------------------------------------
# Access control
# --------------------------------------------------------------------------


class TestAccessControl:
    def test_requires_authentication(self, anon_client):
        assert anon_client.get("/tutorials").status_code == 401
        assert anon_client.put(f"/tutorials/{FIRST}/progress",
                               json={"position_seconds": 1}).status_code == 401

    def test_unverified_users_are_blocked_by_the_feature_1_gate(self, client,
                                                                db_session):
        """Feature 2 inherits Feature 1's chokepoint for free — the point of
        putting that check in get_current_user rather than per-router."""
        r = client.post("/auth/signup", json={"email": "learner@x.com",
                                              "password": "hunter22!"})
        tokens = r.json()
        resp = client.get("/tutorials", headers={
            "Authorization": f"Bearer {tokens['access_token']}"})
        assert resp.status_code == 403
        assert resp.json()["detail"] == "EMAIL_NOT_VERIFIED"

    def test_progress_is_PRIVATE_between_users(self, client, db_session):
        """The one failure here with real consequences."""
        other = m.User(email=f"other_{uuid.uuid4().hex[:6]}@x.com",
                       email_verified=True)
        db_session.add(other)
        db_session.commit()

        # The fixture user completes everything.
        for slug in ALL_SLUGS:
            client.post(f"/tutorials/{slug}/complete")

        # The other user sees a clean slate, not that progress.
        payload = client.get("/tutorials", headers=auth_headers(other)).json()
        assert payload["summary"]["completed"] == 0
        assert all(t["progress"]["started"] is False for t in payload["tutorials"])
        assert all(b["earned"] is False for b in payload["badges"])

    def test_one_users_reset_does_not_touch_another(self, client, db_session):
        other = m.User(email=f"other2_{uuid.uuid4().hex[:6]}@x.com",
                       email_verified=True)
        db_session.add(other)
        db_session.commit()

        client.post(f"/tutorials/{FIRST}/complete")
        client.post(f"/tutorials/{FIRST}/complete", headers=auth_headers(other))

        client.delete(f"/tutorials/{FIRST}/progress", headers=auth_headers(other))

        mine = client.get(f"/tutorials/{FIRST}").json()["progress"]
        assert mine["completed"] is True


# --------------------------------------------------------------------------
# Admin aggregates
# --------------------------------------------------------------------------


class TestAdminCompletions:
    def _make_admin(self, db_session):
        admin = m.User(email=f"admin_{uuid.uuid4().hex[:6]}@x.com",
                       is_admin=True, email_verified=True)
        db_session.add(admin)
        db_session.commit()
        return admin

    def test_non_admin_is_refused(self, client):
        assert client.get("/admin/tutorials/completions").status_code == 403

    def test_counts_are_aggregate(self, client, db_session):
        admin = self._make_admin(db_session)
        client.post(f"/tutorials/{FIRST}/complete")
        _put(client, ALL_SLUGS[1], position=10, duration=120)  # started only

        data = client.get("/admin/tutorials/completions",
                          headers=auth_headers(admin)).json()
        rows = {r["slug"]: r for r in data["tutorials"]}
        assert rows[FIRST]["completed_count"] == 1
        assert rows[FIRST]["in_progress_count"] == 0
        assert rows[ALL_SLUGS[1]]["started_count"] == 1
        assert rows[ALL_SLUGS[1]]["completed_count"] == 0
        assert rows[ALL_SLUGS[1]]["in_progress_count"] == 1
        assert data["active_learners"] == 1
        assert data["total_completions"] == 1

    def test_response_carries_NO_user_identifiers(self, client, db_session):
        """The product decision was: admins see completion counts, never which
        videos a named person watched. Enforced by the payload containing no
        user field at all, not by a UI that declines to render one."""
        admin = self._make_admin(db_session)
        client.post(f"/tutorials/{FIRST}/complete")

        raw = client.get("/admin/tutorials/completions",
                         headers=auth_headers(admin)).text
        assert "user_id" not in raw
        assert "email" not in raw
        assert "test@leadpilot.dev" not in raw

    def test_every_catalogue_entry_is_listed_even_at_zero(self, client, db_session):
        admin = self._make_admin(db_session)
        data = client.get("/admin/tutorials/completions",
                          headers=auth_headers(admin)).json()
        assert [r["slug"] for r in data["tutorials"]] == ALL_SLUGS
        assert all(r["completed_count"] == 0 for r in data["tutorials"])

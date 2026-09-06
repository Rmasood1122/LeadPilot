"""Engagement Hub, Feature 3 — meetings, notes, transcripts, AI summary.

What is actually load-bearing here:

  * the transcript endpoint is CLOSED without a secret and rejects a bad
    signature — it is the one write path into the verbatim contents of a
    private sales call that does not carry a user's JWT;
  * platform failures do not lose the meeting;
  * the AI summary never overwrites the human's own notes, and regenerating
    does not un-tick action items somebody has already completed;
  * ownership, as everywhere else: 404, never 403.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.db import models as m
from app.services import calendar_service as cal

UTC = timezone.utc
SECRET = "test-transcript-secret"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture()
def lead(db_session, verified_strategy):
    row = m.Lead(strategy_id=verified_strategy.id, source="manual",
                 full_name="Sara Khan", company="Acme Fire",
                 title="Owner", email="sara@acme.test",
                 status=m.LeadStatus.REPLIED)
    db_session.add(row)
    db_session.commit()
    return row


@pytest.fixture()
def booking(db_session, test_user, lead):
    page = m.CalendarBookingPage(user_id=test_user.id, slug="intro",
                                 title="Intro call", duration_minutes=30)
    db_session.add(page)
    db_session.flush()
    start = datetime.now(UTC) + timedelta(days=1)
    row = m.CalendarBooking(
        booking_page_id=page.id, invitee_name="Sara Khan",
        invitee_email="sara@acme.test", start_at=start,
        end_at=start + timedelta(minutes=30),
        status=m.BookingStatus.CONFIRMED, lead_id=lead.id,
        slot_key=cal.slot_key_for(start),
    )
    db_session.add(row)
    db_session.commit()
    return row


@pytest.fixture()
def meeting(client, booking):
    resp = client.post("/meetings", json={
        "booking_id": str(booking.id), "platform": "custom",
        "meeting_url": "https://meet.example.test/abc",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture(autouse=True)
def no_broker(monkeypatch):
    """The summary task is enqueued by /end; the root suite has no broker."""
    from app.workers import calendar_tasks

    queued: list[str] = []
    monkeypatch.setattr(calendar_tasks.generate_meeting_summary, "delay",
                        lambda mid: queued.append(mid), raising=False)
    return queued


def _uid(value) -> uuid.UUID:
    """`db_session.get(Model, id)` needs a real UUID.

    The Uuid column type calls `.hex` on whatever it is handed, so passing the
    string the API returned raises AttributeError from inside SQLAlchemy
    rather than returning None.
    """
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _instant(value: str) -> datetime:
    """Parse a timestamp the API returned, as UTC.

    SQLite has no timezone-aware storage, so a value written as aware comes
    back naive and FastAPI then serialises it without the trailing Z --
    meaning the same field can be "…Z" on the response that wrote it and
    "…" on the next read, in the test suite only. PostgreSQL's timestamptz
    returns aware both times, so this is a harness artefact and not a bug to
    encode in an assertion.
    """
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _sign(body: dict) -> tuple[bytes, str]:
    raw = json.dumps(body).encode()
    digest = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return raw, f"sha256={digest}"


# --------------------------------------------------------------------------
# Creation
# --------------------------------------------------------------------------


class TestCreate:
    def test_a_meeting_inherits_everything_from_its_booking(
        self, client, booking, lead
    ):
        body = client.post("/meetings", json={
            "booking_id": str(booking.id), "platform": "custom",
            "meeting_url": "https://meet.example.test/abc",
        }).json()
        assert body["lead_id"] == str(lead.id)
        assert _instant(body["start_at"]) == booking.start_at
        assert "Sara Khan" in body["title"]
        # Host and invitee are seeded so "who is this call with" is answerable
        # before anybody joins.
        assert {p["role"] for p in body["participants"]} == {"host", "client"}

    def test_the_join_url_is_copied_onto_the_booking(
        self, client, db_session, booking
    ):
        """So the confirmation the invitee already has and any re-send agree."""
        client.post("/meetings", json={
            "booking_id": str(booking.id), "platform": "custom",
            "meeting_url": "https://meet.example.test/abc",
        })
        db_session.refresh(booking)
        assert booking.meeting_link == "https://meet.example.test/abc"

    def test_a_standalone_meeting_needs_its_own_times(self, client):
        """A meeting with no time is not a meeting, and defaulting to `now`
        would put a fictional call on the user's calendar."""
        assert client.post("/meetings", json={"platform": "custom"}
                           ).status_code == 422

        start = datetime.now(UTC) + timedelta(days=2)
        resp = client.post("/meetings", json={
            "platform": "custom", "start_at": start.isoformat(),
            "end_at": (start + timedelta(minutes=45)).isoformat(),
        })
        assert resp.status_code == 201
        assert resp.json()["booking_id"] is None

    def test_a_cancelled_booking_cannot_become_a_meeting(
        self, client, db_session, booking
    ):
        booking.status = m.BookingStatus.CANCELLED
        db_session.commit()
        assert client.post("/meetings", json={
            "booking_id": str(booking.id), "platform": "custom",
        }).status_code == 409

    def test_a_platform_failure_still_creates_the_meeting(
        self, client, monkeypatch, booking
    ):
        """Refusing to record a meeting the user has actually scheduled,
        because Google was unavailable, leaves nowhere to attach their notes
        when the call happens anyway."""
        import app.integrations.google_meet as gm

        def boom(*args, **kwargs):
            raise gm.GoogleCalendarNotAuthorized("scope not granted")

        monkeypatch.setattr(gm, "create_meet_event", boom)

        resp = client.post("/meetings", json={
            "booking_id": str(booking.id), "platform": "google_meet",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["meeting_url"] is None
        assert "scope not granted" in body["platform_error"]

    def test_a_successful_platform_call_stores_the_link_and_event_id(
        self, client, monkeypatch, booking
    ):
        import app.integrations.google_meet as gm

        monkeypatch.setattr(gm, "create_meet_event", lambda *a, **k: {
            "join_url": "https://meet.google.test/xyz",
            "external_event_id": "evt-1",
        })
        body = client.post("/meetings", json={
            "booking_id": str(booking.id), "platform": "google_meet",
        }).json()
        assert body["meeting_url"] == "https://meet.google.test/xyz"
        assert body["platform_error"] is None

    def test_another_users_booking_cannot_be_used(self, client, db_session):
        other = m.User(email="other@leadpilot.dev", email_verified=True)
        db_session.add(other)
        db_session.flush()
        page = m.CalendarBookingPage(user_id=other.id, slug="theirs",
                                     title="Theirs", duration_minutes=30)
        db_session.add(page)
        db_session.flush()
        start = datetime.now(UTC) + timedelta(days=1)
        row = m.CalendarBooking(
            booking_page_id=page.id, invitee_name="Not yours",
            invitee_email="x@x.test", start_at=start,
            end_at=start + timedelta(minutes=30),
            status=m.BookingStatus.CONFIRMED,
        )
        db_session.add(row)
        db_session.commit()

        assert client.post("/meetings", json={
            "booking_id": str(row.id), "platform": "custom",
        }).status_code == 404


# --------------------------------------------------------------------------
# Running a meeting
# --------------------------------------------------------------------------


class TestRunning:
    def test_start_notes_end(self, client, meeting, no_broker):
        mid = meeting["id"]

        started = client.post(f"/meetings/{mid}/start").json()
        assert started["status"] == "in_progress"
        assert started["actual_start_at"] is not None

        notes = client.put(f"/meetings/{mid}/notes",
                           json={"raw_notes": "budget confirmed"}).json()
        assert notes["raw_notes"] == "budget confirmed"

        ended = client.post(f"/meetings/{mid}/end").json()
        assert ended["status"] == "completed"
        assert ended["actual_end_at"] is not None
        assert no_broker == [mid], "the summary must be queued on /end"

    def test_start_is_idempotent(self, client, meeting):
        """A second press comes from a refreshed tab; moving actual_start_at
        would shorten the recorded duration of a call still running."""
        first = client.post(f"/meetings/{meeting['id']}/start").json()
        second = client.post(f"/meetings/{meeting['id']}/start").json()
        assert _instant(first["actual_start_at"]) == _instant(
            second["actual_start_at"]
        )

    def test_a_completed_meeting_cannot_be_restarted(self, client, meeting):
        client.post(f"/meetings/{meeting['id']}/start")
        client.post(f"/meetings/{meeting['id']}/end")
        assert client.post(
            f"/meetings/{meeting['id']}/start"
        ).status_code == 409

    def test_ending_without_starting_records_a_real_duration(
        self, client, meeting
    ):
        """Somebody took notes and closed the tab. Left NULL, the summary
        prompt would be told the call lasted an unknown length of time."""
        ended = client.post(f"/meetings/{meeting['id']}/end").json()
        assert ended["actual_start_at"] is not None
        assert ended["actual_end_at"] is not None

    def test_notes_are_replaced_not_appended(self, client, meeting):
        """The client owns a textarea and sends its contents; appending would
        duplicate everything typed on every 10-second autosave."""
        mid = meeting["id"]
        client.put(f"/meetings/{mid}/notes", json={"raw_notes": "one"})
        body = client.put(f"/meetings/{mid}/notes",
                          json={"raw_notes": "two"}).json()
        assert body["raw_notes"] == "two"

    def test_another_users_meeting_is_404(self, client, db_session, meeting):
        other = m.User(email="other2@leadpilot.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        row = db_session.get(m.Meeting, _uid(meeting["id"]))
        row.host_user_id = other.id
        db_session.commit()

        assert client.get(f"/meetings/{meeting['id']}").status_code == 404
        assert client.post(
            f"/meetings/{meeting['id']}/start"
        ).status_code == 404

    def test_the_list_endpoint_omits_the_transcript(
        self, client, db_session, meeting
    ):
        """A page of rows must not ship a transcript each — that is megabytes
        of response for a screen that renders titles and times."""
        row = db_session.get(m.Meeting, _uid(meeting["id"]))
        row.transcript = "x" * 5000
        db_session.commit()

        listed = client.get("/meetings").json()
        assert listed
        assert "transcript" not in listed[0]
        assert "transcript" in client.get(f"/meetings/{meeting['id']}").json()

    def test_upcoming_uses_end_at_not_start_at(
        self, client, db_session, meeting
    ):
        """A call that started ten minutes ago and runs for an hour is still
        the one you need the Join button for."""
        row = db_session.get(m.Meeting, _uid(meeting["id"]))
        now = datetime.now(UTC)
        row.start_at = now - timedelta(minutes=10)
        row.end_at = now + timedelta(minutes=50)
        db_session.commit()

        assert [x["id"] for x in client.get("/meetings?upcoming=true").json()] \
            == [meeting["id"]]
        assert client.get("/meetings?upcoming=false").json() == []


# --------------------------------------------------------------------------
# Transcript ingestion
# --------------------------------------------------------------------------


class TestTranscript:
    def test_closed_when_no_secret_is_configured(self, client, meeting):
        """503, not open. An unauthenticated write path into the verbatim
        contents of a private call must not appear by default."""
        assert settings.meeting_recording_webhook_secret == ""
        resp = client.post(f"/meetings/{meeting['id']}/transcript",
                           json={"text": "hello"})
        assert resp.status_code == 503

    def test_a_bad_signature_is_rejected(self, client, meeting, monkeypatch):
        monkeypatch.setattr(settings, "meeting_recording_webhook_secret",
                            SECRET)
        raw, _ = _sign({"text": "hello"})
        resp = client.post(
            f"/meetings/{meeting['id']}/transcript", content=raw,
            headers={"X-LeadPilot-Signature": "sha256=deadbeef",
                     "Content-Type": "application/json"},
        )
        assert resp.status_code == 401

    def test_a_missing_signature_is_rejected(self, client, meeting, monkeypatch):
        monkeypatch.setattr(settings, "meeting_recording_webhook_secret",
                            SECRET)
        raw, _ = _sign({"text": "hello"})
        resp = client.post(
            f"/meetings/{meeting['id']}/transcript", content=raw,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 401

    def test_signed_chunks_append_with_speaker_labels(
        self, client, db_session, meeting, monkeypatch
    ):
        monkeypatch.setattr(settings, "meeting_recording_webhook_secret",
                            SECRET)
        for speaker, text in (("Sara", "we're stuck on onboarding"),
                              ("Rehan", "how long has that been true?")):
            raw, signature = _sign({"text": text, "speaker": speaker})
            resp = client.post(
                f"/meetings/{meeting['id']}/transcript", content=raw,
                headers={"X-LeadPilot-Signature": signature,
                         "Content-Type": "application/json"},
            )
            assert resp.status_code == 200, resp.text

        row = db_session.get(m.Meeting, _uid(meeting["id"]))
        assert row.transcript.splitlines() == [
            "Sara: we're stuck on onboarding",
            "Rehan: how long has that been true?",
        ]

    def test_a_recording_url_is_recorded_once(
        self, client, db_session, meeting, monkeypatch
    ):
        monkeypatch.setattr(settings, "meeting_recording_webhook_secret",
                            SECRET)
        for url in ("https://rec.test/1", "https://rec.test/2"):
            raw, signature = _sign({"text": "line", "recording_url": url})
            client.post(f"/meetings/{meeting['id']}/transcript", content=raw,
                        headers={"X-LeadPilot-Signature": signature,
                                 "Content-Type": "application/json"})
        row = db_session.get(m.Meeting, _uid(meeting["id"]))
        assert row.recording_url == "https://rec.test/1"

    def test_an_unknown_meeting_is_404_even_when_signed(
        self, client, monkeypatch
    ):
        """A valid signature says 'a trusted integration', not 'entitled to
        this meeting' — the secret is deployment-wide."""
        import uuid as _uuid

        monkeypatch.setattr(settings, "meeting_recording_webhook_secret",
                            SECRET)
        raw, signature = _sign({"text": "hello"})
        resp = client.post(
            f"/meetings/{_uuid.uuid4()}/transcript", content=raw,
            headers={"X-LeadPilot-Signature": signature,
                     "Content-Type": "application/json"},
        )
        assert resp.status_code == 404

    def test_the_transcript_is_capped(
        self, client, db_session, meeting, monkeypatch
    ):
        """An unbounded Text column filled by a webhook-shaped endpoint is a
        disk-space incident waiting for a stuck streaming client."""
        from app.api.meetings import MAX_TRANSCRIPT_CHARS

        monkeypatch.setattr(settings, "meeting_recording_webhook_secret",
                            SECRET)
        row = db_session.get(m.Meeting, _uid(meeting["id"]))
        row.transcript = "x" * MAX_TRANSCRIPT_CHARS
        db_session.commit()

        raw, signature = _sign({"text": "one more"})
        resp = client.post(f"/meetings/{meeting['id']}/transcript", content=raw,
                           headers={"X-LeadPilot-Signature": signature,
                                    "Content-Type": "application/json"})
        assert resp.status_code == 413


# --------------------------------------------------------------------------
# AI summary and action items
# --------------------------------------------------------------------------


class TestSummary:
    def _with_transcript(self, client, db_session, meeting) -> str:
        row = db_session.get(m.Meeting, _uid(meeting["id"]))
        row.transcript = "Sara: our onboarding takes two weeks."
        row.raw_notes = "budget approved"
        db_session.commit()
        return meeting["id"]

    def test_generate_fills_every_field(
        self, client, db_session, meeting, fake_claude
    ):
        mid = self._with_transcript(client, db_session, meeting)
        body = client.post(f"/meetings/{mid}/generate-summary").json()

        assert body["summary"]
        assert body["key_points"]
        assert body["sentiment"] == "positive"
        assert {i["text"] for i in body["action_items"]} == {
            "Send the pricing sheet", "Introduce us to their ops lead",
        }
        # The prompt must carry the lead context the brief requires.
        prompt = fake_claude.meeting_prompts[-1]
        assert "Sara Khan" in prompt and "Acme Fire" in prompt

    def test_the_summary_never_overwrites_the_users_notes(
        self, client, db_session, meeting
    ):
        mid = self._with_transcript(client, db_session, meeting)
        client.post(f"/meetings/{mid}/generate-summary")
        assert db_session.get(m.Meeting, _uid(mid)).raw_notes == "budget approved"

    def test_nothing_to_summarise_is_422_not_a_model_call(
        self, client, meeting, fake_claude
    ):
        """Calling the model with an empty transcript is how you get a
        confidently hallucinated meeting."""
        before = len(fake_claude.meeting_prompts)
        assert client.post(
            f"/meetings/{meeting['id']}/generate-summary"
        ).status_code == 422
        assert len(fake_claude.meeting_prompts) == before

    def test_a_model_failure_is_502_and_changes_nothing(
        self, client, db_session, meeting, fake_claude
    ):
        mid = self._with_transcript(client, db_session, meeting)
        fake_claude.meeting_summary_response = RuntimeError("api down")
        assert client.post(
            f"/meetings/{mid}/generate-summary"
        ).status_code == 502
        assert db_session.get(m.Meeting, _uid(mid)).summary is None

    def test_regenerating_keeps_ticked_items_ticked(
        self, client, db_session, meeting
    ):
        mid = self._with_transcript(client, db_session, meeting)
        client.post(f"/meetings/{mid}/generate-summary")

        items = client.get(f"/meetings/{mid}/action-items").json()["items"]
        items[0]["done"] = True
        client.put(f"/meetings/{mid}/action-items",
                   json={"action_items": items})

        client.post(f"/meetings/{mid}/generate-summary")
        after = client.get(f"/meetings/{mid}/action-items").json()
        done = {i["text"] for i in after["items"] if i["done"]}
        assert items[0]["text"] in done, (
            "regenerating must not un-tick work somebody has already done"
        )

    def test_a_hand_added_item_survives_a_regeneration(
        self, client, db_session, meeting
    ):
        mid = self._with_transcript(client, db_session, meeting)
        client.post(f"/meetings/{mid}/generate-summary")

        items = client.get(f"/meetings/{mid}/action-items").json()["items"]
        items.append({"text": "Chase the contract", "owner": "us",
                      "due": None, "done": False})
        client.put(f"/meetings/{mid}/action-items",
                   json={"action_items": items})
        client.post(f"/meetings/{mid}/generate-summary")

        texts = {i["text"]
                 for i in client.get(f"/meetings/{mid}/action-items"
                                     ).json()["items"]}
        assert "Chase the contract" in texts

    def test_action_items_are_normalised_on_save(self, client, meeting):
        """A hand-typed item and a generated one must be indistinguishable --
        to the UI, and to the CRM handler that turns them into tasks."""
        body = client.put(
            f"/meetings/{meeting['id']}/action-items",
            json={"action_items": [
                {"text": "  Send deck  ", "owner": "nonsense"},
                {"text": "   "},
            ]},
        ).json()
        assert body["items"] == [
            {"text": "Send deck", "owner": "us", "due": None, "done": False},
        ]

    def test_the_endpoint_rejects_a_non_object_item(self, client, meeting):
        """The API schema is list[dict] on purpose. The MODEL is the thing
        that returns bare strings and nulls (meeting_ai._clean_action_items
        copes with those); a client sending one is a client with a bug, and
        coercing it would hide that."""
        assert client.put(
            f"/meetings/{meeting['id']}/action-items",
            json={"action_items": ["a bare string"]},
        ).status_code == 422

    def test_action_items_endpoint_counts_the_open_ones(
        self, client, db_session, meeting
    ):
        mid = self._with_transcript(client, db_session, meeting)
        client.post(f"/meetings/{mid}/generate-summary")
        body = client.get(f"/meetings/{mid}/action-items").json()
        assert body["open_count"] == len(body["items"])

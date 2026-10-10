"""F04 Reply Copilot -- regression tests for the independent review's findings.

1. a later stop event (meeting booked, disqualified, closed, archived, a newer
   reply) cancels a queued answer; approval refuses those leads; the stop an
   answer may pass is the one its own conversation caused;
2. approve / copy / discard are atomic: a second, stale decision is 409 and
   never creates a second message;
3. the link guard catches bare domains and {x} / <x> placeholders;
4. opt-out / meeting-time checks read only the prospect's NEW text, never the
   quoted thread or our own footer; "stop by" is not an opt-out;
5. a blank subject on approve falls back to the drafted "Re: ..." subject;
6. the reply's inbox "handled" marker follows what happened to the answer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from app.db import models as m
from app.integrations.outreach_base import SendResult
from app.services import reply_copilot, system_settings
from app.workers import outreach_tasks, reply_tasks

from .test_reply_copilot import BOOKING, _build, _draft, _row

UTC = timezone.utc


@pytest.fixture()
def flag_on(db_session):
    system_settings.set(db_session, "reply_copilot_enabled", True)


@pytest.fixture(autouse=True)
def sends(monkeypatch):
    queued: list[str] = []
    monkeypatch.setattr(reply_tasks, "enqueue_send",
                        lambda message_id: queued.append(str(message_id)) or True)
    return queued


@pytest.fixture()
def world(db_session, test_user):
    return _build(db_session, test_user)


@pytest.fixture()
def channel(monkeypatch):
    sent: list = []

    class _Channel:
        def send(self, outbound):
            sent.append(outbound)
            return SendResult(ok=True, provider_message_id="pm-1", thread_ref="th-1")

    monkeypatch.setattr(outreach_tasks, "_get_channel", lambda session, account: _Channel())
    from app.services import sequence_engine as engine

    monkeypatch.setattr(engine, "in_send_window", lambda dt, tz, window=None: True)
    return sent


@pytest.fixture()
def gmail(db_session, test_user):
    from app.services import crypto

    row = m.GmailAccount(
        user_id=test_user.id, email_address="me@leadpilot.dev",
        token_ciphertext=crypto.encrypt_json({"access_token": "a", "refresh_token": "r"}),
        token_expires_at=datetime.now(UTC) + timedelta(hours=1))
    db_session.add(row)
    db_session.commit()
    row.created_at = datetime.now(UTC) - timedelta(days=365)
    db_session.commit()
    return row


def _approved(db, world, user, **kw) -> m.Message:
    _draft(db, world["reply"])
    draft = _row(db, world["reply"])
    reply_copilot.approve(db, draft, actor=user, **kw)
    return db.get(m.Message, draft.message_id)


def _later_reply(db, world, body, classification="question", minutes=5):
    row = m.InboundReply(lead_id=world["lead"].id, channel="email",
                         from_address="sara@acme.test", subject="Re: Quick question",
                         body=body, classification=classification,
                         received_at=datetime.now(UTC) + timedelta(minutes=minutes))
    db.add(row)
    db.commit()
    return row


# --------------------------------------------------------------------------
# 1. Later stop events
# --------------------------------------------------------------------------


class TestLaterStopEvents:
    @pytest.mark.parametrize("status", [
        m.LeadStatus.MEETING_BOOKED, m.LeadStatus.DISQUALIFIED, m.LeadStatus.CLOSED_LOST,
        m.LeadStatus.CLOSED_WON, m.LeadStatus.PROPOSAL_SENT, m.LeadStatus.OPPORTUNITY,
        m.LeadStatus.DROPPED])
    def test_a_later_status_change_cancels_a_queued_answer(
            self, db_session, world, test_user, fake_claude, flag_on, channel, gmail, status):
        msg = _approved(db_session, world, test_user)
        # What webhooks.py / crm_sync / meeting_followup do: the status moves,
        # and the ALREADY-stopped enrollment is not re-stopped.
        world["lead"].status = status
        db_session.commit()
        assert reply_tasks.send_reply_draft_impl(db_session, msg.id) == "cancelled_lead_status"
        assert channel == []
        db_session.refresh(msg)
        assert msg.status is m.MessageStatus.CANCELLED and status.value in msg.error

    def test_an_archived_lead_is_not_answered(self, db_session, world, test_user, fake_claude,
                                              flag_on, channel, gmail):
        msg = _approved(db_session, world, test_user)
        world["lead"].engagement_state = "archived"
        db_session.commit()
        assert reply_tasks.send_reply_draft_impl(db_session, msg.id) == "cancelled_lead_status"
        assert channel == []

    @pytest.mark.parametrize("status", [m.LeadStatus.MEETING_BOOKED,
                                        m.LeadStatus.DISQUALIFIED])
    def test_approval_refuses_a_lead_that_moved_on(self, db_session, world, test_user,
                                                   fake_claude, flag_on, sends, status):
        _draft(db_session, world["reply"])
        draft = _row(db_session, world["reply"])
        world["lead"].status = status
        db_session.commit()
        with pytest.raises(reply_copilot.CopilotError) as err:
            reply_copilot.approve(db_session, draft, actor=test_user)
        assert err.value.status == 409 and status.value in err.value.detail
        assert sends == [] and draft.status == "pending"

    def test_a_newer_reply_cancels_the_answer_to_the_older_one(
            self, db_session, world, test_user, fake_claude, flag_on, channel, gmail):
        msg = _approved(db_session, world, test_user)
        _later_reply(db_session, world, "Also - does it integrate with HubSpot?")
        assert reply_tasks.send_reply_draft_impl(db_session, msg.id) == "cancelled_newer_reply"
        assert channel == []

    def test_a_stop_from_a_different_reply_class_is_not_this_conversation(
            self, db_session, world, test_user, fake_claude, flag_on, channel, gmail):
        msg = _approved(db_session, world, test_user)
        world["enrollment"].stop_reason = "replied_objection"   # no objection reply exists
        db_session.commit()
        assert reply_tasks.send_reply_draft_impl(db_session, msg.id) == "cancelled_stopped"
        assert channel == []

    def test_a_stop_from_before_the_reply_is_not_this_conversation(
            self, db_session, world, test_user, fake_claude, flag_on, channel, gmail):
        msg = _approved(db_session, world, test_user)
        world["enrollment"].stopped_at = datetime.now(UTC) - timedelta(days=3)
        db_session.commit()
        assert reply_tasks.send_reply_draft_impl(db_session, msg.id) == "cancelled_stopped"
        assert channel == []

    def test_a_stop_without_a_time_cannot_be_attributed(
            self, db_session, world, test_user, fake_claude, flag_on, channel, gmail):
        msg = _approved(db_session, world, test_user)
        world["enrollment"].stopped_at = None
        db_session.commit()
        assert reply_tasks.send_reply_draft_impl(db_session, msg.id) == "cancelled_stopped"

    def test_answering_the_second_reply_of_a_two_reply_conversation(
            self, db_session, world, test_user, fake_claude, flag_on, channel, gmail):
        """The first reply stopped the sequence; the second is the one answered."""
        second = _later_reply(db_session, world, "And what does it cost?", minutes=1)
        _draft(db_session, second)
        draft = _row(db_session, second)
        reply_copilot.approve(db_session, draft, actor=test_user)
        assert reply_tasks.send_reply_draft_impl(db_session, draft.message_id) == "sent"
        assert len(channel) == 1


# --------------------------------------------------------------------------
# 2. Atomic decisions
# --------------------------------------------------------------------------


def _second_session(db_session):
    return sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)()


class TestAtomicDecisions:
    def test_a_stale_second_approval_is_refused(self, db_session, world, test_user,
                                                fake_claude, flag_on, sends):
        _draft(db_session, world["reply"])
        draft = _row(db_session, world["reply"])
        other = _second_session(db_session)
        try:
            stale = other.get(m.ReplyDraft, draft.id)
            stale_user = other.get(m.User, test_user.id)
            assert stale.status == "pending"
            reply_copilot.approve(db_session, draft, actor=test_user)
            with pytest.raises(reply_copilot.CopilotError) as err:
                reply_copilot.approve(other, stale, actor=stale_user)
            assert err.value.status == 409
        finally:
            other.close()
        assert db_session.query(m.Message).filter_by(origin="reply_copilot").count() == 1
        assert len(sends) == 1

    def test_a_stale_discard_cannot_undo_an_approval(self, db_session, world, test_user,
                                                     fake_claude, flag_on):
        _draft(db_session, world["reply"])
        draft = _row(db_session, world["reply"])
        other = _second_session(db_session)
        try:
            stale = other.get(m.ReplyDraft, draft.id)
            stale_user = other.get(m.User, test_user.id)
            reply_copilot.approve(db_session, draft, actor=test_user)
            with pytest.raises(reply_copilot.CopilotError):
                reply_copilot.discard(other, stale, actor=stale_user)
        finally:
            other.close()
        db_session.expire_all()
        assert _row(db_session, world["reply"]).status == "approved"

    def test_a_stale_second_copy_is_refused(self, db_session, test_user, fake_claude,
                                            flag_on):
        w = _build(db_session, test_user, channel="linkedin")
        _draft(db_session, w["reply"])
        draft = _row(db_session, w["reply"])
        other = _second_session(db_session)
        try:
            stale = other.get(m.ReplyDraft, draft.id)
            stale_user = other.get(m.User, test_user.id)
            reply_copilot.copy(db_session, draft, actor=test_user)
            with pytest.raises(reply_copilot.CopilotError):
                reply_copilot.copy(other, stale, actor=stale_user, body="Different words")
        finally:
            other.close()
        db_session.expire_all()
        row = _row(db_session, w["reply"])
        assert row.status == "copied" and row.edited is False

    def test_auto_send_racing_a_person_sends_once(self, db_session, test_user, fake_claude,
                                                  flag_on, sends):
        system_settings.set(db_session, "reply_copilot_auto_send_allowed", True)
        reply_copilot.set_auto_send(db_session, test_user.id, True)
        fake_claude.reply_copilot_response = {
            "body": f"Here is my calendar: {BOOKING}", "meeting_time_request": True}
        w = _build(db_session, test_user, reply_body="Send me a few times for next week.")
        assert _draft(db_session, w["reply"])["auto"] == "queued"
        draft = _row(db_session, w["reply"])
        # A person's view still shows it pending: a stale, not a dirty, value.
        from sqlalchemy.orm.attributes import set_committed_value

        set_committed_value(draft, "status", "pending")
        with pytest.raises(reply_copilot.CopilotError):
            reply_copilot.approve(db_session, draft, actor=test_user)
        assert db_session.query(m.Message).filter_by(origin="reply_copilot").count() == 1
        assert len(sends) == 1


# --------------------------------------------------------------------------
# 3. Link and placeholder guard
# --------------------------------------------------------------------------


def _problems(body, own=frozenset({"leadpilot.dev"})):
    return reply_copilot.draft_problems(body, allowed_urls={BOOKING}, forbidden=[],
                                        own_domains=set(own))


class TestLinkGuard:
    @pytest.mark.parametrize("body", [
        "Please verify your account at acme-pay.io/verify today.",
        "Details: secure-login.co",
        "See www.other.example for more.",
        "Book here instead: calendly.com/someone-else",
        "Go to https://evil.example/x",
    ])
    def test_foreign_links_are_caught(self, body):
        assert "it contains a link that is not the booking link" in _problems(body)

    @pytest.mark.parametrize("body", [
        f"Pick a slot: {BOOKING}",
        "Pick a slot: calendly.com/founder/intro.",
        "Our write-up is at leadpilot.dev/case-study and app.leadpilot.dev.",
        "E.g. teams see 3.5x faster scheduling, i.e. fewer misses with Node.js.",
        "Write to sara@acme.io any time.",
        "Version 2.0 shipped. Thanks.Let's talk.",
    ])
    def test_allowed_or_non_links_pass(self, body):
        assert _problems(body) == []

    @pytest.mark.parametrize("body", [
        "Hi {first_name}, thanks.", "Hi <name>, thanks.", "Hi [Name], thanks.",
        "Hi {{first_name}}, thanks.", "Hi < company >, thanks."])
    def test_placeholders_are_caught(self, body):
        assert "it contains a placeholder in brackets" in _problems(body)

    def test_a_bare_domain_draft_is_repaired_then_refused(self, db_session, world,
                                                          fake_claude, flag_on):
        fake_claude.reply_copilot_response = {
            "body": "Quick step first: confirm at acme-pay.io/verify and we can talk.",
            "meeting_time_request": False}
        assert _draft(db_session, world["reply"])["reason"] == "unusable_output"
        assert len(fake_claude.reply_copilot_prompts) == 2

    def test_the_senders_own_domain_is_allowed_in_a_draft(self, db_session, world,
                                                          fake_claude, flag_on, gmail):
        fake_claude.reply_copilot_response = {
            "body": "There is a short write-up at leadpilot.dev/how-it-works.",
            "meeting_time_request": False}
        assert _draft(db_session, world["reply"])["status"] == "drafted"


# --------------------------------------------------------------------------
# 4. Quoted text
# --------------------------------------------------------------------------

FOOTER = ("--\nLeadPilot User, 123 Main St, City, Country\n"
          "Don't want these emails? Unsubscribe instantly: "
          "https://api.leadpilot.dev/unsubscribe/abc123")

GMAIL_QUOTED = (
    "Sounds interesting - how does pricing work for a team of 12?\n\n"
    "On Mon, Oct 6, 2026 at 10:02 AM Rehan Masood <me@leadpilot.dev> wrote:\n"
    "> Hi Sara, saw your post about inspection backlogs.\n> \n"
    + "\n".join("> " + line for line in FOOTER.split("\n")))

GMAIL_WRAPPED_UNQUOTED = (
    "Interested - tell me more.\n\n"
    "On Mon, Oct 6, 2026 at 10:02 AM Rehan Masood <\n"
    "me@leadpilot.dev> wrote:\n\n"
    "Hi Sara, saw your post about inspection backlogs.\n\n" + FOOTER)

OUTLOOK_QUOTED = (
    "Yes, let's talk next week.\n\n"
    "________________________________\n"
    "From: Rehan Masood <me@leadpilot.dev>\n"
    "Sent: Monday, October 6, 2026 10:02 AM\n"
    "To: Sara Khan <sara@acme.test>\n"
    "Subject: Quick question\n\n"
    "Hi Sara, saw your post. Please stop by our booth if you are at the expo.\n\n"
    + FOOTER)

OUTLOOK_ORIGINAL_MESSAGE = (
    "Could you send me a few times for Thursday?\r\n\r\n"
    "-----Original Message-----\r\n"
    "From: Rehan Masood [mailto:me@leadpilot.dev]\r\n"
    "Sent: Monday, October 6, 2026 10:02 AM\r\n"
    "Subject: Quick question\r\n\r\n" + FOOTER.replace("\n", "\r\n"))


class TestQuotedText:
    @pytest.mark.parametrize("body", [GMAIL_QUOTED, GMAIL_WRAPPED_UNQUOTED, OUTLOOK_QUOTED,
                                      OUTLOOK_ORIGINAL_MESSAGE])
    def test_our_quoted_footer_does_not_block_a_draft(self, db_session, test_user,
                                                      fake_claude, flag_on, body):
        w = _build(db_session, test_user, reply_body=body)
        assert _draft(db_session, w["reply"])["status"] == "drafted"
        prompt = fake_claude.reply_copilot_prompts[0]
        assert "Unsubscribe instantly" not in prompt     # only their new words go in

    def test_new_text_cuts_at_each_quote_header(self):
        assert reply_copilot.new_text(GMAIL_QUOTED).startswith("Sounds interesting")
        assert "wrote" not in reply_copilot.new_text(GMAIL_QUOTED)
        assert reply_copilot.new_text(GMAIL_WRAPPED_UNQUOTED) == "Interested - tell me more."
        assert reply_copilot.new_text(OUTLOOK_QUOTED) == "Yes, let's talk next week."
        assert reply_copilot.new_text(OUTLOOK_ORIGINAL_MESSAGE) == \
            "Could you send me a few times for Thursday?"

    def test_stop_by_is_not_an_opt_out(self, db_session, test_user, fake_claude, flag_on):
        w = _build(db_session, test_user,
                   reply_body="I'll stop by your booth at the expo - can we talk then?")
        assert _draft(db_session, w["reply"])["status"] == "drafted"

    @pytest.mark.parametrize("body", [
        "Please stop emailing me.\n\n" + GMAIL_QUOTED.split("\n\n", 1)[1],
        "please stop", "STOP", "Stop.\n\nOn Mon, Oct 6, 2026 Rehan wrote:\n> hi",
        "Stop contacting us.", "Unsubscribe\n\n" + OUTLOOK_QUOTED.split("\n\n", 1)[1],
    ])
    def test_an_opt_out_above_the_quote_still_blocks(self, db_session, test_user,
                                                     fake_claude, flag_on, body):
        w = _build(db_session, test_user, reply_body=body)
        assert _draft(db_session, w["reply"])["reason"] == "opt_out_language"
        assert fake_claude.reply_copilot_prompts == []

    def test_meeting_time_is_read_from_the_new_text_only(self):
        quoted_ask = ("Thanks, not right now.\n\nOn Mon, Oct 6, 2026 Rehan wrote:\n"
                      "> Could you send me a few times that work?")
        assert reply_copilot.meeting_time_language(quoted_ask) is False
        assert reply_copilot.meeting_time_language(OUTLOOK_ORIGINAL_MESSAGE) is True

    def test_send_time_hold_reads_new_text_too(self, db_session, world, test_user,
                                               fake_claude, flag_on, channel, gmail):
        """A later thank-you that quotes our footer is a newer reply, not a decline."""
        msg = _approved(db_session, world, test_user)
        _later_reply(db_session, world, "Great, thanks!\n\n" + GMAIL_QUOTED.split("\n\n", 1)[1],
                     classification="interested")
        assert reply_tasks.send_reply_draft_impl(db_session, msg.id) == "cancelled_newer_reply"


# --------------------------------------------------------------------------
# 5. Blank subject
# --------------------------------------------------------------------------


class TestBlankSubject:
    @pytest.mark.parametrize("subject", ["", "   ", "\n\t"])
    def test_blank_subject_falls_back_to_the_drafted_one(self, db_session, world, test_user,
                                                         fake_claude, flag_on, channel, gmail,
                                                         subject):
        msg = _approved(db_session, world, test_user, subject=subject)
        draft = _row(db_session, world["reply"])
        assert draft.final_subject == "Re: Quick question"
        assert draft.edited is False
        assert reply_tasks.send_reply_draft_impl(db_session, msg.id) == "sent"
        assert channel[0].subject == "Re: Quick question"

    def test_blank_subject_over_the_api(self, client, db_session, world, fake_claude,
                                        flag_on):
        draft_id = _draft(db_session, world["reply"])["draft_id"]
        r = client.post(f"/reply-copilot/drafts/{draft_id}/approve", json={"subject": "  "})
        assert r.status_code == 200 and r.json()["final_subject"] == "Re: Quick question"


# --------------------------------------------------------------------------
# 6. The inbox "handled" marker follows the send
# --------------------------------------------------------------------------


class TestHandledMarker:
    def test_a_blocked_send_puts_the_reply_back_in_needs_reply(
            self, db_session, world, test_user, fake_claude, flag_on, channel, gmail):
        msg = _approved(db_session, world, test_user)
        db_session.refresh(world["reply"])
        assert world["reply"].handled_at is not None          # approved: dealt with
        db_session.add(m.SuppressionEntry(email="sara@acme.test", reason="unsubscribed"))
        db_session.commit()
        assert reply_tasks.send_reply_draft_impl(db_session, msg.id) == "cancelled_suppressed"
        db_session.refresh(world["reply"])
        assert world["reply"].handled_at is None

    def test_a_held_send_puts_the_reply_back_in_needs_reply(
            self, db_session, world, test_user, fake_claude, flag_on, channel, gmail,
            monkeypatch):
        from app.services import send_review

        monkeypatch.setattr(send_review, "gate",
                            lambda *a, **k: {"action": "hold", "review": None})
        msg = _approved(db_session, world, test_user)
        assert reply_tasks.send_reply_draft_impl(db_session, msg.id) == "held_for_review"
        db_session.refresh(world["reply"])
        assert world["reply"].handled_at is None

    def test_a_deferred_send_stays_handled(self, db_session, world, test_user, fake_claude,
                                           flag_on, gmail, monkeypatch):
        from app.services import sequence_engine as engine

        monkeypatch.setattr(engine, "in_send_window", lambda dt, tz, window=None: False)
        msg = _approved(db_session, world, test_user)
        assert reply_tasks.send_reply_draft_impl(db_session, msg.id) == "deferred_window"
        db_session.refresh(world["reply"])
        assert world["reply"].handled_at is not None

    def test_a_sent_answer_is_handled(self, db_session, world, test_user, fake_claude,
                                      flag_on, channel, gmail):
        msg = _approved(db_session, world, test_user)
        world["reply"].handled_at = None        # e.g. it was put back meanwhile
        db_session.commit()
        assert reply_tasks.send_reply_draft_impl(db_session, msg.id) == "sent"
        db_session.refresh(world["reply"])
        assert world["reply"].handled_at is not None

    def test_the_dispatcher_path_keeps_the_marker_true(self, db_session, world, test_user,
                                                       fake_claude, flag_on, channel, gmail,
                                                       monkeypatch):
        """The beat dispatcher (broker down, or after a send-review approval)
        sends through outreach_tasks.send_message, not send_reply_draft."""
        msg = _approved(db_session, world, test_user)
        db_session.add(m.SuppressionEntry(email="sara@acme.test", reason="unsubscribed"))
        db_session.commit()
        monkeypatch.setattr(outreach_tasks, "SessionLocal", lambda: db_session)
        monkeypatch.setattr(db_session, "close", lambda: None)
        assert outreach_tasks.send_message.run(str(msg.id)) == "cancelled_suppressed"
        db_session.refresh(world["reply"])
        assert world["reply"].handled_at is None
        assert _row(db_session, world["reply"]).send_result == "cancelled_suppressed"

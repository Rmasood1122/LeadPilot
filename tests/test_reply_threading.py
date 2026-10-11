"""gaps-sweep-2 #6: a Reply Copilot answer threads by In-Reply-To/References.

Gmail's threadId keeps the answer in the thread only in the SENDER's mailbox;
the prospect's client threads by the reply's Message-ID (RFC 5322 3.6.4).
Kept out of tests/test_reply_copilot.py, which is a sealed compliance file
(evals/compliance_testset.yaml); its world/channel/gmail/flag_on fixtures and
its autouse `sends` recorder are reused from there.
"""

from __future__ import annotations

from app.workers import reply_tasks
from tests.test_reply_copilot import (  # noqa: F401 -- fixtures
    _approved,
    channel,
    flag_on,
    gmail,
    sends,
    world,
)


class TestAnswerThreading:
    def test_an_answer_threads_by_in_reply_to_and_references(
            self, db_session, world, test_user, fake_claude, flag_on, channel, gmail):
        world["reply"].rfc_message_id = "<CAB+reply-1@mail.gmail.com>"
        world["reply"].rfc_references = "<step1@leadpilot.dev> <step2@leadpilot.dev>"
        db_session.commit()
        msg = _approved(db_session, world, test_user)
        assert reply_tasks.send_reply_draft_impl(db_session, msg.id) == "sent"
        headers = channel[0].headers
        assert headers["In-Reply-To"] == "<CAB+reply-1@mail.gmail.com>"
        assert headers["References"] == ("<step1@leadpilot.dev> <step2@leadpilot.dev> "
                                          "<CAB+reply-1@mail.gmail.com>")
        assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        assert channel[0].thread_ref == "th-1"
        # And the bytes the Gmail adapter would transmit carry them.
        from app.integrations.gmail import build_mime

        mime = build_mime("me@leadpilot.dev", channel[0])
        assert mime["In-Reply-To"] == "<CAB+reply-1@mail.gmail.com>"

    def test_control_a_reply_stored_before_0086_sends_without_them(
            self, db_session, world, test_user, fake_claude, flag_on, channel, gmail):
        msg = _approved(db_session, world, test_user)
        assert reply_tasks.send_reply_draft_impl(db_session, msg.id) == "sent"
        assert "In-Reply-To" not in channel[0].headers
        assert "References" not in channel[0].headers
        assert channel[0].thread_ref == "th-1"


class TestClosedLeadAnswers:
    def test_an_answer_to_a_closed_won_lead_is_not_sent(
            self, db_session, world, test_user, fake_claude, flag_on, channel, gmail):
        """Reviewer probe 2, ported (review L1): a closed lead cannot be
        answered through Reply Copilot -- send_time_hold cancels it. The
        comments that said otherwise were corrected."""
        from app.db import models as m
        from app.services import sequence_engine

        msg = _approved(db_session, world, test_user)
        lead = db_session.get(m.Lead, msg.lead_id)
        lead.status = m.LeadStatus.CLOSED_WON
        db_session.commit()
        sequence_engine.stop_for_status(db_session, lead)
        assert reply_tasks.send_reply_draft_impl(db_session, msg.id) == "cancelled_lead_status"
        assert channel == []

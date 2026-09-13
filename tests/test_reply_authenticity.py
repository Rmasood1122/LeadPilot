"""Feature A3 — real-time reply-authenticity scoring.

Unit level: each kind (genuine, out-of-office, auto-responder, bot, bounce) is
told apart, with scores and explainable signals. Real time: the email router
scores in the same commit it stores the reply, header evidence from Gmail is
used, and the chat channels score too. API: the reply inbox is owner-scoped,
filterable by kind and sortable by buyer intent.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db import models as m
from app.integrations.outreach_base import InboundMessage
from app.services import reply_authenticity as ra
from tests.conftest import auth_headers


def _score(body, *, subject=None, sender="sara@acme.com", classification="question", **kw):
    return ra.score(from_address=sender, subject=subject, body=body,
                    classification=classification, **kw)


class TestKinds:
    def test_a_real_buyer(self):
        result = _score("Hi — interested. What does pricing look like, and could we talk "
                        "Thursday?", classification="interested")
        assert result.kind == ra.GENUINE
        assert result.authenticity_score == 1.0
        assert result.buyer_intent_score >= 0.9
        assert result.confidence >= 0.8
        assert {"intent:pricing", "intent:meeting", "intent:question"} <= set(result.signals)

    def test_a_polite_no_is_genuine_with_low_intent(self):
        result = _score("Thanks, but we are not looking at this right now.",
                        classification="not_interested")
        assert result.kind == ra.GENUINE and result.buyer_intent_score < 0.15

    def test_out_of_office(self):
        result = _score("I am currently out of the office with limited access to email. "
                        "I will be back on Monday.", subject="Automatic reply: Quick question",
                        classification="out_of_office")
        assert result.kind == ra.OUT_OF_OFFICE
        assert result.buyer_intent_score == 0.0
        assert result.confidence >= 0.9

    def test_out_of_office_is_caught_even_when_the_classifier_missed_it(self):
        result = _score("I'm on annual leave until the 20th. For urgent matters please "
                        "contact Ali in my absence.", classification="question")
        assert result.kind == ra.OUT_OF_OFFICE

    def test_an_auto_acknowledgement(self):
        result = _score("Thank you for contacting us. We have received your message and one "
                        "of our team will get back to you shortly.", classification="question")
        assert result.kind == ra.AUTO_RESPONDER
        assert result.authenticity_score < 0.4

    def test_a_no_reply_bot(self):
        result = _score("Your request has been received. Ticket #44120.",
                        sender="no-reply@helpdesk.acme.com")
        assert result.kind == ra.BOT and result.buyer_intent_score == 0.0

    def test_a_bounce(self):
        result = _score("Delivery has failed to these recipients: address not found.",
                        sender="mailer-daemon@googlemail.com", classification="bounce")
        assert result.kind == ra.BOUNCE

    def test_rfc3834_headers_are_decisive(self):
        result = _score("Thanks for your note.", headers={"Auto-Submitted": "auto-replied"})
        assert result.kind == ra.AUTO_RESPONDER
        assert "header:auto-submitted" in result.signals
        clean = _score("Thanks for your note.", headers={"Auto-Submitted": "no"})
        assert clean.kind == ra.GENUINE

    def test_a_reply_seconds_after_send_counts_against_authenticity(self):
        sent = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
        fast = _score("Thanks for your message, we will respond soon.",
                      sent_at=sent, received_at=sent + timedelta(seconds=8))
        slow = _score("Thanks for your message, we will respond soon.",
                      sent_at=sent, received_at=sent + timedelta(hours=3))
        assert fast.authenticity_score < slow.authenticity_score
        assert any(s.startswith("timing:") for s in fast.signals)

    def test_one_weak_phrase_alone_does_not_condemn_a_human(self):
        result = _score("Thank you for reaching out to us — yes, happy to chat next week.",
                        classification="interested")
        assert result.kind == ra.GENUINE

    def test_headers_from_provider_payloads(self):
        assert ra.headers_from_raw({"headers": {"Precedence": "bulk"}}) == {"Precedence": "bulk"}
        gmail = {"payload": {"headers": [{"name": "Auto-Submitted", "value": "auto-replied"}]}}
        assert ra.headers_from_raw(gmail) == {"Auto-Submitted": "auto-replied"}
        assert ra.headers_from_raw(None) == {} and ra.headers_from_raw({"x": 1}) == {}


def _inbound(body, *, sender="lead0@co0.com", subject="Re: hello", raw=None):
    return InboundMessage(provider_message_id=f"g-{abs(hash(body))}", thread_ref=None,
                          from_address=sender, to_address="sender@leadpilot.dev",
                          subject=subject, body=body, raw=raw or {})


class TestRealTime:
    def test_the_email_router_scores_in_the_same_commit(self, db_session, enrolled,
                                                        gmail_account, fake_claude):
        from app.workers import outreach_tasks

        fake_claude.default_reply_class = "interested"
        outreach_tasks.route_inbound_impl(
            db_session, _inbound("Interested — can we book a call Thursday?"), gmail_account)
        reply = db_session.execute(select(m.InboundReply)).scalar_one()
        assert reply.authenticity_kind == "genuine"
        assert reply.buyer_intent_score >= 0.85
        assert reply.authenticity_scored_at is not None

    def test_gmail_auto_reply_headers_reach_the_scorer(self, db_session, enrolled,
                                                       gmail_account, fake_claude):
        from app.workers import outreach_tasks

        fake_claude.default_reply_class = "question"
        outreach_tasks.route_inbound_impl(
            db_session,
            _inbound("Thanks for your email.", raw={"headers": {"auto-submitted": "auto-replied"}}),
            gmail_account)
        reply = db_session.execute(select(m.InboundReply)).scalar_one()
        assert reply.authenticity_kind == "auto_responder"

    def test_gmail_parser_keeps_only_auto_reply_headers(self):
        import base64

        from app.integrations.gmail import GmailChannel

        data = {"id": "1", "threadId": "t", "labelIds": ["INBOX"], "payload": {
            "mimeType": "text/plain",
            "headers": [{"name": "From", "value": "Sara <sara@acme.com>"},
                        {"name": "Subject", "value": "Out of office"},
                        {"name": "Auto-Submitted", "value": "auto-replied"},
                        {"name": "X-Secret", "value": "nope"}],
            "body": {"data": base64.urlsafe_b64encode(b"Away").decode()}}}
        parsed = GmailChannel._parse_inbound(data)
        assert parsed.raw == {"labelIds": ["INBOX"],
                              "headers": {"auto-submitted": "auto-replied"}}

    def test_a_scoring_failure_never_breaks_routing(self, db_session, enrolled, gmail_account,
                                                    fake_claude, monkeypatch):
        from app.workers import outreach_tasks

        def _boom(**kwargs):
            raise RuntimeError("scorer exploded")

        monkeypatch.setattr(ra, "score", _boom)
        fake_claude.default_reply_class = "interested"
        result = outreach_tasks.route_inbound_impl(db_session, _inbound("Yes please"),
                                                   gmail_account)
        assert result == "interested"
        assert db_session.execute(select(m.InboundReply)).scalar_one().authenticity_kind is None

    def test_whatsapp_replies_are_scored(self, db_session, wa_lead, fake_claude):
        from app.workers import outreach_tasks

        fake_claude.default_reply_class = "out_of_office"
        reply = m.InboundReply(lead_id=wa_lead.id, channel="whatsapp",
                               from_address=wa_lead.phone,
                               body="I am on vacation until next week.",
                               received_at=datetime.now(timezone.utc))
        db_session.add(reply)
        db_session.commit()
        outreach_tasks.route_whatsapp_inbound_impl(db_session, wa_lead, reply)
        db_session.refresh(reply)
        assert reply.authenticity_kind == "out_of_office"


class TestInboxApi:
    @pytest.fixture()
    def replies(self, db_session, verified_leads):
        rows = []
        for lead, body, cls in (
            (verified_leads[0], "Interested, what does pricing look like?", "interested"),
            (verified_leads[1], "I am out of the office until Monday.", "out_of_office"),
            (verified_leads[2], "Thanks, maybe later.", "not_interested"),
        ):
            reply = m.InboundReply(lead_id=lead.id, channel="email", from_address=lead.email,
                                   subject="Re: hi", body=body, classification=cls)
            ra.apply(db_session, reply)
            db_session.add(reply)
            rows.append(reply)
        db_session.commit()
        return rows

    def test_the_inbox_lists_scores(self, client, replies):
        body = client.get("/crm/replies").json()
        assert body["total"] == 3
        item = next(i for i in body["items"] if i["classification"] == "interested")
        assert item["authenticity"]["kind"] == "genuine"
        assert item["lead"]["full_name"] == "Lead 0"

    def test_filter_by_kind_and_automated(self, client, replies):
        assert client.get("/crm/replies?kind=out_of_office").json()["total"] == 1
        assert client.get("/crm/replies?kind=automated").json()["total"] == 1
        assert client.get("/crm/replies?kind=genuine").json()["total"] == 2

    def test_sort_by_intent(self, client, replies):
        items = client.get("/crm/replies?sort=intent").json()["items"]
        assert items[0]["classification"] == "interested"

    def test_min_intent(self, client, replies):
        assert client.get("/crm/replies?min_intent=0.5").json()["total"] == 1

    def test_rescore(self, client, db_session, replies):
        reply = replies[2]
        reply.authenticity_kind = None
        db_session.commit()
        body = client.post(f"/crm/replies/{reply.id}/authenticity/rescore").json()
        assert body["authenticity"]["kind"] == "genuine"

    def test_owner_scoped(self, client, db_session, replies):
        stranger = m.User(email="inbox-stranger@example.com", email_verified=True)
        db_session.add(stranger)
        db_session.commit()
        headers = auth_headers(stranger)
        assert client.get("/crm/replies", headers=headers).json()["total"] == 0
        assert client.get(f"/crm/replies/{replies[0].id}/authenticity",
                          headers=headers).status_code == 404

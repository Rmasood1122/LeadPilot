"""Feature A1 — the fabrication-proof claim engine.

Unit level: what counts as a claim, what counts as support, what is stripped
versus rewritten, the model extractor, the kill switch and fail-closed.
Send level: an email, a WhatsApp template and a call script go through the
REAL send path, and what reaches the channel has the fabricated claim removed
while the log explains why.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import claim_verification as cv
from app.services import system_settings
from tests.conftest import NOW, auth_headers


def _lead(**overrides) -> m.Lead:
    base = dict(id=uuid.uuid4(), source="apollo", full_name="Sara Khan", title="Founder",
                company="Acme Digital", enrichment_json={}, linkedin_posts_json=[],
                company_news_json=[])
    base.update(overrides)
    return m.Lead(**base)


def _check(lead, body, *, subject=None, model_claims=None, vocab=""):
    evidence = cv.build_evidence(lead)
    new_body, decisions = cv.verify_text(body, field_name="body", lead=lead, evidence=evidence,
                                         sender_vocab=vocab, model_claims=model_claims)
    return new_body, decisions


NEWS = [{"headline": "Acme Digital raises $20M Series B", "summary": "Led by Northstar Ventures",
         "url": "https://news.example/acme-b", "source": "TechWire",
         "published_at": "2026-09-01T00:00:00Z"}]
APOLLO = {"enrichment": {"person": {"organization": {"name": "Acme Digital",
                                                     "estimated_num_employees": 45,
                                                     "latest_funding_stage": "Series B"}}}}


class TestWhatIsAClaim:
    def test_statements_about_the_sender_are_not_checked(self):
        body, decisions = _check(_lead(), "We helped 40 agencies grow revenue 3x last year.")
        assert decisions == [] and "40 agencies" in body

    def test_plain_questions_and_opinions_pass_untouched(self):
        text = "Hi Sara,\n\nWould a 15-minute call next week be useful? Happy to share notes."
        body, decisions = _check(_lead(), text)
        assert body == text and decisions == []

    def test_the_greeting_is_never_the_hook(self):
        body, _ = _check(_lead(), "Hi Sara,\n\nCongrats on your recent Series C round.\n\n"
                                  "Worth a chat?")
        assert body.startswith("Hi Sara,")
        assert "Series C" not in body


class TestSupport:
    def test_a_funding_claim_backed_by_news_is_verified(self):
        lead = _lead(company_news_json=NEWS)
        body, (decision,) = _check(lead, "Congrats on Acme Digital's $20 million Series B.")
        assert decision.verdict == cv.VERIFIED
        assert decision.evidence.source == "newsapi:https://news.example/acme-b"
        assert "Series B" in body

    def test_money_is_unit_normalised(self):
        lead = _lead(company_news_json=NEWS)
        _, (decision,) = _check(lead, "Congrats on the $20,000,000 raise.")
        assert decision.verdict == cv.VERIFIED

    def test_a_wrong_number_is_unsupported(self):
        lead = _lead(company_news_json=NEWS)
        body, (decision,) = _check(lead, "Congrats on your $25M Series B.")
        assert decision.verdict == cv.REWRITTEN
        assert "number:2.5e+07" in decision.unsupported
        assert "$25M" not in body

    def test_a_wrong_series_is_unsupported(self):
        lead = _lead(company_news_json=NEWS)
        _, (decision,) = _check(lead, "Congrats on closing your Series C.")
        assert decision.verdict != cv.VERIFIED and "series:c" in decision.unsupported

    def test_headcount_from_apollo(self):
        lead = _lead(enrichment_json=APOLLO)
        _, (ok,) = _check(lead, "With your team of 45 people, onboarding must be busy.")
        assert ok.verdict == cv.VERIFIED and ok.evidence.source.startswith("apollo:")
        _, (bad,) = _check(lead, "With your team of 60 people, onboarding must be busy.")
        assert bad.verdict != cv.VERIFIED

    def test_a_named_partner_must_appear_in_the_evidence(self):
        news = [{"headline": "Acme Digital announces partnership with HubSpot", "summary": "",
                 "url": "u", "published_at": "2026-09-01T00:00:00Z"}]
        lead = _lead(company_news_json=news)
        _, (ok,) = _check(lead, "Saw your partnership with HubSpot, nice move.")
        assert ok.verdict == cv.VERIFIED
        _, (bad,) = _check(lead, "Saw your partnership with Salesforce, nice move.")
        assert bad.verdict != cv.VERIFIED and "name:Salesforce" in bad.unsupported

    def test_a_post_reference_needs_a_post(self):
        _, (bad,) = _check(_lead(), "Loved your recent post about hiring SDRs.")
        assert bad.verdict != cv.VERIFIED
        posts = [{"text": "Hiring SDRs is harder than ever. Here is what we changed.",
                  "url": "https://linkedin.com/p/1"}]
        _, (ok,) = _check(_lead(linkedin_posts_json=posts),
                          "Loved your recent post about hiring SDRs.")
        assert ok.verdict == cv.VERIFIED

    def test_a_quote_must_be_what_they_actually_wrote(self):
        posts = [{"text": "Cold email is dead for agencies.", "url": "p"}]
        lead = _lead(linkedin_posts_json=posts)
        _, (ok,) = _check(lead, 'You wrote "cold email is dead" last week.')
        assert ok.verdict == cv.VERIFIED
        _, (bad,) = _check(lead, 'You wrote "outbound is broken" last week.')
        assert bad.verdict != cv.VERIFIED

    def test_no_evidence_at_all_means_no_claim_survives(self):
        _, (decision,) = _check(_lead(), "Congrats on the acquisition of BrightPath.")
        assert decision.verdict != cv.VERIFIED


class TestStripOrRewrite:
    def test_an_unsupported_hook_is_rewritten_to_a_generic_line(self):
        body, (decision,) = _check(_lead(), "Congrats on your Series A. Would a quick call help?")
        assert decision.verdict == cv.REWRITTEN
        assert decision.replacement == "I wanted to reach out to you at Acme Digital directly."
        assert body.startswith("I wanted to reach out to you at Acme Digital directly.")
        assert body.endswith("Would a quick call help?")

    def test_an_unsupported_claim_later_in_the_body_is_stripped(self):
        text = ("Hi Sara,\n\nI run a small outbound studio. I noticed you're hiring three SDRs. "
                "Would a quick call help?")
        body, (decision,) = _check(_lead(), text)
        assert decision.verdict == cv.STRIPPED
        assert "hiring" not in body and "Would a quick call help?" in body
        assert "I run a small outbound studio." in body

    def test_a_message_that_was_nothing_but_claims_still_says_something_true(self):
        body, _ = _check(_lead(), "Congrats on the Series B. Your team doubled to 90 people.")
        assert body == "I wanted to reach out to you at Acme Digital directly."


class TestEnforce:
    def test_subject_body_and_logging(self, db_session, verified_strategy):
        lead = m.Lead(strategy_id=verified_strategy.id, source="apollo", external_id="C1",
                      full_name="Sara Khan", company="Acme Digital", email="s@acme.io",
                      status=m.LeadStatus.VERIFIED)
        db_session.add(lead)
        db_session.commit()
        out = cv.enforce(db_session, strategy=verified_strategy, lead=lead, message=None,
                         channel="email", fields={"subject": "Congrats on the Series B!",
                                                  "body": "Hi Sara,\n\nWorth a chat?"})
        db_session.commit()
        assert out["subject"] == cv.GENERIC_SUBJECT
        assert out["body"] == "Hi Sara,\n\nWorth a chat?"
        (row,) = db_session.execute(select(m.ClaimVerificationLog)).scalars().all()
        assert (row.field, row.verdict, row.category) == ("subject", "rewritten", "funding")
        assert row.replacement_text == cv.GENERIC_SUBJECT
        product = db_session.get(m.Product, verified_strategy.product_id)
        assert row.user_id == product.user_id

    def test_template_variables_and_list_items(self, db_session, verified_strategy):
        lead = _lead()
        out = cv.enforce(db_session, strategy=verified_strategy, lead=lead, message=None,
                         channel="whatsapp",
                         fields={"variable:1": "Sara", "variable:2": "your new Series B",
                                 "item:talking_point:0": "Congrats on your award"})
        assert out["variable:1"] == "Sara"
        assert out["variable:2"] == cv.GENERIC_VALUE
        assert out["item:talking_point:0"] == ""

    def test_the_model_finds_what_the_rules_miss(self, db_session, verified_strategy,
                                                 fake_claude):
        fake_claude.claim_extraction_response = {"claims": [
            {"text": "You are clearly scaling fast", "category": "other"}]}
        out = cv.enforce(db_session, strategy=verified_strategy, lead=_lead(), message=None,
                         channel="email",
                         fields={"body": "I run a studio. You are clearly scaling fast. Chat?"})
        assert "scaling fast" not in out["body"]
        assert fake_claude.claim_extraction_prompts

    def test_the_model_can_be_switched_off(self, db_session, verified_strategy, fake_claude):
        system_settings.set(db_session, "claim_model_extraction_enabled", False)
        fake_claude.claim_extraction_response = {"claims": [
            {"text": "You are clearly scaling fast", "category": "other"}]}
        out = cv.enforce(db_session, strategy=verified_strategy, lead=_lead(), message=None,
                         channel="email", fields={"body": "You are clearly scaling fast."})
        assert "scaling fast" in out["body"]
        assert fake_claude.claim_extraction_prompts == []

    def test_a_model_failure_leaves_the_rules_in_charge(self, db_session, verified_strategy,
                                                        fake_claude):
        fake_claude.claim_extraction_response = RuntimeError("model down")
        out = cv.enforce(db_session, strategy=verified_strategy, lead=_lead(), message=None,
                         channel="email", fields={"body": "Congrats on your Series B. Chat?"})
        assert "Series B" not in out["body"]

    def test_the_kill_switch(self, db_session, verified_strategy):
        system_settings.set(db_session, "claim_verification_enabled", False)
        out = cv.enforce(db_session, strategy=verified_strategy, lead=_lead(), message=None,
                         channel="email", fields={"body": "Congrats on your Series B."})
        assert out["body"] == "Congrats on your Series B."
        assert db_session.execute(select(m.ClaimVerificationLog)).first() is None

    def test_fails_closed_when_the_verifier_breaks(self, db_session, verified_strategy,
                                                   monkeypatch):
        lead = _lead(company_news_json=NEWS)

        def _boom(_lead):
            raise RuntimeError("evidence store unreachable")

        monkeypatch.setattr(cv, "build_evidence", _boom)
        out = cv.enforce(db_session, strategy=verified_strategy, lead=lead, message=None,
                         channel="email", fields={"body": "Congrats on your $20M Series B."})
        assert "Series B" not in out["body"], "no evidence -> nothing unverified gets through"


# --------------------------------------------------------------------------
# Through the real send path
# --------------------------------------------------------------------------


def _first_message(db_session, sequence):
    return db_session.execute(
        select(m.Message).where(m.Message.sequence_id == sequence.id)
        .order_by(m.Message.created_at)).scalars().first()


class TestSendPath:
    def test_an_email_never_carries_the_fabricated_claim(self, db_session, enrolled,
                                                         fake_channel, monkeypatch):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "render_message",
                            lambda *a, **k: ("Congrats on the Series B",
                                             "Hi Lead,\n\nCongrats on closing your Series B. "
                                             "Worth a quick chat?"))
        message = _first_message(db_session, enrolled)
        result = outreach_tasks.send_message_impl(db_session, message.id,
                                                  channel=fake_channel, now=NOW)
        assert result == "sent"
        (sent,) = fake_channel.sent
        assert "Series B" not in sent.body and "Series B" not in (sent.subject or "")
        assert "Worth a quick chat?" in sent.body
        assert "unsubscribe" in sent.body.lower(), "the compliance footer is untouched"
        db_session.refresh(message)
        assert "Series B" not in message.body
        rows = db_session.execute(select(m.ClaimVerificationLog).where(
            m.ClaimVerificationLog.message_id == message.id)).scalars().all()
        assert {(r.field, r.verdict) for r in rows} == {("subject", "rewritten"),
                                                       ("body", "rewritten")}

    def test_a_call_script_is_checked_and_its_prompt_rebuilt(self, db_session,
                                                             verified_strategy, verified_leads,
                                                             monkeypatch):
        from app.services import phone_calls
        from app.workers import outreach_tasks

        lead = verified_leads[0]
        sequence = m.Sequence(strategy_id=verified_strategy.id, channel=m.ChannelType.PHONE,
                              name="calls", status=m.SequenceStatus.ACTIVE)
        db_session.add(sequence)
        db_session.flush()
        message = m.Message(sequence_id=sequence.id, lead_id=lead.id,
                            channel=m.ChannelType.PHONE, step_no=1, template="call brief")
        db_session.add(message)
        db_session.commit()
        script = {"first_message": "Hi, this is an AI assistant. Congrats on your award.",
                  "voicemail": "Calling about your Series B.", "close": "Would Thursday work?",
                  "talking_points": ["Congrats on the acquisition", "Inspection backlog"],
                  "objective": "Book a call", "questions": [], "objection_handling": []}
        call = SimpleNamespace(script_json=script, voicemail_text=script["voicemail"],
                               voicemail_audio_url="https://media/vm.mp3", to_number="+1555")
        monkeypatch.setattr(phone_calls, "prepare_call",
                            lambda *a, **k: (call, {"first_message": script["first_message"],
                                                    "system_prompt": "old"}))
        outbound = outreach_tasks._render_phone_outbound(db_session, verified_strategy, lead,
                                                         message)
        assert "award" not in outbound.body
        assert call.script_json["talking_points"] == ["Inspection backlog"]
        assert "acquisition" not in outbound.metadata["system_prompt"]
        assert call.voicemail_audio_url is None, "audio of the unchecked text is never played"


class TestApi:
    def test_lead_claim_checks_are_owner_scoped(self, client, db_session, verified_strategy):
        lead = m.Lead(strategy_id=verified_strategy.id, source="apollo", external_id="C2",
                      full_name="Sara", company="Acme", email="c2@acme.io",
                      status=m.LeadStatus.VERIFIED)
        db_session.add(lead)
        db_session.commit()
        cv.enforce(db_session, strategy=verified_strategy, lead=lead, message=None,
                   channel="email", fields={"body": "Congrats on your Series B. Chat?"})
        db_session.commit()

        rows = client.get(f"/leads/{lead.id}/claim-checks").json()
        assert rows[0]["verdict"] == "rewritten" and rows[0]["category"] == "funding"
        summary = client.get("/claim-checks/summary").json()
        assert summary["totals"]["rewritten"] == 1

        stranger = m.User(email="claims-stranger@example.com", email_verified=True)
        db_session.add(stranger)
        db_session.commit()
        assert client.get(f"/leads/{lead.id}/claim-checks",
                          headers=auth_headers(stranger)).status_code == 404

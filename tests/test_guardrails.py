"""F05 Guardrails Studio -- per-account exclusion lists and the per-product
approved-claims / forbidden-phrases library.

What must hold (docs/features/f05-guardrails-studio.md):
  * SAFETY GUARD: a message to an excluded entity is never transmitted --
    the send chokepoint re-checks at send time, an exclusion added after
    scheduling still blocks, a lookup error defers (fails closed);
  * excluded entities are never sourced, are dropped when enrichment reveals
    them, and are never enrolled;
  * forbidden phrases block in the pre-launch review and at send, over the
    FINAL words (after a reviewer's edit);
  * approved claims gate proof claims about us in claim verification, only
    for products that have a library;
  * every list is strictly per account: another account's rows are neither
    visible nor enforced;
  * the flag off (the default) changes nothing anywhere.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, text

from app.db import models as m
from app.integrations.outreach_base import OutboundMessage
from app.services import adversarial_review, guardrails, system_settings
from app.services import claim_verification as cv
from app.workers import outreach_tasks
from app.workers.lead_tasks import (
    enrich_leads_impl,
    find_missing_emails_impl,
    source_leads_impl,
)
from app.workers.outreach_tasks import send_message_impl
from tests.conftest import NOW, auth_headers, make_raw

# --------------------------------------------------------------------------
# Fixtures and helpers
# --------------------------------------------------------------------------


@pytest.fixture()
def guards_on(db_session):
    system_settings.set(db_session, "guardrails_enabled", True)


@pytest.fixture()
def other_user(db_session):
    user = m.User(email="other-tenant@leadpilot.dev", email_verified=True)
    db_session.add(user)
    db_session.commit()
    return user


def _exclude(db, user, kind, value, reason="customer", **kw):
    row, _ = guardrails.upsert_exclusion(db, user.id, kind, value, reason=reason,
                                         now=kw.pop("now", None), **kw)
    db.commit()
    return row


def _message_for(db, lead):
    return db.execute(select(m.Message).where(m.Message.lead_id == lead.id)).scalar_one()


def _owner(db, strategy):
    return db.get(m.User, db.get(m.Product, strategy.product_id).user_id)


def _audit_rows(db, message):
    return db.execute(select(m.ComplianceAuditLog)
                      .where(m.ComplianceAuditLog.message_id == message.id)).scalars().all()


# --------------------------------------------------------------------------
# Normalisation -- one function per kind, for storing AND matching
# --------------------------------------------------------------------------


class TestNormalisation:
    @pytest.mark.parametrize("raw", ["acme.com", "ACME.com", "https://www.acme.com/about?x=1",
                                     "@acme.com", "jane@acme.com", "www.acme.com.",
                                     "http://acme.com:8080"])
    def test_domain_forms(self, raw):
        assert guardrails.normalize_domain(raw) == "acme.com"

    @pytest.mark.parametrize("raw", ["", "not a domain", "localhost", "10.0.0.1", "acme"])
    def test_invalid_domains(self, raw):
        assert guardrails.normalize_domain(raw) is None

    def test_shared_mailbox_domain_is_refused(self):
        with pytest.raises(guardrails.GuardrailValueError, match="shared mailbox"):
            guardrails.normalize("domain", "gmail.com")

    @pytest.mark.parametrize("raw", ["Acme", "ACME Inc", "Acme, Inc.", "Acme Corp.", "acme llc"])
    def test_company_forms(self, raw):
        assert guardrails.normalize_company(raw) == "acme"

    def test_company_matching_is_exact_not_fuzzy(self):
        assert guardrails.normalize_company("Acme Labs") == "acme labs"
        assert guardrails.normalize_company("AT&T") == "at and t"
        assert guardrails.normalize_company("X") is None

    @pytest.mark.parametrize("raw,expected", [
        ("Jane@Acme.com", "jane@acme.com"),
        ("+1 (555) 010-2000", "+15550102000"),
        ("https://www.linkedin.com/in/Jane-Doe/", "linkedin:jane-doe"),
        ("linkedin:jane-doe", "linkedin:jane-doe"),
    ])
    def test_contact_forms(self, raw, expected):
        assert guardrails.normalize_contact(raw) == expected

    @pytest.mark.parametrize("raw", ["jane@", "12", "hello world"])
    def test_invalid_contacts(self, raw):
        with pytest.raises(guardrails.GuardrailValueError):
            guardrails.normalize("contact", raw)

    @pytest.mark.parametrize("raw,kind", [("jane@acme.com", "contact"), ("acme.com", "domain"),
                                          ("Acme Inc", "company"), ("+15550102000", "contact"),
                                          ("https://linkedin.com/in/x", "contact")])
    def test_detect_kind(self, raw, kind):
        assert guardrails.detect_kind(raw) == kind


class TestMatching:
    def test_domain_matches_email_company_domain_and_subdomains(self, db_session, test_user):
        _exclude(db_session, test_user, "domain", "acme.com")
        find = lambda **kw: guardrails.find_match(db_session, test_user.id, **kw)  # noqa: E731
        assert find(email="x@acme.com") is not None
        assert find(email="x@eu.acme.com") is not None
        assert find(domains=["https://sales.acme.com"]) is not None
        assert find(email="x@notacme.com") is None
        assert find(email="x@acme.com.evil.io") is None

    def test_company_and_contact(self, db_session, test_user):
        _exclude(db_session, test_user, "company", "Globex Corporation")
        _exclude(db_session, test_user, "contact", "+1 555 010 2000")
        _exclude(db_session, test_user, "contact", "linkedin.com/in/jane-doe")
        find = lambda **kw: guardrails.find_match(db_session, test_user.id, **kw)  # noqa: E731
        assert find(company="GLOBEX") is not None
        assert find(company="Globex Labs") is None
        assert find(phone="+15550102000") is not None
        assert find(linkedin="https://www.linkedin.com/in/jane-doe/") is not None

    def test_removed_exclusion_no_longer_matches(self, db_session, test_user):
        row = _exclude(db_session, test_user, "domain", "acme.com")
        guardrails.remove_exclusion(db_session, test_user.id, row.id)
        assert guardrails.find_match(db_session, test_user.id, email="x@acme.com") is None

    def test_other_accounts_exclusion_never_matches(self, db_session, test_user, other_user):
        _exclude(db_session, other_user, "domain", "acme.com")
        assert guardrails.find_match(db_session, test_user.id, email="x@acme.com") is None
        assert guardrails.find_match(db_session, other_user.id, email="x@acme.com") is not None


# --------------------------------------------------------------------------
# THE SAFETY GUARD: the send chokepoint
# --------------------------------------------------------------------------


class TestSendTimeGuard:
    @pytest.mark.parametrize("kind,value", [
        ("domain", "co0.com"),
        ("domain", "https://www.CO0.com/"),
        ("company", "Co 0, Inc."),
        ("contact", "LEAD0@co0.com"),
    ])
    def test_exclusion_added_after_scheduling_blocks_the_send(
            self, db_session, guards_on, enrolled, verified_leads, verified_strategy,
            fake_channel, kind, value):
        lead = verified_leads[0]
        msg = _message_for(db_session, lead)
        _exclude(db_session, _owner(db_session, verified_strategy), kind, value)

        out = send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)

        assert out == "cancelled_excluded"
        assert fake_channel.sent == []
        assert msg.status is m.MessageStatus.CANCELLED
        assert msg.error.startswith(f"excluded by guardrails: {kind} (customer)")
        enrollment = db_session.execute(select(m.SequenceEnrollment).where(
            m.SequenceEnrollment.lead_id == lead.id)).scalar_one()
        assert enrollment.status is m.EnrollmentStatus.STOPPED
        assert enrollment.stop_reason == "suppressed_excluded"
        assert enrollment.stop_category == "suppressed"   # an authorised stop
        audit = _audit_rows(db_session, msg)
        assert [a.decision for a in audit] == ["blocked_excluded"]
        recorded = audit[0].checks_json["exclusion"]
        assert recorded["kind"] == kind and recorded["reason"] == "customer"
        assert "value" not in recorded, "the audit row never carries the identifier"

    def test_subdomain_of_an_excluded_domain_is_blocked(
            self, db_session, guards_on, enrolled, verified_leads, verified_strategy,
            fake_channel):
        lead = verified_leads[0]
        lead.email = "lead0@eu.co0.com"
        lead.enrichment_json = {"company_domain": "eu.co0.com"}
        db_session.commit()
        _exclude(db_session, _owner(db_session, verified_strategy), "domain", "co0.com")
        msg = _message_for(db_session, lead)
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == "cancelled_excluded"
        assert fake_channel.sent == []

    def test_other_leads_still_send(self, db_session, guards_on, enrolled, verified_leads,
                                    verified_strategy, fake_channel):
        _exclude(db_session, _owner(db_session, verified_strategy), "domain", "co0.com")
        msg = _message_for(db_session, verified_leads[1])
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"
        assert len(fake_channel.sent) == 1

    def test_removed_exclusion_lets_the_send_through(self, db_session, guards_on, enrolled,
                                                     verified_leads, verified_strategy,
                                                     fake_channel):
        owner = _owner(db_session, verified_strategy)
        row = _exclude(db_session, owner, "domain", "co0.com")
        guardrails.remove_exclusion(db_session, owner.id, row.id)
        msg = _message_for(db_session, verified_leads[0])
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"

    def test_another_accounts_exclusion_is_not_enforced(self, db_session, guards_on, enrolled,
                                                        verified_leads, other_user,
                                                        fake_channel):
        _exclude(db_session, other_user, "domain", "co0.com")
        msg = _message_for(db_session, verified_leads[0])
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"

    def test_lookup_error_defers_and_never_sends(self, db_session, guards_on, enrolled,
                                                 verified_leads, fake_channel, monkeypatch):
        def _broken(*_a, **_k):
            raise RuntimeError("database went away")

        monkeypatch.setattr(guardrails, "send_block", _broken)
        msg = _message_for(db_session, verified_leads[0])
        out = send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert out == "deferred_guardrails_unavailable"
        assert fake_channel.sent == []
        msg = db_session.get(m.Message, msg.id)
        assert msg.status is m.MessageStatus.SCHEDULED
        assert msg.scheduled_at.replace(tzinfo=None) >= (NOW + timedelta(minutes=59)).replace(
            tzinfo=None)

    def test_flag_off_changes_nothing(self, db_session, enrolled, verified_leads,
                                      verified_strategy, fake_channel):
        _exclude(db_session, _owner(db_session, verified_strategy), "domain", "co0.com")
        msg = _message_for(db_session, verified_leads[0])
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"

    def test_suppression_still_wins_first(self, db_session, guards_on, enrolled, verified_leads,
                                          verified_strategy, fake_channel):
        lead = verified_leads[0]
        db_session.add(m.SuppressionEntry(email=lead.email, reason="unsubscribed"))
        db_session.commit()
        _exclude(db_session, _owner(db_session, verified_strategy), "domain", "co0.com")
        msg = _message_for(db_session, lead)
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == "cancelled_suppressed"

    def test_exclusion_added_through_the_api_blocks_the_send(
            self, db_session, guards_on, enrolled, verified_leads, client, fake_channel):
        resp = client.post("/guardrails/exclusions",
                           json={"kind": "domain", "value": "co0.com", "reason": "churned"})
        assert resp.status_code == 201, resp.text
        msg = _message_for(db_session, verified_leads[0])
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == "cancelled_excluded"
        assert msg.error.endswith("(churned)")


# --------------------------------------------------------------------------
# Sourcing, enrichment, enrollment
# --------------------------------------------------------------------------


class TestSourcing:
    def test_excluded_raw_leads_are_never_created(self, db_session, guards_on, lead_batch,
                                                  verified_strategy, fake_source):
        owner = _owner(db_session, verified_strategy)
        _exclude(db_session, owner, "domain", "acme1.com")
        _exclude(db_session, owner, "company", "Acme 2")
        _exclude(db_session, owner, "contact", "p3@elsewhere.com")
        _exclude(db_session, owner, "domain", "acme4.com")
        fake_source.feed = [make_raw(1, email="p1@acme1.com"),
                            make_raw(2),
                            make_raw(3, email="p3@elsewhere.com"),
                            make_raw(4, domain="eu.acme4.com"),
                            make_raw(5, email="fine@acme5.com")]
        counts = source_leads_impl(db_session, lead_batch.id, source=fake_source)
        assert counts == {"added": 1, "duplicates": 0, "suppressed": 0, "plan_limit": 0,
                          "excluded": 4}
        emails = db_session.execute(select(m.Lead.email).where(
            m.Lead.batch_id == lead_batch.id)).scalars().all()
        assert emails == ["fine@acme5.com"]

    def test_flag_off_keeps_the_result_shape_and_sources_everything(
            self, db_session, lead_batch, verified_strategy, fake_source):
        _exclude(db_session, _owner(db_session, verified_strategy), "domain", "acme1.com")
        fake_source.feed = [make_raw(1, email="p1@acme1.com")]
        counts = source_leads_impl(db_session, lead_batch.id, source=fake_source)
        assert counts == {"added": 1, "duplicates": 0, "suppressed": 0, "plan_limit": 0}

    def test_another_accounts_exclusions_do_not_filter_sourcing(
            self, db_session, guards_on, lead_batch, other_user, fake_source):
        _exclude(db_session, other_user, "domain", "acme1.com")
        fake_source.feed = [make_raw(1, email="p1@acme1.com")]
        counts = source_leads_impl(db_session, lead_batch.id, source=fake_source)
        assert counts["added"] == 1 and counts["excluded"] == 0

    def test_enrichment_that_reveals_an_excluded_domain_drops_the_lead(
            self, db_session, guards_on, lead_batch, verified_strategy, fake_source):
        fake_source.feed = [make_raw(1), make_raw(2)]
        source_leads_impl(db_session, lead_batch.id, source=fake_source)
        # FakeLeadSource.enrich derives the domain from the company: acme1.com
        row = _exclude(db_session, _owner(db_session, verified_strategy), "domain", "acme1.com")
        enrich_leads_impl(db_session, lead_batch.id, source=fake_source)
        leads = {l.external_id: l for l in db_session.execute(select(m.Lead).where(
            m.Lead.batch_id == lead_batch.id)).scalars()}
        assert leads["p1"].status is m.LeadStatus.DROPPED
        assert leads["p1"].enrichment_json["dropped_reason"] == "excluded"
        assert leads["p1"].enrichment_json["excluded_by"] == str(row.id)
        assert leads["p2"].status is m.LeadStatus.ENRICHED

    def test_found_email_on_the_exclusion_list_drops_the_lead(
            self, db_session, guards_on, lead_batch, verified_strategy, fake_source,
            fake_verifier):
        fake_source.feed = [make_raw(1), make_raw(2)]
        source_leads_impl(db_session, lead_batch.id, source=fake_source)
        enrich_leads_impl(db_session, lead_batch.id, source=fake_source)
        _exclude(db_session, _owner(db_session, verified_strategy), "contact",
                 "person.1@acme1.com", reason="do_not_contact")
        result = find_missing_emails_impl(db_session, lead_batch.id, verifier=fake_verifier)
        assert result["dropped"] == 1 and result["found"] == 1
        dropped = db_session.execute(select(m.Lead).where(
            m.Lead.batch_id == lead_batch.id, m.Lead.external_id == "p1")).scalar_one()
        assert dropped.status is m.LeadStatus.DROPPED
        assert dropped.enrichment_json["dropped_reason"] == "excluded"


class TestEnrollment:
    def test_excluded_leads_are_not_enrolled(self, db_session, guards_on, fake_claude,
                                             email_sequence, verified_leads, gmail_account,
                                             verified_strategy):
        from app.services.sequence_engine import enroll_leads

        _exclude(db_session, _owner(db_session, verified_strategy), "domain", "co1.com")
        assert enroll_leads(db_session, email_sequence, now=NOW) == 2
        enrolled_ids = set(db_session.execute(select(m.SequenceEnrollment.lead_id)).scalars())
        assert verified_leads[1].id not in enrolled_ids

    def test_flag_off_enrolls_everyone(self, db_session, fake_claude, email_sequence,
                                       verified_leads, gmail_account, verified_strategy):
        from app.services.sequence_engine import enroll_leads

        _exclude(db_session, _owner(db_session, verified_strategy), "domain", "co1.com")
        assert enroll_leads(db_session, email_sequence, now=NOW) == 3


# --------------------------------------------------------------------------
# Forbidden phrases: pre-launch review + send time (final words)
# --------------------------------------------------------------------------


def _fake_render(subject, body):
    def _render(session, strategy, lead, sequence, message):
        message.subject, message.body = subject, body
        return OutboundMessage(message_id=str(message.id), lead_id=str(lead.id),
                               to_address=lead.email, subject=subject, body=body)
    return _render


def _library(db, user, kind, text_, product_id=None):
    return guardrails.add_library_entry(db, user.id, kind, text_, product_id=product_id)


class TestForbiddenPhrases:
    def test_pure_matching_rules(self):
        hits = guardrails.forbidden_hits(
            ["We GUARANTEE   results", "the #1 platform"],
            ["guarantee results", "guaranteed", "#1", "risk free"])
        assert hits == ["guarantee results", "#1"]
        assert guardrails.forbidden_hits(["guaranteed"], ["guarantee"]) == []

    def test_send_is_blocked_over_the_rendered_words(
            self, db_session, guards_on, enrolled, verified_leads, verified_strategy,
            fake_channel, monkeypatch):
        owner = _owner(db_session, verified_strategy)
        _library(db_session, owner, "forbidden_phrase", "guaranteed results",
                 product_id=verified_strategy.product_id)
        monkeypatch.setattr(outreach_tasks, "_render_email_outbound",
                            _fake_render("Hi", "We deliver guaranteed  results."))
        msg = _message_for(db_session, verified_leads[0])
        out = send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert out == "blocked_forbidden_phrase"
        assert fake_channel.sent == []
        assert msg.status is m.MessageStatus.FAILED
        assert msg.error == "forbidden phrase: guaranteed results"
        audit = _audit_rows(db_session, msg)
        assert [a.decision for a in audit] == ["blocked_forbidden_phrase"]
        assert audit[0].checks_json["forbidden_phrases"] == ["guaranteed results"]

    def test_a_reviewer_edit_is_what_gets_checked(
            self, db_session, guards_on, enrolled, verified_leads, verified_strategy,
            fake_channel, monkeypatch):
        from app.services import send_review

        owner = _owner(db_session, verified_strategy)
        _library(db_session, owner, "forbidden_phrase", "act fast")
        monkeypatch.setattr(outreach_tasks, "_render_email_outbound",
                            _fake_render("Hi", "A clean message."))
        monkeypatch.setattr(send_review, "gate", lambda db, lead, message, s, b, now=None: {
            "action": "send", "subject": s, "body": "Edited: act fast!"})
        msg = _message_for(db_session, verified_leads[0])
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == "blocked_forbidden_phrase"
        assert fake_channel.sent == []

        # ...and the other way round: the edit REMOVED the phrase -> it sends.
        monkeypatch.setattr(outreach_tasks, "_render_email_outbound",
                            _fake_render("Hi", "Rendered: act fast!"))
        monkeypatch.setattr(send_review, "gate", lambda db, lead, message, s, b, now=None: {
            "action": "send", "subject": s, "body": "Edited and clean."})
        msg2 = _message_for(db_session, verified_leads[1])
        assert send_message_impl(db_session, msg2.id, channel=fake_channel, now=NOW) == "sent"
        assert fake_channel.sent[-1].body == "Edited and clean."

    def test_another_products_phrases_do_not_apply(
            self, db_session, guards_on, enrolled, verified_leads, verified_strategy,
            fake_channel, monkeypatch, test_user):
        other_product = m.Product(user=test_user, name="Other", description="x",
                                  type=m.ProductType.SKILL)
        db_session.add(other_product)
        db_session.commit()
        _library(db_session, test_user, "forbidden_phrase", "free trial",
                 product_id=other_product.id)
        monkeypatch.setattr(outreach_tasks, "_render_email_outbound",
                            _fake_render("Hi", "Start a free trial today."))
        msg = _message_for(db_session, verified_leads[0])
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"

    def test_flag_off_sends(self, db_session, enrolled, verified_leads, verified_strategy,
                            fake_channel, monkeypatch):
        _library(db_session, _owner(db_session, verified_strategy), "forbidden_phrase",
                 "guaranteed results")
        monkeypatch.setattr(outreach_tasks, "_render_email_outbound",
                            _fake_render("Hi", "We deliver guaranteed results."))
        msg = _message_for(db_session, verified_leads[0])
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"

    def test_pre_launch_review_blocks_a_forbidden_phrase(self, db_session, guards_on,
                                                         email_sequence, verified_strategy):
        _library(db_session, _owner(db_session, verified_strategy), "forbidden_phrase",
                 "step 2")
        findings = adversarial_review.rule_findings(db_session, email_sequence)
        hit = [f for f in findings if f["code"].startswith("guardrail:forbidden:")]
        assert len(hit) == 1
        assert hit[0]["severity"] == "block" and hit[0]["step_no"] == 2

    def test_pre_launch_review_flag_off_has_no_guardrail_finding(
            self, db_session, email_sequence, verified_strategy):
        _library(db_session, _owner(db_session, verified_strategy), "forbidden_phrase",
                 "step 2")
        findings = adversarial_review.rule_findings(db_session, email_sequence)
        assert not [f for f in findings if f["code"].startswith("guardrail:")]


# --------------------------------------------------------------------------
# Approved claims -> claim verification
# --------------------------------------------------------------------------

BODY = ("Hi Lead,\n\nWe helped 40 agencies grow revenue 3x last year. "
        "We are trusted by Fortune 500 brands. Worth a chat?")
SUBJECT = "Our clients see 250% more replies"


@pytest.fixture()
def rules_only(db_session):
    system_settings.set(db_session, "claim_model_extraction_enabled", False)


def _enforce(db, strategy, lead):
    return cv.enforce(db, strategy=strategy, lead=lead, message=None, channel="email",
                      fields={"subject": SUBJECT, "body": BODY})


def _sender_logs(db, lead):
    return db.execute(select(m.ClaimVerificationLog).where(
        m.ClaimVerificationLog.lead_id == lead.id,
        m.ClaimVerificationLog.category == "sender_claim")).scalars().all()


class TestApprovedClaims:
    def test_unapproved_claims_about_us_are_stripped_and_logged(
            self, db_session, guards_on, rules_only, verified_strategy, verified_leads):
        lead = verified_leads[0]
        claim = _library(db_session, _owner(db_session, verified_strategy), "approved_claim",
                         "We helped 40 agencies grow revenue 3x in 2025.",
                         product_id=verified_strategy.product_id)
        out = _enforce(db_session, verified_strategy, lead)
        db_session.commit()

        assert "40 agencies" in out["body"]
        assert "Fortune" not in out["body"] and "Worth a chat?" in out["body"]
        assert out["subject"] == cv.GENERIC_SUBJECT
        logs = {r.verdict: r for r in _sender_logs(db_session, lead)}
        assert set(logs) == {"verified", "stripped", "rewritten"}
        assert logs["verified"].evidence_source == f"approved_claim:{claim.id}"
        assert logs["verified"].extractor == "library"
        assert "phrase:trusted by" in logs["stripped"].unsupported_json
        assert logs["rewritten"].replacement_text == cv.GENERIC_SUBJECT

    def test_a_product_without_a_library_is_untouched(self, db_session, guards_on, rules_only,
                                                      verified_strategy, verified_leads,
                                                      test_user):
        other_product = m.Product(user=test_user, name="Other", description="x",
                                  type=m.ProductType.SKILL)
        db_session.add(other_product)
        db_session.commit()
        _library(db_session, test_user, "approved_claim", "Something else entirely.",
                 product_id=other_product.id)
        out = _enforce(db_session, verified_strategy, verified_leads[0])
        assert out == {"subject": SUBJECT, "body": BODY}

    def test_account_wide_claims_apply_to_every_product(self, db_session, guards_on, rules_only,
                                                        verified_strategy, verified_leads,
                                                        test_user):
        _library(db_session, test_user, "approved_claim",
                 "We are trusted by Fortune 500 brands; we helped 40 agencies grow revenue 3x; "
                 "our clients see 250% more replies.")
        out = _enforce(db_session, verified_strategy, verified_leads[0])
        assert out == {"subject": SUBJECT, "body": BODY}

    def test_flag_off_is_untouched(self, db_session, rules_only, verified_strategy,
                                   verified_leads, test_user):
        _library(db_session, test_user, "approved_claim", "Nothing that matches.")
        out = _enforce(db_session, verified_strategy, verified_leads[0])
        assert out == {"subject": SUBJECT, "body": BODY}
        db_session.commit()
        assert _sender_logs(db_session, verified_leads[0]) == []

    def test_library_error_fails_closed(self, db_session, guards_on, rules_only,
                                        verified_strategy, verified_leads, monkeypatch):
        def _broken(*_a, **_k):
            raise RuntimeError("library unreadable")

        monkeypatch.setattr(guardrails, "approved_claims", _broken)
        out = _enforce(db_session, verified_strategy, verified_leads[0])
        assert "40 agencies" not in out["body"] and "Fortune" not in out["body"]
        assert out["subject"] == cv.GENERIC_SUBJECT

    def test_sentences_that_are_not_proof_claims_about_us_are_kept(self, verified_leads):
        lead = verified_leads[0] if verified_leads else None
        text_, decisions = guardrails.verify_sender_claims(
            "We work with teams like yours. Happy to share more. Your 3 offices look busy.",
            [], field_name="body", lead=lead)
        assert decisions == []
        assert text_.startswith("We work with teams like yours.")


# --------------------------------------------------------------------------
# CSV import, CRM sync, audit
# --------------------------------------------------------------------------


class TestCsvImport:
    def test_typed_layout_with_errors_by_row(self, db_session, test_user):
        csv_text = ("type,value,reason,note\n"
                    "domain,acme.com,customer,big one\n"
                    "company,Globex Inc,churned,\n"
                    ",jane@initech.com,do_not_contact,\n"     # kind detected
                    "domain,gmail.com,customer,\n"            # refused
                    "contact,not-an-identifier,,\n"           # invalid
                    "domain,acme.com,customer,\n"             # duplicate -> exists
                    "company,Umbrella,nonsense,\n")           # bad reason
        result = guardrails.import_csv(db_session, test_user.id, csv_text)
        assert (result["added"], result["exists"], result["error_count"]) == (3, 1, 3)
        assert [e["row"] for e in result["errors"]] == [5, 6, 8]
        rows = guardrails.list_exclusions(db_session, test_user.id)["items"]
        assert {(r["kind"], r["value"], r["source"]) for r in rows} == {
            ("domain", "acme.com", "csv"), ("company", "globex", "csv"),
            ("contact", "jane@initech.com", "csv")}

    def test_column_layout(self, db_session, test_user):
        csv_text = "Company,Domain,Email\nAcme,acme.com,a@acme.com\nGlobex,,\n"
        result = guardrails.import_csv(db_session, test_user.id, csv_text,
                                       default_reason="customer")
        assert result["added"] == 4 and result["error_count"] == 0

    def test_header_is_required(self, db_session, test_user):
        with pytest.raises(guardrails.GuardrailValueError, match="header"):
            guardrails.import_csv(db_session, test_user.id, "acme.com\nglobex.com\n")

    def test_size_limit(self, db_session, test_user, monkeypatch):
        monkeypatch.setattr(guardrails, "MAX_CSV_BYTES", 20)
        with pytest.raises(guardrails.GuardrailValueError, match="2 MB"):
            guardrails.import_csv(db_session, test_user.id, "type,value\n" + "x" * 50)

    def test_reimport_reactivates_a_removed_row(self, db_session, test_user):
        row = _exclude(db_session, test_user, "domain", "acme.com", now=NOW - timedelta(days=5))
        guardrails.remove_exclusion(db_session, test_user.id, row.id, now=NOW - timedelta(days=1))
        result = guardrails.import_csv(db_session, test_user.id, "type,value\ndomain,acme.com\n",
                                       now=NOW)
        assert result["reactivated"] == 1
        db_session.refresh(row)
        assert row.removed_at is None
        assert row.active_since.replace(tzinfo=None) == NOW.replace(tzinfo=None)


class FakeHubSpot:
    def __init__(self):
        self.calls = []

    def search(self, object_type, filter_groups, properties, *, max_pages=50):
        f = filter_groups[0]["filters"][0]
        self.calls.append((object_type, f))
        if f["propertyName"] == "hs_num_open_deals":
            return [{"id": "2", "properties": {"name": "Initech", "domain": "https://www.initech.io"}}]
        if "customer" in f.get("values", []):
            return [{"id": "1", "properties": {"name": "Globex Corp", "domain": "globex.com"}},
                    {"id": "9", "properties": {"name": "Freemail Co", "domain": "gmail.com"}}]
        if "other" in f.get("values", []):
            return [{"id": "3", "properties": {"name": "Umbrella", "domain": None}}]
        return []


class FakeSalesforce:
    def query_all(self, soql, *, max_pages=50):
        if "FROM Opportunity" in soql:
            return [{"Id": "o1", "AccountId": "a2",
                     "Account": {"Name": "Hooli", "Website": "hooli.xyz"}}]
        if "'Former Customer'" in soql:
            return [{"Id": "a3", "Name": "Pied Piper", "Website": "http://piedpiper.com"}]
        return [{"Id": "a1", "Name": "Vandelay Industries", "Website": "www.vandelay.com"}]


class TestCrmSync:
    @pytest.fixture()
    def crm_data(self, db_session, verified_strategy, test_user):
        won = m.Lead(strategy_id=verified_strategy.id, source="x", external_id="W",
                     email="ceo@wonco.com", status=m.LeadStatus.CLOSED_WON,
                     enrichment_json={"company_domain": "wonco.com"})
        open_ = m.Lead(strategy_id=verified_strategy.id, source="x", external_id="O",
                       email="buyer@gmail.com", status=m.LeadStatus.OPPORTUNITY)
        lost = m.Lead(strategy_id=verified_strategy.id, source="x", external_id="L",
                      email="no@lostco.com", status=m.LeadStatus.OPPORTUNITY,
                      enrichment_json={"company_domain": "lostco.com"})
        db_session.add_all([won, open_, lost])
        db_session.flush()
        db_session.add_all([
            m.Deal(user_id=test_user.id, lead_id=open_.id, name="Open", stage=m.DealStage.OPEN),
            m.Deal(user_id=test_user.id, lead_id=lost.id, name="Lost", stage=m.DealStage.LOST)])
        db_session.commit()

    def _values(self, db, user):
        return {(r["kind"], r["value"], r["reason"], r["source"])
                for r in guardrails.list_exclusions(db, user.id, limit=500)["items"]}

    def test_local_sources_customers_and_open_deals(self, db_session, crm_data, test_user):
        result = guardrails.sync_from_crm(db_session, test_user.id)
        assert result == {"local": {"status": "ok", "added": 3, "reactivated": 0, "exists": 0,
                                    "invalid": 0}}
        assert self._values(db_session, test_user) == {
            ("domain", "wonco.com", "customer", "crm_local"),
            ("contact", "ceo@wonco.com", "customer", "crm_local"),
            # an open deal on a gmail address: the contact, never gmail.com
            ("contact", "buyer@gmail.com", "open_deal", "crm_local")}

    def test_hubspot_and_salesforce(self, db_session, test_user, monkeypatch):
        from app.services import crm_sync

        hub = FakeHubSpot()
        db_session.add_all([
            m.CrmConnection(user_id=test_user.id, provider="hubspot",
                            settings_json={"churned_lifecycle_stages": ["other"]}),
            m.CrmConnection(user_id=test_user.id, provider="salesforce")])
        db_session.commit()
        monkeypatch.setattr(crm_sync, "hubspot_client", lambda db, conn: hub)
        monkeypatch.setattr(crm_sync, "salesforce_client", lambda db, conn: FakeSalesforce())

        result = guardrails.sync_from_crm(db_session, test_user.id)
        assert result["hubspot"]["status"] == "ok" and result["salesforce"]["status"] == "ok"
        values = self._values(db_session, test_user)
        assert ("domain", "globex.com", "customer", "crm_hubspot") in values
        assert ("company", "globex", "customer", "crm_hubspot") in values
        assert ("domain", "initech.io", "open_deal", "crm_hubspot") in values
        assert ("company", "umbrella", "churned", "crm_hubspot") in values
        assert ("domain", "vandelay.com", "customer", "crm_salesforce") in values
        assert ("domain", "hooli.xyz", "open_deal", "crm_salesforce") in values
        assert ("domain", "piedpiper.com", "churned", "crm_salesforce") in values
        assert not any(v[1] == "gmail.com" for v in values)
        assert {c[1]["propertyName"] for c in hub.calls} == {"lifecyclestage",
                                                              "hs_num_open_deals"}

    def test_a_vendor_error_is_isolated_and_nothing_is_removed(self, db_session, test_user,
                                                               crm_data, monkeypatch):
        from app.services import crm_sync

        manual = _exclude(db_session, test_user, "domain", "keep.com", reason="partner")
        db_session.add(m.CrmConnection(user_id=test_user.id, provider="hubspot"))
        db_session.commit()

        def _boom(db, conn):
            raise RuntimeError("HubSpot 401")

        monkeypatch.setattr(crm_sync, "hubspot_client", _boom)
        result = guardrails.sync_from_crm(db_session, test_user.id)
        assert result["hubspot"] == {"status": "error", "error": "HubSpot 401"}
        assert result["local"]["added"] == 3
        db_session.refresh(manual)
        assert manual.removed_at is None
        # The CRM forgetting a customer does not remove the exclusion.
        db_session.execute(text("UPDATE leads SET status = 'opportunity' "
                                "WHERE external_id = 'W'"))
        db_session.commit()
        guardrails.sync_from_crm(db_session, test_user.id)
        assert ("domain", "wonco.com", "customer", "crm_local") in self._values(db_session,
                                                                              test_user)

    def test_only_this_accounts_records_are_read(self, db_session, crm_data, other_user):
        result = guardrails.sync_from_crm(db_session, other_user.id)
        assert result["local"]["added"] == 0
        assert self._values(db_session, other_user) == set()

    def test_daily_task_is_a_noop_while_off_and_syncs_when_on(self, db_session, crm_data,
                                                              test_user):
        from app.workers import crm_tasks

        assert crm_tasks.guardrails_crm_sync_all_impl(db_session) == {"status": "disabled"}
        system_settings.set(db_session, "guardrails_enabled", True)
        result = crm_tasks.guardrails_crm_sync_all_impl(db_session)
        assert result["status"] == "ok" and result["ok"] >= 1
        assert self._values(db_session, test_user)


class TestAuditTrail:
    def _actions(self, db, user):
        return [r.action for r in db.execute(
            select(m.SecurityAuditEvent).where(m.SecurityAuditEvent.owner_user_id == user.id)
            .order_by(m.SecurityAuditEvent.created_at)).scalars()]

    def test_every_list_change_is_recorded(self, client, db_session, guards_on, test_user):
        added = client.post("/guardrails/exclusions", json={"kind": "contact",
                                                            "value": "jane@acme.com"}).json()
        client.delete(f"/guardrails/exclusions/{added['id']}")
        client.post("/guardrails/exclusions/import", json={"csv": "type,value\ndomain,a.com\n"})
        client.post("/guardrails/exclusions/crm-sync")
        entry = client.post("/guardrails/library", json={"kind": "forbidden_phrase",
                                                         "text": "act now"}).json()
        client.delete(f"/guardrails/library/{entry['id']}")
        actions = self._actions(db_session, test_user)
        # created_at has one-second resolution on SQLite: compare as a multiset.
        assert sorted(a for a in actions if a.startswith("guardrails.")) == sorted([
            guardrails.AUDIT_ADDED, guardrails.AUDIT_REMOVED, guardrails.AUDIT_IMPORTED,
            guardrails.AUDIT_CRM_SYNCED, guardrails.AUDIT_LIBRARY_ADDED,
            guardrails.AUDIT_LIBRARY_REMOVED])
        details = db_session.execute(select(m.SecurityAuditEvent.details_json)).scalars().all()
        assert not any("jane@acme.com" in str(d) for d in details), \
            "audit rows carry kinds and counts, never the identifier"


# --------------------------------------------------------------------------
# API: flag, validation, tenancy
# --------------------------------------------------------------------------


class TestApi:
    def test_writes_are_refused_while_the_flag_is_off(self, client):
        status = client.get("/guardrails/status").json()
        assert status["enabled"] is False
        resp = client.post("/guardrails/exclusions", json={"kind": "domain", "value": "a.com"})
        assert resp.status_code == 409
        assert resp.json()["detail"]["error"] == "guardrails_disabled"
        assert client.post("/guardrails/library", json={"kind": "forbidden_phrase",
                                                        "text": "act now"}).status_code == 409
        assert client.get("/guardrails/exclusions").status_code == 200

    def test_add_list_check_remove(self, client, guards_on):
        resp = client.post("/guardrails/exclusions",
                           json={"kind": "domain", "value": "https://www.Acme.com",
                                 "reason": "customer", "note": "renewal in May"})
        assert resp.status_code == 201
        assert resp.json()["value"] == "acme.com"
        again = client.post("/guardrails/exclusions", json={"kind": "domain", "value": "acme.com"})
        assert again.status_code == 200 and again.json()["status"] == "exists"
        check = client.post("/guardrails/exclusions/check", json={"email": "x@eu.acme.com"})
        assert check.json()["excluded"] is True
        assert check.json()["match"]["reason"] == "customer"
        listed = client.get("/guardrails/exclusions?kind=domain").json()
        assert listed["total"] == 1
        removed = client.delete(f"/guardrails/exclusions/{resp.json()['id']}")
        assert removed.status_code == 200 and removed.json()["active"] is False
        assert client.get("/guardrails/exclusions").json()["total"] == 0
        assert client.get("/guardrails/exclusions?include_removed=true").json()["total"] == 1

    def test_validation(self, client, guards_on):
        assert client.post("/guardrails/exclusions",
                           json={"kind": "domain", "value": "gmail.com"}).status_code == 422
        assert client.post("/guardrails/exclusions",
                           json={"kind": "domain", "value": "acme.com",
                                 "reason": "because"}).status_code == 422
        assert client.post("/guardrails/exclusions",
                           json={"kind": "planet", "value": "mars"}).status_code == 422
        assert client.post("/guardrails/library",
                           json={"kind": "approved_claim", "text": "We are great",
                                 "source_url": "javascript:alert(1)"}).status_code == 422

    def test_another_account_cannot_see_or_touch_my_rows(self, client, guards_on, db_session,
                                                         product_with_strategy, other_user):
        product, _ = product_with_strategy(m.FlowType.WITH_CLIENTS)
        mine = client.post("/guardrails/exclusions",
                           json={"kind": "domain", "value": "acme.com"}).json()
        entry = client.post("/guardrails/library",
                            json={"kind": "forbidden_phrase", "text": "act now",
                                  "product_id": str(product.id)}).json()

        client.headers.update(auth_headers(other_user))
        assert client.get("/guardrails/exclusions").json()["total"] == 0
        assert client.get("/guardrails/status").json()["exclusions"]["domain"] == 0
        assert client.post("/guardrails/exclusions/check",
                           json={"email": "x@acme.com"}).json()["excluded"] is False
        assert client.delete(f"/guardrails/exclusions/{mine['id']}").status_code == 404
        assert client.delete(f"/guardrails/library/{entry['id']}").status_code == 404
        assert client.get(f"/guardrails/library?product_id={product.id}").status_code == 404
        assert client.post("/guardrails/library",
                           json={"kind": "approved_claim", "text": "We are great",
                                 "product_id": str(product.id)}).status_code == 404
        assert client.get("/guardrails/library").json()["items"] == []
        # ...and nothing of mine changed.
        row = db_session.get(m.GuardrailExclusion, uuid.UUID(mine["id"]))
        assert row.removed_at is None

    def test_library_listing_for_a_product_includes_account_wide_entries(
            self, client, guards_on, product_with_strategy):
        product, _ = product_with_strategy(m.FlowType.WITH_CLIENTS)
        client.post("/guardrails/library", json={"kind": "forbidden_phrase", "text": "act now"})
        client.post("/guardrails/library", json={"kind": "approved_claim",
                                                 "text": "We helped 40 agencies",
                                                 "product_id": str(product.id),
                                                 "source_url": "https://example.com/case"})
        items = client.get(f"/guardrails/library?product_id={product.id}").json()["items"]
        assert {i["kind"] for i in items} == {"forbidden_phrase", "approved_claim"}
        assert client.get("/guardrails/library").json()["items"][0]["text"] == "act now"

    def test_products_lists_only_my_products(self, client, product_with_strategy, other_user,
                                             db_session):
        mine, _ = product_with_strategy(m.FlowType.WITH_CLIENTS)
        db_session.add(m.Product(user=other_user, name="Theirs", description="x",
                                 type=m.ProductType.SKILL))
        db_session.commit()
        items = client.get("/guardrails/products").json()["items"]
        assert items == [{"id": str(mine.id), "name": mine.name}]

    def test_csv_import_endpoint(self, client, guards_on):
        resp = client.post("/guardrails/exclusions/import",
                           json={"csv": "type,value\ndomain,acme.com\ndomain,gmail.com\n",
                                 "default_reason": "customer"})
        assert resp.status_code == 200
        assert resp.json()["added"] == 1 and resp.json()["error_count"] == 1
        bad = client.post("/guardrails/exclusions/import", json={"csv": "acme.com\n"})
        assert bad.status_code == 422


class TestManualCall:
    def test_an_excluded_lead_is_never_dialled(self, client, db_session, guards_on, test_user,
                                               verified_strategy, monkeypatch):
        from tests.test_phone_calls import FakeVoice

        vapi = FakeVoice("vapi")
        monkeypatch.setattr("app.integrations.voice_providers.get_clients",
                            lambda db, user_id=None: (vapi, None))
        system_settings.set(db_session, "phone_calling_enabled", True)
        test_user.plan = m.PlanTier.SCALE
        lead = m.Lead(strategy_id=verified_strategy.id, source="apollo", external_id="PHX",
                      full_name="Sara Khan", company="Acme Fire", phone="+1 (555) 010-2000",
                      status=m.LeadStatus.VERIFIED, phone_consent_at=NOW)
        db_session.add(lead)
        db_session.commit()
        _exclude(db_session, test_user, "company", "Acme Fire LLC")
        resp = client.post(f"/leads/{lead.id}/call", json={})
        assert resp.status_code == 409
        assert resp.json()["detail"] == "this contact is on your exclusion list"
        assert vapi.calls == []


# --------------------------------------------------------------------------
# The production audit query (spec section 11) -- its logic, on SQLite
# --------------------------------------------------------------------------

# SQLite translation of the PostgreSQL query in the spec: same joins, same
# active-at-send-time window, domain and contact-email branches. split_part ->
# substr/instr. It proves the WINDOW logic; the PostgreSQL text itself has not
# been run against production (spec: Unverified).
_AUDIT_SQL = text("""
SELECT m.id AS message_id, e.id AS exclusion_id
FROM messages m
JOIN leads l      ON l.id = m.lead_id
JOIN strategies s ON s.id = l.strategy_id
JOIN products p   ON p.id = s.product_id
JOIN guardrail_exclusions e
  ON e.user_id = p.user_id
 AND e.active_since <= m.sent_at
 AND (e.removed_at IS NULL OR e.removed_at > m.sent_at)
WHERE m.status = 'sent' AND m.sent_at IS NOT NULL
  AND ((e.kind = 'domain'
        AND (lower(substr(l.email, instr(l.email, '@') + 1)) = e.value
             OR lower(substr(l.email, instr(l.email, '@') + 1)) LIKE '%.' || e.value))
    OR (e.kind = 'contact' AND e.value = lower(l.email)))
""")


def test_audit_query_counts_only_sends_while_an_exclusion_was_active(
        db_session, enrolled, verified_leads, verified_strategy, other_user):
    owner = _owner(db_session, verified_strategy)
    for lead in verified_leads:
        msg = _message_for(db_session, lead)
        msg.status, msg.sent_at = m.MessageStatus.SENT, NOW
    # lead 0: excluded a day BEFORE the send -> a violation
    violation = _exclude(db_session, owner, "domain", "co0.com", now=NOW - timedelta(days=1))
    # lead 1: excluded an hour AFTER the send -> not a violation
    _exclude(db_session, owner, "contact", "lead1@co1.com", now=NOW + timedelta(hours=1))
    # lead 2: excluded, then removed before the send -> not a violation
    removed = _exclude(db_session, owner, "domain", "co2.com", now=NOW - timedelta(days=3))
    removed.removed_at = NOW - timedelta(days=2)
    # another account excluding lead 1's domain -> never counts for this account
    _exclude(db_session, other_user, "domain", "co1.com", now=NOW - timedelta(days=9))
    db_session.commit()

    rows = db_session.execute(_AUDIT_SQL).all()
    assert len(rows) == 1
    assert uuid.UUID(str(rows[0].exclusion_id)) == violation.id

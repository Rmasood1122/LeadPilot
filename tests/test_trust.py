"""Feature Group 9 — trust & deliverability.

What must hold:
  * health scoring reads SPF / DMARC / DKIM / bounces / listings the way the
    docs say; Spamhaus's "refused" answers are unknown, never "listed";
  * a NEW listing pauses the account's campaigns and alerts once; a low
    health score warns once and is surfaced on campaign launch;
  * an automated "reply" is stored but is not a reply: the sequence neither
    stops nor advances, nothing is counted, and ordinary replies never reach
    the model;
  * every send (and every compliance block) writes an audit row with the
    lead's region and regime, and GDPR/CASL recipients get their notice.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from app.db import models as m
from app.integrations.outreach_base import InboundMessage
from app.services import (
    compliance_audit,
    credentials,
    crypto,
    deliverability,
    reply_fraud,
    system_settings,
)
from app.workers.outreach_tasks import route_inbound_impl, send_message_impl

from .conftest import NOW, auth_headers


@pytest.fixture()
def dns(monkeypatch):
    records = {"txt": {}, "a": {}}
    monkeypatch.setattr(deliverability, "_txt", lambda name: records["txt"].get(name, []))
    monkeypatch.setattr(deliverability, "_a", lambda name: records["a"].get(name, []))
    return records


def _healthy(dns, domain="leadpilot.dev", policy="reject"):
    dns["txt"][domain] = ["v=spf1 include:_spf.google.com ~all"]
    dns["txt"][f"_dmarc.{domain}"] = [f"v=DMARC1; p={policy}; rua=mailto:d@{domain}"]
    dns["txt"][f"google._domainkey.{domain}"] = ["v=DKIM1; k=rsa; p=MIIBIjANBg"]


def _events(queued_jobs, name):
    return [kw for _, event, kw in queued_jobs["events"] if event == name]


# --------------------------------------------------------------------------
# Health and blacklists
# --------------------------------------------------------------------------


def test_dns_auth_and_scoring(dns):
    _healthy(dns)
    auth = deliverability.dns_auth("leadpilot.dev")
    assert (auth["spf"], auth["dmarc"], auth["dkim"], auth["dmarc_policy"]) == (
        True, True, True, "reject")
    assert deliverability.health_score(auth, None, False) == (100, [])

    _healthy(dns, policy="none")
    score, reasons = deliverability.health_score(deliverability.dns_auth("leadpilot.dev"),
                                                 0.05, False)
    assert score == 60 and any("p=none" in r for r in reasons) and any("5.0%" in r for r in reasons)

    bare = deliverability.dns_auth("nothing.dev")
    assert deliverability.health_score(bare, None, True)[0] == 0      # 100-25-25-15-40
    assert deliverability.health_score(bare, None, False)[0] == 35


def test_dnsbl_listing_and_refused_answers(db_session, dns):
    dns["a"]["acme.dev.dbl.spamhaus.org"] = ["127.0.1.2"]
    dns["a"]["acme.dev.multi.surbl.org"] = ["127.255.255.254"]   # resolver refused
    result = deliverability.check_blacklists(db_session, "acme.dev")
    assert result["source"] == "dnsbl"
    assert result["listed_on"] == ["dbl.spamhaus.org"]
    assert result["unknown"] == ["multi.surbl.org"]


class _FakeHttp:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params=None, headers=None):
        self.calls.append((url, params, headers))
        return self.response


def test_mxtoolbox_is_used_when_configured(db_session, monkeypatch):
    credentials.set_system_secret(db_session, "mxtoolbox", "api_key", "mx-key")
    http = _FakeHttp(httpx.Response(200, json={"Failed": [{"Name": "SORBS SPAM"}],
                                               "Passed": [{"Name": "Spamhaus"}]}))
    monkeypatch.setattr(deliverability, "_http", http)
    result = deliverability.check_blacklists(db_session, "acme.dev")
    assert result == {"source": "mxtoolbox", "listed_on": ["SORBS SPAM"], "unknown": [],
                      "checked": 2}
    assert http.calls[0][1] == {"argument": "acme.dev"}
    assert http.calls[0][2] == {"Authorization": "mx-key"}


def test_new_listing_pauses_and_alerts_once(db_session, dns, gmail_account, verified_strategy,
                                            test_user, queued_jobs):
    _healthy(dns)
    dns["a"]["leadpilot.dev.dbl.spamhaus.org"] = ["127.0.1.2"]
    first = deliverability.run_checks(db_session, test_user.id)
    assert first["domains"][0]["listed_on"] == ["dbl.spamhaus.org"]
    assert first["domains"][0]["campaigns_paused"] == 1
    db_session.refresh(verified_strategy)
    assert verified_strategy.campaign_state == deliverability.PAUSED_BLACKLIST
    assert "dbl.spamhaus.org" in verified_strategy.campaign_pause_reason
    alert = _events(queued_jobs, "domain_blacklisted")
    assert len(alert) == 1 and alert[0]["webhook_payload"]["domain"] == "leadpilot.dev"

    deliverability.run_checks(db_session, test_user.id)       # still listed
    assert len(_events(queued_jobs, "domain_blacklisted")) == 1


def test_low_health_warns_once_and_on_launch(client, db_session, dns, gmail_account,
                                             test_user, email_sequence, verified_leads,
                                             fake_claude, queued_jobs):
    deliverability.run_checks(db_session, test_user.id)       # no DNS records at all
    deliverability.run_checks(db_session, test_user.id)
    warnings = _events(queued_jobs, "deliverability_warning")
    assert len(warnings) == 1 and warnings[0]["webhook_payload"]["score"] == 35

    launched = client.post(f"/sequences/{email_sequence.id}/enroll", json={})
    assert launched.status_code == 202
    assert "35/100" in launched.json()["warning"]


def test_consumer_domains_and_admin_switch(db_session):
    user = m.User(email="solo@x.dev", email_verified=True)
    db_session.add(user)
    db_session.commit()
    db_session.add(m.GmailAccount(user_id=user.id, email_address="solo@gmail.com",
                                  token_ciphertext=crypto.encrypt_json({"access_token": "a"})))
    db_session.commit()
    assert deliverability.sending_domains(db_session, user.id) == []
    system_settings.set(db_session, "blacklist_monitoring_enabled", False)
    assert deliverability.run_all(db_session) == {"users": 0, "disabled": True}


def test_deliverability_api(client, dns, gmail_account):
    before = client.get("/deliverability").json()
    assert before["domains"][0]["domain"] == "leadpilot.dev"
    assert before["domains"][0]["health"] is None and before["threshold"] == 70
    _healthy(dns)
    after = client.post("/deliverability/check").json()
    domain = after["domains"][0]
    assert domain["health"]["score"] == 100 and domain["blacklist"]["listed_on"] == []
    assert len(domain["history"]) == 1


# --------------------------------------------------------------------------
# Reply fraud detection
# --------------------------------------------------------------------------


def test_automated_reply_detection(fake_claude):
    assert reply_fraud.is_automated("no-reply@vendor.com", "Re: hello", "Thanks!")[0]
    assert reply_fraud.is_automated("jo@acme.dev", "Automatic reply: Re: hello", "Hi")[0]
    two_weak = "We received your message. Your ticket number is 4411."
    assert reply_fraud.is_automated("help@acme.dev", "Re: hello", two_weak)[0]
    assert fake_claude.automated_reply_prompts == []          # conclusive: no model call

    one_weak = "Thank you for contacting us, happy to chat next week."
    fake_claude.automated_reply_response = {"automated": True, "reason": "canned"}
    assert reply_fraud.is_automated("jo@acme.dev", "Re: hello", one_weak) == (True, "canned")
    fake_claude.automated_reply_response = {"automated": False}
    assert reply_fraud.is_automated("jo@acme.dev", "Re: hello", one_weak) == (False, "")
    assert len(fake_claude.automated_reply_prompts) == 2

    human = "Sounds great — can we talk Thursday at 3?"
    assert reply_fraud.is_automated("jo@acme.dev", "Re: hello", human) == (False, "")
    assert len(fake_claude.automated_reply_prompts) == 2       # never asked about a person

    assert reply_fraud.second_pass("out_of_office", "no-reply@x.com", None, "") == "out_of_office"
    assert reply_fraud.second_pass("interested", "no-reply@x.com", None, "",
                                   enabled=False) == "interested"


def _send_first(db, lead, channel):
    msg = db.execute(select(m.Message).where(m.Message.lead_id == lead.id)).scalar_one()
    assert send_message_impl(db, msg.id, channel=channel, now=NOW) == "sent"
    return msg


def _inbound(lead, body, thread_ref):
    return InboundMessage(provider_message_id="in-fraud", thread_ref=thread_ref,
                          from_address=lead.email, to_address="sender@leadpilot.dev",
                          subject="Re: hello", body=body, received_at=NOW)


def test_automated_reply_is_not_a_reply(db_session, enrolled, verified_leads, fake_channel,
                                        fake_claude, gmail_account, queued_jobs):
    lead = verified_leads[0]
    msg = _send_first(db_session, lead, fake_channel)
    body = "Thanks! We received your message. Your ticket number is 4411."
    fake_claude.reply_verdicts["received your message"] = "interested"

    out = route_inbound_impl(db_session, _inbound(lead, body, msg.thread_ref), gmail_account)
    assert out == "automated_response"
    db_session.refresh(lead)
    assert lead.status is m.LeadStatus.CONTACTED
    enrollment = db_session.query(m.SequenceEnrollment).filter_by(lead_id=lead.id).one()
    assert enrollment.status is m.EnrollmentStatus.ACTIVE
    assert db_session.query(m.Outcome).filter_by(lead_id=lead.id,
                                                 event=m.OutcomeEvent.REPLIED).count() == 0
    stored = db_session.query(m.InboundReply).filter_by(lead_id=lead.id).one()
    assert stored.classification == "automated_response"
    assert _events(queued_jobs, "reply_received") == []

    system_settings.set(db_session, "reply_fraud_detection_enabled", False)
    other = verified_leads[1]
    msg2 = _send_first(db_session, other, fake_channel)
    assert route_inbound_impl(db_session, _inbound(other, body, msg2.thread_ref),
                              gmail_account) == "interested"


# --------------------------------------------------------------------------
# Region-aware compliance audit
# --------------------------------------------------------------------------


def _audit_rows(db, lead):
    return db.query(m.ComplianceAuditLog).filter_by(lead_id=lead.id).all()


def test_every_send_is_audited_with_its_regime(db_session, enrolled, verified_leads,
                                               fake_channel, gmail_account, test_user):
    eu, plain, suppressed = verified_leads
    eu.enrichment_json = {"person": {"country": "Germany"}}
    db_session.add(m.SuppressionEntry(email=suppressed.email, reason="test"))
    db_session.commit()

    eu_msg = _send_first(db_session, eu, fake_channel)
    (row,) = _audit_rows(db_session, eu)
    assert (row.decision, row.region, row.regime, row.channel) == ("sent", "eu", "GDPR", "email")
    assert row.user_id == test_user.id and row.message_id == eu_msg.id
    assert row.checks_json["unsubscribe_link"] is True
    assert row.checks_json["region_notice"] is True
    assert row.checks_json["open_tracking"] is False
    assert "legitimate interest" in eu_msg.body

    plain_msg = _send_first(db_session, plain, fake_channel)
    (row,) = _audit_rows(db_session, plain)
    assert row.region is None and row.regime is None
    assert row.checks_json["legal_basis"].startswith("unknown region")
    assert "legitimate interest" not in plain_msg.body

    msg = db_session.execute(select(m.Message).where(m.Message.lead_id == suppressed.id)
                             ).scalar_one()
    assert send_message_impl(db_session, msg.id, channel=fake_channel,
                             now=NOW) == "cancelled_suppressed"
    (row,) = _audit_rows(db_session, suppressed)
    assert row.decision == "blocked_suppressed"


def test_casl_notice_names_the_sender():
    lead = m.Lead(enrichment_json={"country": "Canada"})
    notice = compliance_audit.region_notice(lead)
    assert "unsubscribe" in notice and "123 Main St" in notice
    assert compliance_audit.region_notice(m.Lead(enrichment_json={"country": "US"})) is None


def test_compliance_api(client, db_session, enrolled, verified_leads, fake_channel,
                        gmail_account):
    lead = verified_leads[0]
    _send_first(db_session, lead, fake_channel)
    rows = client.get("/compliance/audit").json()
    assert rows[0]["decision"] == "sent" and rows[0]["lead_id"] == str(lead.id)
    summary = client.get(f"/leads/{lead.id}/compliance").json()
    assert summary["audit"][0]["channel"] == "email" and summary["open_tracking"] is True

    stranger = m.User(email="nosy@x.dev", email_verified=True)
    db_session.add(stranger)
    db_session.commit()
    assert client.get(f"/leads/{lead.id}/compliance",
                      headers=auth_headers(stranger)).status_code == 404
    assert client.get("/compliance/audit", headers=auth_headers(stranger)).json() == []

"""F03 — Deliverability Autopilot (docs/features/f03-deliverability-autopilot.md).

What must hold:
  * the preflight reads SPF / DKIM / DMARC with real pass rules and checks the
    one-click unsubscribe headers on the bytes the Gmail send path produces;
  * with the flag ON a failing preflight BLOCKS enroll, approval and resume
    (409) and records a row; with the flag OFF nothing changes and no DNS is read;
  * the send path refuses an email without both RFC 8058 headers;
  * the stepped ramp counts from the mailbox's first send and only ever lowers;
  * brakes force throttled at >= 0.10% and paused at >= 0.30%;
  * a fresh Postmaster reading replaces the proxy, labelled; the importer is
    off by default, parses Google's v2 shape, and never crosses tenants.

Offline: DNS is an injected dict, Postmaster HTTP is a fake client.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.db import models as m
from app.integrations import google_postmaster
from app.services import (
    deliverability,
    deliverability_autopilot as autopilot,
    mailbox_health,
    sequence_engine as engine,
    system_settings,
)

from .conftest import NOW, auth_headers

DOMAIN = "leadpilot.dev"


def _good(records: dict, domain: str = DOMAIN, policy: str = "reject") -> None:
    records[domain] = ["v=spf1 include:_spf.google.com ~all"]
    records[f"_dmarc.{domain}"] = [f"v=DMARC1; p={policy}; rua=mailto:d@{domain}"]
    records[f"google._domainkey.{domain}"] = ["v=DKIM1; k=rsa; p=MIIBIjANBgkqh"]


@pytest.fixture()
def dns(monkeypatch):
    """TXT records by name; every name looked up is recorded."""
    records: dict[str, list[str]] = {}
    lookups: list[str] = []

    def txt(name):
        lookups.append(name)
        return list(records.get(name, []))

    monkeypatch.setattr(deliverability, "_txt", txt)
    records_obj = type("Dns", (), {})()
    records_obj.records, records_obj.lookups, records_obj.txt = records, lookups, txt
    return records_obj


@pytest.fixture()
def https_base(monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://app.leadpilot.dev")


@pytest.fixture()
def on(db_session):
    system_settings.set(db_session, autopilot.FLAG, True)


def _events(queued_jobs, name):
    return [kw for _, event, kw in queued_jobs["events"] if event == name]


def _preflight_rows(db_session):
    return db_session.execute(select(m.DeliverabilityCheck).where(
        m.DeliverabilityCheck.kind == autopilot.PREFLIGHT_KIND)).scalars().all()


def _enrollments(db_session):
    return db_session.execute(select(func.count(m.SequenceEnrollment.id))).scalar_one()


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------


class TestFlags:
    def test_everything_is_off_by_default(self, db_session):
        assert system_settings.get(db_session, "deliverability_autopilot_enabled") is False
        assert system_settings.get(db_session, "postmaster_import_enabled") is False
        assert system_settings.get(db_session, "deliverability_dkim_selectors") == "google"
        assert autopilot.enabled(db_session) is False
        assert autopilot.import_enabled(db_session) is False

    def test_flags_are_typed(self, db_session):
        with pytest.raises(system_settings.SettingTypeError):
            system_settings.set(db_session, autopilot.FLAG, "yes")

    def test_the_import_needs_both_flags(self, db_session):
        system_settings.set(db_session, autopilot.IMPORT_FLAG, True)
        assert autopilot.import_enabled(db_session) is False
        system_settings.set(db_session, autopilot.FLAG, True)
        assert autopilot.import_enabled(db_session) is True

    def test_the_flags_are_listed_for_the_admin_panel(self, db_session):
        keys = {s["key"] for s in system_settings.all_settings(db_session)}
        assert {autopilot.FLAG, autopilot.IMPORT_FLAG, autopilot.SELECTORS_SETTING} <= keys


# --------------------------------------------------------------------------
# SPF / DKIM / DMARC
# --------------------------------------------------------------------------


class TestSpf:
    def test_a_direct_google_include_passes(self, dns):
        dns.records[DOMAIN] = ["v=spf1 include:_spf.google.com ~all"]
        assert autopilot.check_spf(DOMAIN, dns.txt)["ok"]

    def test_a_nested_include_is_followed(self, dns):
        dns.records[DOMAIN] = ["v=spf1 include:_spf.vendor.net -all"]
        dns.records["_spf.vendor.net"] = ["v=spf1 ip4:1.2.3.4 include:_spf.google.com -all"]
        assert autopilot.check_spf(DOMAIN, dns.txt)["ok"]

    def test_a_redirect_is_followed(self, dns):
        dns.records[DOMAIN] = ["v=spf1 redirect=_spf.leadpilot.dev"]
        dns.records["_spf.leadpilot.dev"] = ["v=spf1 include:_spf.google.com ~all"]
        assert autopilot.check_spf(DOMAIN, dns.txt)["ok"]

    def test_no_record_fails_with_the_fix(self, dns):
        result = autopilot.check_spf(DOMAIN, dns.txt)
        assert not result["ok"]
        assert "include:_spf.google.com" in result["detail"]

    def test_two_records_are_a_permanent_error(self, dns):
        dns.records[DOMAIN] = ["v=spf1 include:_spf.google.com ~all", "v=spf1 -all"]
        result = autopilot.check_spf(DOMAIN, dns.txt)
        assert not result["ok"] and "permanent error" in result["detail"]

    def test_a_record_that_does_not_authorise_google_fails(self, dns):
        dns.records[DOMAIN] = ["v=spf1 include:spf.protection.outlook.com -all"]
        result = autopilot.check_spf(DOMAIN, dns.txt)
        assert not result["ok"] and "does not authorise Google" in result["detail"]

    def test_a_negated_google_include_does_not_count(self, dns):
        dns.records[DOMAIN] = ["v=spf1 -include:_spf.google.com ~all"]
        assert not autopilot.check_spf(DOMAIN, dns.txt)["ok"]

    def test_more_than_ten_lookups_is_a_permerror(self, dns):
        dns.records[DOMAIN] = ["v=spf1 include:h0.example ~all"]
        for i in range(12):
            dns.records[f"h{i}.example"] = [f"v=spf1 include:h{i + 1}.example ~all"]
        dns.records["h12.example"] = ["v=spf1 include:_spf.google.com ~all"]
        result = autopilot.check_spf(DOMAIN, dns.txt)
        assert not result["ok"] and "10 DNS lookups" in result["detail"]

    def test_an_include_loop_terminates(self, dns):
        dns.records[DOMAIN] = ["v=spf1 include:a.example ~all"]
        dns.records["a.example"] = ["v=spf1 include:b.example ~all"]
        dns.records["b.example"] = ["v=spf1 include:a.example ~all"]
        assert not autopilot.check_spf(DOMAIN, dns.txt)["ok"]


class TestDkim:
    def test_the_google_selector_passes(self, dns):
        _good(dns.records)
        result = autopilot.check_dkim(DOMAIN, dns.txt, ["google"])
        assert result["ok"] and result["selector"] == "google"

    def test_a_custom_selector_from_the_setting(self, dns, db_session):
        dns.records[f"lp2026._domainkey.{DOMAIN}"] = ["v=DKIM1; p=MIIB"]
        system_settings.set(db_session, autopilot.SELECTORS_SETTING, "google, LP2026")
        selectors = autopilot.selectors_from(
            system_settings.get(db_session, autopilot.SELECTORS_SETTING))
        assert selectors == ["google", "lp2026"]
        assert autopilot.check_dkim(DOMAIN, dns.txt, selectors)["ok"]

    def test_a_revoked_key_fails(self, dns):
        dns.records[f"google._domainkey.{DOMAIN}"] = ["v=DKIM1; k=rsa; p="]
        result = autopilot.check_dkim(DOMAIN, dns.txt, ["google"])
        assert not result["ok"] and "revoked" in result["detail"]

    def test_no_key_fails_and_names_the_setting(self, dns):
        result = autopilot.check_dkim(DOMAIN, dns.txt, ["google"])
        assert not result["ok"] and "deliverability_dkim_selectors" in result["detail"]


class TestDmarc:
    def test_missing_fails(self, dns):
        result = autopilot.check_dmarc(DOMAIN, dns.txt)
        assert not result["ok"] and "_dmarc.leadpilot.dev" in result["detail"]

    def test_p_none_passes_with_a_warning(self, dns):
        dns.records[f"_dmarc.{DOMAIN}"] = ["v=DMARC1; p=none"]
        result = autopilot.check_dmarc(DOMAIN, dns.txt)
        assert result["ok"] and result["policy"] == "none" and "warning" in result

    def test_a_subdomain_falls_back_to_the_organisational_domain(self, dns):
        dns.records[f"_dmarc.{DOMAIN}"] = ["v=DMARC1; p=reject; sp=quarantine"]
        result = autopilot.check_dmarc(f"mail.{DOMAIN}", dns.txt)
        assert result["ok"] and result["found_at"] == DOMAIN
        assert result["policy"] == "quarantine"          # sp= governs subdomains

    def test_an_invalid_policy_fails(self, dns):
        dns.records[f"_dmarc.{DOMAIN}"] = ["v=DMARC1; rua=mailto:x@y"]
        assert not autopilot.check_dmarc(DOMAIN, dns.txt)["ok"]

    def test_two_records_fail(self, dns):
        dns.records[f"_dmarc.{DOMAIN}"] = ["v=DMARC1; p=reject", "v=DMARC1; p=none"]
        assert not autopilot.check_dmarc(DOMAIN, dns.txt)["ok"]


class TestAlignment:
    def test_dmarc_with_dkim_alone_aligns(self):
        result = autopilot.check_alignment({"ok": False}, {"ok": True}, {"ok": True})
        assert result["ok"] and "DKIM" in result["detail"]

    def test_no_dmarc_cannot_align(self):
        assert not autopilot.check_alignment({"ok": True}, {"ok": True}, {"ok": False})["ok"]

    def test_neither_spf_nor_dkim_cannot_align(self):
        assert not autopilot.check_alignment({"ok": False}, {"ok": False}, {"ok": True})["ok"]


# --------------------------------------------------------------------------
# One-click unsubscribe on the real send-path bytes
# --------------------------------------------------------------------------


class TestOneClick:
    def test_the_real_send_path_passes_over_https(self, https_base):
        result = autopilot.check_one_click("sender@leadpilot.dev")
        assert result["ok"], result["detail"]

    def test_an_http_base_url_fails(self, monkeypatch):
        monkeypatch.setattr(settings, "public_base_url", "http://localhost:8000")
        result = autopilot.check_one_click("sender@leadpilot.dev")
        assert not result["ok"] and "HTTPS" in result["detail"]

    def test_a_header_dropped_by_the_email_builder_fails(self, https_base, monkeypatch):
        real = engine.build_compliant_email

        def without_post(lead, subject, body):
            s, b, headers, token = real(lead, subject, body)
            headers.pop("List-Unsubscribe-Post")
            return s, b, headers, token

        monkeypatch.setattr(engine, "build_compliant_email", without_post)
        result = autopilot.check_one_click("sender@leadpilot.dev")
        assert not result["ok"] and "List-Unsubscribe-Post" in result["detail"]

    def test_the_probe_reads_what_the_mime_builder_emits(self, https_base, monkeypatch):
        from app.integrations import gmail

        real = gmail.build_mime

        def stripping(from_address, message):
            mime = real(from_address, message)
            del mime["List-Unsubscribe"]
            return mime

        monkeypatch.setattr(gmail, "build_mime", stripping)
        result = autopilot.check_one_click("sender@leadpilot.dev")
        assert not result["ok"] and "List-Unsubscribe header is missing" in result["detail"]

    def test_the_gmail_channel_sends_exactly_build_mime(self, db_session, gmail_account,
                                                          monkeypatch):
        """The refactor moved MIME assembly out of send() without changing it."""
        import base64
        import email
        import email.policy

        from app.integrations import gmail
        from app.integrations.outreach_base import OutboundMessage

        captured = {}
        channel = gmail.GmailChannel(account=gmail_account, session=db_session)
        monkeypatch.setattr(channel, "call", lambda method, path, json_body=None, **kw:
                            captured.setdefault("payload", json_body) or {"id": "x"})
        out = OutboundMessage(message_id="1", lead_id="2", to_address="a@b.com",
                              subject="Hi", body="Body",
                              headers={"List-Unsubscribe": "<https://x/unsubscribe/t>",
                                       "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"},
                              metadata={"html_body": "<p>Body</p>"})
        channel.send(out)
        sent = email.message_from_bytes(base64.urlsafe_b64decode(captured["payload"]["raw"]),
                                        policy=email.policy.default)
        assert sent["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        assert sent["From"] == "sender@leadpilot.dev"
        built = gmail.build_mime("sender@leadpilot.dev", out)

        def shape(msg):   # the multipart boundary is random; everything else is not
            return ([(k, v) for k, v in msg.items() if k != "Content-Type"],
                    [(p.get_content_type(), p.get_content()) for p in msg.iter_parts()])

        assert shape(sent) == shape(built)


# --------------------------------------------------------------------------
# The preflight report
# --------------------------------------------------------------------------


class TestPreflight:
    def test_a_good_domain_passes(self, db_session, dns, https_base, gmail_account,
                                  email_sequence, verified_strategy):
        _good(dns.records)
        report = autopilot.preflight(db_session, verified_strategy, sequence=email_sequence)
        assert report["ok"] and report["applies"] and report["blocking"] == []
        names = [c["name"] for c in report["mailboxes"][0]["checks"]]
        assert names == ["spf", "dkim", "dmarc", "alignment"]
        assert report["unsubscribe"]["ok"]

    def test_every_failure_is_named(self, db_session, dns, https_base, gmail_account,
                                    email_sequence, verified_strategy):
        report = autopilot.preflight(db_session, verified_strategy, sequence=email_sequence)
        assert not report["ok"]
        text = " ".join(report["blocking"])
        for word in ("SPF", "DKIM", "DMARC", "alignment"):
            assert word.lower() in text.lower()

    def test_a_consumer_mailbox_is_provider_managed_and_not_looked_up(
            self, db_session, dns, https_base, gmail_account, email_sequence,
            verified_strategy):
        gmail_account.email_address = "founder@gmail.com"
        db_session.commit()
        report = autopilot.preflight(db_session, verified_strategy, sequence=email_sequence)
        assert report["ok"] and report["mailboxes"][0]["provider_managed"]
        assert dns.lookups == []

    def test_no_mailbox_blocks(self, db_session, dns, https_base, email_sequence,
                               verified_strategy):
        report = autopilot.preflight(db_session, verified_strategy, sequence=email_sequence)
        assert not report["ok"] and "No Gmail mailbox" in report["blocking"][0]

    def test_a_campaign_without_email_is_not_checked(self, db_session, dns,
                                                     verified_strategy):
        seq = m.Sequence(strategy_id=verified_strategy.id, channel=m.ChannelType.LINKEDIN,
                         name="li", status=m.SequenceStatus.DRAFT)
        db_session.add(seq)
        db_session.flush()
        db_session.add(m.SequenceStep(sequence_id=seq.id, step_no=1, template="t"))
        db_session.commit()
        report = autopilot.preflight(db_session, verified_strategy, sequence=seq)
        assert report == {**report, "ok": True, "applies": False}
        assert dns.lookups == []

    def test_an_email_step_inside_another_channel_is_checked(self, db_session, dns,
                                                             verified_strategy):
        seq = m.Sequence(strategy_id=verified_strategy.id, channel=m.ChannelType.LINKEDIN,
                         name="mixed", status=m.SequenceStatus.DRAFT)
        db_session.add(seq)
        db_session.flush()
        db_session.add(m.SequenceStep(sequence_id=seq.id, step_no=1, template="t"))
        db_session.add(m.SequenceStep(sequence_id=seq.id, step_no=2, template="t",
                                      channel=m.ChannelType.EMAIL))
        db_session.commit()
        assert autopilot.sequence_sends_email(db_session, seq)


# --------------------------------------------------------------------------
# The launch block (API) -- a safety guard
# --------------------------------------------------------------------------


class TestLaunchBlock:
    def test_flag_off_launches_exactly_as_before_without_dns(
            self, client, db_session, dns, gmail_account, email_sequence, verified_leads,
            fake_claude):
        response = client.post(f"/sequences/{email_sequence.id}/enroll", json={})
        assert response.status_code == 202
        assert response.json()["enrolled"] == 3
        assert dns.lookups == []
        assert _preflight_rows(db_session) == []

    def test_failing_auth_blocks_enroll_and_enrols_nobody(
            self, client, db_session, on, dns, https_base, gmail_account, email_sequence,
            verified_leads, fake_claude):
        response = client.post(f"/sequences/{email_sequence.id}/enroll", json={})
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert isinstance(detail, str)
        assert detail.startswith("Deliverability preflight failed") and "SPF" in detail
        assert _enrollments(db_session) == 0
        rows = _preflight_rows(db_session)
        assert len(rows) == 1 and rows[0].ok is False and rows[0].domain == DOMAIN
        assert rows[0].details_json["action"] == "enroll"
        assert rows[0].details_json["sequence_id"] == str(email_sequence.id)

    def test_missing_one_click_headers_block_even_with_good_dns(
            self, client, db_session, on, dns, gmail_account, email_sequence,
            verified_leads, fake_claude, monkeypatch):
        _good(dns.records)
        monkeypatch.setattr(settings, "public_base_url", "http://localhost:8000")
        response = client.post(f"/sequences/{email_sequence.id}/enroll", json={})
        assert response.status_code == 409
        assert "One-click unsubscribe" in response.json()["detail"]

    def test_passing_preflight_launches_and_is_recorded(
            self, client, db_session, on, dns, https_base, gmail_account, email_sequence,
            verified_leads, fake_claude):
        _good(dns.records)
        response = client.post(f"/sequences/{email_sequence.id}/enroll", json={})
        assert response.status_code == 202 and response.json()["enrolled"] == 3
        rows = _preflight_rows(db_session)
        assert len(rows) == 1 and rows[0].ok is True

    def test_approval_is_blocked_too(self, client, db_session, on, dns, https_base,
                                     gmail_account, email_sequence, verified_leads,
                                     fake_claude):
        email_sequence.status = m.SequenceStatus.PENDING_APPROVAL
        db_session.commit()
        response = client.post(f"/sequences/{email_sequence.id}/approve", json={})
        assert response.status_code == 409
        db_session.refresh(email_sequence)
        assert email_sequence.status is m.SequenceStatus.PENDING_APPROVAL
        assert _enrollments(db_session) == 0

    def test_resume_is_blocked_too(self, client, db_session, on, dns, https_base,
                                   gmail_account, email_sequence, verified_strategy):
        verified_strategy.campaign_state = "paused_manual"
        db_session.commit()
        response = client.post(f"/strategies/{verified_strategy.id}/campaign/resume")
        assert response.status_code == 409
        db_session.refresh(verified_strategy)
        assert verified_strategy.campaign_state == "paused_manual"
        assert _preflight_rows(db_session)[0].details_json["action"] == "resume"

    def test_resume_with_the_flag_off_is_unchanged(self, client, db_session, dns,
                                                   gmail_account, email_sequence,
                                                   verified_strategy):
        verified_strategy.campaign_state = "paused_manual"
        db_session.commit()
        response = client.post(f"/strategies/{verified_strategy.id}/campaign/resume")
        assert response.status_code == 200
        assert response.json()["campaign_state"] == "active"
        assert dns.lookups == []

    def test_a_crashing_preflight_fails_closed(self, client, db_session, on,
                                               gmail_account, email_sequence,
                                               verified_leads, fake_claude, monkeypatch):
        def boom(*a, **kw):
            raise RuntimeError("resolver exploded")

        monkeypatch.setattr(autopilot, "preflight", boom)
        response = client.post(f"/sequences/{email_sequence.id}/enroll", json={})
        assert response.status_code == 409
        assert "could not run" in response.json()["detail"]
        assert _enrollments(db_session) == 0


class TestPreflightEndpoint:
    def test_flag_off_reports_disabled_without_dns(self, client, dns, gmail_account,
                                                   email_sequence):
        response = client.get("/deliverability/preflight",
                              params={"sequence_id": str(email_sequence.id)})
        assert response.status_code == 200
        assert response.json() == {"enabled": False}
        assert dns.lookups == []

    def test_flag_on_returns_the_report_and_records_nothing(
            self, client, db_session, on, dns, https_base, gmail_account, email_sequence):
        _good(dns.records)
        body = client.get("/deliverability/preflight",
                          params={"sequence_id": str(email_sequence.id)}).json()
        assert body["enabled"] and body["ok"]
        assert body["mailboxes"][0]["address"] == "sender@leadpilot.dev"
        assert _preflight_rows(db_session) == []

    def test_another_accounts_sequence_is_not_found(self, client, db_session, on, dns):
        other = m.User(email="other-f03@test.dev", email_verified=True)
        db_session.add(other)
        db_session.flush()
        product = m.Product(user_id=other.id, name="Other", description="x",
                            type=m.ProductType.SKILL)
        db_session.add(product)
        db_session.flush()
        strategy = m.Strategy(product_id=product.id, status=m.StrategyStatus.VERIFIED,
                              flow_type=list(m.FlowType)[0])
        db_session.add(strategy)
        db_session.flush()
        seq = m.Sequence(strategy_id=strategy.id, channel=m.ChannelType.EMAIL, name="theirs",
                         status=m.SequenceStatus.DRAFT)
        db_session.add(seq)
        db_session.commit()
        response = client.get("/deliverability/preflight",
                              params={"sequence_id": str(seq.id)})
        assert response.status_code == 404
        assert dns.lookups == []


# --------------------------------------------------------------------------
# Send-time header guard
# --------------------------------------------------------------------------


def _drop_headers(monkeypatch):
    real = engine.build_compliant_email

    def without(lead, subject, body):
        s, b, _headers, token = real(lead, subject, body)
        return s, b, {}, token

    monkeypatch.setattr(engine, "build_compliant_email", without)


class TestSendTimeGuard:
    def _scheduled(self, db_session):
        return db_session.query(m.Message).filter_by(status=m.MessageStatus.SCHEDULED).first()

    def test_an_email_without_the_headers_never_sends(self, db_session, on, enrolled,
                                                       fake_channel, monkeypatch):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        _drop_headers(monkeypatch)
        message = self._scheduled(db_session)
        result = outreach_tasks.send_message_impl(db_session, message.id, now=NOW)
        db_session.refresh(message)
        assert result == "blocked_compliance"
        assert message.status is m.MessageStatus.FAILED
        assert "one-click unsubscribe" in message.error
        assert fake_channel.sent == []

    def test_flag_off_the_guard_is_not_applied(self, db_session, enrolled, fake_channel,
                                               monkeypatch):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        _drop_headers(monkeypatch)
        message = self._scheduled(db_session)
        assert outreach_tasks.send_message_impl(db_session, message.id, now=NOW) == "sent"

    def test_a_normal_email_still_sends_with_the_headers(self, db_session, on, enrolled,
                                                          fake_channel, monkeypatch):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        message = self._scheduled(db_session)
        # A year-old mailbox that has never sent starts the stepped ramp at
        # day 0 -- 10 a day -- which still lets this first send through.
        assert outreach_tasks.send_message_impl(db_session, message.id, now=NOW) == "sent"
        headers = fake_channel.sent[0].headers
        assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"

    def test_the_guard_function(self):
        from app.core.exceptions import ComplianceError

        autopilot.require_one_click_headers({
            "List-Unsubscribe": "<https://x>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})
        with pytest.raises(ComplianceError):
            autopilot.require_one_click_headers({"List-Unsubscribe": "<https://x>"})
        with pytest.raises(ComplianceError):
            autopilot.require_one_click_headers(None)


# --------------------------------------------------------------------------
# Stepped new-mailbox ramp
# --------------------------------------------------------------------------


def _sent_from(db_session, sequence, lead, ref, when, n=1):
    for _ in range(n):
        db_session.add(m.Message(sequence_id=sequence.id, lead_id=lead.id,
                                 channel=m.ChannelType.EMAIL, step_no=1, template="t",
                                 status=m.MessageStatus.SENT, sent_at=when, sender_ref=ref))
    db_session.commit()


class TestRamp:
    @pytest.mark.parametrize("days,ceiling", [(0, 10), (6, 10), (7, 20), (13, 20), (14, 30),
                                              (21, 40), (27, 40), (28, None), (400, None)])
    def test_the_schedule(self, days, ceiling):
        assert engine.ramp_ceiling(days) == ceiling

    def test_unstepped_is_the_old_formula(self, gmail_account):
        day = NOW.date()
        assert engine.daily_allowance(gmail_account, day) == settings.gmail_daily_cap
        assert engine.daily_allowance(gmail_account, day, stepped=False,
                                      first_sent_on=day) == settings.gmail_daily_cap

    def test_a_mailbox_that_never_sent_is_new_however_old_it_is(self, gmail_account):
        assert engine.daily_allowance(gmail_account, NOW.date(), stepped=True) == 10

    def test_the_step_counts_from_the_first_send(self, gmail_account):
        first = NOW.date() - timedelta(days=10)
        assert engine.daily_allowance(gmail_account, NOW.date(), stepped=True,
                                      first_sent_on=first) == 20

    def test_the_step_never_raises_a_lower_cap(self, gmail_account):
        assert engine.daily_allowance(gmail_account, NOW.date(), 5, stepped=True) == 5

    def test_the_step_never_raises_the_linear_ramp(self, db_session, gmail_account):
        gmail_account.created_at = NOW            # linear ramp day 0 = 10
        db_session.commit()
        first = NOW.date() - timedelta(days=60)   # graduated from the steps
        assert engine.daily_allowance(gmail_account, NOW.date(), stepped=True,
                                      first_sent_on=first) == settings.gmail_warmup_start_sends

    def test_first_send_date(self, db_session, email_sequence, verified_leads,
                             gmail_account):
        ref = str(gmail_account.id)
        assert engine.first_send_date(db_session, ref) is None
        _sent_from(db_session, email_sequence, verified_leads[0], ref,
                   NOW - timedelta(days=9))
        _sent_from(db_session, email_sequence, verified_leads[0], ref, NOW)
        _sent_from(db_session, email_sequence, verified_leads[0], "other-ref",
                   NOW - timedelta(days=90))
        assert engine.first_send_date(db_session, ref) == (NOW - timedelta(days=9)).date()

    def test_the_send_path_enforces_the_step(self, db_session, on, enrolled,
                                             verified_leads, gmail_account, fake_channel,
                                             monkeypatch):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        _sent_from(db_session, enrolled, verified_leads[0], str(gmail_account.id),
                   NOW - timedelta(hours=1), n=10)
        message = db_session.query(m.Message).filter_by(
            status=m.MessageStatus.SCHEDULED).first()
        assert outreach_tasks.send_message_impl(db_session, message.id, now=NOW) \
            == "deferred_cap"
        db_session.refresh(message)
        assert message.status is m.MessageStatus.SCHEDULED       # deferred, not dropped
        assert fake_channel.sent == []

    def test_flag_off_the_same_mailbox_keeps_sending(self, db_session, enrolled,
                                                     verified_leads, gmail_account,
                                                     fake_channel, monkeypatch):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        _sent_from(db_session, enrolled, verified_leads[0], str(gmail_account.id),
                   NOW - timedelta(hours=1), n=10)
        message = db_session.query(m.Message).filter_by(
            status=m.MessageStatus.SCHEDULED).first()
        assert outreach_tasks.send_message_impl(db_session, message.id, now=NOW) == "sent"

    def test_the_campaign_page_shows_the_enforced_cap(self, client, db_session, on,
                                                      gmail_account, verified_strategy):
        body = client.get(f"/strategies/{verified_strategy.id}/campaign").json()
        assert body["daily_cap_today"] == 10


# --------------------------------------------------------------------------
# Brakes
# --------------------------------------------------------------------------


class TestBrakes:
    @pytest.mark.parametrize("rate,brake", [
        (None, None), (0.0, None), (0.00099, None), (0.001, mailbox_health.THROTTLED),
        (0.0029, mailbox_health.THROTTLED), (0.003, mailbox_health.PAUSED),
        (0.05, mailbox_health.PAUSED)])
    def test_thresholds(self, rate, brake):
        assert autopilot.brake_for(rate) == brake

    def test_a_brake_never_improves_a_state(self):
        assert autopilot.apply_brake(mailbox_health.PAUSED,
                                     mailbox_health.THROTTLED) == mailbox_health.PAUSED
        assert autopilot.apply_brake(mailbox_health.HEALTHY, None) == mailbox_health.HEALTHY
        assert autopilot.apply_brake(mailbox_health.HEALTHY,
                                     mailbox_health.PAUSED) == mailbox_health.PAUSED

    def test_the_thresholds_are_mailbox_healths(self):
        assert autopilot.SPAM_WARN == mailbox_health.COMPLAINT_WARN == 0.001
        assert autopilot.SPAM_BAD == mailbox_health.COMPLAINT_BAD == 0.003


def _postmaster_row(db_session, user_id, rate, day, domain=DOMAIN):
    db_session.add(m.DeliverabilityCheck(
        user_id=user_id, domain=domain, kind=autopilot.POSTMASTER_KIND,
        source="google_postmaster", ok=rate < 0.001,
        details_json={"spam_rate": rate, "day": day.isoformat(), "unit": "ratio"},
        checked_at=NOW))
    db_session.commit()


@pytest.fixture()
def no_dns_health(monkeypatch):
    monkeypatch.setattr(deliverability, "dns_auth", lambda domain: {
        "spf": True, "dkim": True, "dmarc": True, "dmarc_policy": "reject"})


class TestRefreshWithAutopilot:
    def _row(self, db_session, gmail_account):
        return db_session.execute(select(m.MailboxHealth).where(
            m.MailboxHealth.mailbox_ref == str(gmail_account.id))).scalar_one()

    def test_postmaster_replaces_the_proxy_and_is_labelled(
            self, client, db_session, on, no_dns_health, test_user, gmail_account):
        _postmaster_row(db_session, test_user.id, 0.0004, NOW.date() - timedelta(days=1))
        out = mailbox_health.refresh(db_session, test_user.id, now=NOW)
        assert out[0]["complaint_rate"] == 0.0004
        assert out[0]["complaint_source"] == "postmaster"
        row = self._row(db_session, gmail_account)
        assert row.complaint_source == "postmaster"
        api = client.get("/deliverability/mailboxes").json()["mailboxes"][0]
        assert api["complaint_source"] == "postmaster"

    def test_flag_off_ignores_postmaster_and_stores_nothing_new(
            self, db_session, no_dns_health, test_user, gmail_account):
        _postmaster_row(db_session, test_user.id, 0.02, NOW.date() - timedelta(days=1))
        out = mailbox_health.refresh(db_session, test_user.id, now=NOW)
        row = self._row(db_session, gmail_account)
        assert out[0]["complaint_source"] == "proxy"
        assert row.complaint_source is None
        assert row.complaint_rate is None and row.state == mailbox_health.HEALTHY

    def test_a_stale_reading_falls_back_to_the_proxy(
            self, db_session, on, no_dns_health, test_user, gmail_account):
        _postmaster_row(db_session, test_user.id, 0.02, NOW.date() - timedelta(days=10))
        out = mailbox_health.refresh(db_session, test_user.id, now=NOW)
        assert out[0]["complaint_source"] == "proxy"
        assert self._row(db_session, gmail_account).state == mailbox_health.HEALTHY

    def test_another_accounts_reading_never_applies(
            self, db_session, on, no_dns_health, test_user, gmail_account):
        other = m.User(email="pm-other@test.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        _postmaster_row(db_session, other.id, 0.02, NOW.date())
        out = mailbox_health.refresh(db_session, test_user.id, now=NOW)
        assert out[0]["complaint_source"] == "proxy"
        assert self._row(db_session, gmail_account).state == mailbox_health.HEALTHY

    def test_the_warn_brake_throttles_whatever_the_score(
            self, db_session, on, no_dns_health, test_user, gmail_account, queued_jobs,
            monkeypatch):
        monkeypatch.setattr(mailbox_health, "score_for", lambda *a, **kw: (100, []))
        _postmaster_row(db_session, test_user.id, 0.0012, NOW.date())
        mailbox_health.refresh(db_session, test_user.id, now=NOW)
        row = self._row(db_session, gmail_account)
        assert row.state == mailbox_health.THROTTLED and row.throttle_cap is not None
        assert "brake" in row.reason
        warnings = _events(queued_jobs, "deliverability_warning")
        assert len(warnings) == 1
        assert warnings[0]["webhook_payload"]["complaint_source"] == "postmaster"
        mailbox_health.refresh(db_session, test_user.id, now=NOW)       # no repeat
        assert len(_events(queued_jobs, "deliverability_warning")) == 1

    def test_flag_off_the_same_score_stays_healthy(
            self, db_session, no_dns_health, test_user, gmail_account, monkeypatch):
        monkeypatch.setattr(mailbox_health, "score_for", lambda *a, **kw: (100, []))
        _postmaster_row(db_session, test_user.id, 0.0012, NOW.date())
        mailbox_health.refresh(db_session, test_user.id, now=NOW)
        assert self._row(db_session, gmail_account).state == mailbox_health.HEALTHY

    def test_the_danger_brake_pauses_and_the_send_path_defers(
            self, db_session, on, no_dns_health, test_user, enrolled, gmail_account,
            fake_channel, queued_jobs, monkeypatch):
        from app.workers import outreach_tasks

        monkeypatch.setattr(mailbox_health, "score_for", lambda *a, **kw: (100, []))
        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        _postmaster_row(db_session, test_user.id, 0.004, NOW.date())
        mailbox_health.refresh(db_session, test_user.id, now=NOW)
        assert self._row(db_session, gmail_account).state == mailbox_health.PAUSED
        assert len(_events(queued_jobs, "mailbox_paused")) == 1
        message = db_session.query(m.Message).filter_by(
            status=m.MessageStatus.SCHEDULED).first()
        assert outreach_tasks.send_message_impl(db_session, message.id, now=NOW) \
            == "deferred_mailbox_paused"
        assert fake_channel.sent == []

    def test_a_consumer_mailbox_never_reads_postmaster(
            self, db_session, on, no_dns_health, test_user, gmail_account):
        gmail_account.email_address = "founder@gmail.com"
        db_session.commit()
        _postmaster_row(db_session, test_user.id, 0.02, NOW.date(), domain="gmail.com")
        out = mailbox_health.refresh(db_session, test_user.id, now=NOW)
        assert out[0]["complaint_source"] == "proxy"

    def test_the_brake_reason_names_the_source(self):
        _score, reasons = mailbox_health.score_for(
            {"spf": True, "dkim": True, "dmarc": True}, 0.004, None,
            {"spike": False}, "Gmail spam rate (Google Postmaster)")
        assert reasons[0].startswith("Gmail spam rate (Google Postmaster) 0.40%")


# --------------------------------------------------------------------------
# Google Postmaster adapter (fake HTTP -- never a real call)
# --------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


class FakeHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, json=None, headers=None):
        self.requests.append({"url": url, "json": dict(json or {}), "headers": headers})
        return self.responses.pop(0)


def _stat(day: date, value: dict, metric="spam_rate"):
    return {"date": {"year": day.year, "month": day.month, "day": day.day},
            "metric": metric, "value": value}


class TestPostmasterAdapter:
    def test_the_v2_request_and_pagination(self, monkeypatch):
        d1, d2 = date(2026, 8, 9), date(2026, 8, 10)
        http = FakeHttp([
            FakeResponse(200, {"domainStats": [_stat(d1, {"doubleValue": 0.0004})],
                               "nextPageToken": "p2"}),
            FakeResponse(200, {"domainStats": [_stat(d2, {"intValue": "0"})]}),
        ])
        monkeypatch.setattr(google_postmaster, "_http", lambda: http)
        source = google_postmaster.GooglePostmasterV2(lambda: "tok")
        readings = source.daily_spam_rates(DOMAIN, date(2026, 8, 4), d2)
        assert [(r.day, r.spam_rate) for r in readings] == [(d1, 0.0004), (d2, 0.0)]
        first, second = http.requests
        assert first["url"] == ("https://gmailpostmastertools.googleapis.com/v2/"
                                "domains/leadpilot.dev/domainStats:query")
        assert first["headers"]["Authorization"] == "Bearer tok"
        assert first["json"]["metricDefinitions"] == [
            {"name": "spam_rate", "baseMetric": {"standardMetric": "SPAM_RATE"}}]
        assert first["json"]["timeQuery"] == {"dateRanges": {"dateRanges": [
            {"start": {"year": 2026, "month": 8, "day": 4},
             "end": {"year": 2026, "month": 8, "day": 10}}]}}
        assert first["json"]["aggregationGranularity"] == "DAILY"
        assert "pageToken" not in first["json"] and second["json"]["pageToken"] == "p2"

    def test_permission_denied_is_a_postmaster_error(self, monkeypatch):
        monkeypatch.setattr(google_postmaster, "_http",
                            lambda: FakeHttp([FakeResponse(403, {})]))
        source = google_postmaster.GooglePostmasterV2(lambda: "tok")
        with pytest.raises(google_postmaster.PostmasterError, match="not verified"):
            source.daily_spam_rates(DOMAIN, date(2026, 8, 4), date(2026, 8, 10))

    def test_parsing_is_tolerant_and_rejects_impossible_ratios(self):
        d = date(2026, 8, 10)
        readings = google_postmaster.parse_response(DOMAIN, {"domainStats": [
            _stat(d, {"doubleValue": 0.002}),
            _stat(d, {"floatValue": 1.7}),                 # not a ratio: dropped
            _stat(d, {"stringValue": "n/a"}),
            {"date": {"year": 2026}, "metric": "spam_rate", "value": {"doubleValue": 0.1}},
            _stat(d, {"doubleValue": 0.5}, metric="something_else"),
        ]})
        assert [(r.day, r.spam_rate) for r in readings] == [(d, 0.002)]

    def test_the_scope_and_unit_are_the_documented_ones(self):
        assert google_postmaster.SCOPE == \
            "https://www.googleapis.com/auth/postmaster.traffic.readonly"
        assert google_postmaster.SPAM_RATE_UNIT == "ratio"

    def test_no_grant_no_source(self, db_session, test_user):
        assert google_postmaster.get_source(db_session, test_user.id) is None

    def test_a_grant_is_exchanged_with_the_google_oauth_app(self, db_session, test_user,
                                                           monkeypatch):
        from app.integrations import gmail
        from app.integrations.token_store import TokenStore

        TokenStore.set(db_session, user_id=test_user.id, provider="google_postmaster",
                       key="refresh_token", value="rt-pm")
        refreshed = []

        class FakeOAuth:
            def refresh(self, token):
                refreshed.append(token)
                return {"access_token": "fresh"}

        monkeypatch.setattr(gmail, "get_oauth", lambda: FakeOAuth())
        http = FakeHttp([FakeResponse(200, {"domainStats": []})])
        monkeypatch.setattr(google_postmaster, "_http", lambda: http)
        source = google_postmaster.get_source(db_session, test_user.id)
        source.daily_spam_rates(DOMAIN, date(2026, 8, 4), date(2026, 8, 10))
        assert refreshed == ["rt-pm"]
        assert http.requests[0]["headers"]["Authorization"] == "Bearer fresh"

    def test_a_system_credential_is_never_used_for_a_users_domain(self, db_session,
                                                                 test_user):
        from app.integrations.token_store import TokenStore

        TokenStore.set(db_session, user_id=None, provider="google_postmaster",
                       key="refresh_token", value="deployment-wide")
        assert google_postmaster.get_source(db_session, test_user.id) is None


class FakeSource:
    def __init__(self, readings=None, error=None):
        self.readings = readings or []
        self.error = error
        self.asked = []

    def daily_spam_rates(self, domain, start, end):
        self.asked.append((domain, start, end))
        if self.error:
            raise self.error
        return [r for r in self.readings if r.domain == domain]


class TestImporter:
    def test_disabled_by_default(self, db_session, gmail_account):
        assert autopilot.import_all(db_session, now=NOW) == {"disabled": True, "users": 0}

    def test_disabled_with_only_the_autopilot(self, db_session, on, gmail_account):
        assert autopilot.import_all(db_session, now=NOW)["disabled"] is True

    def test_no_grant_is_reported_not_raised(self, db_session, on, test_user,
                                             gmail_account):
        system_settings.set(db_session, autopilot.IMPORT_FLAG, True)
        assert autopilot.import_all(db_session, now=NOW) == {
            "users": 1, "connected": 0, "failed": 0}

    def test_the_latest_day_is_stored_and_brakes_apply_today(
            self, db_session, on, no_dns_health, test_user, gmail_account, queued_jobs):
        source = FakeSource([
            google_postmaster.SpamReading(DOMAIN, NOW.date() - timedelta(days=3), 0.0001),
            google_postmaster.SpamReading(DOMAIN, NOW.date() - timedelta(days=1), 0.004),
        ])
        result = autopilot.import_spam_rates(db_session, test_user.id, now=NOW,
                                             source=source)
        assert result["domains"][0]["reading"]["spam_rate"] == 0.004
        assert source.asked == [(DOMAIN, NOW.date() - timedelta(days=7), NOW.date())]
        row = db_session.execute(select(m.DeliverabilityCheck).where(
            m.DeliverabilityCheck.kind == "postmaster")).scalar_one()
        assert row.user_id == test_user.id and row.ok is False
        assert row.details_json["day"] == (NOW.date() - timedelta(days=1)).isoformat()
        assert len(row.details_json["readings"]) == 2
        health = db_session.execute(select(m.MailboxHealth)).scalar_one()
        assert health.state == mailbox_health.PAUSED
        assert health.complaint_source == "postmaster"

    def test_an_api_error_keeps_the_proxy(self, db_session, on, test_user, gmail_account):
        source = FakeSource(error=google_postmaster.PostmasterError("HTTP 403"))
        result = autopilot.import_spam_rates(db_session, test_user.id, now=NOW,
                                             source=source)
        assert "403" in result["domains"][0]["error"]
        assert db_session.execute(select(func.count(m.DeliverabilityCheck.id))).scalar_one() == 0

    def test_only_the_users_own_domains_are_queried(self, db_session, on, test_user,
                                                    gmail_account):
        other = m.User(email="pm-tenant@test.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        from app.services import crypto
        db_session.add(m.GmailAccount(user_id=other.id, email_address="x@theirs.example",
                                      token_ciphertext=crypto.encrypt_json({"a": "b"})))
        db_session.commit()
        source = FakeSource()
        autopilot.import_spam_rates(db_session, test_user.id, now=NOW, source=source)
        assert [d for d, _, _ in source.asked] == [DOMAIN]

    def test_the_task_and_its_schedule_exist(self):
        from app.workers import deliverability_tasks  # noqa: F401
        from app.workers.celery_app import celery_app

        celery_app.loader.import_default_modules()
        name = "app.workers.deliverability_tasks.import_postmaster_spam_rates"
        assert name in celery_app.tasks
        entry = celery_app.conf.beat_schedule["import-postmaster-spam-rates"]
        assert entry["task"] == name

    def test_the_task_is_a_no_op_with_the_flags_off(self, db_session, monkeypatch):
        from app.workers import deliverability_tasks

        monkeypatch.setattr(deliverability_tasks, "SessionLocal", lambda: db_session)
        monkeypatch.setattr(db_session, "close", lambda: None)
        assert deliverability_tasks.import_postmaster_spam_rates() == {
            "disabled": True, "users": 0}


# --------------------------------------------------------------------------
# The success metric is a query
# --------------------------------------------------------------------------


def test_zero_launches_with_failing_auth_is_measurable(client, db_session, on, dns,
                                                       https_base, gmail_account,
                                                       email_sequence, verified_leads,
                                                       fake_claude):
    """Every gated launch leaves a preflight row, pass or fail, and a failing
    one is never followed by enrolment until a passing one exists -- so the
    metric is a read-only query over deliverability_checks + enrolments."""
    client.post(f"/sequences/{email_sequence.id}/enroll", json={})       # blocked
    assert [r.ok for r in _preflight_rows(db_session)] == [False]
    assert _enrollments(db_session) == 0
    _good(dns.records)
    client.post(f"/sequences/{email_sequence.id}/enroll", json={})       # passes
    rows = sorted(_preflight_rows(db_session), key=lambda r: r.checked_at)
    assert [r.ok for r in rows] == [False, True]
    assert all(r.details_json["sequence_id"] == str(email_sequence.id) for r in rows)
    assert _enrollments(db_session) == 3

"""One-click unsubscribe headers survive MIME assembly RAW -- a SAFETY guard.

gaps-sweep-2 review (HIGH, pre-existing): build_mime used the default email
policy (max_line_length 78). The List-Unsubscribe value -- an https URL with a
~200-character encrypted token -- has no folding point, so it went out RFC
2047 encoded and folded:

    List-Unsubscribe: =?utf-8?q?=3Chttps=3A//...?=
     =?utf-8?q?...?=

RFC 2369 / RFC 8058 require the <URI> itself; receivers cannot use an encoded
word, so one-click unsubscribe (Gmail / Yahoo bulk-sender rules) was likely
not recognised on any message. The F03 launch preflight parsed (decoded) the
headers and so passed. Every assertion here is on the TRANSMITTED BYTES.

Own file so it can be sealed (evals/compliance_testset.yaml is the
orchestrator's to change). Every test fails on d5da447 except the controls.
"""

from __future__ import annotations

import base64
import email
import email.policy
import uuid

import pytest

from app.config import settings
from app.db import models as m
from app.integrations import gmail
from app.core.mime_policy import raw_header_lines, raw_header_value
from app.integrations.outreach_base import OutboundMessage
from app.services import deliverability_autopilot as autopilot
from app.services import sequence_engine as engine

POST = "List-Unsubscribe=One-Click"
#: A realistic Microsoft 365 Message-ID (83 characters).
M365_ID = ("<PH0PR11MB5880A1B2C3D4E5F60718293A4B5C6D7E@PH0PR11MB5880.namprd11.prod."
           "outlook.com>")


@pytest.fixture(autouse=True)
def https_base(monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://api.calendarharvest.com")


def _compliant(address="sara.khan-operations@acme-fire-protection.example"):
    lead = m.Lead(id=uuid.uuid4(), email=address, enrichment_json={})
    subject, body, headers, _token = engine.build_compliant_email(lead, "Quick question",
                                                                  "Hi Sara")
    return OutboundMessage(message_id="1", lead_id=str(lead.id), to_address=lead.email,
                           subject=subject, body=body, headers=headers,
                           metadata={"html_body": "<p>Hi Sara</p>"}), headers


def _head(raw: bytes) -> str:
    return raw.replace(b"\r\n", b"\n").split(b"\n\n", 1)[0].decode("ascii", "replace")


class TestTheSendPathBytes:
    def test_the_real_token_is_long(self):
        _out, headers = _compliant()
        assert len(headers["List-Unsubscribe"]) >= 228

    def test_list_unsubscribe_is_transmitted_raw_and_intact(self):
        out, headers = _compliant()
        raw = gmail.build_mime("sender@leadpilot.dev", out).as_bytes()
        assert "=?" not in "".join(sum(raw_header_lines(raw, "List-Unsubscribe"), []))
        assert raw_header_value(raw, "List-Unsubscribe") == headers["List-Unsubscribe"]
        assert raw_header_value(raw, "List-Unsubscribe-Post") == POST

    def test_the_bytes_the_gmail_channel_posts_carry_them(self, db_session, gmail_account,
                                                          monkeypatch):
        out, headers = _compliant()
        captured = {}
        channel = gmail.GmailChannel(account=gmail_account, session=db_session)
        monkeypatch.setattr(channel, "call", lambda method, path, json_body=None, **kw:
                            captured.setdefault("payload", json_body) or {"id": "x"})
        channel.send(out)
        raw = base64.urlsafe_b64decode(captured["payload"]["raw"])
        assert "=?utf-8?q?=3Chttps" not in _head(raw)
        assert raw_header_value(raw, "List-Unsubscribe") == headers["List-Unsubscribe"]
        assert raw_header_value(raw, "List-Unsubscribe-Post") == POST

    def test_a_synthetic_long_uri_is_not_folded(self):
        uri = "<https://api.calendarharvest.com/unsubscribe/" + "gAAAAA" + "z" * 230 + ">"
        out = OutboundMessage(message_id="1", lead_id="2", to_address="a@b.com",
                              subject="Hi", body="Body",
                              headers={"List-Unsubscribe": uri, "List-Unsubscribe-Post": POST})
        raw = gmail.build_mime("me@x.test", out).as_bytes()
        assert raw_header_value(raw, "List-Unsubscribe") == uri

    def test_control_non_ascii_subject_is_still_encoded(self):
        out = OutboundMessage(message_id="1", lead_id="2", to_address="a@b.com",
                              subject="Grüße aus Köln", body="Body", headers={})
        raw = gmail.build_mime("me@x.test", out).as_bytes()
        assert "=?utf-8?" in _head(raw)
        parsed = email.message_from_bytes(raw, policy=email.policy.default)
        assert parsed["Subject"] == "Grüße aus Köln"


class TestPreflightReadsTheRawBytes:
    def test_the_real_send_path_passes(self):
        result = autopilot.check_one_click("sender@leadpilot.dev")
        assert result["ok"], result["detail"]

    def test_an_encoded_list_unsubscribe_fails_the_preflight(self, monkeypatch):
        """What d5da447 shipped: the default policy. The parsed header looked
        fine, so the old preflight passed it."""
        from email.message import EmailMessage

        def default_policy_mime(from_address, message):
            mime = EmailMessage()
            mime["From"] = from_address or "me"
            mime["To"] = message.to_address
            mime["Subject"] = message.subject
            for name, value in (message.headers or {}).items():
                mime[name] = value
            mime.set_content(message.body)
            return mime

        monkeypatch.setattr(gmail, "build_mime", default_policy_mime)
        result = autopilot.check_one_click("sender@leadpilot.dev")
        assert not result["ok"]
        assert "RFC 2047 encoded" in result["detail"] or "folded" in result["detail"]


class TestThreadingHeadersRaw:
    def test_a_long_m365_message_id_is_transmitted_raw(self):
        from app.services import email_threading

        assert len(M365_ID) == 83
        headers = email_threading.reply_headers(M365_ID, "<first@leadpilot.dev>")
        out = OutboundMessage(message_id="1", lead_id="2", to_address="a@b.com",
                              subject="Re: hi", body="Body", headers=headers)
        raw = gmail.build_mime("me@x.test", out).as_bytes()
        assert raw_header_value(raw, "In-Reply-To") == M365_ID
        assert raw_header_value(raw, "References") == f"<first@leadpilot.dev> {M365_ID}"

    def test_gmail_drafts_use_the_same_policy(self):
        raw = base64.urlsafe_b64decode(gmail._raw_message("me@x.test", "a@b.com",
                                                          "Re: " + "x" * 120, "Body"))
        assert "=?" not in _head(raw)


class TestSystemMail:
    def test_smtp_system_mail_uses_the_raw_policy(self, monkeypatch):
        from app.services import email_sender

        sent = []

        class _SMTP:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def starttls(self, **k):
                pass

            def login(self, *a):
                pass

            def send_message(self, message):
                sent.append(message)

        monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
        monkeypatch.setattr(email_sender.smtplib, "SMTP", _SMTP)
        email_sender._send_smtp("a@b.com", "Verify", "<p>x</p>", "x")
        assert sent[0].policy.max_line_length == 998

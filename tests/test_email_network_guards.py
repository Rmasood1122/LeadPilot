"""Email network -- the LEGAL / SAFETY GUARDS (docs/features/email-network.md).
Candidate for the sealed compliance set (evals/compliance_testset.yaml).

  1  Headers only: no subject, body, Message-ID or Gmail snippet is ever
     stored -- not in any new table, not in the import result, not in the
     audit trail; the schema has nowhere to put one.
  2  Uploads are never spooled to disk (no temp file), however large.
  3  Filtered before storage: consumer domains, role inboxes, automated /
     list senders, the user's own addresses and colleagues.
  4  Suppressed (unsubscribed / bounced / erased) and F05-excluded people are
     never stored or shown, and a lead's GDPR erasure removes the person.
  5  Tenancy: account A never sees, drafts for, adds or attaches B's
     contacts; a Gmail scan reads only the scanning account's own Gmail.
  6  No new send path: a saved first email reaches a person ONLY through
     send_message_impl, which adds the unsubscribe footer and headers, holds
     it for the daily approval and cancels it for a suppressed person.
  7  A draft is never sent: only SAVED words can be attached, and only an
     attached row is ever rendered.
  8  Wording never claims more relationship than the counts show; CASL.
  9  The "my own business contacts" attestation is required.
 10  GDPR export and erasure cover every new table.

Offline and deterministic: SQLite, a fake Gmail HTTP client, a stub model.
"""

from __future__ import annotations

import json
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import models as m
from app.db.base import Base
from app.services import account_erasure as ae
from app.services import account_export as ax
from app.services import email_network as en
from app.services import email_network_gmail as eng
from app.services import email_network_messages as enm
from app.services import system_settings
from tests.conftest import NOW

NEW_TABLES = ("email_contacts", "email_contact_matches", "email_network_imports",
              "email_network_messages")
SECRETS = ("SECRET-SUBJECT-7731", "SECRET-BODY-7731", "secret-msgid-7731",
           "SECRET-SNIPPET-7731", "SECRET-SIGNATURE-7731")


# --------------------------------------------------------------------------
# Shared builders (also imported by tests/test_email_network.py)
# --------------------------------------------------------------------------


def mbox_message(sender: str, to: str, *, date: str = "Mon, 05 Oct 2026 10:00:00 +0000",
                 cc: str | None = None, extra: str = "", body: str = "Hello") -> bytes:
    lines = [f"From x@y Mon Oct 05 10:00:00 +0000 2026", f"From: {sender}", f"To: {to}"]
    if cc:
        lines.append(f"Cc: {cc}")
    lines += [f"Subject: SECRET-SUBJECT-7731 for {to}",
              "Message-ID: <secret-msgid-7731@mail.example>", f"Date: {date}"]
    if extra:
        lines.append(extra)
    lines += ["", body, "SECRET-BODY-7731", "-- ", "SECRET-SIGNATURE-7731 | CEO | +1 555", ""]
    return ("\n".join(lines) + "\n").encode()


def standard_mbox() -> bytes:
    me = "Test User <test@leadpilot.dev>"
    return b"".join([
        mbox_message(me, '"Ana Lopez" <ana@acme-fire.com>'),
        mbox_message('"Ana Lopez" <ana@acme-fire.com>', me,
                     date="Tue, 06 Oct 2026 10:00:00 +0000"),
        mbox_message(me, "Cara Diaz <cara@summit-safety.com>", cc="ben.personal@gmail.com"),
        mbox_message("Info <info@vendor.com>", me),
        mbox_message("Shop News <deals@shop.com>", me,
                     extra="List-Unsubscribe: <https://shop.com/u>"),
        mbox_message("No Reply <no-reply@service.com>", me),
        mbox_message("Pat Colleague <pat@leadpilot.dev>", me),
        mbox_message('"Personal Pal" <pal@yahoo.com>', me),
    ])


def stored_text(db) -> str:
    """Every value of every row of every new table, as one string."""
    out = []
    for name in NEW_TABLES:
        table = Base.metadata.tables[name]
        for row in db.execute(select(table)).mappings():
            out.append(json.dumps({k: str(v) for k, v in row.items()}))
    return "\n".join(out)


def import_bytes(client, data: bytes, *, attested: bool = True, own: str | None = None):
    params = ({"attested": "true", "attestation_version": en.ATTESTATION_VERSION}
              if attested else {})
    headers = {"Content-Type": "application/octet-stream"}
    if own:
        headers["X-Own-Addresses"] = own          # a header, never the URL
    return client.post("/email-network/import", params=params, content=data,
                       headers=headers)


def make_product(db, user, name="SEO System X",
                 description="Local SEO audits for fire protection companies"):
    product = m.Product(user=user, name=name, description=description,
                        type=m.ProductType.SKILL)
    db.add(product)
    db.commit()
    return product


def make_user(db, email, plan=m.PlanTier.GROWTH):
    user = m.User(email=email, email_verified=True, plan=plan)
    db.add(user)
    db.commit()
    return user


@pytest.fixture()
def on(db_session, test_user):
    test_user.plan = m.PlanTier.GROWTH
    db_session.commit()
    system_settings.set(db_session, en.FLAG, True)
    return test_user


class StubWriter:
    def __init__(self, subject="Fire inspections", body="Hi Ana - quick question about "
                 "your inspection scheduling. Worth a look?"):
        self.subject, self.body, self.prompts = subject, body, []

    def complete_json(self, *, system, prompt, max_tokens=1024, **_kw):
        self.prompts.append((system, prompt))
        return {"subject": self.subject, "body": self.body}


@pytest.fixture()
def writer(monkeypatch):
    stub = StubWriter()
    monkeypatch.setattr("app.services.anthropic_client.get_client", lambda: stub)
    return stub


class _Resp:
    def __init__(self, status: int, data: dict):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


class FakeGmail:
    """users.messages.list / get. Returns MORE than asked (a snippet, a
    Subject and a Message-ID header) to prove they are ignored anyway."""

    def __init__(self, messages: list[dict], page_size: int = 100, status: int = 200):
        self.messages, self.page_size, self.status = messages, page_size, status
        self.calls: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def request(self, method, path, params=None, headers=None, json=None):
        self.calls.append((method, path, list(params or []), dict(headers or {})))
        if self.status != 200:
            return _Resp(self.status, {})
        if path == "/users/me/messages":
            p = dict(params or [])
            start = int(p.get("pageToken") or 0)
            size = int(p.get("maxResults") or 100)
            page = self.messages[start:start + size]
            out = {"messages": [{"id": x["id"], "threadId": "t"} for x in page]}
            if start + size < len(self.messages):
                out["nextPageToken"] = str(start + size)
            return _Resp(200, out)
        mid = path.rsplit("/", 1)[1]
        msg = next(x for x in self.messages if x["id"] == mid)
        headers = [{"name": k, "value": v} for k, v in msg["headers"].items()]
        headers += [{"name": "Subject", "value": "SECRET-SUBJECT-7731"},
                    {"name": "Message-ID", "value": "<secret-msgid-7731@x>"}]
        return _Resp(200, {"id": mid, "internalDate": msg.get("internalDate", "1791000000000"),
                           "labelIds": msg.get("labels", ["INBOX"]),
                           "snippet": "SECRET-SNIPPET-7731",
                           "payload": {"headers": headers,
                                       "body": {"data": "U0VDUkVULUJPRFktNzczMQ=="}}})


def gmail_message(mid, sender, to, labels=("INBOX",), extra=None):
    headers = {"From": sender, "To": to, "Date": "Mon, 05 Oct 2026 10:00:00 +0000"}
    headers.update(extra or {})
    return {"id": mid, "headers": headers, "labels": list(labels)}


def connect_gmail(db, user, address="sender@leadpilot.dev",
                  scopes="https://www.googleapis.com/auth/gmail.send "
                         "https://www.googleapis.com/auth/gmail.readonly"):
    from app.services import crypto

    account = m.GmailAccount(user_id=user.id, email_address=address,
                             token_ciphertext=crypto.encrypt_json(
                                 {"access_token": f"at-{user.id}", "refresh_token": "rt"}),
                             token_expires_at=NOW + timedelta(days=3650), scopes=scopes)
    db.add(account)
    db.commit()
    return account


@pytest.fixture()
def fake_gmail(monkeypatch):
    holder = {"http": FakeGmail([])}
    monkeypatch.setattr("app.integrations.gmail._gmail_http", lambda: holder["http"])
    monkeypatch.setattr("app.integrations.gmail.get_valid_access_token",
                        lambda db, account, oauth=None: f"token-of-{account.user_id}")
    return holder


@pytest.fixture()
def no_queue(monkeypatch):
    jobs = {"chunks": [], "verify": []}
    monkeypatch.setattr("app.workers.network_tasks.enqueue_gmail_chunk",
                        lambda sid, seq, countdown=0: jobs["chunks"].append((str(sid), seq))
                        or True)
    monkeypatch.setattr("app.workers.network_tasks.enqueue_verification",
                        lambda batch_id: jobs["verify"].append(str(batch_id)) or True)
    return jobs


def run_scan(db, scan_id, start_seq=0, now=None) -> str:
    seq, outcome = start_seq, "continue"
    while outcome == "continue":
        outcome = eng.run_chunk(db, scan_id, seq, now=now)
        seq += 1
    return outcome


# ==========================================================================
# 1. Headers only
# ==========================================================================


class TestHeadersOnly:
    def test_the_schema_has_no_place_for_mail_content(self):
        forbidden = ("subject", "body", "snippet", "message_id", "rfc", "signature",
                     "attachment", "raw", "header", "thread")
        for name in ("email_contacts", "email_contact_matches", "email_network_imports"):
            for column in Base.metadata.tables[name].columns:
                assert not any(f in column.name for f in forbidden), (name, column.name)
        # email_network_messages holds the USER'S OWN draft (subject/body) and a
        # foreign key to the campaign message it became -- nothing received.
        msgs = Base.metadata.tables["email_network_messages"]
        assert {fk.column.table.name for fk in msgs.c.message_id.foreign_keys} == {"messages"}
        assert not any(f in c.name for c in msgs.columns
                       for f in ("snippet", "rfc", "signature", "attachment", "raw", "thread"))

    def test_an_mbox_import_stores_no_subject_body_or_message_id(self, client, db_session, on):
        make_product(db_session, on)
        r = import_bytes(client, standard_mbox())
        assert r.status_code == 200, r.text
        assert r.json()["added"] >= 2
        everything = stored_text(db_session) + r.text + json.dumps([
            ev.details_json for ev in db_session.execute(select(m.SecurityAuditEvent))
            .scalars()], default=str)
        for secret in SECRETS:
            assert secret.lower() not in everything.lower(), secret

    def test_a_gmail_scan_asks_for_metadata_headers_only_and_stores_none_of_the_rest(
            self, client, db_session, on, fake_gmail, no_queue):
        connect_gmail(db_session, on)
        fake_gmail["http"] = FakeGmail([
            gmail_message("m1", "Ana Lopez <ana@acme-fire.com>", "sender@leadpilot.dev"),
            gmail_message("m2", "Test <test@leadpilot.dev>", "ana@acme-fire.com",
                          labels=("SENT",))])
        r = client.post("/email-network/gmail-scan",
                        json={"attested": True, "attestation_version": en.ATTESTATION_VERSION})
        assert r.status_code == 202, r.text
        assert run_scan(db_session, r.json()["id"]) == "done"
        gets = [c for c in fake_gmail["http"].calls if c[1] != "/users/me/messages"]
        assert gets
        for _, _, params, _ in gets:
            p = [(k, v) for k, v in params]
            assert ("format", "metadata") in p
            assert sorted(v for k, v in p if k == "metadataHeaders") == sorted(
                ["From", "To", "Cc", "Date", "List-Unsubscribe", "List-Id", "Precedence",
                 "Auto-Submitted"])
            fields = dict(p)["fields"]
            assert "snippet" not in fields and "raw" not in fields and "payload/body" not in fields
            assert all(k != "format" or v not in ("full", "raw") for k, v in p)
        assert db_session.execute(select(m.EmailContact)).scalars().one().two_way is True
        everything = stored_text(db_session) + json.dumps(client.get(
            "/email-network/gmail-scan").json(), default=str)
        for secret in SECRETS:
            assert secret.lower() not in everything.lower(), secret
        scan = db_session.get(m.EmailNetworkImport, __import__("uuid").UUID(r.json()["id"]))
        assert scan.tally_json is None            # transient tallies cleared at the end


# ==========================================================================
# 2. No temp files
# ==========================================================================


class TestNoTempFiles:
    def test_a_large_upload_is_never_spooled_to_disk(self, client, db_session, on,
                                                     monkeypatch):
        def refuse(*a, **k):
            raise AssertionError("an upload was written to a temporary file")

        for name in ("SpooledTemporaryFile", "NamedTemporaryFile", "TemporaryFile",
                     "mkstemp", "mkdtemp"):
            monkeypatch.setattr(tempfile, name, refuse)
        tmp = Path(tempfile.gettempdir())
        before = set(tmp.iterdir())
        filler = ("x" * 1000 + "\n") * 1500         # ~1.5 MB of body text
        big = mbox_message("Test <test@leadpilot.dev>", "Ana <ana@acme-fire.com>",
                           body=filler) * 2
        assert len(big) > 2 * 1024 * 1024
        r = import_bytes(client, big)
        assert r.status_code == 200, r.text
        assert set(tmp.iterdir()) - before == set()


# ==========================================================================
# 3. Filtered before storage
# ==========================================================================


class TestFilters:
    def test_consumer_role_automated_and_own_domain_are_never_stored(self, client,
                                                                     db_session, on):
        r = import_bytes(client, standard_mbox()).json()
        stored = set(db_session.execute(select(m.EmailContact.email)).scalars())
        assert stored == {"ana@acme-fire.com", "cara@summit-safety.com"}
        reasons = {x["reason"]: x["count"] for x in r["excluded_by_reason"]}
        assert reasons["personal_domain"] == 2      # ben.personal@gmail, pal@yahoo
        assert reasons["role_inbox"] == 1           # info@vendor.com
        assert reasons["automated"] == 2            # list sender + no-reply
        assert reasons["own_address"] == 1          # a colleague on leadpilot.dev

    def test_typed_own_addresses_count_as_colleagues(self, client, db_session, on):
        data = mbox_message("Test <test@leadpilot.dev>", "Kim <kim@mycorp.io>")
        import_bytes(client, data, own="me@mycorp.io")
        assert db_session.execute(select(m.EmailContact)).first() is None

    def test_a_contacts_file_is_filtered_the_same_way(self, client, db_session, on):
        csv = ("First Name,Last Name,E-mail Address,Company,Job Title\n"
               "Ana,Lopez,ana@acme-fire.com,Acme Fire,Owner\n"
               "Bo,Home,bo@hotmail.com,,\n"
               "Sales,Team,sales@acme-fire.com,Acme Fire,\n").encode()
        r = import_bytes(client, csv)
        assert r.status_code == 200, r.text
        assert set(db_session.execute(select(m.EmailContact.email)).scalars()) == {
            "ana@acme-fire.com"}


# ==========================================================================
# 4. Suppressed / excluded / erased
# ==========================================================================


class TestDoNotContact:
    def test_suppressed_and_excluded_people_are_never_stored(self, client, db_session, on):
        from app.services import guardrails

        db_session.add(m.SuppressionEntry(email="ana@acme-fire.com", reason="unsubscribed"))
        db_session.commit()
        guardrails.add_exclusion(db_session, on.id, "domain", "summit-safety.com",
                                 reason="customer")
        r = import_bytes(client, standard_mbox()).json()
        assert db_session.execute(select(m.EmailContact)).first() is None
        reasons = {x["reason"]: x["count"] for x in r["excluded_by_reason"]}
        assert reasons["suppressed"] == 1 and reasons["excluded"] == 1

    def test_a_later_unsubscribe_hides_and_then_removes_the_person(self, client,
                                                                   db_session, on):
        make_product(db_session, on)
        import_bytes(client, standard_mbox())
        rec = client.get("/email-network/recommendations").json()["products"][0]
        assert "ana@acme-fire.com" in [x["email"] for x in rec["matches"]]
        db_session.add(m.SuppressionEntry(email="ana@acme-fire.com", reason="unsubscribed"))
        db_session.commit()
        rec = client.get("/email-network/recommendations").json()["products"][0]
        assert "ana@acme-fire.com" not in [x["email"] for x in rec["matches"]]
        client.post("/email-network/analyze")
        assert "ana@acme-fire.com" not in set(
            db_session.execute(select(m.EmailContact.email)).scalars())

    def test_a_leads_gdpr_erasure_removes_the_person_from_the_network(
            self, client, db_session, on, verified_strategy, no_queue, writer):
        import_bytes(client, standard_mbox())
        contact = db_session.execute(select(m.EmailContact).where(
            m.EmailContact.email == "ana@acme-fire.com")).scalar_one()
        added = client.post("/email-network/add-to-campaign", json={
            "strategy_id": str(verified_strategy.id), "contact_ids": [str(contact.id)]}).json()
        lead_id = added["lead_ids"][str(contact.id)]
        draft = client.post("/email-network/messages/draft", json={
            "contact_id": str(contact.id),
            "product_id": str(verified_strategy.product_id)}).json()
        assert client.delete(f"/leads/{lead_id}").status_code == 204
        db_session.expire_all()
        assert db_session.execute(select(m.EmailContact).where(
            m.EmailContact.email == "ana@acme-fire.com")).first() is None
        assert db_session.get(m.EmailNetworkMessage,
                              __import__("uuid").UUID(draft["id"])) is None
        # and an erased (suppressed) person never comes back on re-import
        import_bytes(client, standard_mbox())
        assert db_session.execute(select(m.EmailContact).where(
            m.EmailContact.email == "ana@acme-fire.com")).first() is None


# ==========================================================================
# 5. Tenancy
# ==========================================================================


class TestTenancy:
    def test_another_account_sees_and_touches_nothing(self, client, db_session, on,
                                                      verified_strategy, writer, no_queue):
        other = make_user(db_session, "other@b.example")
        theirs_product = make_product(db_session, other)
        tally_owner = other
        from app.services import email_network_filter as flt
        from app.services import email_network_parse as parse

        tally = parse.Tally(own=flt.own_identity(db_session, tally_owner))
        stream = parse.MboxStream(tally)
        stream.feed(mbox_message("Other <other@b.example>", "Ana <ana@acme-fire.com>")
                    + mbox_message("Ana <ana@acme-fire.com>", "other@b.example"))
        stream.close()
        system_settings.set(db_session, en.FLAG, True)
        en.finish_mbox(db_session, other, stream, attested=True)
        theirs = db_session.execute(select(m.EmailContact).where(
            m.EmailContact.user_id == other.id)).scalar_one()
        make_product(db_session, on)
        assert client.get("/email-network/status").json()["contact_count"] == 0
        recs = client.get("/email-network/recommendations").json()["products"]
        assert all(p["matches"] == [] for p in recs)
        r = client.post("/email-network/messages/draft", json={
            "contact_id": str(theirs.id), "product_id": str(theirs_product.id)})
        assert r.status_code == 404
        r = client.post("/email-network/add-to-campaign", json={
            "strategy_id": str(verified_strategy.id), "contact_ids": [str(theirs.id)]})
        assert r.status_code == 404
        msg = m.EmailNetworkMessage(user_id=other.id, contact_id=theirs.id,
                                    product_id=theirs_product.id, subject="s", body="b",
                                    status="approved")
        db_session.add(msg)
        db_session.commit()
        assert client.put(f"/email-network/messages/{msg.id}",
                          json={"subject": "x", "body": "y"}).status_code == 404
        assert client.post(f"/email-network/messages/{msg.id}/attach",
                           json={"strategy_id": str(verified_strategy.id)}).status_code == 404
        assert client.get("/email-network/messages").json()["messages"] == []
        client.delete("/email-network")
        assert db_session.get(m.EmailContact, theirs.id) is not None

    def test_a_gmail_scan_reads_only_the_scanning_accounts_own_gmail(
            self, client, db_session, on, fake_gmail, no_queue):
        other = make_user(db_session, "other@b.example")
        connect_gmail(db_session, other, address="other@b.example")
        r = client.post("/email-network/gmail-scan",
                        json={"attested": True, "attestation_version": en.ATTESTATION_VERSION})
        assert r.status_code == 409               # I have no Gmail; theirs is never used
        assert fake_gmail["http"].calls == [] and no_queue["chunks"] == []
        connect_gmail(db_session, on)
        fake_gmail["http"] = FakeGmail([gmail_message("m1", "Ana <ana@acme-fire.com>",
                                                      "sender@leadpilot.dev")])
        r = client.post("/email-network/gmail-scan",
                        json={"attested": True, "attestation_version": en.ATTESTATION_VERSION})
        assert r.status_code == 202
        run_scan(db_session, r.json()["id"])
        tokens = {c[3]["Authorization"] for c in fake_gmail["http"].calls}
        assert tokens == {f"Bearer token-of-{on.id}"}
        assert db_session.execute(select(m.EmailContact.user_id)).scalars().all() == [on.id]


# ==========================================================================
# 6 + 7. No new send path; a draft is never sent
# ==========================================================================


@pytest.fixture()
def attached(client, db_session, on, verified_strategy, email_sequence, gmail_account,
             writer, no_queue):
    """Ana imported, a first email drafted, SAVED and attached to her lead in
    the campaign, the lead verified by the normal stage's verdict, then
    enrolled by the normal engine (step 1 scheduled at NOW)."""
    from app.services import sequence_engine as engine

    import_bytes(client, standard_mbox())
    contact = db_session.execute(select(m.EmailContact).where(
        m.EmailContact.email == "ana@acme-fire.com")).scalar_one()
    draft = client.post("/email-network/messages/draft", json={
        "contact_id": str(contact.id), "product_id": str(verified_strategy.product_id)}).json()
    saved = client.put(f"/email-network/messages/{draft['id']}", json={
        "subject": "Your inspection schedule",
        "body": "Hi Ana, thanks for your note in October. Would a short look at your "
                "inspection scheduling help? SAVED-WORDS-4410"})
    assert saved.status_code == 200, saved.text
    r = client.post(f"/email-network/messages/{draft['id']}/attach",
                    json={"strategy_id": str(verified_strategy.id)})
    assert r.status_code == 200, r.text
    lead = db_session.get(m.Lead, __import__("uuid").UUID(r.json()["lead_id"]))
    assert lead.status is m.LeadStatus.EMAIL_FOUND and no_queue["verify"]
    lead.status = m.LeadStatus.VERIFIED          # what the verify stage writes
    db_session.commit()
    assert engine.enroll_leads(db_session, email_sequence, now=NOW,
                               lead_ids=[lead.id]) == 1
    message = db_session.execute(select(m.Message).where(
        m.Message.lead_id == lead.id, m.Message.step_no == 1)).scalar_one()
    return lead, message, draft["id"]


class TestOnlyThroughTheChokepoint:
    def test_the_saved_words_go_out_with_the_footer_and_unsubscribe_headers(
            self, db_session, attached, fake_channel):
        from app.workers import outreach_tasks

        lead, message, _ = attached
        result = outreach_tasks.send_message_impl(db_session, message.id,
                                                  channel=fake_channel, now=NOW)
        assert result == "sent"
        (out,) = fake_channel.sent
        assert "SAVED-WORDS-4410" in out.body
        assert "/unsubscribe/" in out.body
        assert out.headers["List-Unsubscribe"].startswith("<") and \
            out.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        assert out.to_address == "ana@acme-fire.com"

    def test_it_waits_for_the_daily_approval(self, db_session, attached, fake_channel,
                                             monkeypatch):
        from app.services import daily_send_approval as dsa
        from app.workers import outreach_tasks

        monkeypatch.setattr(dsa, "enabled", lambda db: True)
        lead, message, _ = attached
        result = outreach_tasks.send_message_impl(db_session, message.id,
                                                  channel=fake_channel, now=NOW)
        assert result == dsa.SEND_RESULT_AWAITING
        assert fake_channel.sent == []

    def test_a_suppressed_person_is_never_sent_the_saved_email(self, db_session, attached,
                                                               fake_channel):
        from app.workers import outreach_tasks

        lead, message, _ = attached
        db_session.add(m.SuppressionEntry(email=lead.email, reason="unsubscribed"))
        db_session.commit()
        result = outreach_tasks.send_message_impl(db_session, message.id,
                                                  channel=fake_channel, now=NOW)
        assert result == "cancelled_suppressed" and fake_channel.sent == []

    def test_no_module_of_the_feature_can_transmit(self):
        root = Path(__file__).resolve().parents[1] / "app"
        for name in ("services/email_network.py", "services/email_network_parse.py",
                     "services/email_network_filter.py", "services/email_network_gmail.py",
                     "services/email_network_messages.py", "api/email_network.py"):
            source = (root / name).read_text(encoding="utf-8")
            for banned in ("send_message_impl(", "messages/send", "drafts", ".send(",
                           "GmailChannel", "create_draft", "send_draft", "\"POST\"",
                           "'POST'"):
                assert banned not in source, (name, banned)

    def test_an_unsaved_draft_cannot_be_attached(self, client, db_session, on,
                                                 verified_strategy, writer, no_queue):
        import_bytes(client, standard_mbox())
        contact = db_session.execute(select(m.EmailContact).where(
            m.EmailContact.email == "ana@acme-fire.com")).scalar_one()
        draft = client.post("/email-network/messages/draft", json={
            "contact_id": str(contact.id),
            "product_id": str(verified_strategy.product_id)}).json()
        r = client.post(f"/email-network/messages/{draft['id']}/attach",
                        json={"strategy_id": str(verified_strategy.id)})
        assert r.status_code == 409
        assert db_session.execute(select(m.Lead)).first() is None

    def test_a_draft_row_is_never_rendered_into_a_send(self, db_session, attached,
                                                       fake_channel):
        from app.workers import outreach_tasks

        lead, message, msg_id = attached
        row = db_session.get(m.EmailNetworkMessage, __import__("uuid").UUID(msg_id))
        row.status = "draft"                         # even if a row were left linked
        db_session.commit()
        outreach_tasks.send_message_impl(db_session, message.id, channel=fake_channel, now=NOW)
        assert all("SAVED-WORDS-4410" not in o.body for o in fake_channel.sent)


# ==========================================================================
# 8. Wording + CASL
# ==========================================================================


class TestHonestWording:
    def test_no_two_way_exchange_means_no_we_spoke_wording(self, client, db_session, on,
                                                           writer):
        make_product(db_session, on)
        data = mbox_message("Test <test@leadpilot.dev>", "Cara Diaz <cara@summit-safety.com>")
        import_bytes(client, data)
        contact = db_session.execute(select(m.EmailContact)).scalar_one()
        assert contact.two_way is False
        product = db_session.execute(select(m.Product)).scalar_one()
        draft = client.post("/email-network/messages/draft", json={
            "contact_id": str(contact.id), "product_id": str(product.id)}).json()
        r = client.put(f"/email-network/messages/{draft['id']}", json={
            "subject": "Following up", "body": "Great speaking with you last week, Cara."})
        assert r.status_code == 422
        system, prompt = writer.prompts[-1]
        assert "Never claim a meeting" in system
        assert "no reply from them was found" in prompt

    def test_a_canadian_address_without_a_recent_two_way_exchange_is_refused(
            self, client, db_session, on, verified_strategy, no_queue):
        import_bytes(client, mbox_message("Test <test@leadpilot.dev>",
                                          "Dana <dana@maple-fire.ca>"))
        contact = db_session.execute(select(m.EmailContact)).scalar_one()
        r = client.post("/email-network/add-to-campaign", json={
            "strategy_id": str(verified_strategy.id), "contact_ids": [str(contact.id)]})
        assert r.status_code == 200
        assert r.json()["added"] == 0 and "CASL" in r.json()["skipped"][0]["reason"]


# ==========================================================================
# 9. Attestation
# ==========================================================================


class TestAttestation:
    def test_import_and_scan_need_the_attestation(self, client, db_session, on, fake_gmail,
                                                  no_queue):
        assert import_bytes(client, standard_mbox(), attested=False).status_code == 422
        r = client.post("/email-network/import",
                        params={"attested": "true", "attestation_version": "0"},
                        content=standard_mbox())
        assert r.status_code == 422
        assert db_session.execute(select(m.EmailContact)).first() is None
        assert db_session.execute(select(m.EmailNetworkImport)).first() is None
        connect_gmail(db_session, on)
        assert client.post("/email-network/gmail-scan", json={}).status_code == 422
        assert no_queue["chunks"] == []

    def test_the_attestation_is_recorded(self, client, db_session, on):
        import_bytes(client, standard_mbox())
        row = db_session.execute(select(m.EmailNetworkImport)).scalar_one()
        assert row.attested_at is not None
        assert row.attestation_version == en.ATTESTATION_VERSION


# ==========================================================================
# 10. GDPR export + erasure coverage
# ==========================================================================


class TestErasureAndExport:
    def test_every_new_table_is_exported_and_erased(self):
        for name in NEW_TABLES:
            assert ax.OWNERSHIP[name] == ["user_id"], name
            assert name in ae.DELETED, name

    def test_account_erasure_removes_the_network(self, client, db_session, on):
        import_bytes(client, standard_mbox())
        assert db_session.execute(select(m.EmailContact)).first() is not None
        ae.erase_account(db_session, on, now=NOW)
        db_session.commit()
        for name in NEW_TABLES:
            table = Base.metadata.tables[name]
            assert db_session.execute(select(table).where(
                table.c.user_id == on.id)).first() is None, name

    def test_delete_erases_everything_and_is_never_gated(self, client, db_session, on):
        import_bytes(client, standard_mbox())
        on.plan = m.PlanTier.FREE
        db_session.commit()
        system_settings.set(db_session, en.FLAG, False)
        r = client.delete("/email-network")
        assert r.status_code == 200 and r.json()["deleted_contacts"] == 2
        assert stored_text(db_session) == ""


# ==========================================================================
# Gates: plan + flag
# ==========================================================================


class TestGates:
    @pytest.mark.parametrize("plan", [m.PlanTier.FREE, m.PlanTier.STARTER,
                                      m.PlanTier.PAY_PER_MEETING])
    def test_lower_plans_get_402_and_store_nothing(self, client, db_session, on, plan):
        on.plan = plan
        db_session.commit()
        r = import_bytes(client, standard_mbox())
        assert r.status_code == 402
        assert r.json()["detail"]["limit"] == "email_network"
        assert db_session.execute(select(m.EmailContact)).first() is None

    def test_flag_off_refuses_imports_and_defaults_off(self, client, db_session, test_user):
        assert system_settings.DEFAULTS[en.FLAG][0] is False
        test_user.plan = m.PlanTier.GROWTH
        db_session.commit()
        assert import_bytes(client, standard_mbox()).status_code == 409
        assert db_session.execute(select(m.EmailContact)).first() is None

    def test_an_sdr_cannot_import_a_mailbox(self, db_session, on):
        """Reading a mailbox is the account's business (owner / manager)."""
        from fastapi import HTTPException
        from starlette.requests import Request

        from app.api.email_network import _require_manager

        req = Request({"type": "http", "headers": [], "method": "POST", "path": "/"})
        req.state.workspace_role = "sdr"
        with pytest.raises(HTTPException) as exc:
            _require_manager(req)
        assert exc.value.status_code == 403


# ==========================================================================
# Review round 2026-10-12 (each test FAILS on the pre-review tree)
# ==========================================================================


def _contact_row(db, user, email, **kw):
    base = dict(user_id=user.id, email=email, domain=email.rsplit("@", 1)[1],
                full_name="Klaus Weber", company="Feuerschutz", title="Owner",
                sent_to_count=4, received_from_count=4, two_way=True,
                last_seen=en._now() - timedelta(days=30), source_counts_json={})
    base.update(kw)
    row = m.EmailContact(**base)
    db.add(row)
    db.commit()
    return row


def _enrolled_lead(client, db, contact, strategy, sequence, now=NOW):
    from app.services import sequence_engine as engine

    r = client.post("/email-network/add-to-campaign", json={
        "strategy_id": str(strategy.id), "contact_ids": [str(contact.id)]})
    assert r.status_code == 200 and r.json()["added"] == 1, r.text
    lead = db.get(m.Lead, __import__("uuid").UUID(r.json()["lead_ids"][str(contact.id)]))
    lead.status = m.LeadStatus.VERIFIED
    db.commit()
    assert engine.enroll_leads(db, sequence, now=now, lead_ids=[lead.id]) == 1
    step1 = db.execute(select(m.Message).where(m.Message.lead_id == lead.id,
                                               m.Message.step_no == 1)).scalar_one()
    return lead, step1


class TestRegionH2:
    """H2: an email-network lead's region comes from its ccTLD; unknown is
    treated as the strictest regime, on EVERY step (follow-ups too)."""

    @pytest.mark.parametrize("email,notice", [("klaus@feuerschutz-gmbh.de", True),
                                              ("kim@acme-fire.com", True)])
    def test_eu_and_unknown_get_the_notice_and_no_pixel_on_every_step(
            self, client, db_session, on, verified_strategy, email_sequence, gmail_account,
            writer, no_queue, fake_channel, email, notice):
        from app.services import compliance_audit, compliance_region
        from app.services import sequence_engine as engine
        from app.workers import outreach_tasks

        contact = _contact_row(db_session, on, email)
        lead, step1 = _enrolled_lead(client, db_session, contact, verified_strategy,
                                     email_sequence)
        assert compliance_region.open_tracking_allowed(lead) is False
        assert compliance_audit.region_notice(lead) is not None
        if email.endswith(".de"):
            assert lead.enrichment_json["country"] == "DE"
            assert compliance_region.lead_region(lead) == "eu"
        assert outreach_tasks.send_message_impl(db_session, step1.id, channel=fake_channel,
                                                now=NOW) == "sent"
        step2 = db_session.execute(select(m.Message).where(
            m.Message.lead_id == lead.id, m.Message.step_no == 2)).scalar_one()
        when = step2.scheduled_at if step2.scheduled_at.tzinfo else \
            step2.scheduled_at.replace(tzinfo=NOW.tzinfo)
        assert outreach_tasks.send_message_impl(db_session, step2.id, channel=fake_channel,
                                                now=when) == "sent"
        assert len(fake_channel.sent) == 2
        for out in fake_channel.sent:
            assert "legitimate interest" in out.body               # the GDPR notice
            assert "html_body" not in (out.metadata or {})        # no tracking pixel
        assert engine  # noqa: B018

    def test_a_us_address_keeps_us_rules(self, db_session):
        from app.services import compliance_region
        from app.services.email_network_messages import country_for_domain

        assert country_for_domain("acme.us") == "US"
        assert country_for_domain("acme.co.uk") == "GB"
        assert country_for_domain("acme.io") is None
        lead = m.Lead(source="email_network", email="a@acme.us",
                      enrichment_json={"country": "US"})
        assert compliance_region.open_tracking_allowed(lead) is True
        other = m.Lead(source="apollo", email="a@acme.com", enrichment_json={})
        assert compliance_region.open_tracking_allowed(other) is True   # unchanged


class TestCaslAtSend:
    """M3: CASL re-checked at send for email-network leads."""

    def test_a_canadian_contact_past_two_years_is_skipped_at_send(
            self, client, db_session, on, verified_strategy, email_sequence, gmail_account,
            writer, no_queue, fake_channel):
        from app.workers import outreach_tasks

        contact = _contact_row(db_session, on, "dana@maple-fire.ca",
                               last_seen=en._now() - timedelta(days=700))
        lead, step1 = _enrolled_lead(client, db_session, contact, verified_strategy,
                                     email_sequence)
        # By the time the step is due, the last two-way exchange is > 2 years old.
        contact.last_seen = NOW - timedelta(days=800)
        db_session.commit()
        res = outreach_tasks.send_message_impl(db_session, step1.id, channel=fake_channel,
                                               now=NOW)
        assert res == "skipped_casl_window" and fake_channel.sent == []
        db_session.refresh(step1)
        assert step1.status is m.MessageStatus.SKIPPED

    def test_the_two_year_window_applies_to_two_way_contacts(self, db_session, on):
        recent = _contact_row(db_session, on, "a@maple.ca",
                              last_seen=en._now() - timedelta(days=300))
        old = _contact_row(db_session, on, "b@maple.ca",
                           last_seen=en._now() - timedelta(days=3 * 365))
        assert en.casl_block(recent) is None
        assert en.casl_block(old) is not None


class TestOpenerRender:
    """M24 / M3 / M19: the saved opener goes through build_compliant_email,
    only for the owner's row, only on step 1."""

    def test_footer_unsubscribe_headers_and_region_notice(self, db_session, attached,
                                                          fake_channel):
        from app.config import settings
        from app.workers import outreach_tasks

        lead, message, _ = attached
        outreach_tasks.send_message_impl(db_session, message.id, channel=fake_channel, now=NOW)
        (out,) = fake_channel.sent
        db_session.refresh(message)
        url = f"{settings.public_base_url.rstrip('/')}/unsubscribe/{message.unsubscribe_token}"
        assert message.unsubscribe_token
        assert out.headers["List-Unsubscribe"] == f"<{url}>"
        assert url in out.body
        assert settings.sender_identity in out.body                 # postal address
        assert "legitimate interest" in out.body                    # region notice (strictest)

    def test_owner_mismatch_and_later_steps_are_never_rendered(self, db_session, attached):
        from app.services import email_network_messages as enm2

        lead, message, msg_id = attached
        strategy = db_session.get(m.Strategy, lead.strategy_id)
        row = db_session.get(m.EmailNetworkMessage, __import__("uuid").UUID(msg_id))
        step2 = m.Message(sequence_id=message.sequence_id, lead_id=lead.id, step_no=2,
                          channel=m.ChannelType.EMAIL, template="x",
                          status=m.MessageStatus.SCHEDULED, scheduled_at=NOW)
        db_session.add(step2)
        db_session.commit()
        assert enm2.saved_opener(db_session, step2, lead, strategy) is None
        stranger = make_user(db_session, "stranger@x.example")
        row.user_id = stranger.id
        db_session.commit()
        assert enm2.saved_opener(db_session, message, lead, strategy) is None
        db_session.refresh(row)
        assert row.status == "attached" and row.message_id is None


class TestBlockedEverywhere:
    """M1 / M2 / M18 / M7 / M8 / M16 / M17: the do-not-contact and filter
    rules at every entry point."""

    def _import_and_suppress(self, client, db, verified_strategy):
        import_bytes(client, standard_mbox())
        contact = db.execute(select(m.EmailContact).where(
            m.EmailContact.email == "ana@acme-fire.com")).scalar_one()
        db.add(m.SuppressionEntry(email="ana@acme-fire.com", reason="unsubscribed"))
        db.commit()
        return contact

    def test_add_to_campaign_skips_suppressed_and_excluded(self, client, db_session, on,
                                                           verified_strategy, no_queue):
        from app.services import guardrails

        contact = self._import_and_suppress(client, db_session, verified_strategy)
        cara = db_session.execute(select(m.EmailContact).where(
            m.EmailContact.email == "cara@summit-safety.com")).scalar_one()
        guardrails.add_exclusion(db_session, on.id, "contact", "cara@summit-safety.com",
                                 reason="do_not_contact")
        r = client.post("/email-network/add-to-campaign", json={
            "strategy_id": str(verified_strategy.id),
            "contact_ids": [str(contact.id), str(cara.id)]}).json()
        assert r["added"] == 0 and len(r["skipped"]) == 2
        assert all("no longer be contacted" in x["reason"] for x in r["skipped"])
        assert db_session.execute(select(m.Lead)).first() is None

    def test_attach_refuses_a_suppressed_person_who_is_already_a_lead(
            self, client, db_session, on, verified_strategy, writer, no_queue):
        import_bytes(client, standard_mbox())
        contact = db_session.execute(select(m.EmailContact).where(
            m.EmailContact.email == "ana@acme-fire.com")).scalar_one()
        client.post("/email-network/add-to-campaign", json={
            "strategy_id": str(verified_strategy.id), "contact_ids": [str(contact.id)]})
        d = client.post("/email-network/messages/draft", json={
            "contact_id": str(contact.id),
            "product_id": str(verified_strategy.product_id)}).json()
        client.put(f"/email-network/messages/{d['id']}",
                   json={"subject": "Hello", "body": "Would this help your team?"})
        db_session.add(m.SuppressionEntry(email="ana@acme-fire.com", reason="unsubscribed"))
        db_session.commit()
        r = client.post(f"/email-network/messages/{d['id']}/attach",
                        json={"strategy_id": str(verified_strategy.id)})
        assert r.status_code == 409 and "no longer be contacted" in r.json()["detail"]
        db_session.expire_all()
        assert db_session.get(m.EmailNetworkMessage,
                              __import__("uuid").UUID(d["id"])).status == "approved"

    def test_draft_and_attach_refuse_a_suppressed_person(self, client, db_session, on,
                                                         verified_strategy, writer, no_queue):
        import_bytes(client, standard_mbox())
        contact = db_session.execute(select(m.EmailContact).where(
            m.EmailContact.email == "ana@acme-fire.com")).scalar_one()
        d = client.post("/email-network/messages/draft", json={
            "contact_id": str(contact.id),
            "product_id": str(verified_strategy.product_id)}).json()
        client.put(f"/email-network/messages/{d['id']}",
                   json={"subject": "Hello", "body": "Would this help your team?"})
        db_session.add(m.SuppressionEntry(email="ana@acme-fire.com", reason="unsubscribed"))
        db_session.commit()
        assert client.post("/email-network/messages/draft", json={
            "contact_id": str(contact.id),
            "product_id": str(verified_strategy.product_id)}).status_code == 409
        assert client.post(f"/email-network/messages/{d['id']}/attach", json={
            "strategy_id": str(verified_strategy.id)}).status_code == 409
        assert db_session.execute(select(m.Lead)).first() is None

    def test_store_itself_removes_rows_blocked_since(self, client, db_session, on,
                                                     monkeypatch):
        from app.services import email_network_filter as flt
        from app.services import email_network_parse as parse

        import_bytes(client, standard_mbox())
        db_session.add(m.SuppressionEntry(email="ana@acme-fire.com", reason="unsubscribed"))
        db_session.commit()
        monkeypatch.setattr(en, "analyze_user", lambda db, user, now=None: {"matches": 0})
        tally = parse.Tally(own=flt.own_identity(db_session, on))
        tally.add_message(("Ana", "ana@acme-fire.com"), [("T", "test@leadpilot.dev")], NOW,
                          False)
        row = en.new_import(db_session, on, "mbox", attested=True)
        en.store(db_session, on, row, tally, source="mbox")
        assert "ana@acme-fire.com" not in set(
            db_session.execute(select(m.EmailContact.email)).scalars())

    def test_analysis_removes_people_who_became_own_colleagues(self, client, db_session, on):
        import_bytes(client, standard_mbox())
        connect_gmail(db_session, on, address="me@summit-safety.com")
        client.post("/email-network/analyze")
        assert "cara@summit-safety.com" not in set(
            db_session.execute(select(m.EmailContact.email)).scalars())

    def test_a_company_exclusion_keeps_a_contact_out(self, client, db_session, on):
        from app.services import guardrails

        guardrails.add_exclusion(db_session, on.id, "company", "Acme Fire Protection",
                                 reason="customer")
        csv = ("Name,E-mail Address,Company\n"
               "Ana,ana@acme-fire.com,Acme Fire Protection\n").encode()
        r = import_bytes(client, csv).json()
        assert db_session.execute(select(m.EmailContact)).first() is None
        assert {x["reason"] for x in r["excluded_by_reason"]} == {"excluded"}

    def test_the_connected_gmail_address_is_the_user_own(self, client, db_session, on):
        connect_gmail(db_session, on, address="boss@ownbiz.org")
        import_bytes(client, mbox_message("Boss <boss@ownbiz.org>", "Ann <ann@acme-fire.com>"))
        ann = db_session.execute(select(m.EmailContact)).scalar_one()
        assert ann.email == "ann@acme-fire.com" and ann.sent_to_count == 1

    @pytest.mark.parametrize("addr", ["customer-service@acme-fire.com",
                                      "sales-team@acme-fire.com", "help-desk@acme-fire.com",
                                      "info1@acme-fire.com", "accounts-payable@acme-fire.com",
                                      "customer.service@acme-fire.com",
                                      "accounts.payable@acme-fire.com",
                                      "front.desk@acme-fire.com", "front-desk@acme-fire.com"])
    def test_role_inbox_variants(self, addr):
        from app.services import email_network_filter as flt

        assert flt.static_reason(flt.normalize_email(addr), flt.Own()) == flt.ROLE_INBOX

    @pytest.mark.parametrize("addr", ["no.reply@acme-fire.com", "do.not.reply@acme-fire.com"])
    def test_automated_dot_variants(self, addr):
        from app.services import email_network_filter as flt

        assert flt.static_reason(flt.normalize_email(addr), flt.Own()) == flt.AUTOMATED

    @pytest.mark.parametrize("addr", ["a@hotmail.ca", "a@protonmail.ch", "a@yahoo.co.jp",
                                      "a@outlook.co.uk", "a@gmx.at", "a@hotmail.com.br",
                                      "a@uol.com.br", "a@live.de", "a@aol.co.uk", "a@ukr.net",
                                      "a@yahoo.com.mx", "a@msn.co.jp"])
    def test_consumer_domain_variants(self, addr):
        from app.services import email_network_filter as flt

        assert flt.static_reason(flt.normalize_email(addr), flt.Own()) == flt.PERSONAL_DOMAIN

    def test_business_domains_that_look_like_brands_are_kept(self):
        from app.services import email_network_filter as flt

        for addr in ("a@live.example.com", "a@outlook-partners.com", "a@proton-energy.com"):
            assert flt.static_reason(addr, flt.Own()) is None, addr

    def test_own_subdomains_are_colleagues(self):
        from app.services import email_network_filter as flt

        own = flt.Own(addresses={"me@mycorp.com"}, domains={"mycorp.com"})
        assert flt.static_reason("pat@eu.mycorp.com", own) == flt.OWN_ADDRESS
        assert flt.static_reason("pat@notmycorp.com", own) is None


class TestErasureScrub:
    """M4 / M2: erasure reaches drafts attached to the lead, and running scans."""

    def test_erasing_a_lead_removes_drafts_attached_to_it_even_if_the_address_changed(
            self, client, db_session, attached):
        lead, _message, msg_id = attached
        lead.email = "ana.new@acme-fire.com"             # the lead's address was edited
        db_session.commit()
        assert client.delete(f"/leads/{lead.id}").status_code == 204
        db_session.expire_all()
        assert db_session.get(m.EmailNetworkMessage, __import__("uuid").UUID(msg_id)) is None

    def test_a_stale_scan_loses_its_tallies(self, client, db_session, on, fake_gmail,
                                            no_queue):
        connect_gmail(db_session, on)
        fake_gmail["http"] = FakeGmail([gmail_message(f"m{i}", f"P{i} <p{i}@corp{i}.com>",
                                                      "sender@leadpilot.dev")
                                        for i in range(150)])
        sid = __import__("uuid").UUID(client.post("/email-network/gmail-scan", json={
            "attested": True, "attestation_version": en.ATTESTATION_VERSION}).json()["id"])
        assert eng.run_chunk(db_session, sid, 0) == "continue"
        later = eng._now() + timedelta(hours=3)
        assert eng.sweep_stale(db_session, now=later) == 1
        row = db_session.get(m.EmailNetworkImport, sid)
        assert row.status == "failed" and row.tally_json is None

    def test_a_scan_restart_after_staleness_clears_the_old_tallies(self, client, db_session,
                                                                   on, fake_gmail, no_queue):
        connect_gmail(db_session, on)
        fake_gmail["http"] = FakeGmail([gmail_message(f"m{i}", f"P{i} <p{i}@corp{i}.com>",
                                                      "sender@leadpilot.dev")
                                        for i in range(150)])
        sid = __import__("uuid").UUID(client.post("/email-network/gmail-scan", json={
            "attested": True, "attestation_version": en.ATTESTATION_VERSION}).json()["id"])
        eng.run_chunk(db_session, sid, 0)
        eng.start_scan(db_session, on, attested=True, now=eng._now() + timedelta(hours=3))
        db_session.expire_all()
        row = db_session.get(m.EmailNetworkImport, sid)
        assert row.status == "failed" and "p1@corp1.com" not in str(row.tally_json)

    def test_suppression_and_erasure_reach_a_running_scan(self, client, db_session, on,
                                                          fake_gmail, no_queue, monkeypatch):
        monkeypatch.setattr(eng, "PAGE_SIZE", 2)
        connect_gmail(db_session, on)
        fake_gmail["http"] = FakeGmail([
            gmail_message("m1", "Ana <ana@acme-fire.com>", "sender@leadpilot.dev"),
            gmail_message("m2", "Bo <bo@beta-co.com>", "sender@leadpilot.dev"),
            gmail_message("m3", "Cy <cy@gamma-co.com>", "sender@leadpilot.dev"),
            gmail_message("m4", "Ana <ana@acme-fire.com>", "sender@leadpilot.dev")])
        sid = client.post("/email-network/gmail-scan", json={
            "attested": True, "attestation_version": en.ATTESTATION_VERSION}).json()["id"]
        db_session.add(m.SuppressionEntry(email="ana@acme-fire.com", reason="gdpr_delete"))
        db_session.commit()
        assert eng.run_chunk(db_session, sid, 0) == "continue"
        row = db_session.get(m.EmailNetworkImport, __import__("uuid").UUID(sid))
        assert "ana@acme-fire.com" not in str(row.tally_json)      # dropped this chunk
        assert "bo@beta-co.com" in str(row.tally_json)
        en.erase_person(db_session, on.id, email="bo@beta-co.com")
        db_session.commit()
        db_session.refresh(row)
        assert "bo@beta-co.com" not in str(row.tally_json)         # erasure scrubs it
        assert eng.run_chunk(db_session, sid, 1) == "done"
        stored = set(db_session.execute(select(m.EmailContact.email)).scalars())
        assert stored == {"cy@gamma-co.com"}

    def test_an_unsubscribe_removes_the_contact_at_once(self, client, db_session, on,
                                                        verified_strategy, no_queue):
        from app.services import sequence_engine as engine

        import_bytes(client, standard_mbox())
        contact = db_session.execute(select(m.EmailContact).where(
            m.EmailContact.email == "ana@acme-fire.com")).scalar_one()
        added = client.post("/email-network/add-to-campaign", json={
            "strategy_id": str(verified_strategy.id), "contact_ids": [str(contact.id)]}).json()
        lead = db_session.get(m.Lead, __import__("uuid").UUID(added["lead_ids"][str(contact.id)]))
        engine.unsubscribe_lead(db_session, lead, source="link")
        assert db_session.execute(select(m.EmailContact).where(
            m.EmailContact.email == "ana@acme-fire.com")).first() is None

    def test_the_weekly_refresh_purges_whatever_the_flag_or_plan(self, client, db_session,
                                                                 on):
        import_bytes(client, standard_mbox())
        db_session.add(m.SuppressionEntry(email="cara@summit-safety.com", reason="bounced"))
        on.plan = m.PlanTier.FREE
        db_session.commit()
        system_settings.set(db_session, en.FLAG, False)
        assert en.refresh_all(db_session)["purged"] == 1
        assert "cara@summit-safety.com" not in set(
            db_session.execute(select(m.EmailContact.email)).scalars())


class TestHonestWordingReview:
    """M5: wider over-claim patterns, the _RECENT rule, and the check again
    on the words that actually go out (a reviewer's edit)."""

    @pytest.mark.parametrize("text", [
        "It was a pleasure meeting you at the expo.", "Thanks for taking my call.",
        "Great to reconnect!", "As promised on the phone, here is the deck.",
        "Since we've spoken a few times, I wanted to follow up.", "Thanks for lunch.",
    ])
    def test_overclaims_are_refused_for_a_one_way_contact(self, text):
        c = m.EmailContact(email="x@acme.com", domain="acme.com", two_way=False,
                           sent_to_count=1, received_from_count=0, last_seen=None)
        assert enm.relationship_problems(c, "Hi", text)

    def test_plain_offers_are_allowed(self):
        c = m.EmailContact(email="x@acme.com", domain="acme.com", two_way=False,
                           sent_to_count=1, received_from_count=0, last_seen=None)
        assert enm.relationship_problems(
            c, "Inspections", "Would a 15-minute call next week help? Happy to talk on the "
                              "phone or by email.") == []

    def test_recent_wording_needs_a_recent_exchange(self):
        old = m.EmailContact(email="x@acme.com", domain="acme.com", two_way=True,
                             sent_to_count=3, received_from_count=3,
                             last_seen=en._now() - timedelta(days=180))
        fresh = m.EmailContact(email="x@acme.com", domain="acme.com", two_way=True,
                               sent_to_count=3, received_from_count=3,
                               last_seen=en._now() - timedelta(days=3))
        assert enm.relationship_problems(old, "Hi", "Good to hear from you last week.")
        assert enm.relationship_problems(fresh, "Hi", "Good to hear from you last week.") == []

    def test_a_reviewer_edit_that_overclaims_is_blocked_at_send(self, db_session, attached,
                                                                fake_channel):
        from app.workers import outreach_tasks

        lead, message, _ = attached
        contact = db_session.execute(select(m.EmailContact).where(
            m.EmailContact.email == lead.email)).scalar_one()
        contact.two_way, contact.received_from_count = False, 0
        db_session.add(m.SendReview(message_id=message.id, lead_id=lead.id, user_id=None,
                                    status="approved", subject_snapshot="s",
                                    body_snapshot="b", edited_subject="Hi",
                                    edited_body="Great speaking with you at the expo!"))
        db_session.commit()
        res = outreach_tasks.send_message_impl(db_session, message.id, channel=fake_channel,
                                               now=NOW)
        assert res == "blocked_forbidden_phrase" and fake_channel.sent == []


class TestRaceM4:
    def test_a_concurrent_draft_cannot_end_up_attached(self, client, db_session, on,
                                                       verified_strategy, writer, no_queue,
                                                       monkeypatch):
        from sqlalchemy import update

        import_bytes(client, standard_mbox())
        contact = db_session.execute(select(m.EmailContact).where(
            m.EmailContact.email == "ana@acme-fire.com")).scalar_one()
        d = client.post("/email-network/messages/draft", json={
            "contact_id": str(contact.id),
            "product_id": str(verified_strategy.product_id)}).json()
        assert client.put(f"/email-network/messages/{d['id']}", json={
            "subject": "Saved", "body": "Saved and checked words."}).status_code == 200
        real = enm._check_strategy

        def interleaved(db, user, sid):
            db.execute(update(m.EmailNetworkMessage)
                       .where(m.EmailNetworkMessage.id == __import__("uuid").UUID(d["id"]))
                       .values(subject="AI", body="UNSAVED-AI-DRAFT great speaking last week",
                               status="draft", strategy_id=None, lead_id=None)
                       .execution_options(synchronize_session=False))
            db.commit()
            return real(db, user, sid)

        monkeypatch.setattr(enm, "_check_strategy", interleaved)
        r = client.post(f"/email-network/messages/{d['id']}/attach",
                        json={"strategy_id": str(verified_strategy.id)})
        db_session.expire_all()
        row = db_session.get(m.EmailNetworkMessage, __import__("uuid").UUID(d["id"]))
        assert r.status_code == 409
        assert row.status == "draft" and row.lead_id is None


class TestDeletes:
    def test_delete_all_holds_an_attached_first_email_for_review(self, client, db_session,
                                                                attached, fake_channel):
        from app.workers import outreach_tasks

        lead, message, _ = attached
        out = client.delete("/email-network").json()
        assert out["first_emails_held_for_review"] == 1
        res = outreach_tasks.send_message_impl(db_session, message.id, channel=fake_channel,
                                               now=NOW)
        assert res == "held_for_review" and fake_channel.sent == []
        db_session.refresh(message)
        assert message.status is m.MessageStatus.AWAITING_REVIEW
        review = db_session.execute(select(m.SendReview).where(
            m.SendReview.message_id == message.id)).scalar_one()
        assert review.status == "pending" and review.body_snapshot

    def test_delete_one_contact_is_owner_scoped(self, client, db_session, on, writer,
                                                verified_strategy):
        import_bytes(client, standard_mbox())
        ana = db_session.execute(select(m.EmailContact).where(
            m.EmailContact.email == "ana@acme-fire.com")).scalar_one()
        d = client.post("/email-network/messages/draft", json={
            "contact_id": str(ana.id), "product_id": str(verified_strategy.product_id)}).json()
        other = make_user(db_session, "other@b.example")
        theirs = _contact_row(db_session, other, "zed@zeta-co.com")
        assert client.delete(f"/email-network/contacts/{theirs.id}").status_code == 404
        assert client.delete(f"/email-network/contacts/{ana.id}").json() == {
            "deleted_contacts": 1}
        db_session.expire_all()
        assert db_session.get(m.EmailContact, ana.id) is None
        assert db_session.get(m.EmailNetworkMessage, __import__("uuid").UUID(d["id"])) is None
        assert db_session.get(m.EmailContact, theirs.id) is not None

    def test_a_rejected_first_email_does_not_block_the_contact(self, client, db_session,
                                                               attached, writer):
        lead, message, msg_id = attached
        row = db_session.get(m.EmailNetworkMessage, __import__("uuid").UUID(msg_id))
        row.status, row.message_id = "used", message.id
        message.status = m.MessageStatus.CANCELLED          # rejected in review
        db_session.commit()
        assert client.post(f"/email-network/messages/{msg_id}/detach").status_code == 200
        r = client.post("/email-network/messages/draft", json={
            "contact_id": str(row.contact_id), "product_id": str(row.product_id)})
        assert r.status_code == 200 and r.json()["status"] == "draft"


class TestRolesAndPrivacy:
    def test_only_the_owner_can_scan_gmail(self):
        from fastapi import HTTPException
        from starlette.requests import Request

        from app.api.email_network import _require_owner

        req = Request({"type": "http", "headers": [], "method": "POST", "path": "/"})
        req.state.workspace_role = "manager"
        with pytest.raises(HTTPException) as exc:
            _require_owner(req)
        assert exc.value.status_code == 403
        req.state.workspace_role = "owner"
        _require_owner(req)

    def test_own_addresses_are_read_from_a_header_not_the_url(self, client, db_session, on):
        data = mbox_message("Test <test@leadpilot.dev>", "Kim <kim@mycorp.io>")
        client.post("/email-network/import", params={
            "attested": "true", "attestation_version": en.ATTESTATION_VERSION,
            "own_addresses": "me@mycorp.io"}, content=data)
        assert db_session.execute(select(m.EmailContact)).first() is not None  # URL ignored
        client.delete("/email-network")
        import_bytes(client, data, own="me@mycorp.io")
        assert db_session.execute(select(m.EmailContact)).first() is None

    def test_overlong_domains_are_rejected_and_sql_parameters_hidden(self):
        from app.db.base import engine
        from app.services import email_network_filter as flt

        long_domain = ".".join(["a" * 60] * 5) + ".com"
        assert flt.normalize_email(f"x@{long_domain}") is None
        assert flt.normalize_email("x@" + "b" * 64 + ".com") is None
        assert engine.hide_parameters is True

    def test_a_from_sentence_in_a_body_never_makes_contacts(self, client, db_session, on):
        msg = ("From x@y Mon Oct 05 10:00:00 +0000 2026\n"
               "From: Test <test@leadpilot.dev>\nTo: Ana <ana@acme-fire.com>\n"
               "Date: Mon, 05 Oct 2026 10:00:00 +0000\n\nHi Ana,\n\n"
               "From what we saw in 2025 the numbers are fine.\n"
               "From: Test <test@leadpilot.dev>\n"
               "To: SECRET-FORWARD-NAME <boss@other-co.com>\n").encode()
        r = import_bytes(client, msg)
        assert r.status_code == 200, r.text
        assert set(db_session.execute(select(m.EmailContact.email)).scalars()) == {
            "ana@acme-fire.com"}
        assert "SECRET-FORWARD-NAME" not in stored_text(db_session)

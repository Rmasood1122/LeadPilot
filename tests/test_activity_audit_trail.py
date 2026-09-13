"""Feature A2 — the tamper-evident send/reply audit trail.

Pins: every audited Outcome becomes exactly one hash-chained record in the same
transaction; the chain seals incrementally per account; the append-only guard;
tampering (edit, delete) is detected and located; signed JSON exports verify
with the published key and stop verifying when altered; the PDF renders; and
click tracking produces "clicked" events through a redirect that cannot be
turned into an open redirector.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import select, text

from app.db import models as m
from app.services import audit_trail, open_tracking, system_settings
from tests.conftest import auth_headers


def _outcome(db_session, lead, event=m.OutcomeEvent.SENT, **meta):
    db_session.add(m.Outcome(lead_id=lead.id, event=event, channel="email",
                             meta_json=meta or {"step_no": 1, "variant": "A"}))
    db_session.commit()


def _records(db_session, user_id=None):
    query = select(m.ActivityAuditEvent)
    if user_id is not None:
        query = query.where(m.ActivityAuditEvent.user_id == user_id)
    return db_session.execute(query.order_by(m.ActivityAuditEvent.occurred_at)).scalars().all()


class TestRecording:
    def test_each_audited_outcome_becomes_one_record(self, db_session, test_user,
                                                     verified_leads):
        lead = verified_leads[0]
        for event in (m.OutcomeEvent.SENT, m.OutcomeEvent.OPENED, m.OutcomeEvent.REPLIED,
                      m.OutcomeEvent.BOOKED):
            _outcome(db_session, lead, event)
        rows = _records(db_session)
        assert [r.event for r in rows] == ["sent", "opened", "replied", "booked"]
        assert all(r.user_id == test_user.id and r.lead_ref == lead.id for r in rows)
        assert all(r.seq_no is None and r.chain_hash is None for r in rows), "unsealed at insert"
        outcome_ids = set(db_session.execute(select(m.Outcome.id)).scalars())
        assert {r.outcome_ref for r in rows} == outcome_ids

    def test_content_hash_is_the_hash_of_the_content(self, db_session, verified_leads):
        _outcome(db_session, verified_leads[0])
        (row,) = _records(db_session)
        assert row.content_hash == audit_trail.content_hash(audit_trail.content_fields(row))

    def test_the_payload_carries_no_personal_data(self, db_session, verified_leads):
        _outcome(db_session, verified_leads[0], m.OutcomeEvent.CLICKED,
                 url="https://calendly.com/founder?email=lead0@co0.com", source="click_redirect")
        (row,) = _records(db_session)
        assert row.payload_json == {"url_host": "calendly.com", "source": "click_redirect"}
        assert "lead0@co0.com" not in json.dumps(row.payload_json)

    def test_unaudited_events_are_not_recorded(self, db_session, verified_leads):
        _outcome(db_session, verified_leads[0], m.OutcomeEvent.BOUNCED)
        _outcome(db_session, verified_leads[0], m.OutcomeEvent.UNSUBSCRIBED)
        assert _records(db_session) == []


@pytest.fixture()
def chain(db_session, test_user, verified_leads):
    for lead in verified_leads:
        _outcome(db_session, lead)
    assert audit_trail.seal(db_session, test_user.id) == 3
    return _records(db_session, test_user.id)


class TestSealingAndVerification:
    def test_seal_links_records_from_genesis(self, db_session, test_user, chain):
        rows = sorted(chain, key=lambda r: r.seq_no)
        assert [r.seq_no for r in rows] == [1, 2, 3]
        assert rows[0].prev_hash == audit_trail.GENESIS
        for previous, current in zip(rows, rows[1:]):
            assert current.prev_hash == previous.chain_hash
        result = audit_trail.verify_chain(db_session, test_user.id)
        assert result["valid"] is True and result["sealed"] == 3
        assert result["head_hash"] == rows[-1].chain_hash

    def test_sealing_is_incremental(self, db_session, test_user, chain, verified_leads):
        head = max(chain, key=lambda r: r.seq_no)
        _outcome(db_session, verified_leads[0], m.OutcomeEvent.REPLIED)
        assert audit_trail.seal(db_session, test_user.id) == 1
        newest = max(_records(db_session, test_user.id), key=lambda r: r.seq_no)
        assert newest.seq_no == 4 and newest.prev_hash == head.chain_hash
        assert audit_trail.verify_chain(db_session, test_user.id)["valid"] is True

    def test_an_edited_record_is_detected_and_located(self, db_session, test_user, chain):
        target = next(r for r in chain if r.seq_no == 2)
        db_session.execute(text("UPDATE activity_audit_events SET event = 'booked' WHERE id = :id"),
                           {"id": target.id.hex})
        db_session.commit()
        db_session.expire_all()
        result = audit_trail.verify_chain(db_session, test_user.id)
        assert result["valid"] is False
        assert {"seq_no": 2, "problem": "content_modified"} in result["problems"]

    def test_a_deleted_record_is_detected(self, db_session, test_user, chain):
        target = next(r for r in chain if r.seq_no == 2)
        db_session.execute(text("DELETE FROM activity_audit_events WHERE id = :id"),
                           {"id": target.id.hex})
        db_session.commit()
        db_session.expire_all()
        problems = audit_trail.verify_chain(db_session, test_user.id)["problems"]
        assert {p["problem"] for p in problems} >= {"sequence_gap", "broken_link"}

    def test_a_record_altered_before_sealing_is_never_sealed(self, db_session, test_user,
                                                             verified_leads):
        _outcome(db_session, verified_leads[0])
        (row,) = _records(db_session)
        db_session.execute(text("UPDATE activity_audit_events SET channel = 'phone' WHERE id = :id"),
                           {"id": row.id.hex})
        db_session.commit()
        db_session.expire_all()
        assert audit_trail.seal(db_session, test_user.id) == 0
        result = audit_trail.verify_chain(db_session, test_user.id)
        assert result["valid"] is False and result["problems"][0]["seq_no"] is None

    def test_each_account_has_its_own_chain(self, db_session, test_user, chain):
        other = m.User(email="other-chain@example.com", email_verified=True)
        db_session.add(other)
        db_session.flush()
        product = m.Product(user_id=other.id, name="p", description="d",
                            type=m.ProductType.SKILL)
        db_session.add(product)
        db_session.flush()
        strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.WITH_CLIENTS)
        db_session.add(strategy)
        db_session.flush()
        lead = m.Lead(strategy_id=strategy.id, source="manual", external_id="X", email="x@y.z")
        db_session.add(lead)
        db_session.commit()
        _outcome(db_session, lead)
        audit_trail.seal_all(db_session)
        (theirs,) = _records(db_session, other.id)
        assert theirs.seq_no == 1 and theirs.prev_hash == audit_trail.GENESIS


class TestAppendOnlyGuard:
    def test_delete_is_refused(self, db_session, chain):
        db_session.delete(chain[0])
        with pytest.raises(audit_trail.AuditTamperError):
            db_session.commit()
        db_session.rollback()

    def test_content_edits_are_refused(self, db_session, chain):
        chain[0].event = "booked"
        with pytest.raises(audit_trail.AuditTamperError):
            db_session.commit()
        db_session.rollback()

    def test_a_sealed_record_cannot_be_resealed(self, db_session, chain):
        chain[0].chain_hash = "f" * 64
        with pytest.raises(audit_trail.AuditTamperError):
            db_session.commit()
        db_session.rollback()


class TestSignedReports:
    def test_json_export_is_signed_and_verifies(self, client, db_session, chain):
        resp = client.get("/audit/trail/export")
        assert resp.status_code == 200
        assert "attachment" in resp.headers["content-disposition"]
        report = resp.json()
        assert report["chain"]["valid"] is True and len(report["records"]) == 3
        assert report["summary"] == {"sent": 3}

        key = client.get("/audit/public-key").json()
        unsigned = {k: v for k, v in report.items() if k != "signature"}
        Ed25519PublicKey.from_public_bytes(base64.b64decode(key["public_key"])).verify(
            base64.b64decode(report["signature"]["value"]), audit_trail.canonical(unsigned))

        verdict = client.post("/audit/verify", json=report).json()
        assert verdict["valid"] is True and verdict["signed_by_this_deployment"] is True

    def test_an_altered_report_fails_verification(self, client, chain):
        report = client.get("/audit/trail/export").json()
        report["records"][1]["event"] = "booked"
        verdict = client.post("/audit/verify", json=report).json()
        assert verdict["valid"] is False
        assert verdict["signature_valid"] is False
        assert verdict["records_consistent"] is False

    def test_verification_is_public(self, anon_client):
        assert anon_client.get("/audit/public-key").status_code == 200
        verdict = anon_client.post("/audit/verify", json={"records": []}).json()
        assert verdict["signature_valid"] is False

    def test_filtered_export(self, client, chain, verified_leads):
        report = client.get(f"/audit/trail/export?lead_id={verified_leads[0].id}").json()
        assert len(report["records"]) == 1
        assert report["scope"]["complete_chain"] is False

    def test_pdf_export(self, client, chain):
        resp = client.get("/audit/trail/export?format=pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:5] == b"%PDF-"

    def test_exports_are_owner_scoped(self, client, db_session, chain):
        stranger = m.User(email="audit-stranger@example.com", email_verified=True)
        db_session.add(stranger)
        db_session.commit()
        report = client.get("/audit/trail/export", headers=auth_headers(stranger)).json()
        assert report["records"] == []

    def test_verify_endpoint_seals_first(self, client, db_session, verified_leads):
        _outcome(db_session, verified_leads[0])
        body = client.get("/audit/trail/verify").json()
        assert body["valid"] is True and body["sealed"] == 1 and body["unsealed"] == 0

    def test_the_signing_key_is_stable(self):
        assert audit_trail.public_key() == audit_trail.public_key()


class TestClickTracking:
    @pytest.fixture()
    def sent_message(self, db_session, email_sequence, verified_leads):
        message = m.Message(sequence_id=email_sequence.id, lead_id=verified_leads[0].id,
                            channel=m.ChannelType.EMAIL, step_no=1, template="t", body="b",
                            status=m.MessageStatus.SENT,
                            sent_at=datetime.now(timezone.utc) - timedelta(hours=2))
        db_session.add(message)
        db_session.commit()
        return message

    def test_a_click_redirects_and_is_audited(self, client, db_session, sent_message):
        url = "https://calendly.com/founder/intro?utm_content=abc"
        tracked = open_tracking.click_url(sent_message.id, url)
        path = tracked.split("testserver", 1)[1]
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 302 and resp.headers["location"] == url
        assert client.get(path, follow_redirects=False).status_code == 302   # repeat
        clicks = db_session.execute(select(m.Outcome).where(
            m.Outcome.event == m.OutcomeEvent.CLICKED)).scalars().all()
        assert len(clicks) == 1
        assert [r.event for r in _records(db_session)] == ["clicked"]

    def test_the_redirect_cannot_be_repointed(self, client, sent_message):
        token = open_tracking.make_click_token(sent_message.id, "https://calendly.com/x")
        resp = client.get(f"/t/c/{token}?u=https://evil.example.com/", follow_redirects=False)
        assert resp.status_code == 404
        resp = client.get(f"/t/c/{token}?u=javascript:alert(1)", follow_redirects=False)
        assert resp.status_code == 404

    def test_scanner_prefetch_is_not_a_click(self, db_session, sent_message):
        sent_message.sent_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        db_session.commit()
        assert open_tracking.record_click(db_session, sent_message.id,
                                          "https://calendly.com/x") == "prefetch"

    def test_html_twin_uses_tracked_links_only_when_enabled(self, db_session):
        url = "https://cal.com/x?a=1&b=2"
        plain = open_tracking.html_body(f"Book: {url}", None)
        assert '<a href="https://cal.com/x?a=1&amp;b=2">' in plain
        tracked = open_tracking.html_body(f"Book: {url}", None,
                                          click_url=lambda u: f"https://t.example/c?u={u}")
        assert 'href="https://t.example/c?u=https://cal.com/x?a=1&amp;b=2"' in tracked
        assert ">https://cal.com/x?a=1&amp;b=2</a>" in tracked, "visible text is the real URL"

    def test_click_tracking_is_off_by_default(self, db_session, verified_leads):
        assert system_settings.get(db_session, "click_tracking_enabled") is False
        assert open_tracking.click_tracking_enabled(db_session, verified_leads[0]) is False


def test_sealing_is_scheduled_and_routed():
    from app.workers import audit_tasks  # noqa: F401
    from app.workers.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["seal-audit-trails"]
    assert entry["task"] == "app.workers.audit_tasks.seal_audit_trails"
    assert celery_app.amqp.router.route({}, entry["task"])["queue"].name == "default"

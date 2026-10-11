"""GDPR lead erasure also erases the correspondence (DELETE /leads/{id}).

BEFORE: `_gdpr_erase_lead` cleared the lead row but left what the person
wrote to us (inbound_replies: sender address, subject, body, the AI draft
answer) and what was written to them (messages: subject, body), and the
provenance snapshots of the erased field values. The help center said so in
"What this does not do today".

NOW: those are erased in the same transaction; the non-personal metadata the
reply-rate and send counts read is kept; a message that could still go out is
cancelled; provenance keeps WHERE a field came from, not WHAT it was.
Another lead's correspondence is untouched.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import account_erasure as ae
from app.services import auth as auth_svc
from app.services import provenance, send_holds
from tests.conftest import auth_headers

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


def _lead(db, strategy, seq, name):
    lead = m.Lead(strategy_id=strategy.id, source="apollo", external_id=uuid.uuid4().hex,
                  full_name=name, email=f"{name.lower()}@prospect.example",
                  title="CTO", company="Acme", status=m.LeadStatus.CONTACTED)
    db.add(lead)
    db.flush()
    provenance.record(db, lead, "title", provenance.APOLLO, value="CTO",
                      detail="from Apollo person 42", commit=False)
    sent = m.Message(sequence_id=seq.id, lead_id=lead.id, step_no=1,
                     channel=m.ChannelType.EMAIL, template="Step brief", variant="A",
                     subject=f"Hi {name}", body=f"Dear {name}, about Acme...",
                     status=m.MessageStatus.SENT, sent_at=NOW, provider_message_id="pm-1",
                     personalization_json={"linkedin_post_url": "https://li/post/1"},
                     open_count=3, opened_at=NOW)
    scheduled = m.Message(sequence_id=seq.id, lead_id=lead.id, step_no=2,
                          channel=m.ChannelType.EMAIL, template="Step 2", subject=f"Re {name}",
                          body="follow-up", status=m.MessageStatus.SCHEDULED, scheduled_at=NOW)
    held = m.Message(sequence_id=seq.id, lead_id=lead.id, step_no=3,
                     channel=m.ChannelType.EMAIL, template="Step 3", subject="s", body="b",
                     status=m.MessageStatus.FAILED,
                     error=send_holds.BOUNCE_SHIELD_PREFIX + f"{name.lower()}@prospect.example")
    db.add_all([sent, scheduled, held])
    db.flush()
    reply = m.InboundReply(lead_id=lead.id, message_id=sent.id, channel="email",
                           from_address=f"{name.lower()}@prospect.example",
                           subject=f"Re: Hi {name}", body=f"Thanks, I'm {name}, call me",
                           classification="human", reply_category="BUYING_SIGNAL",
                           intent_label="interested", intent_confidence=0.9,
                           intent_reason=f"{name} asked for a call",
                           ai_draft_response=f"Hi {name}, how about Tuesday?",
                           authenticity_kind="genuine",
                           authenticity_signals_json=[f"phrase:'call me {name}'"],
                           thread_ref="thread-1", received_at=NOW)
    db.add(reply)
    db.commit()
    return lead


@pytest.fixture()
def world(db_session):
    user = m.User(email="owner@o.example", email_verified=True,
                  password_hash=auth_svc.hash_password("Owner-pass-1!"))
    db_session.add(user)
    db_session.flush()
    product = m.Product(user_id=user.id, name="P", description="d", type=m.ProductType.SKILL)
    db_session.add(product)
    db_session.flush()
    strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.WITH_CLIENTS)
    db_session.add(strategy)
    db_session.flush()
    seq = m.Sequence(strategy_id=strategy.id, channel=m.ChannelType.EMAIL, name="S",
                     status=m.SequenceStatus.ACTIVE)
    db_session.add(seq)
    db_session.flush()
    jane = _lead(db_session, strategy, seq, "Jane")
    john = _lead(db_session, strategy, seq, "John")
    return user, jane, john


def _erase(client, user, lead):
    resp = client.delete(f"/leads/{lead.id}", headers=auth_headers(user))
    assert resp.status_code == 204, resp.text


def _messages(db, lead_id):
    return db.execute(select(m.Message).where(m.Message.lead_id == lead_id)
                      .order_by(m.Message.step_no)).scalars().all()


def _reply(db, lead_id):
    return db.execute(select(m.InboundReply).where(m.InboundReply.lead_id == lead_id)).scalar_one()


class TestReplies:
    def test_personal_fields_are_erased(self, client, db_session, world):
        user, jane, _ = world
        _erase(client, user, jane)
        db_session.expire_all()
        reply = _reply(db_session, jane.id)
        assert reply.from_address == ae.ERASED_TEXT
        assert reply.body == ae.ERASED_TEXT
        assert reply.subject is None
        assert reply.ai_draft_response is None
        assert reply.intent_reason is None
        assert reply.authenticity_signals_json is None
        assert reply.thread_ref is None

    def test_metadata_for_counts_is_kept(self, client, db_session, world):
        user, jane, _ = world
        _erase(client, user, jane)
        db_session.expire_all()
        reply = _reply(db_session, jane.id)
        assert reply.channel == "email"
        assert reply.classification == "human"
        assert reply.reply_category == "BUYING_SIGNAL"
        assert reply.intent_label == "interested"
        assert reply.authenticity_kind == "genuine"
        assert reply.received_at is not None
        assert reply.message_id is not None


class TestMessages:
    def test_subject_body_and_sources_are_erased(self, client, db_session, world):
        user, jane, _ = world
        _erase(client, user, jane)
        db_session.expire_all()
        for message in _messages(db_session, jane.id):
            assert message.subject is None and message.body is None
            assert message.personalization_json is None
            assert "jane" not in (message.error or "").lower()

    def test_send_metadata_is_kept(self, client, db_session, world):
        user, jane, _ = world
        _erase(client, user, jane)
        db_session.expire_all()
        sent = _messages(db_session, jane.id)[0]
        assert sent.status == m.MessageStatus.SENT
        assert sent.sent_at is not None and sent.open_count == 3
        assert sent.step_no == 1 and sent.variant == "A"
        assert sent.provider_message_id == "pm-1"

    def test_anything_that_could_still_go_out_is_cancelled(self, client, db_session, world):
        user, jane, _ = world
        _erase(client, user, jane)
        db_session.expire_all()
        _sent, scheduled, held = _messages(db_session, jane.id)
        assert scheduled.status == m.MessageStatus.CANCELLED
        assert held.status == m.MessageStatus.CANCELLED
        assert scheduled.error == ae.LEAD_ERASED_ERROR
        # a held message is no longer "held" (cannot be released back to send)
        held_now = db_session.execute(select(m.Message).where(
            m.Message.lead_id == jane.id, send_holds.held_clause())).scalars().all()
        assert held_now == []


class TestProvenanceAndIsolation:
    def test_provenance_keeps_the_source_not_the_value(self, client, db_session, world):
        user, jane, _ = world
        _erase(client, user, jane)
        db_session.expire_all()
        lead = db_session.get(m.Lead, jane.id)
        entry = lead.provenance_json["title"]
        assert entry["source"] == provenance.APOLLO
        assert entry["value"] is None and entry["detail"] is None
        assert "CTO" not in str(lead.provenance_json)

    def test_another_leads_correspondence_is_untouched(self, client, db_session, world):
        user, jane, john = world
        _erase(client, user, jane)
        db_session.expire_all()
        reply = _reply(db_session, john.id)
        assert reply.body == "Thanks, I'm John, call me"
        assert reply.from_address == "john@prospect.example"
        sent, scheduled, _held = _messages(db_session, john.id)
        assert sent.body.startswith("Dear John")
        assert scheduled.status == m.MessageStatus.SCHEDULED
        assert db_session.get(m.Lead, john.id).provenance_json["title"]["value"] == "CTO"


def test_scrub_provenance_handles_empty_and_odd_shapes():
    assert ae.scrub_provenance(None) is None
    assert ae.scrub_provenance({}) == {}
    assert ae.scrub_provenance({"x": "not-a-dict"}) == {"x": None}


# --------------------------------------------------------------------------
# Review fix 4: everything else recorded about the person
# --------------------------------------------------------------------------

from sqlalchemy import JSON as _JSON  # noqa: E402
from sqlalchemy import String as _String  # noqa: E402
from sqlalchemy import Text as _Text  # noqa: E402
from sqlalchemy import insert  # noqa: E402

from app.db.base import Base  # noqa: E402
from tests.test_account_erasure import _value  # noqa: E402


def _personal(column, name):
    if isinstance(column.type, _JSON):
        return {"who": name}
    if isinstance(column.type, (_String, _Text)):
        return f"{name} secret"[: column.type.length or 64]
    raise AssertionError(column)


def _make(db, name, ids, values):
    """One row of `name`; FKs point at `ids` (parents created when missing)."""
    table = Base.metadata.tables[name]
    row = {}
    for column in table.columns:
        if column.name in values:
            row[column.name] = values[column.name]
            continue
        fks = list(column.foreign_keys)
        if fks:
            target = fks[0].column.table.name
            if target in ids:
                row[column.name] = ids[target]
            elif not column.nullable:
                row[column.name] = ids[target] = _make(db, target, ids, {})
            continue
        if column.primary_key:
            row[column.name] = uuid.uuid4()
        elif not column.nullable and column.default is None and column.server_default is None:
            row[column.name] = _value(table, column)
    db.execute(insert(table).values(row))
    return row["id"]


# The order parents first: bookings before meetings before participants.
_ORDER = ["calendar_bookings", "meetings", "meeting_participants"] + [
    n for n in ae.LEAD_SCRUB if n not in ("calendar_bookings", "meetings",
                                          "meeting_participants", "inbound_replies")]


def _records_about(db, user, lead, name):
    sent = _messages(db, lead.id)[0]
    ids = {"users": user.id, "leads": lead.id, "messages": sent.id,
           "strategies": lead.strategy_id, "sequences": sent.sequence_id}
    made = {}
    for table_name in _ORDER:
        table = Base.metadata.tables[table_name]
        action = ae.LEAD_SCRUB[table_name]
        columns = (action if isinstance(action, dict)
                   else {c.name: None for c in table.columns
                         if isinstance(c.type, (_String, _Text)) and not c.foreign_keys})
        values = {c: _personal(table.c[c], name) for c in columns}
        if table_name == "meeting_participants":
            values["role"] = m.MeetingParticipantRole.CLIENT
            # the host (the account holder) is not the prospect: untouched
            _make(db, table_name, ids, {"role": m.MeetingParticipantRole.HOST, "name": "Host"})
        made[table_name] = _make(db, table_name, ids, values)
        ids[table_name] = made[table_name]
    db.commit()
    return made


class TestEverythingRecordedAboutThePerson:
    def test_every_scrubbed_table_is_cleared_for_the_lead_and_only_the_lead(
            self, client, db_session, world):
        user, jane, john = world
        janes = _records_about(db_session, user, jane, "Jane")
        johns = _records_about(db_session, user, john, "John")
        _erase(client, user, jane)
        db_session.expire_all()
        for name, action in ae.LEAD_SCRUB.items():
            if name == "inbound_replies":
                continue
            table = Base.metadata.tables[name]
            row = db_session.execute(select(table).where(
                table.c.id == janes[name])).mappings().one_or_none()
            if action == ae.DELETE:
                assert row is None, f"{name}: Jane's row not deleted"
            else:
                for column, value in action.items():
                    assert row[column] == value, f"{name}.{column} = {row[column]!r}"
                assert "jane" not in str(dict(row)).lower(), f"{name}: {dict(row)}"
            other = db_session.execute(select(table).where(
                table.c.id == johns[name])).mappings().one()
            assert "John secret" in str(dict(other)) or "'who': 'John'" in str(dict(other)), name
        host = db_session.execute(select(m.MeetingParticipant).where(
            m.MeetingParticipant.role == m.MeetingParticipantRole.HOST,
            m.MeetingParticipant.meeting_id == janes["meetings"])).scalar_one()
        assert host.name == "Host"

    def test_a_scheduled_reengagement_plan_is_cancelled(self, client, db_session, world):
        user, jane, _ = world
        plan = m.ReengagementPlan(lead_id=jane.id, due_at=NOW, status="scheduled",
                                  reason_text="Jane said call in Q1")
        db_session.add(plan)
        db_session.commit()
        _erase(client, user, jane)
        db_session.expire_all()
        plan = db_session.get(m.ReengagementPlan, plan.id)
        assert plan.status == "cancelled" and plan.reason_text is None

    def test_whatsapp_opt_in_is_revoked_and_its_number_erased(self, client, db_session, world):
        user, jane, _ = world
        jane.phone = "+15550123456"
        optin = m.WhatsAppOptIn(lead_id=jane.id, phone="+15550123456",
                                status=m.OptInStatus.OPTED_IN, source=m.OptInSource.WEB_FORM,
                                evidence="form at /x", consent_text="Yes Jane agrees")
        db_session.add(optin)
        db_session.commit()
        _erase(client, user, jane)
        db_session.expire_all()
        optin = db_session.get(m.WhatsAppOptIn, optin.id)
        assert optin.status == m.OptInStatus.OPTED_OUT and optin.revoked_at is not None
        assert optin.phone == ae.ERASED_TEXT and optin.consent_text is None
        # the opt-out proof lives on: the number is suppressed
        assert db_session.execute(select(m.SuppressionEntry).where(
            m.SuppressionEntry.phone.isnot(None))).scalars().all()

    def test_voicemail_audio_of_the_persons_calls_is_deleted(self, client, db_session, world,
                                                             tmp_path, monkeypatch):
        from app.config import settings  # noqa: PLC0415

        user, jane, john = world
        monkeypatch.setattr(settings, "media_dir", str(tmp_path))
        (tmp_path / "voicemails").mkdir()
        files = {}
        for lead in (jane, john):
            name = uuid.uuid4().hex + ".mp3"
            (tmp_path / "voicemails" / name).write_bytes(b"audio")
            db_session.add(m.Call(lead_id=lead.id, provider="vapi", to_number="+1555",
                                  voicemail_audio_url=f"https://x/media/voicemails/{name}"))
            files[lead.id] = tmp_path / "voicemails" / name
        db_session.commit()
        _erase(client, user, jane)
        assert not files[jane.id].exists() and files[john.id].exists()

    def test_the_stored_unsubscribe_token_is_cleared(self, client, db_session, world):
        user, jane, _ = world
        sent = _messages(db_session, jane.id)[0]
        sent.unsubscribe_token = "token-with-the-address"
        db_session.commit()
        _erase(client, user, jane)
        db_session.expire_all()
        assert _messages(db_session, jane.id)[0].unsubscribe_token is None


# --------------------------------------------------------------------------
# Review fix 4: the race with a send that is already rendering
# --------------------------------------------------------------------------

class TestSendingRace:
    def test_erasure_mid_send_stops_the_send_and_the_rendered_copy(
            self, db_session, enrolled, verified_leads, fake_channel, monkeypatch):
        from app.api import leads as leads_api  # noqa: PLC0415
        from app.services import guardrails  # noqa: PLC0415
        from app.workers.outreach_tasks import send_message_impl  # noqa: PLC0415
        from tests.conftest import NOW as SEND_NOW  # noqa: PLC0415

        lead = verified_leads[0]
        message = db_session.execute(select(m.Message).where(
            m.Message.lead_id == lead.id,
            m.Message.status == m.MessageStatus.SCHEDULED)).scalars().first()
        owner = db_session.execute(select(m.User)).scalars().first()
        real_block = guardrails.send_copy_block

        def erase_while_rendering(session, *a, **kw):
            # The message is claimed (SENDING) and its copy rendered and
            # committed; the person's erasure lands now, before transmit.
            leads_api._gdpr_erase_lead(session, session.get(m.Lead, lead.id), owner)
            return real_block(session, *a, **kw)

        monkeypatch.setattr(guardrails, "send_copy_block", erase_while_rendering)
        out = send_message_impl(db_session, message.id, channel=fake_channel, now=SEND_NOW)
        assert out == "cancelled_lead_erased"
        assert fake_channel.sent == []
        db_session.expire_all()
        msg = db_session.get(m.Message, message.id)
        assert msg.status == m.MessageStatus.CANCELLED
        assert msg.subject is None and msg.body is None

    def test_a_claim_lost_for_another_reason_sends_nothing_and_touches_nothing(
            self, db_session, enrolled, verified_leads, fake_channel, monkeypatch):
        from sqlalchemy import update as sa_update  # noqa: PLC0415

        from app.services import guardrails  # noqa: PLC0415
        from app.workers.outreach_tasks import send_message_impl  # noqa: PLC0415
        from tests.conftest import NOW as SEND_NOW  # noqa: PLC0415

        lead = verified_leads[0]
        message = db_session.execute(select(m.Message).where(
            m.Message.lead_id == lead.id,
            m.Message.status == m.MessageStatus.SCHEDULED)).scalars().first()
        real_block = guardrails.send_copy_block

        def someone_else_takes_it(session, *a, **kw):
            session.execute(sa_update(m.Message).where(m.Message.id == message.id)
                            .values(status=m.MessageStatus.FAILED, error="operator reset"))
            session.commit()
            return real_block(session, *a, **kw)

        monkeypatch.setattr(guardrails, "send_copy_block", someone_else_takes_it)
        out = send_message_impl(db_session, message.id, channel=fake_channel, now=SEND_NOW)
        assert out == "lost_claim_race"
        assert fake_channel.sent == []
        db_session.expire_all()
        msg = db_session.get(m.Message, message.id)
        assert msg.status == m.MessageStatus.FAILED and msg.error == "operator reset"
        assert msg.body                                   # not erased: lead was not

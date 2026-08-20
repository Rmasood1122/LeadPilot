"""M4 tests — the 24-hour customer-service window (Chunk 4, spec item 1).

The window is computed live from the lead's last INBOUND message:
no inbound ever = never open; open exactly [T, T+24h); every new inbound
resets it; template sends do NOT open it; a queued free-form message whose
window expired by send time fails CLOSED into needs_template.
"""

from datetime import timedelta

import pytest

from app.db import models as m
from app.services.whatsapp_window import window_state, window_state_for_lead
from tests.conftest import NOW, wa_outbound


class TestWindowMath:
    def test_no_inbound_ever_means_closed(self, db_session, wa_lead):
        assert wa_lead.whatsapp_last_inbound_at is None
        state = window_state(db_session, wa_lead.id, now=NOW)
        assert state.closed and state.expires_at is None

    def test_open_for_exactly_24h_from_inbound(self, db_session, wa_lead):
        inbound_at = NOW - timedelta(hours=23, minutes=59)
        wa_lead.whatsapp_last_inbound_at = inbound_at
        db_session.commit()
        state = window_state(db_session, wa_lead.id, now=NOW)
        assert state.open
        assert state.expires_at == inbound_at + timedelta(hours=24)

    def test_closed_at_expiry_boundary_and_after(self, db_session, wa_lead):
        wa_lead.whatsapp_last_inbound_at = NOW - timedelta(hours=24)
        db_session.commit()
        # exactly T+24h: closed (strict inequality — never a grace period)
        assert window_state(db_session, wa_lead.id, now=NOW).closed
        # T+24h+1s: still closed
        assert window_state(db_session, wa_lead.id,
                            now=NOW + timedelta(seconds=1)).closed

    def test_new_inbound_resets_expiry(self, db_session, wa_lead):
        wa_lead.whatsapp_last_inbound_at = NOW - timedelta(hours=23)
        db_session.commit()
        old_expiry = window_state(db_session, wa_lead.id, now=NOW).expires_at
        # a fresh inbound message arrives (what the webhook persists)
        wa_lead.whatsapp_last_inbound_at = NOW
        db_session.commit()
        state = window_state(db_session, wa_lead.id, now=NOW)
        assert state.open and state.expires_at == NOW + timedelta(hours=24)
        assert state.expires_at > old_expiry

    def test_unknown_lead_is_closed(self, db_session):
        import uuid
        assert window_state(db_session, uuid.uuid4(), now=NOW).closed


class TestWindowInteractions:
    def test_template_send_does_not_open_window(self, db_session, wa_lead,
                                                approved_template, wa_channel,
                                                fake_graph_http):
        assert window_state_for_lead(wa_lead, NOW).closed
        result = wa_channel.send(wa_outbound(wa_lead))  # approved template
        assert result.ok
        db_session.refresh(wa_lead)
        # a business-initiated send changed nothing about the window
        assert wa_lead.whatsapp_last_inbound_at is None
        assert window_state_for_lead(wa_lead, NOW).closed

    def test_queued_freeform_expired_by_send_time_fails_closed(
            self, db_session, fake_claude, wa_lead, approved_template,
            multichannel_sequence, fake_channel):
        """Queued while the window was open; window expired before the
        dispatcher got to it -> needs_template, never silently sent."""
        from app.workers.outreach_tasks import send_message_impl
        db_session.add(m.SequenceEnrollment(
            sequence_id=multichannel_sequence.id, lead_id=wa_lead.id,
            status=m.EnrollmentStatus.ACTIVE, current_step=1))
        # window was open at scheduling time...
        wa_lead.whatsapp_last_inbound_at = NOW - timedelta(hours=30)
        msg = m.Message(
            sequence_id=multichannel_sequence.id, lead_id=wa_lead.id,
            channel=m.ChannelType.WHATSAPP, step_no=2, template="reply text",
            whatsapp_kind=m.WhatsAppStepKind.TEXT,
            status=m.MessageStatus.SCHEDULED,
            scheduled_at=NOW - timedelta(hours=7),  # queued 23h after inbound
        )
        db_session.add(msg)
        db_session.commit()
        # ...but it is CLOSED now, at actual send time.
        result = send_message_impl(db_session, msg.id, channel=fake_channel,
                                   now=NOW)
        db_session.refresh(msg)
        assert result == "needs_template_window_closed"
        assert msg.status is m.MessageStatus.NEEDS_TEMPLATE
        assert fake_channel.sent == []  # nothing transmitted

    def test_freeform_sends_inside_open_window(self, db_session, fake_claude,
                                               wa_lead, approved_template,
                                               multichannel_sequence,
                                               fake_channel):
        from app.workers.outreach_tasks import send_message_impl
        db_session.add(m.SequenceEnrollment(
            sequence_id=multichannel_sequence.id, lead_id=wa_lead.id,
            status=m.EnrollmentStatus.ACTIVE, current_step=1))
        wa_lead.whatsapp_last_inbound_at = NOW - timedelta(hours=1)
        msg = m.Message(
            sequence_id=multichannel_sequence.id, lead_id=wa_lead.id,
            channel=m.ChannelType.WHATSAPP, step_no=2, template="reply text",
            whatsapp_kind=m.WhatsAppStepKind.TEXT,
            status=m.MessageStatus.SCHEDULED, scheduled_at=NOW,
        )
        db_session.add(msg)
        db_session.commit()
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == "sent"
        assert len(fake_channel.sent) == 1
        assert fake_channel.sent[0].metadata["kind"] == "text"

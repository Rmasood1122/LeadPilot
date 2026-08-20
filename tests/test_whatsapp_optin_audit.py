"""M4 tests — the opt-in audit trail (Chunk 4, item 5: append-only).

Every consent event is a NEW row; rows are never mutated. Note one
deliberate deviation from a naive "revoke then re-opt-in" flow: after an
opt-out, the SENDER cannot re-opt the contact in (the phone is suppressed
and record_opt_in refuses) — only the contact can re-initiate. This is
stricter than the spec's example and is the compliant behavior; the
three-row append-only property is proven with opt-in -> opt-in -> revoke.
"""

import pytest

from app.db import models as m
from app.services import whatsapp_optin as svc


class TestAppendOnly:
    def test_three_events_yield_three_rows_no_mutations(self, db_session,
                                                        wa_lead):
        # fixture already recorded opt-in #1 (source=api)
        first = svc.latest_row(db_session, wa_lead.id)
        first_id, first_ts = first.id, first.ts

        svc.record_opt_in(db_session, wa_lead, source=m.OptInSource.WEB_FORM,
                          evidence="hosted page", consent_text="I agree")
        svc.revoke_opt_in(db_session, wa_lead)

        rows = svc.history(db_session, wa_lead.id)
        assert len(rows) == 3
        assert [r.status for r in rows] == [
            m.OptInStatus.OPTED_IN, m.OptInStatus.OPTED_IN,
            m.OptInStatus.OPTED_OUT]
        # the first row was never touched
        assert (rows[0].id, rows[0].ts) == (first_id, first_ts)
        assert rows[0].source is m.OptInSource.API
        assert rows[2].revoked_at is not None
        assert svc.current_status(db_session, wa_lead.id) is m.OptInStatus.OPTED_OUT

    def test_sender_cannot_reoptin_after_optout(self, db_session, wa_lead):
        """Stricter than a naive re-opt-in: once opted out the phone is
        suppressed, and there is no sender-side path back."""
        svc.revoke_opt_in(db_session, wa_lead)
        with pytest.raises(svc.OptInError, match="suppress"):
            svc.record_opt_in(db_session, wa_lead, source=m.OptInSource.API,
                              evidence="user asked again, honest")
        # audit trail unchanged by the refused attempt
        assert len(svc.history(db_session, wa_lead.id)) == 2

    def test_inbound_initiation_only_upgrades_unknown(self, db_session,
                                                      wa_lead_no_optin,
                                                      wa_lead):
        # unknown -> recorded
        row = svc.record_inbound_initiation(db_session, wa_lead_no_optin,
                                            wamid="wamid.X1")
        assert row is not None and row.source is m.OptInSource.INBOUND_MESSAGE
        assert "wamid.X1" in row.evidence
        # opted_out -> NEVER silently upgraded
        svc.revoke_opt_in(db_session, wa_lead)
        assert svc.record_inbound_initiation(db_session, wa_lead,
                                             wamid="wamid.X2") is None
        assert svc.current_status(db_session, wa_lead.id) is m.OptInStatus.OPTED_OUT


class TestConsentRules:
    def test_manual_import_requires_evidence(self, db_session,
                                             wa_lead_no_optin):
        with pytest.raises(svc.OptInError, match="evidence"):
            svc.record_opt_in(db_session, wa_lead_no_optin,
                              source=m.OptInSource.MANUAL_IMPORT)

    @pytest.mark.parametrize("phone", ["abc", "0300123", "+0123456789",
                                       "1234567890123456"])
    def test_invalid_phones_rejected(self, db_session, wa_lead_no_optin,
                                     phone):
        with pytest.raises(svc.OptInError):
            svc.record_opt_in(db_session, wa_lead_no_optin, phone=phone,
                              source=m.OptInSource.API, evidence="e")

    def test_e164_normalization(self):
        assert svc.normalize_e164("+92 300-123 4567") == "+923001234567"
        assert svc.normalize_e164("0092 300 1234567") == "+923001234567"

    def test_revoke_propagates_suppression_and_stops_wa_sequences(
            self, db_session, verified_strategy, wa_lead, approved_template):
        from sqlalchemy import select
        seq = m.Sequence(strategy_id=verified_strategy.id,
                         channel=m.ChannelType.WHATSAPP, name="wa",
                         status=m.SequenceStatus.ACTIVE)
        db_session.add(seq)
        db_session.flush()
        enr = m.SequenceEnrollment(sequence_id=seq.id, lead_id=wa_lead.id,
                                   status=m.EnrollmentStatus.ACTIVE)
        db_session.add(enr)
        db_session.commit()

        svc.revoke_opt_in(db_session, wa_lead)
        db_session.refresh(enr)
        db_session.refresh(wa_lead)
        assert enr.status is m.EnrollmentStatus.STOPPED
        assert enr.stop_reason == "whatsapp_optout"
        assert wa_lead.whatsapp_opted_in is False
        assert db_session.execute(select(m.SuppressionEntry).where(
            m.SuppressionEntry.phone == wa_lead.phone)).scalars().first()
        # the UNSUBSCRIBED outcome carries the channel (M8 dependency)
        outcome = db_session.execute(select(m.Outcome).where(
            m.Outcome.lead_id == wa_lead.id,
            m.Outcome.event == m.OutcomeEvent.UNSUBSCRIBED)).scalars().one()
        assert outcome.channel == "whatsapp"

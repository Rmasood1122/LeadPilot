"""Closed leads stop their sequences (gaps-sweep-2 #3) -- a SAFETY guard.

Before: only "Remove" (dropped) on the Pipeline board stopped a lead's
sequences, and the send chokepoint blocked only `dropped`. A lead moved to
closed won / closed lost / disqualified from the CRM grid (single or bulk
edit) kept receiving its sequence. Now every status writer calls
sequence_engine.stop_for_status, and the chokepoint refuses a sequence step to
a closed lead whatever set the status.

Kept in its own file so it can be sealed on its own
(evals/compliance_testset.yaml is the orchestrator's to change). Every test
fails on the base (master be2f9e0) except those marked as controls.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import sequence_engine as engine
from app.workers import outreach_tasks as tasks
from tests.conftest import NOW


def _enrollment(db, sequence, lead):
    return db.execute(select(m.SequenceEnrollment).where(
        m.SequenceEnrollment.sequence_id == sequence.id,
        m.SequenceEnrollment.lead_id == lead.id)).scalar_one()


def _scheduled(db, lead):
    return db.execute(select(m.Message).where(
        m.Message.lead_id == lead.id,
        m.Message.status == m.MessageStatus.SCHEDULED)).scalars().all()


@pytest.fixture()
def opportunity(db_session, enrolled, verified_leads):
    """An enrolled lead, with step 1 scheduled, that reached the opportunity
    stage (the only stage the board may close from)."""
    lead = verified_leads[0]
    lead.status = m.LeadStatus.OPPORTUNITY
    db_session.commit()
    assert _scheduled(db_session, lead)
    return lead


class TestStatusWritersStopSequences:
    @pytest.mark.parametrize("status", ["closed_won", "closed_lost", "disqualified"])
    def test_crm_grid_close_stops_the_sequence(self, client, db_session, enrolled,
                                                opportunity, status):
        resp = client.patch(f"/crm/leads/{opportunity.id}", json={"status": status})
        assert resp.status_code == 200, resp.text
        enrollment = _enrollment(db_session, enrolled, opportunity)
        assert enrollment.status is m.EnrollmentStatus.STOPPED
        assert enrollment.stop_reason == f"crm_{status}"
        assert enrollment.stop_category == "crm_closed"
        assert _scheduled(db_session, opportunity) == []

    def test_crm_bulk_close_stops_every_moved_lead(self, client, db_session, enrolled,
                                                    verified_leads):
        first, second, third = verified_leads
        for lead in (first, second):
            lead.status = m.LeadStatus.OPPORTUNITY
        db_session.commit()
        resp = client.post("/crm/leads/bulk", json={
            "lead_ids": [str(first.id), str(second.id), str(third.id)],
            "status": "closed_lost"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["skipped_count"] == 1          # verified -> closed_lost is illegal
        for lead in (first, second):
            enrollment = _enrollment(db_session, enrolled, lead)
            assert enrollment.status is m.EnrollmentStatus.STOPPED
            assert enrollment.stop_category == "crm_closed"
            assert _scheduled(db_session, lead) == []
        assert _enrollment(db_session, enrolled, third).status is m.EnrollmentStatus.ACTIVE

    def test_pipeline_board_disqualify_stops_the_sequence(self, client, db_session, enrolled,
                                                          verified_leads):
        lead = verified_leads[0]
        lead.status = m.LeadStatus.MEETING_BOOKED
        db_session.commit()
        resp = client.patch(f"/leads/{lead.id}", json={"status": "disqualified"})
        assert resp.status_code == 200, resp.text
        enrollment = _enrollment(db_session, enrolled, lead)
        assert enrollment.status is m.EnrollmentStatus.STOPPED
        assert enrollment.stop_reason == "crm_disqualified"

    def test_control_a_non_closing_move_keeps_the_sequence(self, client, db_session,
                                                           enrolled, verified_leads):
        lead = verified_leads[0]
        lead.status = m.LeadStatus.MEETING_BOOKED
        db_session.commit()
        resp = client.patch(f"/crm/leads/{lead.id}", json={"status": "opportunity"})
        assert resp.status_code == 200, resp.text
        assert _enrollment(db_session, enrolled, lead).status is m.EnrollmentStatus.ACTIVE

    def test_crm_sync_terminal_set_is_the_shared_rule(self):
        from app.services import crm_sync

        assert crm_sync.TERMINAL == {s.value for s in engine.CLOSED_STATUSES}


class TestSendRefusesAClosedLead:
    @pytest.mark.parametrize("status", [m.LeadStatus.CLOSED_WON, m.LeadStatus.CLOSED_LOST,
                                        m.LeadStatus.DISQUALIFIED])
    def test_a_sequence_step_to_a_closed_lead_is_cancelled(
            self, db_session, enrolled, verified_leads, fake_channel, status):
        lead = verified_leads[0]
        lead.status = status          # set by a path that did not stop the enrollment
        db_session.commit()
        msg = _scheduled(db_session, lead)[0]
        out = tasks.send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert out == "cancelled_lead_closed"
        db_session.refresh(msg)
        assert msg.status is m.MessageStatus.CANCELLED
        assert fake_channel.sent == []
        enrollment = _enrollment(db_session, enrolled, lead)
        assert enrollment.status is m.EnrollmentStatus.STOPPED
        assert enrollment.stop_category == "crm_closed"

"""Manual launch lawful basis -- LEGAL GUARD (docs/features/autopilot-launch.md 3.5).

Before: the launch card's "I confirm I may lawfully email each of these people"
checkbox was enforced only in the browser; POST /sequences/{id}/enroll accepted
any caller and recorded nothing. Now the SERVER requires it, with the same
mechanism as the Autopilot opt-in: an explicit `lawful_basis_confirmed: true`
plus the CURRENT text version, else a clear 422 and nothing enrolled; and every
confirmation is recorded (who, when, text version AND exact text) in
compliance_audit_log (kept on account erasure) and security_audit_events.

Kept in its own file so it can be sealed. Other suites run with this guard off
(conftest `launch_lawful_basis_off`, the same pattern as
`daily_send_approval_off`), because sealed send-path suites launch with `{}`;
this module turns it back on and asserts the production default is ON.
"""

from __future__ import annotations

import pytest

from app.db import models as m
from tests.conftest import auth_headers

#: Captured at import, before conftest's autouse `launch_lawful_basis_off`.
from app.services import launch_consent  # noqa: E402

_REAL_ENFORCED = launch_consent.enforced


@pytest.fixture(autouse=True)
def guard_on(monkeypatch):
    monkeypatch.setattr(launch_consent, "enforced", _REAL_ENFORCED)


def _ok():
    return {"lead_statuses": ["verified"], "lawful_basis_confirmed": True,
            "lawful_basis_text_version": launch_consent.VERSION}


def _enrolled(db):
    return db.query(m.SequenceEnrollment).count()


class TestRequired:
    def test_the_production_default_is_on(self):
        assert _REAL_ENFORCED() is True

    @pytest.mark.parametrize("body", [
        {},
        {"lead_statuses": ["verified"]},
        {"lawful_basis_confirmed": False, "lawful_basis_text_version": "x"},
        {"lawful_basis_confirmed": True},
        {"lawful_basis_confirmed": True, "lawful_basis_text_version": "launch-2020-01-01"},
    ])
    def test_without_the_confirmation_it_is_a_clear_422_and_nothing_launches(
            self, client, db_session, email_sequence, verified_leads, gmail_account,
            fake_claude, body):
        r = client.post(f"/sequences/{email_sequence.id}/enroll", json=body)
        assert r.status_code == 422, r.text
        assert "lawful basis" in r.json()["detail"].lower()
        assert launch_consent.VERSION in r.json()["detail"]
        assert _enrolled(db_session) == 0
        assert db_session.query(m.ComplianceAuditLog).filter_by(channel="launch").count() == 0

    def test_confirmed_launch_enrolls_and_is_audited(self, client, db_session, test_user,
                                                     email_sequence, verified_leads,
                                                     gmail_account, fake_claude):
        r = client.post(f"/sequences/{email_sequence.id}/enroll", json=_ok())
        assert r.status_code == 202, r.text
        assert r.json()["enrolled"] == 3
        audit = db_session.query(m.ComplianceAuditLog).filter_by(channel="launch").one()
        assert audit.decision == launch_consent.AUDIT_DECISION
        assert audit.user_id == test_user.id
        assert audit.checks_json["text"] == launch_consent.TEXT
        assert audit.checks_json["text_version"] == launch_consent.VERSION
        assert audit.checks_json["sequence_id"] == str(email_sequence.id)
        assert audit.checks_json["actor_user_id"] == str(test_user.id)
        assert audit.checks_json["enrolled"] == 3
        event = db_session.query(m.SecurityAuditEvent).filter_by(
            action="sequence.launch_lawful_basis").one()
        assert event.target_id == str(email_sequence.id)

    def test_a_refused_launch_gate_records_no_confirmation(self, client, db_session,
                                                           email_sequence, verified_leads,
                                                           gmail_account, fake_claude,
                                                           verified_strategy):
        verified_strategy.campaign_state = "paused_manual"
        db_session.commit()
        r = client.post(f"/sequences/{email_sequence.id}/enroll", json=_ok())
        assert r.status_code == 409
        assert db_session.query(m.ComplianceAuditLog).filter_by(channel="launch").count() == 0

    def test_the_text_is_served(self, client):
        body = client.get("/launch/lawful-basis").json()
        assert body == {"version": launch_consent.VERSION, "text": launch_consent.TEXT}


class TestManagerApproval:
    def _team(self, db, test_user):
        from app.services import workspaces

        ws = workspaces.personal_workspace(db, test_user)
        people = {}
        for role in ("manager", "sdr"):
            user = m.User(email=f"{role}@lb.dev", email_verified=True)
            db.add(user)
            db.flush()
            db.add(m.WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=role))
            people[role] = user
        db.commit()
        return ws, people

    def _as(self, user, ws):
        return {**auth_headers(user), "X-Workspace-Id": str(ws.id)}

    def test_the_sdrs_confirmation_travels_with_the_request(self, client, db_session,
                                                            test_user, email_sequence,
                                                            verified_leads, gmail_account,
                                                            fake_claude):
        ws, people = self._team(db_session, test_user)
        email_sequence.status = m.SequenceStatus.DRAFT
        db_session.commit()
        held = client.post(f"/sequences/{email_sequence.id}/enroll", json=_ok(),
                           headers=self._as(people["sdr"], ws))
        assert held.json()["status"] == "pending_approval"
        audit = db_session.query(m.ComplianceAuditLog).filter_by(channel="launch").one()
        assert audit.checks_json["actor_user_id"] == str(people["sdr"].id)
        approved = client.post(f"/sequences/{email_sequence.id}/approve",
                               headers=self._as(people["manager"], ws))
        assert approved.status_code == 200, approved.text
        assert approved.json()["enrolled"] == 3

    def test_a_request_stored_without_it_needs_the_managers_confirmation(
            self, client, db_session, test_user, email_sequence, verified_leads,
            gmail_account, fake_claude):
        ws, people = self._team(db_session, test_user)
        email_sequence.status = m.SequenceStatus.PENDING_APPROVAL
        email_sequence.approval_payload_json = {"lead_statuses": ["verified"]}   # pre-guard
        db_session.commit()
        headers = self._as(people["manager"], ws)
        refused = client.post(f"/sequences/{email_sequence.id}/approve", headers=headers)
        assert refused.status_code == 422 and _enrolled(db_session) == 0
        ok = client.post(f"/sequences/{email_sequence.id}/approve", headers=headers,
                         json={"lawful_basis_confirmed": True,
                               "lawful_basis_text_version": launch_consent.VERSION})
        assert ok.status_code == 200, ok.text
        audit = db_session.query(m.ComplianceAuditLog).filter_by(channel="launch").one()
        assert audit.checks_json["actor_user_id"] == str(people["manager"].id)

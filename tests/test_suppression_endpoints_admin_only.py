"""F-SEC-04 — the suppression-list endpoints are admin-only.

GET /suppression listed every opted-out email and phone on the deployment to
any logged-in tenant, and POST /suppression let any tenant add rows to a list
that blocks every other tenant's sends. The list is global on purpose; reading
and editing it is therefore an operator action.

What does NOT change: enforcement. A suppressed address is blocked at send
time for every account, admin or not.
"""

import pytest
from sqlalchemy import select

from app.db import models as m
from app.workers.lead_tasks import is_suppressed
from tests.conftest import NOW, auth_headers


@pytest.fixture()
def admin(db_session):
    user = m.User(email="admin-suppression@test.dev", email_verified=True,
                  is_admin=True)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def existing_row(db_session):
    row = m.SuppressionEntry(email="gone@elsewhere.test", reason="unsubscribed")
    db_session.add(row)
    db_session.commit()
    return row


def _rows(db_session) -> list:
    return db_session.execute(select(m.SuppressionEntry)).scalars().all()


class TestNonAdminIsRefused:
    """`client` is authenticated as the canonical, non-admin test_user."""

    def test_list_is_forbidden(self, client, existing_row):
        response = client.get("/suppression")
        assert response.status_code == 403, response.text
        assert "gone@elsewhere.test" not in response.text

    def test_add_is_forbidden_and_writes_nothing(self, client, db_session):
        response = client.post("/suppression",
                               json={"email": "rival-prospect@x.test", "reason": "spite"})
        assert response.status_code == 403, response.text
        assert _rows(db_session) == []

    def test_add_by_phone_is_forbidden_and_writes_nothing(self, client, db_session):
        response = client.post("/suppression",
                               json={"phone": "+923001112233", "reason": "spite"})
        assert response.status_code == 403, response.text
        assert _rows(db_session) == []

    def test_delete_is_forbidden_and_removes_nothing(self, client, db_session,
                                                     existing_row):
        response = client.delete("/admin/suppression-list/gone@elsewhere.test")
        assert response.status_code == 403, response.text
        assert len(_rows(db_session)) == 1


class TestAdminWorks:
    def test_list(self, client, admin, existing_row):
        response = client.get("/suppression", headers=auth_headers(admin))
        assert response.status_code == 200, response.text
        assert [e["email"] for e in response.json()["entries"]] == ["gone@elsewhere.test"]

    def test_add(self, client, db_session, admin):
        response = client.post("/suppression", headers=auth_headers(admin),
                               json={"email": "Asked@Us.test", "reason": "asked"})
        assert response.status_code == 201, response.text
        assert [(r.email, r.reason) for r in _rows(db_session)] == [
            ("asked@us.test", "manual_asked")]

    def test_add_still_requires_an_identifier(self, client, admin):
        response = client.post("/suppression", headers=auth_headers(admin),
                               json={"reason": "x"})
        assert response.status_code == 422

    def test_delete(self, client, db_session, admin, existing_row):
        response = client.delete("/admin/suppression-list/gone@elsewhere.test",
                                 headers=auth_headers(admin))
        assert response.status_code == 200, response.text
        assert _rows(db_session) == []


class TestEnforcementIsUnchanged:
    def test_a_suppressed_email_is_still_blocked_for_a_non_admin_tenant(
            self, db_session, fake_claude, email_sequence, verified_leads,
            gmail_account):
        """The tenant can no longer READ the list, but it still binds them."""
        from app.services.sequence_engine import enroll_leads

        blocked = verified_leads[0]
        db_session.add(m.SuppressionEntry(email=blocked.email, reason="unsubscribed"))
        db_session.commit()

        assert is_suppressed(db_session, email=blocked.email) is True
        assert enroll_leads(db_session, email_sequence, now=NOW) == 2
        enrolled = {row.lead_id for row in db_session.execute(
            select(m.SequenceEnrollment)).scalars().all()}
        assert blocked.id not in enrolled

    def test_a_suppressed_phone_is_still_blocked_at_send_time(
            self, db_session, wa_lead, approved_template, wa_channel, fake_graph_http):
        from app.integrations.whatsapp import ComplianceError
        from tests.conftest import wa_outbound

        outbound = wa_outbound(wa_lead)
        db_session.add(m.SuppressionEntry(phone=wa_lead.phone, reason="stop"))
        db_session.commit()
        with pytest.raises(ComplianceError, match="suppression"):
            wa_channel.send(outbound)
        assert fake_graph_http.requests == []

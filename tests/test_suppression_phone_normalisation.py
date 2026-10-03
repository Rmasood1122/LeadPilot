"""NEW-04 — a suppressed phone must be blocked in ANY format.

suppression_list.phone was compared as an exact string, so a STOP recorded
as '+923001112233' did not block a lead stored as '+92 300-111 2233' or
'923001112233'. An opt-out that depends on punctuation is not an opt-out.

After the fix:
  * the check compares NORMALISED phones (digits only), so every format of a
    suppressed number is blocked -- including rows written before this change;
  * new rows are written in one canonical form, '+<digits>';
  * email matching is exactly what it was.
"""

import pytest
from sqlalchemy import select

from app.db import models as m
from app.integrations.whatsapp import ComplianceError
from app.services import consent
from app.services import whatsapp_optin as optin_svc
from app.workers.lead_tasks import is_suppressed
from tests.conftest import auth_headers, wa_outbound, wa_signed_post

CANONICAL = "+923001112233"
FORMATS = [
    "+923001112233",
    "923001112233",
    "+92 300-111 2233",
    "(+92) 300.111.2233",
    "  +92 300 111 2233  ",
]


def _phones(db_session) -> list:
    return [row.phone for row in db_session.execute(
        select(m.SuppressionEntry).where(m.SuppressionEntry.phone.isnot(None))
    ).scalars().all()]


def _lead(db_session, strategy, tag: str, phone: str, email: str | None = None) -> m.Lead:
    lead = m.Lead(strategy_id=strategy.id, source="apollo", external_id=f"NEW04-{tag}",
                  full_name=f"Lead {tag}", company=f"Company {tag}",
                  email=email or f"lead-{tag.lower()}@new04.test", phone=phone,
                  status=m.LeadStatus.VERIFIED)
    db_session.add(lead)
    db_session.commit()
    return lead


# --------------------------------------------------------------------------
# The check
# --------------------------------------------------------------------------


class TestEveryFormatOfASuppressedNumberIsBlocked:
    @pytest.mark.parametrize("stored", FORMATS)
    @pytest.mark.parametrize("asked", FORMATS)
    def test_stored_in_one_format_blocked_in_every_other(self, db_session, stored, asked):
        """`stored` stands for a row written before this change, in whatever
        format the writer happened to use."""
        db_session.add(m.SuppressionEntry(phone=stored, reason="legacy"))
        db_session.commit()
        assert is_suppressed(db_session, phone=asked) is True

    def test_a_different_number_is_not_blocked(self, db_session):
        db_session.add(m.SuppressionEntry(phone=CANONICAL, reason="stop"))
        db_session.commit()
        assert is_suppressed(db_session, phone="+923001112234") is False
        assert is_suppressed(db_session, phone="+92300111223") is False      # one digit short
        assert is_suppressed(db_session, phone="+9230011122330") is False    # one digit long

    def test_nothing_suppressed_means_nothing_blocked(self, db_session):
        assert is_suppressed(db_session, phone="+92 300-111 2233") is False

    def test_a_phone_with_no_digits_never_matches_another_one(self, db_session):
        db_session.add(m.SuppressionEntry(phone="unknown", reason="legacy"))
        db_session.commit()
        assert is_suppressed(db_session, phone="n/a") is False
        assert is_suppressed(db_session, phone="unknown") is True


class TestEmailIsUnchanged:
    def test_email_still_matches_case_insensitively_and_exactly(self, db_session):
        db_session.add(m.SuppressionEntry(email="gone@acme.test", reason="unsubscribed"))
        db_session.commit()
        assert is_suppressed(db_session, email="Gone@Acme.test ") is True
        assert is_suppressed(db_session, email="gone@acme.test.uk") is False
        assert is_suppressed(db_session, email="other@acme.test") is False

    def test_an_email_made_of_the_same_digits_as_a_phone_is_not_a_match(self, db_session):
        db_session.add(m.SuppressionEntry(phone=CANONICAL, reason="stop"))
        db_session.commit()
        assert is_suppressed(db_session, email="923001112233@acme.test") is False

    def test_either_identifier_is_enough(self, db_session):
        db_session.add(m.SuppressionEntry(phone="+92 300-111 2233", reason="stop"))
        db_session.commit()
        assert is_suppressed(db_session, email="fine@acme.test",
                             phone="923001112233") is True


# --------------------------------------------------------------------------
# Writes store one canonical form
# --------------------------------------------------------------------------


class TestWritesAreCanonical:
    def test_suppress_everywhere_stores_the_canonical_form(self, db_session,
                                                           verified_strategy):
        lead = _lead(db_session, verified_strategy, "W1", "+92 300-111 2233")
        consent.suppress_everywhere(db_session, lead, source="reply", reason="r")
        assert _phones(db_session) == [CANONICAL]

    def test_the_same_number_in_another_format_adds_no_second_row(
            self, db_session, verified_strategy):
        first = _lead(db_session, verified_strategy, "W2", "+92 300-111 2233")
        second = _lead(db_session, verified_strategy, "W3", "923001112233")
        consent.suppress_everywhere(db_session, first, source="reply", reason="r")
        result = consent.suppress_everywhere(db_session, second, source="reply", reason="r")
        assert result["applied"][consent.PHONE] == "already"
        assert _phones(db_session) == [CANONICAL]

    def test_gdpr_delete_stores_the_canonical_form(self, client, db_session,
                                                   verified_strategy, test_user):
        lead = _lead(db_session, verified_strategy, "W4", "(+92) 300.111.2233")
        response = client.delete(f"/leads/{lead.id}", headers=auth_headers(test_user))
        assert response.status_code == 204
        assert _phones(db_session) == [CANONICAL]

    def test_gdpr_delete_does_not_duplicate_a_row_stored_in_another_format(
            self, client, db_session, verified_strategy, test_user):
        db_session.add(m.SuppressionEntry(phone="923001112233", reason="legacy"))
        db_session.commit()
        lead = _lead(db_session, verified_strategy, "W5", "+92 300-111 2233")
        response = client.delete(f"/leads/{lead.id}", headers=auth_headers(test_user))
        assert response.status_code == 204
        assert _phones(db_session) == ["923001112233"]

    def test_the_manual_add_endpoint_stores_the_canonical_form(self, client, db_session,
                                                               test_user):
        # Setup changed for F-SEC-04: the endpoint is admin-only.
        test_user.is_admin = True
        db_session.commit()
        response = client.post("/suppression",
                               json={"phone": "+92 300-111 2233", "reason": "asked"})
        assert response.status_code == 201
        assert _phones(db_session) == [CANONICAL]


# --------------------------------------------------------------------------
# What it is for: the STOP holds whatever format the lead is stored in
# --------------------------------------------------------------------------


def _stop_from(number: str, wamid: str) -> dict:
    return {"entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "5550001"},
        "messages": [{"id": wamid, "from": number, "timestamp": "1754900000",
                      "type": "text", "text": {"body": "STOP"}}],
    }}]}]}


class TestAnUnattachedStopCoversEveryFormat:
    @pytest.mark.parametrize("stored", ["+92 300-111 2233", "923001112233",
                                        "(+92) 300.111.2233"])
    def test_a_lead_created_later_in_any_format_is_blocked(
            self, client, db_session, verified_strategy, stored):
        """Nobody holds the number when the STOP arrives (Task 1 writes the
        global row). A lead sourced afterwards, in any format, is blocked."""
        assert wa_signed_post(client, _stop_from("923001112233", "wamid.N4")).status_code == 200
        assert _phones(db_session) == [CANONICAL]

        lead = _lead(db_session, verified_strategy, "S1", stored)
        assert is_suppressed(db_session, phone=lead.phone) is True
        with pytest.raises(optin_svc.OptInError, match="suppression"):
            optin_svc.record_opt_in(db_session, lead, source=m.OptInSource.API,
                                    evidence="signed up")


class TestSendTime:
    def test_whatsapp_send_is_blocked_when_the_row_is_in_another_format(
            self, db_session, wa_lead, approved_template, wa_channel, fake_graph_http):
        """Same shape as the sealed guard test, with the suppression row
        written in a different format from the lead's phone."""
        outbound = wa_outbound(wa_lead)                     # lead: +923001234567
        db_session.add(m.SuppressionEntry(phone="92 300 123-4567", reason="test"))
        db_session.commit()
        with pytest.raises(ComplianceError, match="suppression"):
            wa_channel.send(outbound)
        assert fake_graph_http.requests == []

    def test_a_suppressed_lead_is_not_enrolled_whatever_its_phone_format(
            self, db_session, fake_claude, email_sequence, verified_strategy,
            gmail_account):
        from app.services.sequence_engine import enroll_leads
        from tests.conftest import NOW

        db_session.add(m.SuppressionEntry(phone=CANONICAL, reason="stop"))
        db_session.commit()
        blocked = _lead(db_session, verified_strategy, "E1", "+92 300-111 2233")
        allowed = _lead(db_session, verified_strategy, "E2", "+92 300-999 8888")

        enroll_leads(db_session, email_sequence, now=NOW)

        enrolled = {row.lead_id for row in db_session.execute(
            select(m.SequenceEnrollment)).scalars().all()}
        assert blocked.id not in enrolled
        assert allowed.id in enrolled

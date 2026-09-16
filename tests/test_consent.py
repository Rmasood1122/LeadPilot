"""Part 1 Feature 9 — the compliance and consent layer.

The properties that matter:
  * "stop contacting me" is ONE instruction about a person and is applied to
    every channel at once — including WhatsApp, which the old unsubscribe path
    left alone,
  * both halves of consent are recorded (granted as well as withdrawn),
  * the erasure record survives the erasure it is proof of,
  * what each regime demands is stated in exactly one place.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.db import models as m
from app.services import consent
from tests.conftest import auth_headers

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def lead(db_session, verified_strategy):
    row = m.Lead(strategy_id=verified_strategy.id, source="apollo", external_id="CN1",
                 full_name="Sara Khan", title="Owner", company="Blaze Safety",
                 email="sara@blaze.test", phone="+15550001234",
                 linkedin_url="https://www.linkedin.com/in/sara-khan/",
                 whatsapp_opted_in=True, whatsapp_opt_in_at=NOW,
                 status=m.LeadStatus.CONTACTED,
                 enrichment_json={"person": {"country": "United States"}})
    db_session.add(row)
    db_session.commit()
    return row


# --------------------------------------------------------------------------
# Requirements
# --------------------------------------------------------------------------


class TestRequirements:
    def test_every_region_gets_a_named_regime(self):
        for region in consent.REGIMES:
            assert consent.regime_for(region) != consent.UNKNOWN_REGIME
        assert consent.regime_for(None) == consent.UNKNOWN_REGIME
        assert consent.regime_for("atlantis") == consent.UNKNOWN_REGIME

    def test_gdpr_forbids_tracking_pixels_and_says_why(self):
        rules = consent.requirements_for("eu", consent.EMAIL)
        assert rules["tracking_allowed"] is False
        assert any("legitimate interest" in note for note in rules["notes"])

    def test_can_spam_is_an_opt_out_regime_not_an_opt_in_one(self):
        rules = consent.requirements_for("us", consent.EMAIL)
        assert rules["prior_consent"] is False
        assert rules["unsubscribe_required"] is True

    def test_casl_records_that_implied_consent_is_assumed_not_verified(self):
        rules = consent.requirements_for("ca", consent.EMAIL)
        assert any("cannot be verified" in note for note in rules["notes"])

    def test_an_unknown_region_gets_the_strictest_baseline(self):
        rules = consent.requirements_for(None, consent.EMAIL)
        assert rules["unsubscribe_required"] is True
        assert rules["sender_identity"] is True
        assert any("strictest" in note for note in rules["notes"])

    def test_whatsapp_needs_prior_consent_everywhere(self):
        """Not because of a statute — because Meta's policy says so, and
        losing the number is a harder problem than a regulator's letter."""
        for region in list(consent.REGIMES) + [None]:
            assert consent.requirements_for(region, consent.WHATSAPP)["prior_consent"] is True

    def test_an_ai_call_needs_prior_consent_in_the_us(self):
        assert consent.requirements_for("us", consent.PHONE)["prior_consent"] is True
        assert consent.requirements_for("eu", consent.PHONE)["prior_consent"] is False

    def test_the_lead_view_carries_every_channel(self, db_session, lead):
        out = consent.lead_requirements(lead)
        assert out["region"] == "us"
        assert set(out["channels"]) == set(consent.CHANNELS)


# --------------------------------------------------------------------------
# One instruction, every channel
# --------------------------------------------------------------------------


class TestSuppressEverywhere:
    def test_it_covers_whatsapp_which_the_old_path_did_not(self, db_session, lead):
        """The gap this feature closes: an unsubscribe by email used to leave
        whatsapp_opted_in True, and the next WhatsApp step went out."""
        result = consent.suppress_everywhere(db_session, lead, source="unsubscribe_link",
                                             reason="unsubscribed_link")
        db_session.refresh(lead)
        assert result["applied"][consent.WHATSAPP] == "suppressed"
        assert lead.whatsapp_opted_in is False

    def test_it_covers_email_phone_and_linkedin(self, db_session, lead):
        from app.workers.lead_tasks import is_suppressed

        consent.suppress_everywhere(db_session, lead, source="reply",
                                    reason="unsubscribed_reply")
        assert is_suppressed(db_session, email=lead.email)
        assert is_suppressed(db_session, phone=lead.phone)
        assert is_suppressed(db_session, linkedin="https://www.linkedin.com/in/sara-khan/")

    def test_it_writes_one_event_per_channel_plus_one_for_the_instruction(
            self, db_session, lead):
        consent.suppress_everywhere(db_session, lead, source="reply",
                                    reason="unsubscribed_reply")
        events = db_session.query(m.ConsentEvent).all()
        kinds = [e.kind for e in events]
        assert kinds.count(consent.WITHDRAWN) == 1
        assert kinds.count(consent.SUPPRESSED) == 4
        instruction = next(e for e in events if e.kind == consent.WITHDRAWN)
        assert instruction.channel == consent.ALL
        assert instruction.meta_json["applied"][consent.EMAIL] == "suppressed"

    def test_it_is_idempotent(self, db_session, lead):
        consent.suppress_everywhere(db_session, lead, source="reply", reason="r")
        second = consent.suppress_everywhere(db_session, lead, source="reply", reason="r")
        assert second["applied"][consent.EMAIL] == "already"
        assert db_session.query(m.SuppressionEntry).filter_by(
            email=lead.email).count() == 1

    def test_a_missing_identifier_is_reported_not_invented(
            self, db_session, verified_strategy):
        bare = m.Lead(strategy_id=verified_strategy.id, source="manual",
                      external_id="BARE", email="only@email.test",
                      status=m.LeadStatus.VERIFIED)
        db_session.add(bare)
        db_session.commit()
        result = consent.suppress_everywhere(db_session, bare, source="manual",
                                             reason="r")["applied"]
        assert result[consent.PHONE] == "no_identifier"
        assert result[consent.LINKEDIN] == "no_identifier"

    def test_the_region_and_regime_are_captured_on_every_event(self, db_session, lead):
        consent.suppress_everywhere(db_session, lead, source="reply", reason="r")
        events = db_session.query(m.ConsentEvent).all()
        assert all(e.region == "us" for e in events)
        assert all(e.regime == "CAN-SPAM" for e in events)


class TestWiring:
    def test_the_email_unsubscribe_now_revokes_whatsapp_too(
            self, db_session, lead, email_sequence):
        from app.services import sequence_engine as engine

        engine.unsubscribe_lead(db_session, lead, source="link")
        db_session.refresh(lead)
        assert lead.whatsapp_opted_in is False
        assert db_session.query(m.ConsentEvent).filter_by(
            kind=consent.WITHDRAWN).count() == 1

    def test_the_unsubscribe_still_stops_the_sequence(
            self, db_session, fake_claude, lead, email_sequence):
        from app.services import sequence_engine as engine

        enrollment = m.SequenceEnrollment(sequence_id=email_sequence.id, lead_id=lead.id)
        db_session.add(enrollment)
        db_session.commit()
        engine.unsubscribe_lead(db_session, lead, source="link")
        db_session.refresh(enrollment)
        assert enrollment.status is m.EnrollmentStatus.STOPPED

    def test_a_whatsapp_stop_suppresses_email_too(self, db_session, lead):
        from app.services import whatsapp_optin

        whatsapp_optin.revoke_opt_in(db_session, lead,
                                     source=m.OptInSource.INBOUND_MESSAGE)
        from app.workers.lead_tasks import is_suppressed

        assert is_suppressed(db_session, email=lead.email)

    def test_an_opt_in_is_recorded_as_a_grant(self, db_session, verified_strategy):
        from app.services import whatsapp_optin

        row = m.Lead(strategy_id=verified_strategy.id, source="manual",
                     external_id="OPT", email="opt@in.test", phone="+15550009999",
                     status=m.LeadStatus.VERIFIED)
        db_session.add(row)
        db_session.commit()
        whatsapp_optin.record_opt_in(db_session, row, source=m.OptInSource.MANUAL_IMPORT,
                                     evidence="signed up at leadpilot.io/whatsapp")
        granted = db_session.query(m.ConsentEvent).filter_by(kind=consent.GRANTED).all()
        assert len(granted) == 1
        assert granted[0].channel == consent.WHATSAPP
        assert "signed up" in granted[0].detail


class TestErasure:
    def test_the_erasure_record_survives_the_erasure(self, client, db_session, lead,
                                                     test_user):
        """The one moment the ledger exists for: proving the request was
        honoured, after the data it concerned is gone."""
        response = client.delete(f"/leads/{lead.id}", headers=auth_headers(test_user))
        assert response.status_code == 204
        db_session.expire_all()
        event = db_session.query(m.ConsentEvent).filter_by(kind=consent.ERASED).one()
        assert event.identifier == "sara@blaze.test"
        assert event.user_id == test_user.id
        db_session.refresh(lead)
        assert lead.email is None          # the data really is gone


# --------------------------------------------------------------------------
# Reading it back
# --------------------------------------------------------------------------


class TestLeadStatus:
    def test_a_clean_prospect_is_contactable_on_every_route_they_have(
            self, db_session, lead):
        status = consent.lead_status(db_session, lead)
        assert status["channels"][consent.EMAIL]["contactable"] is True
        assert status["channels"][consent.WHATSAPP]["contactable"] is True

    def test_it_names_the_reason_a_channel_is_closed(self, db_session, lead):
        consent.suppress_everywhere(db_session, lead, source="reply", reason="r")
        status = consent.lead_status(db_session, lead)
        assert status["channels"][consent.EMAIL]["reason"] == "suppressed"
        assert status["channels"][consent.WHATSAPP]["reason"] == "no recorded opt-in"

    def test_a_us_phone_without_consent_is_blocked_with_the_reason(
            self, db_session, lead):
        status = consent.lead_status(db_session, lead)
        assert status["channels"][consent.PHONE]["contactable"] is False
        assert "prior express consent" in status["channels"][consent.PHONE]["reason"]

    def test_a_missing_address_is_not_the_same_as_a_suppression(
            self, db_session, verified_strategy):
        bare = m.Lead(strategy_id=verified_strategy.id, source="manual",
                      external_id="B2", email="a@b.test", status=m.LeadStatus.VERIFIED)
        db_session.add(bare)
        db_session.commit()
        status = consent.lead_status(db_session, bare)
        assert status["channels"][consent.LINKEDIN]["reason"] == "no address on file"

    def test_the_history_is_included(self, db_session, lead):
        consent.suppress_everywhere(db_session, lead, source="reply", reason="r")
        assert consent.lead_status(db_session, lead)["history"]


class TestApi:
    def test_the_requirements_endpoint_covers_every_region_and_channel(
            self, client, db_session, test_user):
        body = client.get("/compliance/requirements",
                          headers=auth_headers(test_user)).json()
        assert set(body["channels"]) == set(consent.CHANNELS)
        assert len(body["regions"]) == len(consent.REGIMES) + 1     # + unknown
        assert "Not legal advice" in body["note"]

    def test_the_ledger_endpoint(self, client, db_session, lead, test_user):
        consent.suppress_everywhere(db_session, lead, source="reply", reason="r")
        response = client.get("/compliance/consent", headers=auth_headers(test_user))
        assert response.status_code == 200
        assert response.json()["total"] == 5

    def test_the_ledger_is_searchable_by_identifier(self, client, db_session, lead,
                                                    test_user):
        """When someone writes "I asked you to stop three months ago", the
        address is the only thing you have."""
        consent.suppress_everywhere(db_session, lead, source="reply", reason="r")
        response = client.get("/compliance/consent?identifier=sara@blaze.test",
                              headers=auth_headers(test_user))
        assert response.json()["total"] >= 1

    def test_the_lead_consent_endpoint(self, client, db_session, lead, test_user):
        response = client.get(f"/leads/{lead.id}/consent",
                              headers=auth_headers(test_user))
        assert response.status_code == 200
        assert response.json()["regime"] == "CAN-SPAM"

    def test_withdrawing_from_the_api_covers_every_channel(self, client, db_session,
                                                           lead, test_user):
        response = client.post(f"/leads/{lead.id}/consent/withdraw",
                               json={"source": "phone_call",
                                     "detail": "asked me to stop on a call"},
                               headers=auth_headers(test_user))
        assert response.status_code == 200
        body = response.json()
        assert body["applied"][consent.WHATSAPP] == "suppressed"
        assert body["channels"][consent.EMAIL]["contactable"] is False

    def test_the_source_is_recorded_verbatim(self, client, db_session, lead, test_user):
        """'They clicked unsubscribe' and 'a person asked on the phone' are
        different facts, and a regulator may care which."""
        client.post(f"/leads/{lead.id}/consent/withdraw", json={"source": "phone_call"},
                    headers=auth_headers(test_user))
        event = db_session.query(m.ConsentEvent).filter_by(kind=consent.WITHDRAWN).one()
        assert event.source == "phone_call"
        assert event.actor_user_id == test_user.id

    def test_another_account_cannot_read_or_withdraw(self, client, db_session, lead):
        other = m.User(email="nosy-consent@test.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        assert client.get(f"/leads/{lead.id}/consent",
                          headers=auth_headers(other)).status_code == 404
        assert client.post(f"/leads/{lead.id}/consent/withdraw", json={},
                           headers=auth_headers(other)).status_code == 404
        assert client.get("/compliance/consent",
                          headers=auth_headers(other)).json()["total"] == 0

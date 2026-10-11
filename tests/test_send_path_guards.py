"""Send-path gap fixes that add or repair a LEGAL / SAFETY GUARD
(docs/program/fixes/send-path-gaps.md). Candidates for the sealed compliance
set (evals/compliance_testset.yaml) -- the orchestrator decides.

  1  meeting follow-up email: the chokepoint's person-level guards
     (suppression on email/phone/LinkedIn, F05 exclusions, F10 departure,
     earlier-record opt-out), failing closed
  3  sourcing / enrichment check the LinkedIn profile against suppression
     (a GDPR-erased LinkedIn-only person is not re-sourced)
  4  "Remove" stops the lead's sequences; the send refuses a dropped lead
  7  enroll accepts verified leads only

Every test FAILS on the code before the fix unless it is a control (it pins
behaviour that must not change). Offline and deterministic.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import meeting_followup, system_settings
from app.services import sequence_engine as engine
from app.workers import outreach_tasks as tasks
from tests.conftest import NOW


def _enrollment(db, sequence, lead):
    return db.execute(select(m.SequenceEnrollment).where(
        m.SequenceEnrollment.sequence_id == sequence.id,
        m.SequenceEnrollment.lead_id == lead.id)).scalar_one()


# ===========================================================================
# 1. Meeting follow-up email -- same person-level guards as the chokepoint
# ===========================================================================


class _Resp:
    def __init__(self, status: int, data: dict):
        self.status_code = status
        self._data = data

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeGmailHTTP:
    def __init__(self):
        self.calls: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def request(self, method, path, json=None, headers=None):
        self.calls.append((method, path))
        if path.endswith("/send"):
            return _Resp(200, {"id": "sent-1", "threadId": "t1"})
        return _Resp(200, {"id": "draft-1", "message": {"id": "msg-1"}})


@pytest.fixture()
def gmail_http(monkeypatch):
    from app.integrations import gmail

    http = _FakeGmailHTTP()
    monkeypatch.setattr(gmail, "_gmail_http", lambda: http)
    monkeypatch.setattr(gmail, "get_valid_access_token", lambda *a, **k: "at")
    return http


@pytest.fixture()
def met_lead(db_session, verified_strategy):
    lead = m.Lead(strategy_id=verified_strategy.id, source="apollo", external_id="MF1",
                  full_name="Sara Khan", title="COO", company="Acme Fire",
                  email="sara@acmefire.test",
                  linkedin_url="https://www.linkedin.com/in/sara-khan-acme",
                  status=m.LeadStatus.OPPORTUNITY,
                  enrichment_json={"company_domain": "acmefire.test"})
    db_session.add(lead)
    db_session.commit()
    return lead


@pytest.fixture()
def saved_followup(db_session, met_lead, test_user, gmail_account):
    row = m.MeetingOutcome(lead_id=met_lead.id, user_id=test_user.id,
                           outcome=m.MeetingOutcomeKind.INTERESTED,
                           followup_subject="Great speaking today",
                           followup_body="Thanks Sara -- next step as agreed.",
                           draft_status="draft_saved", gmail_draft_id="draft-1")
    db_session.add(row)
    db_session.commit()
    return row


def _sends(http) -> list:
    return [c for c in http.calls if c[1].endswith("/send")]


class TestMeetingFollowupGuards:
    def test_an_unblocked_contact_is_still_sent(self, db_session, saved_followup,
                                                test_user, gmail_http):
        meeting_followup.send_followup(db_session, saved_followup, user=test_user)
        assert saved_followup.draft_status == "sent"
        assert len(_sends(gmail_http)) == 1

    def test_a_linkedin_suppression_blocks_the_send(self, db_session, saved_followup,
                                                    met_lead, test_user, gmail_http):
        """GDPR erasure suppresses the LinkedIn profile: before the fix only
        email and phone were checked."""
        from app.services.linkedin_outreach import normalize_profile

        db_session.add(m.LinkedInSuppression(profile=normalize_profile(met_lead.linkedin_url),
                                             reason="gdpr_delete"))
        db_session.commit()
        with pytest.raises(meeting_followup.FollowupNotSendable, match="suppression"):
            meeting_followup.send_followup(db_session, saved_followup, user=test_user)
        assert _sends(gmail_http) == []
        assert saved_followup.draft_status == "suppressed"

    def test_an_f05_do_not_contact_exclusion_blocks_the_send(
            self, db_session, saved_followup, met_lead, test_user, gmail_http):
        from app.services import guardrails

        system_settings.set(db_session, "guardrails_enabled", True)
        guardrails.add_exclusion(db_session, test_user.id, "contact", met_lead.email,
                                 reason="do_not_contact")
        with pytest.raises(meeting_followup.FollowupNotSendable, match="exclusion"):
            meeting_followup.send_followup(db_session, saved_followup, user=test_user)
        assert _sends(gmail_http) == []
        assert saved_followup.draft_status == "blocked"
        assert "do_not_contact" in saved_followup.draft_error

    def test_the_customer_and_open_deal_exclusions_do_not_block_it(
            self, db_session, saved_followup, met_lead, test_user, gmail_http):
        """The CRM sync adds every won / open-deal lead to these lists; the
        follow-up after the meeting that created the deal must still go."""
        from app.services import guardrails

        system_settings.set(db_session, "guardrails_enabled", True)
        guardrails.add_exclusion(db_session, test_user.id, "domain", "acmefire.test",
                                 reason="open_deal")
        meeting_followup.send_followup(db_session, saved_followup, user=test_user)
        assert saved_followup.draft_status == "sent"

    def test_a_recorded_departure_blocks_the_send(self, db_session, saved_followup,
                                                  met_lead, test_user, gmail_http):
        db_session.add(m.ChampionMove(user_id=test_user.id, old_lead_id=met_lead.id,
                                      trigger="refresh", outcome="not_champion",
                                      from_company="Acme Fire", detected_at=NOW))
        db_session.commit()
        with pytest.raises(meeting_followup.FollowupNotSendable, match="left Acme Fire"):
            meeting_followup.send_followup(db_session, saved_followup, user=test_user)
        assert _sends(gmail_http) == []
        assert saved_followup.draft_status == "blocked"

    def test_a_check_that_cannot_run_refuses_the_send(self, db_session, saved_followup,
                                                      test_user, gmail_http, monkeypatch):
        from app.services import guardrails

        def broken(*a, **k):
            raise RuntimeError("database went away")

        monkeypatch.setattr(guardrails, "send_blocks", broken)
        with pytest.raises(meeting_followup.FollowupNotSendable, match="could not be run"):
            meeting_followup.send_followup(db_session, saved_followup, user=test_user)
        assert _sends(gmail_http) == []

    def test_drafting_runs_the_same_guards(self, db_session, saved_followup, met_lead,
                                           test_user, gmail_http):
        db_session.add(m.ChampionMove(user_id=test_user.id, old_lead_id=met_lead.id,
                                      trigger="refresh", outcome="not_champion",
                                      from_company="Acme Fire", detected_at=NOW))
        saved_followup.draft_status, saved_followup.gmail_draft_id = "pending", None
        db_session.commit()
        meeting_followup.save_gmail_draft(db_session, saved_followup, user=test_user)
        assert saved_followup.draft_status == "blocked"
        assert gmail_http.calls == []


class TestExemptionNeverHidesDoNotContact:
    """Review finding 1 (H): the customer/open_deal exemption used to look at
    ONE exclusion row (find_match: ORDER BY kind LIMIT 1), and upsert kept the
    first writer's reason -- so an exempt row could hide a do_not_contact row
    and the follow-up was SENT. Ported from the reviewer's probes."""

    def _send(self, db_session, saved_followup, test_user):
        try:
            meeting_followup.send_followup(db_session, saved_followup, user=test_user)
        except meeting_followup.FollowupNotSendable as exc:
            return str(exc)
        return None

    def test_company_open_deal_does_not_hide_a_contact_dnc(
            self, db_session, saved_followup, met_lead, test_user, gmail_http):
        from app.services import guardrails

        system_settings.set(db_session, "guardrails_enabled", True)
        guardrails.upsert_exclusion(db_session, test_user.id, "company", met_lead.company,
                                    reason="open_deal", source="crm_hubspot")
        db_session.commit()
        guardrails.add_exclusion(db_session, test_user.id, "contact", met_lead.email,
                                 reason="do_not_contact")
        assert "do_not_contact" in (self._send(db_session, saved_followup, test_user) or "")
        assert _sends(gmail_http) == []

    def test_a_manual_dnc_overrides_a_crm_open_deal_on_the_same_contact(
            self, db_session, saved_followup, met_lead, test_user, gmail_http):
        from app.services import guardrails

        system_settings.set(db_session, "guardrails_enabled", True)
        guardrails.upsert_exclusion(db_session, test_user.id, "contact", met_lead.email,
                                    reason="open_deal", source="crm_local")
        db_session.commit()
        row, status = guardrails.add_exclusion(db_session, test_user.id, "contact",
                                               met_lead.email, reason="do_not_contact")
        assert (status, row.reason, row.source) == ("updated", "do_not_contact", "manual")
        assert self._send(db_session, saved_followup, test_user) is not None
        assert _sends(gmail_http) == []

    def test_contact_open_deal_does_not_hide_a_domain_dnc(
            self, db_session, saved_followup, met_lead, test_user, gmail_http):
        from app.services import guardrails

        system_settings.set(db_session, "guardrails_enabled", True)
        guardrails.add_exclusion(db_session, test_user.id, "domain", "acmefire.test",
                                 reason="do_not_contact")
        guardrails.upsert_exclusion(db_session, test_user.id, "contact", met_lead.email,
                                    reason="open_deal", source="crm_local")
        db_session.commit()
        assert self._send(db_session, saved_followup, test_user) is not None
        assert _sends(gmail_http) == []

    def test_the_f05_chokepoint_still_blocks_on_any_exclusion(
            self, db_session, enrolled, verified_leads, test_user, fake_channel):
        """F05 send-time behaviour is unchanged: an open_deal row alone still
        blocks a sequence message (no exemption there)."""
        from sqlalchemy import select as _select

        from app.services import guardrails

        system_settings.set(db_session, "guardrails_enabled", True)
        lead = verified_leads[0]
        guardrails.upsert_exclusion(db_session, test_user.id, "contact", lead.email,
                                    reason="open_deal", source="crm_local")
        db_session.commit()
        msg = db_session.execute(_select(m.Message).where(
            m.Message.lead_id == lead.id)).scalars().first()
        out = tasks.send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert out == "cancelled_excluded"
        assert fake_channel.sent == []


class TestExclusionPrecedence:
    """upsert_exclusion's documented precedence (review finding 1)."""

    @pytest.mark.parametrize("first,second,expected", [
        # (reason, source) first write, second write -> stored (reason, source), status
        (("open_deal", "crm_local"), ("do_not_contact", "manual"),
         ("do_not_contact", "manual", "updated")),
        (("do_not_contact", "manual"), ("open_deal", "crm_hubspot"),
         ("do_not_contact", "manual", "exists")),
        (("do_not_contact", "csv"), ("customer", "manual"),
         ("do_not_contact", "csv", "exists")),
        (("customer", "crm_salesforce"), ("churned", "manual"),
         ("churned", "manual", "updated")),
        (("churned", "manual"), ("customer", "crm_local"),
         ("churned", "manual", "exists")),
        (("customer", "crm_local"), ("open_deal", "crm_hubspot"),
         ("customer", "crm_local", "exists")),
        (("customer", "manual"), ("do_not_contact", "csv"),
         ("do_not_contact", "csv", "updated")),
    ])
    def test_precedence(self, db_session, test_user, first, second, expected):
        from app.services import guardrails

        guardrails.upsert_exclusion(db_session, test_user.id, "contact", "x@acme.test",
                                    reason=first[0], source=first[1])
        row, status = guardrails.upsert_exclusion(db_session, test_user.id, "contact",
                                                  "x@acme.test", reason=second[0],
                                                  source=second[1])
        assert (row.reason, row.source, status) == expected


class TestFollowupRemovedLeadAndRecheck:
    """Review finding 4: the follow-up refuses a removed (dropped) lead, and a
    blocked row can be checked again once the cause is gone."""

    def test_a_removed_lead_gets_no_follow_up(self, db_session, saved_followup, met_lead,
                                              test_user, gmail_http):
        met_lead.status = m.LeadStatus.DROPPED
        db_session.commit()
        with pytest.raises(meeting_followup.FollowupNotSendable, match="removed"):
            meeting_followup.send_followup(db_session, saved_followup, user=test_user)
        assert _sends(gmail_http) == []
        assert saved_followup.draft_status == "blocked"

    def test_check_again_saves_the_draft_once_the_cause_is_gone(
            self, client, db_session, saved_followup, met_lead, test_user, gmail_http):
        from app.services import guardrails

        system_settings.set(db_session, "guardrails_enabled", True)
        row, _ = guardrails.add_exclusion(db_session, test_user.id, "contact",
                                          met_lead.email, reason="do_not_contact")
        saved_followup.draft_status, saved_followup.gmail_draft_id = "pending", None
        db_session.commit()
        meeting_followup.save_gmail_draft(db_session, saved_followup, user=test_user)
        assert saved_followup.draft_status == "blocked"

        still = client.post(f"/meeting-outcomes/{saved_followup.id}/recheck")
        assert still.status_code == 200 and still.json()["draft_status"] == "blocked"

        guardrails.remove_exclusion(db_session, test_user.id, row.id)
        db_session.commit()
        cleared = client.post(f"/meeting-outcomes/{saved_followup.id}/recheck")
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["draft_status"] == "draft_saved"
        assert ("POST", "/users/me/drafts") in gmail_http.calls

    def test_check_again_needs_a_blocked_row(self, client, saved_followup):
        resp = client.post(f"/meeting-outcomes/{saved_followup.id}/recheck")
        assert resp.status_code == 409


# ===========================================================================
# 3. Sourcing checks the LinkedIn profile against the suppression list
# ===========================================================================


class TestSourcingLinkedInSuppression:
    def test_an_erased_linkedin_only_person_is_not_sourced_again(
            self, db_session, lead_batch, fake_source):
        from app.services.linkedin_outreach import normalize_profile
        from app.workers.lead_tasks import source_leads_impl
        from tests.conftest import make_raw

        url = "https://www.linkedin.com/in/erased-person"
        db_session.add(m.LinkedInSuppression(profile=normalize_profile(url),
                                             reason="gdpr_delete"))
        db_session.commit()
        raw = make_raw(1)
        raw.raw = {"id": "p1", "linkedin_url": url}
        fake_source.feed = [raw]
        counts = source_leads_impl(db_session, lead_batch.id, source=fake_source)
        assert counts["suppressed"] == 1 and counts["added"] == 0
        assert db_session.query(m.Lead).count() == 0

    def test_enrichment_drops_a_lead_whose_profile_is_suppressed(
            self, db_session, lead_batch, fake_source):
        from app.services.linkedin_outreach import normalize_profile
        from app.workers.lead_tasks import enrich_leads_impl

        url = "https://www.linkedin.com/in/opted-out"
        lead = m.Lead(strategy_id=lead_batch.strategy_id, batch_id=lead_batch.id,
                      source="fakesource", external_id="x1", full_name="Opted Out",
                      company="Acme", linkedin_url=url, status=m.LeadStatus.SOURCED,
                      enrichment_json={"raw": {"id": "x1"}})
        db_session.add(lead)
        db_session.add(m.LinkedInSuppression(profile=normalize_profile(url),
                                             reason="linkedin_optout"))
        db_session.commit()
        enrich_leads_impl(db_session, lead_batch.id, source=fake_source)
        db_session.refresh(lead)
        assert lead.status is m.LeadStatus.DROPPED
        assert lead.enrichment_json["dropped_reason"] == "suppressed"


# ===========================================================================
# 4. "Remove" stops the lead's sequences; the send refuses a dropped lead
# ===========================================================================


class TestRemovedLead:
    def test_remove_stops_the_sequence_the_lead_is_in(self, client, db_session, enrolled,
                                                      verified_leads):
        lead = verified_leads[0]
        resp = client.patch(f"/leads/{lead.id}", json={"status": "dropped"})
        assert resp.status_code == 200, resp.text
        enrollment = _enrollment(db_session, enrolled, lead)
        assert enrollment.status is m.EnrollmentStatus.STOPPED
        assert enrollment.stop_reason == engine.STOP_LEAD_REMOVED
        assert enrollment.stop_category == "lead_removed"
        pending = db_session.execute(select(m.Message).where(
            m.Message.lead_id == lead.id,
            m.Message.status == m.MessageStatus.SCHEDULED)).scalars().all()
        assert pending == []
        # Other leads are untouched.
        assert _enrollment(db_session, enrolled, verified_leads[1]).status is \
            m.EnrollmentStatus.ACTIVE

    def test_the_send_refuses_a_dropped_lead_whatever_set_the_status(
            self, db_session, enrolled, verified_leads, fake_channel):
        lead = verified_leads[0]
        lead.status = m.LeadStatus.DROPPED   # e.g. a bulk move or another path
        db_session.commit()
        msg = db_session.execute(select(m.Message).where(
            m.Message.lead_id == lead.id)).scalars().first()
        out = tasks.send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert out == "cancelled_lead_removed"
        assert fake_channel.sent == []
        db_session.refresh(msg)
        assert msg.status is m.MessageStatus.CANCELLED
        assert _enrollment(db_session, enrolled, lead).stop_reason == "lead_removed"


# ===========================================================================
# 7. Enroll accepts verified leads only
# ===========================================================================


class TestEnrollableStatuses:
    @pytest.mark.parametrize("status", ["dropped", "flagged", "replied", "contacted"])
    def test_the_api_refuses_other_statuses(self, client, db_session, gmail_account,
                                            email_sequence, verified_leads, fake_claude,
                                            status):
        resp = client.post(f"/sequences/{email_sequence.id}/enroll",
                           json={"lead_statuses": ["verified", status]})
        assert resp.status_code == 422, resp.text
        assert db_session.query(m.SequenceEnrollment).count() == 0

    def test_verified_still_launches(self, client, db_session, gmail_account, email_sequence,
                                     verified_leads, fake_claude):
        resp = client.post(f"/sequences/{email_sequence.id}/enroll",
                           json={"lead_statuses": ["verified"]})
        assert resp.status_code == 202, resp.text
        assert resp.json()["enrolled"] == 3

    def test_the_engine_refuses_them_too(self, db_session, email_sequence, verified_leads):
        verified_leads[0].status = m.LeadStatus.DROPPED
        db_session.commit()
        with pytest.raises(ValueError, match="dropped"):
            engine.enroll_leads(db_session, email_sequence,
                                lead_statuses=[m.LeadStatus.DROPPED], now=NOW)
        assert db_session.query(m.SequenceEnrollment).count() == 0

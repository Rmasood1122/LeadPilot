"""F10 -- Champion Tracker + Staleness Check.

The properties that matter:
  * flag off = the send path is exactly what it was (meta included), no
    provider call, no ledger row; leftover holds are released by the sweep,
  * a recorded departure blocks the old lead AND the old address at the send
    chokepoint, on every channel, even with the flag off (SAFETY GUARD),
  * stale role data HOLDS a message (kept, visible, releasable, audited, the
    sequence lives) and never makes a provider call in the send path,
  * re-verification releases, keeps holding, or records a move -- and only
    ever through the existing lead source + F01 ledger, within the caps,
  * a champion who moved gets a NEW lead at the new company (verified email,
    never the old address) with a job-change plan and no enrollment; opt-outs
    and exclusions carry over,
  * every query is owner-filtered.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import settings
from app.db import models as m
from app.integrations.base import EmailVerificationStatus, EnrichedLead, LeadSource
from app.services import champion_tracker as ct
from app.services import provenance, reengagement_memory, system_settings
from app.services import waterfall_enrichment as wf
from app.workers.outreach_tasks import send_message_impl
from tests.conftest import NOW, FakeVerifier, auth_headers
from tests.test_bounce_shield import _member, _other_account_lead


# --------------------------------------------------------------------------
# Fakes and helpers
# --------------------------------------------------------------------------


class ScriptedSource(LeadSource):
    """A LeadSource whose enrich() answers from a script keyed by the
    provider person id (or email). An Exception value is raised."""

    provider = "apollo"

    def __init__(self):
        self.people: dict = {}
        self.calls: list = []
        self.api_key = "k"
        self.cached = False
        self.last_call = None

    def search(self, icp_criteria, max_leads):
        return []

    def enrich(self, lead):
        self.calls.append(lead.external_id or lead.email)
        answer = self.people.get(lead.external_id) or self.people.get(lead.email)
        if isinstance(answer, Exception):
            raise answer
        self.last_call = {"cached": self.cached, "cost_units": 1}
        payload = {"person": answer} if answer else {}
        return EnrichedLead.from_raw(lead, enrichment=payload)

    def health_check(self):
        return True


def person(title="Owner", company="Co 0", domain="co0.com", email=None, pid="P"):
    return {"id": pid, "name": "Lead 0", "title": title, "email": email,
            "linkedin_url": None,
            "organization": {"name": company, "primary_domain": domain}}


@pytest.fixture()
def source():
    return ScriptedSource()


@pytest.fixture()
def verifier():
    return FakeVerifier()


@pytest.fixture()
def on(db_session):
    system_settings.set(db_session, "champion_tracker_enabled", True)


def make_stale(db, lead, days=100):
    provenance.record(db, lead, "title", provenance.APOLLO, value=lead.title,
                      observed_at=NOW - timedelta(days=days))


def make_fresh(db, lead, days=5):
    make_stale(db, lead, days=days)


def message_for(db, lead):
    return db.execute(select(m.Message).where(m.Message.lead_id == lead.id)
                      .order_by(m.Message.created_at)).scalars().first()


def audit_decisions(db, lead):
    return [r.decision for r in db.execute(select(m.ComplianceAuditLog).where(
        m.ComplianceAuditLog.lead_id == lead.id)).scalars()]


def enrollment_of(db, lead):
    return db.execute(select(m.SequenceEnrollment).where(
        m.SequenceEnrollment.lead_id == lead.id)).scalar_one()


def ledger(db, lead=None):
    q = select(m.EnrichmentAttempt).order_by(m.EnrichmentAttempt.created_at)
    if lead is not None:
        q = q.where(m.EnrichmentAttempt.lead_id == lead.id)
    return db.execute(q).scalars().all()


def sent_meta(db, message):
    return db.execute(select(m.Outcome.meta_json).where(
        m.Outcome.message_id == message.id,
        m.Outcome.event == m.OutcomeEvent.SENT)).scalar_one()


def positive_reply(db, lead):
    db.add(m.InboundReply(lead_id=lead.id, from_address=lead.email or "x@y.com",
                          body="Yes, let's talk", intent_label="interested"))
    db.commit()


def held(db, lead):
    """Send the lead's first message with the flag on and stale data -> held."""
    make_stale(db, lead)
    msg = message_for(db, lead)
    assert send_message_impl(db, msg.id, channel=None, now=NOW) == ct.SEND_RESULT_HELD
    return msg


def another_scheduled(db, lead, sequence):
    msg = m.Message(sequence_id=sequence.id, lead_id=lead.id, channel=m.ChannelType.EMAIL,
                    step_no=9, template="later step", status=m.MessageStatus.SCHEDULED,
                    scheduled_at=NOW)
    db.add(msg)
    db.commit()
    return msg


def move_lead(db, lead, source, verifier, **kw):
    """Record a move for `lead` through the real reverify path."""
    source.people[lead.external_id] = person(title=kw.get("title", "Head of Sales"),
                                             company=kw.get("company", "NewCo"),
                                             domain=kw.get("domain", "newco.com"),
                                             email=kw.get("email", "lead0@newco.com"))
    make_stale(db, lead)
    return ct.reverify(db, lead, source, verifier, trigger="refresh", now=NOW)


# --------------------------------------------------------------------------
# The flag
# --------------------------------------------------------------------------


class TestFlag:
    def test_declared_off_by_default_with_settings(self, db_session):
        default, description = system_settings.DEFAULTS["champion_tracker_enabled"]
        assert default is False and description
        assert ct.enabled(db_session) is False
        assert ct.staleness_days(db_session) == 90
        assert ct.run_cap(db_session) == 100
        assert ct.account_units_cap(db_session) == 200

    def test_is_listed_for_the_admin_panel_and_type_checked(self, db_session):
        keys = {row["key"] for row in system_settings.all_settings(db_session)}
        assert {"champion_tracker_enabled", "champion_staleness_days",
                "champion_refresh_run_cap", "champion_account_monthly_units"} <= keys
        with pytest.raises(system_settings.SettingTypeError):
            system_settings.set(db_session, "champion_tracker_enabled", "yes")

    @pytest.mark.parametrize("stored,effective", [(10, 60), (90, 90), (5000, 365)])
    def test_staleness_is_clamped(self, db_session, stored, effective):
        system_settings.set(db_session, "champion_staleness_days", stored)
        assert ct.staleness_days(db_session) == effective


class TestFlagOff:
    def test_stale_lead_sends_exactly_as_before(self, db_session, enrolled, verified_leads,
                                                fake_channel, source):
        lead = verified_leads[0]
        make_stale(db_session, lead, days=400)
        msg = message_for(db_session, lead)
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"
        assert len(fake_channel.sent) == 1
        assert sent_meta(db_session, msg) == {"step_no": 1, "variant": msg.variant}
        assert ledger(db_session) == [] and source.calls == []

    def test_refresh_makes_no_call(self, db_session, verified_leads, source, verifier):
        lead = verified_leads[0]
        positive_reply(db_session, lead)
        make_stale(db_session, lead)
        out = ct.run_refresh(db_session, source, verifier, now=NOW)
        assert out["skipped"] == "flag off" and source.calls == []

    def test_switching_off_releases_leftover_holds(self, db_session, enrolled, verified_leads,
                                                   source, fake_channel):
        system_settings.set(db_session, "champion_tracker_enabled", True)
        msg = held(db_session, verified_leads[0])
        system_settings.set(db_session, "champion_tracker_enabled", False)
        counts = ct.run_held(db_session, source, None, now=NOW)
        assert counts["released"] == 1 and source.calls == []
        db_session.refresh(msg)
        assert msg.status is m.MessageStatus.SCHEDULED and msg.error is None
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"


# --------------------------------------------------------------------------
# The staleness hold in the chokepoint
# --------------------------------------------------------------------------


@pytest.mark.usefixtures("on")
class TestStalenessHold:
    def test_fresh_role_sends(self, db_session, enrolled, verified_leads, fake_channel):
        lead = verified_leads[0]
        make_fresh(db_session, lead)
        msg = message_for(db_session, lead)
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"

    def test_stale_role_is_held_kept_audited_and_the_sequence_lives(
            self, db_session, enrolled, verified_leads, fake_channel, source):
        lead = verified_leads[0]
        make_stale(db_session, lead, days=100)
        msg = message_for(db_session, lead)
        out = send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert out == "held_role_unverified"
        assert fake_channel.sent == [] and source.calls == [], "no send, no provider call"
        assert msg.status is m.MessageStatus.FAILED
        assert msg.error.startswith(ct.ERROR_PREFIX)
        assert "100 days old (limit 90)" in msg.error
        assert not msg.body, "nothing was rendered"
        assert enrollment_of(db_session, lead).status is m.EnrollmentStatus.ACTIVE
        assert "held_role_unverified" in audit_decisions(db_session, lead)
        assert db_session.execute(select(m.Outcome).where(
            m.Outcome.message_id == msg.id)).first() is None

    def test_age_falls_back_to_the_lead_row(self, db_session, enrolled, verified_leads,
                                            fake_channel):
        lead = verified_leads[0]
        lead.created_at = NOW - timedelta(days=120)
        db_session.commit()
        msg = message_for(db_session, lead)
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == "held_role_unverified"

    def test_a_confirmed_role_check_beats_old_provenance(self, db_session, enrolled,
                                                         verified_leads, fake_channel):
        lead = verified_leads[0]
        make_stale(db_session, lead, days=300)
        ct._set_role_check(lead, state=ct.CURRENT, observed_at=NOW - timedelta(days=10))
        db_session.commit()
        msg = message_for(db_session, lead)
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"

    def test_the_clamp_applies_in_the_send_path(self, db_session, enrolled, verified_leads,
                                                fake_channel):
        system_settings.set(db_session, "champion_staleness_days", 10)   # -> 60
        lead_ok, lead_old = verified_leads[0], verified_leads[1]
        make_stale(db_session, lead_ok, days=50)
        make_stale(db_session, lead_old, days=61)
        assert send_message_impl(db_session, message_for(db_session, lead_ok).id,
                                 channel=fake_channel, now=NOW) == "sent"
        assert send_message_impl(db_session, message_for(db_session, lead_old).id,
                                 channel=fake_channel, now=NOW) == "held_role_unverified"

    def test_a_title_change_is_held_for_a_person(self, db_session, enrolled, verified_leads,
                                                 fake_channel):
        lead = verified_leads[0]
        make_fresh(db_session, lead)
        ct._set_role_check(lead, state=ct.TITLE_CHANGED, observed_title="CFO")
        db_session.commit()
        msg = message_for(db_session, lead)
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == "held_role_unverified"
        assert "confirm the role" in msg.error and "CFO" in msg.error

    def test_suppression_still_runs_first(self, db_session, enrolled, verified_leads,
                                          fake_channel):
        lead = verified_leads[0]
        make_stale(db_session, lead)
        db_session.add(m.SuppressionEntry(email=lead.email, reason="unsubscribed"))
        db_session.commit()
        msg = message_for(db_session, lead)
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == "cancelled_suppressed"


# --------------------------------------------------------------------------
# Re-verification
# --------------------------------------------------------------------------


@pytest.mark.usefixtures("on")
class TestReverify:
    def test_still_in_role_releases_and_the_next_send_goes_out(
            self, db_session, enrolled, verified_leads, fake_channel, source, verifier):
        lead = verified_leads[0]
        msg = held(db_session, lead)
        source.people["L0"] = person()               # same company, same title
        counts = ct.run_held(db_session, source, verifier, now=NOW)
        assert counts["checked"] == 1 and counts["released"] == 1
        assert source.calls == ["L0"]
        db_session.refresh(msg)
        assert msg.status is m.MessageStatus.SCHEDULED
        assert ct.role_check(lead)["state"] == ct.CURRENT
        rows = ledger(db_session, lead)
        assert [(r.step, r.operation, r.outcome, r.cost_units) for r in rows] == [
            ("champion_role", "role_check", "current", 1)]
        assert rows[0].email_domain == "co0.com"
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"

    def test_title_normalisation_counts_rewordings_as_the_same_role(self, db_session,
                                                                     verified_leads):
        lead = verified_leads[0]
        lead.title = "VP of Sales & Marketing"
        assert ct.compare(lead, ct.Person(title="Vice President, Marketing and Sales",
                                          company="Co 0", domain="co0.com")) == ct.CURRENT
        assert ct.compare(lead, ct.Person(title="CFO", company="Co 0",
                                          domain="co0.com")) == ct.TITLE_CHANGED

    def test_a_rebrand_with_the_same_name_is_not_a_move(self, verified_leads):
        lead = verified_leads[0]
        assert ct.compare(lead, ct.Person(title="Owner", company="Co 0",
                                          domain="co0-new.com")) == ct.CURRENT

    def test_merged_adapter_fields_never_confirm_the_old_company(self, verified_leads):
        """No `person` in the payload = not found, even though the adapter's
        merged lead still says the old company."""
        assert ct.read_person({"provider": "x"}) is None
        assert ct.compare(verified_leads[0], None) == ct.NOT_FOUND

    def test_a_cached_answer_counts_as_cache_ttl_old(self, db_session, verified_leads,
                                                     source, verifier):
        lead = verified_leads[0]
        source.people["L0"] = person()
        source.cached = True
        make_stale(db_session, lead)
        ct.reverify(db_session, lead, source, verifier, trigger="manual", now=NOW)
        observed = ct.role_observed_at(lead)
        assert observed == NOW - timedelta(seconds=settings.cache_ttl_enrichment_seconds)
        assert ledger(db_session, lead)[0].cached is True
        assert ledger(db_session, lead)[0].cost_units == 0

    def test_title_change_stays_held(self, db_session, enrolled, verified_leads, source,
                                     verifier):
        lead = verified_leads[0]
        msg = held(db_session, lead)
        source.people["L0"] = person(title="Chief Financial Officer")
        ct.run_held(db_session, source, verifier, now=NOW)
        db_session.refresh(msg)
        assert msg.status is m.MessageStatus.FAILED
        assert ct.role_check(lead)["state"] == ct.TITLE_CHANGED
        assert ct.role_check(lead)["observed_title"] == "Chief Financial Officer"
        # Waiting for a person: the next sweep spends nothing.
        ct.run_held(db_session, source, verifier, now=NOW + timedelta(days=1))
        assert source.calls == ["L0"]

    def test_not_found_stays_held_and_backs_off(self, db_session, enrolled, verified_leads,
                                                source, verifier):
        lead = verified_leads[0]
        msg = held(db_session, lead)
        ct.run_held(db_session, source, verifier, now=NOW)      # nobody in the script
        db_session.refresh(msg)
        assert msg.status is m.MessageStatus.FAILED
        assert ct.role_check(lead)["last_outcome"] == ct.NOT_FOUND
        counts = ct.run_held(db_session, source, verifier, now=NOW + timedelta(days=2))
        assert counts["skipped_backoff"] == 1 and len(source.calls) == 1
        ct.run_held(db_session, source, verifier, now=NOW + timedelta(days=8))
        assert len(source.calls) == 2
        assert "last check: not found" in ct.staleness_hold(db_session, lead, NOW)

    def test_a_provider_error_is_ledgered_and_retried_tomorrow(self, db_session, enrolled,
                                                               verified_leads, source,
                                                               verifier):
        lead = verified_leads[0]
        held(db_session, lead)
        source.people["L0"] = RuntimeError("apollo down")
        out = ct.run_held(db_session, source, verifier, now=NOW)
        assert out["failed"] == 0
        assert [r.outcome for r in ledger(db_session, lead)] == ["error"]
        assert ct.role_check(lead)["last_outcome"] == ct.ERROR
        assert ct.wf._parse(ct.role_check(lead)["retry_after"]) == NOW + timedelta(days=1)

    def test_an_exhausted_budget_makes_no_call(self, db_session, enrolled, verified_leads,
                                               source, verifier):
        system_settings.set(db_session, "champion_account_monthly_units", 0)
        lead = verified_leads[0]
        msg = held(db_session, lead)
        source.people["L0"] = person()
        out = ct.run_held(db_session, source, verifier, now=NOW)
        assert source.calls == [] and out["budget_exhausted"] == 1
        db_session.refresh(msg)
        assert msg.status is m.MessageStatus.FAILED
        assert ct.role_check(lead)["last_outcome"] == ct.BUDGET_EXHAUSTED

    def test_the_budget_is_read_from_the_ledger_window(self, db_session, verified_leads,
                                                       test_user):
        lead = verified_leads[0]
        for age, units, step in [(1, 3, "champion_role"), (40, 50, "champion_role"),
                                 (1, 7, "hunter")]:
            row = m.EnrichmentAttempt(user_id=test_user.id, lead_id=lead.id, step=step,
                                      provider="apollo", operation="role_check",
                                      outcome="current", cached=False, cost_units=units)
            db_session.add(row)
            db_session.flush()
            row.created_at = NOW - timedelta(days=age)
        db_session.commit()
        assert ct.units_used(db_session, test_user.id, NOW) == 3, \
            "only F10 steps, only the last 30 days"

    def test_a_suppressed_person_is_never_looked_up(self, db_session, enrolled,
                                                    verified_leads, source, verifier,
                                                    fake_channel):
        lead = verified_leads[0]
        msg = held(db_session, lead)
        db_session.add(m.SuppressionEntry(email=lead.email, reason="unsubscribed"))
        db_session.commit()
        ct.run_held(db_session, source, verifier, now=NOW)
        assert source.calls == []
        db_session.refresh(msg)
        assert msg.status is m.MessageStatus.SCHEDULED, "released to the chokepoint"
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == "cancelled_suppressed"


# --------------------------------------------------------------------------
# A move: the old address is closed for good
# --------------------------------------------------------------------------


@pytest.mark.usefixtures("on")
class TestDeparture:
    def test_a_move_cancels_every_pending_message_and_stops_the_sequence(
            self, db_session, enrolled, verified_leads, source, verifier):
        lead = verified_leads[0]
        held_msg = held(db_session, lead)
        later = another_scheduled(db_session, lead, enrolled)
        review = another_scheduled(db_session, lead, enrolled)
        review.status = m.MessageStatus.AWAITING_REVIEW
        db_session.commit()
        source.people["L0"] = person(title="Head of Sales", company="NewCo",
                                     domain="newco.com")
        out = ct.run_held(db_session, source, verifier, now=NOW)
        assert out["moves"] == 1
        for msg in (held_msg, later, review):
            db_session.refresh(msg)
            assert msg.status is m.MessageStatus.CANCELLED, msg.error
        assert held_msg.error.startswith(ct.ERROR_PREFIX) and "left Co 0" in held_msg.error
        enrollment = enrollment_of(db_session, lead)
        assert enrollment.status is m.EnrollmentStatus.STOPPED
        assert enrollment.stop_reason == "suppressed_left_company"
        assert enrollment.stop_category == "suppressed"
        assert "left_company_detected" in audit_decisions(db_session, lead)
        move = db_session.execute(select(m.ChampionMove)).scalar_one()
        assert (move.from_company, move.to_company, move.to_domain) == ("Co 0", "NewCo",
                                                                        "newco.com")
        assert move.outcome == ct.NOT_CHAMPION and move.new_lead_id is None
        assert move.old_email_sha256 == wf.email_hash(lead.email)
        assert db_session.execute(select(m.Lead).where(
            m.Lead.source == "champion")).first() is None, "no lead for a non-champion"

    def test_a_new_message_to_the_old_lead_is_cancelled_even_with_the_flag_off(
            self, db_session, enrolled, verified_leads, source, verifier, fake_channel):
        lead = verified_leads[0]
        move_lead(db_session, lead, source, verifier)
        system_settings.set(db_session, "champion_tracker_enabled", False)
        # A step created later on a fresh enrollment, as if re-enrolled.
        enrollment = enrollment_of(db_session, lead)
        enrollment.status = m.EnrollmentStatus.ACTIVE
        msg = another_scheduled(db_session, lead, enrolled)
        out = send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert out == "cancelled_left_company"
        assert fake_channel.sent == []
        assert msg.status is m.MessageStatus.CANCELLED
        assert "blocked_left_company" in audit_decisions(db_session, lead)
        assert enrollment_of(db_session, lead).status is m.EnrollmentStatus.STOPPED

    def test_the_old_address_is_blocked_in_the_accounts_other_campaigns(
            self, db_session, enrolled, verified_leads, verified_strategy, source, verifier,
            fake_channel, product_with_strategy):
        lead = verified_leads[0]
        _, other_strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
        twin = m.Lead(strategy_id=other_strategy.id, source="apollo", external_id="T1",
                      full_name="Lead 0", title="Owner", company="Co 0",
                      email=lead.email.upper(), status=m.LeadStatus.VERIFIED)
        db_session.add(twin)
        db_session.commit()
        move_lead(db_session, lead, source, verifier)
        assert ct.departure_block(db_session, twin, other_strategy) is not None

    def test_another_accounts_lead_with_the_same_address_is_not_blocked(
            self, db_session, enrolled, verified_leads, source, verifier):
        lead = verified_leads[0]
        move_lead(db_session, lead, source, verifier)
        _, other_strategy, other = _other_account_lead(db_session)
        other.email = lead.email
        db_session.commit()
        assert ct.departure_block(db_session, other, other_strategy) is None

    def test_a_lookup_error_defers_the_send(self, db_session, enrolled, verified_leads,
                                            fake_channel, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("db hiccup")

        monkeypatch.setattr(ct, "departure_block", boom)
        msg = message_for(db_session, verified_leads[0])
        out = send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert out == "deferred_champion_check_unavailable"
        assert fake_channel.sent == []
        assert msg.status is m.MessageStatus.SCHEDULED
        assert msg.scheduled_at.replace(tzinfo=NOW.tzinfo) == NOW + timedelta(hours=1)

    def test_the_old_leads_open_plans_are_cancelled(self, db_session, enrolled,
                                                    verified_leads, source, verifier):
        lead = verified_leads[0]
        plan = m.ReengagementPlan(lead_id=lead.id, due_at=NOW + timedelta(days=30),
                                  status="scheduled", reason_kind="timing")
        db_session.add(plan)
        db_session.commit()
        move_lead(db_session, lead, source, verifier)
        db_session.refresh(plan)
        assert plan.status == "cancelled" and "left the company" in plan.cancelled_reason

    def test_recording_is_idempotent(self, db_session, enrolled, verified_leads, source,
                                     verifier):
        lead = verified_leads[0]
        move_lead(db_session, lead, source, verifier)
        again = ct.reverify(db_session, lead, source, verifier, trigger="refresh", now=NOW)
        assert again["outcome"] == "already_moved"
        assert len(db_session.execute(select(m.ChampionMove)).all()) == 1

    def test_dismissing_lifts_the_block_for_future_messages(
            self, db_session, enrolled, verified_leads, source, verifier, fake_channel,
            test_user):
        lead = verified_leads[0]
        move_lead(db_session, lead, source, verifier)
        move = db_session.execute(select(m.ChampionMove)).scalar_one()
        ct.dismiss_move(db_session, move, actor_id=test_user.id, owner_id=test_user.id,
                        reason="still there, spoke today", now=NOW)
        assert "champion_move_dismissed" in audit_decisions(db_session, lead)
        assert ct.departure_block(db_session, lead, db_session.get(
            m.Strategy, lead.strategy_id)) is None
        # The provider still says the same thing: held for a person, not re-decided.
        make_stale(db_session, lead)
        ct._set_role_check(lead, state=None)
        db_session.commit()
        out = ct.reverify(db_session, lead, source, verifier, trigger="refresh", now=NOW)
        assert out["outcome"] == ct.DISPUTED
        assert len(db_session.execute(select(m.ChampionMove)).all()) == 1


# --------------------------------------------------------------------------
# Champions: the re-engagement lead
# --------------------------------------------------------------------------


@pytest.mark.usefixtures("on")
class TestChampionMove:
    def test_a_positive_replier_gets_a_new_verified_lead_and_a_due_plan(
            self, db_session, enrolled, verified_leads, source, verifier, queued_jobs,
            test_user):
        lead = verified_leads[0]
        lead.linkedin_url = "https://www.linkedin.com/in/lead-zero"
        lead.phone = "+15550001111"
        db_session.commit()
        positive_reply(db_session, lead)
        out = move_lead(db_session, lead, source, verifier)
        assert out["outcome"] == ct.LEFT and out["move_outcome"] == ct.LEAD_CREATED
        move = db_session.execute(select(m.ChampionMove)).scalar_one()
        new = db_session.get(m.Lead, move.new_lead_id)
        assert move.champion_kind == ct.POSITIVE_REPLY
        assert (new.source, new.strategy_id, new.external_id) == (
            "champion", lead.strategy_id, None)
        assert (new.title, new.company) == ("Head of Sales", "NewCo")
        assert new.email == "lead0@newco.com" and new.status is m.LeadStatus.VERIFIED
        assert wf.verdict_for(new)["verdict"] == wf.VALID
        assert new.linkedin_url == lead.linkedin_url, "a LinkedIn opt-out still applies"
        assert new.phone is None, "no phone carried over"
        champion = new.enrichment_json["champion"]
        assert champion["from_company"] == "Co 0" and champion["previous_lead_id"] == str(
            lead.id)
        assert ct.role_check(new)["state"] == ct.CURRENT
        assert provenance.field_out(new, "title")["source"] == provenance.APOLLO
        steps = [(r.step, r.operation) for r in ledger(db_session, new)]
        assert ("champion_apollo", "verify") in steps
        # The plan: re-engagement memory, already due, no message, no enrollment.
        plan = db_session.execute(select(m.ReengagementPlan).where(
            m.ReengagementPlan.lead_id == new.id)).scalar_one()
        assert (plan.reason_kind, plan.status, plan.reason_text) == ("job_change", "due",
                                                                      None)
        assert plan.user_id == test_user.id
        assert reengagement_memory.plan_out(db_session, plan)["reason_label"] == "Changed jobs"
        assert any(e[1] == "reengagement_due" for e in queued_jobs["events"])
        assert db_session.execute(select(m.Message).where(
            m.Message.lead_id == new.id)).first() is None
        assert db_session.execute(select(m.SequenceEnrollment).where(
            m.SequenceEnrollment.lead_id == new.id)).first() is None
        # The new lead is a different address: never caught by the old block.
        assert ct.departure_block(db_session, new, db_session.get(
            m.Strategy, new.strategy_id)) is None

    def test_auto_send_never_turns_the_plan_into_a_message(self, db_session, enrolled,
                                                           verified_leads, source,
                                                           verifier):
        system_settings.set(db_session, "reengagement_memory_auto_send", True)
        lead = verified_leads[0]
        positive_reply(db_session, lead)
        move_lead(db_session, lead, source, verifier)
        new_id = db_session.execute(select(m.ChampionMove.new_lead_id)).scalar_one()
        reengagement_memory.run_due(db_session, now=NOW + timedelta(days=1))
        assert db_session.execute(select(m.Message).where(
            m.Message.lead_id == new_id)).first() is None

    def test_the_job_change_brief_never_claims_they_said_something(self, db_session,
                                                                   enrolled, verified_leads,
                                                                   source, verifier):
        lead = verified_leads[0]
        positive_reply(db_session, lead)
        move_lead(db_session, lead, source, verifier)
        new = db_session.get(m.Lead, db_session.execute(
            select(m.ChampionMove.new_lead_id)).scalar_one())
        plan = db_session.execute(select(m.ReengagementPlan).where(
            m.ReengagementPlan.lead_id == new.id)).scalar_one()
        brief = reengagement_memory.brief_for(plan, new)
        assert "JOB CHANGE" in brief and "They said" not in brief
        assert "Owner at Co 0" in brief and "Head of Sales at NewCo" in brief

    @pytest.mark.parametrize("how", ["closed_won", "deal"])
    def test_a_customer_is_a_champion(self, db_session, enrolled, verified_leads, source,
                                      verifier, test_user, how):
        lead = verified_leads[0]
        if how == "closed_won":
            lead.status = m.LeadStatus.CLOSED_WON
        else:
            db_session.add(m.Deal(user_id=test_user.id, lead_id=lead.id, name="d",
                                  stage=m.DealStage.WON))
        db_session.commit()
        move_lead(db_session, lead, source, verifier)
        move = db_session.execute(select(m.ChampionMove)).scalar_one()
        assert move.champion_kind == ct.CUSTOMER and move.outcome == ct.LEAD_CREATED

    def test_the_old_address_is_never_the_new_one(self, db_session, enrolled,
                                                  verified_leads, source, verifier):
        lead = verified_leads[0]
        positive_reply(db_session, lead)
        move_lead(db_session, lead, source, verifier, email=lead.email)
        new = db_session.get(m.Lead, db_session.execute(
            select(m.ChampionMove.new_lead_id)).scalar_one())
        assert new.email != lead.email
        assert new.email == "lead.0@newco.com", "found by the Hunter step instead"
        assert ("champion_hunter", "find_email") in [(r.step, r.operation)
                                                     for r in ledger(db_session, new)]

    def test_an_undeliverable_new_address_is_not_stored(self, db_session, enrolled,
                                                        verified_leads, source, verifier):
        lead = verified_leads[0]
        positive_reply(db_session, lead)
        verifier.verdicts["lead0@newco.com"] = EmailVerificationStatus.UNDELIVERABLE
        verifier.findable[("Lead 0", "newco.com")] = None
        move_lead(db_session, lead, source, verifier)
        move = db_session.execute(select(m.ChampionMove)).scalar_one()
        new = db_session.get(m.Lead, move.new_lead_id)
        assert new.email is None and new.status is m.LeadStatus.ENRICHED
        assert move.outcome == ct.LEAD_CREATED
        assert "no deliverable address" in move.detail

    def test_no_verifier_means_no_email(self, db_session, enrolled, verified_leads, source):
        lead = verified_leads[0]
        positive_reply(db_session, lead)
        move_lead(db_session, lead, source, None)
        new = db_session.get(m.Lead, db_session.execute(
            select(m.ChampionMove.new_lead_id)).scalar_one())
        assert new.email is None and new.status is m.LeadStatus.ENRICHED

    def test_an_unsubscribe_carries_over_to_the_new_address(self, db_session, enrolled,
                                                            verified_leads, source,
                                                            verifier):
        lead = verified_leads[0]
        positive_reply(db_session, lead)
        db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.UNSUBSCRIBED,
                                 channel="email"))
        db_session.commit()
        move_lead(db_session, lead, source, verifier)
        move = db_session.execute(select(m.ChampionMove)).scalar_one()
        assert move.outcome == ct.SUPPRESSED and move.new_lead_id is None
        assert db_session.execute(select(m.Lead).where(
            m.Lead.source == "champion")).first() is None
        row = db_session.execute(select(m.SuppressionEntry).where(
            m.SuppressionEntry.email == "lead0@newco.com")).scalar_one()
        assert row.reason == "opt_out_carried_over"

    def test_a_suppressed_new_address_drops_the_person(self, db_session, enrolled,
                                                       verified_leads, source, verifier):
        lead = verified_leads[0]
        positive_reply(db_session, lead)
        db_session.add(m.SuppressionEntry(email="lead0@newco.com", reason="unsubscribed"))
        db_session.commit()
        move_lead(db_session, lead, source, verifier)
        move = db_session.execute(select(m.ChampionMove)).scalar_one()
        new = db_session.get(m.Lead, move.new_lead_id)
        assert move.outcome == ct.SUPPRESSED
        assert new.status is m.LeadStatus.DROPPED and new.email is None
        assert db_session.execute(select(m.ReengagementPlan).where(
            m.ReengagementPlan.lead_id == new.id)).first() is None

    def test_a_linkedin_opt_out_means_no_lookup_at_all(self, db_session, enrolled,
                                                       verified_leads, source, verifier):
        lead = verified_leads[0]
        lead.linkedin_url = "https://www.linkedin.com/in/lead-zero"
        db_session.add(m.LinkedInSuppression(profile="lead-zero", reason="opted_out"))
        db_session.commit()
        positive_reply(db_session, lead)
        out = move_lead(db_session, lead, source, verifier)
        assert out["outcome"] == "suppressed" and source.calls == []

    @pytest.mark.parametrize("what", ["new_domain", "contact"])
    def test_guardrail_exclusions_are_respected(self, db_session, enrolled, verified_leads,
                                                source, verifier, test_user, what):
        from app.services import guardrails

        system_settings.set(db_session, "guardrails_enabled", True)
        lead = verified_leads[0]
        positive_reply(db_session, lead)
        if what == "new_domain":
            guardrails.add_exclusion(db_session, test_user.id, "domain", "newco.com",
                                     reason="customer")
        else:
            guardrails.add_exclusion(db_session, test_user.id, "contact", lead.email,
                                     reason="do_not_contact")
        out = move_lead(db_session, lead, source, verifier)
        move = db_session.execute(select(m.ChampionMove)).scalar_one()
        assert move.outcome == ct.EXCLUDED, out
        assert move.new_lead_id is None

    def test_the_old_company_being_a_customer_does_not_stop_the_champion(
            self, db_session, enrolled, verified_leads, source, verifier, test_user):
        """F05's customer list holds the OLD company of a customer champion --
        that is exactly the case this feature exists for."""
        from app.services import guardrails

        system_settings.set(db_session, "guardrails_enabled", True)
        lead = verified_leads[0]
        lead.status = m.LeadStatus.CLOSED_WON
        db_session.commit()
        guardrails.add_exclusion(db_session, test_user.id, "domain", "co0.com",
                                 reason="customer")
        move_lead(db_session, lead, source, verifier)
        move = db_session.execute(select(m.ChampionMove)).scalar_one()
        assert move.outcome == ct.LEAD_CREATED and move.new_lead_id is not None

    def test_an_existing_lead_at_the_new_company_is_linked_not_duplicated(
            self, db_session, enrolled, verified_leads, verified_strategy, source,
            verifier):
        lead = verified_leads[0]
        positive_reply(db_session, lead)
        existing = m.Lead(strategy_id=verified_strategy.id, source="apollo",
                          external_id="E1", full_name="Lead 0", email="lead0@newco.com",
                          company="NewCo", status=m.LeadStatus.VERIFIED)
        db_session.add(existing)
        db_session.commit()
        move_lead(db_session, lead, source, verifier)
        move = db_session.execute(select(m.ChampionMove)).scalar_one()
        assert (move.outcome, move.new_lead_id) == (ct.EXISTING_LEAD, existing.id)
        assert db_session.execute(select(m.Lead).where(
            m.Lead.source == "champion")).first() is None

    def test_a_champion_lead_moving_again_is_tracked_by_its_inherited_kind(
            self, db_session, enrolled, verified_leads, source, verifier):
        lead = verified_leads[0]
        positive_reply(db_session, lead)
        move_lead(db_session, lead, source, verifier)
        new = db_session.get(m.Lead, db_session.execute(
            select(m.ChampionMove.new_lead_id)).scalar_one())
        owner = ct._owner_of_lead(db_session, new)
        assert ct.champion_kind(db_session, new, owner) == ct.POSITIVE_REPLY
        assert new.id in ct.champion_lead_ids(db_session, owner)


# --------------------------------------------------------------------------
# The scheduled refresh
# --------------------------------------------------------------------------


@pytest.mark.usefixtures("on")
class TestRefresh:
    def test_only_stale_champions_oldest_first_within_the_run_cap(
            self, db_session, verified_leads, source, verifier):
        a, b, c = verified_leads
        positive_reply(db_session, a)
        positive_reply(db_session, b)
        make_stale(db_session, a, days=100)
        make_stale(db_session, b, days=200)
        make_stale(db_session, c, days=300)             # not a champion
        for lead in (a, b):
            source.people[lead.external_id] = person(company=lead.company,
                                                     domain=f"co{lead.external_id[1]}.com")
        system_settings.set(db_session, "champion_refresh_run_cap", 1)
        out = ct.run_refresh(db_session, source, verifier, now=NOW)
        assert out["checked"] == 1 and source.calls == ["L1"], "the oldest champion first"
        system_settings.set(db_session, "champion_refresh_run_cap", 100)
        ct.run_refresh(db_session, source, verifier, now=NOW)
        assert source.calls == ["L1", "L0"]
        # Idempotent: everything is fresh now; a re-run spends nothing.
        out = ct.run_refresh(db_session, source, verifier, now=NOW)
        assert out["checked"] == 0 and source.calls == ["L1", "L0"]

    def test_the_account_cap_stops_an_account(self, db_session, verified_leads, source,
                                              verifier):
        system_settings.set(db_session, "champion_account_monthly_units", 1)
        for lead in verified_leads:
            lead.status = m.LeadStatus.CLOSED_WON
            make_stale(db_session, lead)
            source.people[lead.external_id] = person(company=lead.company,
                                                     domain=f"co{lead.external_id[1]}.com")
        db_session.commit()
        out = ct.run_refresh(db_session, source, verifier, now=NOW)
        assert out["checked"] == 1 and out["budget_exhausted"] == 1
        assert len(source.calls) == 1

    def test_candidates_are_owner_filtered(self, db_session, verified_leads, test_user):
        user, _, other_lead = _other_account_lead(db_session)
        other_lead.status = m.LeadStatus.CLOSED_WON
        make_stale(db_session, other_lead)
        positive_reply(db_session, verified_leads[0])
        make_stale(db_session, verified_leads[0])
        mine = {lead.id for lead in ct.refresh_candidates(db_session, test_user.id, NOW)}
        theirs = {lead.id for lead in ct.refresh_candidates(db_session, user.id, NOW)}
        assert mine == {verified_leads[0].id} and theirs == {other_lead.id}

    def test_moved_and_suppressed_champions_are_skipped(self, db_session, enrolled,
                                                        verified_leads, source, verifier,
                                                        test_user):
        a, b, _ = verified_leads
        for lead in (a, b):
            positive_reply(db_session, lead)
        move_lead(db_session, a, source, verifier)
        make_stale(db_session, b)
        db_session.add(m.SuppressionEntry(email=b.email, reason="unsubscribed"))
        db_session.commit()
        ids = {lead.id for lead in ct.refresh_candidates(db_session, test_user.id, NOW)}
        assert a.id not in ids and b.id not in ids

    def test_no_credentials_means_no_run(self, db_session, verified_leads, source, verifier):
        source.api_key = ""
        out = ct.run_refresh(db_session, source, verifier, now=NOW)
        assert out["skipped"] == "no lead source credentials"


# --------------------------------------------------------------------------
# GDPR
# --------------------------------------------------------------------------


@pytest.mark.usefixtures("on")
def test_gdpr_delete_scrubs_the_move(client, db_session, enrolled, verified_leads, source,
                                     verifier):
    lead = verified_leads[0]
    positive_reply(db_session, lead)
    move_lead(db_session, lead, source, verifier)
    r = client.delete(f"/leads/{lead.id}")
    assert r.status_code == 204, r.text
    move = db_session.execute(select(m.ChampionMove)).scalar_one()
    db_session.refresh(move)
    assert (move.from_company, move.from_title, move.to_company, move.to_title,
            move.to_domain, move.old_email_sha256) == (None,) * 6
    assert move.outcome == ct.LEAD_CREATED, "the tombstone keeps the count"


@pytest.mark.usefixtures("on")
def test_gdpr_delete_of_the_new_lead_keeps_the_old_address_closed(
        client, db_session, enrolled, verified_leads, source, verifier,
        product_with_strategy, fake_channel):
    """Erasing the re-engagement lead erases the old lead too (same person);
    the old address then stays closed through the GDPR suppression, including
    for another campaign's lead that still carries it."""
    from app.workers.lead_tasks import is_suppressed

    lead = verified_leads[0]
    old_email = lead.email
    positive_reply(db_session, lead)
    move_lead(db_session, lead, source, verifier)
    move = db_session.execute(select(m.ChampionMove)).scalar_one()
    assert client.delete(f"/leads/{move.new_lead_id}").status_code == 204
    db_session.refresh(move)
    assert move.to_company is None and move.from_company is None
    assert is_suppressed(db_session, email=old_email)
    _, other_strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
    twin = m.Lead(strategy_id=other_strategy.id, source="apollo", external_id="T2",
                  email=old_email, status=m.LeadStatus.VERIFIED)
    db_session.add(twin)
    db_session.commit()
    assert is_suppressed(db_session, email=twin.email)


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


@pytest.fixture()
def api_providers(monkeypatch, source, verifier):
    monkeypatch.setattr("app.api.champions._get_source", lambda: source)
    monkeypatch.setattr("app.api.champions._get_verifier", lambda: verifier)
    return source, verifier


class TestApi:
    def test_role_check_shape_with_the_flag_off(self, client, db_session, verified_leads):
        lead = verified_leads[0]
        make_stale(db_session, lead)
        body = client.get(f"/leads/{lead.id}/role-check").json()
        assert body["enabled"] is False
        assert body["send_decision"]["would_send"] is True
        assert "re-verification queued" in body["send_decision"]["would_hold_if_enabled"]
        assert body["move"] is None and body["held_messages"] == []
        assert body["settings"]["staleness_days"] == 90

    def test_another_accounts_lead_and_move_are_404_everywhere(self, client, db_session,
                                                              api_providers, test_user):
        system_settings.set(db_session, "champion_tracker_enabled", True)
        user, _, lead = _other_account_lead(db_session)
        move = m.ChampionMove(user_id=user.id, old_lead_id=lead.id, trigger="refresh",
                              outcome="not_champion", detected_at=NOW)
        db_session.add(move)
        db_session.commit()
        assert client.get(f"/leads/{lead.id}/role-check").status_code == 404
        assert client.post(f"/leads/{lead.id}/role-check/refresh").status_code == 404
        assert client.post(f"/leads/{lead.id}/role-check/confirm",
                           json={"reason": "I know them"}).status_code == 404
        assert client.post(f"/champions/moves/{move.id}/dismiss",
                           json={"reason": "not right"}).status_code == 404
        assert client.get("/champions/moves").json()["total"] == 0
        assert api_providers[0].calls == []

    def test_refresh_is_409_with_the_flag_off(self, client, verified_leads, api_providers):
        r = client.post(f"/leads/{verified_leads[0].id}/role-check/refresh")
        assert r.status_code == 409 and api_providers[0].calls == []

    def test_refresh_runs_one_check(self, client, db_session, enrolled, verified_leads,
                                    api_providers):
        system_settings.set(db_session, "champion_tracker_enabled", True)
        lead = verified_leads[0]
        held(db_session, lead)
        api_providers[0].people["L0"] = person()
        body = client.post(f"/leads/{lead.id}/role-check/refresh").json()
        assert body["result"]["outcome"] == "current" and body["result"]["released"] == 1
        assert body["state"] == "current" and body["held_messages"] == []
        assert body["attempts"][0]["step"] == "champion_role"

    def test_confirm_releases_and_can_adopt_the_new_title(self, client, db_session,
                                                          enrolled, verified_leads):
        system_settings.set(db_session, "champion_tracker_enabled", True)
        lead = verified_leads[0]
        msg = held(db_session, lead)
        ct._set_role_check(lead, state=ct.TITLE_CHANGED, observed_title="Owner & CEO")
        db_session.commit()
        r = client.post(f"/leads/{lead.id}/role-check/confirm",
                        json={"reason": "Spoke to her this week", "adopt_title": True})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["released_messages"] == 1 and body["adopted_title"] == "Owner & CEO"
        assert body["state"] == "confirmed" and body["send_decision"]["would_send"] is True
        db_session.refresh(lead)
        db_session.refresh(msg)
        assert lead.title == "Owner & CEO" and msg.status is m.MessageStatus.SCHEDULED
        assert provenance.field_out(lead, "title")["source"] == provenance.MANUAL
        assert "role_check_confirmed" in audit_decisions(db_session, lead)

    def test_confirm_needs_a_manager_and_a_reason(self, client, db_session, verified_leads,
                                                  test_user):
        lead = verified_leads[0]
        sdr = _member(db_session, test_user, "sdr")
        r = client.post(f"/leads/{lead.id}/role-check/confirm",
                        json={"reason": "I know them"}, headers=sdr)
        assert r.status_code == 403
        r = client.post(f"/leads/{lead.id}/role-check/confirm", json={"reason": "ok"})
        assert r.status_code == 422

    def test_confirm_is_refused_for_a_departed_prospect(self, client, db_session, enrolled,
                                                       verified_leads, source, verifier):
        system_settings.set(db_session, "champion_tracker_enabled", True)
        lead = verified_leads[0]
        move_lead(db_session, lead, source, verifier)
        r = client.post(f"/leads/{lead.id}/role-check/confirm",
                        json={"reason": "I think they are back"})
        assert r.status_code == 409

    def test_moves_list_dismiss_and_rbac(self, client, db_session, enrolled, verified_leads,
                                         source, verifier, test_user):
        system_settings.set(db_session, "champion_tracker_enabled", True)
        lead = verified_leads[0]
        positive_reply(db_session, lead)
        move_lead(db_session, lead, source, verifier)
        body = client.get("/champions/moves").json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["to_company"] == "NewCo" and item["new_lead"]["company"] == "NewCo"
        assert item["outcome"] == "lead_created"
        sdr = _member(db_session, test_user, "sdr")
        r = client.post(f"/champions/moves/{item['id']}/dismiss",
                        json={"reason": "wrong person"}, headers=sdr)
        assert r.status_code == 403
        r = client.post(f"/champions/moves/{item['id']}/dismiss",
                        json={"reason": "wrong person matched"})
        assert r.status_code == 200 and r.json()["dismissed_at"]
        r = client.post(f"/champions/moves/{item['id']}/dismiss",
                        json={"reason": "wrong person matched"})
        assert r.status_code == 409

    def test_held_list(self, client, db_session, enrolled, verified_leads):
        system_settings.set(db_session, "champion_tracker_enabled", True)
        held(db_session, verified_leads[0])
        body = client.get("/champions/held").json()
        assert body["total"] == 1
        assert body["items"][0]["lead"]["company"] == "Co 0"
        assert "re-verification queued" in body["items"][0]["reason"]

    def test_metrics_count_sends_after_departure_and_reengagements(
            self, client, db_session, enrolled, verified_leads, source, verifier):
        system_settings.set(db_session, "champion_tracker_enabled", True)
        lead = verified_leads[0]
        positive_reply(db_session, lead)
        msg = message_for(db_session, lead)
        move_lead(db_session, lead, source, verifier)
        body = client.get("/champions/metrics").json()
        assert body["champion_reengagements"] == 1
        assert body["by_outcome"]["lead_created"] == 1
        assert body["sends_after_departure"] == 0
        # A send recorded after the departure (say, by a path that bypassed the
        # guard) is exactly what the metric must surface.
        msg.status = m.MessageStatus.SENT
        msg.sent_at = NOW + timedelta(minutes=5)
        db_session.add(m.Outcome(lead_id=lead.id, message_id=msg.id,
                                 event=m.OutcomeEvent.SENT, channel="email"))
        db_session.commit()
        body = client.get("/champions/metrics").json()
        assert body["sends_after_departure"] == 1
        assert body["budget"]["units_used_30d"] >= 1


def test_beat_runs_both_sweeps_on_the_default_queue():
    import app.workers.champion_tasks  # noqa: F401 -- importing registers the tasks
    from app.workers.celery_app import celery_app

    assert "app.workers.champion_tasks" in celery_app.conf.include

    schedule = celery_app.conf.beat_schedule
    assert schedule["champion-reverify-held"]["task"] == "leadpilot.champion.reverify_held"
    assert schedule["champion-refresh"]["task"] == "leadpilot.champion.refresh"
    assert celery_app.conf.task_routes["leadpilot.champion.*"] == {"queue": "default"}
    assert {"leadpilot.champion.reverify_held", "leadpilot.champion.refresh"} <= set(
        celery_app.tasks)


def test_the_manual_ai_call_refuses_a_departed_prospect(client, db_session, verified_strategy,
                                                       test_user, monkeypatch):
    """The one cold contact path outside send_message_impl (POST /leads/{id}/call)
    carries the departure block too -- before any provider is touched."""
    from datetime import UTC, datetime

    system_settings.set(db_session, "phone_calling_enabled", True)
    test_user.plan = m.PlanTier.SCALE
    lead = m.Lead(strategy_id=verified_strategy.id, source="apollo", external_id="PH9",
                  full_name="Sara Khan", company="Acme Fire", phone="+1 (555) 010-2000",
                  status=m.LeadStatus.VERIFIED, phone_consent_at=datetime.now(UTC),
                  phone_consent_source="web form")
    db_session.add(lead)
    db_session.flush()
    db_session.add(m.ChampionMove(user_id=test_user.id, old_lead_id=lead.id, trigger="refresh",
                                  outcome="not_champion", detected_at=NOW))
    db_session.commit()

    def no_provider(*a, **k):
        raise AssertionError("a provider was reached")

    monkeypatch.setattr("app.integrations.voice_providers.get_clients", no_provider)
    r = client.post(f"/leads/{lead.id}/call", json={})
    assert r.status_code == 409 and "left the company" in r.json()["detail"]


# ==========================================================================
# Review fixes (independent review of 33fb67c). Each test fails without its fix.
# ==========================================================================


def _msgs(db, lead):
    return db.execute(select(m.Message).where(m.Message.lead_id == lead.id)
                      .order_by(m.Message.step_no, m.Message.created_at)).scalars().all()


def _first_step_sent(db, lead, fake_channel):
    make_fresh(db, lead)
    first = message_for(db, lead)
    assert send_message_impl(db, first.id, channel=fake_channel, now=NOW) == "sent"
    return [x for x in _msgs(db, lead) if x.step_no == 2][0]


class TestReviewHoldsAreNotDuplicated:
    """(H1) A held step must count as pending for the follow-up sweep, and a
    release must put back at most one message per (sequence, step)."""

    def test_reviewer_repro_followup_sweep_never_double_sends_a_held_step(
            self, db_session, enrolled, verified_leads, fake_channel):
        from app.workers import outreach_tasks as ot

        lead = verified_leads[0]
        step2 = _first_step_sent(db_session, lead, fake_channel)
        system_settings.set(db_session, "champion_tracker_enabled", True)
        make_stale(db_session, lead)
        later = NOW + timedelta(days=4)
        step2.scheduled_at = later
        db_session.commit()
        assert send_message_impl(db_session, step2.id, channel=fake_channel,
                                 now=later) == ct.SEND_RESULT_HELD
        enrollment = enrollment_of(db_session, lead)
        for _ in range(3):              # the sweep runs again and again while held
            due = ot.check_followup_due_impl(db_session, now=later, enqueue=lambda *a: None)
            for eid, step in due:
                if eid == str(enrollment.id):
                    ot.send_followup_impl(db_session, enrollment.id, step, now=later)
        ct.confirm(db_session, lead, actor_id=None,
                   owner_id=ct._owner_of_lead(db_session, lead), reason="checked", now=later)
        for x in _msgs(db_session, lead):
            if x.status is m.MessageStatus.SCHEDULED:
                for hours in range(0, 24 * 7):
                    t = later + timedelta(hours=hours)
                    x.scheduled_at = t
                    db_session.commit()
                    if not send_message_impl(db_session, x.id, channel=fake_channel,
                                             now=t).startswith("deferred"):
                        break
        step2_sent = [x for x in _msgs(db_session, lead)
                      if x.step_no == 2 and x.status is m.MessageStatus.SENT]
        assert len(step2_sent) == 1, f"step 2 sent {len(step2_sent)} times"

    def test_a_champion_hold_is_pending_for_the_followup_sweep(
            self, db_session, enrolled, verified_leads, fake_channel):
        from app.workers import outreach_tasks as ot

        lead = verified_leads[0]
        step2 = _first_step_sent(db_session, lead, fake_channel)
        ct.hold_message(step2, "role data is old")
        db_session.commit()
        later = NOW + timedelta(days=10)
        due = ot.check_followup_due_impl(db_session, now=later, enqueue=lambda *a: None)
        assert str(enrollment_of(db_session, lead).id) not in {eid for eid, _ in due}

    def test_an_f01_bounce_shield_hold_is_pending_for_the_followup_sweep(
            self, db_session, enrolled, verified_leads, fake_channel):
        """The same flaw existed for F01's FAILED + 'bounce_shield: ' hold."""
        from app.services import bounce_shield
        from app.workers import outreach_tasks as ot

        lead = verified_leads[0]
        step2 = _first_step_sent(db_session, lead, fake_channel)
        system_settings.set(db_session, "bounce_shield_enabled", True)
        step2.scheduled_at = NOW + timedelta(days=3)
        db_session.commit()
        assert send_message_impl(db_session, step2.id, channel=fake_channel,
                                 now=NOW + timedelta(days=3)) == bounce_shield.SEND_RESULT
        later = NOW + timedelta(days=10)
        due = ot.check_followup_due_impl(db_session, now=later, enqueue=lambda *a: None)
        assert str(enrollment_of(db_session, lead).id) not in {eid for eid, _ in due}
        enrollment = enrollment_of(db_session, lead)
        assert ot.send_followup_impl(db_session, enrollment.id, 2,
                                     now=later) == "skipped_already_pending"

    @pytest.mark.parametrize("which", ["champion", "bounce_shield"])
    def test_release_puts_back_one_message_per_step_and_cancels_copies(
            self, db_session, enrolled, verified_leads, which):
        from app.services import bounce_shield

        lead = verified_leads[0]
        first = message_for(db_session, lead)
        prefix = ct.ERROR_PREFIX if which == "champion" else bounce_shield.ERROR_PREFIX
        copies = []
        for _ in range(3):
            copy = another_scheduled(db_session, lead, enrolled)
            copy.step_no = 2
            copy.status = m.MessageStatus.FAILED
            copy.error = f"{prefix}held"
            copies.append(copy)
        first.status = m.MessageStatus.FAILED
        first.error = f"{prefix}held"
        db_session.commit()
        if which == "champion":
            released = ct.release_held(db_session, lead, NOW)
        else:
            released = bounce_shield.requeue_blocked(db_session, lead, NOW)
        assert released == 2, "one for step 1, one for step 2"
        for msg in copies + [first]:
            db_session.refresh(msg)
        step2 = [c.status for c in copies]
        assert step2.count(m.MessageStatus.SCHEDULED) == 1
        assert step2.count(m.MessageStatus.CANCELLED) == 2
        assert first.status is m.MessageStatus.SCHEDULED

    def test_a_held_copy_of_a_step_that_already_went_out_is_cancelled(
            self, db_session, enrolled, verified_leads, fake_channel):
        lead = verified_leads[0]
        make_fresh(db_session, lead)
        first = message_for(db_session, lead)
        assert send_message_impl(db_session, first.id, channel=fake_channel, now=NOW) == "sent"
        copy = another_scheduled(db_session, lead, enrolled)
        copy.step_no = 1
        ct.hold_message(copy, "old")
        db_session.commit()
        assert ct.release_held(db_session, lead, NOW) == 0
        db_session.refresh(copy)
        assert copy.status is m.MessageStatus.CANCELLED


class TestReviewErasedAndDroppedLeads:
    """(H2) An erased or dropped lead is never looked up, never written to."""

    def test_reviewer_repro_an_erased_lead_with_a_held_message_is_not_reenriched(
            self, db_session, enrolled, verified_leads, client, fake_channel):
        lead = verified_leads[0]
        system_settings.set(db_session, "champion_tracker_enabled", True)
        msg = held(db_session, lead)
        assert client.delete(f"/leads/{lead.id}").status_code == 204
        db_session.expire_all()
        lead = db_session.get(m.Lead, lead.id)
        db_session.refresh(msg)
        assert msg.status is m.MessageStatus.CANCELLED, "erasure cancels the hold"
        src = ScriptedSource()
        src.people[lead.external_id] = person(title="CTO", company="Erased Person Inc",
                                              domain="x.com")
        ct.run_held(db_session, src, None, now=NOW + timedelta(minutes=15))
        assert src.calls == [], "provider called for an erased person"
        db_session.expire_all()
        assert db_session.get(m.Lead, lead.id).enrichment_json == {"gdpr_deleted": True}

    @pytest.mark.usefixtures("on")
    def test_reverify_refuses_an_erased_lead_and_writes_nothing(self, db_session,
                                                                verified_leads, source):
        lead = verified_leads[0]
        lead.enrichment_json = {"gdpr_deleted": True}
        lead.status = m.LeadStatus.DROPPED
        db_session.commit()
        source.people["L0"] = person()
        out = ct.reverify(db_session, lead, source, None, trigger="manual", now=NOW)
        assert out["outcome"] == "erased" and source.calls == []
        db_session.refresh(lead)
        assert lead.enrichment_json == {"gdpr_deleted": True}
        assert ledger(db_session, lead) == []

    @pytest.mark.usefixtures("on")
    def test_a_dropped_lead_with_a_held_message_is_cancelled_not_looked_up(
            self, db_session, enrolled, verified_leads, source):
        lead = verified_leads[0]
        msg = held(db_session, lead)
        lead.status = m.LeadStatus.DROPPED
        db_session.commit()
        source.people["L0"] = person()
        ct.run_held(db_session, source, None, now=NOW)
        assert source.calls == []
        db_session.refresh(msg)
        assert msg.status is m.MessageStatus.CANCELLED
        assert ct.ROLE_KEY not in (lead.enrichment_json or {})

    def test_the_refresh_endpoint_refuses_an_erased_lead(self, client, db_session,
                                                         verified_leads, api_providers):
        system_settings.set(db_session, "champion_tracker_enabled", True)
        lead = verified_leads[0]
        assert client.delete(f"/leads/{lead.id}").status_code == 204
        r = client.post(f"/leads/{lead.id}/role-check/refresh")
        assert r.status_code == 409 and api_providers[0].calls == []


@pytest.mark.usefixtures("on")
class TestReviewThePersonNotTheRecord:
    """(M3) Erasure and opt-outs reach the derived re-engagement lead."""

    def _moved(self, db, lead, source, verifier):
        positive_reply(db, lead)
        move_lead(db, lead, source, verifier)
        move = db.execute(select(m.ChampionMove)).scalar_one()
        return move, db.get(m.Lead, move.new_lead_id)

    def test_erasing_the_old_lead_erases_the_derived_lead(self, client, db_session, enrolled,
                                                          verified_leads, source, verifier):
        move, new = self._moved(db_session, verified_leads[0], source, verifier)
        new_email = new.email
        assert client.delete(f"/leads/{verified_leads[0].id}").status_code == 204
        db_session.expire_all()
        new = db_session.get(m.Lead, move.new_lead_id)
        assert (new.email, new.full_name, new.linkedin_url) == (None, None, None)
        assert new.enrichment_json == {"gdpr_deleted": True}
        assert db_session.execute(select(m.SuppressionEntry).where(
            m.SuppressionEntry.email == new_email)).scalar_one().reason == "gdpr_delete"

    def test_erasing_the_derived_lead_erases_the_old_lead(self, client, db_session, enrolled,
                                                          verified_leads, source, verifier):
        move, new = self._moved(db_session, verified_leads[0], source, verifier)
        assert client.delete(f"/leads/{new.id}").status_code == 204
        db_session.expire_all()
        old = db_session.get(m.Lead, move.old_lead_id)
        assert old.email is None and old.enrichment_json == {"gdpr_deleted": True}

    def test_an_unsubscribe_on_the_old_lead_after_the_move_blocks_the_derived_lead(
            self, db_session, enrolled, verified_leads, source, verifier, fake_channel,
            email_sequence):
        move, new = self._moved(db_session, verified_leads[0], source, verifier)
        db_session.add(m.Outcome(lead_id=verified_leads[0].id,
                                 event=m.OutcomeEvent.UNSUBSCRIBED, channel="email"))
        db_session.add(m.SequenceEnrollment(sequence_id=email_sequence.id, lead_id=new.id,
                                            status=m.EnrollmentStatus.ACTIVE))
        db_session.commit()
        system_settings.set(db_session, "champion_tracker_enabled", False)
        msg = another_scheduled(db_session, new, email_sequence)
        out = send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert out == "cancelled_suppressed" and fake_channel.sent == []
        assert "earlier record" in msg.error
        assert enrollment_of(db_session, new).status is m.EnrollmentStatus.STOPPED

    def test_a_suppression_of_the_old_address_after_the_move_blocks_the_derived_lead(
            self, db_session, enrolled, verified_leads, source, verifier, fake_channel,
            email_sequence):
        move, new = self._moved(db_session, verified_leads[0], source, verifier)
        db_session.add(m.SuppressionEntry(email=verified_leads[0].email, reason="unsubscribed"))
        db_session.add(m.SequenceEnrollment(sequence_id=email_sequence.id, lead_id=new.id,
                                            status=m.EnrollmentStatus.ACTIVE))
        db_session.commit()
        msg = another_scheduled(db_session, new, email_sequence)
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == "cancelled_suppressed"
        assert fake_channel.sent == []
        assert ct.reverify(db_session, new, source, verifier, trigger="refresh",
                           now=NOW)["outcome"] == "suppressed"


def test_review_an_unresolvable_owner_defers_the_send(db_session, enrolled, verified_leads,
                                                      fake_channel, monkeypatch):
    """(L1) Fails closed: no owner, no proof the person is still there."""
    monkeypatch.setattr("app.services.notifications.owner_of_strategy", lambda *a, **k: None)
    msg = message_for(db_session, verified_leads[0])
    out = send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
    assert out == ct.SEND_RESULT_DEFERRED and fake_channel.sent == []
    with pytest.raises(ct.OwnerUnresolved):
        ct.active_move(db_session, None, verified_leads[0])


@pytest.mark.usefixtures("on")
class TestReviewPendingMovesAreRetried:
    """(L2) A move whose follow-through crashed is finished by the sweep."""

    def test_a_crash_creating_the_lead_is_retried(self, db_session, enrolled, verified_leads,
                                                  source, verifier, monkeypatch):
        lead = verified_leads[0]
        positive_reply(db_session, lead)
        real = ct.create_reengagement_lead

        def boom(*a, **k):
            raise RuntimeError("crash after the move committed")

        monkeypatch.setattr(ct, "create_reengagement_lead", boom)
        with pytest.raises(RuntimeError):
            move_lead(db_session, lead, source, verifier)
        move = db_session.execute(select(m.ChampionMove)).scalar_one()
        assert move.outcome == ct.PENDING and move.new_lead_id is None
        monkeypatch.setattr(ct, "create_reengagement_lead", real)
        counts = ct.run_held(db_session, source, verifier, now=NOW + timedelta(minutes=15))
        assert counts["moves_retried"] == 1
        db_session.refresh(move)
        assert move.outcome == ct.LEAD_CREATED and move.new_lead_id is not None
        assert db_session.get(m.Lead, move.new_lead_id).company == "NewCo"

    def test_a_crash_closing_the_old_address_is_retried(self, db_session, enrolled,
                                                        verified_leads, source, verifier,
                                                        monkeypatch):
        lead = verified_leads[0]
        later = another_scheduled(db_session, lead, enrolled)
        real = ct.close_old_address

        def boom(*a, **k):
            raise RuntimeError("crash")

        monkeypatch.setattr(ct, "close_old_address", boom)
        with pytest.raises(RuntimeError):
            move_lead(db_session, lead, source, verifier)
        move = db_session.execute(select(m.ChampionMove)).scalar_one()
        assert move.outcome == ct.PENDING
        monkeypatch.setattr(ct, "close_old_address", real)
        ct.run_held(db_session, source, verifier, now=NOW + timedelta(minutes=15))
        db_session.refresh(move)
        db_session.refresh(later)
        assert move.outcome == ct.NOT_CHAMPION
        assert later.status is m.MessageStatus.CANCELLED


@pytest.mark.usefixtures("on")
def test_review_refresh_skips_leads_blocked_by_an_address_move(
        db_session, enrolled, verified_leads, source, verifier, test_user,
        product_with_strategy):
    """(L3) A twin already blocked by the address hash never costs a lookup."""
    lead = verified_leads[0]
    move_lead(db_session, lead, source, verifier)
    _, other_strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
    twin = m.Lead(strategy_id=other_strategy.id, source="apollo", external_id="T3",
                  full_name="Lead 0", title="Owner", company="Co 0", email=lead.email,
                  status=m.LeadStatus.CLOSED_WON)
    db_session.add(twin)
    db_session.commit()
    make_stale(db_session, twin)
    ids = {x.id for x in ct.refresh_candidates(db_session, test_user.id, NOW)}
    assert twin.id not in ids


@pytest.mark.usefixtures("on")
def test_review_a_hunter_found_address_is_checked_against_contact_exclusions(
        db_session, enrolled, verified_leads, source, verifier, test_user):
    """(L4) The finder's address gets the same F05 check as the provider's."""
    from app.services import guardrails

    system_settings.set(db_session, "guardrails_enabled", True)
    lead = verified_leads[0]
    positive_reply(db_session, lead)
    guardrails.add_exclusion(db_session, test_user.id, "contact", "lead.0@newco.com",
                             reason="do_not_contact")
    move_lead(db_session, lead, source, verifier, email=None)   # Hunter finds lead.0@newco.com
    move = db_session.execute(select(m.ChampionMove)).scalar_one()
    assert move.outcome == ct.EXCLUDED
    new = db_session.get(m.Lead, move.new_lead_id) if move.new_lead_id else None
    assert new is None or new.email is None


def test_review_every_guard_hold_prefix_is_in_the_shared_list():
    """One list (app/services/send_holds.py) decides what counts as a held,
    still-pending step; a guard whose prefix is missing would reopen H1."""
    from app.services import bounce_shield, send_holds

    assert ct.ERROR_PREFIX in send_holds.HOLD_PREFIXES
    assert bounce_shield.ERROR_PREFIX in send_holds.HOLD_PREFIXES   # F01

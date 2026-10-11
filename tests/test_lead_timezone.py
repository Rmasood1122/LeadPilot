"""Lead timezones (docs/features/autopilot-launch.md section 3.4).

Before this, nothing wrote a lead's timezone, so "the prospect's local time"
was the deployment fallback (UTC) for every lead -- for the send window AND
for best-time scheduling. Pinned here:

  * a deterministic resolver from the location the lead already carries
    (Apollo person / organization: time_zone, country, state): single-zone
    countries directly; US, Canada, Australia and Brazil through state tables;
    a multi-zone country without a state stays unresolved;
  * it is WRITTEN at enrichment into enrichment_json.timezone (the field the
    send window reads) and resolved lazily on read for older leads;
  * unresolved -> the strategy's target region -> the account's timezone ->
    the deployment default, and the source is reported; fallbacks are never
    written onto the lead, so the compliance REGION (which may read the
    stored timezone) is never inferred from the account's or the strategy's
    location;
  * the sending-hours guard follows the prospect's zone, across DST.
"""

from __future__ import annotations

from datetime import datetime, time, timezone

import pytest

from app.db import models as m
from app.services import compliance_region
from app.services import sequence_engine as engine

WINTER = datetime(2026, 1, 13, 8, 30, tzinfo=timezone.utc)     # Tuesday
SUMMER = datetime(2026, 7, 14, 8, 30, tzinfo=timezone.utc)     # Tuesday


def _lead(db, strategy, enrichment, ext="tz1"):
    lead = m.Lead(strategy_id=strategy.id, source="apollo", external_id=ext,
                  full_name="P", title="Owner", company="Co", email=f"{ext}@co.test",
                  status=m.LeadStatus.VERIFIED, enrichment_json=enrichment)
    db.add(lead)
    db.commit()
    return lead


class TestFromLocation:
    @pytest.mark.parametrize("enrichment, zone", [
        ({"raw": {"country": "Germany"}}, "Europe/Berlin"),
        ({"raw": {"country": "United Kingdom", "city": "Leeds"}}, "Europe/London"),
        ({"raw": {"country": "Singapore"}}, "Asia/Singapore"),
        ({"raw": {"country": "Pakistan"}}, "Asia/Karachi"),
        ({"raw": {"country": "United States", "state": "California"}}, "America/Los_Angeles"),
        ({"raw": {"country": "US", "state": "TX"}}, "America/Chicago"),
        ({"raw": {"country": "Canada", "state": "British Columbia"}}, "America/Vancouver"),
        ({"raw": {"country": "Australia", "state": "Western Australia"}}, "Australia/Perth"),
        ({"raw": {"country": "Brazil", "state": "Amazonas"}}, "America/Manaus"),
        # Apollo's own time_zone, on the enrichment match response, wins.
        ({"enrichment": {"person": {"time_zone": "America/Denver", "country": "United States",
                                    "state": "New York"}}}, "America/Denver"),
        # No person location: the organization's.
        ({"raw": {"organization": {"country": "United States", "state": "Florida"}}},
         "America/New_York"),
    ])
    def test_resolves(self, enrichment, zone):
        from app.services import lead_timezone as lt

        assert lt.zone_from_lead(m.Lead(enrichment_json=enrichment))[0] == zone

    @pytest.mark.parametrize("enrichment", [
        {"raw": {"country": "United States"}},                  # multi-zone, no state
        {"raw": {"country": "Mexico", "state": "Jalisco"}},      # no table
        {"raw": {"state": "California"}},                       # a state without a country
        {"raw": {"time_zone": "Mars/Olympus"}},                  # not an IANA zone
        {},
    ])
    def test_stays_unresolved(self, enrichment):
        from app.services import lead_timezone as lt

        assert lt.zone_from_lead(m.Lead(enrichment_json=enrichment)) is None

    def test_the_send_window_reads_it_lazily_for_existing_leads(self, db_session,
                                                                verified_strategy):
        lead = _lead(db_session, verified_strategy,
                     {"raw": {"country": "United States", "state": "Illinois"}})
        assert engine.lead_timezone(lead) == "America/Chicago"
        db_session.refresh(lead)
        assert "timezone" not in lead.enrichment_json        # read never writes

    def test_a_recorded_timezone_is_kept(self, db_session, verified_strategy):
        lead = _lead(db_session, verified_strategy,
                     {"timezone": "Asia/Tokyo", "raw": {"country": "Germany"}})
        assert engine.lead_timezone(lead) == "Asia/Tokyo"


class TestWrittenAtEnrichment:
    def test_enrichment_records_the_zone_and_its_evidence(self, db_session, lead_batch,
                                                          fake_source):
        from app.integrations.base import RawLead
        from app.workers import lead_tasks

        fake_source.feed = [RawLead(source="fakesource", external_id="p1", full_name="A B",
                                    title="Owner", company="Acme", email="a@acme.test",
                                    raw={"id": "p1", "country": "Canada",
                                         "state": "Alberta"})]
        lead_tasks.source_leads_impl(db_session, lead_batch.id, source=fake_source)
        lead_tasks.enrich_leads_impl(db_session, lead_batch.id, source=fake_source)
        lead = db_session.query(m.Lead).filter_by(external_id="p1").one()
        assert lead.enrichment_json["timezone"] == "America/Edmonton"
        assert lead.enrichment_json["timezone_source"] == "location: Alberta, Canada"

    def test_unresolved_writes_nothing(self, db_session, lead_batch, fake_source):
        from app.integrations.base import RawLead
        from app.workers import lead_tasks

        fake_source.feed = [RawLead(source="fakesource", external_id="p2", full_name="C D",
                                    title="Owner", company="Acme", email="c@acme.test",
                                    raw={"id": "p2", "country": "United States"})]
        lead_tasks.source_leads_impl(db_session, lead_batch.id, source=fake_source)
        lead_tasks.enrich_leads_impl(db_session, lead_batch.id, source=fake_source)
        lead = db_session.query(m.Lead).filter_by(external_id="p2").one()
        assert "timezone" not in lead.enrichment_json


class TestFallbacks:
    def test_strategy_region_then_account_then_default(self, db_session, verified_strategy,
                                                       test_user):
        from app.services import lead_timezone as lt

        lead = _lead(db_session, verified_strategy, {"raw": {"country": "United States"}})
        assert lt.resolve(lead) == ("UTC", lt.SOURCE_DEFAULT)

        db_session.add(m.CalendarAvailability(user_id=test_user.id, day_of_week=1,
                                              start_time=time(9), end_time=time(17),
                                              timezone="Europe/Dublin"))
        db_session.commit()
        lt.clear_cache(db_session)
        assert lt.resolve(lead) == ("Europe/Dublin", lt.SOURCE_ACCOUNT)

        verified_strategy.pattern_inputs_json = {"icp": {"locations": ["Texas, US",
                                                                       "Oklahoma, US"]}}
        db_session.commit()
        lt.clear_cache(db_session)
        assert lt.resolve(lead) == ("America/Chicago", lt.SOURCE_STRATEGY)
        assert engine.lead_timezone(lead) == "America/Chicago"

    def test_fallbacks_never_decide_the_compliance_region(self, db_session,
                                                          verified_strategy):
        from app.services import lead_timezone as lt

        verified_strategy.pattern_inputs_json = {"icp": {"locations": ["London, UK"]}}
        db_session.commit()
        lead = _lead(db_session, verified_strategy, {"raw": {"title": "x"}})
        lt.clear_cache(db_session)
        assert lt.resolve(lead) == ("Europe/London", lt.SOURCE_STRATEGY)
        assert compliance_region.lead_region(lead) is None       # unknown stays unknown
        assert "timezone" not in (lead.enrichment_json or {})

    def test_a_recorded_zone_agrees_with_the_region(self, db_session, lead_batch, fake_source):
        from app.integrations.base import RawLead
        from app.workers import lead_tasks

        fake_source.feed = [RawLead(source="fakesource", external_id="p3", full_name="E F",
                                    title="Owner", company="Acme", email="e@acme.test",
                                    raw={"id": "p3", "country": "France"})]
        lead_tasks.source_leads_impl(db_session, lead_batch.id, source=fake_source)
        lead_tasks.enrich_leads_impl(db_session, lead_batch.id, source=fake_source)
        lead = db_session.query(m.Lead).filter_by(external_id="p3").one()
        assert lead.enrichment_json["timezone"] == "Europe/Paris"
        assert compliance_region.lead_region(lead) == "eu"
        assert compliance_region.region_for_timezone("Europe/Paris") == "eu"
        assert compliance_region.open_tracking_allowed(lead) is False


class TestSendingHoursFollowTheProspect:
    """The permitted-hours guard in send_message_impl, across zones and DST."""

    @pytest.fixture()
    def wired(self, monkeypatch, fake_channel):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        return outreach_tasks

    def _message_for(self, db, enrolled, enrichment):
        msg = (db.query(m.Message).filter_by(status=m.MessageStatus.SCHEDULED)
               .order_by(m.Message.created_at, m.Message.id).first())
        lead = db.get(m.Lead, msg.lead_id)
        lead.enrichment_json = {**(lead.enrichment_json or {}), **enrichment}
        db.commit()
        return msg

    @pytest.mark.parametrize("now, expected", [
        (WINTER, "sent"),                           # 09:30 CET
        (SUMMER, "sent"),                           # 10:30 CEST
        (datetime(2026, 1, 13, 7, 30, tzinfo=timezone.utc), "deferred_window"),  # 08:30 CET
        (datetime(2026, 7, 14, 15, 30, tzinfo=timezone.utc), "deferred_window"),  # 17:30 CEST
    ])
    def test_berlin(self, db_session, enrolled, wired, now, expected):
        msg = self._message_for(db_session, enrolled, {"raw": {"country": "Germany"}})
        msg.scheduled_at = now
        db_session.commit()
        assert wired.send_message_impl(db_session, msg.id, now=now) == expected

    def test_new_york_winter_defers_to_nine_local(self, db_session, enrolled, wired):
        msg = self._message_for(db_session, enrolled,
                                {"raw": {"country": "United States", "state": "New York"}})
        now = datetime(2026, 11, 10, 13, 0, tzinfo=timezone.utc)    # 08:00 EST
        assert wired.send_message_impl(db_session, msg.id, now=now) == "deferred_window"
        db_session.refresh(msg)
        assert msg.scheduled_at.replace(tzinfo=timezone.utc) == datetime(
            2026, 11, 10, 14, 0, tzinfo=timezone.utc)                # 09:00 EST

    def test_new_york_summer_is_inside(self, db_session, enrolled, wired):
        msg = self._message_for(db_session, enrolled,
                                {"raw": {"country": "United States", "state": "New York"}})
        now = datetime(2026, 7, 14, 13, 0, tzinfo=timezone.utc)     # 09:00 EDT
        assert wired.send_message_impl(db_session, msg.id, now=now) == "sent"

    def test_compliance_rule_window_applies_in_the_prospects_zone(self, db_session, enrolled,
                                                                  wired):
        """A quiet-hours rule (compliance_rules) is read in the lead's own zone."""
        db_session.add(m.ComplianceRule(scope="global", region="eu", channel="email",
                                        send_start_hour=10,
                                        send_end_hour=12))
        db_session.commit()
        msg = self._message_for(db_session, enrolled, {"raw": {"country": "Germany"}})
        assert wired.send_message_impl(db_session, msg.id, now=WINTER) == "deferred_window"
        db_session.refresh(msg)
        assert msg.scheduled_at.replace(tzinfo=timezone.utc) == datetime(
            2026, 1, 13, 9, 0, tzinfo=timezone.utc)                  # 10:00 CET


class TestDiagnosticsSayWhichZone:
    def test_sources_are_counted(self, db_session, enrolled, verified_strategy):
        from app.services import send_diagnostics

        lead = db_session.query(m.Lead).filter_by(strategy_id=verified_strategy.id).first()
        lead.enrichment_json = {"raw": {"country": "Japan"}}
        db_session.commit()
        out = send_diagnostics.diagnose(db_session, verified_strategy,
                                        now=datetime(2026, 8, 11, 10, 0, tzinfo=timezone.utc))
        assert out["timezones"]["lead_location"] == 1
        assert out["timezones"]["deployment_default"] == 2
        reason = next(r for r in out["general"] if r["code"] == "timezone_fallback")
        assert "2 lead(s)" in reason["title"] and reason["blocking"] is False

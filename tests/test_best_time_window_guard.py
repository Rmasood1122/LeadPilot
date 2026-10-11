"""Best time to send never places a message outside the permitted window --
SAFETY GUARD (docs/features/autopilot-launch.md 3.2), for sealing.

The sealed send-path suites run with best-time scheduling OFF (conftest
`best_time_scheduling_off`), because they pin the window START, while
production has it ON. This file pins what production actually does, through
the REAL send_message_impl deferral and the real enrollment placement, with
best-time ON:

  * every placement is inside the permitted window AND the compliance-rule
    window resolved for that lead, in the lead's own timezone, across DST
    changes and odd-offset zones (Kathmandu +5:45, Lord Howe's 30-minute DST,
    Chatham +12:45, St John's -3:30);
  * never earlier than the old placement (the window start) and never more
    than the horizon later;
  * the sealed test_compliance.py::TestSendWindow::
    test_outside_hours_defers_to_window_start scenario (Tuesday 06:00 UTC ->
    09:00) in production lands on 09:00-09:29: the same day, inside the
    window, at or after its start. Still compliant: the send path re-checks
    the window at send time, and the slot is never outside it.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.services import send_time, system_settings
from app.services import sequence_engine as engine

_REAL_ENABLED = send_time.enabled
NOW = datetime(2026, 8, 11, 10, 0, tzinfo=timezone.utc)      # Tuesday
ZONES = ["America/New_York", "Europe/Berlin", "Asia/Kathmandu", "Australia/Lord_Howe",
         "Pacific/Chatham", "America/St_Johns", "Asia/Singapore", "America/Sao_Paulo"]
#: Around the 2026 DST changes (US 8 Mar / 1 Nov, EU 29 Mar / 25 Oct,
#: Lord Howe and Chatham 5 Apr / 27 Sep) and an ordinary week.
INSTANTS = [datetime(2026, 3, 7, 23, 0), datetime(2026, 3, 28, 22, 30),
            datetime(2026, 4, 4, 14, 15), datetime(2026, 9, 26, 13, 45),
            datetime(2026, 10, 24, 21, 0), datetime(2026, 10, 31, 23, 30),
            datetime(2026, 8, 11, 20, 0), datetime(2026, 8, 14, 18, 0)]


@pytest.fixture(autouse=True)
def best_time_on(monkeypatch):
    monkeypatch.setattr(send_time, "enabled", _REAL_ENABLED)


def test_production_default_is_on(db_session):
    assert system_settings.DEFAULTS[send_time.FLAG][0] is True
    assert send_time.enabled(db_session) is True


def test_property_never_earlier_never_outside(db_session):
    """The reviewer's property test (review-ap/test_ap_property.py)."""
    rnd = random.Random(7)
    bad = []
    for _ in range(600):
        tz = rnd.choice(ZONES)
        window = rnd.choice([None, (9, 17, True), (11, 13, True), (8, 20, False)])
        start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
            minutes=rnd.randrange(0, 525600))
        earliest = engine.next_window_slot(start, tz, window)
        for ch in ("email", "linkedin", "whatsapp"):
            scorer = send_time.Scorer(send_time.PRIORS[ch]["windows"])
            got = send_time.best_slot(db_session, scorer, False, earliest, tz, window=window,
                                      spread_key=rnd.random(), horizon=timedelta(hours=72))
            if (got < earliest or not engine.in_send_window(got, tz, window)
                    or got - earliest > timedelta(hours=73)):
                bad.append((tz, window, earliest, got, ch))
    assert not bad, bad[:3]


@pytest.fixture()
def wired(monkeypatch, fake_channel):
    from app.workers import outreach_tasks

    monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
    return outreach_tasks


def _first(db):
    return (db.query(m.Message).filter_by(status=m.MessageStatus.SCHEDULED)
            .order_by(m.Message.created_at, m.Message.id).first())


@pytest.mark.parametrize("zone", ZONES)
@pytest.mark.parametrize("rule", [None, (11, 14)])
def test_send_path_deferral_stays_inside_the_resolved_window(db_session, enrolled, wired,
                                                             zone, rule):
    from app.services import compliance_rules as rules

    if rule:
        db_session.add(m.ComplianceRule(scope=rules.GLOBAL, region="*", channel="email",
                                        send_start_hour=rule[0], send_end_hour=rule[1]))
    msg = _first(db_session)
    lead = db_session.get(m.Lead, msg.lead_id)
    lead.enrichment_json = {**(lead.enrichment_json or {}), "timezone": zone}
    db_session.commit()
    window = rules.resolve(db_session, lead, "email").window
    for naive in INSTANTS:
        now = naive.replace(tzinfo=timezone.utc)
        if engine.in_send_window(now, zone, window):
            continue
        msg.status, msg.scheduled_at, msg.error = m.MessageStatus.SCHEDULED, now, None
        db_session.commit()
        assert wired.send_message_impl(db_session, msg.id, now=now) == "deferred_window"
        db_session.refresh(msg)
        placed = msg.scheduled_at.replace(tzinfo=timezone.utc)
        floor = engine.next_window_slot(now, zone, window)
        assert floor <= placed <= floor + timedelta(hours=73), (zone, now, placed)
        assert engine.in_send_window(placed, zone, window), (zone, now, placed)


@pytest.mark.parametrize("zone", ZONES)
def test_enrollment_placement_stays_inside_the_resolved_window(db_session, fake_claude,
                                                               email_sequence, verified_leads,
                                                               gmail_account, zone):
    from app.services import compliance_rules as rules

    db_session.add(m.ComplianceRule(scope=rules.GLOBAL, region="*", channel="email",
                                    send_start_hour=13, send_end_hour=16))
    for lead in verified_leads:
        lead.enrichment_json = {**(lead.enrichment_json or {}), "timezone": zone}
    db_session.commit()
    for naive in INSTANTS[:4]:
        db_session.query(m.Message).delete()
        db_session.query(m.SequenceEnrollment).delete()
        db_session.commit()
        now = naive.replace(tzinfo=timezone.utc)
        engine.enroll_leads(db_session, email_sequence, now=now)
        for msg in db_session.query(m.Message):
            placed = msg.scheduled_at.replace(tzinfo=timezone.utc)
            assert placed >= now
            assert engine.in_send_window(placed, zone, (13, 16, True)), (zone, now, placed)


def test_the_sealed_window_start_scenario_in_production(db_session, enrolled, wired):
    """test_compliance.py::TestSendWindow::test_outside_hours_defers_to_window_start
    pins 09:00 exactly with best-time OFF. With it ON (production) the same
    deferral lands at 09:00-09:29 the same morning: inside the window, never
    before its start -- the spread is the only difference."""
    msg = _first(db_session)
    early = NOW.replace(hour=6)
    assert wired.send_message_impl(db_session, msg.id, now=early) == "deferred_window"
    db_session.refresh(msg)
    placed = msg.scheduled_at.replace(tzinfo=timezone.utc)
    assert NOW.replace(hour=9) <= placed < NOW.replace(hour=9, minute=30)

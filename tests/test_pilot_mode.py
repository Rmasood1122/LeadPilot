"""F09 — 30-Day Pilot Mode (docs/features/f09-pilot-mode.md).

What must hold (the STAR success metric is the first block):
  * EVERY pilot ends with a verdict and an export: the sweep (after the
    grace period), "end now" (before or after day 30) and starting the next
    pilot all go through end_pilot, which always stores the verdict, and the
    export answers for every ended pilot; READS NEVER WRITE;
  * the verdict's numbers ARE the F08 ledger's for the pilot's period, with
    the min/max rules, "no meetings" never meeting a cost cap, and a currency
    change reported as not comparable; the stored verdict does not move when
    the data changes later;
  * criteria are validated, locked, and one pilot runs at a time;
  * the weekly scorecard is sent once per pilot per week (re-runs, a claimed
    row, retries capped), only the current week, only to the account owner,
    never through the outreach path, never with the flag off;
  * NO AUTOMATIC CONVERSION: nothing a pilot does changes users.plan or the
    billing subscription, and there is no annual plan to convert to;
  * tenancy, RBAC, flag off, export headers, GDPR export completeness, Celery
    routing.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core import billing_catalog
from app.db import models as m
from app.integrations import stripe_billing
from app.services import account_export, meetings_ledger, pilot_mode, system_settings, workspaces

from .conftest import auth_headers

UTC = timezone.utc
START = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)          # day 1 = 1 Sep, day 30 = 30 Sep
AFTER_END = datetime(2026, 10, 1, 0, 30, tzinfo=UTC)   # 30 days over, inside the grace
FINAL = AFTER_END + timedelta(hours=24)                 # past the default 24h grace
CRITERIA = {"meetings_booked_min": 2, "qualified_conversations_min": 5,
            "max_cost_per_meeting_booked_cents": 6_000}


def at(day: int, hour: int = 10, month: int = 9) -> datetime:
    return datetime(2026, month, day, hour, 0, tzinfo=UTC)


def _on(db):
    system_settings.set(db, pilot_mode.FLAG, True)


def _lead(db, strategy, n):
    lead = m.Lead(strategy_id=strategy.id, source="apollo", external_id=f"PM{n}",
                  full_name=f"Person {n}", company=f"Company {n}",
                  email=f"p{n}@pilot{n}.test", status=m.LeadStatus.CONTACTED)
    db.add(lead)
    db.commit()
    return lead


def _outcome(db, lead, event, when):
    db.add(m.Outcome(lead_id=lead.id, strategy_id=lead.strategy_id, event=event,
                     channel="email", ts=when))
    db.commit()


def _interested(db, lead, when):
    db.add(m.InboundReply(lead_id=lead.id, channel="email", from_address=lead.email,
                          body="yes please", received_at=when, intent_label="interested"))
    db.commit()
    _outcome(db, lead, m.OutcomeEvent.REPLIED, when)


@pytest.fixture()
def seeded(db_session, test_user, verified_strategy):
    """Campaign A in September: l1 interested 3 Sep + booked 4 Sep + meeting
    held 10 Sep; l2 booked 5 Sep; l3 interested 8 Sep; 100.00 USD of data
    cost on 2 Sep. -> qualified 3, booked 2, held 1, cost/booked 50.00."""
    db = db_session
    a = verified_strategy
    l1, l2, l3 = (_lead(db, a, n) for n in (1, 2, 3))
    for lead in (l1, l2, l3):
        _outcome(db, lead, m.OutcomeEvent.SENT, at(2))
    _interested(db, l1, at(3))
    _outcome(db, l1, m.OutcomeEvent.BOOKED, at(4))
    db.add(m.Meeting(host_user_id=test_user.id, lead_id=l1.id, start_at=at(10),
                     end_at=at(10) + timedelta(minutes=30),
                     status=m.MeetingStatus.COMPLETED, actual_start_at=at(10)))
    _outcome(db, l2, m.OutcomeEvent.BOOKED, at(5))
    _interested(db, l3, at(8))
    db.add(m.CampaignCost(user_id=test_user.id, strategy_id=a.id, category="data",
                          amount_cents=10_000, incurred_on=date(2026, 9, 2)))
    db.commit()
    return {"strategy": a, "leads": (l1, l2, l3)}


def _start(db, user, criteria=None, **kw):
    return pilot_mode.start_pilot(db, user, criteria=criteria or dict(CRITERIA),
                                  now=kw.pop("now", START), **kw)


def _ledger(db, user, date_to=date(2026, 9, 30), strategy_ids=None):
    return meetings_ledger.build_ledger(db, user.id, date(2026, 9, 1), date_to,
                                        strategy_ids=strategy_ids)


def _other_account(db):
    other = m.User(email="other-pilot@leadpilot.dev", email_verified=True)
    db.add(other)
    db.commit()
    product = m.Product(user_id=other.id, name="Rival", description="x",
                        type=m.ProductType.SKILL)
    db.add(product)
    db.flush()
    strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.WITH_CLIENTS)
    db.add(strategy)
    db.commit()
    return other, strategy


# --------------------------------------------------------------------------
# Success metric: every pilot ends with a verdict and an export
# --------------------------------------------------------------------------


class TestEveryPilotEndsWithAVerdict:
    def test_the_sweep_ends_a_due_pilot_with_a_verdict(self, db_session, test_user, seeded):
        _on(db_session)
        pilot = _start(db_session, test_user)
        assert pilot_mode.sweep(db_session, now=AFTER_END - timedelta(hours=1))["ended"] == 0
        # 30 days over but inside the 24h grace: not frozen yet.
        assert pilot_mode.sweep(db_session, now=AFTER_END)["ended"] == 0
        final_at = datetime(2026, 10, 2, 0, 0, tzinfo=UTC)
        assert pilot_mode.sweep(db_session, now=final_at - timedelta(seconds=1))["ended"] == 0
        db_session.refresh(pilot)
        assert pilot.status == "active" and pilot.verdict_json is None
        result = pilot_mode.sweep(db_session, now=final_at)
        assert result["ended"] == 1
        db_session.refresh(pilot)
        assert pilot.status == "ended" and pilot.end_reason == "completed"
        assert pilot.verdict_json is not None and pilot.active_owner_id is None
        assert pilot.verdict_json["date_from"] == "2026-09-01"
        assert pilot.verdict_json["date_to"] == "2026-09-30"

    def test_a_read_after_day_30_shows_verdict_pending_and_writes_nothing(
            self, client, db_session, test_user):
        _on(db_session)
        started = datetime.now(UTC) - timedelta(days=31)
        pilot = _start(db_session, test_user, now=started)
        body = client.get("/pilots/current").json()["pilot"]
        assert body["id"] == str(pilot.id)
        assert body["status"] == "active" and body["phase"] == "verdict_pending"
        assert body["verdict"] is None and body["export_available"] is False
        assert body["verdict_final_at"] == (pilot_mode.verdict_final_at(
            pilot, timedelta(hours=24))).isoformat()
        for path in (f"/pilots/{pilot.id}", "/pilots", f"/pilots/{pilot.id}/export"):
            client.get(path)
        db_session.refresh(pilot)
        assert pilot.status == "active" and pilot.verdict_json is None

    def test_ending_early_writes_a_verdict(self, client, db_session, test_user):
        _on(db_session)
        pilot = _start(db_session, test_user, now=datetime.now(UTC))
        resp = client.post(f"/pilots/{pilot.id}/end")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "ended" and body["end_reason"] == "ended_early"
        assert body["verdict"]["date_to"] == datetime.now(UTC).date().isoformat()
        assert client.post(f"/pilots/{pilot.id}/end").status_code == 409

    @pytest.mark.parametrize("path", ["sweep", "end_after_day_30", "early", "next_pilot"])
    def test_every_ending_path_has_a_verdict_and_an_export(self, client, db_session,
                                                           test_user, path):
        _on(db_session)
        now = datetime.now(UTC)
        pilot = _start(db_session, test_user,
                       now=now - timedelta(days=33) if path != "early" else now)
        if path == "sweep":
            pilot_mode.sweep(db_session, now=now)
        elif path == "next_pilot":
            assert client.post("/pilots", json={"criteria": CRITERIA}).status_code == 201
        else:
            assert client.post(f"/pilots/{pilot.id}/end").status_code == 200
        db_session.refresh(pilot)
        assert pilot.status == "ended" and pilot.verdict_json is not None
        for fmt in ("pdf", "csv"):
            assert client.get(f"/pilots/{pilot.id}/export?format={fmt}").status_code == 200
        # The production audit query from the spec.
        assert db_session.execute(select(m.Pilot).where(
            m.Pilot.status == "ended", m.Pilot.verdict_json.is_(None))).first() is None


# --------------------------------------------------------------------------
# The verdict is F08's numbers against the buyer's criteria
# --------------------------------------------------------------------------


class TestVerdict:
    def test_actuals_are_the_ledgers_totals(self, db_session, test_user, seeded):
        _on(db_session)
        pilot = _start(db_session, test_user)
        pilot_mode.end_pilot(db_session, pilot, reason="completed", now=AFTER_END)
        totals = _ledger(db_session, test_user)["totals"]
        assert (totals["qualified_conversations"], totals["meetings_booked"],
                totals["meetings_held"]) == (3, 2, 1)
        assert totals["cost_per_meeting_booked_cents"] == 5_000
        rows = {r["key"]: r for r in pilot.verdict_json["criteria"]}
        assert rows["meetings_booked_min"]["actual"] == totals["meetings_booked"]
        assert rows["qualified_conversations_min"]["actual"] == \
            totals["qualified_conversations"]
        assert rows["max_cost_per_meeting_booked_cents"]["actual"] == \
            totals["cost_per_meeting_booked_cents"]
        assert rows["meetings_booked_min"]["status"] == "met"            # 2 >= 2
        assert rows["qualified_conversations_min"]["status"] == "not_met"  # 3 < 5
        assert rows["max_cost_per_meeting_booked_cents"]["status"] == "met"  # 50 <= 60
        assert pilot.verdict_json["met_count"] == 2
        assert pilot.verdict_json["outcome"] == "not_met"
        snap = pilot.verdict_json["ledger"]
        assert snap["totals"] == totals and "events" not in snap

    def test_all_met_is_met(self, db_session, test_user, seeded):
        pilot = _start(db_session, test_user, criteria={"meetings_booked_min": 1,
                                                        "meetings_held_min": 1})
        pilot_mode.end_pilot(db_session, pilot, reason="completed", now=AFTER_END)
        assert pilot.verdict_json["outcome"] == "met"
        assert pilot.verdict_json["met_count"] == 2

    def test_no_meetings_never_meets_a_cost_cap(self):
        ledger = {"currency": "USD", "totals": {"meetings_booked": 0,
                                                "cost_per_meeting_booked_cents": None}}
        result = pilot_mode.evaluate({"max_cost_per_meeting_booked_cents": 10**6}, "USD",
                                     ledger)
        row = result["criteria"][0]
        assert row["status"] == "not_met" and row["actual"] is None
        assert "no cost per booked meeting" in row["note"]

    def test_min_and_max_boundaries(self):
        ledger = {"currency": "USD", "totals": {"meetings_held": 4,
                                                "cost_per_qualified_conversation_cents": 900}}
        res = pilot_mode.evaluate({"meetings_held_min": 4,
                                   "max_cost_per_qualified_conversation_cents": 899},
                                  "USD", ledger)
        status = {r["key"]: r["status"] for r in res["criteria"]}
        assert status == {"meetings_held_min": "met",
                          "max_cost_per_qualified_conversation_cents": "not_met"}

    def test_a_currency_change_is_not_comparable_and_not_met(self):
        ledger = {"currency": "EUR", "totals": {"cost_per_meeting_booked_cents": 1,
                                                "meetings_booked": 9}}
        res = pilot_mode.evaluate({"max_cost_per_meeting_booked_cents": 500,
                                   "meetings_booked_min": 1}, "USD", ledger)
        rows = {r["key"]: r for r in res["criteria"]}
        assert rows["max_cost_per_meeting_booked_cents"]["status"] == "not_comparable"
        assert rows["max_cost_per_meeting_booked_cents"]["met"] is False
        assert rows["meetings_booked_min"]["status"] == "met"   # counts have no currency
        assert res["outcome"] == "not_met"

    def test_the_stored_verdict_does_not_move_when_data_changes(self, client, db_session,
                                                               test_user, seeded):
        _on(db_session)
        pilot = _start(db_session, test_user)
        pilot_mode.end_pilot(db_session, pilot, reason="completed", now=AFTER_END)
        before = client.get(f"/pilots/{pilot.id}").json()["verdict"]
        late = _lead(db_session, seeded["strategy"], 9)
        _outcome(db_session, late, m.OutcomeEvent.BOOKED, at(20))
        assert _ledger(db_session, test_user)["totals"]["meetings_booked"] == 3
        assert client.get(f"/pilots/{pilot.id}").json()["verdict"] == before

    def test_scope_limits_the_campaigns(self, db_session, test_user, seeded):
        other_campaign = m.Strategy(product_id=seeded["strategy"].product_id,
                                    flow_type=m.FlowType.WITH_CLIENTS)
        db_session.add(other_campaign)
        db_session.commit()
        b1 = _lead(db_session, other_campaign, 7)
        _outcome(db_session, b1, m.OutcomeEvent.BOOKED, at(6))
        pilot = _start(db_session, test_user, strategy_ids=[seeded["strategy"].id])
        pilot_mode.end_pilot(db_session, pilot, reason="completed", now=AFTER_END)
        rows = {r["key"]: r for r in pilot.verdict_json["criteria"]}
        assert rows["meetings_booked_min"]["actual"] == 2      # not 3
        assert pilot.strategy_ids_json == [str(seeded["strategy"].id)]


# --------------------------------------------------------------------------
# Criteria: validated, locked; one pilot at a time; dates
# --------------------------------------------------------------------------


class TestStart:
    @pytest.mark.parametrize("criteria, message", [
        ({}, "at least one"),
        (None, "at least one"),
        ({"reply_rate_min": 5}, "Unknown criterion"),
        ({"meetings_booked_min": True}, "whole number"),
        ({"meetings_booked_min": 2.5}, "whole number"),
        ({"meetings_booked_min": 5.0}, "whole number"),
        ({"meetings_booked_min": "5"}, "whole number"),
        ({"meetings_booked_min": 0}, "at least 1"),
        ({"meetings_booked_min": -3}, "at least 1"),
        ({"meetings_booked_min": 100_001}, "at most"),
        ({"max_cost_per_meeting_booked_cents": 100_000_001}, "at most"),
    ])
    def test_invalid_criteria_are_refused(self, criteria, message):
        with pytest.raises(pilot_mode.PilotError) as err:
            pilot_mode.validate_criteria(criteria)
        assert err.value.status_code == 422 and message in str(err.value)

    def test_start_over_the_api(self, client, db_session, test_user):
        _on(db_session)
        resp = client.post("/pilots", json={"criteria": CRITERIA})
        assert resp.status_code == 201, resp.text
        body = resp.json()
        today = datetime.now(UTC).date()
        assert body["status"] == "active" and body["day"] == 1
        assert body["start_date"] == today.isoformat()
        assert body["end_date"] == (today + timedelta(days=29)).isoformat()
        assert body["ends_at"].startswith((today + timedelta(days=30)).isoformat())
        assert {c["key"]: c["target"] for c in body["criteria"]} == CRITERIA
        assert body["currency"] == "USD" and body["plan_at_start"] == "free"
        assert body["progress"]["criteria_count"] == 3
        assert client.post("/pilots", json={"criteria": {"meetings_booked_min": 0}}) \
            .status_code == 422

    def test_invalid_criteria_over_the_api(self, client, db_session):
        _on(db_session)
        resp = client.post("/pilots", json={"criteria": {"meetings_booked_min": 5.5}})
        assert resp.status_code == 422 and "whole number" in resp.json()["detail"]

    def test_one_active_pilot_per_account(self, client, db_session, test_user):
        _on(db_session)
        assert client.post("/pilots", json={"criteria": CRITERIA}).status_code == 201
        resp = client.post("/pilots", json={"criteria": CRITERIA})
        assert resp.status_code == 409 and "already running" in resp.json()["detail"]

    def test_the_schema_refuses_a_second_active_pilot(self, db_session, test_user):
        first = _start(db_session, test_user)
        clone = m.Pilot(user_id=test_user.id, active_owner_id=test_user.id, status="active",
                        start_date=first.start_date, end_date=first.end_date,
                        started_at=START, ends_at=first.ends_at, criteria_json=CRITERIA,
                        currency="USD")
        db_session.add(clone)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_a_new_pilot_can_start_after_the_last_ended(self, db_session, test_user):
        first = _start(db_session, test_user)
        pilot_mode.end_pilot(db_session, first, reason="ended_early", now=START)
        second = _start(db_session, test_user, now=START + timedelta(days=1))
        assert second.status == "active" and first.status == "ended"

    def test_dates(self):
        start, end, ends_at = pilot_mode.period_for(datetime(2026, 9, 1, 23, 59, tzinfo=UTC))
        assert (start, end) == (date(2026, 9, 1), date(2026, 9, 30))
        assert ends_at == datetime(2026, 10, 1, 0, 0, tzinfo=UTC)

    def test_criteria_are_locked(self, client, db_session, test_user):
        _on(db_session)
        pilot_id = client.post("/pilots", json={"criteria": CRITERIA}).json()["id"]
        resp = client.patch(f"/pilots/{pilot_id}",
                            json={"criteria": {"meetings_booked_min": 1}})
        assert resp.status_code == 422
        resp = client.patch(f"/pilots/{pilot_id}", json={"scorecard_emails": False})
        assert resp.status_code == 200 and resp.json()["scorecard_emails"] is False
        assert {c["key"]: c["target"] for c in resp.json()["criteria"]} == CRITERIA

    def test_a_campaign_that_is_not_yours_is_404(self, client, db_session, verified_strategy):
        _on(db_session)
        _, foreign = _other_account(db_session)
        resp = client.post("/pilots", json={"criteria": CRITERIA,
                                            "strategy_ids": [str(foreign.id)]})
        assert resp.status_code == 404
        resp = client.post("/pilots", json={"criteria": CRITERIA,
                                            "strategy_ids": [str(verified_strategy.id)]})
        assert resp.status_code == 201
        assert resp.json()["strategy_ids"] == [str(verified_strategy.id)]

    def test_template_prefills_no_targets(self, client, db_session):
        _on(db_session)
        body = client.get("/pilots/template").json()
        assert body["pilot_days"] == 30 and body["scorecard_after_days"] == [7, 14, 21, 28]
        assert {c["key"] for c in body["criteria"]} == set(pilot_mode.CRITERIA)
        assert all("target" not in c and "default" not in c for c in body["criteria"])


# --------------------------------------------------------------------------
# Weekly scorecard
# --------------------------------------------------------------------------


def _scorecards(db, pilot):
    return db.execute(select(m.PilotScorecard).where(
        m.PilotScorecard.pilot_id == pilot.id).order_by(m.PilotScorecard.week)).scalars().all()


class TestScorecard:
    def test_sent_once_per_week_to_the_owner_only(self, db_session, test_user, seeded,
                                                  mailbox):
        _on(db_session)
        pilot = _start(db_session, test_user)
        assert pilot_mode.sweep(db_session, now=START + timedelta(days=6, hours=23)) \
            ["scorecards_sent"] == 0
        week1 = START + timedelta(days=7, minutes=5)
        assert pilot_mode.sweep(db_session, now=week1)["scorecards_sent"] == 1
        assert pilot_mode.sweep(db_session, now=week1)["scorecards_sent"] == 0
        assert pilot_mode.sweep(db_session, now=week1 + timedelta(days=1))["scorecards_sent"] == 0
        assert len(mailbox) == 1
        mail = mailbox[0]
        assert mail["to"] == test_user.email
        assert mail["subject"].startswith("Pilot week 1 of 4:")
        # Figures are the ledger's for 1-8 Sep.
        totals = _ledger(db_session, test_user, date_to=date(2026, 9, 8))["totals"]
        assert f"Meetings booked: {totals['meetings_booked']} " in mail["text"]
        assert "changes nothing in your plan or billing" in mail["text"]
        # Never an outreach send: no Message row, no prospect address.
        assert db_session.query(m.Message).count() == 0
        assert all(lead.email not in mail["text"] for lead in seeded["leads"])
        rows = _scorecards(db_session, pilot)
        assert [(r.week, r.status, r.attempts) for r in rows] == [(1, "sent", 1)]
        assert rows[0].summary_json["criteria"][0]["actual"] == totals["meetings_booked"]
        assert pilot_mode.sweep(db_session, now=START + timedelta(days=14, hours=1)) \
            ["scorecards_sent"] == 1
        assert [r.week for r in _scorecards(db_session, pilot)] == [1, 2]

    def test_only_the_current_week_is_sent(self, db_session, test_user, mailbox):
        _on(db_session)
        pilot = _start(db_session, test_user)
        pilot_mode.sweep(db_session, now=START + timedelta(days=15))
        assert [r.week for r in _scorecards(db_session, pilot)] == [2]
        assert len(mailbox) == 1

    def test_a_claimed_week_is_never_sent_again(self, db_session, test_user, mailbox):
        """Another worker already claimed week 1 (row exists, `sending`)."""
        _on(db_session)
        pilot = _start(db_session, test_user)
        db_session.add(m.PilotScorecard(pilot_id=pilot.id, user_id=test_user.id, week=1,
                                        status="sending", attempts=1))
        db_session.commit()
        assert pilot_mode.send_due_scorecard(db_session, pilot,
                                             START + timedelta(days=7, hours=1)) == "skipped"
        assert mailbox == []

    def test_the_schema_allows_one_row_per_week(self, db_session, test_user):
        pilot = _start(db_session, test_user)
        for _ in range(2):
            db_session.add(m.PilotScorecard(pilot_id=pilot.id, user_id=test_user.id, week=1))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_a_failed_send_is_retried_and_capped(self, db_session, test_user, mailbox,
                                                 monkeypatch):
        from app.services import email_sender

        _on(db_session)
        pilot = _start(db_session, test_user)
        real = email_sender.send_email
        calls = {"n": 0}

        def flaky(**kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise email_sender.EmailSendError("relay down")
            return real(**kw)

        monkeypatch.setattr(email_sender, "send_email", flaky)
        week1 = START + timedelta(days=7, hours=1)
        assert pilot_mode.send_due_scorecard(db_session, pilot, week1) == "failed"
        row = _scorecards(db_session, pilot)[0]
        assert (row.status, row.attempts) == ("failed", 1) and "relay down" in row.error
        assert pilot_mode.send_due_scorecard(db_session, pilot, week1) == "sent"
        db_session.refresh(row)
        assert (row.status, row.attempts) == ("sent", 2) and len(mailbox) == 1

        def always_down(**kw):
            raise email_sender.EmailSendError("still down")

        monkeypatch.setattr(email_sender, "send_email", always_down)
        week2 = START + timedelta(days=14, hours=1)
        outcomes = [pilot_mode.send_due_scorecard(db_session, pilot, week2) for _ in range(5)]
        assert outcomes == ["failed", "failed", "failed", "skipped", "skipped"]
        assert _scorecards(db_session, pilot)[1].attempts == pilot_mode.MAX_EMAIL_ATTEMPTS

    def test_opted_out_and_ended_pilots_get_no_scorecard(self, db_session, test_user,
                                                         mailbox):
        _on(db_session)
        pilot = _start(db_session, test_user, scorecard_emails=False)
        assert pilot_mode.send_due_scorecard(db_session, pilot,
                                             START + timedelta(days=7, hours=1)) == "opted_out"
        pilot_mode.set_scorecard_emails(db_session, pilot, True)
        pilot_mode.end_pilot(db_session, pilot, reason="ended_early", now=START)
        assert pilot_mode.send_due_scorecard(db_session, pilot,
                                             START + timedelta(days=7, hours=1)) == "not_active"
        assert _scorecards(db_session, pilot) == []
        assert all(not mail["subject"].startswith("Pilot week") for mail in mailbox)


class TestVerdictEmail:
    def test_sent_once_to_the_owner(self, db_session, test_user, seeded, mailbox):
        _on(db_session)
        pilot = _start(db_session, test_user)
        first = pilot_mode.sweep(db_session, now=FINAL)
        assert first["ended"] == 1 and first["verdict_emails_sent"] == 1
        assert pilot_mode.sweep(db_session, now=FINAL + timedelta(hours=1)) \
            ["verdict_emails_sent"] == 0
        verdicts = [mail for mail in mailbox if "verdict" in mail["subject"]]
        assert len(verdicts) == 1 and verdicts[0]["to"] == test_user.email
        assert verdicts[0]["subject"] == "Your 30-day pilot verdict: 2 of 3 criteria met"
        assert "full account data" in verdicts[0]["text"]
        db_session.refresh(pilot)
        assert pilot.verdict_emailed_at is not None and pilot.verdict_email_attempts == 1
        assert pilot.verdict_email_status == "sent"

    def test_a_failed_verdict_email_is_retried_three_times_at_most(
            self, db_session, test_user, mailbox, monkeypatch):
        from app.services import email_sender

        def down(**kw):
            raise email_sender.EmailSendError("down")

        monkeypatch.setattr(email_sender, "send_email", down)
        _on(db_session)
        pilot = _start(db_session, test_user)
        for hour in range(6):
            pilot_mode.sweep(db_session, now=FINAL + timedelta(hours=hour))
        db_session.refresh(pilot)
        assert pilot.verdict_email_attempts == 3 and pilot.verdict_emailed_at is None
        assert pilot.verdict_email_status == "failed"
        assert pilot.verdict_json is not None     # the verdict itself never depends on mail


# --------------------------------------------------------------------------
# No automatic conversion
# --------------------------------------------------------------------------


def _billing_state(db, user_id):
    db.expire_all()
    user = db.get(m.User, user_id)
    subs = db.execute(select(m.BillingSubscription).where(
        m.BillingSubscription.user_id == user_id)).scalars().all()
    return (user.plan, [(s.billing_model, s.tier, s.status, s.is_stub, s.trial_ends_at,
                         s.current_period_end, s.cancel_at_period_end, s.canceled_at,
                         s.stripe_subscription_id) for s in subs],
            db.query(m.BillingSubscription).count(), db.query(m.BillableMeeting).count())


class TestNoAutomaticConversion:
    @pytest.mark.parametrize("subscription", [False, True])
    @pytest.mark.parametrize("ending", ["completed", "ended_early"])
    def test_a_pilot_never_changes_plan_or_billing(self, db_session, test_user, seeded,
                                                   subscription, ending):
        _on(db_session)
        if subscription:
            test_user.plan = m.PlanTier.STARTER
            db_session.add(m.BillingSubscription(
                user_id=test_user.id, billing_model="monthly", tier="starter",
                status="trialing", is_stub=True, trial_ends_at=START + timedelta(days=14),
                current_period_end=START + timedelta(days=14)))
            db_session.commit()
        before = _billing_state(db_session, test_user.id)
        pilot = _start(db_session, test_user)
        for days in (7, 14, 21, 28):
            pilot_mode.sweep(db_session, now=START + timedelta(days=days, hours=1))
        assert _billing_state(db_session, test_user.id) == before
        if ending == "completed":
            pilot_mode.sweep(db_session, now=FINAL)
        else:
            pilot_mode.end_pilot(db_session, pilot, reason="ended_early",
                                 now=START + timedelta(days=20))
        pilot_mode.sweep(db_session, now=FINAL + timedelta(days=1))
        assert _billing_state(db_session, test_user.id) == before
        db_session.refresh(pilot)
        expected = "starter" if subscription else "free"
        assert pilot.plan_at_start == pilot.plan_at_end == expected
        assert pilot.verdict_json["billing_statement"] == pilot_mode.BILLING_STATEMENT

    def test_there_is_no_annual_plan_to_convert_to(self, monkeypatch):
        """The spec says LeadPilot has no annual plan. If someone adds one,
        this fails and sends them to docs/features/f09-pilot-mode.md first."""
        assert billing_catalog.BILLING_MODELS == ("monthly", "pay_per_meeting")
        sent = []
        monkeypatch.setattr(stripe_billing, "_request",
                            lambda method, path, data=None, **kw: sent.append(data) or {})
        stripe_billing.create_subscription_checkout(
            customer_id="cus_x", user_id="u", tier=billing_catalog.MONTHLY_TIERS[0],
            trial_days=0, success_url="https://x/s", cancel_url="https://x/c")
        recurring = sent[0]["line_items"][0]["price_data"]["recurring"]
        assert recurring == {"interval": "month"}

    def test_the_pilot_module_never_writes_billing(self):
        import inspect

        source = inspect.getsource(pilot_mode)
        for forbidden in ("BillingSubscription", "services.billing", "import billing",
                          "stripe", ".plan =", "start_checkout", "PlanTier",
                          "billing_catalog"):
            assert forbidden not in source, forbidden


# --------------------------------------------------------------------------
# Tenancy and RBAC
# --------------------------------------------------------------------------


class TestTenancy:
    def test_another_accounts_pilot_is_invisible(self, client, db_session, test_user):
        _on(db_session)
        other, _ = _other_account(db_session)
        theirs = _start(db_session, other)
        pilot_mode.end_pilot(db_session, theirs, reason="ended_early", now=START)
        assert client.get("/pilots").json()["items"] == []
        assert client.get("/pilots/current").json()["pilot"] is None
        for method, path in (("get", f"/pilots/{theirs.id}"),
                             ("patch", f"/pilots/{theirs.id}"),
                             ("post", f"/pilots/{theirs.id}/end"),
                             ("get", f"/pilots/{theirs.id}/export")):
            kwargs = {"json": {"scorecard_emails": False}} if method == "patch" else {}
            assert getattr(client, method)(path, **kwargs).status_code == 404, path

    def test_another_accounts_outcomes_never_count(self, db_session, test_user, seeded):
        other, foreign = _other_account(db_session)
        for n in (40, 41, 42):
            lead = _lead(db_session, foreign, n)
            _outcome(db_session, lead, m.OutcomeEvent.BOOKED, at(6))
        pilot = _start(db_session, test_user)
        pilot_mode.end_pilot(db_session, pilot, reason="completed", now=AFTER_END)
        rows = {r["key"]: r for r in pilot.verdict_json["criteria"]}
        assert rows["meetings_booked_min"]["actual"] == 2

    def test_account_export_includes_the_pilot_and_only_ours(self, db_session, test_user):
        other, _ = _other_account(db_session)
        mine, theirs = _start(db_session, test_user), _start(db_session, other)
        db_session.add(m.PilotScorecard(pilot_id=mine.id, user_id=test_user.id, week=1,
                                        status="sent"))
        db_session.commit()
        export = account_export.build(db_session, test_user.id)
        assert [p["id"] for p in export["tables"]["pilots"]] == [str(mine.id)]
        assert len(export["tables"]["pilot_scorecards"]) == 1
        assert str(theirs.id) not in str(export["tables"])


@pytest.fixture()
def team(db_session, test_user):
    ws = workspaces.personal_workspace(db_session, test_user)
    people = {}
    for role in ("manager", "sdr", "viewer"):
        user = m.User(email=f"{role}@pilot-team.dev", email_verified=True)
        db_session.add(user)
        db_session.commit()
        db_session.add(m.WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=role))
        people[role] = user
    db_session.commit()
    return ws, people


def _as(user, ws):
    return {**auth_headers(user), "X-Workspace-Id": str(ws.id)}


class TestRoles:
    def test_sdr_and_viewer_can_read_but_not_start_or_end(self, client, db_session,
                                                          test_user, team):
        _on(db_session)
        ws, people = team
        for role in ("sdr", "viewer"):
            resp = client.post("/pilots", json={"criteria": CRITERIA},
                               headers=_as(people[role], ws))
            assert resp.status_code == 403, role
        pilot_id = client.post("/pilots", json={"criteria": CRITERIA}).json()["id"]
        for role in ("sdr", "viewer"):
            headers = _as(people[role], ws)
            assert client.get("/pilots/current", headers=headers).json()["pilot"]["id"] \
                == pilot_id
            assert client.post(f"/pilots/{pilot_id}/end", headers=headers).status_code == 403

    def test_a_manager_starts_on_the_owners_account(self, client, db_session, test_user,
                                                    team):
        _on(db_session)
        ws, people = team
        resp = client.post("/pilots", json={"criteria": CRITERIA},
                           headers=_as(people["manager"], ws))
        assert resp.status_code == 201, resp.text
        pilot = db_session.get(m.Pilot, uuid.UUID(resp.json()["id"]))
        assert pilot.user_id == test_user.id
        assert pilot.started_by_user_id == people["manager"].id


# --------------------------------------------------------------------------
# Flag off
# --------------------------------------------------------------------------


class TestFlagOff:
    def test_default_is_off(self):
        assert system_settings.DEFAULTS[pilot_mode.FLAG][0] is False

    def test_every_route_is_409(self, client, db_session, test_user):
        pilot = _start(db_session, test_user)
        for method, path in (("get", "/pilots/template"), ("get", "/pilots"),
                             ("get", "/pilots/current"), ("post", "/pilots"),
                             ("get", f"/pilots/{pilot.id}"),
                             ("patch", f"/pilots/{pilot.id}"),
                             ("post", f"/pilots/{pilot.id}/end"),
                             ("get", f"/pilots/{pilot.id}/export")):
            kwargs = {}
            if method == "post" and path == "/pilots":
                kwargs = {"json": {"criteria": CRITERIA}}
            if method == "patch":
                kwargs = {"json": {"scorecard_emails": False}}
            resp = getattr(client, method)(path, **kwargs)
            assert resp.status_code == 409, path
            assert resp.json()["detail"] == "Pilot mode is disabled by the administrator"

    def test_the_sweep_does_nothing(self, db_session, test_user, mailbox):
        pilot = _start(db_session, test_user)
        assert pilot_mode.sweep(db_session, now=START + timedelta(days=7, hours=1)) == \
            {"skipped": "disabled"}
        assert pilot_mode.sweep(db_session, now=AFTER_END) == {"skipped": "disabled"}
        db_session.refresh(pilot)
        assert pilot.status == "active" and _scorecards(db_session, pilot) == []
        assert mailbox == []
        # Back on: the pilot is finished (verdict + notice) on the next sweep
        # after the grace period.
        _on(db_session)
        assert pilot_mode.sweep(db_session, now=FINAL)["ended"] == 1

    def test_the_meetings_ledger_is_unaffected(self, client, db_session, seeded):
        system_settings.set(db_session, meetings_ledger.FLAG, True)
        url = "/analytics/meetings-ledger?date_from=2026-09-01&date_to=2026-09-30"
        off = client.get(url).json()
        _on(db_session)
        on = client.get(url).json()
        off.pop("generated_at"), on.pop("generated_at")
        assert on == off


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------


class TestExport:
    def test_only_once_the_pilot_has_ended(self, client, db_session, test_user, seeded):
        _on(db_session)
        pilot = _start(db_session, test_user, now=datetime.now(UTC))
        resp = client.get(f"/pilots/{pilot.id}/export")
        assert resp.status_code == 409 and "verdict is final" in resp.json()["detail"]
        assert pilot.exported_at is None

    def test_pdf_and_csv(self, client, db_session, test_user, seeded):
        _on(db_session)
        pilot = _start(db_session, test_user)
        pilot_mode.end_pilot(db_session, pilot, reason="completed", now=AFTER_END)
        pdf = client.get(f"/pilots/{pilot.id}/export?format=pdf")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        assert pdf.headers["cache-control"] == "private, no-store"
        assert pdf.headers["content-disposition"] == \
            'attachment; filename="leadpilot-pilot-verdict-2026-09-01.pdf"'
        db_session.refresh(pilot)
        assert pilot.exported_at is not None

        rows = list(csv.reader(io.StringIO(
            client.get(f"/pilots/{pilot.id}/export?format=csv").text)))
        assert rows[0] == list(pilot_mode.VERDICT_COLUMNS)
        by_key = {r[0]: r for r in rows[1:]}
        assert by_key["meetings_booked_min"][3:7] == ["2", "2", "count", "met"]
        assert by_key["max_cost_per_meeting_booked_cents"][3:7] == ["60.00", "50.00", "USD",
                                                                    "met"]
        assert by_key["OUTCOME"][3:7] == ["3", "2", "criteria met", "not_met"]
        text = client.get(f"/pilots/{pilot.id}/export?format=csv").text
        assert all(lead.email not in text for lead in seeded["leads"])

        campaigns = client.get(f"/pilots/{pilot.id}/export?format=csv&view=campaigns")
        assert campaigns.status_code == 200
        assert campaigns.text == meetings_ledger.to_csv(pilot.verdict_json["ledger"],
                                                        view="campaigns")
        assert 'filename="leadpilot-pilot-verdict-2026-09-01-campaigns.csv"' in \
            campaigns.headers["content-disposition"]

    def test_meetings_ledger_pdf_is_unchanged_by_the_refactor(self, db_session, test_user,
                                                              seeded, monkeypatch):
        """F08's to_pdf renders exactly pdf_lines (the PDF bytes themselves
        carry a creation timestamp, so the lines are compared)."""
        from app.services import audit_trail

        rendered = []
        monkeypatch.setattr(audit_trail, "render_lines_pdf",
                            lambda lines: rendered.append(lines) or b"%PDF")
        ledger = _ledger(db_session, test_user)
        meetings_ledger.to_pdf(ledger)
        lines = meetings_ledger.pdf_lines(ledger)
        assert rendered == [lines]
        assert lines[0] == ("LeadPilot meetings-per-dollar ledger", "title")


# --------------------------------------------------------------------------
# Worker wiring
# --------------------------------------------------------------------------


def test_the_sweep_is_routed_and_scheduled():
    from app.workers import pilot_tasks  # noqa: F401
    from app.workers.celery_app import celery_app

    name = "app.workers.pilot_tasks.run_pilot_sweep"
    assert name in celery_app.tasks
    assert celery_app.amqp.router.route({}, name)["queue"].name == "default"
    entry = celery_app.conf.beat_schedule["pilot-mode-sweep"]
    assert entry["task"] == name


def test_the_task_impl_runs_the_sweep(db_session, test_user):
    from app.workers import pilot_tasks

    _on(db_session)
    _start(db_session, test_user)
    assert pilot_tasks.run_pilot_sweep_impl(db_session, now=FINAL)["ended"] == 1


# --------------------------------------------------------------------------
# Review fixes (grace period, races, stale objects, read-only reads, mail)
# --------------------------------------------------------------------------


def _stale_end(db, pilot, **values):
    """Another request ended the pilot: the row changes, this object does not."""
    db.execute(update(m.Pilot).where(m.Pilot.id == pilot.id)
               .values(status="ended", active_owner_id=None, **values)
               .execution_options(synchronize_session=False))
    db.commit()
    assert pilot.status == "active"          # the object is stale on purpose


class TestGracePeriod:
    def test_the_setting_defaults_to_24_hours_and_is_clamped(self, db_session):
        assert system_settings.DEFAULTS[pilot_mode.GRACE_SETTING][0] == 24
        assert pilot_mode.grace(db_session) == timedelta(hours=24)
        system_settings.set(db_session, pilot_mode.GRACE_SETTING, 10_000)
        assert pilot_mode.grace(db_session) == timedelta(hours=168)

    def test_a_meeting_held_just_after_day_30_still_counts(self, db_session, test_user,
                                                           seeded):
        _on(db_session)
        pilot = _start(db_session, test_user)
        assert pilot_mode.sweep(db_session, now=AFTER_END)["ended"] == 0
        # Marked held after midnight, for a meeting on day 30.
        l2 = seeded["leads"][1]
        db_session.add(m.Meeting(host_user_id=test_user.id, lead_id=l2.id, start_at=at(30, 22),
                                 end_at=at(30, 22) + timedelta(minutes=30),
                                 status=m.MeetingStatus.COMPLETED, actual_start_at=at(30, 22)))
        db_session.commit()
        assert pilot_mode.sweep(db_session, now=FINAL)["ended"] == 1
        db_session.refresh(pilot)
        assert pilot.verdict_json["ledger"]["totals"]["meetings_held"] == 2

    def test_the_grace_setting_moves_the_boundary(self, db_session, test_user):
        _on(db_session)
        system_settings.set(db_session, pilot_mode.GRACE_SETTING, 0)
        pilot = _start(db_session, test_user)
        ends_at = datetime(2026, 10, 1, tzinfo=UTC)
        assert pilot_mode.sweep(db_session, now=ends_at - timedelta(seconds=1))["ended"] == 0
        assert pilot_mode.sweep(db_session, now=ends_at)["ended"] == 1
        system_settings.set(db_session, pilot_mode.GRACE_SETTING, 48)
        second = _start(db_session, test_user, now=START + timedelta(days=40))
        assert pilot_mode.verdict_final_at(second, pilot_mode.grace(db_session)) == \
            second.ends_at.replace(tzinfo=UTC) + timedelta(hours=48)


class TestStartAndEndAfterDay30:
    def test_start_after_the_grace_finalizes_the_previous_pilot(self, client, db_session,
                                                                test_user):
        _on(db_session)
        old = _start(db_session, test_user, now=datetime.now(UTC) - timedelta(days=40))
        resp = client.post("/pilots", json={"criteria": CRITERIA})
        assert resp.status_code == 201, resp.text
        db_session.refresh(old)
        assert old.status == "ended" and old.end_reason == "completed"
        assert old.verdict_json["date_to"] == old.end_date.isoformat()

    def test_start_inside_the_grace_is_409_with_the_time(self, client, db_session,
                                                         test_user):
        _on(db_session)
        # ends_at is 12-36h ago (calendar days); a 72h grace keeps it pending.
        system_settings.set(db_session, pilot_mode.GRACE_SETTING, 72)
        old = _start(db_session, test_user,
                     now=datetime.now(UTC) - timedelta(days=30, hours=12))
        resp = client.post("/pilots", json={"criteria": CRITERIA})
        assert resp.status_code == 409 and "verdict is pending until" in resp.json()["detail"]
        db_session.refresh(old)
        assert old.status == "active"

    def test_end_after_day_30_is_200_with_the_full_period_verdict(self, client, db_session,
                                                                  test_user):
        _on(db_session)
        pilot = _start(db_session, test_user, now=datetime.now(UTC) - timedelta(days=40))
        resp = client.post(f"/pilots/{pilot.id}/end")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "ended" and body["end_reason"] == "completed"
        assert body["verdict"]["date_to"] == pilot.end_date.isoformat()
        assert client.post(f"/pilots/{pilot.id}/end").status_code == 409


class TestReadsNeverWrite:
    def test_viewer_and_sdr_reads_and_downloads_write_nothing(self, client, db_session,
                                                             test_user, team):
        _on(db_session)
        ws, people = team
        due = _start(db_session, test_user, now=datetime.now(UTC) - timedelta(days=40))
        for role in ("viewer", "sdr"):
            headers = _as(people[role], ws)
            for path in ("/pilots", "/pilots/current", f"/pilots/{due.id}",
                         f"/pilots/{due.id}/export?format=csv"):
                client.get(path, headers=headers)
        db_session.refresh(due)
        assert due.status == "active" and due.verdict_json is None

        pilot_mode.end_pilot(db_session, due, reason="completed")
        for role in ("viewer", "sdr"):
            resp = client.get(f"/pilots/{due.id}/export?format=csv",
                              headers=_as(people[role], ws))
            assert resp.status_code == 200
        db_session.refresh(due)
        assert due.exported_at is None
        assert client.get(f"/pilots/{due.id}/export?format=csv",
                          headers=_as(people["manager"], ws)).status_code == 200
        db_session.refresh(due)
        assert due.exported_at is not None


class TestStaleObjectsAndRaces:
    def test_no_scorecard_for_a_pilot_another_request_ended(self, db_session, test_user,
                                                            mailbox):
        _on(db_session)
        pilot = _start(db_session, test_user)
        _stale_end(db_session, pilot)
        assert pilot_mode.send_due_scorecard(db_session, pilot,
                                             START + timedelta(days=7, hours=1)) == "not_active"
        assert mailbox == [] and _scorecards(db_session, pilot) == []

    def test_a_pilot_ended_after_the_claim_releases_it_unsent(self, db_session, test_user,
                                                              mailbox, monkeypatch):
        _on(db_session)
        pilot = _start(db_session, test_user)
        answers = iter(["active", "ended"])
        monkeypatch.setattr(pilot_mode, "_fresh_status", lambda db, p: next(answers))
        assert pilot_mode.send_due_scorecard(db_session, pilot,
                                             START + timedelta(days=7, hours=1)) == "not_active"
        assert mailbox == [] and _scorecards(db_session, pilot) == []

    def test_end_pilot_loser_returns_the_winners_verdict(self, db_session, test_user):
        pilot = _start(db_session, test_user)
        _stale_end(db_session, pilot, verdict_json={"winner": True}, end_reason="completed")
        result = pilot_mode.end_pilot(db_session, pilot, reason="ended_early", now=START)
        assert result.status == "ended"
        assert result.verdict_json == {"winner": True} and result.end_reason == "completed"

    def test_verdict_email_loser_sends_nothing(self, db_session, test_user, mailbox):
        pilot = _start(db_session, test_user)
        pilot_mode.end_pilot(db_session, pilot, reason="ended_early", now=START)
        db_session.execute(update(m.Pilot).where(m.Pilot.id == pilot.id)
                           .values(verdict_email_status="sending", verdict_email_attempts=1)
                           .execution_options(synchronize_session=False))
        db_session.commit()
        assert pilot.verdict_email_status is None      # stale
        assert pilot_mode.send_verdict_email(db_session, pilot, START) == "already_claimed"
        assert mailbox == []

    def test_a_sending_verdict_email_is_never_retried(self, db_session, test_user, mailbox):
        """A crash after the claim leaves `sending`: no automatic resend."""
        _on(db_session)
        pilot = _start(db_session, test_user)
        pilot_mode.end_pilot(db_session, pilot, reason="ended_early", now=START)
        pilot.verdict_email_status, pilot.verdict_email_attempts = "sending", 1
        db_session.commit()
        for hour in range(3):
            assert pilot_mode.sweep(db_session, now=FINAL + timedelta(hours=hour)) \
                ["verdict_emails_sent"] == 0
        assert mailbox == []

    def test_the_unique_race_is_409(self, db_session, test_user, monkeypatch):
        pilot_mode.start_pilot(db_session, test_user, criteria=CRITERIA)
        monkeypatch.setattr(pilot_mode, "get_active", lambda db, uid: None)
        with pytest.raises(pilot_mode.PilotError) as err:
            pilot_mode.start_pilot(db_session, test_user, criteria=CRITERIA)
        assert err.value.status_code == 409 and "already running" in str(err.value)

    def test_another_integrity_error_is_not_called_already_running(
            self, db_session, test_user, monkeypatch):
        def boom():
            raise IntegrityError("INSERT INTO pilots", {},
                                 Exception("FOREIGN KEY constraint failed"))

        monkeypatch.setattr(db_session, "commit", boom)
        with pytest.raises(IntegrityError):
            pilot_mode.start_pilot(db_session, test_user, criteria=CRITERIA)


class TestMailCopyAndSuspension:
    def test_scorecard_copy_does_not_claim_the_reader_started_it(self, db_session, test_user,
                                                                mailbox):
        _on(db_session)
        _start(db_session, test_user)
        pilot_mode.sweep(db_session, now=START + timedelta(days=7, hours=1))
        text = mailbox[0]["text"]
        assert "because you started" not in text
        assert "a 30-day pilot is running on your LeadPilot account" in text

    def test_a_suspended_owner_is_not_mailed(self, db_session, test_user, mailbox):
        _on(db_session)
        pilot = _start(db_session, test_user)
        test_user.is_suspended = True
        db_session.commit()
        assert pilot_mode.send_due_scorecard(
            db_session, pilot, START + timedelta(days=7, hours=1)) == "owner_suspended"
        assert _scorecards(db_session, pilot) == []
        assert pilot_mode.sweep(db_session, now=FINAL)["ended"] == 1   # verdict still stored
        db_session.refresh(pilot)
        assert pilot.verdict_json is not None
        assert pilot.verdict_email_attempts == 0 and mailbox == []

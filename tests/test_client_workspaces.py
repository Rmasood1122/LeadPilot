"""Part 1 Feature 11 — founder / agency mode: per-client workspaces.

The properties that matter:
  * isolation is at the QUERY, not a filter someone can forget,
  * the sending-domain pool is enforced in the SEND PATH, not just rendered,
  * an empty pool means no restriction, so nothing changes for an account
    without clients,
  * "assigned to no client" is the agency's own work, not an error,
  * the billing view shows its working, because a client will query the total.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.services import client_workspaces as cw
from app.services import workspaces
from tests.conftest import auth_headers

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def agency(db_session, test_user):
    return workspaces.personal_workspace(db_session, test_user)


@pytest.fixture()
def client_row(db_session, agency):
    return cw.create(db_session, agency, name="Blaze Safety",
                     monthly_fee_cents=200000, per_meeting_fee_cents=15000,
                     currency="GBP", billing_email="ap@blaze.test")


# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------


class TestCrud:
    def test_a_client_gets_a_slug(self, db_session, client_row):
        assert client_row.slug == "blaze-safety"
        assert client_row.status == cw.ACTIVE

    def test_two_clients_with_the_same_name_get_different_slugs(self, db_session, agency):
        first = cw.create(db_session, agency, name="Acme")
        second = cw.create(db_session, agency, name="Acme")
        assert first.slug != second.slug

    def test_a_nameless_client_is_refused(self, db_session, agency):
        with pytest.raises(cw.ClientError):
            cw.create(db_session, agency, name="   ")

    def test_a_negative_fee_is_refused_rather_than_stored(self, db_session, agency):
        with pytest.raises(cw.ClientError):
            cw.create(db_session, agency, name="Acme", monthly_fee_cents=-1)

    def test_an_unknown_status_is_refused(self, db_session, client_row):
        with pytest.raises(cw.ClientError):
            cw.update(db_session, client_row, {"status": "vibes"})

    def test_archiving_stamps_the_time_and_hides_it_from_the_default_list(
            self, db_session, agency, client_row):
        cw.update(db_session, client_row, {"status": cw.ARCHIVED})
        assert client_row.archived_at is not None
        assert cw.clients(db_session, agency) == []
        assert len(cw.clients(db_session, agency, include_archived=True)) == 1

    def test_un_archiving_clears_the_stamp(self, db_session, client_row):
        cw.update(db_session, client_row, {"status": cw.ARCHIVED})
        cw.update(db_session, client_row, {"status": cw.ACTIVE})
        assert client_row.archived_at is None

    def test_a_client_in_another_agency_does_not_exist(self, db_session, agency,
                                                       client_row):
        other_user = m.User(email="other-agency@test.dev", email_verified=True)
        db_session.add(other_user)
        db_session.commit()
        other = workspaces.personal_workspace(db_session, other_user)
        assert cw.owned(db_session, other, client_row.id) is None


# --------------------------------------------------------------------------
# Assignment
# --------------------------------------------------------------------------


class TestAssignment:
    def test_a_campaign_can_be_filed_under_a_client(self, db_session, client_row,
                                                    verified_strategy):
        cw.assign_strategy(db_session, verified_strategy, client_row)
        assert verified_strategy.client_workspace_id == client_row.id
        assert cw.strategies_for(db_session, client_row) == [verified_strategy]

    def test_it_can_be_moved_back_to_the_agencys_own_work(self, db_session, client_row,
                                                          verified_strategy):
        """Not an error state: work the agency does for itself is real."""
        cw.assign_strategy(db_session, verified_strategy, client_row)
        cw.assign_strategy(db_session, verified_strategy, None)
        assert verified_strategy.client_workspace_id is None

    def test_existing_campaigns_are_unassigned_rather_than_force_fitted(
            self, db_session, verified_strategy):
        assert verified_strategy.client_workspace_id is None


# --------------------------------------------------------------------------
# The sending-domain pool
# --------------------------------------------------------------------------


class TestPool:
    def test_a_domain_is_normalised(self, db_session, client_row):
        cw.add_domain(db_session, client_row, "  @Blaze-Outreach.COM ")
        assert cw.pool(db_session, client_row) == ["blaze-outreach.com"]

    def test_adding_the_same_domain_twice_is_one_row(self, db_session, client_row):
        cw.add_domain(db_session, client_row, "blaze.com")
        cw.add_domain(db_session, client_row, "blaze.com")
        assert cw.pool(db_session, client_row) == ["blaze.com"]

    @pytest.mark.parametrize("bad", ["not a domain", "http://blaze.com", "blaze", "@@"])
    def test_a_non_domain_is_refused(self, db_session, client_row, bad):
        with pytest.raises(cw.ClientError):
            cw.add_domain(db_session, client_row, bad)

    def test_removing_returns_whether_anything_was_there(self, db_session, client_row):
        cw.add_domain(db_session, client_row, "blaze.com")
        assert cw.remove_domain(db_session, client_row, "blaze.com") is True
        assert cw.remove_domain(db_session, client_row, "blaze.com") is False

    def test_an_empty_pool_means_no_restriction(self, db_session, client_row,
                                                verified_strategy):
        """An agency that has not set pools up sends exactly as it does today."""
        cw.assign_strategy(db_session, verified_strategy, client_row)
        assert cw.domain_allowed(db_session, verified_strategy,
                                 "sales@anything.com") is None

    def test_a_campaign_with_no_client_is_unrestricted(self, db_session,
                                                       verified_strategy):
        assert cw.domain_allowed(db_session, verified_strategy,
                                 "sales@anything.com") is None

    def test_a_domain_in_the_pool_is_allowed(self, db_session, client_row,
                                             verified_strategy):
        cw.assign_strategy(db_session, verified_strategy, client_row)
        cw.add_domain(db_session, client_row, "blaze-outreach.com")
        assert cw.domain_allowed(db_session, verified_strategy,
                                 "sara@blaze-outreach.com") is None

    def test_a_domain_outside_the_pool_is_refused_with_a_readable_reason(
            self, db_session, client_row, verified_strategy):
        cw.assign_strategy(db_session, verified_strategy, client_row)
        cw.add_domain(db_session, client_row, "blaze-outreach.com")
        reason = cw.domain_allowed(db_session, verified_strategy, "sara@other.com")
        assert reason is not None
        assert "Blaze Safety" in reason
        assert "blaze-outreach.com" in reason

    def test_the_check_fails_open_when_it_breaks(self, db_session, client_row,
                                                 verified_strategy, monkeypatch):
        """It routes sending; it must not stop it."""
        cw.assign_strategy(db_session, verified_strategy, client_row)
        monkeypatch.setattr(cw, "pool",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        assert cw.domain_allowed(db_session, verified_strategy, "a@b.com") is None


class TestSendPath:
    def test_a_send_from_outside_the_pool_is_blocked(
            self, db_session, fake_claude, enrolled, gmail_account, client_row,
            verified_strategy, fake_channel, monkeypatch):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        gmail_account.email_address = "sales@wrong-domain.com"
        cw.assign_strategy(db_session, verified_strategy, client_row)
        cw.add_domain(db_session, client_row, "blaze-outreach.com")
        db_session.commit()
        message = db_session.query(m.Message).filter_by(
            status=m.MessageStatus.SCHEDULED).first()
        result = outreach_tasks.send_message_impl(db_session, message.id, now=NOW)
        db_session.refresh(message)
        assert result == "blocked_client_domain"
        assert fake_channel.sent == []
        assert "client's pool" in message.error

    def test_a_send_from_inside_the_pool_goes_out(
            self, db_session, fake_claude, enrolled, gmail_account, client_row,
            verified_strategy, fake_channel, monkeypatch):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        gmail_account.email_address = "sara@blaze-outreach.com"
        cw.assign_strategy(db_session, verified_strategy, client_row)
        cw.add_domain(db_session, client_row, "blaze-outreach.com")
        db_session.commit()
        message = db_session.query(m.Message).filter_by(
            status=m.MessageStatus.SCHEDULED).first()
        assert outreach_tasks.send_message_impl(db_session, message.id, now=NOW) == "sent"

    def test_an_account_with_no_clients_sends_exactly_as_before(
            self, db_session, fake_claude, enrolled, gmail_account, fake_channel,
            monkeypatch):
        from app.workers import outreach_tasks

        monkeypatch.setattr(outreach_tasks, "_get_channel", lambda s, a: fake_channel)
        message = db_session.query(m.Message).filter_by(
            status=m.MessageStatus.SCHEDULED).first()
        assert outreach_tasks.send_message_impl(db_session, message.id, now=NOW) == "sent"


# --------------------------------------------------------------------------
# Reporting and billing
# --------------------------------------------------------------------------


class TestReport:
    def _campaign(self, db_session, strategy, sequence, *, leads=2, replies=1,
                  meetings=1):
        for index in range(leads):
            lead = m.Lead(strategy_id=strategy.id, source="apollo",
                          external_id=f"R{strategy.id}{index}",
                          email=f"r{strategy.id.hex[:4]}{index}@co.test",
                          status=m.LeadStatus.CONTACTED)
            db_session.add(lead)
            db_session.flush()
            db_session.add(m.Message(sequence_id=sequence.id, lead_id=lead.id,
                                     channel=m.ChannelType.EMAIL, step_no=1,
                                     template="t", status=m.MessageStatus.SENT,
                                     sent_at=NOW))
            if index < replies:
                db_session.add(m.Outcome(lead_id=lead.id, strategy_id=strategy.id,
                                         event=m.OutcomeEvent.REPLIED,
                                         channel="email", ts=NOW))
            if index < meetings:
                db_session.add(m.Outcome(lead_id=lead.id, strategy_id=strategy.id,
                                         event=m.OutcomeEvent.BOOKED,
                                         channel="email", ts=NOW))
        db_session.commit()

    def test_a_client_with_no_campaigns_reports_zeroes_not_an_error(
            self, db_session, client_row):
        report = cw.report(db_session, client_row)
        assert report["strategies"] == 0
        assert report["reply_rate"] is None

    def test_a_rate_is_null_not_zero_when_nothing_was_sent(self, db_session,
                                                           client_row,
                                                           verified_strategy):
        """0% reads as failure in a report someone is about to forward to
        that client."""
        cw.assign_strategy(db_session, verified_strategy, client_row)
        assert cw.report(db_session, client_row)["reply_rate"] is None

    def test_the_numbers_cover_only_this_clients_campaigns(
            self, db_session, agency, client_row, verified_strategy, email_sequence,
            product_with_strategy):
        """Isolation at the query, not a filter someone can forget."""
        other_client = cw.create(db_session, agency, name="Other Co")
        other_strategy = m.Strategy(product_id=verified_strategy.product_id,
                                    flow_type=verified_strategy.flow_type,
                                    status=m.StrategyStatus.VERIFIED)
        db_session.add(other_strategy)
        db_session.commit()
        other_sequence = m.Sequence(strategy_id=other_strategy.id,
                                    channel=m.ChannelType.EMAIL, name="Other",
                                    status=m.SequenceStatus.ACTIVE)
        db_session.add(other_sequence)
        db_session.commit()

        cw.assign_strategy(db_session, verified_strategy, client_row)
        cw.assign_strategy(db_session, other_strategy, other_client)
        self._campaign(db_session, verified_strategy, email_sequence, leads=2)
        self._campaign(db_session, other_strategy, other_sequence, leads=5)

        mine = cw.report(db_session, client_row)
        theirs = cw.report(db_session, other_client)
        assert mine["leads"] == 2
        assert theirs["leads"] == 5
        assert mine["sent"] == 2

    def test_won_revenue_is_counted_in_cents(self, db_session, client_row,
                                             verified_strategy, test_user):
        cw.assign_strategy(db_session, verified_strategy, client_row)
        db_session.add(m.Deal(user_id=test_user.id, strategy_id=verified_strategy.id,
                              name="Pilot", value_cents=450000,
                              stage=m.DealStage.WON))
        db_session.commit()
        assert cw.report(db_session, client_row)["revenue_cents"] == 450000


class TestBilling:
    def test_a_retainer_only_client(self, db_session, agency):
        client = cw.create(db_session, agency, name="Retainer Co",
                           monthly_fee_cents=150000)
        view = cw.billing_view(db_session, client, now=NOW)
        assert view["total_cents"] == 150000
        assert view["variable_cents"] == 0
        assert [line["label"] for line in view["lines"]] == ["Monthly retainer"]

    def test_a_per_meeting_client_shows_the_count(self, db_session, agency,
                                                  verified_strategy, email_sequence):
        """An agency that cannot show the count loses the argument."""
        client = cw.create(db_session, agency, name="PPM Co",
                           per_meeting_fee_cents=20000)
        cw.assign_strategy(db_session, verified_strategy, client)
        lead = m.Lead(strategy_id=verified_strategy.id, source="apollo",
                      external_id="B1", email="b1@co.test",
                      status=m.LeadStatus.MEETING_BOOKED)
        db_session.add(lead)
        db_session.flush()
        for _ in range(3):
            db_session.add(m.Outcome(lead_id=lead.id, strategy_id=verified_strategy.id,
                                     event=m.OutcomeEvent.BOOKED, channel="email",
                                     ts=NOW))
        db_session.commit()
        view = cw.billing_view(db_session, client, now=NOW)
        assert view["meetings_this_period"] == 3
        assert view["variable_cents"] == 60000
        assert "3 meetings booked" in view["lines"][0]["label"]

    def test_meetings_before_this_month_are_not_billed_again(
            self, db_session, agency, verified_strategy, email_sequence):
        client = cw.create(db_session, agency, name="PPM Co",
                           per_meeting_fee_cents=20000)
        cw.assign_strategy(db_session, verified_strategy, client)
        lead = m.Lead(strategy_id=verified_strategy.id, source="apollo",
                      external_id="B2", email="b2@co.test",
                      status=m.LeadStatus.MEETING_BOOKED)
        db_session.add(lead)
        db_session.flush()
        db_session.add(m.Outcome(lead_id=lead.id, strategy_id=verified_strategy.id,
                                 event=m.OutcomeEvent.BOOKED, channel="email",
                                 ts=NOW - timedelta(days=45)))
        db_session.commit()
        assert cw.billing_view(db_session, client, now=NOW)["meetings_this_period"] == 0

    def test_the_clients_own_currency_is_used(self, db_session, client_row):
        assert cw.billing_view(db_session, client_row, now=NOW)["currency"] == "GBP"


class TestOverview:
    def test_unassigned_work_is_shown_rather_than_hidden(
            self, db_session, agency, test_user, verified_strategy):
        """Work that belongs to nobody is exactly the work that stops being
        invoiced."""
        overview = cw.overview(db_session, agency, test_user.id)
        assert overview["unassigned_strategies"] == 1
        assert "Assign them to bill for them" in overview["note"]


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


class TestApi:
    def test_creating_and_listing(self, client, db_session, test_user):
        created = client.post("/clients", json={"name": "Blaze Safety",
                                                "monthly_fee_cents": 200000},
                              headers=auth_headers(test_user))
        assert created.status_code == 201
        listed = client.get("/clients", headers=auth_headers(test_user))
        assert listed.json()["clients"][0]["name"] == "Blaze Safety"

    def test_a_negative_fee_is_a_422(self, client, db_session, test_user):
        assert client.post("/clients", json={"name": "X", "monthly_fee_cents": -5},
                           headers=auth_headers(test_user)).status_code == 422

    def test_the_report_endpoint(self, client, db_session, client_row, test_user):
        response = client.get(f"/clients/{client_row.id}/report",
                              headers=auth_headers(test_user))
        assert response.status_code == 200
        assert response.json()["name"] == "Blaze Safety"

    def test_the_billing_endpoint_shows_the_working(self, client, db_session,
                                                    client_row, test_user):
        body = client.get(f"/clients/{client_row.id}/billing",
                          headers=auth_headers(test_user)).json()
        assert body["total_cents"] == 200000
        assert body["currency"] == "GBP"
        assert body["lines"]

    def test_adding_and_removing_a_domain(self, client, db_session, client_row,
                                          test_user):
        added = client.post(f"/clients/{client_row.id}/domains",
                            json={"domain": "blaze-outreach.com"},
                            headers=auth_headers(test_user))
        assert added.status_code == 201
        assert added.json()["sending_domains"] == ["blaze-outreach.com"]
        removed = client.delete(
            f"/clients/{client_row.id}/domains/blaze-outreach.com",
            headers=auth_headers(test_user))
        assert removed.json()["sending_domains"] == []

    def test_removing_a_domain_that_is_not_there_is_a_404(self, client, db_session,
                                                          client_row, test_user):
        assert client.delete(f"/clients/{client_row.id}/domains/nope.com",
                             headers=auth_headers(test_user)).status_code == 404

    def test_a_bad_domain_is_a_422(self, client, db_session, client_row, test_user):
        assert client.post(f"/clients/{client_row.id}/domains",
                           json={"domain": "not a domain"},
                           headers=auth_headers(test_user)).status_code == 422

    def test_assigning_a_campaign(self, client, db_session, client_row,
                                  verified_strategy, test_user):
        response = client.post(f"/strategies/{verified_strategy.id}/client",
                               json={"client_id": str(client_row.id)},
                               headers=auth_headers(test_user))
        assert response.status_code == 200
        assert response.json()["client_name"] == "Blaze Safety"

    def test_unassigning_a_campaign(self, client, db_session, client_row,
                                    verified_strategy, test_user):
        client.post(f"/strategies/{verified_strategy.id}/client",
                    json={"client_id": str(client_row.id)},
                    headers=auth_headers(test_user))
        response = client.post(f"/strategies/{verified_strategy.id}/client",
                               json={"client_id": None},
                               headers=auth_headers(test_user))
        assert response.json()["client_id"] is None

    def test_another_agency_cannot_see_or_touch_a_client(self, client, db_session,
                                                         client_row):
        other = m.User(email="nosy-agency@test.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        assert client.get(f"/clients/{client_row.id}",
                          headers=auth_headers(other)).status_code == 404
        assert client.get("/clients",
                          headers=auth_headers(other)).json()["clients"] == []
        assert client.post(f"/clients/{client_row.id}/domains",
                           json={"domain": "steal.com"},
                           headers=auth_headers(other)).status_code == 404

"""M9 CRM dashboards — aggregation correctness against seeded fixture data.

Every number on all four pages is asserted against a hand-counted fixture.
That matters more here than in most tests: an aggregation bug does not throw,
it produces a plausible-looking number, and a dashboard that is confidently
wrong is worse than one that is broken -- nobody knows to distrust it.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.services import crm_service


def _lead(db, strategy, *, status, source="apollo", index=0, company=None,
          created=None):
    lead = m.Lead(
        strategy_id=strategy.id, source=source, external_id=f"d{index}",
        full_name=f"Lead {index}", company=company or f"Co {index}",
        email=f"d{index}@x.test", status=status,
    )
    if created is not None:
        lead.created_at = created
        lead.updated_at = created
    db.add(lead)
    return lead


@pytest.fixture()
def funnel_data(db_session, verified_strategy):
    """A funnel with a known shape.

    sourced 4 | enriched 3 | email_found 2 | verified 2 |
    contacted 2 | replied 1 | meeting_booked 1 | dropped 2 | flagged 1
    """
    counts = {
        m.LeadStatus.SOURCED: 4,
        m.LeadStatus.ENRICHED: 3,
        m.LeadStatus.EMAIL_FOUND: 2,
        m.LeadStatus.VERIFIED: 2,
        m.LeadStatus.CONTACTED: 2,
        m.LeadStatus.REPLIED: 1,
        m.LeadStatus.MEETING_BOOKED: 1,
        m.LeadStatus.DROPPED: 2,
        m.LeadStatus.FLAGGED: 1,
    }
    index = 0
    made = []
    for status, count in counts.items():
        for _ in range(count):
            made.append(_lead(db_session, verified_strategy, status=status,
                              index=index))
            index += 1
    db_session.commit()
    return {"leads": made, "counts": counts}


class TestPipelinePage:
    def test_status_counts_are_exact(self, client, funnel_data):
        body = client.get("/crm/dashboard/pipeline").json()
        assert body["total_leads"] == 18
        assert body["by_status"]["sourced"] == 4
        assert body["by_status"]["dropped"] == 2
        assert body["by_status"]["meeting_booked"] == 1

    def test_active_excludes_terminal_stages(self, client, funnel_data):
        """A booked meeting and a dropped address are finished, not active.
        18 total - 2 dropped - 1 booked = 15."""
        assert client.get("/crm/dashboard/pipeline").json()["active_leads"] == 15

    def test_funnel_reach_is_cumulative(self, client, funnel_data):
        """Status is a single current value, not a set of stages passed
        through. `reached` must count leads AT a stage or BEYOND it, or the
        funnel reads as if every later stage were a leak."""
        funnel = {row["stage"]: row
                  for row in client.get("/crm/dashboard/pipeline").json()["funnel"]}
        # meeting_booked(1) -> replied(1+1=2) -> contacted(2+2=4) ->
        # verified(4+2=6) -> email_found(6+2=8) -> enriched(8+3=11) ->
        # sourced(11+4=15). `flagged` and `dropped` are exits, not stages.
        assert funnel["meeting_booked"]["reached"] == 1
        assert funnel["replied"]["reached"] == 2
        assert funnel["contacted"]["reached"] == 4
        assert funnel["verified"]["reached"] == 6
        assert funnel["sourced"]["reached"] == 15

    def test_conversion_never_exceeds_one(self, client, funnel_data):
        """The specific bug cumulative reach exists to prevent: dividing the
        `replied` COLUMN by the `contacted` COLUMN reports over 100% the
        moment more leads have replied than are sitting unanswered."""
        for row in client.get("/crm/dashboard/pipeline").json()["funnel"]:
            rate = row["conversion_from_previous"]
            if rate is not None:
                assert 0.0 <= rate <= 1.0, row

    def test_first_stage_has_no_conversion(self, client, funnel_data):
        funnel = client.get("/crm/dashboard/pipeline").json()["funnel"]
        assert funnel[0]["stage"] == "sourced"
        assert funnel[0]["conversion_from_previous"] is None

    def test_dropped_is_not_a_funnel_stage(self, client, funnel_data):
        stages = [row["stage"]
                  for row in client.get("/crm/dashboard/pipeline").json()["funnel"]]
        assert "dropped" not in stages
        assert "flagged" not in stages

    def test_bookings_this_week_and_month_use_real_timestamps(
        self, client, db_session, funnel_data
    ):
        lead = funnel_data["leads"][0]
        now = datetime.now(timezone.utc)
        db_session.add_all([
            m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.BOOKED,
                      ts=now - timedelta(days=2)),
            m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.BOOKED,
                      ts=now - timedelta(days=20)),
            m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.BOOKED,
                      ts=now - timedelta(days=200)),
        ])
        db_session.commit()
        body = client.get("/crm/dashboard/pipeline").json()
        assert body["meetings_booked_week"] == 1
        assert body["meetings_booked_month"] == 2

    def test_bookings_trend_is_bucketed_by_day(self, client, db_session,
                                               funnel_data):
        lead = funnel_data["leads"][0]
        now = datetime.now(timezone.utc)
        db_session.add_all([
            m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.BOOKED,
                      ts=now - timedelta(days=1)),
            m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.BOOKED,
                      ts=now - timedelta(days=1, hours=2)),
            m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.BOOKED,
                      ts=now - timedelta(days=3)),
        ])
        db_session.commit()
        trend = client.get("/crm/dashboard/pipeline").json()["bookings_trend"]
        assert sum(point["count"] for point in trend) == 3
        by_bucket = {point["bucket"]: point["count"] for point in trend}
        assert max(by_bucket.values()) == 2, "same-day bookings must share a bucket"

    def test_top_strategy_is_the_one_with_most_bookings(self, client, db_session,
                                                        test_user,
                                                        verified_strategy,
                                                        funnel_data):
        second_product = m.Product(user_id=test_user.id, name="Second",
                                   description="d", type=m.ProductType.PRODUCT)
        db_session.add(second_product)
        db_session.flush()
        second = m.Strategy(product_id=second_product.id,
                            flow_type=m.FlowType.NO_CLIENTS,
                            status=m.StrategyStatus.VERIFIED)
        db_session.add(second)
        db_session.flush()
        winner = _lead(db_session, second, status=m.LeadStatus.MEETING_BOOKED,
                       index=99)
        db_session.flush()
        db_session.add_all([
            m.Outcome(lead_id=winner.id, event=m.OutcomeEvent.BOOKED),
            m.Outcome(lead_id=winner.id, event=m.OutcomeEvent.BOOKED),
            m.Outcome(lead_id=funnel_data["leads"][0].id,
                      event=m.OutcomeEvent.BOOKED),
        ])
        db_session.commit()

        top = client.get("/crm/dashboard/pipeline").json()["top_strategy"]
        assert top["strategy_id"] == str(second.id)
        assert top["meetings_booked"] == 2

    def test_empty_account_returns_zeroes_not_an_error(self, client):
        body = client.get("/crm/dashboard/pipeline").json()
        assert body["total_leads"] == 0
        assert body["top_strategy"] is None
        assert all(row["reached"] == 0 for row in body["funnel"])

    def test_strategy_filter_narrows_the_aggregate(self, client, db_session,
                                                   test_user, funnel_data):
        other_product = m.Product(user_id=test_user.id, name="Other",
                                  description="d", type=m.ProductType.PRODUCT)
        db_session.add(other_product)
        db_session.flush()
        other = m.Strategy(product_id=other_product.id,
                           flow_type=m.FlowType.NO_CLIENTS,
                           status=m.StrategyStatus.VERIFIED)
        db_session.add(other)
        db_session.flush()
        _lead(db_session, other, status=m.LeadStatus.SOURCED, index=200)
        db_session.commit()

        assert client.get("/crm/dashboard/pipeline").json()["total_leads"] == 19
        scoped = client.get(
            f"/crm/dashboard/pipeline?strategy_id={other.id}").json()
        assert scoped["total_leads"] == 1


class TestLeadAnalyticsPage:
    def test_source_breakdown_counts_each_provider(self, client, db_session,
                                                   verified_strategy):
        for index in range(3):
            _lead(db_session, verified_strategy, status=m.LeadStatus.VERIFIED,
                  source="apollo", index=index)
        _lead(db_session, verified_strategy, status=m.LeadStatus.VERIFIED,
              source="manual", index=10)
        db_session.commit()
        sources = {row["source"]: row["count"]
                   for row in client.get("/crm/dashboard/leads").json()["sources"]}
        assert sources == {"apollo": 3, "manual": 1}

    def test_verification_ratio_excludes_leads_that_never_reached_hunter(
        self, client, db_session, verified_strategy
    ):
        """Counting `sourced` rows in the denominator would make a fresh batch
        look like a deliverability problem."""
        for index in range(3):
            _lead(db_session, verified_strategy, status=m.LeadStatus.SOURCED,
                  index=index)
        _lead(db_session, verified_strategy, status=m.LeadStatus.VERIFIED,
              index=10)
        _lead(db_session, verified_strategy, status=m.LeadStatus.FLAGGED,
              index=11)
        _lead(db_session, verified_strategy, status=m.LeadStatus.DROPPED,
              index=12)
        db_session.commit()

        verification = client.get("/crm/dashboard/leads").json()["verification"]
        assert verification["total"] == 3, "sourced leads must not be counted"
        assert verification["verified"] == 1
        assert verification["verified_ratio"] == pytest.approx(1 / 3, abs=1e-4)

    def test_verification_ratio_is_none_rather_than_zero_when_empty(self, client):
        """None means "no data"; 0.0 means "everything failed". Rendering the
        second when the first is true is a lie the chart would tell."""
        verification = client.get("/crm/dashboard/leads").json()["verification"]
        assert verification["total"] == 0
        assert verification["verified_ratio"] is None

    def test_velocity_marks_estimated_stages_honestly(self, client, db_session,
                                                       verified_strategy):
        """Leads whose status last changed before M9 have no stage_entered_at,
        and 0019 deliberately does not backfill one. Their time-in-stage is
        derived from updated_at, and the payload must say so -- a single
        blended average with no marker looks authoritative while being partly
        invented."""
        old = _lead(db_session, verified_strategy, status=m.LeadStatus.CONTACTED,
                    index=1)
        db_session.commit()

        velocity = {row["stage"]: row
                    for row in client.get("/crm/dashboard/leads").json()["velocity"]}
        assert velocity["contacted"]["estimated"] == 1
        assert velocity["contacted"]["measured"] == 0
        assert velocity["contacted"]["fully_measured"] is False

        # After a real transition the measurement exists and is marked as such.
        client.patch(f"/crm/leads/{old.id}", json={"status": "replied"})
        velocity = {row["stage"]: row
                    for row in client.get("/crm/dashboard/leads").json()["velocity"]}
        assert velocity["replied"]["measured"] == 1
        assert velocity["replied"]["fully_measured"] is True

    def test_stuck_leads_use_the_threshold(self, client, db_session,
                                           verified_strategy):
        long_ago = datetime.now(timezone.utc) - timedelta(days=30)
        stale = _lead(db_session, verified_strategy,
                      status=m.LeadStatus.CONTACTED, index=1, created=long_ago)
        _lead(db_session, verified_strategy, status=m.LeadStatus.CONTACTED,
              index=2)
        db_session.commit()

        body = client.get("/crm/dashboard/leads?stuck_after_days=7").json()
        assert body["stuck_count"] == 1
        assert body["stuck_leads"][0]["lead_id"] == str(stale.id)

        assert client.get(
            "/crm/dashboard/leads?stuck_after_days=90").json()["stuck_count"] == 0

    def test_terminal_stages_are_never_stuck(self, client, db_session,
                                             verified_strategy):
        """A booked meeting and a dropped address would otherwise be reported
        as problems forever."""
        long_ago = datetime.now(timezone.utc) - timedelta(days=365)
        _lead(db_session, verified_strategy,
              status=m.LeadStatus.MEETING_BOOKED, index=1, created=long_ago)
        _lead(db_session, verified_strategy, status=m.LeadStatus.DROPPED,
              index=2, created=long_ago)
        db_session.commit()
        assert client.get("/crm/dashboard/leads").json()["stuck_count"] == 0

    def test_stuck_list_is_capped_but_the_count_is_not(self, client, db_session,
                                                        verified_strategy):
        """The count drives a headline number; the list drives a table. Capping
        both would under-report the problem."""
        long_ago = datetime.now(timezone.utc) - timedelta(days=30)
        for index in range(60):
            _lead(db_session, verified_strategy,
                  status=m.LeadStatus.CONTACTED, index=index, created=long_ago)
        db_session.commit()
        body = client.get("/crm/dashboard/leads").json()
        assert body["stuck_count"] == 60
        assert len(body["stuck_leads"]) == 50


@pytest.fixture()
def campaign_data(db_session, verified_strategy):
    """One email sequence: 4 dispatched messages (1 bounced), 2 replies,
    1 booking, split across variants A (3 sends) and B (1 send)."""
    sequence = m.Sequence(strategy_id=verified_strategy.id,
                          channel=m.ChannelType.EMAIL, name="Outreach",
                          status=m.SequenceStatus.ACTIVE)
    db_session.add(sequence)
    db_session.flush()

    leads, messages = [], []
    for index in range(4):
        lead = _lead(db_session, verified_strategy,
                     status=m.LeadStatus.CONTACTED, index=index)
        leads.append(lead)
    db_session.flush()

    for index, lead in enumerate(leads):
        message = m.Message(
            sequence_id=sequence.id, lead_id=lead.id,
            channel=m.ChannelType.EMAIL, step_no=1, template="t",
            variant="A" if index < 3 else "B",
            status=(m.MessageStatus.BOUNCED if index == 3
                    else m.MessageStatus.SENT),
        )
        db_session.add(message)
        messages.append(message)
    db_session.flush()

    db_session.add_all([
        m.Outcome(lead_id=leads[0].id, message_id=messages[0].id,
                  event=m.OutcomeEvent.REPLIED, channel="email"),
        m.Outcome(lead_id=leads[1].id, message_id=messages[1].id,
                  event=m.OutcomeEvent.REPLIED, channel="email"),
        m.Outcome(lead_id=leads[0].id, message_id=messages[0].id,
                  event=m.OutcomeEvent.BOOKED, channel="email"),
        m.Outcome(lead_id=leads[3].id, message_id=messages[3].id,
                  event=m.OutcomeEvent.BOUNCED, channel="email"),
    ])
    db_session.commit()
    return {"sequence": sequence, "leads": leads, "messages": messages}


class TestCampaignPage:
    def test_per_sequence_rates(self, client, campaign_data):
        row = client.get("/crm/dashboard/campaigns").json()["sequences"][0]
        assert row["sequence_id"] == str(campaign_data["sequence"].id)
        assert row["sent"] == 4          # 3 sent + 1 bounced
        assert row["replied"] == 2
        assert row["booked"] == 1
        assert row["reply_rate"] == pytest.approx(0.5)
        assert row["booking_rate"] == pytest.approx(0.25)

    def test_bounced_messages_count_as_dispatched(self, client, campaign_data):
        """A bounced message WAS sent. Excluding it from the denominator
        flatters the reply rate exactly when deliverability is worst."""
        channels = {row["channel"]: row
                    for row in client.get("/crm/dashboard/campaigns").json()["channels"]}
        assert channels["email"]["sent"] == 4

    def test_channel_split_is_per_channel(self, client, campaign_data):
        channels = {row["channel"]: row
                    for row in client.get("/crm/dashboard/campaigns").json()["channels"]}
        assert channels["email"]["replied"] == 2
        assert channels["whatsapp"]["sent"] == 0
        assert channels["whatsapp"]["reply_rate"] is None

    def test_variant_breakdown_matches_the_ab_engine_shape(self, client,
                                                            campaign_data):
        """Same (variant, event) aggregation ab_testing.py reads, so the
        dashboard and the promotion engine cannot disagree about which
        variant is ahead."""
        variants = {row["variant"]: row
                    for row in client.get("/crm/dashboard/campaigns").json()["variants"]}
        assert variants["A"]["sent"] == 3
        assert variants["A"]["replied"] == 2
        assert variants["B"]["sent"] == 1
        assert variants["B"]["replied"] == 0

    def test_bounce_rate_is_compared_to_the_pause_threshold(self, client,
                                                             campaign_data):
        bounce = client.get("/crm/dashboard/campaigns").json()["bounce"]
        assert bounce["sent"] == 4
        assert bounce["bounced"] == 1
        assert bounce["rate"] == pytest.approx(0.25)
        assert bounce["pause_threshold"] == pytest.approx(0.03)
        assert bounce["over_threshold"] is True

    def test_paused_campaigns_are_surfaced(self, client, db_session,
                                           verified_strategy, campaign_data):
        verified_strategy.campaign_state = "paused_bounce_rate"
        verified_strategy.campaign_pause_reason = "bounce rate 25% exceeded 3%"
        db_session.commit()
        paused = client.get("/crm/dashboard/campaigns").json()["paused_campaigns"]
        assert len(paused) == 1
        assert paused[0]["strategy_id"] == str(verified_strategy.id)

    def test_empty_account_has_no_division_by_zero(self, client):
        body = client.get("/crm/dashboard/campaigns").json()
        assert body["sequences"] == []
        assert body["bounce"]["rate"] == 0.0
        assert body["bounce"]["over_threshold"] is False
        for row in body["channels"]:
            assert row["reply_rate"] is None


class TestActivityFeed:
    def test_feed_is_newest_first(self, client, db_session, verified_strategy):
        lead = _lead(db_session, verified_strategy,
                     status=m.LeadStatus.VERIFIED, index=1)
        db_session.commit()
        client.post(f"/crm/leads/{lead.id}/notes", json={"body": "first"})
        client.post(f"/crm/leads/{lead.id}/notes", json={"body": "second"})

        items = client.get("/crm/dashboard/activity").json()["items"]
        assert [i["to_value"] for i in items] == ["second", "first"]

    def test_feed_carries_lead_context(self, client, db_session,
                                       verified_strategy):
        """The feed is read across leads, so each row must say who it is about
        without the client having to fetch every lead it mentions."""
        lead = _lead(db_session, verified_strategy,
                     status=m.LeadStatus.VERIFIED, index=1,
                     company="Northwind")
        db_session.commit()
        client.post(f"/crm/leads/{lead.id}/notes", json={"body": "hi"})
        item = client.get("/crm/dashboard/activity").json()["items"][0]
        assert item["lead"]["company"] == "Northwind"

    def test_machine_activity_has_no_actor(self, client, db_session,
                                           verified_strategy):
        """NULL actor is how the feed distinguishes "you moved this" from
        "the pipeline moved this"."""
        lead = _lead(db_session, verified_strategy,
                     status=m.LeadStatus.VERIFIED, index=1)
        db_session.flush()
        crm_service.log_activity(db_session, lead,
                                 m.CrmActivityKind.STATUS_CHANGED,
                                 actor=None, from_value="sourced",
                                 to_value="verified")
        db_session.commit()
        item = client.get("/crm/dashboard/activity").json()["items"][0]
        assert item["actor_user_id"] is None

    def test_filter_by_kind(self, client, db_session, verified_strategy):
        lead = _lead(db_session, verified_strategy,
                     status=m.LeadStatus.VERIFIED, index=1)
        db_session.commit()
        client.post(f"/crm/leads/{lead.id}/notes", json={"body": "note"})
        client.patch(f"/crm/leads/{lead.id}", json={"status": "flagged"})

        items = client.get(
            "/crm/dashboard/activity?kind=status_changed").json()["items"]
        assert [i["kind"] for i in items] == ["status_changed"]

    def test_keyset_pagination_is_stable_against_new_rows(self, client,
                                                          db_session,
                                                          verified_strategy):
        """OFFSET would re-show page 1's rows on page 2 every time an event
        arrives at the head -- which, on a live feed, is constantly."""
        lead = _lead(db_session, verified_strategy,
                     status=m.LeadStatus.VERIFIED, index=1)
        db_session.commit()
        for n in range(5):
            client.post(f"/crm/leads/{lead.id}/notes", json={"body": f"n{n}"})

        first = client.get("/crm/dashboard/activity?limit=2").json()
        assert first["has_more"] is True

        # A new event lands at the head between the two page requests.
        client.post(f"/crm/leads/{lead.id}/notes", json={"body": "interloper"})

        second = client.get(
            f"/crm/dashboard/activity?limit=2&before={first['next_before']}"
        ).json()
        first_ids = {i["id"] for i in first["items"]}
        second_ids = {i["id"] for i in second["items"]}
        assert not (first_ids & second_ids), "page 2 repeated a row from page 1"

    def test_per_lead_activity_is_scoped_to_that_lead(self, client, db_session,
                                                       verified_strategy):
        first = _lead(db_session, verified_strategy,
                      status=m.LeadStatus.VERIFIED, index=1)
        second = _lead(db_session, verified_strategy,
                       status=m.LeadStatus.VERIFIED, index=2)
        db_session.commit()
        client.post(f"/crm/leads/{first.id}/notes", json={"body": "mine"})
        client.post(f"/crm/leads/{second.id}/notes", json={"body": "theirs"})

        items = client.get(f"/crm/leads/{first.id}/activity").json()["items"]
        assert [i["to_value"] for i in items] == ["mine"]


class TestAggregationIsDoneInSql:
    """Rule 7 of the brief -- every number comes from a real aggregation
    query -- has a corollary worth pinning: the queries must not degrade into
    "load everything, count in Python", which passes every correctness test
    above and falls over at the scale this product is sold at."""

    def test_dashboards_do_not_scale_query_count_with_row_count(
        self, client, db_session, verified_strategy
    ):
        from sqlalchemy import event as sa_event

        for index in range(120):
            _lead(db_session, verified_strategy,
                  status=m.LeadStatus.VERIFIED, index=index)
        db_session.commit()

        counter = {"n": 0}

        def _count(*_args, **_kwargs):
            counter["n"] += 1

        engine = db_session.get_bind()
        sa_event.listen(engine, "before_cursor_execute", _count)
        try:
            client.get("/crm/dashboard/pipeline")
            with_120 = counter["n"]
        finally:
            sa_event.remove(engine, "before_cursor_execute", _count)

        # A handful of GROUP BY queries, not one per lead. The exact number is
        # not the point -- the order of magnitude is.
        assert with_120 < 25, (
            f"pipeline dashboard issued {with_120} queries for 120 leads; "
            "an aggregation has become a per-row loop"
        )

    def test_grid_page_is_a_bounded_number_of_queries(self, client, db_session,
                                                       verified_strategy):
        """The EAV custom-field design costs ONE extra query per page. If it
        ever becomes one per row, that trade-off is no longer the one that
        was accepted."""
        from sqlalchemy import event as sa_event

        client.post("/crm/fields", json={"key": "k", "label": "K"})
        leads = [
            _lead(db_session, verified_strategy, status=m.LeadStatus.VERIFIED,
                  index=index)
            for index in range(50)
        ]
        db_session.commit()
        for lead in leads[:20]:
            client.patch(f"/crm/leads/{lead.id}", json={"custom": {"k": "v"}})

        counter = {"n": 0}

        def _count(*_args, **_kwargs):
            counter["n"] += 1

        engine = db_session.get_bind()
        sa_event.listen(engine, "before_cursor_execute", _count)
        try:
            body = client.post("/crm/grid", json={"limit": 50}).json()
        finally:
            sa_event.remove(engine, "before_cursor_execute", _count)

        assert len(body["items"]) == 50
        assert counter["n"] < 15, (
            f"grid issued {counter['n']} queries for 50 rows; the per-page "
            "batch fetch has regressed into N+1"
        )

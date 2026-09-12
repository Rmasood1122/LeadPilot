"""Feature 5 — client ROI dashboard and the shareable proof card.

Pins each of the six metrics, the flow-vs-stock distinction that governs which
of them the date range bounds, the nightly sweep's idempotency, and both
endpoints -- including that the card is a real 1200x628 PNG.
"""

import io
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.db import models as m
from app.services import roi_calculator, roi_card
from app.workers import roi_tasks

TODAY = datetime.now(timezone.utc).date()
YESTERDAY = TODAY - timedelta(days=1)
MONTH_AGO = TODAY - timedelta(days=29)


@pytest.fixture()
def campaign(db_session, product_with_strategy):
    _product, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
    strategy.status = m.StrategyStatus.EXECUTING
    sequence = m.Sequence(strategy_id=strategy.id, channel=m.ChannelType.EMAIL,
                          name="cold", status=m.SequenceStatus.ACTIVE)
    db_session.add(sequence)
    db_session.commit()
    return strategy, sequence


def _lead(db_session, strategy, *, status=m.LeadStatus.CONTACTED, value=None):
    lead = m.Lead(strategy_id=strategy.id, source="manual",
                  external_id=str(uuid.uuid4()),
                  email=f"{uuid.uuid4().hex[:10]}@example.com",
                  full_name="Sara Khan", company="Acme", status=status,
                  estimated_deal_value=value)
    db_session.add(lead)
    db_session.commit()
    return lead


def _sent(db_session, sequence, lead, *, when=None, step_no=1):
    when = when or datetime.now(timezone.utc)
    db_session.add(m.Message(sequence_id=sequence.id, lead_id=lead.id,
                             channel=m.ChannelType.EMAIL, step_no=step_no,
                             template="t", body="b",
                             status=m.MessageStatus.SENT, sent_at=when))
    db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.SENT,
                             channel="email", ts=when))
    db_session.commit()


class TestMetrics:
    def test_an_empty_campaign_is_all_zeros(self, db_session, campaign):
        strategy, _sequence = campaign
        metrics = roi_calculator.compute_roi_snapshot(db_session, strategy.id,
                                                      MONTH_AGO, TODAY)
        assert metrics["meetings_booked"] == 0
        assert metrics["messages_sent"] == 0
        assert metrics["reply_rate"] == 0.0
        assert metrics["pipeline_value"] == Decimal("0.00")
        assert metrics["revenue_attributed"] == Decimal("0.00")
        assert metrics["time_saved_hours"] == 0.0
        assert "error" not in metrics

    def test_messages_sent_counts_only_sent_messages_in_the_window(self, db_session,
                                                                   campaign):
        strategy, sequence = campaign
        lead = _lead(db_session, strategy)
        _sent(db_session, sequence, lead)
        _sent(db_session, sequence, lead)
        # Outside the window, and one that never left.
        _sent(db_session, sequence, lead,
              when=datetime.now(timezone.utc) - timedelta(days=90))
        db_session.add(m.Message(sequence_id=sequence.id, lead_id=lead.id,
                                 channel=m.ChannelType.EMAIL, step_no=9,
                                 template="t", status=m.MessageStatus.SCHEDULED))
        db_session.commit()

        metrics = roi_calculator.compute_roi_snapshot(db_session, strategy.id,
                                                      MONTH_AGO, TODAY)
        assert metrics["messages_sent"] == 2

    def test_reply_rate_is_unique_people_not_unique_messages(self, db_session,
                                                             campaign):
        strategy, sequence = campaign
        leads = [_lead(db_session, strategy) for _ in range(4)]
        for lead in leads:
            _sent(db_session, sequence, lead)
        # One lead replies twice; another replies once. 2 of 4 people = 50%.
        now = datetime.now(timezone.utc)
        for lead, count in ((leads[0], 2), (leads[1], 1)):
            for _ in range(count):
                db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.REPLIED,
                                         channel="email", ts=now))
        db_session.commit()

        metrics = roi_calculator.compute_roi_snapshot(db_session, strategy.id,
                                                      MONTH_AGO, TODAY)
        assert metrics["leads_contacted"] == 4
        assert metrics["leads_replied"] == 2
        assert metrics["reply_rate"] == 50.0

    def test_meetings_need_both_step_three_and_the_booked_status(self, db_session,
                                                                 campaign):
        strategy, sequence = campaign
        now = datetime.now(timezone.utc)

        def _booked(step, status):
            lead = _lead(db_session, strategy, status=status)
            db_session.add(m.SequenceEnrollment(sequence_id=sequence.id,
                                                lead_id=lead.id, current_step=step))
            db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.BOOKED,
                                     channel="email", ts=now))
            db_session.commit()
            return lead

        _booked(3, m.LeadStatus.MEETING_BOOKED)     # counts
        _booked(4, m.LeadStatus.MEETING_BOOKED)     # counts
        _booked(2, m.LeadStatus.MEETING_BOOKED)     # too early in the sequence
        _booked(3, m.LeadStatus.REPLIED)            # never actually booked

        metrics = roi_calculator.compute_roi_snapshot(db_session, strategy.id,
                                                      MONTH_AGO, TODAY)
        assert metrics["meetings_booked"] == 2

    def test_a_meeting_outside_the_window_is_not_counted(self, db_session, campaign):
        strategy, sequence = campaign
        lead = _lead(db_session, strategy, status=m.LeadStatus.MEETING_BOOKED)
        db_session.add(m.SequenceEnrollment(sequence_id=sequence.id, lead_id=lead.id,
                                            current_step=3))
        db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.BOOKED,
                                 channel="email",
                                 ts=datetime.now(timezone.utc) - timedelta(days=120)))
        db_session.commit()

        metrics = roi_calculator.compute_roi_snapshot(db_session, strategy.id,
                                                      MONTH_AGO, TODAY)
        assert metrics["meetings_booked"] == 0

    def test_pipeline_value_sums_the_three_live_statuses(self, db_session, campaign):
        strategy, _sequence = campaign
        _lead(db_session, strategy, status=m.LeadStatus.MEETING_BOOKED,
              value=Decimal("1000.00"))
        _lead(db_session, strategy, status=m.LeadStatus.PROPOSAL_SENT,
              value=Decimal("2500.50"))
        _lead(db_session, strategy, status=m.LeadStatus.CLOSED_WON,
              value=Decimal("4000.00"))
        _lead(db_session, strategy, status=m.LeadStatus.CLOSED_LOST,
              value=Decimal("9999.00"))     # not pipeline
        _lead(db_session, strategy, status=m.LeadStatus.MEETING_BOOKED, value=None)

        metrics = roi_calculator.compute_roi_snapshot(db_session, strategy.id,
                                                      MONTH_AGO, TODAY)
        assert metrics["pipeline_value"] == Decimal("7500.50")

    def test_a_null_deal_value_is_skipped_not_read_as_zero(self, db_session, campaign):
        """Nobody priced this lead. That is not a deal worth nothing, and the
        difference is visible the moment an average is taken downstream."""
        strategy, _sequence = campaign
        _lead(db_session, strategy, status=m.LeadStatus.CLOSED_WON, value=None)
        metrics = roi_calculator.compute_roi_snapshot(db_session, strategy.id,
                                                      MONTH_AGO, TODAY)
        assert metrics["revenue_attributed"] == Decimal("0.00")

    def test_money_stays_decimal_end_to_end(self, db_session, campaign):
        strategy, _sequence = campaign
        _lead(db_session, strategy, status=m.LeadStatus.MEETING_BOOKED,
              value=Decimal("0.10"))
        _lead(db_session, strategy, status=m.LeadStatus.MEETING_BOOKED,
              value=Decimal("0.20"))
        metrics = roi_calculator.compute_roi_snapshot(db_session, strategy.id,
                                                      MONTH_AGO, TODAY)
        assert isinstance(metrics["pipeline_value"], Decimal)
        assert metrics["pipeline_value"] == Decimal("0.30")   # not 0.30000000000000004

    def test_revenue_attributed_counts_only_closed_won(self, db_session, campaign):
        strategy, _sequence = campaign
        _lead(db_session, strategy, status=m.LeadStatus.CLOSED_WON,
              value=Decimal("4000.00"))
        _lead(db_session, strategy, status=m.LeadStatus.PROPOSAL_SENT,
              value=Decimal("8000.00"))
        metrics = roi_calculator.compute_roi_snapshot(db_session, strategy.id,
                                                      MONTH_AGO, TODAY)
        assert metrics["revenue_attributed"] == Decimal("4000.00")

    def test_time_saved_is_messages_plus_meetings(self, db_session, campaign):
        strategy, sequence = campaign
        for _ in range(8):
            _sent(db_session, sequence, _lead(db_session, strategy))
        lead = _lead(db_session, strategy, status=m.LeadStatus.MEETING_BOOKED)
        db_session.add(m.SequenceEnrollment(sequence_id=sequence.id, lead_id=lead.id,
                                            current_step=3))
        db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.BOOKED,
                                 channel="email", ts=datetime.now(timezone.utc)))
        db_session.commit()

        metrics = roi_calculator.compute_roi_snapshot(db_session, strategy.id,
                                                      MONTH_AGO, TODAY)
        # 8 * 0.25 + 1 * 1.5
        assert metrics["messages_sent"] == 8
        assert metrics["meetings_booked"] == 1
        assert metrics["time_saved_hours"] == 3.5


class TestNeverRaises:
    def test_unknown_strategy_is_zeros_not_an_exception(self, db_session):
        metrics = roi_calculator.compute_roi_snapshot(db_session, uuid.uuid4(),
                                                       MONTH_AGO, TODAY)
        assert metrics["messages_sent"] == 0 and "error" not in metrics

    def test_a_garbage_id_degrades_with_an_error_key(self, db_session):
        metrics = roi_calculator.compute_roi_snapshot(db_session, "nope",
                                                       MONTH_AGO, TODAY)
        assert "error" in metrics

    def test_an_inverted_range_degrades_rather_than_raising(self, db_session,
                                                            campaign):
        strategy, _sequence = campaign
        metrics = roi_calculator.compute_roi_snapshot(db_session, strategy.id,
                                                       TODAY, MONTH_AGO)
        assert "error" in metrics


class TestSnapshots:
    def test_upsert_writes_one_row_per_day(self, db_session, campaign):
        strategy, _sequence = campaign
        first = roi_calculator.upsert_daily_snapshot(db_session, strategy.id, TODAY)
        second = roi_calculator.upsert_daily_snapshot(db_session, strategy.id, TODAY)

        assert first.id == second.id
        assert db_session.query(m.ROISnapshot).count() == 1

    def test_a_second_day_is_a_second_row(self, db_session, campaign):
        strategy, _sequence = campaign
        roi_calculator.upsert_daily_snapshot(db_session, strategy.id, YESTERDAY)
        roi_calculator.upsert_daily_snapshot(db_session, strategy.id, TODAY)
        assert db_session.query(m.ROISnapshot).count() == 2

    def test_a_failed_computation_writes_nothing(self, db_session, campaign):
        assert roi_calculator.upsert_daily_snapshot(db_session, "nope", TODAY) is None
        assert db_session.query(m.ROISnapshot).count() == 0

    def test_the_sweep_covers_only_scorable_strategies(self, db_session, campaign,
                                                       product_with_strategy):
        product_with_strategy(m.FlowType.WITH_CLIENTS)   # PENDING, out of scope
        result = roi_tasks.refresh_all_roi_snapshots_impl(db_session, TODAY)
        assert result["total"] == 1 and result["written"] == 1

    def test_the_sweep_is_idempotent(self, db_session, campaign):
        roi_tasks.refresh_all_roi_snapshots_impl(db_session, TODAY)
        roi_tasks.refresh_all_roi_snapshots_impl(db_session, TODAY)
        assert db_session.query(m.ROISnapshot).count() == 1


class TestCard:
    METRICS = {"meetings_booked": 12, "pipeline_value": Decimal("84000.00"),
               "messages_sent": 1432, "reply_rate": 8.42,
               "time_saved_hours": 376.0, "revenue_attributed": Decimal("21500.00")}

    def test_formats_money_and_rates_for_display(self):
        context = roi_card.card_context(self.METRICS, "Fire Protection",
                                        MONTH_AGO, TODAY)
        assert context["pipeline_value"] == "$84.0k"
        assert context["revenue_attributed"] == "$21.5k"
        assert context["messages_sent"] == "1,432"
        assert context["reply_rate"] == "8.4%"
        assert context["meetings_booked"] == "12"
        assert context["day_count"] == 30

    @pytest.mark.parametrize("amount,expected", [
        (Decimal("0"), "$0"), (Decimal("840"), "$840"),
        (Decimal("12400"), "$12.4k"), (Decimal("1200000"), "$1.2M"),
    ])
    def test_money_scales(self, amount, expected):
        context = roi_card.card_context({"pipeline_value": amount}, "x",
                                        MONTH_AGO, TODAY)
        assert context["pipeline_value"] == expected

    def test_the_html_template_makes_no_network_calls(self):
        """A stylesheet or webfont fetched at render time would be a network
        call on a request path and a silent failure when it is blocked."""
        html = roi_card.render_card_html(
            roi_card.card_context(self.METRICS, "Fire Protection", MONTH_AGO, TODAY))
        for forbidden in ("http://", "https://", "//fonts.", "@import", "<img"):
            assert forbidden not in html, forbidden

    def test_the_campaign_name_is_escaped(self):
        html = roi_card.render_card_html(
            roi_card.card_context(self.METRICS, "<script>alert(1)</script>",
                                  MONTH_AGO, TODAY))
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_renders_a_real_png_at_the_linkedin_preview_size(self):
        from PIL import Image

        png = roi_card.render_card_png(self.METRICS, "Fire Protection",
                                       MONTH_AGO, TODAY)

        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        image = Image.open(io.BytesIO(png))
        assert image.size == (roi_card.CARD_WIDTH, roi_card.CARD_HEIGHT) == (1200, 628)
        assert roi_card.last_renderer() in ("weasyprint", "pillow")

    def test_renders_even_when_every_metric_is_missing(self):
        png = roi_card.render_card_png({}, "", MONTH_AGO, TODAY)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"


class TestEndpoints:
    def test_roi_returns_all_six_metrics(self, client, db_session, campaign):
        strategy, sequence = campaign
        _sent(db_session, sequence, _lead(db_session, strategy))

        response = client.get(f"/strategies/{strategy.id}/roi")

        assert response.status_code == 200
        body = response.json()
        for key in ("meetings_booked", "pipeline_value", "messages_sent",
                    "reply_rate", "time_saved_hours", "revenue_attributed"):
            assert key in body
        assert body["messages_sent"] == 1
        assert body["pipeline_value_is_as_of_today"] is True

    def test_roi_defaults_to_the_last_thirty_days(self, client, campaign):
        strategy, _sequence = campaign
        body = client.get(f"/strategies/{strategy.id}/roi").json()
        assert body["date_to"] == TODAY.isoformat()
        assert body["date_from"] == (TODAY - timedelta(days=29)).isoformat()

    def test_roi_honours_an_explicit_range(self, client, campaign):
        strategy, _sequence = campaign
        body = client.get(f"/strategies/{strategy.id}/roi",
                          params={"date_from": "2026-01-01",
                                  "date_to": "2026-01-31"}).json()
        assert body["date_from"] == "2026-01-01" and body["date_to"] == "2026-01-31"

    def test_roi_rejects_an_inverted_range(self, client, campaign):
        strategy, _sequence = campaign
        response = client.get(f"/strategies/{strategy.id}/roi",
                              params={"date_from": "2026-02-01",
                                      "date_to": "2026-01-01"})
        assert response.status_code == 422

    def test_card_returns_a_png(self, client, campaign):
        from PIL import Image

        strategy, _sequence = campaign
        response = client.get(f"/strategies/{strategy.id}/roi/card")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert Image.open(io.BytesIO(response.content)).size == (1200, 628)

    def test_card_is_not_publicly_cacheable(self, client, campaign):
        strategy, _sequence = campaign
        cache_control = client.get(
            f"/strategies/{strategy.id}/roi/card").headers["cache-control"]
        assert "private" in cache_control and "public" not in cache_control

    def test_both_routes_404_for_another_users_strategy(self, client, db_session):
        other = m.User(email="stranger5@example.com", plan=m.PlanTier.PRO)
        db_session.add(other)
        db_session.flush()
        product = m.Product(user_id=other.id, name="theirs", description="x",
                            type=m.ProductType.SKILL)
        db_session.add(product)
        db_session.flush()
        strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.WITH_CLIENTS)
        db_session.add(strategy)
        db_session.commit()

        assert client.get(f"/strategies/{strategy.id}/roi").status_code == 404
        assert client.get(f"/strategies/{strategy.id}/roi/card").status_code == 404

    def test_both_routes_appear_in_the_openapi_schema(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        assert "/strategies/{strategy_id}/roi" in paths
        assert "/strategies/{strategy_id}/roi/card" in paths

"""Feature 6 — anonymised benchmarks.

What must hold:
  * a bucket with fewer accounts than the threshold is NEVER written, and the
    threshold cannot be configured below the hard floor;
  * the unit is the account: an account below the minimum sends does not
    count, and one huge account is one data point, not the benchmark;
  * only rounded percentiles are stored -- no user, strategy or raw totals;
  * the window and suspended accounts are respected; a re-run replaces the
    snapshot rather than adding to it;
  * a user's own numbers use the same definitions and only their own rows;
    another account's campaign is a 404.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.services import benchmarks, system_settings

UTC = timezone.utc


def _fill(db, strategy, *, sent, replies=0, booked=0, bounced=0,
          channel=m.ChannelType.EMAIL, days_ago=5):
    seq = m.Sequence(strategy_id=strategy.id, channel=channel, name="S",
                     status=m.SequenceStatus.ACTIVE)
    lead = m.Lead(strategy_id=strategy.id, source="manual",
                  external_id=f"b-{strategy.id.hex[:8]}-{channel.value}",
                  email=f"{strategy.id.hex[:8]}-{channel.value}@bench.test",
                  status=m.LeadStatus.CONTACTED)
    db.add_all([seq, lead])
    db.flush()
    when = datetime.now(UTC) - timedelta(days=days_ago)
    for i in range(sent):
        status = m.MessageStatus.BOUNCED if i < bounced else m.MessageStatus.SENT
        db.add(m.Message(sequence_id=seq.id, lead_id=lead.id, channel=channel, step_no=1,
                         template="x", status=status, sent_at=when))
    for event, count in ((m.OutcomeEvent.REPLIED, replies), (m.OutcomeEvent.BOOKED, booked),
                         (m.OutcomeEvent.BOUNCED, bounced)):
        for _ in range(count):
            db.add(m.Outcome(lead_id=lead.id, event=event, channel=channel.value, ts=when))
    db.commit()


def _account(db, n, *, industry="saas", suspended=False, **fill):
    user = m.User(email=f"acct{n}@bench.test", email_verified=True, is_suspended=suspended)
    db.add(user)
    db.flush()
    product = m.Product(user_id=user.id, name=f"P{n}", description="d",
                        type=m.ProductType.PRODUCT)
    db.add(product)
    db.flush()
    strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.NO_CLIENTS,
                          status=m.StrategyStatus.VERIFIED,
                          pattern_inputs_json={"icp": {"industries": [industry]}})
    db.add(strategy)
    db.commit()
    _fill(db, strategy, **{"sent": 40, "replies": 4, **fill})
    return user, strategy


def _rows(db, industry="saas", channel="email"):
    return {r.metric: r for r in db.query(m.BenchmarkBucket).filter_by(
        industry=industry, channel=channel)}


# --------------------------------------------------------------------------
# Publishing thresholds
# --------------------------------------------------------------------------


class TestThresholds:
    def test_a_bucket_below_the_minimum_is_never_written(self, db_session):
        for n in range(9):
            _account(db_session, n)
        result = benchmarks.compute_snapshot(db_session)
        assert result["published"] == 0 and result["suppressed"] >= 1
        assert db_session.query(m.BenchmarkBucket).count() == 0

    def test_ten_accounts_publish_the_industry_and_the_all_industries_bucket(self, db_session):
        for n in range(10):
            _account(db_session, n, replies=n + 1)        # 2.5% .. 25%
        benchmarks.compute_snapshot(db_session)
        saas = _rows(db_session)
        assert set(saas) == {"reply_rate", "meeting_rate", "bounce_rate"}
        assert saas["reply_rate"].account_count == 10
        assert set(_rows(db_session, industry="*")) == set(saas)

    def test_the_setting_cannot_lower_the_hard_floor(self, db_session):
        system_settings.set(db_session, "benchmark_min_accounts", 1)
        for n in range(benchmarks.HARD_MIN_ACCOUNTS - 1):
            _account(db_session, n)
        benchmarks.compute_snapshot(db_session)
        assert db_session.query(m.BenchmarkBucket).count() == 0

        _account(db_session, 99)
        benchmarks.compute_snapshot(db_session)
        assert _rows(db_session)["reply_rate"].account_count == benchmarks.HARD_MIN_ACCOUNTS

    def test_an_account_below_the_minimum_sends_does_not_count(self, db_session):
        for n in range(9):
            _account(db_session, n)
        _account(db_session, 50, sent=5, replies=5)      # 100% on five sends
        benchmarks.compute_snapshot(db_session)
        assert db_session.query(m.BenchmarkBucket).count() == 0

    def test_suspended_accounts_are_excluded(self, db_session):
        for n in range(9):
            _account(db_session, n)
        _account(db_session, 60, suspended=True)
        benchmarks.compute_snapshot(db_session)
        assert db_session.query(m.BenchmarkBucket).count() == 0

    def test_activity_outside_the_window_is_ignored(self, db_session):
        for n in range(10):
            _account(db_session, n, days_ago=200)
        benchmarks.compute_snapshot(db_session)
        assert db_session.query(m.BenchmarkBucket).count() == 0


# --------------------------------------------------------------------------
# What is stored
# --------------------------------------------------------------------------


class TestSnapshot:
    def test_one_huge_account_is_one_data_point(self, db_session):
        for n in range(9):
            _account(db_session, n, sent=40, replies=4)            # 10%
        _account(db_session, 70, sent=400, replies=360)             # 90%, 10x volume
        benchmarks.compute_snapshot(db_session)
        # Pooled, the "benchmark" would be ~62%. Across accounts the median is 10%.
        assert _rows(db_session)["reply_rate"].p50 == 0.1

    def test_percentiles_are_rounded_to_half_a_point(self, db_session):
        for n in range(10):
            _account(db_session, n, sent=81, replies=10)           # 12.345...%
        benchmarks.compute_snapshot(db_session)
        assert _rows(db_session)["reply_rate"].p50 == 0.125

    def test_the_rates_follow_the_dashboard_definitions(self, db_session):
        for n in range(10):
            _account(db_session, n, sent=50, replies=5, booked=2, bounced=1)
        benchmarks.compute_snapshot(db_session)
        rows = _rows(db_session)
        assert (rows["reply_rate"].p50, rows["meeting_rate"].p50, rows["bounce_rate"].p50) \
            == (0.1, 0.04, 0.02)

    def test_a_rerun_replaces_the_snapshot(self, db_session):
        for n in range(10):
            _account(db_session, n)
        benchmarks.compute_snapshot(db_session)
        first = db_session.query(m.BenchmarkBucket).count()
        benchmarks.compute_snapshot(db_session)
        assert db_session.query(m.BenchmarkBucket).count() == first == 6

    def test_no_identifying_columns_are_stored(self):
        columns = {c.name for c in m.BenchmarkBucket.__table__.columns}
        assert not {"user_id", "strategy_id", "lead_id", "product_id"} & columns

    @pytest.mark.parametrize("industries,expected", [
        (["SaaS "], "saas"), (["saas", "fintech"], "multiple"), ([], "unspecified"),
        (None, "unspecified"),
    ])
    def test_industry_bucketing(self, industries, expected):
        strategy = m.Strategy(pattern_inputs_json={"icp": {"industries": industries}})
        assert benchmarks.industry_of(strategy) == expected


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


class TestApi:
    def test_your_numbers_sit_next_to_the_published_bucket(self, client, db_session,
                                                           verified_strategy):
        verified_strategy.pattern_inputs_json = {"icp": {"industries": ["saas"]}}
        db_session.commit()
        _fill(db_session, verified_strategy, sent=40, replies=10)
        for n in range(10):
            _account(db_session, n)
        benchmarks.compute_snapshot(db_session)

        body = client.get(f"/benchmarks?strategy_id={verified_strategy.id}").json()
        email = next(c for c in body["channels"] if c["channel"] == "email")
        assert email["yours"]["dispatched"] == 40
        assert email["yours"]["reply_rate"] == 0.25 and email["yours"]["enough_data"]
        assert email["industry"]["metrics"]["reply_rate"]["p50"] == 0.1
        assert email["industry"]["accounts"] == "10+"
        assert "Not an industry statistic" in body["note"]

    def test_your_numbers_never_include_other_accounts(self, client, db_session,
                                                       verified_strategy):
        for n in range(10):
            _account(db_session, n)
        body = client.get("/benchmarks").json()
        assert all(c["yours"]["dispatched"] == 0 for c in body["channels"])

    def test_a_suppressed_bucket_is_simply_absent(self, client, db_session, verified_strategy):
        verified_strategy.pattern_inputs_json = {"icp": {"industries": ["niche"]}}
        db_session.commit()
        _fill(db_session, verified_strategy, sent=40, replies=4)
        benchmarks.compute_snapshot(db_session)
        body = client.get(f"/benchmarks?strategy_id={verified_strategy.id}").json()
        email = next(c for c in body["channels"] if c["channel"] == "email")
        assert email["industry"] is None and email["all_industries"] is None

    def test_another_accounts_campaign_is_404(self, client, db_session):
        _, theirs = _account(db_session, 1)
        assert client.get(f"/benchmarks?strategy_id={theirs.id}").status_code == 404


def test_the_nightly_job_runs_on_the_learning_queue():
    from app.workers.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["compute-benchmarks"]
    assert entry["task"] == "app.workers.benchmark_tasks.compute_benchmarks"
    assert celery_app.amqp.router.route({}, entry["task"])["queue"].name == "learning"

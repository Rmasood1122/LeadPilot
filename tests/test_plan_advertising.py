"""Product defects #18 and #20: what the plans advertise must be what the code
enforces.

#18 Decisions (docs/program/fixes/product-defects.md):
  * multi_variate   ENFORCED. GET /strategies/{id}/mv-results was gated by
                    ab_testing, so Starter and Pay-per-meeting (multi_variate
                    False) got it anyway. It now needs multi_variate.
  * analytics_history_days  ENFORCED on the analytics time series
                    (GET /strategies/{id}/analytics `series`): outcomes older
                    than the plan's window are left out; -1 = all history.
  * api_rate_limit_multiplier  REMOVED. Nothing ever read it; scaling the
                    rate limits by plan would loosen the cost-protecting
                    limits (2 strategies/hour) with no stated intent. It is no
                    longer in PLANS or in the price list's entitlements.
  * "Unlimited" sequence steps  CORRECTED. The API caps a sequence at 20 steps
                    (SequenceCreate / StepIn), so plans that said -1 now say 20.
#20 PLANS["starter"]["upgrade_to"] said "pro" (no longer sold) while the 402
    upgrade path said "growth"; both now come from one table.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.api.sequences import SequenceCreate, StepIn
from app.core import billing_catalog
from app.core.plans import _PLAN_UPGRADE_PATH, PLANS, SEQUENCE_STEP_CAP
from app.db import models as m


class TestDefinitions:
    def test_no_plan_advertises_more_sequence_steps_than_the_api_accepts(self):
        assert SEQUENCE_STEP_CAP == 20
        assert SequenceCreate.model_fields["steps"].metadata[-1].max_length == SEQUENCE_STEP_CAP
        for name, plan in PLANS.items():
            assert 1 <= plan["max_sequence_steps"] <= SEQUENCE_STEP_CAP, name
        le = [c.le for c in StepIn.model_fields["step_no"].metadata if hasattr(c, "le")]
        assert le == [SEQUENCE_STEP_CAP]

    def test_unenforced_rate_limit_multiplier_is_not_advertised(self):
        for name, plan in PLANS.items():
            assert "api_rate_limit_multiplier" not in plan, name
        for tier in billing_catalog.catalog()["monthly"]["tiers"]:
            assert "api_rate_limit_multiplier" not in tier["limits"]

    def test_upgrade_to_matches_the_upgrade_path(self):
        for name, plan in PLANS.items():
            assert plan["upgrade_to"] == _PLAN_UPGRADE_PATH[name], name
        assert PLANS["starter"]["upgrade_to"] == "growth"


def _set_plan(db, user, plan):
    user.plan = plan
    db.commit()


class TestMultiVariateGate:
    @pytest.mark.parametrize("plan", [m.PlanTier.STARTER, m.PlanTier.PAY_PER_MEETING])
    def test_ab_testing_alone_does_not_unlock_multi_variate(self, client, db_session,
                                                           test_user, verified_strategy, plan):
        _set_plan(db_session, test_user, plan)
        r = client.get(f"/strategies/{verified_strategy.id}/mv-results")
        assert r.status_code == 402
        assert r.json()["detail"]["limit"] == "multi_variate"

    def test_growth_passes_the_gate(self, client, db_session, test_user, verified_strategy):
        _set_plan(db_session, test_user, m.PlanTier.GROWTH)
        r = client.get(f"/strategies/{verified_strategy.id}/mv-results")
        assert r.status_code != 402


class TestAnalyticsHistory:
    def _outcome(self, db, lead, days_ago):
        db.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.SENT, channel="email",
                         ts=datetime.now(timezone.utc) - timedelta(days=days_ago)))

    @pytest.fixture()
    def history(self, db_session, verified_strategy):
        lead = m.Lead(strategy_id=verified_strategy.id, source="apollo", external_id="H",
                      full_name="H", email="h@h.co")
        db_session.add(lead)
        db_session.flush()
        for days in (5, 60, 400):
            self._outcome(db_session, lead, days)
        db_session.commit()
        return verified_strategy

    @pytest.mark.parametrize("plan,days,expected", [
        (m.PlanTier.FREE, 30, 1),
        (m.PlanTier.STARTER, 90, 2),
        (m.PlanTier.GROWTH, 365, 2),
        (m.PlanTier.SCALE, None, 3),
    ])
    def test_series_is_limited_to_the_plan_window(self, client, db_session, test_user,
                                                  history, plan, days, expected):
        _set_plan(db_session, test_user, plan)
        body = client.get(f"/strategies/{history.id}/analytics?granularity=month").json()
        assert body["history_days"] == days
        assert sum(row["count"] for row in body["series"]) == expected

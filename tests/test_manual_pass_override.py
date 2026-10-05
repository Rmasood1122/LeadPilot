"""Human sign-off on 1-3 failed verification passes (needs_human_review).

Seen live on 2026-10-05: a strategy had 9 of 10 passes green and one failed pass
(factual accuracy) and could not be used: needs_human_review was a dead end.
POST /strategies/{id}/override-passes lets the owner accept it -- as a recorded
HUMAN decision, never as a judge PASS, with hard limits:
  - only needs_human_review; 1-3 failed passes; exactly those passes named;
  - a written reason and an explicit acknowledgement;
  - the Legal & compliance pass can never be overridden;
  - the original FAIL rows stay; the override is audited.
Offline.
"""

import pytest
from sqlalchemy import select

from app.db import models as m
from app.db.models import StrategyStatus
from app.services import security_audit
from app.verification.passes import build_passes

REASON = "Checked the competitor names and prices by hand against vendor sites."


def _log(failed: dict[int, int], flow=m.FlowType.WITH_CLIENTS):
    """Pass log: every pass PASS on attempt 1, except `failed` {pass_no: attempts}
    which fail every attempt."""
    rows = []
    for spec in build_passes(flow):
        n = failed.get(spec.pass_no)
        if n is None:
            rows.append({"pass_no": spec.pass_no, "key": spec.key, "name": spec.name,
                         "attempt": 1, "result": "PASS", "fix_description": None,
                         "fix_applied": False})
        else:
            for a in range(1, n + 1):
                rows.append({"pass_no": spec.pass_no, "key": spec.key, "name": spec.name,
                             "attempt": a, "result": "FAIL",
                             "fix_description": f"claim {spec.pass_no} unverified",
                             "fix_applied": a < n})
    return rows


def _strategy(db, product_with_strategy, failed, status=StrategyStatus.NEEDS_HUMAN_REVIEW):
    _, s = product_with_strategy(m.FlowType.WITH_CLIENTS)
    s.status = status
    s.verified_passes_json = _log(failed)
    db.commit()
    return s


def _post(client, s, **over):
    body = {"pass_nos": [1], "reason": REASON, "acknowledge": True, **over}
    return client.post(f"/strategies/{s.id}/override-passes", json=body)


def _events(db, action):
    return db.execute(select(m.SecurityAuditEvent)
                      .where(m.SecurityAuditEvent.action == action)).scalars().all()


class TestHappyPath:
    def test_one_failed_pass_can_be_signed_off(self, client, db_session,
                                               product_with_strategy):
        s = _strategy(db_session, product_with_strategy, {1: 2})
        resp = _post(client, s)
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "verified"
        db_session.refresh(s)
        assert s.status is StrategyStatus.VERIFIED
        entry = s.verified_passes_json[-1]
        assert entry["pass_no"] == 1 and entry["result"] == "PASS"
        assert entry["manual_override"] is True
        assert entry["outcome"] == "manual_override"
        assert entry["reason"] == REASON
        assert entry["overridden_by_email"]
        assert entry["attempt"] == 3
        assert entry["overridden_failure"] == "claim 1 unverified"

    def test_original_failures_are_kept(self, client, db_session, product_with_strategy):
        s = _strategy(db_session, product_with_strategy, {1: 2})
        before = len(s.verified_passes_json)
        _post(client, s)
        db_session.refresh(s)
        assert len(s.verified_passes_json) == before + 1
        fails = [e for e in s.verified_passes_json
                 if e["pass_no"] == 1 and e["result"] == "FAIL"]
        assert len(fails) == 2

    def test_three_failed_passes_can_be_signed_off(self, client, db_session,
                                                   product_with_strategy):
        s = _strategy(db_session, product_with_strategy, {1: 2, 6: 2, 8: 2})
        resp = _post(client, s, pass_nos=[8, 1, 6])
        assert resp.status_code == 200, resp.text
        db_session.refresh(s)
        assert sum(1 for e in s.verified_passes_json if e.get("manual_override")) == 3

    def test_a_pass_that_failed_then_passed_is_not_failing(self, client, db_session,
                                                           product_with_strategy):
        s = _strategy(db_session, product_with_strategy, {1: 2})
        s.verified_passes_json = [*s.verified_passes_json,
                                  {"pass_no": 4, "key": "legal_compliance", "name": "L",
                                   "attempt": 1, "result": "FAIL", "fix_description": "x",
                                   "fix_applied": True},
                                  {"pass_no": 4, "key": "legal_compliance", "name": "L",
                                   "attempt": 2, "result": "PASS", "fix_description": None,
                                   "fix_applied": False}]
        db_session.commit()
        assert _post(client, s).status_code == 200

    def test_is_audited(self, client, db_session, product_with_strategy):
        s = _strategy(db_session, product_with_strategy, {1: 2})
        _post(client, s)
        [ev] = _events(db_session, security_audit.STRATEGY_PASSES_OVERRIDDEN)
        assert ev.target_id == str(s.id)
        assert ev.details_json["passes"] == [1]
        assert ev.details_json["reason"] == REASON


class TestRefusals:
    def test_four_failed_passes_is_too_many(self, client, db_session, product_with_strategy):
        s = _strategy(db_session, product_with_strategy, {1: 2, 2: 2, 6: 2, 8: 2})
        resp = _post(client, s, pass_nos=[1, 2, 6])
        assert resp.status_code == 409
        db_session.refresh(s)
        assert s.status is StrategyStatus.NEEDS_HUMAN_REVIEW
        assert not any(e.get("manual_override") for e in s.verified_passes_json)

    def test_legal_compliance_can_never_be_overridden(self, client, db_session,
                                                      product_with_strategy):
        s = _strategy(db_session, product_with_strategy, {1: 2, 4: 2})
        resp = _post(client, s, pass_nos=[1, 4])
        assert resp.status_code == 409
        assert "Legal" in resp.json()["detail"]
        db_session.refresh(s)
        assert s.status is StrategyStatus.NEEDS_HUMAN_REVIEW
        assert not any(e.get("manual_override") for e in s.verified_passes_json)
        assert len(_events(db_session, security_audit.STRATEGY_PASSES_OVERRIDE_DENIED)) == 1

    def test_must_name_exactly_the_failed_passes(self, client, db_session,
                                                 product_with_strategy):
        s = _strategy(db_session, product_with_strategy, {1: 2, 6: 2})
        assert _post(client, s, pass_nos=[1]).status_code == 422      # partial
        assert _post(client, s, pass_nos=[1, 6, 7]).status_code == 422  # extra
        db_session.refresh(s)
        assert s.status is StrategyStatus.NEEDS_HUMAN_REVIEW

    @pytest.mark.parametrize("reason", ["", "ok", "too short reason"])
    def test_reason_is_required(self, client, db_session, product_with_strategy, reason):
        s = _strategy(db_session, product_with_strategy, {1: 2})
        assert _post(client, s, reason=reason).status_code in (422,)
        db_session.refresh(s)
        assert s.status is StrategyStatus.NEEDS_HUMAN_REVIEW

    def test_acknowledgement_is_required(self, client, db_session, product_with_strategy):
        s = _strategy(db_session, product_with_strategy, {1: 2})
        assert _post(client, s, acknowledge=False).status_code == 422
        db_session.refresh(s)
        assert s.status is StrategyStatus.NEEDS_HUMAN_REVIEW

    @pytest.mark.parametrize("status", [
        StrategyStatus.VERIFIED, StrategyStatus.VERIFYING, StrategyStatus.RESEARCHING,
        StrategyStatus.FAILED, StrategyStatus.PENDING, StrategyStatus.EXECUTING,
    ])
    def test_only_from_needs_human_review(self, client, db_session,
                                          product_with_strategy, status):
        s = _strategy(db_session, product_with_strategy, {1: 2}, status=status)
        assert _post(client, s).status_code == 409
        db_session.refresh(s)
        assert s.status is status

    def test_nothing_failed_means_nothing_to_override(self, client, db_session,
                                                      product_with_strategy):
        s = _strategy(db_session, product_with_strategy, {})
        assert _post(client, s).status_code == 409

    def test_another_accounts_strategy_is_not_found(self, client, db_session):
        other = m.User(email="other-ov@leadpilot.dev", email_verified=True)
        db_session.add(other)
        db_session.flush()
        p = m.Product(user=other, name="P", description="d", type=m.ProductType.SKILL)
        db_session.add(p)
        db_session.flush()
        s = m.Strategy(product_id=p.id, flow_type=m.FlowType.WITH_CLIENTS,
                       status=StrategyStatus.NEEDS_HUMAN_REVIEW,
                       verified_passes_json=_log({1: 2}))
        db_session.add(s)
        db_session.commit()
        assert _post(client, s).status_code == 404
        db_session.refresh(s)
        assert s.status is StrategyStatus.NEEDS_HUMAN_REVIEW

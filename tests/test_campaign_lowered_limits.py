"""Product defect #21: the campaign page ignored compliance-rule limits.

* The bounce banner said "≥ 3%" while the pause fires at "> threshold", and a
  workspace compliance rule can lower the threshold (compliance_rules
  .bounce_threshold). GET /strategies/{id}/campaign now reports the threshold
  the pause really uses, and so does the CRM campaigns dashboard.
* "Today / cap" showed the warm-up allowance with no rule cap and no mailbox
  health cap, while the send path applies both (outreach_tasks: effective_cap
  = min(rule cap, health cap)). The overview now applies the same caps (the
  rule for every region; a region-specific rule can lower it further for some
  leads).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.services import compliance_rules as rules
from app.services import crypto, workspaces


@pytest.fixture()
def ws(db_session, test_user):
    return workspaces.personal_workspace(db_session, test_user)


@pytest.fixture()
def mailbox(db_session, test_user):
    row = m.GmailAccount(
        user_id=test_user.id, email_address="me@leadpilot.dev",
        token_ciphertext=crypto.encrypt_json({"access_token": "a", "refresh_token": "r"}),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        created_at=datetime.now(timezone.utc) - timedelta(days=365))
    db_session.add(row)
    db_session.commit()
    return row


def _rule(db, ws, **fields):
    db.add(m.ComplianceRule(scope=str(ws.id), workspace_id=ws.id, region="*", channel="*",
                            **fields))
    db.commit()


def test_overview_reports_the_lowered_bounce_threshold(client, db_session, ws,
                                                       verified_strategy, mailbox):
    base = client.get(f"/strategies/{verified_strategy.id}/campaign").json()
    assert base["bounce_pause_threshold"] == pytest.approx(0.03)
    _rule(db_session, ws, bounce_pause_threshold=0.02)
    assert rules.bounce_threshold(db_session, verified_strategy) == pytest.approx(0.02)
    body = client.get(f"/strategies/{verified_strategy.id}/campaign").json()
    assert body["bounce_pause_threshold"] == pytest.approx(0.02)
    crm = client.get("/crm/dashboard/campaigns").json()["bounce"]
    assert crm["pause_threshold"] == pytest.approx(0.02)


def test_today_cap_applies_the_rule_cap(client, db_session, ws, verified_strategy, mailbox):
    before = client.get(f"/strategies/{verified_strategy.id}/campaign").json()
    assert before["daily_cap_today"] > 7
    _rule(db_session, ws, daily_cap=7)
    body = client.get(f"/strategies/{verified_strategy.id}/campaign").json()
    assert body["daily_cap_today"] == 7
    assert body["channels"]["email"]["daily_cap_today"] == 7
    assert body["channels"]["whatsapp"]["daily_cap_today"] <= 7


def test_today_cap_applies_the_mailbox_health_cap(client, db_session, verified_strategy,
                                                  mailbox, test_user):
    from app.services import mailbox_health

    db_session.add(m.MailboxHealth(user_id=test_user.id, mailbox_ref=str(mailbox.id), channel="email",
                                   state=mailbox_health.THROTTLED, throttle_cap=5, score=40))
    db_session.commit()
    body = client.get(f"/strategies/{verified_strategy.id}/campaign").json()
    assert body["daily_cap_today"] == 5

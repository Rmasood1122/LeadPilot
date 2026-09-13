"""Feature A6 — the client-facing shareable ROI dashboard.

Pins: a link is a one-time-shown token stored only as a hash; the public
dashboard needs no login, shows ROI aggregates and pipeline, and never a lead's
personal data; account vs campaign scope; revocation and expiry take effect at
once and look identical to an unknown token; the public endpoint is rate
limited and not cacheable or indexable; creation is owner-scoped and
phone-gated.

Public requests are made with an explicitly EMPTY Authorization header rather
than the shared `anon_client` fixture: `anon_client` strips the header from
the very same TestClient `client` uses, so a test needing both an owner call
and an anonymous call cannot use the two fixtures together.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import share_links
from tests.conftest import auth_headers


def _public(client, token):
    """An anonymous request: no bearer token reaches the app."""
    return client.get(f"/public/roi/{token}", headers={"Authorization": ""})


@pytest.fixture()
def campaign(db_session, verified_strategy):
    verified_strategy.status = m.StrategyStatus.EXECUTING
    sequence = m.Sequence(strategy_id=verified_strategy.id, channel=m.ChannelType.EMAIL,
                          name="cold", status=m.SequenceStatus.ACTIVE)
    db_session.add(sequence)
    db_session.commit()
    now = datetime.now(timezone.utc)
    leads = []
    for i, (status, value) in enumerate([(m.LeadStatus.CONTACTED, None),
                                         (m.LeadStatus.REPLIED, None),
                                         (m.LeadStatus.MEETING_BOOKED, Decimal("2500.00")),
                                         (m.LeadStatus.CLOSED_WON, Decimal("4000.00"))]):
        lead = m.Lead(strategy_id=verified_strategy.id, source="manual", external_id=f"S{i}",
                      full_name=f"Secret Person {i}", email=f"secret{i}@client-corp.com",
                      company="Client Corp", status=status, estimated_deal_value=value)
        db_session.add(lead)
        db_session.flush()
        db_session.add(m.Message(sequence_id=sequence.id, lead_id=lead.id,
                                 channel=m.ChannelType.EMAIL, step_no=1, template="t", body="b",
                                 status=m.MessageStatus.SENT, sent_at=now - timedelta(days=3)))
        db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.SENT, channel="email",
                                 ts=now - timedelta(days=3)))
        leads.append(lead)
    db_session.add(m.Outcome(lead_id=leads[1].id, event=m.OutcomeEvent.REPLIED, channel="email",
                             ts=now - timedelta(days=2)))
    db_session.add(m.ROISnapshot(strategy_id=verified_strategy.id,
                                 snapshot_date=now.date() - timedelta(days=1), meetings_booked=1,
                                 pipeline_value=Decimal("6500.00"),
                                 revenue_attributed=Decimal("4000.00")))
    db_session.commit()
    return verified_strategy, leads


def _create(client, **body):
    resp = client.post("/share-links", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestCreate:
    def test_the_token_is_shown_once_and_stored_hashed(self, client, db_session, campaign):
        created = _create(client, label="Q3 results for Acme")
        token = created["token"]
        assert len(token) >= 40 and created["url"].endswith(f"/share/roi?token={token}")
        row = db_session.execute(select(m.ShareLink)).scalar_one()
        assert row.token_hash == share_links.hash_token(token) and token not in row.token_hash
        assert row.token_prefix == token[:8]
        listed = client.get("/share-links").json()
        assert "token" not in listed[0] and listed[0]["status"] == "active"

    @pytest.mark.parametrize("days", [0, 366])
    def test_expiry_must_be_bounded(self, client, days):
        assert client.post("/share-links", json={"expires_in_days": days}).status_code == 422

    def test_a_campaign_link_needs_an_owned_campaign(self, client, db_session):
        other = m.User(email="share-other@example.com", email_verified=True)
        db_session.add(other)
        db_session.flush()
        product = m.Product(user_id=other.id, name="theirs", description="x",
                            type=m.ProductType.SKILL)
        db_session.add(product)
        db_session.flush()
        strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.WITH_CLIENTS)
        db_session.add(strategy)
        db_session.commit()
        assert client.post("/share-links", json={"strategy_id": str(strategy.id)}).status_code == 404

    def test_creation_is_phone_gated(self, client, db_session, test_user):
        test_user.identity_required = True
        db_session.commit()
        resp = client.post("/share-links", json={})
        assert resp.status_code == 403 and resp.json()["detail"] == "PHONE_NOT_VERIFIED"

    def test_listing_requires_login(self, client):
        resp = client.get("/share-links", headers={"Authorization": ""})
        assert resp.status_code == 401


class TestPublicDashboard:
    def test_no_login_needed_and_the_numbers_are_there(self, client, campaign):
        token = _create(client)["token"]
        resp = _public(client, token)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["totals"]["messages_sent"] == 4
        assert body["totals"]["revenue_attributed"] == "4000.00"
        assert body["totals"]["pipeline_value"] == "6500.00"
        stages = {s["key"]: s["count"] for s in body["pipeline"]}
        assert stages == {"contacted": 1, "replied": 1, "meeting_booked": 1,
                          "proposal_sent": 0, "won": 1}
        assert body["trend"][0]["revenue_attributed"] == "4000.00"
        assert body["scope"]["type"] == "account"

    def test_no_personal_data_ever_reaches_the_page(self, client, campaign):
        token = _create(client)["token"]
        text = json.dumps(_public(client, token).json())
        for leaked in ("Secret Person", "secret0@client-corp.com", "Client Corp",
                       "test@leadpilot.dev"):
            assert leaked not in text

    def test_campaign_scope(self, client, db_session, campaign, test_user):
        second_product = m.Product(user_id=test_user.id, name="Other", description="x",
                                   type=m.ProductType.SKILL)
        db_session.add(second_product)
        db_session.flush()
        other = m.Strategy(product_id=second_product.id, flow_type=m.FlowType.WITH_CLIENTS)
        db_session.add(other)
        db_session.commit()
        token = _create(client, strategy_id=str(other.id))["token"]
        body = _public(client, token).json()
        assert body["scope"] == {"type": "campaign", "campaign_name": "Other", "campaigns": 1}
        assert body["totals"]["messages_sent"] == 0

    def test_views_are_counted(self, client, campaign):
        token = _create(client)["token"]
        _public(client, token)
        _public(client, token)
        (link,) = client.get("/share-links").json()
        assert link["view_count"] == 2 and link["last_viewed_at"]

    def test_not_cacheable_or_indexable(self, client, campaign):
        token = _create(client)["token"]
        headers = _public(client, token).headers
        assert headers["cache-control"] == "no-store"
        assert "noindex" in headers["x-robots-tag"]


class TestRevokeAndExpire:
    def test_revocation_is_immediate(self, client, campaign):
        created = _create(client)
        assert client.delete(f"/share-links/{created['id']}").json()["status"] == "revoked"
        assert _public(client, created["token"]).status_code == 404

    def test_expired_links_stop_working(self, client, db_session, campaign):
        created = _create(client, expires_in_days=1)
        link = db_session.get(m.ShareLink, uuid.UUID(created["id"]))
        link.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()
        assert _public(client, created["token"]).status_code == 404
        assert client.get("/share-links").json()[0]["status"] == "expired"

    def test_unknown_expired_and_revoked_are_indistinguishable(self, client, campaign):
        revoked = _create(client)
        client.delete(f"/share-links/{revoked['id']}")
        unknown = _public(client, "not-a-real-token")
        gone = _public(client, revoked["token"])
        assert unknown.status_code == gone.status_code == 404
        assert unknown.json() == gone.json()

    def test_only_the_owner_can_revoke(self, client, db_session, campaign):
        created = _create(client)
        stranger = m.User(email="share-stranger@example.com", email_verified=True)
        db_session.add(stranger)
        db_session.commit()
        assert client.delete(f"/share-links/{created['id']}",
                             headers=auth_headers(stranger)).status_code == 404
        assert client.get("/share-links", headers=auth_headers(stranger)).json() == []


def test_the_public_endpoint_is_rate_limited(client, monkeypatch, campaign):
    from app.core.config import settings as core

    token = _create(client)["token"]
    monkeypatch.setattr(core, "RATE_LIMIT_PUBLIC_SHARE", 2)
    codes = [_public(client, token).status_code for _ in range(3)]
    assert codes == [200, 200, 429]

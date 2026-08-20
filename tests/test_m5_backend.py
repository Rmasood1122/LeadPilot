"""M5 backend tests — auth, theme persistence, analytics aggregates,
manual campaign pause/resume."""

import io
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import auth as auth_svc
from tests.conftest import NOW


def _signup(client, email="ui@x.com", password="hunter22!"):
    r = client.post("/auth/signup", json={"email": email, "password": password})
    assert r.status_code == 201
    return r.json()


def _auth_headers(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}


class TestAuth:
    def test_signup_login_me_roundtrip(self, client, db_session):
        tokens = _signup(client)
        me = client.get("/auth/me", headers=_auth_headers(tokens))
        assert me.status_code == 200
        assert me.json()["email"] == "ui@x.com"
        login = client.post("/auth/login", json={"email": "ui@x.com",
                                                 "password": "hunter22!"})
        assert login.status_code == 200

    def test_wrong_password_and_unknown_user_same_error(self, client):
        _signup(client)
        bad = client.post("/auth/login", json={"email": "ui@x.com",
                                               "password": "wrongwrong"})
        unknown = client.post("/auth/login", json={"email": "no@x.com",
                                                   "password": "wrongwrong"})
        assert bad.status_code == unknown.status_code == 401
        assert bad.json()["detail"] == unknown.json()["detail"]

    def test_duplicate_signup_rejected(self, client):
        _signup(client)
        r = client.post("/auth/signup", json={"email": "ui@x.com",
                                              "password": "hunter22!"})
        assert r.status_code == 409

    def test_refresh_rotates_tokens_and_typ_is_enforced(self, client):
        tokens = _signup(client)
        r = client.post("/auth/refresh",
                        json={"refresh_token": tokens["refresh_token"]})
        assert r.status_code == 200
        # an ACCESS token can never be used as a refresh token
        r = client.post("/auth/refresh",
                        json={"refresh_token": tokens["access_token"]})
        assert r.status_code == 401

    def test_password_hashing_roundtrip_and_min_length(self):
        stored = auth_svc.hash_password("longenough")
        assert auth_svc.verify_password("longenough", stored)
        assert not auth_svc.verify_password("wrong", stored)
        with pytest.raises(ValueError):
            auth_svc.hash_password("short")

    def test_protected_endpoint_requires_token(self, anon_client):
        assert anon_client.get("/auth/me").status_code == 401


class TestTheme:
    def test_theme_persist_roundtrip_with_contrast_flag(self, client,
                                                        db_session):
        tokens = _signup(client)
        theme = {"preset": "custom", "background_color": "#101014",
                 "primary_color": "#ffaa00", "accent_color": "#00ccaa",
                 "font_family": "Sora", "font_size_scale": 1.1,
                 "radius_px": 12, "density": "compact",
                 "contrast_warnings": ["accent-on-background 2.7:1 < 4.5:1"]}
        r = client.put("/me/theme", json=theme, headers=_auth_headers(tokens))
        assert r.status_code == 200
        saved = client.get("/me/theme", headers=_auth_headers(tokens)).json()
        assert saved["theme"]["font_family"] == "Sora"
        # the user was demonstrably informed — the flag is persisted
        assert saved["theme"]["contrast_warnings"] == theme["contrast_warnings"]

    def test_invalid_hex_rejected(self, client):
        tokens = _signup(client)
        r = client.put("/me/theme", json={"background_color": "red"},
                       headers=_auth_headers(tokens))
        assert r.status_code == 422

    def test_background_upload_serves_url(self, client, tmp_path, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "media_dir", str(tmp_path))
        tokens = _signup(client)
        r = client.post("/me/theme/background",
                        headers=_auth_headers(tokens),
                        files={"file": ("bg.png", io.BytesIO(b"\x89PNG rest"),
                                        "image/png")})
        assert r.status_code == 201
        assert "/media/bg_" in r.json()["url"]
        r = client.post("/me/theme/background",
                        headers=_auth_headers(tokens),
                        files={"file": ("x.gif", io.BytesIO(b"gif"),
                                        "image/gif")})
        assert r.status_code == 422


class TestAnalyticsAndControls:
    def _seed(self, db, strategy, lead):
        msg = m.Message(sequence_id=None, lead_id=lead.id,
                        channel=m.ChannelType.EMAIL, step_no=1, template="t",
                        variant="A", status=m.MessageStatus.SENT, sent_at=NOW)
        # Message.sequence_id is non-nullable — create a sequence
        seq = m.Sequence(strategy_id=strategy.id, channel=m.ChannelType.EMAIL,
                         name="s", status=m.SequenceStatus.ACTIVE)
        db.add(seq)
        db.flush()
        msg.sequence_id = seq.id
        db.add(msg)
        db.flush()
        db.add_all([
            m.Outcome(lead_id=lead.id, message_id=msg.id,
                      event=m.OutcomeEvent.SENT, channel="email", ts=NOW),
            m.Outcome(lead_id=lead.id, message_id=msg.id,
                      event=m.OutcomeEvent.REPLIED, channel="email",
                      ts=NOW + timedelta(hours=1)),
            m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.SENT,
                      channel="whatsapp", ts=NOW + timedelta(days=1)),
        ])
        db.commit()

    def test_analytics_series_and_variants(self, leads_client, db_session,
                                           verified_strategy):
        lead = m.Lead(strategy_id=verified_strategy.id, source="manual",
                      email="a@b.com", status=m.LeadStatus.VERIFIED)
        db_session.add(lead)
        db_session.commit()
        self._seed(db_session, verified_strategy, lead)
        r = leads_client.get(
            f"/strategies/{verified_strategy.id}/analytics?granularity=day")
        assert r.status_code == 200
        data = r.json()
        assert {(p["channel"], p["event"]) for p in data["series"]} == {
            ("email", "sent"), ("email", "replied"), ("whatsapp", "sent")}
        assert data["variants"]["A"]["sent"] == 1
        assert data["variants"]["A"]["replied"] == 1
        assert data["learning_insights"] is None  # M8 fills this

    def test_bad_granularity_rejected(self, leads_client, verified_strategy):
        r = leads_client.get(
            f"/strategies/{verified_strategy.id}/analytics?granularity=hour")
        assert r.status_code == 422

    def test_manual_pause_and_resume(self, leads_client, db_session,
                                     verified_strategy):
        r = leads_client.post(
            f"/strategies/{verified_strategy.id}/campaign/pause")
        assert r.json()["campaign_state"] == "paused_manual"
        db_session.refresh(verified_strategy)
        assert verified_strategy.campaign_state == "paused_manual"
        r = leads_client.post(
            f"/strategies/{verified_strategy.id}/campaign/resume")
        assert r.json()["campaign_state"] == "active"


class TestUiSupport:
    def test_strategy_list_and_document(self, leads_client, verified_strategy,
                                        db_session):
        verified_strategy.strategy_document = "# Final Strategy"
        db_session.commit()
        rows = leads_client.get("/strategies").json()
        assert rows and rows[0]["id"] == str(verified_strategy.id)
        doc = leads_client.get(
            f"/strategies/{verified_strategy.id}/document").json()
        assert doc["strategy_document"] == "# Final Strategy"

    def test_lead_patch_validates_transitions(self, leads_client, db_session,
                                              verified_strategy):
        lead = m.Lead(strategy_id=verified_strategy.id, source="manual",
                      email="k@b.com", status=m.LeadStatus.VERIFIED)
        db_session.add(lead)
        db_session.commit()
        ok = leads_client.patch(f"/leads/{lead.id}", json={"status": "flagged"})
        assert ok.status_code == 200
        bad = leads_client.patch(f"/leads/{lead.id}",
                                 json={"status": "meeting_booked"})
        assert bad.status_code == 422  # disallowed drag snaps back

    def test_integrations_status_masks_secrets(self, leads_client,
                                               monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "apollo_api_key", "sk-apollo-supersecret")
        data = leads_client.get("/integrations/status").json()
        assert data["apollo"]["key_set"] is True
        assert "supersecret" not in (data["apollo"]["masked"] or "")

    def test_suppression_viewer_and_manual_add(self, leads_client, db_session):
        r = leads_client.post("/suppression",
                              json={"email": "gone@x.com", "reason": "spam"})
        assert r.status_code == 201
        entries = leads_client.get("/suppression").json()["entries"]
        assert any(e["email"] == "gone@x.com" for e in entries)
        assert leads_client.post("/suppression",
                                 json={"reason": "x"}).status_code == 422

    def test_sequence_list(self, leads_client, db_session, verified_strategy):
        seq = m.Sequence(strategy_id=verified_strategy.id,
                         channel=m.ChannelType.EMAIL, name="s1",
                         status=m.SequenceStatus.ACTIVE)
        db_session.add(seq)
        db_session.flush()
        db_session.add(m.SequenceStep(sequence_id=seq.id, step_no=1,
                                      template="t", delay_days=0))
        db_session.commit()
        rows = leads_client.get(
            f"/strategies/{verified_strategy.id}/sequences").json()
        assert rows[0]["steps"][0]["step_no"] == 1

"""PD-1: migration 0071 brings the outbound-webhook tables in line with the model.

Migration 0011 created webhook_targets.event_types as text[] and
webhook_deliveries with payload_json text, last_response_code and no
delivered_at. app/services/webhook_delivery.py writes through the ORM model
(event_types JSON, payload_json JSON, last_status_code, delivered_at), so on
PostgreSQL every target creation failed with DatatypeMismatch and every
delivery with UndefinedColumn. SQLite never showed it: the offline suite
builds tables from the model.

Each test runs alembic in a subprocess against its own throwaway database on
the integration server, so the shared pg_engine schema is never touched.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from tests.integration.conftest import TEST_DATABASE_URL

REPO = Path(__file__).resolve().parents[2]
BEFORE = "0070_linkedin_network_messages"
AFTER = "0071_webhook_schema_sync"


@pytest.fixture()
def scratch_url():
    """A fresh empty database next to the integration database."""
    base = make_url(TEST_DATABASE_URL)
    assert base.host in ("localhost", "127.0.0.1"), "scratch databases are local only"
    name = f"lp_mig0071_{uuid.uuid4().hex[:8]}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = base.set(database=name).render_as_string(hide_password=False)
    try:
        yield url
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _alembic(url: str, *args: str) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=str(REPO),
        env={**os.environ, "DATABASE_URL": url}, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, f"alembic {' '.join(args)} failed:\n{proc.stdout}\n{proc.stderr}"


def _columns(engine, table: str) -> dict[str, str]:
    return {c["name"]: str(c["type"]) for c in inspect(engine).get_columns(table)}


def _seed_legacy_rows(engine) -> tuple[str, str, str]:
    """One target and two deliveries in the pre-0071 shapes: one with a JSON
    payload, one whose payload text is not valid JSON."""
    user_id, target_id, delivery_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    bad_id = uuid.uuid4()
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (id, email, plan, theme_json, is_admin, is_suspended, "
                       "email_verified) VALUES (:id, 'legacy@test.io', 'FREE', '{}', false, "
                       "false, true)"), {"id": user_id})
        c.execute(text("INSERT INTO webhook_targets (id, user_id, url, secret_encrypted, "
                       "event_types) VALUES (:id, :uid, 'https://hooks.example.com/x', 's', "
                       "ARRAY['meeting_booked','reply_received'])"),
                  {"id": target_id, "uid": user_id})
        c.execute(text("INSERT INTO webhook_deliveries (id, target_id, event_type, payload_json, "
                       "status, attempts, last_response_code) VALUES (:id, :tid, "
                       "'meeting_booked', :payload, 'failed', 2, 503)"),
                  {"id": delivery_id, "tid": target_id,
                   "payload": json.dumps({"event": "meeting_booked", "data": {"lead": "l1"}})})
        c.execute(text("INSERT INTO webhook_deliveries (id, target_id, event_type, payload_json, "
                       "status, attempts) VALUES (:id, :tid, 'x', 'not json {', 'failed', 1)"),
                  {"id": bad_id, "tid": target_id})
    return str(target_id), str(delivery_id), str(bad_id)


def _column_info(engine, table: str, column: str) -> tuple[str, str | None]:
    with engine.connect() as c:
        return c.execute(text(
            "SELECT data_type, column_default FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"), {"t": table, "c": column}).one()


def test_upgrade_converts_legacy_rows_and_matches_the_model(scratch_url):
    _alembic(scratch_url, "upgrade", BEFORE)
    engine = create_engine(scratch_url)
    try:
        target_id, delivery_id, bad_id = _seed_legacy_rows(engine)

        _alembic(scratch_url, "upgrade", AFTER)

        with engine.connect() as c:
            events = c.execute(text("SELECT event_types FROM webhook_targets WHERE id = :id"),
                               {"id": target_id}).scalar_one()
            row = c.execute(text("SELECT payload_json, last_status_code, delivered_at "
                                 "FROM webhook_deliveries WHERE id = :id"),
                            {"id": delivery_id}).one()
        assert events == ["meeting_booked", "reply_received"]
        assert row.payload_json == {"event": "meeting_booked", "data": {"lead": "l1"}}
        assert row.last_status_code == 503
        assert row.delivered_at is None

        # A payload that is not valid JSON is kept, not lost and not fatal.
        with engine.connect() as c:
            kept = c.execute(text("SELECT payload_json FROM webhook_deliveries WHERE id = :id"),
                             {"id": bad_id}).scalar_one()
        assert kept == {"legacy_text": "not json {"}

        targets, deliveries = (_columns(engine, "webhook_targets"),
                               _columns(engine, "webhook_deliveries"))
        assert targets["event_types"] == "JSON"
        assert _column_info(engine, "webhook_targets", "event_types")[1] == "'[]'::json"
        assert deliveries["payload_json"] == "JSON"
        assert {"last_status_code", "delivered_at"} <= deliveries.keys()
    finally:
        engine.dispose()


def test_orm_round_trip_works_after_upgrade(scratch_url, monkeypatch):
    """create_target + create_delivery + a failed attempt, through the ORM."""
    import httpx
    from sqlalchemy.orm import Session

    from app.db.models import User, WebhookDelivery
    from app.services import webhook_delivery

    _alembic(scratch_url, "upgrade", "head")
    monkeypatch.setattr(webhook_delivery, "_resolve", lambda host: ["93.184.216.34"])
    monkeypatch.setattr(webhook_delivery, "_http", lambda: httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))))
    monkeypatch.setattr(webhook_delivery, "_schedule", lambda delivery_id, countdown=0: None)
    engine = create_engine(scratch_url)
    try:
        with Session(engine) as db:
            user = User(email="orm@test.io", email_verified=True)
            db.add(user)
            db.commit()
            target, _ = webhook_delivery.create_target(
                db, user.id, "https://hooks.example.com/y", ["meeting_booked"])
            delivery = webhook_delivery.create_delivery(db, target, "meeting_booked", {"a": 1})

            assert webhook_delivery.deliver(db, delivery.id) == "retry"

            db.expire_all()
            row = db.get(WebhookDelivery, delivery.id)
            assert row.last_status_code == 500 and row.attempts == 1
            assert row.payload_json["data"] == {"a": 1}
            assert target.event_types == ["meeting_booked"]
    finally:
        engine.dispose()


def test_downgrade_restores_the_previous_shapes(scratch_url):
    _alembic(scratch_url, "upgrade", BEFORE)
    engine = create_engine(scratch_url)
    try:
        target_id, delivery_id, bad_id = _seed_legacy_rows(engine)
        _alembic(scratch_url, "upgrade", AFTER)
        # A status code written by the post-0071 code must survive a downgrade.
        with engine.begin() as c:
            c.execute(text("UPDATE webhook_deliveries SET last_status_code = 418 WHERE id = :id"),
                      {"id": bad_id})
        _alembic(scratch_url, "downgrade", BEFORE)

        assert _column_info(engine, "webhook_targets", "event_types") == (
            "ARRAY", "'{}'::text[]")
        assert _column_info(engine, "webhook_deliveries", "payload_json")[0] == "text"
        deliveries = _columns(engine, "webhook_deliveries")
        assert "last_status_code" not in deliveries and "delivered_at" not in deliveries

        with engine.connect() as c:
            events = c.execute(text("SELECT event_types FROM webhook_targets WHERE id = :id"),
                               {"id": target_id}).scalar_one()
            good = c.execute(text("SELECT payload_json, last_response_code FROM "
                                  "webhook_deliveries WHERE id = :id"),
                             {"id": delivery_id}).one()
            bad = c.execute(text("SELECT payload_json, last_response_code FROM "
                                 "webhook_deliveries WHERE id = :id"), {"id": bad_id}).one()
        assert events == ["meeting_booked", "reply_received"]
        assert json.loads(good.payload_json) == {"event": "meeting_booked",
                                                 "data": {"lead": "l1"}}
        assert good.last_response_code == 503
        assert bad.payload_json == "not json {"     # legacy_text unwrapped
        assert bad.last_response_code == 418
    finally:
        engine.dispose()

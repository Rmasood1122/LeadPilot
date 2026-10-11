"""Customer win-back import against REAL PostgreSQL (review fix M3).

SQLite does not enforce VARCHAR lengths and accepts NUL bytes in text;
PostgreSQL rejects both with an error mid-transaction. The import validates
every row against the column sizes before writing, refuses NUL bytes for the
whole file, and commits once -- so on the dialect that ships an over-long
value is a refused row (never a DataError), and a failure half way leaves
nothing behind.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import local_business as lb
from app.services import system_settings

HEADER = "name,email,phone,consent_channels,consent_date,consent_source,consent_text"


def _csv(*rows: str) -> bytes:
    return ("\n".join([HEADER, *rows]) + "\n").encode()


@pytest.fixture()
def setup(db_session):
    user = m.User(email=f"cafe-{uuid.uuid4().hex[:6]}@import-pg.test", email_verified=True)
    db_session.add(user)
    db_session.flush()
    product = m.Product(user_id=user.id, name="Bella Cafe", description="Cafe",
                        type=m.ProductType.PRODUCT, business_type="restaurant")
    db_session.add(product)
    db_session.flush()
    strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.NO_CLIENTS,
                          status=m.StrategyStatus.VERIFIED)
    db_session.add(strategy)
    db_session.commit()
    system_settings.set(db_session, lb.WINBACK_FLAG, True)
    return user, product, strategy


def _customers(db, strategy):
    return db.execute(select(m.Lead).where(m.Lead.strategy_id == strategy.id)).scalars().all()


def test_over_long_fields_are_refused_rows_not_database_errors(db_session, setup):
    user, product, strategy = setup
    out = lb.import_customers(db_session, user, strategy, product, _csv(
        "N" * 300 + ",a@example.com,,email,2026-03-01,web form,",
        "B,b@example.com,,email,2026-03-01," + "s" * 500 + ",",
        "C,c@example.com,,email,2026-03-01,web form," + "t" * 5000,
        "D," + "e" * 400 + "@example.com,,email,2026-03-01,web form,",
        "E,,+1" + "2" * 60 + ",whatsapp,2026-03-01,web form,",
        "Fine,fine@example.com,+12125550100,email;whatsapp,2026-03-01,web form,ok",
    ), lb.ATTESTATION)
    assert len(out["accepted"]) == 1, out
    assert len(out["rejected"]) == 5
    leads = _customers(db_session, strategy)
    assert [lead.email for lead in leads] == ["fine@example.com"]
    events = db_session.execute(select(m.ConsentEvent).where(
        m.ConsentEvent.lead_id == leads[0].id)).scalars().all()
    assert sorted(e.channel for e in events) == ["email", "whatsapp"]


def test_nul_bytes_refuse_the_whole_file(db_session, setup):
    user, product, strategy = setup
    with pytest.raises(lb.ImportRefused) as exc:
        lb.import_customers(db_session, user, strategy, product,
                            _csv("A\x00,a@example.com,,email,2026-03-01,web form,"),
                            lb.ATTESTATION)
    assert exc.value.status == 422
    assert _customers(db_session, strategy) == []


def test_a_failure_half_way_leaves_nothing(db_session, setup, monkeypatch):
    from app.services import whatsapp_optin

    user, product, strategy = setup
    real = whatsapp_optin.record_opt_in
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("connection lost")
        return real(*a, **k)

    monkeypatch.setattr(whatsapp_optin, "record_opt_in", flaky)
    with pytest.raises(lb.ImportRefused) as exc:
        lb.import_customers(db_session, user, strategy, product, _csv(
            "A,,+12125550101,whatsapp,2026-03-01,web form,",
            "B,,+12125550102,whatsapp,2026-03-01,web form,"), lb.ATTESTATION)
    assert exc.value.status == 500 and "nothing was saved" in exc.value.detail
    assert _customers(db_session, strategy) == []
    assert db_session.execute(select(m.WhatsAppOptIn)).scalars().all() == []
    assert db_session.execute(select(m.CustomerImport)).scalars().all() == []

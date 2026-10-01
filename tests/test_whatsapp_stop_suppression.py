"""NEW-01 — a signed WhatsApp STOP must suppress, not return HTTP 500.

The defect only exists under the PRODUCTION session configuration:
app/db/base.py builds SessionLocal with autoflush=False. revoke_opt_in added a
phone SuppressionEntry and then called consent.suppress_everywhere, which added
the same phone again; with autoflush off neither guard's SELECT saw the other's
pending row, and the commit violated the unique index on suppression_list.phone.

The shared `db_session` fixture uses SQLAlchemy's default autoflush=True, which
hides this. So this module overrides `db_session` with a sessionmaker
configured the way production is, and goes through the signed HTTP webhook.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import models as m
from app.db.base import Base, get_db
from app.services import consent
from app.services import whatsapp_optin as optin_svc
from app.workers.lead_tasks import is_suppressed
from tests.conftest import wa_signed_post

FROM_PHONE = "923001234567"   # wa_lead's number as Meta sends it (no '+')


@pytest.fixture()
def db_session():
    """Same SQLite schema as conftest, but the session factory mirrors
    app/db/base.py::SessionLocal — autoflush=False, expire_on_commit=False."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    ProductionLikeSession = sessionmaker(bind=engine, autoflush=False,
                                         expire_on_commit=False)
    session = ProductionLikeSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def http(db_session):
    """raise_server_exceptions=False so an unhandled error is observed as the
    HTTP 500 Meta would receive, not as an exception raised into the test."""
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def _stop(wamid: str, text: str = "STOP") -> dict:
    return {"entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "5550001"},
        "messages": [{"id": wamid, "from": FROM_PHONE,
                      "timestamp": "1754900000", "type": "text",
                      "text": {"body": text}}],
    }}]}]}


def _phone_rows(db_session, lead) -> list:
    return db_session.execute(select(m.SuppressionEntry).where(
        m.SuppressionEntry.phone == lead.phone)).scalars().all()


def _email_rows(db_session, lead) -> list:
    return db_session.execute(select(m.SuppressionEntry).where(
        m.SuppressionEntry.email == lead.email)).scalars().all()


def _ledger(db_session, lead, kind: str, channel: str) -> list:
    return db_session.execute(select(m.ConsentEvent).where(
        m.ConsentEvent.lead_id == lead.id,
        m.ConsentEvent.kind == kind,
        m.ConsentEvent.channel == channel)).scalars().all()


class TestPreconditions:
    def test_the_session_is_configured_like_production(self, db_session):
        assert db_session.autoflush is False

    def test_the_unique_phone_index_exists_in_the_test_schema(self, db_session):
        """Without it the duplicate insert would be silently accepted and this
        module would prove nothing."""
        indexes = {ix["name"]: ix for ix in
                   inspect(db_session.get_bind()).get_indexes("suppression_list")}
        assert "ix_suppression_list_phone" in indexes
        assert bool(indexes["ix_suppression_list_phone"]["unique"]) is True

    def test_the_lead_has_both_identifiers_and_a_live_opt_in(self, wa_lead):
        assert wa_lead.email and wa_lead.phone
        assert wa_lead.whatsapp_opted_in is True


class TestSignedStop:
    def test_stop_returns_200_and_suppresses_the_phone_exactly_once(
            self, http, db_session, wa_lead):
        response = wa_signed_post(http, _stop("wamid.STOP1"))
        assert response.status_code == 200, response.text
        assert response.json()["processed"] == 1

        assert len(_phone_rows(db_session, wa_lead)) == 1
        assert len(_ledger(db_session, wa_lead, consent.SUPPRESSED, consent.PHONE)) == 1
        assert optin_svc.current_status(db_session, wa_lead.id) is m.OptInStatus.OPTED_OUT

    def test_stop_still_suppresses_the_email(self, http, db_session, wa_lead):
        """A STOP is an instruction about the person, not about one channel."""
        assert wa_signed_post(http, _stop("wamid.STOP2")).status_code == 200

        assert len(_email_rows(db_session, wa_lead)) == 1
        assert len(_ledger(db_session, wa_lead, consent.SUPPRESSED, consent.EMAIL)) == 1
        assert len(_ledger(db_session, wa_lead, consent.WITHDRAWN, consent.ALL)) >= 1

    def test_send_time_enforcement_sees_the_stop(self, http, db_session, wa_lead):
        """The global check every send path runs, and the flag the WhatsApp
        adapter refuses to send without."""
        assert wa_signed_post(http, _stop("wamid.STOP3")).status_code == 200

        assert is_suppressed(db_session, phone=wa_lead.phone) is True
        assert is_suppressed(db_session, email=wa_lead.email) is True
        db_session.refresh(wa_lead)
        assert wa_lead.whatsapp_opted_in is False

    def test_redelivery_of_the_same_stop_is_idempotent(self, http, db_session, wa_lead):
        """Meta retries deliveries."""
        first = wa_signed_post(http, _stop("wamid.STOP4"))
        second = wa_signed_post(http, _stop("wamid.STOP4"))
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert second.json()["duplicates"] == 1

        assert len(_phone_rows(db_session, wa_lead)) == 1
        assert len(_ledger(db_session, wa_lead, consent.SUPPRESSED, consent.PHONE)) == 1

    def test_a_second_stop_message_does_not_duplicate_the_suppression(
            self, http, db_session, wa_lead):
        """A person who sends STOP twice gets a new message id each time, so
        this one is NOT absorbed by the webhook's event-id dedupe."""
        first = wa_signed_post(http, _stop("wamid.STOP5"))
        second = wa_signed_post(http, _stop("wamid.STOP6"))
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert second.json()["processed"] == 1

        assert len(_phone_rows(db_session, wa_lead)) == 1
        assert len(_email_rows(db_session, wa_lead)) == 1
        assert len(_ledger(db_session, wa_lead, consent.SUPPRESSED, consent.PHONE)) == 1

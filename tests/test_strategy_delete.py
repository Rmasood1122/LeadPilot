"""DELETE /strategies/{id} -- password-confirmed, audited, permanent.

This module runs on a SQLite database with FOREIGN KEY ENFORCEMENT ON (the
shared conftest's engine leaves it off, SQLite's default). Deletion leans on
the schema's ON DELETE CASCADE rules exactly as PostgreSQL does, so with
enforcement off a broken cascade -- or a child the ORM tries to NULL first --
would pass here and fail in production.
"""

import uuid

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import models as m
from app.db.base import Base
from app.services import auth as auth_svc
from app.services import security_audit
from tests.conftest import auth_headers

PASSWORD = "CorrectHorse!1"


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _foreign_keys_on(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(scope="module")
def password_hash():
    return auth_svc.hash_password(PASSWORD)


@pytest.fixture()
def confirmable(db_session, test_user, password_hash):
    test_user.password_hash = password_hash
    db_session.commit()
    return test_user


def _delete(client, strategy_id, password=PASSWORD, **headers):
    return client.request("DELETE", f"/strategies/{strategy_id}",
                          json={"password": password} if password is not None else {},
                          headers=headers or None)


def _count(db_session, model, *where):
    db_session.expire_all()
    return db_session.execute(select(func.count()).select_from(model).where(*where)).scalar_one()


def _audit(db_session, action):
    db_session.expire_all()
    return db_session.execute(select(m.SecurityAuditEvent)
                              .where(m.SecurityAuditEvent.action == action)).scalars().all()


class TestDeleteStrategy:
    def test_the_right_password_deletes_the_strategy_and_everything_under_it(
            self, client, db_session, confirmable, verified_strategy, lead_batch, enrolled):
        sid, product_id = verified_strategy.id, verified_strategy.product_id
        sequence_ids = [s for (s,) in db_session.execute(
            select(m.Sequence.id).where(m.Sequence.strategy_id == sid))]
        assert _count(db_session, m.Lead, m.Lead.strategy_id == sid) > 0
        assert _count(db_session, m.SequenceEnrollment,
                      m.SequenceEnrollment.sequence_id.in_(sequence_ids)) > 0

        resp = _delete(client, sid)

        assert resp.status_code == 200, resp.text
        assert resp.json()["deleted"] is True and resp.json()["id"] == str(sid)
        assert _count(db_session, m.Strategy, m.Strategy.id == sid) == 0
        assert _count(db_session, m.Lead, m.Lead.strategy_id == sid) == 0
        assert _count(db_session, m.LeadBatch, m.LeadBatch.strategy_id == sid) == 0
        assert _count(db_session, m.Sequence, m.Sequence.strategy_id == sid) == 0
        assert _count(db_session, m.SequenceStep,
                      m.SequenceStep.sequence_id.in_(sequence_ids)) == 0
        assert _count(db_session, m.SequenceEnrollment,
                      m.SequenceEnrollment.sequence_id.in_(sequence_ids)) == 0
        # The product the strategy was built for is not part of the delete.
        assert _count(db_session, m.Product, m.Product.id == product_id) == 1

    def test_the_deletion_is_audited(self, client, db_session, confirmable, verified_strategy):
        sid = verified_strategy.id
        assert _delete(client, sid, **{"User-Agent": "pytest-agent"}).status_code == 200
        [event_row] = _audit(db_session, security_audit.STRATEGY_DELETED)
        assert event_row.user_id == confirmable.id
        assert event_row.owner_user_id == confirmable.id
        assert event_row.target_type == "strategy"
        assert event_row.target_id == str(sid)
        assert event_row.created_at is not None
        assert event_row.user_agent == "pytest-agent"
        assert event_row.details_json["status"] == "verified"

    def test_a_wrong_password_deletes_nothing_and_is_recorded(
            self, client, db_session, confirmable, verified_strategy):
        resp = _delete(client, verified_strategy.id, password="not-my-password")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "INVALID_PASSWORD"
        assert _count(db_session, m.Strategy, m.Strategy.id == verified_strategy.id) == 1
        [denied] = _audit(db_session, security_audit.STRATEGY_DELETE_DENIED)
        assert denied.target_id == str(verified_strategy.id)
        assert denied.details_json == {"reason": "invalid_password"}
        assert _audit(db_session, security_audit.STRATEGY_DELETED) == []

    def test_an_account_without_a_password_cannot_confirm(
            self, client, db_session, test_user, verified_strategy):
        assert test_user.password_hash is None
        assert _delete(client, verified_strategy.id).status_code == 403
        assert _count(db_session, m.Strategy, m.Strategy.id == verified_strategy.id) == 1

    def test_the_password_is_required(self, client, db_session, confirmable, verified_strategy):
        assert _delete(client, verified_strategy.id, password=None).status_code == 422
        assert _delete(client, verified_strategy.id, password="").status_code == 422
        assert _count(db_session, m.Strategy, m.Strategy.id == verified_strategy.id) == 1

    def test_unauthenticated_requests_are_refused(self, anon_client, verified_strategy):
        assert _delete(anon_client, verified_strategy.id).status_code == 401

    def test_another_accounts_strategy_is_a_404_and_untouched(
            self, client, db_session, confirmable, password_hash):
        stranger = m.User(email="stranger@example.com", email_verified=True,
                          password_hash=password_hash)
        db_session.add(stranger)
        db_session.flush()
        product = m.Product(user_id=stranger.id, name="Theirs", description="d",
                            type=m.ProductType.SKILL)
        db_session.add(product)
        db_session.flush()
        theirs = m.Strategy(product_id=product.id, flow_type=m.FlowType.NO_CLIENTS)
        db_session.add(theirs)
        db_session.commit()

        assert _delete(client, theirs.id).status_code == 404
        assert _count(db_session, m.Strategy, m.Strategy.id == theirs.id) == 1
        assert _audit(db_session, security_audit.STRATEGY_DELETE_DENIED) == []

    def test_an_unknown_id_is_a_404(self, client, confirmable):
        assert _delete(client, uuid.uuid4()).status_code == 404

    def test_a_live_campaign_must_be_paused_first(
            self, client, db_session, confirmable, verified_strategy):
        verified_strategy.status = m.StrategyStatus.EXECUTING
        verified_strategy.campaign_state = "active"
        db_session.commit()
        resp = _delete(client, verified_strategy.id)
        assert resp.status_code == 409
        assert "Pause the campaign" in resp.json()["detail"]
        assert _count(db_session, m.Strategy, m.Strategy.id == verified_strategy.id) == 1

        verified_strategy.campaign_state = "paused_manual"
        db_session.commit()
        assert _delete(client, verified_strategy.id).status_code == 200

    def test_password_attempts_are_rate_limited(
            self, client, db_session, confirmable, verified_strategy, monkeypatch):
        from app.core.config import settings as core_settings

        monkeypatch.setattr(core_settings, "RATE_LIMIT_AUTH", 2)
        assert _delete(client, verified_strategy.id, password="wrong-1").status_code == 403
        assert _delete(client, verified_strategy.id, password="wrong-2").status_code == 403
        assert _delete(client, verified_strategy.id).status_code == 429
        assert _count(db_session, m.Strategy, m.Strategy.id == verified_strategy.id) == 1


class TestWorkspaceMembers:
    @pytest.fixture()
    def workspace(self, db_session, confirmable, password_hash):
        ws = m.Workspace(name="Team", slug="team", owner_user_id=confirmable.id)
        db_session.add(ws)
        db_session.flush()
        people = {}
        for role in ("manager", "sdr"):
            person = m.User(email=f"{role}@example.com", email_verified=True,
                            password_hash=auth_svc.hash_password(f"{role}-own-password"))
            db_session.add(person)
            db_session.flush()
            db_session.add(m.WorkspaceMember(workspace_id=ws.id, user_id=person.id, role=role))
            people[role] = person
        db_session.commit()
        return ws, people

    def _as(self, person, ws):
        return {**auth_headers(person), "X-Workspace-Id": str(ws.id)}

    def test_a_manager_confirms_with_their_own_password_not_the_owners(
            self, client, db_session, workspace, verified_strategy):
        ws, people = workspace
        manager = people["manager"]
        owners = _delete(client, verified_strategy.id, PASSWORD, **self._as(manager, ws))
        assert owners.status_code == 403 and owners.json()["detail"] == "INVALID_PASSWORD"

        own = _delete(client, verified_strategy.id, "manager-own-password",
                      **self._as(manager, ws))
        assert own.status_code == 200, own.text
        [event_row] = _audit(db_session, security_audit.STRATEGY_DELETED)
        assert event_row.user_id == manager.id
        assert event_row.owner_user_id == ws.owner_user_id

    def test_an_sdr_cannot_delete(self, client, db_session, workspace, verified_strategy):
        ws, people = workspace
        resp = _delete(client, verified_strategy.id, "sdr-own-password",
                       **self._as(people["sdr"], ws))
        assert resp.status_code == 403
        assert _count(db_session, m.Strategy, m.Strategy.id == verified_strategy.id) == 1

"""GDPR -- an account can download everything it owns (Art. 15 / 20).

BEFORE: no route, service or task exported a `users` row or the data hanging
off it (BASELINE.md, "GDPR export / deletion for user accounts", HIGH). A
subject access request could only be met by hand in the database.

NOW: POST /me/data-export (password re-check) returns one JSON file built by
app/services/account_export.py. Pinned here:

  * COMPLETENESS -- every table in the schema is either exported through an
    ownership path or excluded with a reason, and every path is a real chain
    of foreign keys ending at users.id. A new table fails this file until
    someone decides which list it belongs on.
  * ISOLATION -- another account's rows never appear (each query is filtered
    by the requesting account's id).
  * NO CREDENTIALS -- password hash, OAuth ciphertexts, webhook secrets, token
    hashes, integration token values are redacted.
  * ACCESS -- wrong password 403 + audit row; personal API key refused;
    success writes an audit row.

Offline: SQLite, the real app, real auth.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from app.db import models as m
from app.db.base import Base
from app.services import account_export as ax
from app.services import api_keys
from app.services import auth as auth_svc
from app.services import crypto, security_audit
from tests.conftest import auth_headers

PASSWORD = "Export-me-1!"


# --------------------------------------------------------------------------
# Completeness of the ownership map
# --------------------------------------------------------------------------

class TestOwnershipMap:
    def test_every_table_is_exported_or_excluded_with_a_reason(self):
        tables = set(Base.metadata.tables)
        missing = sorted(tables - set(ax.OWNERSHIP) - set(ax.EXCLUDED))
        assert missing == [], (
            f"tables in neither OWNERSHIP nor EXCLUDED: {missing}. Add each to "
            "app/services/account_export.py: an ownership path if it can hold an "
            "account's data, else EXCLUDED with the reason.")

    def test_no_table_is_on_both_lists(self):
        assert set(ax.OWNERSHIP) & set(ax.EXCLUDED) == set()

    def test_exclusions_carry_a_reason(self):
        for name, reason in ax.EXCLUDED.items():
            assert reason.strip(), name

    @pytest.mark.parametrize("name", sorted(n for n, p in ax.OWNERSHIP.items() if p))
    def test_each_path_is_a_real_foreign_key_chain_ending_at_users(self, name):
        table = Base.metadata.tables[name]
        path = ax.OWNERSHIP[name]
        for hop in path[:-1]:
            parent = ax._fk_target(table, hop)
            assert parent is not None, f"{table.name}.{hop} has no foreign key"
            table = parent
        last = path[-1]
        assert last in table.c, f"{table.name}.{last} does not exist"
        if (table.name, last) in ax._PLAIN_USER_COLUMNS:
            return
        target = ax._fk_target(table, last)
        assert target is not None and target.name == "users", (
            f"{name}: path must end at a foreign key to users.id, ends at {table.name}.{last}")

    def test_paths_never_follow_an_actor_column(self):
        # Ownership is CASCADE from the owner. A SET NULL user column points at
        # someone who TOUCHED the row (author, approver), not its owner, except
        # for the append-only logs that outlive the account on purpose.
        set_null_ok = {"account_security_events", "api_usage", "attribution_entries",
                       "claim_verification_log", "compliance_audit_log", "consent_events"}
        # Decision E1 (migration 0081, docs/features/gdpr-erasure.md): billing
        # rows are kept when an account is erased, so their owner FK is
        # RESTRICT -- still the owner column, never an actor's.
        restrict_ok = {"billing_subscriptions", "billable_meetings"}
        for name, path in ax.OWNERSHIP.items():
            if len(path) != 1 or name in set_null_ok:
                continue
            table = Base.metadata.tables[name]
            expected = "RESTRICT" if name in restrict_ok else "CASCADE"
            for fk in table.c[path[0]].foreign_keys:
                assert fk.ondelete == expected, f"{name}.{path[0]} is {fk.ondelete}"


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

def _account(db, email):
    user = m.User(email=email, email_verified=True,
                  password_hash=auth_svc.hash_password(PASSWORD), full_name="Owner " + email)
    db.add(user)
    db.flush()
    product = m.Product(user_id=user.id, name=f"Product of {email}",
                        description="d", type=m.ProductType.SKILL)
    db.add(product)
    db.flush()
    strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.WITH_CLIENTS)
    db.add(strategy)
    db.flush()
    lead = m.Lead(strategy_id=strategy.id, source="apollo", external_id=uuid.uuid4().hex,
                  full_name=f"Prospect of {email}", email=f"prospect.{email}",
                  status=m.LeadStatus.VERIFIED)
    db.add(lead)
    db.flush()
    seq = m.Sequence(strategy_id=strategy.id, channel=m.ChannelType.EMAIL,
                     name=f"Seq of {email}", status=m.SequenceStatus.ACTIVE)
    db.add(seq)
    db.flush()
    db.add(m.Message(sequence_id=seq.id, lead_id=lead.id, step_no=1,
                     channel=m.ChannelType.EMAIL, template="t", subject=f"Hello from {email}",
                     body="body", unsubscribe_token=f"unsub-{uuid.uuid4().hex}"))
    db.add(m.GmailAccount(user_id=user.id, email_address=f"sender.{email}",
                          token_ciphertext=crypto.encrypt_json({"refresh_token": "rt-secret"}),
                          scopes="send"))
    db.add(m.IntegrationToken(user_id=user.id, provider="hubspot", value="plain-secret-value"))
    db.commit()
    return user


@pytest.fixture()
def alice(db_session):
    return _account(db_session, "alice@a.example")


@pytest.fixture()
def bob(db_session):
    return _account(db_session, "bob@b.example")


def _all_strings(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _all_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_strings(v)
    elif isinstance(obj, str):
        yield obj


class TestBuild:
    def test_own_rows_are_all_there(self, db_session, alice, bob):
        out = ax.build(db_session, alice.id)
        t = out["tables"]
        assert [u["email"] for u in t["users"]] == ["alice@a.example"]
        assert [p["name"] for p in t["products"]] == ["Product of alice@a.example"]
        assert len(t["strategies"]) == 1
        assert [lead["email"] for lead in t["leads"]] == ["prospect.alice@a.example"]
        assert [s["name"] for s in t["sequences"]] == ["Seq of alice@a.example"]
        assert [msg["subject"] for msg in t["messages"]] == ["Hello from alice@a.example"]
        assert [g["email_address"] for g in t["gmail_accounts"]] == ["sender.alice@a.example"]
        assert out["row_counts"]["leads"] == 1
        assert out["account_id"] == str(alice.id)

    def test_another_accounts_rows_never_appear(self, db_session, alice, bob):
        text = json.dumps(ax.build(db_session, alice.id))
        assert "bob@b.example" not in text
        assert str(bob.id) not in text

    def test_credentials_are_redacted(self, db_session, alice):
        out = ax.build(db_session, alice.id)
        t = out["tables"]
        assert t["users"][0]["password_hash"] == ax.REDACTED
        assert t["gmail_accounts"][0]["token_ciphertext"] == ax.REDACTED
        assert t["messages"][0]["unsubscribe_token"] == ax.REDACTED
        assert t["integration_tokens"][0]["value"] == ax.REDACTED
        strings = list(_all_strings(out))
        assert not any("plain-secret-value" in s or "rt-secret" in s for s in strings)
        assert alice.password_hash not in strings

    def test_every_owned_table_is_present_even_when_empty(self, db_session, alice):
        out = ax.build(db_session, alice.id)
        assert set(out["tables"]) == set(ax.OWNERSHIP)
        assert out["tables"]["calls"] == []

    def test_the_export_is_json_serialisable(self, db_session, alice):
        json.dumps(ax.build(db_session, alice.id))


# --------------------------------------------------------------------------
# Endpoint
# --------------------------------------------------------------------------

class TestEndpoint:
    def test_export_with_the_right_password(self, client, db_session, alice, bob):
        resp = client.post("/me/data-export", json={"password": PASSWORD},
                           headers=auth_headers(alice))
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("application/json")
        assert "attachment" in resp.headers["content-disposition"]
        assert resp.headers["cache-control"] == "no-store"
        body = resp.json()
        assert body["format"] == "leadpilot-account-export"
        assert body["tables"]["users"][0]["email"] == "alice@a.example"
        assert "bob@b.example" not in resp.text
        events = db_session.execute(select(m.SecurityAuditEvent).where(
            m.SecurityAuditEvent.action == security_audit.ACCOUNT_EXPORTED)).scalars().all()
        assert [e.user_id for e in events] == [alice.id]

    def test_wrong_password_is_refused_and_recorded(self, client, db_session, alice):
        resp = client.post("/me/data-export", json={"password": "wrong-one"},
                           headers=auth_headers(alice))
        assert resp.status_code == 403
        assert "tables" not in resp.text
        events = db_session.execute(select(m.SecurityAuditEvent).where(
            m.SecurityAuditEvent.action == security_audit.ACCOUNT_EXPORT_DENIED)).scalars().all()
        assert [e.user_id for e in events] == [alice.id]

    def test_personal_api_key_is_refused(self, client, db_session, alice):
        _, raw = api_keys.create(db_session, alice.id, "zapier")
        db_session.commit()
        resp = client.post("/me/data-export", json={"password": PASSWORD},
                           headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 403
        assert "API key" in resp.json()["detail"]

    def test_unauthenticated_is_refused(self, anon_client):
        resp = anon_client.post("/me/data-export", json={"password": PASSWORD})
        assert resp.status_code == 401

    def test_workspace_header_cannot_export_the_owners_data(self, client, db_session, alice, bob):
        # bob is a member of alice's workspace; /me is personal, so bob still
        # gets HIS data, never alice's.
        ws = m.Workspace(owner_user_id=alice.id, name="Alice Co", slug=f"alice-{uuid.uuid4().hex[:8]}")
        db_session.add(ws)
        db_session.flush()
        db_session.add(m.WorkspaceMember(workspace_id=ws.id, user_id=bob.id, role="manager"))
        db_session.commit()
        resp = client.post("/me/data-export", json={"password": PASSWORD},
                           headers={**auth_headers(bob), "X-Workspace-Id": str(ws.id)})
        assert resp.status_code == 200, resp.text
        assert resp.json()["account_id"] == str(bob.id)
        assert "prospect.alice@a.example" not in resp.text

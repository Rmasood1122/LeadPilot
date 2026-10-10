"""GDPR account export against REAL PostgreSQL.

tests/test_account_export.py covers the export on SQLite. The export runs 86
queries built from nested IN (SELECT id ...) subqueries over UUID columns and
returns rows full of JSON columns -- exactly what SQLite forgives and
PostgreSQL does not (see test_roi_postgres.py for the JSON-equality bug that
shipped that way). This runs the same build() on the dialect that ships.
"""

from __future__ import annotations

import json
import uuid

from app.db import models as m
from app.services import account_export as ax
from app.services import auth as auth_svc


def _account(db, tag):
    user = m.User(email=f"export-pg-{tag}-{uuid.uuid4().hex[:6]}@example.test",
                  email_verified=True, password_hash=auth_svc.hash_password("Pg-export-1!"),
                  theme_json={"preset": "dark"})
    db.add(user)
    db.flush()
    product = m.Product(user_id=user.id, name=f"Product {tag}", description="d",
                        type=m.ProductType.SKILL)
    db.add(product)
    db.flush()
    strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.WITH_CLIENTS,
                          market_signals_json={"signals": [{"title": f"news {tag}"}]})
    db.add(strategy)
    db.flush()
    lead = m.Lead(strategy_id=strategy.id, source="apollo", external_id=uuid.uuid4().hex,
                  full_name=f"Prospect {tag}", email=f"prospect-{tag}@example.test",
                  status=m.LeadStatus.VERIFIED, enrichment_json={"k": tag})
    db.add(lead)
    db.flush()
    seq = m.Sequence(strategy_id=strategy.id, channel=m.ChannelType.EMAIL,
                     name=f"Seq {tag}", status=m.SequenceStatus.ACTIVE)
    db.add(seq)
    db.flush()
    db.add(m.SequenceStep(sequence_id=seq.id, step_no=1, template="t", delay_days=0))
    db.add(m.Message(sequence_id=seq.id, lead_id=lead.id, step_no=1, template="t",
                     channel=m.ChannelType.EMAIL, subject=f"Hello {tag}", body="b",
                     unsubscribe_token=uuid.uuid4().hex))
    db.add(m.CrmNote(lead_id=lead.id, body=f"note {tag}"))
    db.commit()
    return user


def test_build_runs_on_postgres_and_stays_inside_the_account(db_session):
    alice = _account(db_session, "alice")
    bob = _account(db_session, "bob")

    out = ax.build(db_session, alice.id)
    text = json.dumps(out)  # every value serialisable from PG types (UUID, JSON, enums)

    t = out["tables"]
    assert set(t) == set(ax.OWNERSHIP)
    assert [u["email"] for u in t["users"]] == [alice.email]
    assert t["users"][0]["theme_json"] == {"preset": "dark"}
    assert t["users"][0]["password_hash"] == ax.REDACTED
    assert [lead["full_name"] for lead in t["leads"]] == ["Prospect alice"]
    assert t["leads"][0]["enrichment_json"] == {"k": "alice"}
    assert [s["step_no"] for s in t["sequence_steps"]] == [1]
    assert [msg["subject"] for msg in t["messages"]] == ["Hello alice"]
    assert t["messages"][0]["unsubscribe_token"] == ax.REDACTED
    assert [n["body"] for n in t["crm_notes"]] == ["note alice"]
    assert t["strategies"][0]["market_signals_json"]["signals"][0]["title"] == "news alice"

    assert bob.email not in text and str(bob.id) not in text
    assert "Prospect bob" not in text and "note bob" not in text

"""Where adapters run: the model client swap and an in-memory database.

use_client(client) points every get_client() the app can reach at `client`
-- the gateway's own function and every module that imported it by name --
and restores them afterwards. It is how a ReplayClient (offline) or a live
client (evals/ai/live_eval.py) reaches the real app code unchanged.

fresh_session() is an in-memory SQLite database with every table, the same
setup as the offline test suite (tests/conftest.py db_session), plus
seed helpers for the records adapters need. Everything synthetic; no real
personal data (program rule).
"""

from __future__ import annotations

import sys
import uuid
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@contextmanager
def use_client(client: Any):
    from app.services import anthropic_client  # noqa: PLC0415

    original = anthropic_client.get_client
    patched: list[tuple[object, str]] = []
    for module in list(sys.modules.values()):
        if module is None:
            continue
        try:
            if getattr(module, "get_client", None) is original:
                patched.append((module, "get_client"))
        except Exception:  # noqa: BLE001 -- lazy modules can raise on getattr
            continue
    try:
        for module, name in patched:
            setattr(module, name, lambda: client)
        yield client
    finally:
        for module, name in patched:
            setattr(module, name, original)


def fresh_session():
    from app.db import models  # noqa: F401,PLC0415 -- registers every table
    from app.db.base import Base  # noqa: PLC0415

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def seed_account(db, *, email: str | None = None, product_name: str = "Brightline Bookkeeping",
                 description: str = "Monthly bookkeeping and payroll for small UK agencies.",
                 pattern_key: str | None = None):
    """A user, one product and one strategy. Returns (user, product, strategy)."""
    from app.db import models as m  # noqa: PLC0415

    user = m.User(email=email or f"owner-{uuid.uuid4().hex[:8]}@example.test", email_verified=True)
    db.add(user)
    db.flush()
    product = m.Product(user_id=user.id, name=product_name, description=description,
                        type=m.ProductType.SKILL)
    db.add(product)
    db.flush()
    strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.NO_CLIENTS,
                          pattern_key=pattern_key)
    db.add(strategy)
    db.flush()
    return user, product, strategy


def seed_lead(db, strategy, **fields):
    from app.db import models as m  # noqa: PLC0415

    base = {"source": "manual", "external_id": uuid.uuid4().hex[:12],
            "full_name": "Dana Whitfield", "title": "Founder", "company": "Northwind Studio",
            "email": f"dana-{uuid.uuid4().hex[:6]}@northwind.example"}
    base.update(fields)
    lead = m.Lead(strategy_id=strategy.id, **base)
    db.add(lead)
    db.flush()
    return lead

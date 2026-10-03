"""Feature 6 — anonymised benchmarks.

GET /benchmarks?strategy_id=   your rates next to the published benchmark
                               buckets for that campaign's industry and for
                               all industries, per channel

`/benchmarks`, not `/api/benchmarks` as the brief spelled it: no route in this
API carries an /api prefix (tests/test_config_paths_match_routes.py exists
because a config once pointed at one). A campaign that is not yours is a 404.
"""

# No `from __future__ import annotations` -- see the note in app/api/crm.py.

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.analytics import _owned_strategy
from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import User
from app.services import benchmarks

router = APIRouter(tags=["benchmarks"])


@router.get("/benchmarks")
def get_benchmarks(
    strategy_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    strategy = (_owned_strategy(strategy_id, db, current_user)
                if strategy_id is not None else None)
    return benchmarks.comparison(db, current_user, strategy)

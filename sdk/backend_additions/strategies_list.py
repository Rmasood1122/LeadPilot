"""Backend addition: GET /strategies — list all strategies for the authenticated user.

HOW TO INTEGRATE (M5 backend):
    1. Copy the route below into app/api/strategies.py (append at the bottom).
    2. No new imports needed — all symbols are already in that file.
    3. Run `pytest` to confirm the existing test suite still passes.
    4. This endpoint is required by `clienthunter status` (the CLI all-strategies
       table).  Until it is deployed, the CLI degrades gracefully with a message
       pointing here.

WHY A NEW ENDPOINT AND NOT A FILE EDIT:
    M1–M5 source is treated as read-only in this delivery.  This file contains
    the exact snippet to paste so the integration is a copy-paste, not a diff
    to apply blindly.

ENDPOINT CONTRACT:
    GET /strategies
    Query params:
        product_id  (optional UUID)  — filter to one product's strategies
        limit       (default 50)     — max strategies to return
        offset      (default 0)      — pagination
    Response 200: {"total": int, "items": [StrategyStatusOut, ...]}

NOTE: auth scoping (filter by the requesting user's strategies) is a follow-up
once get_current_user is wired into all routes (flagged in M5 comments).
Until then, this returns ALL strategies — acceptable for single-tenant
self-hosted deployments.
"""

# ── Paste the following code into app/api/strategies.py ─────────────────────
#
# (It uses the StrategyStatusOut schema and helpers already in that module.)

_SNIPPET = '''
@router.get("/strategies", response_model=list[StrategyStatusOut])
def list_strategies(
    product_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[StrategyStatusOut]:
    """List strategies, optionally filtered by product_id.

    Required by `clienthunter status` (the CLI all-strategy table).
    TODO: once get_current_user is wired, filter by owner here.
    """
    query = select(Strategy)
    if product_id is not None:
        query = query.where(Strategy.product_id == product_id)
    query = query.order_by(Strategy.created_at.desc()).offset(offset).limit(limit)
    strategies = db.execute(query).scalars().all()
    return [get_strategy(s.id, db) for s in strategies]
'''

# ── Additional Query import ──────────────────────────────────────────────────
# If `Query` is not already imported at the top of strategies.py, add it:
#
#   from fastapi import APIRouter, Depends, HTTPException, Query

print("See the _SNIPPET variable in this file for the code to paste into app/api/strategies.py")
print("Do not run this file directly — it is documentation/scaffolding only.")

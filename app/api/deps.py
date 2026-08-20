"""Shared FastAPI dependencies for M8+ routers.

get_current_user — canonical JWT dependency (delegates to app.services.auth,
                   the M5 implementation used across the whole API).
require_admin    — get_current_user + users.is_admin gate (column added in
                   migration 0009_m8c3).
"""
from __future__ import annotations

from fastapi import Depends, HTTPException

from app.services.auth import get_current_user  # canonical implementation
from app.db.models import User

__all__ = ["get_current_user", "require_admin"]


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not bool(getattr(current_user, "is_admin", False)):
        raise HTTPException(status_code=403, detail="admin privileges required")
    if bool(getattr(current_user, "is_suspended", False)):
        raise HTTPException(status_code=403, detail="account suspended")
    return current_user

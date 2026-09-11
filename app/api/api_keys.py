"""Personal API keys (Feature Group 4).

GET    /me/api-keys          the user's keys (never the key itself)
POST   /me/api-keys          {"name": "Zapier"} -> 201, the key is returned ONCE
DELETE /me/api-keys/{id}     revoke -> 204
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import ApiKey, User
from app.services import api_keys

router = APIRouter(prefix="/me/api-keys", tags=["api-keys"])


class KeyIn(BaseModel):
    name: str = Field(default="API key", min_length=1, max_length=100)


@router.get("")
def list_keys(db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)) -> list[dict]:
    rows = db.execute(select(ApiKey).where(ApiKey.user_id == current_user.id)
                      .order_by(ApiKey.created_at.desc())).scalars().all()
    return [api_keys.out(r) for r in rows]


@router.post("", status_code=201)
def create_key(body: KeyIn, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)) -> dict:
    enforce_rate_limit(str(current_user.id), "api_key_create", "RATE_LIMIT_AI_ACTION")
    try:
        row, plaintext = api_keys.create(db, current_user.id, body.name)
    except api_keys.ApiKeyLimit as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {**api_keys.out(row), "key": plaintext}


@router.delete("/{key_id}", status_code=204)
def revoke_key(key_id: uuid.UUID, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)) -> Response:
    if not api_keys.revoke(db, current_user.id, key_id):
        raise HTTPException(status_code=404, detail="API key not found")
    return Response(status_code=204)

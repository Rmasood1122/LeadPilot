"""GDPR account data -- the account holder's right of access (Art. 15 / 20).

POST /me/data-export   {"password": "..."} -> a JSON file of every row this
                       account owns (app/services/account_export.py).

WHY POST WITH A PASSWORD. The file holds every prospect, message and meeting
note in the account. A stolen access token must not be enough to walk off with
all of it in one request, so the signed-in person re-types their password, the
same rule as deleting a strategy. A personal API key (Zapier, scripts) is
refused outright: a takeout of the whole account is a person's act.

WHOSE DATA. /me is a personal route (app/services/rbac.py), so the workspace
header is ignored and current_user is always the person who signed in: a
workspace member exports their own account, never the owner's.

AUDIT. Every export and every refused attempt writes a security_audit_events
row, committed before the response leaves.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limiting import AUTH_WINDOW_SECONDS, enforce_rate_limit
from app.db.base import get_db
from app.db.models import User
from app.services import account_export
from app.services import auth as auth_svc
from app.services import security_audit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["account"])

INVALID_PASSWORD = "INVALID_PASSWORD"
API_KEY_REFUSED = ("A data export needs you to sign in; a personal API key "
                   "cannot download the whole account.")


class DataExportIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


@router.post("/me/data-export")
def export_my_data(body: DataExportIn, request: Request,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)) -> Response:
    """Download everything this account owns as one JSON file.

    ORDER. API-key refusal, then the rate limit (its own bucket, shared limit
    and window with login, so mistyping here cannot lock anyone out of
    signing in), then the password, then the export.
    """
    if getattr(request.state, "auth_via", None) == "api_key":
        raise HTTPException(status_code=403, detail=API_KEY_REFUSED)
    enforce_rate_limit(f"acct:{current_user.id}", "password_confirm", "RATE_LIMIT_AUTH",
                       AUTH_WINDOW_SECONDS)

    if not auth_svc.verify_password(body.password, current_user.password_hash):
        security_audit.record(
            db, action=security_audit.ACCOUNT_EXPORT_DENIED, request=request,
            user_id=current_user.id, target_type="account", target_id=current_user.id,
            details={"reason": "invalid_password"})
        db.commit()
        raise HTTPException(status_code=403, detail=INVALID_PASSWORD)

    payload = account_export.build(db, current_user.id)
    security_audit.record(
        db, action=security_audit.ACCOUNT_EXPORTED, request=request,
        user_id=current_user.id, target_type="account", target_id=current_user.id,
        details={"format_version": payload["format_version"],
                 "rows": sum(payload["row_counts"].values())})
    db.commit()
    logger.info("account %s exported its data (%d rows)", current_user.id,
                sum(payload["row_counts"].values()))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=1),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="leadpilot-account-export-{stamp}.json"',
            "Cache-Control": "no-store",
        },
    )

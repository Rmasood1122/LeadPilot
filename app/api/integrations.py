"""Integration endpoints — Gmail OAuth connect flow (M3 Chunk 1)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import GmailAccount, User
from app.integrations.gmail import get_oauth, make_state, parse_state, store_tokens

router = APIRouter(prefix="/integrations/gmail", tags=["integrations"])


@router.get("/auth-url")
def gmail_auth_url(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Step 1: the client opens this URL in a browser to grant access.

    Owner is the authenticated user (JWT) — the old user_email query param
    (which let anyone request an auth URL, and silently auto-created a
    User row, for ANY email address without proving they owned it) is
    removed.
    """
    state = make_state(current_user.id)
    return {"auth_url": get_oauth().build_auth_url(state), "state": state}


@router.get("/callback")
def gmail_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Step 2: Google redirects here; we exchange the code and store
    ENCRYPTED tokens. Never logs or returns the tokens themselves.

    No get_current_user dependency here on purpose — Google's redirect is
    a plain browser navigation with no Authorization header. The signed,
    encrypted `state` value (created in gmail_auth_url from the JWT
    holder's id) is what proves which user this callback belongs to —
    tamper it and parse_state raises, so this is not an auth bypass.
    """
    if error:
        raise HTTPException(status_code=400, detail=f"Google returned an error: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing code or state")

    try:
        user_id = parse_state(state)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid or tampered state")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user for this state not found")

    oauth = get_oauth()
    try:
        tokens = oauth.exchange_code(code)
    except Exception:
        raise HTTPException(status_code=502, detail="token exchange with Google failed")

    account = store_tokens(db, user, tokens, oauth=oauth)
    return {
        "connected": True,
        "email_address": account.email_address,
        "scopes": account.scopes,
    }


@router.get("/status")
def gmail_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Owner is the authenticated user (JWT) — the old user_email query
    param let anyone probe ANY email's Gmail-connection status/scopes/
    token expiry without authentication. Removed."""
    account = db.execute(
        select(GmailAccount).where(GmailAccount.user_id == current_user.id)
    ).scalar_one_or_none()
    if account is None:
        return {"connected": False}
    return {
        "connected": True,
        "email_address": account.email_address,
        "scopes": account.scopes,
        "token_expires_at": account.token_expires_at,
    }
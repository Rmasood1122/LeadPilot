"""Integration endpoints — Gmail OAuth connect flow (M3 Chunk 1)."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import GmailAccount, User
from app.integrations.gmail import (GmailNotConnected, get_oauth, make_state, parse_state,
                                    store_tokens)

logger = logging.getLogger(__name__)

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
    # Without a client id Google answers "Missing required parameter: client_id"
    # on its own page, which tells the user nothing. Say what is missing here.
    from app.config import settings  # noqa: PLC0415

    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=503,
            detail="Gmail is not configured on the server: set GOOGLE_CLIENT_ID, "
                   "GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI.",
        )
    state = make_state(current_user.id)
    return {"auth_url": get_oauth().build_auth_url(state), "state": state}


@router.get("/callback", include_in_schema=False)
def gmail_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Step 2: Google redirects here; we exchange the code and store
    ENCRYPTED tokens. Never logs or returns the tokens themselves.

    No get_current_user dependency here on purpose — Google's redirect is
    a plain browser navigation with no Authorization header. The signed,
    encrypted `state` value (created in gmail_auth_url from the JWT
    holder's id) is what proves which user this callback belongs to —
    tamper it and parse_state raises, so this is not an auth bypass.

    Product defect #16: this is a browser tab, so every outcome redirects to
    /settings?tab=integrations&gmail=connected|error[&reason=...] like the
    Slack / HubSpot / Salesforce callbacks, instead of showing raw JSON.
    """
    from app.api.crm_integrations import frontend_redirect  # noqa: PLC0415

    if error:
        return frontend_redirect("gmail", "error", f"Google returned an error: {error}")
    if not code or not state:
        return frontend_redirect("gmail", "error", "missing code or state")

    try:
        user_id = parse_state(state)
    except ValueError:
        return frontend_redirect("gmail", "error", "invalid or tampered state")

    user = db.get(User, user_id)
    if user is None:
        return frontend_redirect("gmail", "error", "user for this state not found")

    oauth = get_oauth()
    try:
        tokens = oauth.exchange_code(code)
    except Exception:
        logger.warning("gmail token exchange failed for user %s", user_id)
        return frontend_redirect("gmail", "error", "token exchange with Google failed")

    try:
        store_tokens(db, user, tokens, oauth=oauth)
    except GmailNotConnected as exc:
        return frontend_redirect("gmail", "error", str(exc))
    except Exception:  # noqa: BLE001 -- review L6: never a 500 page in the user's tab
        db.rollback()
        logger.exception("storing Gmail tokens failed for user %s", user_id)
        return frontend_redirect("gmail", "error", "could not save the Gmail connection")
    return frontend_redirect("gmail", "connected")


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
    from app.integrations.google_meet import calendar_scope_state  # noqa: PLC0415

    if account is None:
        return {"connected": False, "calendar_access": "not_connected"}
    return {
        "connected": True,
        "email_address": account.email_address,
        "scopes": account.scopes,
        "token_expires_at": account.token_expires_at,
        "calendar_access": calendar_scope_state(account),
    }
"""OAuth 2.1 endpoints for the Claude / ChatGPT connector.

Every rule lives in app/services/oauth_server.py; this module only speaks
HTTP. All of it answers 404 while MCP_ENABLED is false, like /mcp itself.

  GET  /.well-known/oauth-authorization-server   RFC 8414 metadata
  POST /oauth/register                           RFC 7591 DCR (JSON)
  GET  /oauth/authorize                          -> consent page or client
  GET  /oauth/requests/{id}                      consent page reads (signed in)
  POST /oauth/requests/{id}/decision             consent page answers (signed in)
  POST /oauth/token                              form-urlencoded; code / refresh
  POST /oauth/revoke                             RFC 7009

Claude's limits: discovery, registration and token must answer within 10 s,
refresh within 30 s. Nothing here waits on anything but the database.
Responses carrying tokens are `Cache-Control: no-store`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.core.rate_limiting import client_ip, enforce_rate_limit
from app.db.base import get_db
from app.db.models import User
from app.services import oauth_server
from app.services.oauth_server import OAuthError

router = APIRouter(tags=["oauth"])

NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}
RATE_WINDOW_SECONDS = 3600


def _require_enabled() -> None:
    if not settings.mcp_enabled:
        raise HTTPException(status_code=404, detail="Not Found")


def _error(exc: OAuthError) -> JSONResponse:
    headers = dict(NO_STORE)
    if exc.status == 401:
        headers["WWW-Authenticate"] = 'Bearer error="invalid_client"'
    return JSONResponse(exc.body(), status_code=exc.status, headers=headers)


def _consent_error(exc: OAuthError) -> JSONResponse:
    """The consent page's errors also carry `detail`, which the web app's
    API client shows to the person."""
    return JSONResponse({**exc.body(), "detail": exc.description}, status_code=exc.status,
                        headers=NO_STORE)


def _person(request: Request, user: User) -> User:
    """The signed-in person, never a workspace owner, and never an API key:
    consent is a human decision (CONN-WORKSPACE)."""
    if getattr(request.state, "auth_via", None) == "api_key":
        raise HTTPException(status_code=403,
                            detail="connector consent does not accept API keys")
    return getattr(request.state, "actor", None) or user


@router.get("/.well-known/oauth-authorization-server")
def authorization_server_metadata() -> JSONResponse:
    _require_enabled()
    return JSONResponse(oauth_server.metadata())


@router.post("/oauth/register", status_code=201)
async def register(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    _require_enabled()
    enforce_rate_limit(f"ip:{client_ip(request)}", "oauth_register", "RATE_LIMIT_OAUTH",
                       window_seconds=RATE_WINDOW_SECONDS)
    try:
        body = await request.json()
    except ValueError:
        return _error(OAuthError("invalid_client_metadata", "the body must be JSON"))
    try:
        client = await run_in_threadpool(oauth_server.register_client, db, body)
    except OAuthError as exc:
        return _error(exc)
    return JSONResponse(oauth_server.client_info(client), status_code=201, headers=NO_STORE)


@router.get("/oauth/authorize")
def authorize(request: Request, db: Session = Depends(get_db)):
    _require_enabled()
    enforce_rate_limit(f"ip:{client_ip(request)}", "oauth_authorize", "RATE_LIMIT_OAUTH",
                       window_seconds=RATE_WINDOW_SECONDS)
    params = dict(request.query_params)
    try:
        row = oauth_server.start_authorization(db, params)
    except OAuthError as exc:
        if exc.redirectable:
            return RedirectResponse(oauth_server.redirect_with(params["redirect_uri"], {
                "error": exc.error, "error_description": exc.description,
                "state": params.get("state")}), status_code=302)
        return _error(exc)
    return RedirectResponse(oauth_server.consent_url(row), status_code=302)


class DecisionIn(BaseModel):
    approve: bool


@router.get("/oauth/requests/{request_id}")
def consent_request(request_id: str, request: Request, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)) -> JSONResponse:
    _require_enabled()
    _person(request, current_user)
    try:
        row, client = oauth_server.pending_request(db, request_id)
    except OAuthError as exc:
        return _consent_error(exc)
    return JSONResponse(oauth_server.describe(row, client), headers=NO_STORE)


@router.post("/oauth/requests/{request_id}/decision")
def consent_decision(request_id: str, body: DecisionIn, request: Request,
                     db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)) -> JSONResponse:
    _require_enabled()
    person = _person(request, current_user)
    try:
        target = oauth_server.decide(db, request_id, person, approve=body.approve,
                                     request=request)
    except OAuthError as exc:
        return _consent_error(exc)
    # The code goes to the browser in this JSON and from there to the
    # client's redirect URI -- never into a log or this API's own URLs.
    return JSONResponse({"redirect_to": target}, headers=NO_STORE)


@router.post("/oauth/token")
def token(request: Request, db: Session = Depends(get_db),
          grant_type: str | None = Form(None), code: str | None = Form(None),
          redirect_uri: str | None = Form(None), code_verifier: str | None = Form(None),
          client_id: str | None = Form(None), refresh_token: str | None = Form(None),
          scope: str | None = Form(None), resource: str | None = Form(None)) -> JSONResponse:
    _require_enabled()
    form = {"grant_type": grant_type, "code": code, "redirect_uri": redirect_uri,
            "code_verifier": code_verifier, "client_id": client_id,
            "refresh_token": refresh_token, "scope": scope, "resource": resource}
    try:
        tokens = oauth_server.token(db, form, request=request)
    except OAuthError as exc:
        return _error(exc)
    return JSONResponse(tokens.response(), headers=NO_STORE)


@router.post("/oauth/revoke")
def revoke(request: Request, db: Session = Depends(get_db),
           token: str | None = Form(None), client_id: str | None = Form(None),
           token_type_hint: str | None = Form(None)) -> JSONResponse:
    _require_enabled()
    oauth_server.revoke(db, {"token": token, "client_id": client_id}, request=request)
    return JSONResponse({}, headers=NO_STORE)

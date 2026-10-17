"""OAuth 2.1 authorization server for the Claude / ChatGPT connector.

Decision: docs/program/DECISIONS.md CONN-AS. Spec: docs/features/mcp-connector.md.
The HTTP surface is app/api/oauth.py; this module holds every rule.

WHO THE CLIENTS ARE. Claude registers itself by Dynamic Client Registration
(RFC 7591) and always sends PKCE S256; its hosted apps redirect to
https://claude.ai/api/mcp/auth_callback and Claude Code to
http://localhost:<port>/callback or http://127.0.0.1:<port>/callback (an
ephemeral port per session, RFC 8252 §7.3). ChatGPT redirects to
https://chatgpt.com/connector_platform_oauth_redirect -- the stable URI it
uses only for servers that return `iss` in every authorization response and
advertise authorization_response_iss_parameter_supported (RFC 9207), which
this server does. No other redirect URI can be registered.

WHAT A TOKEN IS. A connector session in auth_sessions (oauth_client_id,
scope), so rotation, reuse detection and revocation are the same code as web
sign-in (auth_sessions.start_connector_session / rotate_connector). Access
tokens are audience-bound JWTs (`aud` = the MCP URL). Public clients only:
no client secrets exist, PKCE is the proof of possession.

WHAT NEVER HAPPENS. No token, code or verifier is logged or stored in clear
(codes are SHA-256 hashed). No token travels in a URL: the authorization
code does, as OAuth requires, single-use and two minutes long.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit

from fastapi import Request
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import AuthSession, OAuthAuthorizationCode, OAuthClient, User
from app.services import auth as auth_svc
from app.services import auth_sessions, security_audit

logger = logging.getLogger(__name__)

# Kept in step with app/mcp/scopes.py (that module imports the MCP SDK; this
# one is imported by the REST app and must not).
SCOPE_READ = "leadpilot:read"
SCOPE_WRITE = "leadpilot:write"
SCOPE_OFFLINE = auth_sessions.OFFLINE_ACCESS
SUPPORTED_SCOPES = (SCOPE_READ, SCOPE_WRITE, SCOPE_OFFLINE)

SCOPE_DESCRIPTIONS = {
    SCOPE_READ: "See your leads, F-P-T-A scores, strategies, outreach messages, "
                "replies, attribution and claim checks.",
    SCOPE_WRITE: "Create strategies (which start paid AI research within your plan "
                 "and spend limits) and pause or resume campaigns. It cannot send "
                 "or schedule messages.",
    SCOPE_OFFLINE: "Stay connected without signing in again, until you disconnect "
                   "or 30 days pass without use.",
}

CLAUDE_CALLBACK = "https://claude.ai/api/mcp/auth_callback"
CHATGPT_CALLBACK = "https://chatgpt.com/connector_platform_oauth_redirect"
EXACT_REDIRECTS = frozenset({CLAUDE_CALLBACK, CHATGPT_CALLBACK})
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1"})
LOOPBACK_PATH = "/callback"
MAX_REDIRECT_URIS = 5

REQUEST_TTL = timedelta(minutes=10)
CODE_TTL = timedelta(minutes=2)
# Finished or abandoned authorize requests are deleted this long after they
# expire (whenever a new one is created).
PURGE_AFTER = timedelta(days=1)

GRANT_AUTHORIZATION_CODE = "authorization_code"
GRANT_REFRESH_TOKEN = "refresh_token"

_PKCE_VALUE = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")

APPROVED = "approved"
DENIED = "denied"


class OAuthError(Exception):
    """An OAuth error answer. `redirectable` = may be sent to the client's
    redirect URI (only once that URI has been validated)."""

    def __init__(self, error: str, description: str, *, status: int = 400,
                 redirectable: bool = False):
        super().__init__(description)
        self.error = error
        self.description = description
        self.status = status
        self.redirectable = redirectable

    def body(self) -> dict:
        return {"error": self.error, "error_description": self.description}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# --------------------------------------------------------------------------
# Metadata
# --------------------------------------------------------------------------


def issuer() -> str:
    return settings.mcp_issuer


def metadata() -> dict:
    """RFC 8414 authorization server metadata."""
    base = issuer()
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "revocation_endpoint": f"{base}/oauth/revoke",
        "scopes_supported": list(SUPPORTED_SCOPES),
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": [GRANT_AUTHORIZATION_CODE, GRANT_REFRESH_TOKEN],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "revocation_endpoint_auth_methods_supported": ["none"],
        "authorization_response_iss_parameter_supported": True,
    }


# --------------------------------------------------------------------------
# Redirect URIs
# --------------------------------------------------------------------------


def _loopback(uri: str):
    """The parsed URI if it is an http loopback /callback URI, else None."""
    try:
        parts = urlsplit(uri)
        port = parts.port  # raises ValueError on a non-numeric port
    except ValueError:
        return None
    if (parts.scheme != "http" or parts.hostname not in LOOPBACK_HOSTS
            or parts.path != LOOPBACK_PATH or parts.query or parts.fragment
            or parts.username or parts.password):
        return None
    if port is not None and not 0 < port < 65536:
        return None
    return parts


def redirect_uri_allowed(uri: str) -> bool:
    return isinstance(uri, str) and (uri in EXACT_REDIRECTS or _loopback(uri) is not None)


def redirect_uri_matches(registered: str, presented: str) -> bool:
    """Exact match, except that a loopback URI's port is ignored (RFC 8252
    §7.3): Claude Code registers once and listens on a new port each time."""
    if presented == registered:
        return True
    a, b = _loopback(registered), _loopback(presented)
    return (a is not None and b is not None and a.hostname == b.hostname
            and a.path == b.path)


def _registered_match(client: OAuthClient, presented: str | None) -> bool:
    return bool(presented) and any(redirect_uri_matches(r, presented)
                                   for r in (client.redirect_uris or []))


# --------------------------------------------------------------------------
# Registration (RFC 7591)
# --------------------------------------------------------------------------


def register_client(db: Session, body) -> OAuthClient:
    if not isinstance(body, dict):
        raise OAuthError("invalid_client_metadata", "the body must be a JSON object")
    uris = body.get("redirect_uris")
    if (not isinstance(uris, list) or not uris or len(uris) > MAX_REDIRECT_URIS
            or not all(isinstance(u, str) for u in uris)):
        raise OAuthError("invalid_redirect_uri",
                         f"redirect_uris must be a list of 1-{MAX_REDIRECT_URIS} URIs")
    refused = [u for u in uris if not redirect_uri_allowed(u)]
    if refused:
        raise OAuthError(
            "invalid_redirect_uri",
            "redirect URI not allowed: " + refused[0][:200] + ". Allowed: "
            f"{CLAUDE_CALLBACK}, {CHATGPT_CALLBACK}, http://localhost/callback or "
            "http://127.0.0.1/callback (any port).")
    grants = body.get("grant_types") or [GRANT_AUTHORIZATION_CODE, GRANT_REFRESH_TOKEN]
    if not isinstance(grants, list) or not set(grants) <= {GRANT_AUTHORIZATION_CODE,
                                                            GRANT_REFRESH_TOKEN}:
        raise OAuthError("invalid_client_metadata",
                         "grant_types may only contain authorization_code and refresh_token")
    responses = body.get("response_types") or ["code"]
    if not isinstance(responses, list) or set(responses) != {"code"}:
        raise OAuthError("invalid_client_metadata", 'response_types must be ["code"]')
    requested = body.get("scope")
    if requested is not None and not isinstance(requested, str):
        raise OAuthError("invalid_client_metadata", "scope must be a space-separated string")
    scopes = (requested or " ".join(SUPPORTED_SCOPES)).split()
    unknown = [s for s in scopes if s not in SUPPORTED_SCOPES]
    if unknown:
        raise OAuthError("invalid_client_metadata", f"unknown scope: {unknown[0][:60]}")
    name = body.get("client_name")
    client = OAuthClient(
        client_id="lpc_" + secrets.token_urlsafe(24),
        client_name=(name.strip()[:200] or None) if isinstance(name, str) else None,
        redirect_uris=list(dict.fromkeys(uris)),
        scope=" ".join(s for s in SUPPORTED_SCOPES if s in scopes),
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    logger.info("oauth: registered client %s (%s)", client.client_id, client.client_name)
    return client


def client_info(client: OAuthClient) -> dict:
    """RFC 7591 §3.2.1 response. token_endpoint_auth_method is always
    "none" -- public clients only -- whatever the request asked for."""
    issued = _aware(client.created_at) or _now()
    return {
        "client_id": client.client_id,
        "client_id_issued_at": int(issued.timestamp()),
        "client_name": client.client_name,
        "redirect_uris": client.redirect_uris,
        "grant_types": [GRANT_AUTHORIZATION_CODE, GRANT_REFRESH_TOKEN],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": client.scope,
    }


def _client(db: Session, client_id: str | None) -> OAuthClient | None:
    if not client_id or len(client_id) > 100:
        return None
    return db.execute(select(OAuthClient).where(OAuthClient.client_id == client_id)
                      ).scalar_one_or_none()


# --------------------------------------------------------------------------
# Authorization endpoint
# --------------------------------------------------------------------------


def redirect_with(uri: str, params: dict) -> str:
    """`uri` plus query parameters, always including `iss` (RFC 9207)."""
    query = urlencode({k: v for k, v in {**params, "iss": issuer()}.items() if v is not None})
    return f"{uri}{'&' if urlsplit(uri).query else '?'}{query}"


def start_authorization(db: Session, params: dict) -> OAuthAuthorizationCode:
    """Validate an /oauth/authorize request and record it pending consent.

    Until client and redirect URI are validated, an error is answered to the
    browser (never redirected: that would make this an open redirector);
    after, it is redirected to the client with `state` and `iss`.
    """
    client = _client(db, params.get("client_id"))
    if client is None:
        raise OAuthError("invalid_request", "unknown client_id")
    redirect_uri = params.get("redirect_uri")
    if not _registered_match(client, redirect_uri):
        raise OAuthError("invalid_request", "redirect_uri is not registered for this client")

    def fail(error: str, description: str) -> OAuthError:
        return OAuthError(error, description, redirectable=True)

    if params.get("response_type") != "code":
        raise fail("unsupported_response_type", 'response_type must be "code"')
    challenge = params.get("code_challenge") or ""
    if params.get("code_challenge_method") != "S256" or not _PKCE_VALUE.match(challenge):
        raise fail("invalid_request", "PKCE is required: code_challenge with "
                                      "code_challenge_method=S256")
    resource = params.get("resource")
    if resource and resource != settings.mcp_resource:
        raise fail("invalid_target", f"resource must be {settings.mcp_resource}")
    requested = (params.get("scope") or "").split()
    unknown = [s for s in requested if s not in SUPPORTED_SCOPES]
    if unknown:
        raise fail("invalid_scope", f"unknown scope: {unknown[0][:60]}")
    allowed = set(client.scope.split())
    if not set(requested) <= allowed:
        raise fail("invalid_scope", "scope exceeds what this client registered")
    # Read is what every connection is for; without a requested scope the
    # grant is the least that works (read, plus staying connected when the
    # client registered for it).
    granted = set(requested) or ({SCOPE_READ, SCOPE_OFFLINE} & allowed)
    granted.add(SCOPE_READ)
    state = params.get("state")
    if state is not None and len(state) > 500:
        raise fail("invalid_request", "state is longer than 500 characters")

    now = _now()
    db.execute(delete(OAuthAuthorizationCode)
               .where(OAuthAuthorizationCode.expires_at < now - PURGE_AFTER)
               .execution_options(synchronize_session=False))
    row = OAuthAuthorizationCode(
        client_id=client.client_id, redirect_uri=redirect_uri,
        scope=" ".join(s for s in SUPPORTED_SCOPES if s in granted),
        code_challenge=challenge, state=state, expires_at=now + REQUEST_TTL,
    )
    db.add(row)
    db.commit()
    return row


def consent_url(row: OAuthAuthorizationCode) -> str:
    """Where the browser goes to sign in and approve. The id is an opaque
    reference to a pending request, not a credential: acting on it needs
    the person's own signed-in session."""
    # Trailing slash: the web app is a static export with trailingSlash
    # (frontend/next.config.*), so the page is served at /oauth/consent/.
    return f"{settings.frontend_url.rstrip('/')}/oauth/consent/?request={row.id}"


def pending_request(db: Session, request_id) -> tuple[OAuthAuthorizationCode, OAuthClient]:
    try:
        row = db.get(OAuthAuthorizationCode, uuid.UUID(str(request_id)))
    except ValueError:
        row = None
    if row is None:
        raise OAuthError("not_found", "this authorization request does not exist", status=404)
    if row.decision is not None:
        raise OAuthError("already_decided", "this authorization request was already answered",
                         status=409)
    if _aware(row.expires_at) <= _now():
        raise OAuthError("expired", "this authorization request has expired; start the "
                                    "connection again from Claude or ChatGPT", status=410)
    client = _client(db, row.client_id)
    if client is None:
        raise OAuthError("not_found", "this authorization request does not exist", status=404)
    return row, client


def describe(row: OAuthAuthorizationCode, client: OAuthClient) -> dict:
    """What the consent page shows."""
    parts = urlsplit(row.redirect_uri)
    return {
        "request_id": str(row.id),
        "client_name": client.client_name,
        "redirect_uri": row.redirect_uri,
        "redirect_host": parts.hostname,
        "scopes": [{"scope": s, "description": SCOPE_DESCRIPTIONS[s]}
                   for s in row.scope.split()],
        "expires_at": _aware(row.expires_at).isoformat(),
    }


def decide(db: Session, request_id, user: User, *, approve: bool,
           request: Request | None = None) -> str:
    """Record the person's answer; return where to send their browser."""
    row, client = pending_request(db, request_id)
    now = _now()
    code = secrets.token_urlsafe(32) if approve else None
    values = {"decision": APPROVED if approve else DENIED, "decided_at": now,
              "user_id": user.id}
    if code is not None:
        values.update(code_hash=_hash(code), code_expires_at=now + CODE_TTL)
    claimed = db.execute(
        update(OAuthAuthorizationCode)
        .where(OAuthAuthorizationCode.id == row.id, OAuthAuthorizationCode.decision.is_(None))
        .values(**values)
        .execution_options(synchronize_session=False)
    ).rowcount
    if not claimed:
        db.rollback()
        raise OAuthError("already_decided", "this authorization request was already answered",
                         status=409)
    security_audit.record(
        db, action=(security_audit.OAUTH_CONSENT_GRANTED if approve
                    else security_audit.OAUTH_CONSENT_DENIED),
        request=request, user_id=user.id, owner_user_id=user.id,
        target_type="oauth_client", target_id=None,
        details={"oauth_client_id": client.client_id, "client_name": client.client_name,
                 "redirect_host": urlsplit(row.redirect_uri).hostname,
                 "scope": row.scope})
    db.commit()
    if approve:
        return redirect_with(row.redirect_uri, {"code": code, "state": row.state})
    return redirect_with(row.redirect_uri, {
        "error": "access_denied", "error_description": "the user declined", "state": row.state})


# --------------------------------------------------------------------------
# Token endpoint
# --------------------------------------------------------------------------


def _pkce_ok(verifier: str | None, challenge: str) -> bool:
    if not verifier or not _PKCE_VALUE.match(verifier):
        return False
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(computed, challenge)


def _token_client(db: Session, client_id: str | None) -> OAuthClient:
    client = _client(db, client_id)
    if client is None:
        raise OAuthError("invalid_client", "unknown client_id", status=401)
    return client


def exchange_code(db: Session, form: dict, *,
                  request: Request | None = None) -> auth_sessions.ConnectorTokens:
    for name in ("code", "redirect_uri", "code_verifier", "client_id"):
        if not form.get(name):
            raise OAuthError("invalid_request", f"{name} is required")
    client = _token_client(db, form["client_id"])
    row = db.execute(select(OAuthAuthorizationCode)
                     .where(OAuthAuthorizationCode.code_hash == _hash(form["code"]))
                     ).scalar_one_or_none()
    if row is None or row.client_id != client.client_id or row.decision != APPROVED:
        raise OAuthError("invalid_grant", "authorization code is invalid")
    now = _now()
    if row.used_at is not None:
        # A code redeemed twice was intercepted or replayed: end whatever
        # the first redemption started (RFC 6749 §4.1.2).
        if row.session_family_id is not None:
            auth_sessions.revoke_family(db, row.session_family_id, auth_sessions.REUSE_DETECTED,
                                        now)
        security_audit.record(db, action=security_audit.OAUTH_CODE_REUSE, request=request,
                              user_id=row.user_id, target_type="auth_session_family",
                              target_id=row.session_family_id,
                              details={"oauth_client_id": client.client_id})
        db.commit()
        raise OAuthError("invalid_grant", "authorization code has already been used")
    if _aware(row.code_expires_at) is None or _aware(row.code_expires_at) <= now:
        raise OAuthError("invalid_grant", "authorization code has expired")
    if form["redirect_uri"] != row.redirect_uri:
        raise OAuthError("invalid_grant", "redirect_uri does not match the authorization request")
    if not _pkce_ok(form.get("code_verifier"), row.code_challenge):
        raise OAuthError("invalid_grant", "PKCE verification failed")
    resource = form.get("resource")
    if resource and resource != settings.mcp_resource:
        raise OAuthError("invalid_target", f"resource must be {settings.mcp_resource}")

    claimed = db.execute(
        update(OAuthAuthorizationCode)
        .where(OAuthAuthorizationCode.id == row.id, OAuthAuthorizationCode.used_at.is_(None))
        .values(used_at=now)
        .execution_options(synchronize_session=False)
    ).rowcount
    if not claimed:
        db.rollback()
        raise OAuthError("invalid_grant", "authorization code has already been used")
    user = db.get(User, row.user_id)
    if user is None or not auth_sessions._account_usable(user):
        db.commit()
        raise OAuthError("invalid_grant", "the account cannot sign in")
    tokens = auth_sessions.start_connector_session(
        db, user, client_id=client.client_id, scope=row.scope, request=request, now=now)
    db.execute(update(OAuthAuthorizationCode).where(OAuthAuthorizationCode.id == row.id)
               .values(session_family_id=tokens.session.family_id)
               .execution_options(synchronize_session=False))
    client.last_used_at = now
    db.commit()
    return tokens


def refresh(db: Session, form: dict, *,
            request: Request | None = None) -> auth_sessions.ConnectorTokens:
    if not form.get("refresh_token"):
        raise OAuthError("invalid_request", "refresh_token is required")
    client = _token_client(db, form.get("client_id"))
    requested = (form.get("scope") or "").split()
    if requested:
        # RFC 6749 §6: a refresh may not widen the grant. Checked BEFORE
        # rotating, so a refused request leaves the session as it was. A
        # narrower request gets the original grant back (the response's
        # `scope` says so); narrowing needs a new consent.
        granted = _session_scope(db, form["refresh_token"])
        if granted is not None and not set(requested) <= set(granted.split()):
            raise OAuthError("invalid_scope", "a refresh cannot add scopes; reconnect instead")
    try:
        tokens = auth_sessions.rotate_connector(db, form["refresh_token"],
                                                client_id=client.client_id, request=request)
    except auth_sessions.OAuthGrantError as exc:
        raise OAuthError(exc.error, exc.description) from None
    client.last_used_at = _now()
    db.commit()
    return tokens


def _session_scope(db: Session, refresh_token: str) -> str | None:
    """The scope a connector refresh token's session was granted, or None
    when the token is unusable (rotate_connector then says why)."""
    try:
        payload = auth_svc.decode_mcp_refresh_token(refresh_token)
        row = db.get(AuthSession, uuid.UUID(payload["jti"]))
    except (auth_svc.TokenRejected, ValueError):
        return None
    return row.scope if row is not None else None


def token(db: Session, form: dict, *,
          request: Request | None = None) -> auth_sessions.ConnectorTokens:
    grant = form.get("grant_type")
    if grant == GRANT_AUTHORIZATION_CODE:
        return exchange_code(db, form, request=request)
    if grant == GRANT_REFRESH_TOKEN:
        return refresh(db, form, request=request)
    if not grant:
        raise OAuthError("invalid_request", "grant_type is required")
    raise OAuthError("unsupported_grant_type",
                     "grant_type must be authorization_code or refresh_token")


def revoke(db: Session, form: dict, *, request: Request | None = None) -> None:
    """RFC 7009: always succeeds from the caller's point of view."""
    token_value = form.get("token")
    client = _client(db, form.get("client_id"))
    if not token_value or client is None:
        return
    auth_sessions.revoke_connector_token(db, token_value, client_id=client.client_id,
                                         request=request)

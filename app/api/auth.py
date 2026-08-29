"""Auth + current-user endpoints (M5).

POST /auth/signup   — create account (or claim a pre-auth row with no
                      password yet), returns access+refresh tokens AND sends
                      a verification email (Feature 1)
POST /auth/login    — email+password -> tokens
POST /auth/refresh  — refresh token -> new token pair
GET  /auth/me       — the authenticated user
GET  /auth/verify   — target of the emailed link; marks the account verified
                      and 302s to the frontend login page (Feature 1)
POST /auth/resend-verification — send a fresh link; always 202, never reveals
                      whether the address has an account (Feature 1)
GET  /me/theme      — the user's theme JSON (section H)
PUT  /me/theme      — persist theme JSON (validated; contrast_warnings
                      flag persisted so the user was demonstrably informed)
POST /me/theme/background — upload a background image; served at /media/*

NOTE: only these user-scoped endpoints enforce auth in M5. Wiring
get_current_user into every pre-existing endpoint (and scoping strategies/
leads by owner) is a deliberate follow-up — flagged, not silently done,
because it changes every existing API contract and test.
"""

import logging
import re
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.rate_limiting import (
    AUTH_WINDOW_SECONDS,
    client_ip,
    enforce_rate_limit,
)
from app.db.base import get_db
from app.db.models import User
from app.services import auth as auth_svc
from app.services import email_verification as verify_svc
from app.services.email_sender import EmailSendError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

_ALLOWED_IMAGE = {"image/png": ".png", "image/jpeg": ".jpg",
                  "image/webp": ".webp"}
_MAX_IMAGE_BYTES = 5 * 1024 * 1024

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class RefreshIn(BaseModel):
    refresh_token: str


class ResendIn(BaseModel):
    email: EmailStr


class ThemeIn(BaseModel):
    """Mirrors the frontend Theme type (section H)."""
    preset: str | None = None
    background_color: str = "#ffffff"
    background_image_url: str | None = None
    background_overlay: float = Field(default=0.0, ge=0.0, le=0.9)
    primary_color: str = "#1d4ed8"
    accent_color: str = "#0891b2"
    font_family: str = "Inter"
    font_size_scale: float = Field(default=1.0, ge=0.8, le=1.4)
    radius_px: int = Field(default=8, ge=0, le=24)
    density: str = Field(default="comfortable", pattern="^(comfortable|compact)$")
    contrast_warnings: list[str] = Field(default_factory=list)

    def validated(self) -> dict:
        for name in ("background_color", "primary_color", "accent_color"):
            if not _HEX.match(getattr(self, name)):
                raise HTTPException(status_code=422,
                                    detail=f"{name} must be #rrggbb")
        return self.model_dump()


def _user_out(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "plan": user.plan.value,
        # M8-C3 admin UI reads this to gate the /admin route group.
        "is_admin": bool(getattr(user, "is_admin", False)),
        # Feature 1: the frontend routes an unverified user to the
        # check-your-email screen straight off the signup/login response,
        # instead of letting them reach the dashboard and discover it as a 403
        # on the first data fetch.
        "email_verified": bool(getattr(user, "email_verified", False)),
    }


def _deliver_verification(db: Session, user: User) -> bool:
    """Persist a fresh token, then email it. Returns whether the mail went out.

    Never raises. Both callers (signup, resend) treat a mail-transport failure
    as a degraded success rather than an error, because the alternatives are
    worse: failing signup with a 500 destroys an account the user just created
    and cannot retry (the address is now taken), and rolling the account back
    loses their password entry for a fault that is entirely ours.

    The commit happens BEFORE the send so the token is durable by the time the
    link can be clicked -- see email_verification.send_link.
    """
    raw = verify_svc.issue_token(db, user)
    db.commit()
    try:
        verify_svc.send_link(user, raw)
    except EmailSendError as exc:
        # Logged at error level with the address, because this is the failure
        # mode that silently strands users and it must be greppable.
        logger.error("verification email FAILED for %s: %s", user.email, exc)
        return False
    return True


@router.post("/auth/signup", status_code=201)
def signup(request: Request, body: Credentials,
           db: Session = Depends(get_db)) -> dict:
    """Create an account (or claim a pre-auth row that has no password yet).

    Rate limited per IP: unlimited signups let one caller farm accounts, and
    an account-creation flood is the cheapest way to pollute the user table.
    """
    # Quota AFTER validation, before any DB work — same ordering as
    # create_strategy. FastAPI validates `body` before this line runs, so a
    # malformed payload cannot burn a slot.
    enforce_rate_limit(f"ip:{client_ip(request)}", "auth_ip",
                       "RATE_LIMIT_AUTH", AUTH_WINDOW_SECONDS)

    email = body.email.lower().strip()
    user = db.execute(select(User).where(User.email == email)).scalars().first()
    if user is not None and user.password_hash:
        raise HTTPException(status_code=409, detail="account already exists")
    if user is None:
        user = User(email=email)
        db.add(user)
    try:
        user.password_hash = auth_svc.hash_password(body.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    # New accounts start UNVERIFIED. Pre-auth rows being claimed here are new
    # accounts too as far as verification goes -- nobody has ever proved they
    # control the address. (Rows that existed before migration 0015 were
    # backfilled to verified by that migration and are not affected: this line
    # only runs for a row that had no password, i.e. one nobody has used.)
    user.email_verified = False
    user.email_verified_at = None
    db.commit()

    # Tokens are still returned. The account cannot DO anything with them --
    # get_current_user rejects every authenticated route with 403
    # EMAIL_NOT_VERIFIED -- but handing them over means the client is already
    # signed in the instant the link is clicked, with no second login, and the
    # check-your-email screen has a session to resend from.
    sent = _deliver_verification(db, user)
    return {
        "user": _user_out(user),
        **auth_svc.issue_tokens(user.id),
        "email_verification_required": True,
        "verification_email_sent": sent,
    }


@router.get("/auth/verify", include_in_schema=True)
def verify_email(token: str = Query(default="", max_length=512),
                 db: Session = Depends(get_db)) -> RedirectResponse:
    """The target of the link in the verification email.

    Always REDIRECTS, never renders. The API has no templates and no styling,
    and a bare JSON body is not something to show a person who just clicked a
    button in their inbox. Every outcome lands on the frontend login page with
    a query flag it can turn into a message:

        ?verified=true            success
        ?verified=already         the account was already verified
        ?error=expired            link older than EMAIL_VERIFICATION_TTL_HOURS
        ?error=invalid            unknown or malformed token

    302 (not 307) is deliberate: this is a GET being answered with a GET, and
    302 is what every mail client and link scanner handles predictably.

    NOT rate limited. The token is 43 URL-safe characters of os.urandom inside
    a 24-hour window; there is nothing to brute force, and a limiter keyed on
    IP would punish the shared corporate NAT of exactly the customer we want.
    """
    frontend = settings.frontend_url.rstrip("/")
    status, _user = verify_svc.consume_token(db, token or "")
    if status == verify_svc.VERIFIED:
        db.commit()
        target = f"{frontend}/login?verified=true"
    elif status == verify_svc.ALREADY_VERIFIED:
        target = f"{frontend}/login?verified=already"
    elif status == verify_svc.EXPIRED:
        target = f"{frontend}/login?error=expired"
    else:
        target = f"{frontend}/login?error=invalid"
    logger.info("email verification outcome=%s", status)
    return RedirectResponse(url=target, status_code=302)


@router.post("/auth/resend-verification", status_code=202)
def resend_verification(request: Request, body: ResendIn,
                        db: Session = Depends(get_db)) -> dict:
    """Send a fresh verification link.

    ALWAYS returns 202 with the same body, whatever the address is. Reporting
    "no such account" here would hand anyone an account-existence oracle for
    every address they care to try -- and /auth/login went to the trouble of
    avoiding exactly that with its single "invalid email or password". A
    resend endpoint that leaks it would undo that.

    Rate limited on BOTH keys for the same reason /auth/login is: per IP stops
    one host hammering the mail transport, per account stops a distributed
    mail-bomb aimed at one person's inbox. Both consume on every call.
    """
    enforce_rate_limit(f"ip:{client_ip(request)}", "auth_ip",
                       "RATE_LIMIT_AUTH", AUTH_WINDOW_SECONDS)
    email = body.email.lower().strip()
    enforce_rate_limit(f"acct:{email}", "auth_account",
                       "RATE_LIMIT_AUTH", AUTH_WINDOW_SECONDS)

    user = db.execute(select(User).where(User.email == email)).scalars().first()
    # Nothing to send for an unknown address, a passwordless pre-auth row, or
    # an account that is already verified -- and the caller is told none of it.
    if user is not None and user.password_hash and not user.email_verified:
        _deliver_verification(db, user)
    return {"status": "accepted",
            "detail": "If that address has an unverified account, "
                      "a verification email has been sent."}


@router.post("/auth/login")
def login(request: Request, body: Credentials,
          db: Session = Depends(get_db)) -> dict:
    """Email + password -> tokens.

    Two independent limits, both governed by RATE_LIMIT_AUTH:

      per IP       stops one host brute-forcing passwords.
      per account  stops CREDENTIAL STUFFING, where an attacker spreads
                   attempts against a single account across many IPs. A
                   per-IP limit alone does nothing about that, which is why
                   both keys exist rather than just the obvious one.

    Both are consumed on every attempt, successful or not — enforce_rate_limit
    is INCR-then-compare, so the check and the spend are one step. Counting
    only failures would be gentler on shared IPs, but it needs a
    check-then-conditionally-record split this codebase does not have, and
    adding one here would mean two divergent limiter mechanisms. The trade-off
    is recorded in CLAUDE_CODE_HANDOFF.md rather than hidden.

    /auth/refresh is deliberately NOT limited: a legitimate client hits it
    every time a 15-minute access token expires, so it is the one auth route
    where normal use approaches the threshold, and guessing a signed refresh
    token is not a brute-forceable attack in the first place.
    """
    enforce_rate_limit(f"ip:{client_ip(request)}", "auth_ip",
                       "RATE_LIMIT_AUTH", AUTH_WINDOW_SECONDS)

    email = body.email.lower().strip()
    # Keyed on the normalised address, so Foo@x.com and foo@x.com share a
    # bucket and casing cannot be used to multiply the allowance.
    enforce_rate_limit(f"acct:{email}", "auth_account",
                       "RATE_LIMIT_AUTH", AUTH_WINDOW_SECONDS)

    user = db.execute(select(User).where(User.email == email)).scalars().first()
    if user is None or not auth_svc.verify_password(body.password,
                                                    user.password_hash):
        # one message for both cases: no account enumeration
        raise HTTPException(status_code=401, detail="invalid email or password")
    return {"user": _user_out(user), **auth_svc.issue_tokens(user.id)}


@router.post("/auth/refresh")
def refresh(body: RefreshIn, db: Session = Depends(get_db)) -> dict:
    user_id = auth_svc.decode_token(body.refresh_token, "refresh")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="user not found")
    return {"user": _user_out(user), **auth_svc.issue_tokens(user.id)}


@router.get("/auth/me")
def me(user: User = Depends(auth_svc.get_current_user)) -> dict:
    return _user_out(user)


# --------------------------------------------------------------------------
# Theme (section H) — stored as users.theme_json
# --------------------------------------------------------------------------


@router.get("/me/theme")
def get_theme(user: User = Depends(auth_svc.get_current_user)) -> dict:
    return {"theme": user.theme_json or {}}


@router.put("/me/theme")
def put_theme(body: ThemeIn, db: Session = Depends(get_db),
              user: User = Depends(auth_svc.get_current_user)) -> dict:
    user.theme_json = body.validated()
    db.commit()
    return {"theme": user.theme_json}


@router.post("/me/theme/background", status_code=201)
async def upload_background(file: UploadFile, db: Session = Depends(get_db),
                            user: User = Depends(auth_svc.get_current_user)
                            ) -> dict:
    ext = _ALLOWED_IMAGE.get(file.content_type or "")
    if ext is None:
        raise HTTPException(status_code=422,
                            detail="only png, jpeg or webp images")
    data = await file.read()
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=422, detail="image over 5MB")
    media = Path(settings.media_dir)
    media.mkdir(parents=True, exist_ok=True)
    name = f"bg_{user.id.hex}_{secrets.token_hex(6)}{ext}"
    (media / name).write_bytes(data)
    url = f"{settings.public_base_url.rstrip('/')}/media/{name}"
    return {"url": url}

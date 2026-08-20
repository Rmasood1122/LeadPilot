"""ADMIN_EMAIL bootstrap — make the configured address an admin on startup.

THE PROBLEM THIS SOLVES
    `ADMIN_EMAIL` was declared in app/core/config.py and read by absolutely
    nothing. `require_admin` gates every /admin route on `users.is_admin`, and
    /auth/signup takes only email+password (an `is_admin` key in the body is
    dropped, correctly - no self-promotion over HTTP). So on a freshly deployed
    database there was no admin and no way to get one without shell access to
    run `python -m app.cli.create_admin`. Every /admin route and
    /playbook/aggregate was unreachable.

WHAT IT DOES
    On startup, if ADMIN_EMAIL is set and a user with that address exists, it
    is flagged as admin. Idempotent: already-admin is a no-op, and it NEVER
    clears is_admin on anyone, so a second admin promoted by the CLI is not
    downgraded when a different ADMIN_EMAIL is configured.

WHAT IT DELIBERATELY DOES NOT DO: create the account.
    There is no password-reset flow anywhere in this application. An account
    conjured at startup would need either a password nobody knows (unloggable,
    so it removes nothing - the operator still has to run the CLI) or a
    generated one written to the logs (a credential in the log stream, which is
    worse). So a missing ADMIN_EMAIL user is reported as a loud, actionable
    ERROR naming the exact command instead. Signup once, or run the CLI, and
    the next restart promotes it.

    Startup is never blocked: a database that is not migrated yet, or is simply
    unreachable, must not stop the API from booting.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def ensure_admin_from_env(session, admin_email: str | None) -> bool:
    """Promote `admin_email` to admin. Returns True if a row was changed.

    Pure and testable: the caller supplies the session and the address.
    """
    if not admin_email or not admin_email.strip():
        logger.debug("ADMIN_EMAIL is not set - no admin bootstrap performed")
        return False

    email = admin_email.strip().lower()

    from sqlalchemy import select

    from app.db.models import User

    user = session.execute(
        select(User).where(User.email == email)
    ).scalars().first()

    if user is None:
        logger.error(
            "ADMIN_EMAIL=%s is set but no user with that address exists, so "
            "nothing was promoted. Create it with: "
            "python -m app.cli.create_admin --email %s   "
            "(or sign up with that address, then restart).",
            email, email,
        )
        return False

    if bool(getattr(user, "is_admin", False)):
        logger.info("ADMIN_EMAIL=%s is already an admin", email)
        return False

    user.is_admin = True
    session.commit()
    logger.warning("Promoted %s to admin via ADMIN_EMAIL", email)
    return True


def bootstrap_admin() -> bool:
    """Startup entry point. Opens its own session and never raises."""
    try:
        from app.core.config import settings as m8_settings
    except Exception:  # pragma: no cover - config module is always importable
        return False

    admin_email = getattr(m8_settings, "ADMIN_EMAIL", None)
    if not admin_email:
        return False

    try:
        from app.db.base import SessionLocal

        session = SessionLocal()
        try:
            return ensure_admin_from_env(session, admin_email)
        finally:
            session.close()
    except Exception as exc:  # noqa: BLE001 - startup must not be blocked
        logger.warning("admin bootstrap skipped: %s", exc)
        return False

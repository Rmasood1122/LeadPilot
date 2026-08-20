"""Unsubscribe endpoint — CAN-SPAM one-click, no login, instant.

GET renders a plain confirmation page (human clicked the footer link);
POST supports RFC 8058 one-click (List-Unsubscribe-Post). Both do the
same thing immediately: suppression + hard stop of every sequence for
that lead. Invalid or tampered tokens are rejected safely with no
information leak.
"""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import Lead
from app.services import sequence_engine as engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["unsubscribe"])

_CONFIRM_HTML = """<!doctype html>
<html><head><title>Unsubscribed</title></head>
<body style="font-family: sans-serif; max-width: 480px; margin: 80px auto;">
<h2>You're unsubscribed.</h2>
<p>You will not receive any further emails from this sender. This took
effect immediately.</p>
</body></html>"""

_INVALID_HTML = """<!doctype html>
<html><head><title>Invalid link</title></head>
<body style="font-family: sans-serif; max-width: 480px; margin: 80px auto;">
<h2>This unsubscribe link is not valid.</h2>
<p>The link may be incomplete. If you keep receiving unwanted email,
reply with "unsubscribe" and you will be removed immediately.</p>
</body></html>"""


def _process(token: str, db: Session) -> HTMLResponse:
    try:
        lead_id = engine.parse_unsubscribe_token(token)
    except Exception:
        return HTMLResponse(_INVALID_HTML, status_code=400)
    lead = db.get(Lead, lead_id)
    if lead is None:
        # Token was valid once but the lead is gone (e.g. GDPR-deleted).
        return HTMLResponse(_CONFIRM_HTML, status_code=200)
    engine.unsubscribe_lead(db, lead, source="link")
    return HTMLResponse(_CONFIRM_HTML, status_code=200)


@router.get("/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe_get(token: str, db: Session = Depends(get_db)) -> HTMLResponse:
    return _process(token, db)


@router.post("/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe_post(token: str, db: Session = Depends(get_db)) -> HTMLResponse:
    """RFC 8058 one-click target (mail clients POST here)."""
    return _process(token, db)

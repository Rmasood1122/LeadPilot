"""GET /t/o/{token}.gif -- the email open pixel (Feature Group 3). Public.

Always answers with the same transparent GIF, whatever happened: a valid,
an invalid, a rate-limited or a failing request are indistinguishable from
outside, so the endpoint cannot be used to probe which message ids exist.

The HMAC check runs BEFORE the rate limiter, deliberately breaking the
"rate limit first" convention: the limiter keys on the token, and letting
unauthenticated garbage tokens mint Redis keys would turn the limiter itself
into the thing being flooded. A forged token costs one HMAC and nothing else.
The limit is per token, not per IP -- Gmail fetches every recipient's images
through a small pool of Google proxy IPs, and a per-IP limit would drop real
opens at exactly the scale where they matter.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.services import open_tracking

logger = logging.getLogger(__name__)
router = APIRouter(tags=["tracking"])

_NO_CACHE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _pixel() -> Response:
    return Response(content=open_tracking.PIXEL_GIF, media_type="image/gif",
                    headers=_NO_CACHE)


@router.get("/t/o/{token}.gif", include_in_schema=False)
def open_pixel(token: str, request: Request, db: Session = Depends(get_db)) -> Response:
    message_id = open_tracking.parse_token(token)
    if message_id is None:
        return _pixel()
    try:
        enforce_rate_limit(token, "open_pixel", "RATE_LIMIT_OPEN_PIXEL")
    except Exception:
        return _pixel()
    try:
        open_tracking.record_open(db, message_id,
                                  user_agent=request.headers.get("user-agent"))
    except Exception:
        db.rollback()
        logger.exception("open pixel: could not record open for message %s", message_id)
    return _pixel()


@router.get("/t/c/{token}", include_in_schema=False)
def click_redirect(token: str, u: str = Query(default="", max_length=2000),
                   db: Session = Depends(get_db)) -> Response:
    """Feature A2: a tracked link. Redirects ONLY to the destination the token
    was minted for (HMAC-bound), so this is never an open redirector. A forged
    or mismatched token is a plain 404 -- there is no safe place to send it."""
    message_id = open_tracking.parse_click_token(token, u)
    if message_id is None:
        return Response(content="Link not found", status_code=404, media_type="text/plain")
    try:
        enforce_rate_limit(token, "click_redirect", "RATE_LIMIT_OPEN_PIXEL")
        open_tracking.record_click(db, message_id, u)
    except Exception:  # noqa: BLE001 -- the person still reaches the page
        db.rollback()
        logger.info("click redirect: not recorded for message %s", message_id)
    return RedirectResponse(url=u, status_code=302,
                            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

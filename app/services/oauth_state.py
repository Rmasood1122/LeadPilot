"""Signed, expiring OAuth `state` values for the Feature Group 4 connect flows.

The callback of an OAuth flow is a plain browser redirect with no
Authorization header; `state` is the only thing that says which user started
it. Gmail's state (app/integrations/gmail.py) is Fernet-encrypted but carries
no purpose and no expiry, so a state minted for one provider would be accepted
by another's callback, forever. These carry both: a HubSpot state is rejected
by the Salesforce callback, and every state dies after fifteen minutes.
"""

from __future__ import annotations

import time
import uuid

from app.services import crypto

TTL_SECONDS = 15 * 60


class InvalidState(ValueError):
    pass


def make(user_id, purpose: str, *, ttl: int = TTL_SECONDS) -> str:
    return crypto.encrypt_json({"u": str(user_id), "p": purpose, "n": uuid.uuid4().hex,
                                "e": int(time.time()) + ttl})


def parse(state: str | None, purpose: str) -> uuid.UUID:
    if not state:
        raise InvalidState("missing state")
    try:
        data = crypto.decrypt_json(state)
    except Exception as exc:
        raise InvalidState("invalid or tampered state") from exc
    if data.get("p") != purpose:
        raise InvalidState("state was issued for a different integration")
    if int(data.get("e") or 0) < time.time():
        raise InvalidState("state expired -- start the connection again")
    try:
        return uuid.UUID(str(data["u"]))
    except (KeyError, ValueError) as exc:
        raise InvalidState("invalid state") from exc

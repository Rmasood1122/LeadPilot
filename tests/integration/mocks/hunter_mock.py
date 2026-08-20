"""
Hunter.io API transport mock.

alice.chen@saasco.io        → deliverable   (should be kept)
ben@growthagency.com        → deliverable   (should be kept)
carol@psvc.net              → undeliverable (should be dropped before send)
unknown@example.com         → risky         (treated as drop in strict mode)
"""
from __future__ import annotations

import json

import respx
from httpx import Request, Response

HUNTER_BASE = "https://api.hunter.io/v2"

VERIFY_RESPONSES: dict[str, dict] = {
    "alice.chen@saasco.io": {
        "email": "alice.chen@saasco.io",
        "result": "deliverable",
        "score": 92,
        "regexp": True,
        "gibberish": False,
        "disposable": False,
        "webmail": False,
        "mx_records": True,
        "smtp_server": True,
        "smtp_check": True,
        "accept_all": False,
        "block": False,
    },
    "ben@growthagency.com": {
        "email": "ben@growthagency.com",
        "result": "deliverable",
        "score": 88,
        "regexp": True,
        "gibberish": False,
        "disposable": False,
        "webmail": False,
        "mx_records": True,
        "smtp_server": True,
        "smtp_check": True,
        "accept_all": False,
        "block": False,
    },
    "carol@psvc.net": {
        "email": "carol@psvc.net",
        "result": "undeliverable",
        "score": 12,
        "regexp": True,
        "gibberish": False,
        "disposable": False,
        "webmail": False,
        "mx_records": False,
        "smtp_server": False,
        "smtp_check": False,
        "accept_all": False,
        "block": False,
    },
    "unknown@example.com": {
        "email": "unknown@example.com",
        "result": "risky",
        "score": 40,
        "regexp": True,
        "gibberish": False,
        "disposable": False,
        "webmail": True,
        "mx_records": True,
        "smtp_server": True,
        "smtp_check": False,
        "accept_all": True,
        "block": False,
    },
}

_DEFAULT_RESPONSE = {
    "result": "deliverable",
    "score": 75,
    "regexp": True,
    "gibberish": False,
    "disposable": False,
    "webmail": False,
    "mx_records": True,
    "smtp_server": True,
    "smtp_check": True,
    "accept_all": False,
    "block": False,
}


def _verify_handler(request: Request) -> Response:
    params = dict(request.url.params)
    email = params.get("email", "")
    data = VERIFY_RESPONSES.get(email, {**_DEFAULT_RESPONSE, "email": email})
    return Response(200, json={"data": data, "meta": {"params": {"email": email}}})


def _email_finder_handler(request: Request) -> Response:
    params = dict(request.url.params)
    domain = params.get("domain", "example.com")
    first = params.get("first_name", "John")
    last = params.get("last_name", "Doe")
    email = f"{first.lower()}.{last.lower()}@{domain}"
    return Response(200, json={
        "data": {
            "first_name": first,
            "last_name": last,
            "email": email,
            "score": 72,
            "domain": domain,
            "verification": {"result": "deliverable"},
        }
    })


def register(router: respx.MockRouter) -> None:
    """Register Hunter routes on the given respx router."""
    router.get(f"{HUNTER_BASE}/email-verifier").mock(side_effect=_verify_handler)
    router.get(f"{HUNTER_BASE}/email-finder").mock(side_effect=_email_finder_handler)

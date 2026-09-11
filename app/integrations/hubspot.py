"""HubSpot — OAuth, the CRM v3 objects API and webhook signatures (Feature Group 4).

The HubSpot public APP (client id / secret) is a system credential under
"hubspot_app"; each user's grant (access + refresh token) is a user
credential under "hubspot". The client secret also signs HubSpot's webhooks
(signature v3), so there is no separate webhook secret to configure.

Only what the sync needs is wrapped: contact search/create/update, deal
create/update/associate, and batch reads for the pull side.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from urllib.parse import urlencode

import httpx

AUTH_URL = "https://app.hubspot.com/oauth/authorize"
API_BASE = "https://api.hubapi.com"
TOKEN_URL = f"{API_BASE}/oauth/v1/token"
SCOPES = (
    "oauth",
    "crm.objects.contacts.read",
    "crm.objects.contacts.write",
    "crm.objects.deals.read",
    "crm.objects.deals.write",
)
PROVIDER = "hubspot"
APP_PROVIDER = "hubspot_app"
SIGNATURE_TOLERANCE_SECONDS = 300

CONTACT_PROPERTIES = ["email", "firstname", "lastname", "company", "jobtitle", "phone",
                      "hs_lead_status", "lifecyclestage"]
DEAL_PROPERTIES = ["dealname", "amount", "dealstage", "closedate", "pipeline",
                   "deal_currency_code"]


class HubSpotError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status
        # 4xx other than 429 will not get better on retry.
        self.permanent = status is not None and 400 <= status < 500 and status != 429


def _http() -> httpx.Client:
    """Factory tests monkeypatch."""
    return httpx.Client(timeout=20.0)


def build_auth_url(client_id: str, redirect_uri: str, state: str) -> str:
    return f"{AUTH_URL}?" + urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "state": state,
    })


def _token_request(data: dict) -> dict:
    with _http() as client:
        resp = client.post(TOKEN_URL, data=data)
    if resp.status_code >= 400:
        raise HubSpotError(f"token endpoint: HTTP {resp.status_code} {resp.text[:200]}",
                           resp.status_code)
    return resp.json()


def exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    # TODO: verify against current HubSpot docs (OAuth v1 token endpoint)
    return _token_request({"grant_type": "authorization_code", "client_id": client_id,
                           "client_secret": client_secret, "redirect_uri": redirect_uri,
                           "code": code})


def refresh(client_id: str, client_secret: str, refresh_token: str) -> dict:
    return _token_request({"grant_type": "refresh_token", "client_id": client_id,
                           "client_secret": client_secret, "refresh_token": refresh_token})


def token_info(access_token: str) -> dict:
    """{hub_id, hub_domain, user, ...} for the portal the grant belongs to."""
    with _http() as client:
        resp = client.get(f"{API_BASE}/oauth/v1/access-tokens/{access_token}")
    if resp.status_code >= 400:
        raise HubSpotError(f"token info: HTTP {resp.status_code}", resp.status_code)
    return resp.json()


def verify_signature_v3(client_secret: str, method: str, uri: str, body: bytes,
                        timestamp: str | None, signature: str | None,
                        now: float | None = None) -> bool:
    """X-HubSpot-Signature-v3 = base64(HMAC-SHA256(secret,
    method + uri + body + timestamp)); timestamps older than five minutes
    are rejected so a captured request cannot be replayed."""
    if not (client_secret and timestamp and signature):
        return False
    try:
        ts_ms = int(timestamp)
    except ValueError:
        return False
    now = time.time() if now is None else now
    if abs(now - ts_ms / 1000) > SIGNATURE_TOLERANCE_SECONDS:
        return False
    message = method.upper().encode() + uri.encode() + body + timestamp.encode()
    expected = base64.b64encode(
        hmac.new(client_secret.encode(), message, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(expected, signature)


class HubSpotClient:
    def __init__(self, access_token: str):
        self.access_token = access_token

    def _req(self, method: str, path: str, *, json: dict | None = None,
             params: dict | None = None) -> dict:
        with _http() as client:
            resp = client.request(method, f"{API_BASE}{path}", json=json, params=params,
                                  headers={"Authorization": f"Bearer {self.access_token}"})
        if resp.status_code >= 400:
            raise HubSpotError(f"{method} {path}: HTTP {resp.status_code} {resp.text[:300]}",
                               resp.status_code)
        return resp.json() if resp.content else {}

    # ---- contacts ---------------------------------------------------------
    def find_contact_by_email(self, email: str) -> str | None:
        # TODO: verify against current HubSpot docs (CRM v3 search)
        data = self._req("POST", "/crm/v3/objects/contacts/search", json={
            "filterGroups": [{"filters": [
                {"propertyName": "email", "operator": "EQ", "value": email}]}],
            "properties": ["email"], "limit": 1,
        })
        results = data.get("results") or []
        return str(results[0]["id"]) if results else None

    def create_contact(self, properties: dict) -> str:
        return str(self._req("POST", "/crm/v3/objects/contacts",
                             json={"properties": properties})["id"])

    def update_contact(self, contact_id: str, properties: dict) -> None:
        self._req("PATCH", f"/crm/v3/objects/contacts/{contact_id}",
                  json={"properties": properties})

    # ---- deals ------------------------------------------------------------
    def create_deal(self, properties: dict) -> str:
        return str(self._req("POST", "/crm/v3/objects/deals",
                             json={"properties": properties})["id"])

    def update_deal(self, deal_id: str, properties: dict) -> None:
        self._req("PATCH", f"/crm/v3/objects/deals/{deal_id}", json={"properties": properties})

    def associate_deal_contact(self, deal_id: str, contact_id: str) -> None:
        # TODO: verify against current HubSpot docs (associations v4 default)
        self._req("PUT", f"/crm/v4/objects/deals/{deal_id}/associations/default/"
                         f"contacts/{contact_id}")

    def get_deal(self, deal_id: str) -> dict:
        return self._req("GET", f"/crm/v3/objects/deals/{deal_id}",
                         params={"properties": ",".join(DEAL_PROPERTIES),
                                 "associations": "contacts"})

    # ---- pull ---------------------------------------------------------------
    def batch_read(self, object_type: str, ids: list[str], properties: list[str]) -> list[dict]:
        """[{id, properties, updatedAt}] for up to 100 ids per call."""
        out: list[dict] = []
        for start in range(0, len(ids), 100):
            chunk = ids[start:start + 100]
            data = self._req("POST", f"/crm/v3/objects/{object_type}/batch/read", json={
                "properties": properties, "inputs": [{"id": i} for i in chunk]})
            out.extend(data.get("results") or [])
        return out

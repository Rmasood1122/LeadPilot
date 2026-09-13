"""Stripe over its REST API (no SDK dependency) — Section E.

The repo had no payments code, so this follows the house integration style
(httpx, a monkeypatchable `_http()` factory, one error type) rather than
adding the `stripe` package. Stripe's API is form-encoded; `_form()` flattens
nested dicts into `a[b][c]=v` keys the way the official SDKs do.

STUB MODE. With no STRIPE_SECRET_KEY every call raises StripeNotConfigured,
and app/services/billing.py takes its explicit stub path instead (activating
plans locally with is_stub=True). Nothing here pretends to have charged.
    # TODO: connect live Stripe keys (STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET)

WEBHOOKS are verified with Stripe's scheme: header
`Stripe-Signature: t=<unix>,v1=<hex hmac_sha256(secret, "<t>.<raw body>")>`,
constant-time compared, with a timestamp tolerance against replay.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

from app.config import settings
from app.core.exceptions import ClientHunterError

logger = logging.getLogger(__name__)


class StripeError(ClientHunterError):
    """Stripe refused or could not be reached."""


class StripeNotConfigured(StripeError):
    """No STRIPE_SECRET_KEY: the caller must take its stub path."""


def _http() -> httpx.Client:
    """Factory tests monkeypatch."""
    return httpx.Client(base_url=settings.stripe_api_base,
                        timeout=settings.stripe_timeout_seconds)


def _form(data: dict[str, Any], prefix: str = "") -> list[tuple[str, str]]:
    """{"a": {"b": 1}, "c": [{"d": 2}]} -> [("a[b]", "1"), ("c[0][d]", "2")]."""
    out: list[tuple[str, str]] = []
    for key, value in data.items():
        name = f"{prefix}[{key}]" if prefix else str(key)
        if value is None:
            continue
        if isinstance(value, dict):
            out.extend(_form(value, name))
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                item_name = f"{name}[{index}]"
                if isinstance(item, dict):
                    out.extend(_form(item, item_name))
                else:
                    out.append((item_name, _scalar(item)))
        else:
            out.append((name, _scalar(value)))
    return out


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _request(method: str, path: str, data: dict | None = None,
             idempotency_key: str | None = None) -> dict:
    if settings.billing_stub_mode:
        raise StripeNotConfigured("STRIPE_SECRET_KEY is not set")
    headers = {"Stripe-Version": "2024-06-20"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    try:
        with _http() as client:
            resp = client.request(method, path, data=_form(data or {}) or None,
                                  headers=headers,
                                  auth=(settings.stripe_secret_key, ""))
    except httpx.HTTPError as exc:
        raise StripeError(f"stripe transport error: {exc}") from exc
    try:
        body = resp.json() or {}
    except ValueError:
        body = {}
    if resp.status_code >= 400:
        message = ((body.get("error") or {}).get("message")) or resp.text[:200]
        raise StripeError(f"stripe HTTP {resp.status_code}: {message}")
    return body


# --------------------------------------------------------------------------
# Objects
# --------------------------------------------------------------------------


def create_customer(*, email: str, user_id: str) -> dict:
    return _request("POST", "/v1/customers",
                    {"email": email, "metadata": {"user_id": user_id}},
                    idempotency_key=f"customer-{user_id}")


def create_subscription_checkout(*, customer_id: str, user_id: str, tier: dict,
                                 trial_days: int, success_url: str, cancel_url: str,
                                 price_id: str | None = None) -> dict:
    """Checkout Session in subscription mode for one monthly tier."""
    if price_id:
        line_item: dict[str, Any] = {"price": price_id, "quantity": 1}
    else:
        line_item = {"quantity": 1, "price_data": {
            "currency": "usd", "unit_amount": tier["price_cents"],
            "recurring": {"interval": "month"},
            "product_data": {"name": f"LeadPilot {tier['name']}"},
        }}
    metadata = {"user_id": user_id, "billing_model": "monthly", "tier": tier["id"]}
    return _request("POST", "/v1/checkout/sessions", {
        "mode": "subscription", "customer": customer_id,
        "line_items": [line_item],
        "subscription_data": {"trial_period_days": trial_days, "metadata": metadata},
        "metadata": metadata, "client_reference_id": user_id,
        "success_url": success_url, "cancel_url": cancel_url,
    })


def create_setup_checkout(*, customer_id: str, user_id: str, success_url: str,
                          cancel_url: str) -> dict:
    """Checkout Session in setup mode: save a card for per-meeting charges."""
    metadata = {"user_id": user_id, "billing_model": "pay_per_meeting",
                "tier": "pay_per_meeting"}
    return _request("POST", "/v1/checkout/sessions", {
        "mode": "setup", "customer": customer_id, "currency": "usd",
        "payment_method_types": ["card"], "metadata": metadata,
        "setup_intent_data": {"metadata": metadata},
        "client_reference_id": user_id,
        "success_url": success_url, "cancel_url": cancel_url,
    })


def cancel_subscription_at_period_end(subscription_id: str) -> dict:
    return _request("POST", f"/v1/subscriptions/{subscription_id}",
                    {"cancel_at_period_end": True})


def cancel_subscription_now(subscription_id: str) -> dict:
    return _request("DELETE", f"/v1/subscriptions/{subscription_id}")


def charge_meeting(*, customer_id: str, amount_cents: int, currency: str,
                   description: str, meeting_id: str) -> dict:
    """One invoice for one meeting: invoice item -> invoice -> finalize.

    Idempotency keys are derived from the meeting id, so a retried sweep can
    never create a second invoice for the same meeting.
    """
    metadata = {"billable_meeting_id": meeting_id}
    item = _request("POST", "/v1/invoiceitems", {
        "customer": customer_id, "amount": amount_cents, "currency": currency,
        "description": description, "metadata": metadata,
    }, idempotency_key=f"meeting-item-{meeting_id}")
    invoice = _request("POST", "/v1/invoices", {
        "customer": customer_id, "collection_method": "charge_automatically",
        "auto_advance": True, "pending_invoice_items_behavior": "include",
        "description": description, "metadata": metadata,
    }, idempotency_key=f"meeting-invoice-{meeting_id}")
    finalized = _request("POST", f"/v1/invoices/{invoice['id']}/finalize",
                         idempotency_key=f"meeting-finalize-{meeting_id}")
    return {"invoice_item_id": item.get("id"), "invoice_id": finalized.get("id"),
            "status": finalized.get("status")}


# --------------------------------------------------------------------------
# Webhooks
# --------------------------------------------------------------------------


def verify_webhook(raw_body: bytes, header: str | None, *, secret: str | None = None,
                   now: float | None = None) -> bool:
    secret = secret if secret is not None else settings.stripe_webhook_secret
    if not secret or not header:
        return False
    parts: dict[str, list[str]] = {}
    for piece in header.split(","):
        key, _, value = piece.strip().partition("=")
        parts.setdefault(key, []).append(value)
    try:
        timestamp = int((parts.get("t") or [""])[0])
    except ValueError:
        return False
    tolerance = max(int(settings.stripe_webhook_tolerance_seconds), 1)
    if abs((now if now is not None else time.time()) - timestamp) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + raw_body,
                        hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, candidate) for candidate in parts.get("v1", []))


def sign_webhook(raw_body: bytes, secret: str, timestamp: int | None = None) -> str:
    """The header Stripe would send. For tests and local webhook replay."""
    ts = int(timestamp if timestamp is not None else time.time())
    digest = hmac.new(secret.encode(), f"{ts}.".encode() + raw_body,
                      hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"

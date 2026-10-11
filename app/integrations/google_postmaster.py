"""Google Postmaster Tools -- the real Gmail spam rate (F03 Deliverability Autopilot).

STATUS: BUILT, DISABLED, UNVERIFIED. Nothing here has been called against a
live Postmaster account. The request and response shapes follow Google's v2
reference as read on 2026-10-11 (URLs in docs/features/f03-deliverability-
autopilot.md); the import only runs when BOTH `deliverability_autopilot_enabled`
and `postmaster_import_enabled` are on AND the user has a Postmaster grant.

WHY v2. Google is retiring the v1 `domains.trafficStats` methods in favour of
v2 `domains.domainStats.query` ("v1 will stop working" once v2 launches), so
v1 is not implemented.

    POST https://gmailpostmastertools.googleapis.com/v2/domains/{domain}/domainStats:query
    scope https://www.googleapis.com/auth/postmaster.traffic.readonly
    body  {"metricDefinitions": [{"name": ..., "baseMetric": {"standardMetric": "SPAM_RATE"}}],
           "timeQuery": {"dateRanges": {"dateRanges": [{"start": Date, "end": Date}]}},
           "aggregationGranularity": "DAILY", "pageSize": <=200, "pageToken": ...}
    resp  {"domainStats": [{"date": Date, "metric": name, "value": {"doubleValue": ...}}],
           "nextPageToken": ...}

UNVERIFIED UNIT. The v2 MetricDefinition page does not say whether SPAM_RATE
is a 0-1 ratio or a percent. v1's userReportedSpamRatio was a ratio, so
SPAM_RATE_UNIT assumes "ratio". A value above 1 cannot be a ratio and is
dropped (and logged) rather than trusted either way.

THE GRANT. There is no connect flow yet: the user's refresh token is read from
integration_tokens (user scope only -- a domain's spam data belongs to that
customer, never to a deployment-wide credential) and exchanged with the
existing Google OAuth app, the same one that mints Gmail tokens.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Callable, Protocol

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://gmailpostmastertools.googleapis.com/v2"
SCOPE = "https://www.googleapis.com/auth/postmaster.traffic.readonly"
PROVIDER = "google_postmaster"
REFRESH_TOKEN_KEY = "refresh_token"
SPAM_RATE_METRIC = "SPAM_RATE"
METRIC_NAME = "spam_rate"
#: UNVERIFIED -- see the module docstring.
SPAM_RATE_UNIT = "ratio"
PAGE_SIZE = 200
MAX_PAGES = 10


class PostmasterError(Exception):
    """The API refused or failed. Never fatal: the proxy stays in use."""


@dataclass(frozen=True)
class SpamReading:
    domain: str
    day: date
    spam_rate: float          # always a 0-1 ratio once it leaves this module


class SpamRateSource(Protocol):
    """The adapter interface. Anything that can say "this domain's Gmail spam
    rate on these days" can stand in for Google -- tests use a fake."""

    def daily_spam_rates(self, domain: str, start: date, end: date) -> list[SpamReading]:
        ...


def _http() -> httpx.Client:
    """Factory tests monkeypatch."""
    return httpx.Client(timeout=20.0)


def _date(d: date) -> dict:
    return {"year": d.year, "month": d.month, "day": d.day}


def _value(value: dict | None) -> float | None:
    if not isinstance(value, dict):
        return None
    for key in ("doubleValue", "floatValue", "intValue"):
        raw = value.get(key)
        if raw is None:
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    return None


def to_ratio(value: float) -> float | None:
    """Normalise to 0-1 under SPAM_RATE_UNIT; None for an impossible value."""
    ratio = value / 100.0 if SPAM_RATE_UNIT == "percent" else value
    if ratio < 0 or ratio > 1:
        return None
    return ratio


def parse_response(domain: str, data: dict) -> list[SpamReading]:
    readings = []
    for stat in (data or {}).get("domainStats") or []:
        if not isinstance(stat, dict) or stat.get("metric") not in (None, METRIC_NAME):
            continue
        d = stat.get("date") or {}
        try:
            day = date(int(d["year"]), int(d["month"]), int(d["day"]))
        except (KeyError, TypeError, ValueError):
            continue
        raw = _value(stat.get("value"))
        if raw is None:
            continue
        ratio = to_ratio(raw)
        if ratio is None:
            logger.warning("postmaster SPAM_RATE %r for %s on %s is not a %s; dropped",
                           raw, domain, day, SPAM_RATE_UNIT)
            continue
        readings.append(SpamReading(domain=domain, day=day, spam_rate=ratio))
    return readings


class GooglePostmasterV2:
    def __init__(self, access_token: Callable[[], str]):
        self._access_token = access_token
        self._token: str | None = None

    def _bearer(self) -> str:
        if self._token is None:
            self._token = self._access_token()
        return self._token

    def daily_spam_rates(self, domain: str, start: date, end: date) -> list[SpamReading]:
        body: dict = {
            "metricDefinitions": [{"name": METRIC_NAME,
                                   "baseMetric": {"standardMetric": SPAM_RATE_METRIC}}],
            "timeQuery": {"dateRanges": {"dateRanges": [{"start": _date(start),
                                                         "end": _date(end)}]}},
            "aggregationGranularity": "DAILY",
            "pageSize": PAGE_SIZE,
        }
        readings: list[SpamReading] = []
        for _ in range(MAX_PAGES):
            try:
                with _http() as client:
                    resp = client.post(f"{API_BASE}/domains/{domain}/domainStats:query",
                                       json=body,
                                       headers={"Authorization": f"Bearer {self._bearer()}"})
            except httpx.HTTPError as exc:
                raise PostmasterError(f"{domain}: {type(exc).__name__}") from exc
            if resp.status_code in (401, 403, 404):
                raise PostmasterError(
                    f"{domain}: HTTP {resp.status_code} -- the domain is not verified in "
                    "Postmaster Tools for this Google account, or the grant lacks "
                    "postmaster.traffic.readonly")
            if resp.status_code >= 400:
                raise PostmasterError(f"{domain}: HTTP {resp.status_code}")
            try:
                data = resp.json()
            except ValueError as exc:
                raise PostmasterError(f"{domain}: response is not JSON") from exc
            readings.extend(parse_response(domain, data))
            token = data.get("nextPageToken") if isinstance(data, dict) else None
            if not token:
                break
            body["pageToken"] = token
        return readings


def get_source(db, user_id) -> GooglePostmasterV2 | None:
    """The user's Postmaster source, or None when they have no grant."""
    from app.integrations.token_store import TokenStore  # noqa: PLC0415

    refresh_token = TokenStore.get(db, user_id=user_id, provider=PROVIDER,
                                   key=REFRESH_TOKEN_KEY)
    if not refresh_token:
        return None

    def access_token() -> str:
        from app.integrations.gmail import get_oauth  # noqa: PLC0415

        try:
            return get_oauth().refresh(refresh_token)["access_token"]
        except (httpx.HTTPError, KeyError) as exc:
            raise PostmasterError(f"could not refresh the Postmaster grant: "
                                  f"{type(exc).__name__}") from exc

    return GooglePostmasterV2(access_token)

"""IP intelligence — is this connection a VPN, proxy, Tor exit or datacenter?

Consulted by app/services/network_guard.py at signup and login. Provider is
configuration (VPN_DETECTION_PROVIDER):

  proxycheck      https://proxycheck.io/v2/<ip>?vpn=1&asn=1  key optional
  ipqualityscore  https://ipqualityscore.com/api/json/ip/<key>/<ip>  key required
  disabled        every IP is clean

Unlike geolocation this module DOES raise (IpIntelligenceError) when the
provider cannot answer: the caller has a real decision to make there -- fail
open or fail closed (VPN_DETECTION_FAIL_CLOSED) -- and a silent "clean" would
take that decision away from it.

Verdicts are cached in Redis per (provider, ip) for VPN_DETECTION_CACHE_SECONDS.
A retried login must not spend a second lookup, and a flood of logins from one
address must not spend thousands. A Redis failure only skips the cache.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

CACHE_PREFIX = "ipintel:"


class IpIntelligenceError(Exception):
    pass


@dataclass
class IpRisk:
    ip: str
    provider: str
    is_vpn: bool = False
    is_proxy: bool = False
    is_tor: bool = False
    is_datacenter: bool = False
    raw: dict = field(default_factory=dict)

    @property
    def reasons(self) -> list[str]:
        return [name for name, flag in (("vpn", self.is_vpn), ("proxy", self.is_proxy),
                                        ("tor", self.is_tor),
                                        ("datacenter", self.is_datacenter)) if flag]

    @property
    def blocked(self) -> bool:
        return bool(self.reasons)


def _http() -> httpx.Client:
    """Factory tests monkeypatch."""
    return httpx.Client(timeout=settings.vpn_detection_timeout_seconds)


class ProxycheckProvider:
    name = "proxycheck"
    # TODO: verify against current proxycheck.io v2 docs (the `type` values,
    # and whether hosting ranges report proxy="yes" with vpn=1)
    URL = "https://proxycheck.io/v2/{ip}"
    _DATACENTER_TYPES = {"hosting", "business", "compromised server", "inference engine"}

    def assess(self, ip: str) -> IpRisk:
        params = {"vpn": 1, "asn": 1}
        if settings.vpn_detection_api_key:
            params["key"] = settings.vpn_detection_api_key
        with _http() as client:
            resp = client.get(self.URL.format(ip=ip), params=params)
        if resp.status_code >= 400:
            raise IpIntelligenceError(f"proxycheck HTTP {resp.status_code}")
        data = resp.json() or {}
        if data.get("status") in ("error", "denied"):
            raise IpIntelligenceError(f"proxycheck: {data.get('message') or data.get('status')}")
        entry = data.get(ip) or {}
        kind = str(entry.get("type") or "").strip().lower()
        flagged = str(entry.get("proxy") or "").lower() == "yes"
        return IpRisk(
            ip=ip, provider=self.name,
            is_vpn=flagged and kind in ("vpn", "openvpn", "wireguard"),
            is_tor=flagged and kind == "tor",
            is_proxy=flagged and kind not in ("vpn", "openvpn", "wireguard", "tor")
            and kind not in self._DATACENTER_TYPES,
            is_datacenter=kind in self._DATACENTER_TYPES,
            raw=entry,
        )


class IpqsProvider:
    name = "ipqualityscore"
    # TODO: verify against current IPQualityScore proxy-detection docs
    URL = "https://ipqualityscore.com/api/json/ip/{key}/{ip}"

    def assess(self, ip: str) -> IpRisk:
        if not settings.vpn_detection_api_key:
            raise IpIntelligenceError("ipqualityscore needs VPN_DETECTION_API_KEY")
        with _http() as client:
            resp = client.get(self.URL.format(key=settings.vpn_detection_api_key, ip=ip),
                              params={"strictness": 1, "allow_public_access_points": "true"})
        if resp.status_code >= 400:
            raise IpIntelligenceError(f"ipqualityscore HTTP {resp.status_code}")
        data = resp.json() or {}
        if data.get("success") is False:
            raise IpIntelligenceError(f"ipqualityscore: {data.get('message')}")
        connection = str(data.get("connection_type") or "").lower()
        return IpRisk(
            ip=ip, provider=self.name,
            is_vpn=bool(data.get("vpn") or data.get("active_vpn")),
            is_tor=bool(data.get("tor") or data.get("active_tor")),
            is_proxy=bool(data.get("proxy")) and not bool(data.get("vpn")),
            is_datacenter=connection == "data center",
            raw={k: data.get(k) for k in ("vpn", "active_vpn", "tor", "active_tor",
                                          "proxy", "connection_type", "fraud_score")},
        )


class DisabledProvider:
    name = "disabled"

    def assess(self, ip: str) -> IpRisk:
        return IpRisk(ip=ip, provider=self.name)


PROVIDERS = {cls.name: cls for cls in (ProxycheckProvider, IpqsProvider, DisabledProvider)}


def get_provider(name: str | None = None):
    key = (name or settings.vpn_detection_provider or "disabled").strip().lower()
    cls = PROVIDERS.get(key)
    if cls is None:
        raise IpIntelligenceError(f"unknown VPN_DETECTION_PROVIDER {key!r}")
    return cls()


def _cache_get(key: str) -> IpRisk | None:
    try:
        from app.core.redis_client import get_sync_redis  # noqa: PLC0415

        raw = get_sync_redis().get(key)
        return IpRisk(**json.loads(raw)) if raw else None
    except Exception:  # noqa: BLE001 -- a cache miss, not an error
        return None


def _cache_set(key: str, risk: IpRisk) -> None:
    try:
        from app.core.redis_client import get_sync_redis  # noqa: PLC0415

        get_sync_redis().set(key, json.dumps(asdict(risk)),
                             ex=max(int(settings.vpn_detection_cache_seconds), 1))
    except Exception:  # noqa: BLE001
        pass


def assess(ip: str) -> IpRisk:
    """The provider's verdict for `ip`, cached. Raises IpIntelligenceError."""
    provider = get_provider()
    key = f"{CACHE_PREFIX}{provider.name}:{ip}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    try:
        risk = provider.assess(ip)
    except IpIntelligenceError:
        raise
    except Exception as exc:  # noqa: BLE001 -- transport errors, bad JSON
        raise IpIntelligenceError(f"{provider.name}: {type(exc).__name__}: {exc}") from exc
    _cache_set(key, risk)
    return risk

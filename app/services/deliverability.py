"""Sending-domain health and blacklist monitoring (Feature Group 9).

WHAT IS CHECKED, per sending domain (the domain of each connected Gmail
address; consumer domains like gmail.com are skipped -- their reputation is
Google's, not the user's):
  * SPF    a TXT record starting "v=spf1"
  * DMARC  a TXT record at _dmarc.<domain> starting "v=DMARC1" (p=none is a
           monitoring-only policy and scores lower than quarantine/reject)
  * DKIM   the Google Workspace selector (google._domainkey). Other
           providers use other selectors, so a miss is "not found under the
           Google selector", scored softer than a missing SPF.
  * bounce rate over the last 30 days of this user's sends
  * blacklists: MXToolbox when a key is configured, otherwise direct DNS
           lookups against the domain blocklists (Spamhaus DBL, SURBL, URIBL).
           Spamhaus answers 127.255.255.x to resolvers it refuses (public DNS
           providers); that is recorded as "unknown", never as listed.
  * Mailreach account score, when a Mailreach key exists.

HEALTH SCORE (0-100): starts at 100; -25 no SPF; -25 no DMARC (-10 for
p=none); -15 DKIM not found; up to -30 for bounces over 2%; -40 if
blacklisted. With Mailreach data the result is the lower of the two scores.

ON A NEW LISTING every active campaign of the user is paused
(campaign_state "paused_blacklist") and a critical domain_blacklisted alert
goes out (push, Slack, webhooks). Delisting does not auto-resume: resuming
after a reputation incident is a human decision, same as the bounce pause.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    DeliverabilityCheck,
    GmailAccount,
    Lead,
    Message,
    MessageStatus,
    Outcome,
    OutcomeEvent,
    Product,
    Strategy,
)

logger = logging.getLogger(__name__)

DOMAIN_BLOCKLISTS = ("dbl.spamhaus.org", "multi.surbl.org", "black.uribl.com")
CONSUMER_DOMAINS = frozenset({"gmail.com", "googlemail.com", "outlook.com", "hotmail.com",
                              "live.com", "yahoo.com", "icloud.com", "aol.com", "proton.me",
                              "protonmail.com"})
PAUSED_BLACKLIST = "paused_blacklist"
MXTOOLBOX_URL = "https://api.mxtoolbox.com/api/v1/Lookup/blacklist/"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---- DNS (patchable) -------------------------------------------------------


def _txt(name: str) -> list[str]:
    import dns.resolver  # noqa: PLC0415

    try:
        answers = dns.resolver.resolve(name, "TXT", lifetime=5)
    except Exception:  # noqa: BLE001 -- NXDOMAIN / NoAnswer / timeout: no record
        return []
    return [b"".join(r.strings).decode(errors="replace") for r in answers]


def _a(name: str) -> list[str]:
    import dns.resolver  # noqa: PLC0415

    try:
        answers = dns.resolver.resolve(name, "A", lifetime=5)
    except Exception:  # noqa: BLE001
        return []
    return [r.address for r in answers]


def _http() -> httpx.Client:
    """Factory tests monkeypatch."""
    return httpx.Client(timeout=20.0)


# ---- checks -----------------------------------------------------------------


def sending_domains(db: Session, user_id) -> list[tuple[str, str]]:
    """[(domain, address)] of the user's connected Gmail accounts."""
    out = []
    for email in db.execute(select(GmailAccount.email_address)
                            .where(GmailAccount.user_id == user_id)).scalars():
        if email and "@" in email:
            domain = email.rsplit("@", 1)[1].lower()
            if domain not in CONSUMER_DOMAINS:
                out.append((domain, email))
    return out


def dns_auth(domain: str) -> dict:
    spf = next((r for r in _txt(domain) if r.lower().startswith("v=spf1")), None)
    dmarc = next((r for r in _txt(f"_dmarc.{domain}") if r.lower().startswith("v=dmarc1")), None)
    policy = None
    if dmarc:
        for part in dmarc.split(";"):
            key, _, value = part.strip().partition("=")
            if key.lower() == "p":
                policy = value.strip().lower()
    dkim = next((r for r in _txt(f"google._domainkey.{domain}")
                 if "v=dkim1" in r.lower() or "p=" in r), None)
    return {"spf": bool(spf), "spf_record": spf, "dmarc": bool(dmarc), "dmarc_policy": policy,
            "dkim": bool(dkim), "dkim_selector": "google"}


def check_blacklists(db: Session, domain: str) -> dict:
    from app.services import credentials  # noqa: PLC0415

    key = credentials.get_secret(db, "mxtoolbox", "api_key")
    if key:
        try:
            with _http() as client:
                resp = client.get(MXTOOLBOX_URL, params={"argument": domain},
                                  headers={"Authorization": key})
            data = resp.json() if resp.status_code < 400 else {}
            failed = [str(f.get("Name") or f.get("name") or "") for f in data.get("Failed") or []]
            if resp.status_code < 400:
                return {"source": "mxtoolbox", "listed_on": [f for f in failed if f],
                        "unknown": [], "checked": len(data.get("Passed") or []) + len(failed)}
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("mxtoolbox lookup for %s failed (%s); using DNSBL", domain, exc)
    listed, unknown = [], []
    for zone in DOMAIN_BLOCKLISTS:
        answers = _a(f"{domain}.{zone}")
        if any(a.startswith("127.255.255.") for a in answers):
            unknown.append(zone)              # resolver refused / rate limited
        elif any(a.startswith("127.") for a in answers):
            listed.append(zone)
    return {"source": "dnsbl", "listed_on": listed, "unknown": unknown,
            "checked": len(DOMAIN_BLOCKLISTS)}


def bounce_rate(db: Session, user_id, days: int = 30) -> float | None:
    since = _now() - timedelta(days=days)
    owned = (select(Lead.id).join(Strategy, Strategy.id == Lead.strategy_id)
             .join(Product, Product.id == Strategy.product_id)
             .where(Product.user_id == user_id))
    sent = db.execute(select(func.count(Message.id)).where(
        Message.lead_id.in_(owned), Message.sent_at >= since,
        Message.status.in_([MessageStatus.SENT, MessageStatus.BOUNCED]))).scalar_one()
    if not sent:
        return None
    bounced = db.execute(select(func.count(Outcome.id)).where(
        Outcome.lead_id.in_(owned), Outcome.event == OutcomeEvent.BOUNCED,
        Outcome.ts >= since)).scalar_one()
    return round(bounced / sent, 4)


def health_score(auth: dict, bounces: float | None, blacklisted: bool) -> tuple[int, list[str]]:
    score, reasons = 100, []
    if not auth.get("spf"):
        score -= 25
        reasons.append("No SPF record")
    if not auth.get("dmarc"):
        score -= 25
        reasons.append("No DMARC record")
    elif auth.get("dmarc_policy") == "none":
        score -= 10
        reasons.append("DMARC policy is p=none (monitoring only)")
    if not auth.get("dkim"):
        score -= 15
        reasons.append("DKIM not found under the Google selector")
    if bounces is not None and bounces > 0.02:
        penalty = min(30, int(round(bounces * 1000)))
        score -= penalty
        reasons.append(f"Bounce rate {bounces:.1%} over the last 30 days")
    if blacklisted:
        score -= 40
        reasons.append("Domain is on a blocklist")
    return max(0, min(100, score)), reasons


def _latest(db: Session, user_id, domain: str, kind: str) -> DeliverabilityCheck | None:
    return db.execute(select(DeliverabilityCheck).where(
        DeliverabilityCheck.user_id == user_id, DeliverabilityCheck.domain == domain,
        DeliverabilityCheck.kind == kind).order_by(DeliverabilityCheck.checked_at.desc())
        .limit(1)).scalar_one_or_none()


def pause_for_blacklist(db: Session, user_id, domain: str, lists: list[str]) -> int:
    strategies = db.execute(
        select(Strategy).join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == user_id, Strategy.campaign_state == "active")
    ).scalars().all()
    for strategy in strategies:
        strategy.campaign_state = PAUSED_BLACKLIST
        strategy.campaign_pause_reason = (f"sending domain {domain} is listed on "
                                          f"{', '.join(lists)} -- delist, then resume")
    db.commit()
    return len(strategies)


def run_checks(db: Session, user_id, now: datetime | None = None) -> dict:
    """Health + blacklist check of every sending domain of one user."""
    from app.integrations import mailreach  # noqa: PLC0415
    from app.services import system_settings  # noqa: PLC0415
    from app.workers import notification_tasks  # noqa: PLC0415

    now = now or _now()
    user_id = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    threshold = system_settings.get(db, "deliverability_health_threshold")
    results = []
    bounces = bounce_rate(db, user_id)
    for domain, address in sending_domains(db, user_id):
        previous_bl = _latest(db, user_id, domain, "blacklist")
        previous_health = _latest(db, user_id, domain, "health")
        blacklist = check_blacklists(db, domain)
        listed = bool(blacklist["listed_on"])
        db.add(DeliverabilityCheck(user_id=user_id, domain=domain, kind="blacklist",
                                   source=blacklist["source"], ok=not listed,
                                   listed_on=blacklist["listed_on"], details_json=blacklist,
                                   checked_at=now))
        auth = dns_auth(domain)
        score, reasons = health_score(auth, bounces, listed)
        source, mailreach_data = "dns", None
        try:
            client = mailreach.get_client(db, user_id)
            mailreach_data = client.account_health(address) if client else None
        except Exception as exc:  # noqa: BLE001 -- optional enrichment
            logger.warning("mailreach health for %s failed: %s", address, exc)
        if mailreach_data and mailreach_data.get("score") is not None:
            source = "mailreach"
            if mailreach_data["score"] < score:
                reasons.append(f"Mailreach reputation {mailreach_data['score']}")
            score = min(score, mailreach_data["score"])
        db.add(DeliverabilityCheck(
            user_id=user_id, domain=domain, kind="health", source=source, score=score,
            ok=score >= threshold,
            details_json={**auth, "bounce_rate": bounces, "reasons": reasons,
                          "mailreach": {k: v for k, v in (mailreach_data or {}).items()
                                        if k != "raw"} or None},
            checked_at=now))
        db.commit()

        paused = 0
        if listed and (previous_bl is None or previous_bl.ok is not False):
            paused = pause_for_blacklist(db, user_id, domain, blacklist["listed_on"])
            notification_tasks.enqueue_event(
                user_id, "domain_blacklisted", title=f"{domain} is blacklisted",
                body=(f"Your sending domain is listed on {', '.join(blacklist['listed_on'])}. "
                      f"{paused} campaign(s) were paused to protect your reputation."),
                deep_link="/settings?tab=deliverability",
                data={"domain": domain},
                webhook_payload={"domain": domain, "listed_on": blacklist["listed_on"],
                                 "campaigns_paused": paused})
        if score < threshold and (previous_health is None or (previous_health.score or 0)
                                  >= threshold):
            notification_tasks.enqueue_event(
                user_id, "deliverability_warning", title=f"Email health {score}/100 for {domain}",
                body="; ".join(reasons) or "Health score below your threshold.",
                deep_link="/settings?tab=deliverability", data={"domain": domain},
                webhook_payload={"domain": domain, "score": score, "reasons": reasons})
        results.append({"domain": domain, "score": score, "listed_on": blacklist["listed_on"],
                        "campaigns_paused": paused})
    return {"domains": results}


def run_all(db: Session) -> dict:
    from app.services import system_settings  # noqa: PLC0415

    if not system_settings.get(db, "blacklist_monitoring_enabled"):
        return {"users": 0, "disabled": True}
    users = db.execute(select(GmailAccount.user_id).distinct()).scalars().all()
    failed = 0
    for user_id in users:
        try:
            run_checks(db, user_id)
        except Exception:
            db.rollback()
            failed += 1
            logger.exception("deliverability check for user %s failed", user_id)
    return {"users": len(users), "failed": failed}


def status(db: Session, user_id) -> dict:
    from app.services import system_settings  # noqa: PLC0415

    domains = []
    for domain, address in sending_domains(db, user_id):
        health = _latest(db, user_id, domain, "health")
        blacklist = _latest(db, user_id, domain, "blacklist")
        history = db.execute(select(DeliverabilityCheck.checked_at, DeliverabilityCheck.score)
                             .where(DeliverabilityCheck.user_id == user_id,
                                    DeliverabilityCheck.domain == domain,
                                    DeliverabilityCheck.kind == "health")
                             .order_by(DeliverabilityCheck.checked_at.desc()).limit(30)).all()
        domains.append({
            "domain": domain, "address": address,
            "health": ({"score": health.score, "source": health.source,
                        "checked_at": health.checked_at.isoformat(),
                        "details": health.details_json} if health else None),
            "blacklist": ({"listed_on": blacklist.listed_on or [],
                           "unknown": (blacklist.details_json or {}).get("unknown", []),
                           "source": blacklist.source,
                           "checked_at": blacklist.checked_at.isoformat()} if blacklist else None),
            "history": [{"checked_at": ts.isoformat(), "score": s} for ts, s in reversed(history)],
        })
    return {"threshold": system_settings.get(db, "deliverability_health_threshold"),
            "monitoring_enabled": system_settings.get(db, "blacklist_monitoring_enabled"),
            "domains": domains}


def launch_warning(db: Session, user_id) -> str | None:
    """A warning for a campaign launch when the latest health is low."""
    from app.services import system_settings  # noqa: PLC0415

    threshold = system_settings.get(db, "deliverability_health_threshold")
    for domain, _ in sending_domains(db, user_id):
        latest = _latest(db, user_id, domain, "health")
        if latest is not None and latest.score is not None and latest.score < threshold:
            return (f"Email health for {domain} is {latest.score}/100 (below {threshold}). "
                    "Sending now risks the spam folder -- see Settings > Deliverability.")
    return None

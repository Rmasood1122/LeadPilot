"""F03 Deliverability Autopilot (docs/features/f03-deliverability-autopilot.md).

EXTENDS what Feature Group 9 (deliverability.py) and Part 1 Feature 4
(mailbox_health.py) built; it does not replace either:

  * PREFLIGHT. deliverability.launch_warning only WARNS about a sick domain.
    With the Autopilot on, a campaign launch (enroll, manager approval,
    resume) is BLOCKED when the mailbox it will send from fails SPF / DKIM /
    DMARC alignment, or when the one-click unsubscribe headers (RFC 8058) are
    missing from the message the send path actually builds. DNS is read
    through deliverability._txt -- the same reader the health score uses --
    and every function takes an injectable `txt` so tests never touch DNS.
    A safety guard: it fails CLOSED (a lookup that fails reads as "not
    found", and a preflight that crashes blocks).

  * SEND-TIME HEADER GUARD. require_one_click_headers() refuses an outbound
    email without both headers (ComplianceError -> FAILED, never sent).

  * BRAKES. brake_for() turns a spam rate into a minimum mailbox state:
    >= 0.10% throttled, >= 0.30% paused -- applied by mailbox_health.refresh
    on top of the score, so the score can only make it worse.

  * POSTMASTER. The real Gmail spam rate (google_postmaster adapter) stored as
    deliverability_checks rows (kind "postmaster") and used by
    mailbox_health in place of the proxy while fresh. Built, disabled by its
    own flag, UNVERIFIED against a live account.

The stepped new-mailbox ramp lives where the ramp always lived:
sequence_engine.daily_allowance (`stepped=True`).

Nothing here does anything while `deliverability_autopilot_enabled` is off.
"""

from __future__ import annotations

import email
import email.policy
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ChannelType,
    DeliverabilityCheck,
    GmailAccount,
    Product,
    Sequence,
    SequenceStep,
    Strategy,
)
from app.services import mailbox_health

logger = logging.getLogger(__name__)

Txt = Callable[[str], list[str]]

FLAG = "deliverability_autopilot_enabled"
IMPORT_FLAG = "postmaster_import_enabled"
SELECTORS_SETTING = "deliverability_dkim_selectors"

#: The Gmail API sends through Google's servers, so the SPF chain must reach
#: Google's include for SPF to pass on the actual send path.
GOOGLE_SPF_INCLUDE = "_spf.google.com"
#: RFC 7208 section 4.6.4: more than 10 DNS-querying terms is a permerror.
SPF_LOOKUP_LIMIT = 10
ONE_CLICK_POST_VALUE = "List-Unsubscribe=One-Click"
DMARC_POLICIES = ("none", "quarantine", "reject")

#: The brakes reuse mailbox_health's danger lines -- one definition of
#: "0.10%" and "0.30%" in the codebase, not two that can drift.
SPAM_WARN = mailbox_health.COMPLAINT_WARN    # 0.001
SPAM_BAD = mailbox_health.COMPLAINT_BAD      # 0.003

#: A Postmaster reading is used for this many days after the day it covers.
#: Postmaster data lags a day or two; older than this, the proxy returns.
POSTMASTER_MAX_AGE_DAYS = 5
POSTMASTER_LOOKBACK_DAYS = 7

PREFLIGHT_KIND = "preflight"
POSTMASTER_KIND = "postmaster"
POSTMASTER_SOURCE = "postmaster"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enabled(db: Session) -> bool:
    from app.services import system_settings  # noqa: PLC0415

    return bool(system_settings.get(db, FLAG))


def import_enabled(db: Session) -> bool:
    from app.services import system_settings  # noqa: PLC0415

    return enabled(db) and bool(system_settings.get(db, IMPORT_FLAG))


def _default_txt(name: str) -> list[str]:
    # Resolved at call time so a test that patches deliverability._txt is
    # honoured here too.
    from app.services import deliverability  # noqa: PLC0415

    return deliverability._txt(name)


def _tags(record: str) -> dict[str, str]:
    out = {}
    for part in record.split(";"):
        key, sep, value = part.strip().partition("=")
        if sep:
            out[key.strip().lower()] = value.strip()
    return out


def _spf_records(txt: Txt, name: str) -> list[str]:
    return [r.strip() for r in txt(name) if r.strip().lower().startswith("v=spf1")]


# --------------------------------------------------------------------------
# SPF / DKIM / DMARC
# --------------------------------------------------------------------------


class _SpfLimit(Exception):
    pass


def _spf_reaches_google(record: str, txt: Txt, seen: set[str], lookups: list[int]) -> bool:
    for term in record.split()[1:]:
        term = term.strip().lower()
        if term[:1] in ("-", "~", "?"):
            continue          # a non-pass qualifier never authorises
        term = term.lstrip("+")
        if term.startswith("include:"):
            target = term[len("include:"):]
        elif term.startswith("redirect="):
            target = term[len("redirect="):]
        else:
            continue
        lookups[0] += 1
        if lookups[0] > SPF_LOOKUP_LIMIT:
            raise _SpfLimit()
        if target == GOOGLE_SPF_INCLUDE:
            return True
        if target in seen or "%" in target:
            continue
        seen.add(target)
        nested = _spf_records(txt, target)
        if len(nested) == 1 and _spf_reaches_google(nested[0], txt, seen, lookups):
            return True
    return False


def check_spf(domain: str, txt: Txt) -> dict:
    records = _spf_records(txt, domain)
    if not records:
        return {"name": "spf", "ok": False,
                "detail": f"No SPF record on {domain} (or the DNS lookup failed). Publish "
                          f"a TXT record like 'v=spf1 include:{GOOGLE_SPF_INCLUDE} ~all'."}
    if len(records) > 1:
        return {"name": "spf", "ok": False,
                "detail": f"{domain} publishes {len(records)} SPF records; RFC 7208 makes "
                          "that a permanent error. Merge them into one."}
    try:
        reaches = _spf_reaches_google(records[0], txt, {domain}, [0])
    except _SpfLimit:
        return {"name": "spf", "ok": False, "record": records[0],
                "detail": f"The SPF record of {domain} needs more than "
                          f"{SPF_LOOKUP_LIMIT} DNS lookups (permerror). Flatten it."}
    if not reaches:
        return {"name": "spf", "ok": False, "record": records[0],
                "detail": f"The SPF record of {domain} does not authorise Google's servers, "
                          f"which send this mailbox's mail. Add include:{GOOGLE_SPF_INCLUDE}."}
    return {"name": "spf", "ok": True, "record": records[0], "detail": "SPF authorises Google"}


def selectors_from(value: str | None) -> list[str]:
    found = [s.strip().lower() for s in (value or "").split(",") if s.strip()]
    return found or ["google"]


def check_dkim(domain: str, txt: Txt, selectors: list[str]) -> dict:
    revoked = []
    for selector in selectors:
        for record in txt(f"{selector}._domainkey.{domain}"):
            tags = _tags(record)
            if "p" not in tags:
                continue
            if tags["p"]:
                return {"name": "dkim", "ok": True, "selector": selector,
                        "detail": f"DKIM key published under '{selector}'"}
            revoked.append(selector)
    if revoked:
        return {"name": "dkim", "ok": False,
                "detail": f"The DKIM key of {domain} under {', '.join(revoked)} is revoked "
                          "(empty p=). Generate a new key in Google Admin."}
    return {"name": "dkim", "ok": False,
            "detail": f"No DKIM key for {domain} under selector(s) {', '.join(selectors)} "
                      "(or the DNS lookup failed). Turn on DKIM signing in Google Admin, "
                      "or add your selector to deliverability_dkim_selectors."}


def _org_domain(domain: str) -> str:
    """Last two labels. No Public Suffix List -- see the spec's Unverified."""
    labels = domain.split(".")
    return ".".join(labels[-2:]) if len(labels) > 2 else domain


def check_dmarc(domain: str, txt: Txt) -> dict:
    def records(name: str) -> list[str]:
        return [r.strip() for r in txt(f"_dmarc.{name}")
                if r.strip().lower().startswith("v=dmarc1")]

    found_at, recs = domain, records(domain)
    if not recs and _org_domain(domain) != domain:
        found_at, recs = _org_domain(domain), records(_org_domain(domain))
    if not recs:
        return {"name": "dmarc", "ok": False,
                "detail": f"No DMARC record at _dmarc.{domain} (or the DNS lookup failed). "
                          "Gmail and Yahoo require one; 'v=DMARC1; p=none' is the minimum."}
    if len(recs) > 1:
        return {"name": "dmarc", "ok": False,
                "detail": f"_dmarc.{found_at} has {len(recs)} DMARC records; receivers "
                          "ignore all of them. Keep one."}
    tags = _tags(recs[0])
    policy = (tags.get("sp") if found_at != domain and tags.get("sp") else tags.get("p"))
    policy = (policy or "").lower()
    if policy not in DMARC_POLICIES:
        return {"name": "dmarc", "ok": False, "record": recs[0],
                "detail": f"The DMARC record at _dmarc.{found_at} has no valid p= policy."}
    out = {"name": "dmarc", "ok": True, "record": recs[0], "policy": policy,
           "found_at": found_at, "detail": f"DMARC p={policy}"}
    if policy == "none":
        out["warning"] = (f"DMARC on {found_at} is p=none (monitoring only). It meets "
                          "Gmail's requirement; quarantine or reject protects the domain.")
    return out


def check_alignment(spf: dict, dkim: dict, dmarc: dict) -> dict:
    """DMARC passes only when SPF or DKIM passes ALIGNED with the From domain.
    Gmail sends with envelope-from and DKIM d= equal to the mailbox domain once
    SPF/DKIM are set up for it, so alignment holds iff DMARC exists and at
    least one of the two is in place."""
    ok = bool(dmarc["ok"] and (spf["ok"] or dkim["ok"]))
    if ok:
        detail = "DMARC can pass aligned via " + " and ".join(
            n for n, c in (("SPF", spf), ("DKIM", dkim)) if c["ok"])
    elif not dmarc["ok"]:
        detail = "DMARC alignment cannot be evaluated without a valid DMARC record."
    else:
        detail = "Neither SPF nor DKIM can pass aligned with the From domain, so DMARC fails."
    return {"name": "alignment", "ok": ok, "detail": detail}


# --------------------------------------------------------------------------
# One-click unsubscribe, on the bytes the send path really produces
# --------------------------------------------------------------------------


def _one_click_route_registered() -> bool:
    from app.api.unsubscribe import router  # noqa: PLC0415

    return any(getattr(r, "path", None) == "/unsubscribe/{token}"
               and "POST" in (getattr(r, "methods", None) or set())
               for r in router.routes)


def check_one_click(from_address: str | None) -> dict:
    """Push a synthetic message through build_compliant_email AND the Gmail
    MIME builder, parse the bytes, and check what a receiver would see."""
    from app.db.models import Lead  # noqa: PLC0415
    from app.integrations.gmail import build_mime  # noqa: PLC0415
    from app.integrations.outreach_base import OutboundMessage  # noqa: PLC0415
    from app.services import sequence_engine as engine  # noqa: PLC0415

    problems: list[str] = []
    try:
        probe = Lead(id=uuid.uuid4(), email="preflight@example.invalid", enrichment_json={})
        subject, body, headers, _token = engine.build_compliant_email(
            probe, "Deliverability preflight", "Preflight probe.")
        outbound = OutboundMessage(message_id="preflight", lead_id=str(probe.id),
                                   to_address=probe.email, subject=subject, body=body,
                                   headers=headers)
        raw = build_mime(from_address, outbound).as_bytes()
        parsed = email.message_from_bytes(raw, policy=email.policy.default)
    except Exception as exc:  # noqa: BLE001 -- a probe that cannot run fails closed
        logger.exception("one-click unsubscribe probe failed")
        return {"name": "one_click_unsubscribe", "ok": False,
                "detail": f"Could not build a test message ({type(exc).__name__}); "
                          "launching is blocked until it can."}

    list_unsub = str(parsed.get("List-Unsubscribe") or "")
    list_post = str(parsed.get("List-Unsubscribe-Post") or "").strip()
    urls = re.findall(r"<([^>]+)>", list_unsub)
    https = [u.strip() for u in urls if u.strip().lower().startswith("https://")]
    if not list_unsub:
        problems.append("the List-Unsubscribe header is missing")
    elif not https:
        problems.append("List-Unsubscribe has no HTTPS URL (RFC 8058 requires one) -- "
                        "set PUBLIC_BASE_URL to the public https address")
    if list_post != ONE_CLICK_POST_VALUE:
        problems.append(f"List-Unsubscribe-Post is missing or not '{ONE_CLICK_POST_VALUE}'")
    if https:
        token = https[0].rstrip("/").rsplit("/", 1)[-1]
        try:
            if engine.parse_unsubscribe_token(token) != probe.id:
                problems.append("the unsubscribe link does not identify the recipient")
        except Exception:  # noqa: BLE001
            problems.append("the unsubscribe link carries a token the endpoint cannot read")
        if "/unsubscribe/" not in https[0]:
            problems.append("the unsubscribe link does not point at /unsubscribe/<token>")
    # The PARSED headers above are decoded, so an RFC 2047 encoded or folded
    # header used to pass here while receivers could not use it (gaps-sweep-2
    # review). RFC 2369 / 8058: the transmitted value must be the raw <URI>
    # and the exact Post value, each on one line.
    from app.core.mime_policy import raw_header_lines  # noqa: PLC0415

    for name in ("List-Unsubscribe", "List-Unsubscribe-Post"):
        for block in raw_header_lines(raw, name):
            if any("=?" in line for line in block):
                problems.append(f"{name} is RFC 2047 encoded in the transmitted bytes")
            if len(block) > 1:
                problems.append(f"{name} is folded across lines in the transmitted bytes")
    if not _one_click_route_registered():
        problems.append("POST /unsubscribe/{token} (the one-click endpoint) is not registered")
    if problems:
        return {"name": "one_click_unsubscribe", "ok": False,
                "detail": "One-click unsubscribe: " + "; ".join(problems) + "."}
    return {"name": "one_click_unsubscribe", "ok": True,
            "detail": "List-Unsubscribe (HTTPS) and List-Unsubscribe-Post are on the "
                      "message the send path builds"}


def require_one_click_headers(headers: dict | None) -> None:
    """Send-time guard: an email without both RFC 8058 headers never sends."""
    from app.core.exceptions import ComplianceError  # noqa: PLC0415

    headers = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    if (not headers.get("list-unsubscribe")
            or headers.get("list-unsubscribe-post", "").strip() != ONE_CLICK_POST_VALUE):
        raise ComplianceError(
            "one-click unsubscribe headers (List-Unsubscribe + List-Unsubscribe-Post) "
            "are missing from this email",
            rule="rfc8058_one_click_unsubscribe",
            remediation="restore the headers in sequence_engine.build_compliant_email")


# --------------------------------------------------------------------------
# The preflight
# --------------------------------------------------------------------------


def _owner_id(db: Session, strategy: Strategy):
    return db.get(Product, strategy.product_id).user_id


def sequence_sends_email(db: Session, sequence: Sequence) -> bool:
    channels = {step_channel or sequence.channel for step_channel in db.execute(
        select(SequenceStep.channel).where(SequenceStep.sequence_id == sequence.id)
    ).scalars()}
    return ChannelType.EMAIL in (channels or {sequence.channel})


def strategy_sends_email(db: Session, strategy: Strategy) -> bool:
    return any(sequence_sends_email(db, s) for s in db.execute(
        select(Sequence).where(Sequence.strategy_id == strategy.id)).scalars())


def preflight(db: Session, strategy: Strategy, *, sequence: Sequence | None = None,
              txt: Txt | None = None, now: datetime | None = None) -> dict:
    """The full report. Never writes. `applies` is False for a campaign that
    sends no email -- there is nothing to authenticate."""
    from app.services import deliverability, system_settings  # noqa: PLC0415

    txt = txt or _default_txt
    now = now or _now()
    applies = (sequence_sends_email(db, sequence) if sequence is not None
               else strategy_sends_email(db, strategy))
    report: dict = {"ok": True, "applies": applies, "checked_at": now.isoformat(),
                    "mailboxes": [], "unsubscribe": None, "blocking": [], "warnings": []}
    if not applies:
        return report

    owner_id = _owner_id(db, strategy)
    accounts = db.execute(select(GmailAccount).where(GmailAccount.user_id == owner_id)
                          .order_by(GmailAccount.created_at)).scalars().all()
    if not accounts:
        report["blocking"].append("No Gmail mailbox is connected to send this campaign from.")
    selectors = selectors_from(system_settings.get(db, SELECTORS_SETTING))
    for account in accounts:
        address = account.email_address or ""
        domain = address.rsplit("@", 1)[1].lower() if "@" in address else None
        entry: dict = {"address": address or None, "domain": domain,
                       "provider_managed": False, "checks": []}
        if domain is None:
            entry["checks"].append({"name": "mailbox", "ok": False,
                                    "detail": "The connected mailbox has no address."})
        elif domain in deliverability.CONSUMER_DOMAINS:
            entry["provider_managed"] = True
            entry["checks"] = [{"name": n, "ok": True,
                                "detail": f"{domain} is signed and authorised by its provider"}
                               for n in ("spf", "dkim", "dmarc", "alignment")]
        else:
            spf = check_spf(domain, txt)
            dkim = check_dkim(domain, txt, selectors)
            dmarc = check_dmarc(domain, txt)
            entry["checks"] = [spf, dkim, dmarc, check_alignment(spf, dkim, dmarc)]
            if dmarc.get("warning"):
                report["warnings"].append(dmarc["warning"])
        for check in entry["checks"]:
            if not check["ok"]:
                report["blocking"].append(f"{address or 'mailbox'}: {check['detail']}")
        report["mailboxes"].append(entry)

    report["unsubscribe"] = check_one_click(accounts[0].email_address if accounts else None)
    if not report["unsubscribe"]["ok"]:
        report["blocking"].append(report["unsubscribe"]["detail"])
    report["ok"] = not report["blocking"]
    return report


def record(db: Session, strategy: Strategy, report: dict, *, action: str,
           sequence: Sequence | None = None, now: datetime | None = None) -> None:
    """One deliverability_checks row per mailbox domain -- pass or fail -- so
    "zero launches with failing auth" is a query, not a claim."""
    now = now or _now()
    owner_id = _owner_id(db, strategy)
    context = {"action": action, "strategy_id": str(strategy.id),
               "sequence_id": str(sequence.id) if sequence is not None else None}
    domains = [mb["domain"] or "-" for mb in report["mailboxes"]] or ["-"]
    for domain in dict.fromkeys(domains):
        db.add(DeliverabilityCheck(user_id=owner_id, domain=domain[:253], kind=PREFLIGHT_KIND,
                                   source="preflight", ok=bool(report["ok"]),
                                   details_json={**report, **context}, checked_at=now))
    db.commit()


def launch_block(db: Session, strategy: Strategy, *, action: str,
                 sequence: Sequence | None = None, txt: Txt | None = None) -> str | None:
    """None when the launch may proceed, else the 409 detail. Flag off: None,
    with no DNS lookup and no row written -- behaviour exactly as before."""
    if not enabled(db):
        return None
    try:
        report = preflight(db, strategy, sequence=sequence, txt=txt)
    except Exception as exc:  # noqa: BLE001 -- a safety guard fails closed
        db.rollback()
        logger.exception("deliverability preflight crashed for strategy %s", strategy.id)
        return (f"Deliverability preflight could not run ({type(exc).__name__}); the launch "
                "is blocked until it can.")
    if not report["applies"]:
        return None
    record(db, strategy, report, action=action, sequence=sequence)
    if report["ok"]:
        return None
    return ("Deliverability preflight failed: " + " ".join(report["blocking"])
            + " Fix these, then launch again (Settings > Deliverability).")


# --------------------------------------------------------------------------
# Brakes
# --------------------------------------------------------------------------

_SEVERITY = {mailbox_health.HEALTHY: 0, mailbox_health.THROTTLED: 1, mailbox_health.PAUSED: 2}


def brake_for(spam_rate: float | None) -> str | None:
    if spam_rate is None:
        return None
    if spam_rate >= SPAM_BAD:
        return mailbox_health.PAUSED
    if spam_rate >= SPAM_WARN:
        return mailbox_health.THROTTLED
    return None


def apply_brake(state: str, brake: str | None) -> str:
    """The more severe of the two -- a brake never makes a state better."""
    if brake is None:
        return state
    return brake if _SEVERITY[brake] > _SEVERITY.get(state, 0) else state


# --------------------------------------------------------------------------
# Postmaster readings
# --------------------------------------------------------------------------


def postmaster_reading(db: Session, user_id, domain: str | None,
                       now: datetime | None = None) -> dict | None:
    """The latest fresh Postmaster spam rate for one of THIS user's domains."""
    from datetime import date as date_cls  # noqa: PLC0415

    if not domain:
        return None
    now = now or _now()
    row = db.execute(select(DeliverabilityCheck).where(
        DeliverabilityCheck.user_id == mailbox_health._uuid(user_id),
        DeliverabilityCheck.domain == domain,
        DeliverabilityCheck.kind == POSTMASTER_KIND,
    ).order_by(DeliverabilityCheck.checked_at.desc()).limit(1)).scalar_one_or_none()
    if row is None:
        return None
    details = row.details_json or {}
    try:
        day = date_cls.fromisoformat(str(details["day"]))
        rate = float(details["spam_rate"])
    except (KeyError, TypeError, ValueError):
        return None
    if (now.astimezone(timezone.utc).date() - day).days > POSTMASTER_MAX_AGE_DAYS:
        return None
    return {"spam_rate": rate, "day": day.isoformat()}


def import_spam_rates(db: Session, user_id, *, now: datetime | None = None,
                      source=None) -> dict:
    """Pull the last week of Postmaster spam rates for each of one user's own
    sending domains and store the latest day. Then re-score the user's
    mailboxes so a brake applies today, not at the next 4-hourly sweep."""
    from app.integrations import google_postmaster  # noqa: PLC0415
    from app.services import deliverability  # noqa: PLC0415

    now = now or _now()
    user_id = mailbox_health._uuid(user_id)
    source = source if source is not None else google_postmaster.get_source(db, user_id)
    if source is None:
        return {"connected": False, "domains": []}
    end = now.astimezone(timezone.utc).date()
    start = end - timedelta(days=POSTMASTER_LOOKBACK_DAYS)
    results, imported = [], 0
    for domain in dict.fromkeys(d for d, _ in deliverability.sending_domains(db, user_id)):
        try:
            readings = [r for r in source.daily_spam_rates(domain, start, end)
                        if r.domain == domain]
        except google_postmaster.PostmasterError as exc:
            logger.warning("postmaster import for %s failed: %s", domain, exc)
            results.append({"domain": domain, "error": str(exc)})
            continue
        if not readings:
            results.append({"domain": domain, "reading": None})
            continue
        latest = max(readings, key=lambda r: r.day)
        db.add(DeliverabilityCheck(
            user_id=user_id, domain=domain, kind=POSTMASTER_KIND, source="google_postmaster",
            ok=latest.spam_rate < SPAM_WARN,
            details_json={"spam_rate": latest.spam_rate, "day": latest.day.isoformat(),
                          "unit": google_postmaster.SPAM_RATE_UNIT,
                          "readings": [{"day": r.day.isoformat(), "spam_rate": r.spam_rate}
                                       for r in sorted(readings, key=lambda r: r.day)]},
            checked_at=now))
        db.commit()
        imported += 1
        results.append({"domain": domain, "reading": {"spam_rate": latest.spam_rate,
                                                       "day": latest.day.isoformat()}})
    if imported:
        mailbox_health.refresh(db, user_id, now=now, check_dns=False)
    return {"connected": True, "domains": results}


def import_all(db: Session, now: datetime | None = None) -> dict:
    """The daily sweep. Disabled unless BOTH flags are on. One user's failure
    never stops the others."""
    if not import_enabled(db):
        return {"disabled": True, "users": 0}
    users = db.execute(select(GmailAccount.user_id).distinct()).scalars().all()
    imported = failed = 0
    for user_id in users:
        try:
            if import_spam_rates(db, user_id, now=now).get("connected"):
                imported += 1
        except Exception:  # noqa: BLE001
            db.rollback()
            failed += 1
            logger.exception("postmaster import failed for user %s", user_id)
    return {"users": len(users), "connected": imported, "failed": failed}

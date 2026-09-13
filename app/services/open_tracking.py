"""Email open tracking (Feature Group 3).

HOW
Outreach email gains an HTML alternative part carrying a 1x1 pixel whose URL
is `/t/o/<token>.gif`. The token is the message id plus a truncated
HMAC-SHA256 under a key derived from SECRET_KEY, so a pixel URL cannot be
forged or enumerated, and a bad token is rejected BEFORE any database read.
The plain-text part is unchanged and still comes first.

WHAT AN "OPEN" IS WORTH -- read before trusting the numbers
  * Apple Mail Privacy Protection loads every image through a proxy shortly
    after delivery whether or not anyone reads the mail. It inflates opens.
  * Mail security scanners (Defender, Mimecast, Proofpoint) fetch images on
    delivery. Loads within `open_prefetch_seconds` of sending are ignored for
    that reason; later scanner loads cannot be told apart.
  * Clients that block images never register an open at all.
So opens are a DIRECTIONAL signal. Reply-based metrics remain the ground
truth, and the smart-send-time windows weight a reply three times an open.

WHO IS NOT TRACKED
Leads in the EU/EEA/UK (compliance_region.open_tracking_allowed), and
everyone when the admin turns `open_tracking_enabled` off.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import re
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Lead, Message, Outcome, OutcomeEvent, Strategy

# The smallest valid transparent GIF.
PIXEL_GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
_MAC_BYTES = 12


def _key() -> bytes:
    secret = (settings.jwt_secret or "leadpilot-dev-only").encode()
    return hashlib.sha256(b"open-pixel:" + secret).digest()


def make_token(message_id) -> str:
    raw = uuid.UUID(str(message_id)).bytes
    mac = hmac.new(_key(), raw, hashlib.sha256).digest()[:_MAC_BYTES]
    return base64.urlsafe_b64encode(raw + mac).decode().rstrip("=")


def parse_token(token: str) -> uuid.UUID | None:
    try:
        data = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    except (ValueError, TypeError):
        return None
    if len(data) != 16 + _MAC_BYTES:
        return None
    raw, mac = data[:16], data[16:]
    expected = hmac.new(_key(), raw, hashlib.sha256).digest()[:_MAC_BYTES]
    if not hmac.compare_digest(mac, expected):
        return None
    return uuid.UUID(bytes=raw)


def pixel_url(message_id) -> str:
    return f"{settings.public_base_url.rstrip('/')}/t/o/{make_token(message_id)}.gif"


def tracking_enabled(session: Session, lead: Lead) -> bool:
    from app.services import compliance_region, system_settings  # noqa: PLC0415

    return (bool(system_settings.get(session, "open_tracking_enabled"))
            and compliance_region.open_tracking_allowed(lead))


_URL = re.compile(r"https?://[^\s<>\"']+")
_TRAILING = ".,;:!?)"


def _linkify(escaped: str, click_url=None) -> str:
    def repl(m: re.Match) -> str:
        url = m.group(0)
        tail = ""
        while url and url[-1] in _TRAILING:
            tail = url[-1] + tail
            url = url[:-1]
        # Feature A2: the href may point at the click redirect; the visible
        # text is always the real destination, so the reader sees where the
        # link goes.
        href = html.escape(click_url(html.unescape(url))) if click_url else url
        return f'<a href="{href}">{url}</a>{tail}'
    return _URL.sub(repl, escaped)


def html_body(text: str, pixel: str | None, click_url=None) -> str:
    """The HTML twin of a plain-text email: same words, links clickable,
    paragraphs kept, plus the pixel. No styling -- cold email that looks
    like a newsletter is filtered like one.

    `click_url`, when given, maps a destination URL to its tracked redirect
    (click tracking, off by default -- see system setting click_tracking_enabled)."""
    paragraphs = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    parts = [f"<p>{_linkify(html.escape(p), click_url).replace(chr(10), '<br>')}</p>"
             for p in paragraphs]
    if pixel:
        parts.append(f'<img src="{html.escape(pixel)}" width="1" height="1" alt="" '
                     'style="display:block;border:0;width:1px;height:1px">')
    return "<html><body>" + "".join(parts) + "</body></html>"


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def record_open(session: Session, message_id: uuid.UUID, *,
                user_agent: str | None = None, now: datetime | None = None) -> str:
    """Apply one pixel load. Returns what happened, for logs and tests:
    recorded | repeat | prefetch | not_sent | unknown."""
    from app.services import sequence_engine, system_settings  # noqa: PLC0415

    now = now or datetime.now(timezone.utc)
    message = session.get(Message, message_id)
    if message is None:
        return "unknown"
    sent_at = _aware(message.sent_at)
    if sent_at is None:
        return "not_sent"
    if (now - sent_at).total_seconds() < system_settings.get(session, "open_prefetch_seconds"):
        return "prefetch"

    message.open_count = (message.open_count or 0) + 1
    if message.opened_at is not None:
        session.commit()
        return "repeat"

    message.opened_at = now
    lead = session.get(Lead, message.lead_id)
    local = now.astimezone(ZoneInfo(sequence_engine.lead_timezone(lead))) if lead else now
    session.add(Outcome(
        lead_id=message.lead_id, message_id=message.id,
        strategy_id=lead.strategy_id if lead else None, variant=message.variant,
        event=OutcomeEvent.OPENED, channel="email",
        meta_json={"local_dow": local.weekday(), "local_hour": local.hour,
                   "user_agent": (user_agent or "")[:200], "source": "pixel"},
    ))
    session.commit()
    if lead is not None:
        _maybe_compute_windows(session, lead.strategy_id)
    return "recorded"


# --------------------------------------------------------------------------
# Feature A2: click tracking
# --------------------------------------------------------------------------
#
# /t/c/<token>?u=<destination>. The token is the message id plus an HMAC over
# (message id, destination), so the redirect can never be pointed at a URL the
# message did not contain -- an unauthenticated redirect that accepted any `u`
# would be an open redirector on our domain, which phishing uses and spam
# filters punish.


def _click_mac(raw: bytes, url: str) -> bytes:
    return hmac.new(_key(), b"click:" + raw + url.encode(), hashlib.sha256).digest()[:_MAC_BYTES]


def make_click_token(message_id, url: str) -> str:
    raw = uuid.UUID(str(message_id)).bytes
    return base64.urlsafe_b64encode(raw + _click_mac(raw, url)).decode().rstrip("=")


def parse_click_token(token: str, url: str) -> uuid.UUID | None:
    try:
        data = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    except (ValueError, TypeError):
        return None
    if len(data) != 16 + _MAC_BYTES or not url.lower().startswith(("http://", "https://")):
        return None
    raw, mac = data[:16], data[16:]
    if not hmac.compare_digest(mac, _click_mac(raw, url)):
        return None
    return uuid.UUID(bytes=raw)


def click_url(message_id, url: str) -> str:
    from urllib.parse import quote  # noqa: PLC0415

    return (f"{settings.public_base_url.rstrip('/')}/t/c/{make_click_token(message_id, url)}"
            f"?u={quote(url, safe='')}")


def click_tracking_enabled(session: Session, lead: Lead) -> bool:
    from app.services import system_settings  # noqa: PLC0415

    return tracking_enabled(session, lead) and bool(
        system_settings.get(session, "click_tracking_enabled"))


def record_click(session: Session, message_id: uuid.UUID, url: str, *,
                 now: datetime | None = None) -> str:
    """Apply one click. recorded | repeat | prefetch | not_sent | unknown.

    Only the FIRST click on a given link of a given message writes a CLICKED
    outcome; security scanners that follow links on delivery are ignored with
    the same prefetch window as the open pixel."""
    from app.services import system_settings  # noqa: PLC0415

    now = now or datetime.now(timezone.utc)
    message = session.get(Message, message_id)
    if message is None:
        return "unknown"
    sent_at = _aware(message.sent_at)
    if sent_at is None:
        return "not_sent"
    if (now - sent_at).total_seconds() < system_settings.get(session, "open_prefetch_seconds"):
        return "prefetch"
    earlier = session.execute(
        select(Outcome.meta_json).where(Outcome.message_id == message.id,
                                        Outcome.event == OutcomeEvent.CLICKED)
    ).scalars().all()
    if any((meta or {}).get("url") == url[:500] for meta in earlier):
        return "repeat"
    lead = session.get(Lead, message.lead_id)
    session.add(Outcome(
        lead_id=message.lead_id, message_id=message.id,
        strategy_id=lead.strategy_id if lead else None, variant=message.variant,
        event=OutcomeEvent.CLICKED, channel=message.channel.value if message.channel else "email",
        meta_json={"url": url[:500], "source": "click_redirect"},
    ))
    session.commit()
    return "recorded"


def strategy_open_count(session: Session, strategy_id) -> int:
    return session.execute(
        select(func.count(Outcome.id))
        .join(Lead, Lead.id == Outcome.lead_id)
        .where(Lead.strategy_id == strategy_id, Outcome.event == OutcomeEvent.OPENED)
    ).scalar_one()


def _maybe_compute_windows(session: Session, strategy_id) -> None:
    """First time a campaign crosses the open threshold, compute its windows
    right away rather than waiting for the nightly refresh."""
    from app.services import system_settings  # noqa: PLC0415
    from app.workers import analytics_tasks  # noqa: PLC0415

    strategy = session.get(Strategy, strategy_id)
    if strategy is None or strategy.send_windows_computed_at is not None:
        return
    if strategy_open_count(session, strategy_id) >= system_settings.get(
            session, "send_time_min_opens"):
        analytics_tasks.enqueue_send_windows(strategy_id)

"""Client-facing shareable ROI dashboard (Feature A6).

A founder sends their client (or their own boss) a link; the recipient sees
pipeline, meetings booked and revenue attributed, read-only, with no account.

THE LINK IS THE CREDENTIAL, so it is treated like an API key
(app/services/api_keys.py): 32 bytes of `secrets` randomness, shown once, only
its SHA-256 stored, every link has an expiry, and revocation is immediate.
`resolve()` answers the same "not found" for unknown, expired and revoked
tokens, so the public endpoint is not an oracle for which tokens once existed.

WHAT IS SHOWN is built on the existing ROI engine (roi_calculator, the same six
metrics the in-app ROI card uses) plus the daily roi_snapshots trend and a
pipeline-stage count -- aggregates only. No lead name, email, company, message
text or strategy document ever reaches the public payload; a test pins that.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Lead,
    LeadStatus,
    Product,
    ROISnapshot,
    ShareLink,
    Strategy,
    User,
    Workspace,
)

TOKEN_BYTES = 32
PERIOD_DAYS = 90
MAX_EXPIRY_DAYS = 365
PIPELINE_STAGES = [
    ("contacted", "Contacted", [LeadStatus.CONTACTED]),
    ("replied", "Replied", [LeadStatus.REPLIED]),
    ("meeting_booked", "Meeting booked", [LeadStatus.MEETING_BOOKED]),
    ("proposal_sent", "Proposal sent", [LeadStatus.PROPOSAL_SENT, LeadStatus.OPPORTUNITY]),
    ("won", "Won", [LeadStatus.CLOSED_WON]),
]


class ShareLinkError(ValueError):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def share_url(token: str) -> str:
    from app.config import settings  # noqa: PLC0415

    return f"{settings.frontend_url.rstrip('/')}/share/roi?token={token}"


def owned_strategy_ids(session: Session, user_id) -> list:
    return list(session.execute(
        select(Strategy.id).join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == user_id).order_by(Strategy.created_at)
    ).scalars())


def create(session: Session, *, owner: User, actor: User | None, label: str,
           strategy_id=None, expires_in_days: int = 30,
           now: datetime | None = None) -> tuple[ShareLink, str]:
    now = now or _now()
    if not 1 <= int(expires_in_days) <= MAX_EXPIRY_DAYS:
        raise ShareLinkError(f"expires_in_days must be between 1 and {MAX_EXPIRY_DAYS}")
    if strategy_id is not None and strategy_id not in owned_strategy_ids(session, owner.id):
        raise ShareLinkError("campaign not found", status_code=404)
    token = secrets.token_urlsafe(TOKEN_BYTES)
    link = ShareLink(user_id=owner.id, created_by_user_id=actor.id if actor else owner.id,
                     strategy_id=strategy_id, label=(label or "ROI dashboard").strip()[:120],
                     token_hash=hash_token(token), token_prefix=token[:8],
                     expires_at=now + timedelta(days=int(expires_in_days)))
    session.add(link)
    session.commit()
    return link, token


def status(link: ShareLink, now: datetime | None = None) -> str:
    now = now or _now()
    if link.revoked_at is not None:
        return "revoked"
    if _aware(link.expires_at) <= now:
        return "expired"
    return "active"


def revoke(session: Session, link: ShareLink, now: datetime | None = None) -> ShareLink:
    if link.revoked_at is None:
        link.revoked_at = now or _now()
        session.commit()
    return link


def resolve(session: Session, token: str, now: datetime | None = None) -> ShareLink | None:
    """The live link for a token, or None for unknown, expired or revoked."""
    if not token or len(token) > 200:
        return None
    link = session.execute(
        select(ShareLink).where(ShareLink.token_hash == hash_token(token))
    ).scalar_one_or_none()
    if link is None or status(link, now) != "active":
        return None
    return link


def link_out(link: ShareLink, now: datetime | None = None) -> dict:
    return {
        "id": str(link.id), "label": link.label, "token_prefix": link.token_prefix,
        "strategy_id": str(link.strategy_id) if link.strategy_id else None,
        "scope": "campaign" if link.strategy_id else "account",
        "status": status(link, now),
        "expires_at": _aware(link.expires_at).isoformat(),
        "revoked_at": _aware(link.revoked_at).isoformat() if link.revoked_at else None,
        "last_viewed_at": _aware(link.last_viewed_at).isoformat() if link.last_viewed_at else None,
        "view_count": link.view_count or 0,
        "created_at": _aware(link.created_at).isoformat() if link.created_at else None,
    }


def _money(value) -> str:
    return str(Decimal(str(value or 0)).quantize(Decimal("0.01")))


def public_dashboard(session: Session, link: ShareLink, now: datetime | None = None) -> dict:
    """The read-only payload. Records the view. Aggregates only -- no PII."""
    from app.services import roi_calculator  # noqa: PLC0415
    from app.services.revenue_analytics import primary_currency  # noqa: PLC0415

    now = now or _now()
    date_to = now.date()
    date_from = date_to - timedelta(days=PERIOD_DAYS - 1)
    strategy_ids = [link.strategy_id] if link.strategy_id else owned_strategy_ids(session, link.user_id)

    totals = {"meetings_booked": 0, "messages_sent": 0, "leads_contacted": 0,
              "leads_replied": 0, "pipeline_value": Decimal("0"),
              "revenue_attributed": Decimal("0"), "time_saved_hours": 0.0}
    for strategy_id in strategy_ids:
        metrics = roi_calculator.compute_roi_snapshot(session, strategy_id, date_from, date_to)
        if metrics.get("error"):
            continue
        for key in totals:
            totals[key] += metrics.get(key) or 0
    reply_rate = (round(100.0 * totals["leads_replied"] / totals["leads_contacted"], 1)
                  if totals["leads_contacted"] else 0.0)

    counts = dict(session.execute(
        select(Lead.status, func.count(Lead.id))
        .where(Lead.strategy_id.in_(strategy_ids) if strategy_ids else False)
        .group_by(Lead.status)
    ).all()) if strategy_ids else {}
    pipeline = [{"key": key, "label": label,
                 "count": int(sum(counts.get(s, 0) for s in statuses))}
                for key, label, statuses in PIPELINE_STAGES]

    trend_rows = session.execute(
        select(ROISnapshot.snapshot_date, func.sum(ROISnapshot.meetings_booked),
               func.sum(ROISnapshot.pipeline_value), func.sum(ROISnapshot.revenue_attributed))
        .where(ROISnapshot.strategy_id.in_(strategy_ids) if strategy_ids else False,
               ROISnapshot.snapshot_date >= date_from)
        .group_by(ROISnapshot.snapshot_date).order_by(ROISnapshot.snapshot_date)
    ).all() if strategy_ids else []
    trend = [{"date": str(day), "meetings_booked": int(meetings or 0),
              "pipeline_value": _money(pipeline_value), "revenue_attributed": _money(revenue)}
             for day, meetings, pipeline_value, revenue in trend_rows]

    workspace = session.execute(
        select(Workspace).where(Workspace.owner_user_id == link.user_id)).scalar_one_or_none()
    brand = None
    if workspace is not None:
        brand = {"name": (workspace.brand_name if workspace.white_label_enabled and workspace.brand_name
                          else workspace.name),
                 "logo_url": workspace.logo_url if workspace.white_label_enabled else None,
                 "primary_color": workspace.primary_color if workspace.white_label_enabled else None}
    campaign_name = None
    if link.strategy_id:
        strategy = session.get(Strategy, link.strategy_id)
        product = session.get(Product, strategy.product_id) if strategy else None
        campaign_name = product.name if product else None

    link.view_count = (link.view_count or 0) + 1
    link.last_viewed_at = now
    session.commit()

    return {
        "title": link.label,
        "brand": brand,
        "scope": {"type": "campaign" if link.strategy_id else "account",
                  "campaign_name": campaign_name, "campaigns": len(strategy_ids)},
        "period": {"date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
                   "days": PERIOD_DAYS},
        "currency": primary_currency(session, link.user_id),
        "totals": {
            "meetings_booked": int(totals["meetings_booked"]),
            "messages_sent": int(totals["messages_sent"]),
            "leads_contacted": int(totals["leads_contacted"]),
            "reply_rate": reply_rate,
            "pipeline_value": _money(totals["pipeline_value"]),
            "revenue_attributed": _money(totals["revenue_attributed"]),
            "time_saved_hours": round(float(totals["time_saved_hours"]), 1),
        },
        "pipeline": pipeline,
        "trend": trend,
        "generated_at": now.isoformat(),
        "expires_at": _aware(link.expires_at).isoformat(),
    }


def get_owned(session: Session, link_id, user_id) -> ShareLink:
    try:
        link = session.get(ShareLink, uuid.UUID(str(link_id)))
    except ValueError:
        link = None
    if link is None or link.user_id != user_id:
        raise ShareLinkError("share link not found", status_code=404)
    return link


def group_trend_by_week(trend: list[dict]) -> list[dict]:
    """Server-side helper kept for exports; the page groups client-side too."""
    weeks: dict[str, int] = defaultdict(int)
    for point in trend:
        day = datetime.fromisoformat(point["date"]).date()
        weeks[(day - timedelta(days=day.weekday())).isoformat()] += point["meetings_booked"]
    return [{"week_start": w, "meetings_booked": n} for w, n in sorted(weeks.items())]

"""Founder / agency mode: per-client workspaces (Part 1, Feature 11).

WHAT AN AGENCY ACTUALLY NEEDS, and what they get here:

  SEPARATE REPORTING        every number a client sees is computed over that
                            client's campaigns only. `report()` takes a client
                            and scopes to its strategies -- there is no
                            "filter the shared dashboard" step that someone
                            can forget.
  SEPARATE SENDING DOMAINS  a client's prospects must never see another
                            client's sending domain. `domain_allowed()` is
                            checked in the send path, not just rendered in a
                            settings page.
  SEPARATE BILLING VIEW     what this client is owed for this month, and what
                            it cost to deliver -- per client, in that client's
                            currency.

WHY THIS IS NOT `workspaces`. That table is a TEAM around one owner
(`owner_user_id` is UNIQUE), and its own docstring says the workspace's data is
its owner's data. An agency's SDRs are shared across every client; the clients
are separate books of business. A client therefore hangs OFF the team workspace
rather than replacing it, and isolation is achieved by scoping.

THE UNASSIGNED CASE IS FIRST-CLASS. A strategy with no client is the agency's
own work, not an error and not a client that does not exist. An account that
never creates a client workspace behaves exactly as it does today -- which is
the property that makes this safe to ship to every account at once.
"""

from __future__ import annotations

import logging
import re
import secrets
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ClientSendingDomain,
    ClientWorkspace,
    Deal,
    DealStage,
    Lead,
    Message,
    MessageStatus,
    Outcome,
    OutcomeEvent,
    Product,
    Strategy,
    Workspace,
)

logger = logging.getLogger(__name__)

ACTIVE, PAUSED, ARCHIVED = "active", "paused", "archived"
STATUSES = (ACTIVE, PAUSED, ARCHIVED)

_DOMAIN = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (slug or "client")[:40]


class ClientError(ValueError):
    """A refusal the API turns into a 422 with this message."""


# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------


def create(db: Session, workspace: Workspace, *, name: str, **fields) -> ClientWorkspace:
    """Add a client. The slug is derived and made unique within the agency."""
    name = (name or "").strip()
    if not name:
        raise ClientError("a client needs a name")
    base = _slugify(name)
    slug = base
    while db.execute(select(ClientWorkspace.id).where(
            ClientWorkspace.workspace_id == workspace.id,
            ClientWorkspace.slug == slug)).first():
        slug = f"{base}-{secrets.token_hex(2)}"

    client = ClientWorkspace(workspace_id=workspace.id, name=name[:200], slug=slug)
    _apply(client, fields)
    db.add(client)
    db.commit()
    return client


def _apply(client: ClientWorkspace, fields: dict) -> None:
    for key in ("contact_name", "contact_email", "billing_email", "billing_reference",
                "notes"):
        if key in fields and fields[key] is not None:
            setattr(client, key, str(fields[key])[:320] or None)
    for key in ("monthly_fee_cents", "per_meeting_fee_cents"):
        if key in fields and fields[key] is not None:
            value = int(fields[key])
            if value < 0:
                raise ClientError(f"{key} cannot be negative")
            setattr(client, key, value)
    if fields.get("currency"):
        setattr(client, "currency", str(fields["currency"]).upper()[:3])
    if fields.get("status"):
        status = str(fields["status"]).lower()
        if status not in STATUSES:
            raise ClientError(f"status must be one of {', '.join(STATUSES)}")
        client.status = status
        client.archived_at = _now() if status == ARCHIVED else None


def update(db: Session, client: ClientWorkspace, fields: dict) -> ClientWorkspace:
    if "name" in fields and fields["name"]:
        client.name = str(fields["name"]).strip()[:200]
    _apply(client, fields)
    db.commit()
    return client


def clients(db: Session, workspace: Workspace, *,
            include_archived: bool = False) -> list[ClientWorkspace]:
    query = select(ClientWorkspace).where(ClientWorkspace.workspace_id == workspace.id)
    if not include_archived:
        query = query.where(ClientWorkspace.status != ARCHIVED)
    return list(db.execute(query.order_by(ClientWorkspace.name)).scalars())


def owned(db: Session, workspace: Workspace, client_id) -> ClientWorkspace | None:
    """404-shaped lookup: a client in another agency simply does not exist."""
    client = db.get(ClientWorkspace, client_id)
    if client is None or client.workspace_id != workspace.id:
        return None
    return client


# --------------------------------------------------------------------------
# Assignment
# --------------------------------------------------------------------------


def strategies_for(db: Session, client: ClientWorkspace) -> list[Strategy]:
    return list(db.execute(select(Strategy).where(
        Strategy.client_workspace_id == client.id)).scalars())


def assign_strategy(db: Session, strategy: Strategy,
                    client: ClientWorkspace | None) -> Strategy:
    """Move a campaign to a client, or back to the agency's own work (None).

    Deliberately allowed while a campaign is running: an agency that wins a
    client mid-flight should not have to stop outreach to file it correctly.
    """
    strategy.client_workspace_id = client.id if client is not None else None
    db.commit()
    return strategy


# --------------------------------------------------------------------------
# The sending-domain pool
# --------------------------------------------------------------------------


def add_domain(db: Session, client: ClientWorkspace, domain: str,
               note: str | None = None) -> ClientSendingDomain:
    domain = (domain or "").strip().lower().lstrip("@")
    if not _DOMAIN.match(domain):
        raise ClientError(f"'{domain}' is not a domain name")
    existing = db.execute(select(ClientSendingDomain).where(
        ClientSendingDomain.client_workspace_id == client.id,
        ClientSendingDomain.domain == domain)).scalar_one_or_none()
    if existing is not None:
        return existing
    row = ClientSendingDomain(client_workspace_id=client.id, domain=domain,
                              note=(note or "")[:200] or None)
    db.add(row)
    db.commit()
    return row


def remove_domain(db: Session, client: ClientWorkspace, domain: str) -> bool:
    row = db.execute(select(ClientSendingDomain).where(
        ClientSendingDomain.client_workspace_id == client.id,
        ClientSendingDomain.domain == (domain or "").strip().lower())).scalar_one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def pool(db: Session, client: ClientWorkspace) -> list[str]:
    return [row.domain for row in db.execute(
        select(ClientSendingDomain)
        .where(ClientSendingDomain.client_workspace_id == client.id)
        .order_by(ClientSendingDomain.domain)).scalars()]


def domain_allowed(db: Session, strategy: Strategy, address: str | None) -> str | None:
    """May this campaign send from this address? None = yes.

    AN EMPTY POOL MEANS NO RESTRICTION -- an agency that has not set pools up
    sends exactly as it does today, and the pool only ever narrows. A campaign
    with no client is unrestricted for the same reason: it is the agency's own
    work, not a client's.

    Never raises: this runs in the send path, and a broken pool lookup must
    not stop outreach it was only ever meant to route.
    """
    try:
        if strategy is None or strategy.client_workspace_id is None or not address:
            return None
        client = db.get(ClientWorkspace, strategy.client_workspace_id)
        if client is None:
            return None
        allowed = pool(db, client)
        if not allowed:
            return None
        domain = address.rsplit("@", 1)[-1].strip().lower()
        if domain in allowed:
            return None
        return (f"{client.name}'s campaigns may only send from "
                f"{', '.join(allowed)} — this mailbox is on {domain}")
    except Exception:  # noqa: BLE001 -- see the docstring
        logger.exception("client sending-domain check failed for strategy %s",
                         getattr(strategy, "id", None))
        return None


# --------------------------------------------------------------------------
# Reporting, scoped to one client
# --------------------------------------------------------------------------


def _strategy_ids(db: Session, client: ClientWorkspace) -> list:
    return [row for row in db.execute(select(Strategy.id).where(
        Strategy.client_workspace_id == client.id)).scalars()]


def report(db: Session, client: ClientWorkspace, *, date_from: date | None = None,
           date_to: date | None = None) -> dict:
    """Every number for ONE client, computed over that client's campaigns.

    Scoped at the query, not filtered afterwards: there is no step here that
    someone can forget, and no path by which another client's prospect can
    appear in this total.
    """
    ids = _strategy_ids(db, client)
    if not ids:
        return {"client_id": str(client.id), "name": client.name,
                "strategies": 0, "leads": 0, "sent": 0, "replies": 0,
                "meetings": 0, "won": 0, "reply_rate": None, "meeting_rate": None,
                "revenue_cents": 0, "currency": client.currency}

    leads = db.execute(select(func.count(Lead.id))
                       .where(Lead.strategy_id.in_(ids))).scalar_one()
    sent = db.execute(
        select(func.count(Message.id))
        .join(Lead, Lead.id == Message.lead_id)
        .where(Lead.strategy_id.in_(ids), Message.status == MessageStatus.SENT)
    ).scalar_one()

    def _events(event: OutcomeEvent) -> int:
        query = select(func.count(Outcome.id)).join(
            Lead, Lead.id == Outcome.lead_id).where(
            Lead.strategy_id.in_(ids), Outcome.event == event)
        if date_from:
            query = query.where(Outcome.ts >= datetime.combine(
                date_from, datetime.min.time(), tzinfo=timezone.utc))
        if date_to:
            query = query.where(Outcome.ts <= datetime.combine(
                date_to, datetime.max.time(), tzinfo=timezone.utc))
        return db.execute(query).scalar_one()

    replies = _events(OutcomeEvent.REPLIED)
    meetings = _events(OutcomeEvent.BOOKED)
    won = _events(OutcomeEvent.WON)
    revenue = db.execute(
        select(func.coalesce(func.sum(Deal.value_cents), 0))
        .where(Deal.strategy_id.in_(ids), Deal.stage == DealStage.WON)
    ).scalar_one()

    return {
        "client_id": str(client.id),
        "name": client.name,
        "strategies": len(ids),
        "leads": leads,
        "sent": sent,
        "replies": replies,
        "meetings": meetings,
        "won": won,
        # None, never 0.0, on an empty denominator: a client whose campaign
        # has not sent yet has no reply rate, and 0% reads as failure in a
        # report someone is about to forward to that client.
        "reply_rate": round(replies / sent, 4) if sent else None,
        "meeting_rate": round(meetings / sent, 4) if sent else None,
        "revenue_cents": int(revenue or 0),
        "currency": client.currency,
    }


def billing_view(db: Session, client: ClientWorkspace,
                 now: datetime | None = None) -> dict:
    """What this client owes for the current month, and how it was earned.

    Deliberately shows the WORKING, not just a total: a retainer plus a
    per-meeting fee times a meeting count is an invoice a client will query,
    and an agency that cannot show the count loses the argument.
    """
    now = now or _now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ids = _strategy_ids(db, client)

    meetings = 0
    if ids:
        meetings = db.execute(
            select(func.count(Outcome.id))
            .join(Lead, Lead.id == Outcome.lead_id)
            .where(Lead.strategy_id.in_(ids), Outcome.event == OutcomeEvent.BOOKED,
                   Outcome.ts >= month_start)
        ).scalar_one()

    retainer = int(client.monthly_fee_cents or 0)
    per_meeting = int(client.per_meeting_fee_cents or 0)
    variable = per_meeting * meetings
    return {
        "client_id": str(client.id),
        "name": client.name,
        "currency": client.currency,
        "period_start": month_start.date().isoformat(),
        "retainer_cents": retainer,
        "per_meeting_fee_cents": per_meeting,
        "meetings_this_period": meetings,
        "variable_cents": variable,
        "total_cents": retainer + variable,
        "billing_email": client.billing_email,
        "billing_reference": client.billing_reference,
        # The working, so an invoice can be defended line by line.
        "lines": [
            *([{"label": "Monthly retainer", "amount_cents": retainer}]
              if retainer else []),
            *([{"label": f"{meetings} meeting{'s' if meetings != 1 else ''} booked "
                         f"x {per_meeting / 100:.2f}",
                "amount_cents": variable}] if per_meeting else []),
        ],
    }


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def client_out(db: Session, client: ClientWorkspace) -> dict:
    return {
        "id": str(client.id),
        "name": client.name,
        "slug": client.slug,
        "status": client.status,
        "contact_name": client.contact_name,
        "contact_email": client.contact_email,
        "billing_email": client.billing_email,
        "billing_reference": client.billing_reference,
        "monthly_fee_cents": client.monthly_fee_cents,
        "per_meeting_fee_cents": client.per_meeting_fee_cents,
        "currency": client.currency,
        "notes": client.notes,
        "sending_domains": pool(db, client),
        "strategy_count": len(_strategy_ids(db, client)),
        "archived_at": client.archived_at.isoformat() if client.archived_at else None,
        "created_at": client.created_at.isoformat() if client.created_at else None,
    }


def overview(db: Session, workspace: Workspace, user_id) -> dict:
    """The agency's own screen: every client, plus what is NOT assigned.

    The unassigned bucket is shown rather than hidden, because work that
    belongs to nobody is exactly the work that stops being invoiced.
    """
    rows = clients(db, workspace)
    unassigned = db.execute(
        select(func.count(Strategy.id))
        .join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == user_id, Strategy.client_workspace_id.is_(None))
    ).scalar_one()
    return {
        "clients": [{**client_out(db, client), **report(db, client)} for client in rows],
        "unassigned_strategies": unassigned,
        "note": ("Campaigns with no client are the agency's own work. "
                 "Assign them to bill for them."),
    }

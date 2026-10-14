"""Private email network (Growth plan and up, flag email_network_enabled).

The LinkedIn network's twin for the people a user already emails
(docs/features/email-network.md). Every query below is filtered on
current_user.id; there is no endpoint, flag or parameter that reads another
account's contacts or another account's Gmail.

  GET    /email-network/status            plan, flag, counts, last import, Gmail state
  POST   /email-network/import            ONE file as the raw request body:
                                          Google / Outlook CSV, vCard, or an mbox
                                          (streamed, headers only, never spooled
                                          to disk). ?attested=true is required.
  POST   /email-network/gmail-scan        scan the connected Gmail (headers only)
  GET    /email-network/gmail-scan        the latest scan's progress
  POST   /email-network/analyze           re-filter + re-score now
  GET    /email-network/recommendations   matches per product, with the why
  GET    /email-network/campaigns         the account's campaigns a contact can join
  POST   /email-network/add-to-campaign   contacts -> leads (+ normal verification)
  GET    /email-network/messages          saved first emails
  POST   /email-network/messages/draft    AI draft (metered, never sent)
  PUT    /email-network/messages/{id}     save the user's words
  POST   /email-network/messages/{id}/attach   use as the lead's first campaign email
  POST   /email-network/messages/{id}/detach
  DELETE /email-network                   erase everything imported (never gated)
  DELETE /email-network/contacts/{id}     erase one contact (never gated)

ROLES: import = owner or manager; Gmail scan = the account OWNER only (it reads
the owner's own mailbox); viewers and SDRs can read the contacts list and
recommendations, exactly as with the LinkedIn network.

Nothing here sends anything. A saved first email is sent, if ever, by the
campaign's normal send path (app/workers/outreach_tasks.send_message_impl).
"""

# NOTE: deliberately NO `from __future__ import annotations` (FastAPI).

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.metering import metered
from app.core.plans import PLANS, PlanLimitExceeded, plan_limit_response
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import (
    ChannelType, EmailNetworkMessage, Product, Sequence, SequenceStatus, Strategy, User,
)
from app.services import email_network as en
from app.services import email_network_filter as flt
from app.services import email_network_gmail as eng
from app.services import email_network_messages as enm
from app.services import email_network_parse as parse
from app.services import security_audit

router = APIRouter(prefix="/email-network", tags=["email-network"])

UPGRADE_TO = "growth"


# --------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------


def _require_plan(user: User) -> None:
    if en.is_eligible(user):
        return
    plan = getattr(user.plan, "value", user.plan) or "free"
    raise HTTPException(status_code=402, detail=plan_limit_response(PlanLimitExceeded(
        limit_key=en.PLAN_KEY, current_plan=plan, upgrade_to=UPGRADE_TO,
        message=f"{PLANS.get(plan, PLANS['free'])['display_name']} plan does not include "
                "the email network. Upgrade to Growth or higher.")))


def _require_enabled(db: Session) -> None:
    if not en.enabled(db):
        raise HTTPException(status_code=409,
                            detail="The email network is switched off on this server.")


def _require_manager(request: Request) -> None:
    """Reading a mailbox is the account's business: owner or manager only."""
    from app.services import rbac  # noqa: PLC0415

    if not rbac.at_least(getattr(request.state, "workspace_role", "owner"), "manager"):
        raise HTTPException(status_code=403,
                            detail="Only the account owner or a manager can import contacts.")


def _gate(db: Session, user: User) -> None:
    _require_plan(user)
    _require_enabled(db)


def _run(fn, *args):
    try:
        return fn(*args)
    except (enm.MessageError, en.EmailNetworkError) as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


# --------------------------------------------------------------------------
# Status
# --------------------------------------------------------------------------


@router.get("/status")
def status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict:
    """Readable on every plan and with the flag off, so the page can explain."""
    plan = getattr(current_user.plan, "value", current_user.plan) or "free"
    eligible = en.is_eligible(current_user)
    last = en.last_import(db, current_user.id)
    return {
        "eligible": eligible, "plan": plan, "upgrade_to": None if eligible else UPGRADE_TO,
        "feature_enabled": en.enabled(db),
        "contact_count": en.contact_count(db, current_user.id),
        "last_import": en.import_out(last) if last else None,
        "needs_new_import": en.stale(db, current_user.id),
        "gmail": eng.gmail_state(db, current_user),
        "attestation": {"version": en.ATTESTATION_VERSION, "text": en.ATTESTATION_TEXT},
        "limits": {"mbox_max_bytes": parse.MBOX_MAX_BYTES,
                   "contacts_max_bytes": parse.CONTACTS_MAX_BYTES,
                   "max_messages": parse.MAX_MESSAGES,
                   "max_contact_rows": parse.MAX_CONTACT_ROWS,
                   "gmail_max_messages": eng.MAX_MESSAGES},
        "exclusion_labels": flt.LABELS,
    }


# --------------------------------------------------------------------------
# Import (raw body; mbox streamed)
# --------------------------------------------------------------------------


def _attested(attested: bool, version: str | None) -> bool:
    return bool(attested) and version == en.ATTESTATION_VERSION


#: Your other addresses travel in a HEADER, not the query string, so they
#: never reach access logs (review round LOW). Comma-separated, max 2,000 chars.
OWN_ADDRESSES_HEADER = "x-own-addresses"
FEED_BATCH = 1024 * 1024


@router.post("/import")
async def import_file(
    request: Request,
    attested: bool = Query(default=False),
    attestation_version: str | None = Query(default=None, max_length=10),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Body: the file itself (any Content-Type). Read in chunks; an mbox is
    parsed AS IT STREAMS (headers only) and never held whole or written to
    disk. Plan, flag, role, the attestation and the rate limit are checked
    BEFORE the body is read. All parsing, storing and scoring runs in the
    thread pool, never on the event loop (review round H1)."""
    _gate(db, current_user)
    _require_manager(request)
    if not _attested(attested, attestation_version):
        raise HTTPException(status_code=422,
                            detail="Confirm that these are your own business contacts first.")
    enforce_rate_limit(str(current_user.id), "email_network_import", "RATE_LIMIT_AI_ACTION")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > parse.MBOX_MAX_BYTES:
        raise HTTPException(status_code=413, detail="That file is larger than 300 MB.")
    from urllib.parse import unquote  # noqa: PLC0415

    own_extra = flt.parse_own_addresses(
        unquote(request.headers.get(OWN_ADDRESSES_HEADER) or "")[:2000])

    head = b""
    stream = request.stream()
    async for chunk in stream:
        head += chunk
        if len(head) >= 4096:
            break
    if not head.strip():
        raise HTTPException(status_code=422, detail="The file is empty.")
    try:
        kind = parse.detect(head[:4096])
    except parse.ParseError as exc:
        raise HTTPException(status_code=422, detail=exc.user_message) from exc

    if kind == parse.MBOX:
        own = await run_in_threadpool(flt.own_identity, db, current_user, own_extra)
        mbox = parse.MboxStream(parse.Tally(own=own))
        capped_bytes = False
        try:
            buffer = bytearray(head)
            async for chunk in stream:
                if mbox.bytes_read + len(buffer) + len(chunk) > parse.MBOX_MAX_BYTES:
                    capped_bytes = True
                    break
                buffer += chunk
                if len(buffer) >= FEED_BATCH:
                    await run_in_threadpool(mbox.feed, bytes(buffer))
                    buffer = bytearray()
                    if mbox.capped:
                        break
            if buffer and not mbox.capped:
                await run_in_threadpool(mbox.feed, bytes(buffer))
            await run_in_threadpool(mbox.close)
        except parse.ParseError as exc:
            raise HTTPException(status_code=422, detail=exc.user_message) from exc
        if mbox.messages_seen == 0:
            raise HTTPException(status_code=422, detail="No messages were found in this file.")
        out = await run_in_threadpool(_run, lambda: en.finish_mbox(
            db, current_user, mbox, attested=True, capped_bytes=capped_bytes))
    else:
        data = bytearray(head)
        async for chunk in stream:
            data += chunk
            if len(data) > parse.CONTACTS_MAX_BYTES:
                raise HTTPException(status_code=413,
                                    detail="A contacts file can be at most 20 MB.")
        payload = bytes(data)
        del data
        out = await run_in_threadpool(_run, lambda: en.import_contacts_file(
            db, current_user, payload, attested=True, own_extra=own_extra))
    # Counts only: never names, addresses, subjects or bodies.
    security_audit.record(db, action=security_audit.EMAIL_NETWORK_IMPORTED, request=request,
                          user_id=current_user.id, target_type="email_network",
                          details={k: out[k] for k in ("kind", "people_found", "added",
                                                       "updated", "excluded")})
    db.commit()
    return out


@router.delete("/contacts/{contact_id}")
def delete_contact(contact_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)) -> dict:
    """Delete ONE of your email contacts, its scores and its saved first
    email. Never plan- or flag-gated. 404 for anyone else's contact."""
    out = _run(en.delete_contact, db, current_user, contact_id)
    security_audit.record(db, action=security_audit.EMAIL_NETWORK_ERASED, request=request,
                          user_id=current_user.id, target_type="email_contact",
                          target_id=contact_id, details=out)
    db.commit()
    return out


# --------------------------------------------------------------------------
# Gmail scan
# --------------------------------------------------------------------------


class ScanIn(BaseModel):
    attested: bool = False
    attestation_version: str | None = Field(default=None, max_length=10)
    own_addresses: list[str] = Field(default_factory=list, max_length=20)


def _require_owner(request: Request) -> None:
    """Scanning the account owner's OWN connected Gmail: only the owner.
    A workspace manager is refused (founder-safe default, review round)."""
    if getattr(request.state, "workspace_role", "owner") != "owner":
        raise HTTPException(status_code=403,
                            detail="Only the account owner can scan the owner's Gmail.")


@router.post("/gmail-scan", status_code=202)
def start_gmail_scan(body: ScanIn, request: Request, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)) -> dict:
    _gate(db, current_user)
    _require_owner(request)
    if not _attested(body.attested, body.attestation_version):
        raise HTTPException(status_code=422,
                            detail="Confirm that these are your own business contacts first.")
    enforce_rate_limit(str(current_user.id), "email_network_scan", "RATE_LIMIT_AI_ACTION")
    try:
        row, new = eng.start_scan(db, current_user, attested=True,
                                  own_extra=body.own_addresses)
    except eng.ScanError as exc:
        detail = {"error": exc.code, "message": exc.detail} if exc.code else exc.detail
        raise HTTPException(status_code=exc.status, detail=detail) from exc
    if new:
        from app.workers import network_tasks  # noqa: PLC0415

        if not network_tasks.enqueue_gmail_chunk(row.id, 0):
            eng.fail(db, row.id, "The scan could not be queued. Try again in a minute.")
        security_audit.record(db, action=security_audit.EMAIL_NETWORK_SCAN_STARTED,
                              request=request, user_id=current_user.id,
                              target_type="email_network", target_id=row.id)
        db.commit()
        db.refresh(row)
    return eng.scan_out(row)


@router.get("/gmail-scan")
def gmail_scan_status(db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)) -> dict:
    return eng.gmail_state(db, current_user)


# --------------------------------------------------------------------------
# Analysis + recommendations
# --------------------------------------------------------------------------


@router.post("/analyze")
def analyze(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict:
    _gate(db, current_user)
    return en.analyze_user(db, current_user)


@router.get("/recommendations")
def recommendations(
    product_id: uuid.UUID | None = None,
    min_score: int = Query(default=en.MATCH_THRESHOLD, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_plan(current_user)
    return {"products": en.recommendations(db, current_user, product_id=product_id,
                                           min_score=min_score, limit=limit)}


@router.delete("")
def erase(request: Request, db: Session = Depends(get_db),
          current_user: User = Depends(get_current_user)) -> dict:
    """Delete everything this account imported. Never plan- or flag-gated:
    a downgraded account can always remove its data."""
    out = en.erase_user_network(db, current_user)
    security_audit.record(db, action=security_audit.EMAIL_NETWORK_ERASED, request=request,
                          user_id=current_user.id, target_type="email_network", details=out)
    db.commit()
    return out


# --------------------------------------------------------------------------
# Campaigns: add contacts as leads; attach a saved first email
# --------------------------------------------------------------------------


@router.get("/campaigns")
def campaigns(db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)) -> dict:
    rows = db.execute(
        select(Strategy, Product).join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == current_user.id,
               Strategy.status.in_(enm._STRATEGY_OK))  # noqa: SLF001
        .order_by(Product.name, Strategy.created_at)).all()
    out = []
    for strategy, product in rows:
        sequences = db.execute(select(Sequence).where(Sequence.strategy_id == strategy.id)
                               ).scalars().all()
        email_first = any(
            s.status is not SequenceStatus.COMPLETED and s.steps
            and sorted(s.steps, key=lambda x: x.step_no)[0].effective_channel(s)
            is ChannelType.EMAIL for s in sequences) if sequences else False
        out.append({"strategy_id": str(strategy.id), "product_name": product.name,
                    "created_at": strategy.created_at, "campaign_state": strategy.campaign_state,
                    "has_email_first_sequence": email_first})
    return {"campaigns": out}


class AddIn(BaseModel):
    strategy_id: uuid.UUID
    contact_ids: list[uuid.UUID] = Field(min_length=1, max_length=enm.ADD_MAX)


@router.post("/add-to-campaign")
def add_to_campaign(body: AddIn, request: Request, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)) -> dict:
    """Contacts become ordinary leads (status email_found) and go through
    the normal email verification stage; only VERIFIED leads can be
    enrolled, through the campaign's normal launch."""
    _gate(db, current_user)
    out = _run(enm.add_to_campaign, db, current_user, body.strategy_id, body.contact_ids)
    if out["batch_id"]:
        from app.workers import network_tasks  # noqa: PLC0415

        out["verification_queued"] = network_tasks.enqueue_verification(out["batch_id"])
        security_audit.record(db, action=security_audit.EMAIL_NETWORK_ADDED_TO_CAMPAIGN,
                              request=request, user_id=current_user.id,
                              target_type="strategy", target_id=body.strategy_id,
                              details={"added": out["added"], "skipped": len(out["skipped"])})
        db.commit()
    return out


# --------------------------------------------------------------------------
# Saved first emails
# --------------------------------------------------------------------------


class DraftIn(BaseModel):
    contact_id: uuid.UUID
    product_id: uuid.UUID


class SaveIn(BaseModel):
    subject: str = Field(max_length=enm.SUBJECT_MAX)
    body: str = Field(max_length=enm.BODY_MAX)


class AttachIn(BaseModel):
    strategy_id: uuid.UUID


@router.get("/messages")
def list_messages(db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> dict:
    rows = db.execute(select(EmailNetworkMessage)
                      .where(EmailNetworkMessage.user_id == current_user.id)
                      .order_by(EmailNetworkMessage.created_at)).scalars().all()
    return {"messages": [enm.message_out(db, r) for r in rows]}


@router.post("/messages/draft")
def draft_message(body: DraftIn, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> dict:
    _gate(db, current_user)
    with metered(db, current_user, "drafting"):
        msg = _run(enm.draft, db, current_user, body.contact_id, body.product_id)
        return enm.message_out(db, msg)


@router.put("/messages/{message_id}")
def save_message(message_id: uuid.UUID, body: SaveIn, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)) -> dict:
    _gate(db, current_user)
    return enm.message_out(db, _run(enm.save, db, current_user, message_id, body.subject,
                                    body.body))


@router.post("/messages/{message_id}/attach")
def attach_message(message_id: uuid.UUID, body: AttachIn, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)) -> dict:
    """Use a SAVED email as this person's first email in one of your
    campaigns. Nothing is sent or enrolled here."""
    _gate(db, current_user)
    msg, batch_id = _run(enm.attach, db, current_user, message_id, body.strategy_id)
    out = enm.message_out(db, msg)
    if batch_id:
        from app.workers import network_tasks  # noqa: PLC0415

        out["verification_queued"] = network_tasks.enqueue_verification(batch_id)
    return out


@router.post("/messages/{message_id}/detach")
def detach_message(message_id: uuid.UUID, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)) -> dict:
    _require_plan(current_user)
    return enm.message_out(db, _run(enm.detach, db, current_user, message_id))

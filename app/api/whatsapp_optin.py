"""WhatsApp opt-in APIs — Milestone 4, Chunk 2.

POST   /leads/{id}/whatsapp-optin   — record consent (evidence required
                                      for manual_import)
DELETE /leads/{id}/whatsapp-optin   — revoke: opted_out + phone suppressed
                                      + WhatsApp sequences hard-stopped
GET    /leads/{id}/whatsapp-optin   — current status + FULL audit history

GET/POST /optin/whatsapp/{token}    — hosted PUBLIC opt-in page (signed
                                      token per lead, like the M3
                                      unsubscribe page). The compliant way
                                      to convert email leads into
                                      WhatsApp-reachable leads: link it in
                                      an email footer/signature and let the
                                      prospect consent themselves.

POST /whatsapp/optins/import        — CSV bulk import (phone, evidence,
                                      consent_text, date). Every row needs
                                      evidence; rows without it are
                                      REJECTED with a reason, never
                                      silently accepted. Importing numbers
                                      that never actually consented
                                      violates WhatsApp policy and risks a
                                      permanent business-account ban — the
                                      system will not pretend otherwise.
"""

import csv
import io
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import Lead, OptInSource, Product, Strategy, User, WhatsAppOptIn
from app.services import whatsapp_optin as svc
from app.services.whatsapp_optin import OptInError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["whatsapp"])


# --------------------------------------------------------------------------
# Schemas / serialization
# --------------------------------------------------------------------------


class OptInCreate(BaseModel):
    source: OptInSource = OptInSource.API
    phone: str | None = Field(
        default=None, description="E.164; defaults to the lead's stored phone"
    )
    evidence: str | None = Field(
        default=None,
        description="Where/when/how consent was given (URL, note, message id). "
                    "REQUIRED for manual_import.",
    )
    consent_text: str | None = Field(
        default=None, description="The exact consent wording shown to the person"
    )


def _row(r: WhatsAppOptIn) -> dict:
    return {
        "id": str(r.id),
        "phone": r.phone,
        "status": r.status.value,
        "source": r.source.value,
        "evidence": r.evidence,
        "consent_text": r.consent_text,
        "ts": r.ts.isoformat() if r.ts else None,
        "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
    }


def _owned_lead(lead_id: uuid.UUID, db: Session, current_user: User) -> Lead:
    """Fetch a lead and verify it belongs (via its strategy's product) to
    current_user, else 404."""
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="lead not found")
    strategy = db.get(Strategy, lead.strategy_id)
    product = db.get(Product, strategy.product_id) if strategy else None
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead


# --------------------------------------------------------------------------
# Per-lead opt-in endpoints
# --------------------------------------------------------------------------


@router.post("/leads/{lead_id}/whatsapp-optin", status_code=201)
def record_optin(
    lead_id: uuid.UUID,
    body: OptInCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    lead = _owned_lead(lead_id, db, current_user)
    try:
        row = svc.record_opt_in(
            db, lead,
            phone=body.phone,
            source=body.source,
            evidence=body.evidence,
            consent_text=body.consent_text,
        )
    except OptInError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "optin": _row(row),
        "why_evidence_matters": (
            "Consent evidence is what protects you in a dispute: Meta and "
            "regulators treat undocumented 'opt-ins' as no opt-in at all. "
            "Keep the URL, form, or message that proves this person agreed."
        ),
    }


@router.delete("/leads/{lead_id}/whatsapp-optin")
def revoke_optin(
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    lead = _owned_lead(lead_id, db, current_user)
    row = svc.revoke_opt_in(db, lead, source=OptInSource.API,
                            evidence="revoked via API")
    return {
        "optin": _row(row),
        "effects": [
            "status is now opted_out (appended to the audit trail)",
            "phone added to the suppression list",
            "all WhatsApp sequences for this lead hard-stopped",
        ],
    }


@router.get("/leads/{lead_id}/whatsapp-optin")
def get_optin(
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    lead = _owned_lead(lead_id, db, current_user)
    return {
        "current_status": svc.current_status(db, lead.id).value,
        "history": [_row(r) for r in svc.history(db, lead.id)],
    }


# --------------------------------------------------------------------------
# Hosted public opt-in page
# --------------------------------------------------------------------------

_CONSENT_TEXT = (
    "I agree to receive WhatsApp messages from this sender about their "
    "products and services. I can opt out at any time by replying STOP "
    "or using an opt-out link."
)

_PAGE_HTML = """<!doctype html>
<html><head><title>WhatsApp opt-in</title></head>
<body style="font-family: sans-serif; max-width: 480px; margin: 80px auto;">
<h2>Receive updates on WhatsApp?</h2>
<p>{consent_text}</p>
<form method="post">
  <label>Your WhatsApp number (with country code):<br>
    <input name="phone" placeholder="+923001234567" required
           style="width: 100%; padding: 8px; margin: 8px 0;">
  </label>
  <button type="submit" style="padding: 8px 16px;">Yes, opt me in</button>
</form>
<p style="color:#666;font-size:0.85em;">If you do nothing, you will not
receive WhatsApp messages.</p>
</body></html>"""

_DONE_HTML = """<!doctype html>
<html><head><title>Opted in</title></head>
<body style="font-family: sans-serif; max-width: 480px; margin: 80px auto;">
<h2>You're opted in.</h2>
<p>You may receive WhatsApp messages from this sender. Reply STOP to any
message to opt out instantly.</p>
</body></html>"""

_INVALID_HTML = """<!doctype html>
<html><head><title>Invalid link</title></head>
<body style="font-family: sans-serif; max-width: 480px; margin: 80px auto;">
<h2>This link is not valid.</h2>
<p>The link may be incomplete or expired.</p>
</body></html>"""

_ERROR_HTML = """<!doctype html>
<html><head><title>Could not opt in</title></head>
<body style="font-family: sans-serif; max-width: 480px; margin: 80px auto;">
<h2>Could not record your opt-in.</h2>
<p>{reason}</p>
</body></html>"""


@router.get("/optin/whatsapp/{token}", response_class=HTMLResponse)
def optin_page(token: str, db: Session = Depends(get_db)) -> HTMLResponse:
    try:
        lead_id = svc.parse_optin_token(token)
    except Exception:
        return HTMLResponse(_INVALID_HTML, status_code=400)
    if db.get(Lead, lead_id) is None:
        return HTMLResponse(_INVALID_HTML, status_code=400)
    return HTMLResponse(_PAGE_HTML.format(consent_text=_CONSENT_TEXT))


@router.post("/optin/whatsapp/{token}", response_class=HTMLResponse)
def optin_submit(token: str, phone: str = Form(...),
                 db: Session = Depends(get_db)) -> HTMLResponse:
    try:
        lead_id = svc.parse_optin_token(token)
    except Exception:
        return HTMLResponse(_INVALID_HTML, status_code=400)
    lead = db.get(Lead, lead_id)
    if lead is None:
        return HTMLResponse(_INVALID_HTML, status_code=400)
    try:
        svc.record_opt_in(
            db, lead,
            phone=phone,
            source=OptInSource.WEB_FORM,
            evidence=f"hosted opt-in page, token for lead {lead_id}",
            consent_text=_CONSENT_TEXT,
        )
    except OptInError as exc:
        return HTMLResponse(_ERROR_HTML.format(reason=str(exc)), status_code=422)
    return HTMLResponse(_DONE_HTML)


def optin_url(lead_id: uuid.UUID) -> str:
    """Public URL of a lead's opt-in page (used by email footers/Chunk 3)."""
    from app.config import settings
    token = svc.make_optin_token(lead_id)
    return f"{settings.public_base_url.rstrip('/')}/optin/whatsapp/{token}"


# --------------------------------------------------------------------------
# Bulk import — honest by construction
# --------------------------------------------------------------------------


@router.post("/whatsapp/optins/import")
async def import_optins(
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """CSV columns: phone, evidence, consent_text, date (ISO, optional).
    Each row is matched to a lead by (normalized) phone. Rows are accepted
    ONLY with evidence; everything else is rejected with a per-row reason.

    Matching is scoped to leads owned by current_user — without this, a
    phone number matching another account's lead would silently write an
    opt-in record onto data that isn't the caller's.
    """
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    if reader.fieldnames is None or "phone" not in [
        (f or "").strip().lower() for f in reader.fieldnames
    ]:
        raise HTTPException(
            status_code=422,
            detail="CSV must have a header row including at least: phone, "
                   "evidence, consent_text (date optional)",
        )

    # Normalized-phone -> lead lookup built once (import files can be big;
    # a per-row table scan would be quadratic). Scoped to current_user's
    # own leads only (via strategy -> product -> user_id).
    leads_by_phone: dict[str, Lead] = {}
    owned_leads = db.execute(
        select(Lead)
        .join(Strategy, Strategy.id == Lead.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .where(Lead.phone.isnot(None), Product.user_id == current_user.id)
    ).scalars()
    for lead in owned_leads:
        try:
            leads_by_phone[svc.normalize_e164(lead.phone)] = lead
        except OptInError:
            digits = "".join(ch for ch in lead.phone if ch.isdigit())
            if digits:
                leads_by_phone[f"+{digits}"] = lead

    accepted: list[dict] = []
    rejected: list[dict] = []
    for line_no, row in enumerate(reader, start=2):  # 1 = header
        cells = {(k or "").strip().lower(): (v or "").strip()
                 for k, v in row.items()}
        phone_raw = cells.get("phone", "")
        evidence = cells.get("evidence", "")
        consent_text = cells.get("consent_text", "")

        def reject(reason: str) -> None:
            rejected.append({"line": line_no, "phone": phone_raw, "reason": reason})

        if not phone_raw:
            reject("missing phone")
            continue
        if not evidence:
            reject(
                "missing evidence — every imported opt-in must document "
                "where/when/how this person consented. Rows without "
                "evidence are never accepted."
            )
            continue
        try:
            normalized = svc.normalize_e164(phone_raw)
        except OptInError as exc:
            reject(str(exc))
            continue
        lead = leads_by_phone.get(normalized)
        if lead is None:
            reject("no lead with this phone — source the lead first, then import")
            continue
        date_note = f" (consented {cells['date']})" if cells.get("date") else ""
        try:
            svc.record_opt_in(
                db, lead,
                phone=normalized,
                source=OptInSource.MANUAL_IMPORT,
                evidence=evidence + date_note,
                consent_text=consent_text or None,
            )
        except OptInError as exc:
            reject(str(exc))
            continue
        accepted.append({"line": line_no, "phone": normalized,
                         "lead_id": str(lead.id)})

    return {
        "accepted": accepted,
        "rejected": rejected,
        "summary": f"{len(accepted)} accepted, {len(rejected)} rejected",
        "policy_note": (
            "Only rows with real consent evidence were accepted. Importing "
            "numbers that never actually consented violates WhatsApp policy "
            "and can get the business account permanently banned."
        ),
    }
"""Private email network: the LinkedIn network's twin for the people a user
already emails (docs/features/email-network.md).

PRIVACY BOUNDARY (the same as app/services/linkedin_network.py)
  * A contact belongs to the account that imported it and is only ever read
    back for that account. There is no shared pool and no cross-account read.
  * Headers only. From / To / Cc / Date and the four bulk-mail markers are
    read; a subject, a body, a Message-ID, an attachment or a signature is
    never read into a stored field (app/services/email_network_parse.py).
  * Filtered before storage (app/services/email_network_filter.py): people a
    rule excludes are never written; only counts by reason.
  * Scoring is rule-based and offline (no model, no third party): the LinkedIn
    network's ICP scoring plus how strong the email relationship is.

Counts are the LARGEST seen in any one source (a mailbox file, a Gmail scan),
never summed, so importing the same mailbox twice -- or a file and a scan of
the same mailbox -- never inflates them.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.plans import PLANS
from app.db.models import (
    EmailContact, EmailContactMatch, EmailNetworkImport, EmailNetworkMessage, Product, User,
)
from app.services import email_network_filter as flt
from app.services import email_network_parse as parse
from app.services import linkedin_network as ln

FLAG = "email_network_enabled"
PLAN_KEY = "email_network"
MATCH_THRESHOLD = 30
MAX_MATCHES_PER_PRODUCT = 500
#: Review round H1: an account holds at most this many email contacts; an
#: import past it adds no new people and says so (cap_note).
MAX_CONTACTS_PER_ACCOUNT = 100_000
INSERT_BATCH = 1000
STALE_AFTER_DAYS = 30

#: The attestation the user ticks before any import or scan. Bump the
#: version whenever the TEXT changes.
ATTESTATION_VERSION = "1"
ATTESTATION_TEXT = (
    "These are my own business contacts: people I or my business have dealt "
    "with. I will only email them about things relevant to that relationship, "
    "and anyone who asks not to be contacted will not be.")

#: CASL s.10(10): implied consent from an existing business relationship
#: lasts two years. See casl_block().
CASL_WINDOW = timedelta(days=730)

ICP_WEIGHT = 0.6          # the LinkedIn ICP score (0-100) counts for up to 60
TWO_WAY_POINTS = 20
RECENCY_POINTS = ((timedelta(days=183), 12), (timedelta(days=365), 8),
                  (timedelta(days=730), 4))
VOLUME_POINTS = 8         # log-scaled; 50 messages or more = all 8
VOLUME_FULL_AT = 50


class EmailNetworkError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Flag + plan
# --------------------------------------------------------------------------


def enabled(db: Session) -> bool:
    from app.services import system_settings  # noqa: PLC0415

    return bool(system_settings.get(db, FLAG))


def is_eligible(user: User) -> bool:
    plan = getattr(user.plan, "value", user.plan) or "free"
    return bool(PLANS.get(plan, PLANS["free"]).get(PLAN_KEY))


# --------------------------------------------------------------------------
# Storing an import
# --------------------------------------------------------------------------


def _month(value: datetime | None) -> str | None:
    return _aware(value).strftime("%b %Y") if value else None


def _source_counts(person: parse.Person) -> dict:
    return {"sent": person.sent, "received": person.received,
            "first": person.first.isoformat() if person.first else None,
            "last": person.last.isoformat() if person.last else None}


def _merge_source(old: dict | None, new: dict) -> dict:
    """Same source imported again: the larger count, the wider date range."""
    if not old:
        return new
    firsts = [d for d in (old.get("first"), new.get("first")) if d]
    lasts = [d for d in (old.get("last"), new.get("last")) if d]
    return {"sent": max(int(old.get("sent") or 0), new["sent"]),
            "received": max(int(old.get("received") or 0), new["received"]),
            "first": min(firsts) if firsts else None,
            "last": max(lasts) if lasts else None}


def _derive(contact: EmailContact) -> None:
    sources = (contact.source_counts_json or {}).values()
    contact.sent_to_count = max([int(s.get("sent") or 0) for s in sources] or [0])
    contact.received_from_count = max([int(s.get("received") or 0) for s in sources] or [0])
    firsts = [parse._iso(s.get("first")) for s in sources if s.get("first")]  # noqa: SLF001
    lasts = [parse._iso(s.get("last")) for s in sources if s.get("last")]  # noqa: SLF001
    contact.first_seen = min(firsts) if firsts else None
    contact.last_seen = max(lasts) if lasts else None
    contact.two_way = contact.sent_to_count > 0 and contact.received_from_count > 0


def _cap_notes(tally: parse.Tally, account_full: int) -> list[str]:
    notes = []
    if tally.people_capped:
        notes.append(f"Only the first {tally.people_limit:,} people in this upload were kept")
    if tally.big_messages:
        notes.append(f"{tally.big_messages:,} messages had more than "
                     f"{parse.MAX_RECIPIENTS_PER_MESSAGE} recipients; only the first "
                     f"{parse.MAX_RECIPIENTS_PER_MESSAGE} of each were counted")
    if account_full:
        notes.append(f"{account_full:,} new people were not added: an account can hold at "
                     f"most {MAX_CONTACTS_PER_ACCOUNT:,} email contacts")
    return notes


def store(db: Session, user: User, row: EmailNetworkImport, tally: parse.Tally, *,
          source: str | None, contacts: dict[str, parse.ContactRow] | None = None,
          analyze: bool = True) -> dict:
    """Write what survived the filters into THIS account's contacts, count
    the rest by reason on the import row, re-score. `source` is "mbox" or
    "gmail" for mailbox traffic (None for a contacts file). Bounded: at most
    MAX_CONTACTS_PER_ACCOUNT rows per account; new rows are inserted in
    batches. Commits."""
    contacts = contacts or {}
    excluded: Counter = Counter(tally.excluded_counts())

    candidates: dict[str, tuple[parse.Person | None, parse.ContactRow | None]] = {}
    for email, person in tally.people.items():
        if flt.automated_by_traffic(person.automated, person.sent) and email not in contacts:
            excluded[flt.AUTOMATED] += 1
            continue
        candidates[email] = (person, None)
    for email, crow in contacts.items():
        person = candidates.get(email, (None, None))[0]
        candidates[email] = (person, crow)

    lists = flt.load_blocklists(db, user.id, candidates.keys())
    blocked: list[str] = []
    for email in list(candidates):
        crow = candidates[email][1]
        reason = lists.reason(email, crow.company if crow else None)
        if reason is not None:
            excluded[reason] += 1
            blocked.append(email)
            del candidates[email]
    if blocked:          # stored earlier, blocked now: removed, not kept
        _delete_contacts(db, user.id, blocked)

    existing = {c.email: c for c in db.execute(
        select(EmailContact).where(EmailContact.user_id == user.id)).scalars()
        if c.email in candidates} if candidates else {}
    room = max(0, MAX_CONTACTS_PER_ACCOUNT - contact_count(db, user.id))
    added = updated = account_full = 0
    pending: list[EmailContact] = []
    for email, (person, crow) in candidates.items():
        contact = existing.get(email)
        if contact is None:
            if added >= room:
                account_full += 1
                continue
            contact = EmailContact(user_id=user.id, email=email, domain=flt.domain_of(email),
                                   source_counts_json={})
            pending.append(contact)
            added += 1
        else:
            updated += 1
        if crow is not None:
            contact.in_contacts_file = True
            if crow.name:
                contact.full_name = crow.name
            if crow.company:
                contact.company, contact.company_from_domain = crow.company, False
            if crow.title:
                contact.title = crow.title
        if person is not None:
            if person.name and not contact.full_name:
                contact.full_name = person.name
            if source:
                counts = dict(contact.source_counts_json or {})
                counts[source] = _merge_source(counts.get(source), _source_counts(person))
                contact.source_counts_json = counts
        if not contact.company:
            guess = parse.company_from_domain(contact.domain)
            contact.company, contact.company_from_domain = guess, bool(guess)
        _derive(contact)
        if len(pending) >= INSERT_BATCH:
            db.add_all(pending)
            db.flush()
            pending = []
    if pending:
        db.add_all(pending)

    # Everyone seen once: kept candidates (traffic or file) + people a fixed
    # rule excluded (counted through their hashes, so each person once).
    row.people_found = (len(set(tally.people) | set(contacts))
                        + sum(tally.excluded_counts().values()))
    row.added, row.updated = added, updated
    row.excluded = sum(excluded.values())
    row.excluded_json = {r: int(n) for r, n in excluded.items() if n}
    row.messages_scanned = max(row.messages_scanned or 0, tally.messages)
    notes = ([row.cap_note.rstrip(".")] if row.cap_note else []) + _cap_notes(tally,
                                                                             account_full)
    row.cap_note = ("; ".join(notes) + ".")[:300] if notes else None
    row.status, row.finished_at, row.tally_json = "done", _now(), None
    db.commit()
    analysis = analyze_user(db, user) if analyze else {"matches": 0}
    return {**import_out(row), "matched": analysis["matches"]}


def import_out(row: EmailNetworkImport) -> dict:
    counts = row.excluded_json or {}
    return {
        "id": str(row.id), "kind": row.kind, "status": row.status,
        "rows_in_file": row.rows_in_file, "messages_scanned": row.messages_scanned,
        "people_found": row.people_found, "added": row.added, "updated": row.updated,
        "excluded": row.excluded, "excluded_by_reason": flt.summary(counts),
        "cap_note": row.cap_note, "error": row.error,
        "created_at": row.created_at, "finished_at": row.finished_at,
    }


def new_import(db: Session, user: User, kind: str, *, attested: bool,
               status: str = "done") -> EmailNetworkImport:
    if not attested:
        raise EmailNetworkError(422, "Confirm that these are your own business contacts first.")
    row = EmailNetworkImport(user_id=user.id, kind=kind, status=status,
                             attested_at=_now(), attestation_version=ATTESTATION_VERSION)
    db.add(row)
    db.flush()
    return row


def import_contacts_file(db: Session, user: User, data: bytes, *, attested: bool,
                         own_extra=()) -> dict:
    """A whole (size-capped) contacts CSV or vCard file."""
    if not attested:
        raise EmailNetworkError(422, "Confirm that these are your own business contacts first.")
    try:
        result = parse.parse_contacts(data)
    except parse.ParseError as exc:
        raise EmailNetworkError(422, exc.user_message) from exc
    row = new_import(db, user, result.kind, attested=attested)
    row.rows_in_file = result.rows_in_file
    if result.capped:
        row.cap_note = (f"Only the first {parse.MAX_CONTACT_ROWS:,} contacts were read. "
                        "Split the file and upload the rest separately.")
    tally = parse.Tally(own=flt.own_identity(db, user, own_extra))
    kept = parse.contacts_into(tally, result.rows)
    return store(db, user, row, tally, source=None, contacts=kept)


def finish_mbox(db: Session, user: User, stream: parse.MboxStream, *, attested: bool,
                capped_bytes: bool = False) -> dict:
    row = new_import(db, user, "mbox", attested=attested)
    row.rows_in_file = stream.messages_seen
    notes = []
    if stream.capped:
        notes.append(f"Only the first {stream.max_messages:,} messages were read")
    if capped_bytes:
        notes.append(f"only the first {parse.MBOX_MAX_BYTES // (1024 * 1024)} MB were read")
    if notes:
        row.cap_note = ("; ".join(notes) + ". People who appear only later in the file "
                        "are missing.")[:300]
    return store(db, user, row, stream.tally, source="mbox")


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------


def relationship(contact: EmailContact, now: datetime) -> tuple[int, str]:
    """0-40 points for how strong the email relationship is, and the sentence
    that says why -- built ONLY from the counts and dates, never more."""
    sent, received = contact.sent_to_count or 0, contact.received_from_count or 0
    last = _aware(contact.last_seen)
    points = TWO_WAY_POINTS if contact.two_way else 0
    if last is not None:
        age = now - last
        for window, pts in RECENCY_POINTS:
            if age <= window:
                points += pts
                break
    total = sent + received
    if total:
        points += round(VOLUME_POINTS * min(1.0, math.log1p(total) / math.log1p(VOLUME_FULL_AT)))
    when = f", last in {_month(last)}" if last else ""
    if contact.two_way:
        why = f"You emailed each other {total} time{'s' if total != 1 else ''}{when}"
    elif sent:
        why = (f"You emailed them {sent} time{'s' if sent != 1 else ''}{when}; "
               "no reply from them was found")
    elif received:
        why = (f"They emailed you {received} time{'s' if received != 1 else ''}{when}; "
               "you have not written to them")
    else:
        why = "In your contacts file; no emails between you were found"
    return points, why


def score_contact(profile, contact: EmailContact, now: datetime) -> tuple[int, int, int, list]:
    """(score, icp part, relationship part, reasons). 0 when the ICP does not
    match at all: a strong relationship alone is not a product match."""
    icp_raw, icp_reasons = ln.icp_score(profile, contact.title, contact.company)
    if icp_raw == 0:
        return 0, 0, 0, []
    icp_part = round(icp_raw * ICP_WEIGHT)
    rel_part, why = relationship(contact, now)
    reasons = [why] + list(icp_reasons)
    if not contact.two_way:
        reasons.append("No two-way exchange: ranked below people you have written with")
    return min(100, icp_part + rel_part), icp_part, rel_part, reasons


OPENER_DELETED = "opener_deleted"


def flag_deleted_openers(db: Session, *clauses) -> int:
    """Before saved first emails that are ATTACHED (not yet used) are deleted:
    mark their leads, so the campaign's first email to that person is HELD
    for a person to review instead of being silently written by AI
    (email_network_messages.hold_if_opener_deleted, called by the send
    path). Review round LOW. Does not commit."""
    from sqlalchemy.orm.attributes import flag_modified  # noqa: PLC0415

    from app.db.models import Lead  # noqa: PLC0415

    lead_ids = [lid for lid in db.execute(select(EmailNetworkMessage.lead_id).where(
        EmailNetworkMessage.status == "attached", EmailNetworkMessage.lead_id.is_not(None),
        *clauses)).scalars() if lid is not None]
    flagged = 0
    for lead_id in lead_ids:
        lead = db.get(Lead, lead_id)
        if lead is None or (lead.enrichment_json or {}).get("gdpr_deleted"):
            continue
        enrichment = dict(lead.enrichment_json or {})
        mine = dict(enrichment.get("email_network") or {})
        mine[OPENER_DELETED] = True
        enrichment["email_network"] = mine
        lead.enrichment_json = enrichment
        flag_modified(lead, "enrichment_json")
        flagged += 1
    return flagged


def _delete_contacts(db: Session, user_id, emails) -> int:
    """Delete THIS account's rows for these addresses (and their scores and
    saved first emails), in chunks so a long list stays under any bound-parameter limit."""
    emails = sorted(set(emails))
    removed = 0
    for i in range(0, len(emails), 500):
        ids = list(db.execute(select(EmailContact.id).where(
            EmailContact.user_id == user_id,
            EmailContact.email.in_(emails[i:i + 500]))).scalars())
        if not ids:
            continue
        flag_deleted_openers(db, EmailNetworkMessage.user_id == user_id,
                             EmailNetworkMessage.contact_id.in_(ids))
        db.execute(delete(EmailNetworkMessage).where(EmailNetworkMessage.user_id == user_id,
                                                     EmailNetworkMessage.contact_id.in_(ids)))
        db.execute(delete(EmailContactMatch).where(EmailContactMatch.user_id == user_id,
                                                   EmailContactMatch.contact_id.in_(ids)))
        removed += db.execute(delete(EmailContact).where(EmailContact.user_id == user_id,
                                                         EmailContact.id.in_(ids))).rowcount or 0
    return removed


def delete_contact(db: Session, user: User, contact_id) -> dict:
    """DELETE /email-network/contacts/{id}: one of THIS account's contacts,
    its scores and its saved first email. 404 for anyone else's. Commits."""
    contact = db.execute(select(EmailContact).where(
        EmailContact.id == contact_id, EmailContact.user_id == user.id)).scalar_one_or_none()
    if contact is None:
        raise EmailNetworkError(404, "Contact not found.")
    removed = _delete_contacts(db, user.id, [contact.email])
    db.commit()
    return {"deleted_contacts": removed}


def scrub_scan_tallies(db: Session, emails, *, user_id=None) -> int:
    """Remove these addresses from the TRANSIENT tallies of running Gmail
    scans (of one account, or of every account for a global suppression), so
    an erased or unsubscribed person is not written when the scan finishes.
    Review round M2. Does not commit."""
    from sqlalchemy.orm.attributes import flag_modified  # noqa: PLC0415

    wanted = {e for e in (flt.normalize_email(x) for x in emails) if e}
    if not wanted:
        return 0
    q = select(EmailNetworkImport).where(EmailNetworkImport.kind == "gmail_scan",
                                         EmailNetworkImport.tally_json.is_not(None))
    if user_id is not None:
        q = q.where(EmailNetworkImport.user_id == user_id)
    scrubbed = 0
    for row in db.execute(q).scalars():
        state = dict(row.tally_json or {})
        tally = dict(state.get("tally") or {})
        people = dict(tally.get("people") or {})
        hit = wanted & set(people)
        if not hit:
            continue
        for email in hit:
            people.pop(email, None)
        tally["people"] = people
        state["tally"] = tally
        row.tally_json = state
        flag_modified(row, "tally_json")
        scrubbed += len(hit)
    return scrubbed


def purge_blocked(db: Session, user: User) -> int:
    """Delete THIS account's stored contacts that may no longer be kept:
    suppressed (unsubscribed / bounced / erased), excluded, or now 'own'.
    Runs whatever the plan or the flag (data that must go, goes). Commits."""
    contacts = db.execute(select(EmailContact.email, EmailContact.company,
                                 EmailContact.company_from_domain)
                          .where(EmailContact.user_id == user.id)).all()
    if not contacts:
        return 0
    gone = _no_longer_kept(db, user, contacts)
    removed = _delete_contacts(db, user.id, gone) if gone else 0
    db.commit()
    return removed


def _no_longer_kept(db: Session, user: User, contacts) -> list[str]:
    """Addresses among `contacts` (rows with email / company /
    company_from_domain) that a rule now excludes: a fixed rule (own
    addresses and domains change), the suppression list, the F05 lists."""
    own = flt.own_identity(db, user)
    lists = flt.load_blocklists(db, user.id, [c.email for c in contacts])
    return [c.email for c in contacts
            if flt.static_reason(c.email, own) is not None
            or lists.reason(c.email, None if c.company_from_domain else c.company) is not None]


def purge_address(db: Session, email: str | None) -> int:
    """A global suppression of `email` (an unsubscribe): the address leaves
    EVERY account's email network and every running scan tally. Called after
    the suppression is committed; never raises (an unsubscribe must not fail
    because of this -- the weekly refresh purges again). Commits."""
    import logging  # noqa: PLC0415

    normalized = flt.normalize_email(email)
    if not normalized:
        return 0
    try:
        owners = db.execute(select(EmailContact.user_id).where(
            EmailContact.email == normalized).distinct()).scalars().all()
        removed = sum(_delete_contacts(db, uid, [normalized]) for uid in owners)
        scrub_scan_tallies(db, [normalized])
        db.commit()
        return removed
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).exception("email network purge after unsubscribe failed")
        db.rollback()
        return 0


def analyze_user(db: Session, user: User, now: datetime | None = None) -> dict:
    """Re-filter (suppression, exclusions, own addresses -- they change) and
    re-score the user's OWN contacts against the user's OWN products."""
    now = now or _now()
    contacts = db.execute(select(EmailContact).where(EmailContact.user_id == user.id)
                          ).scalars().all()
    gone = _no_longer_kept(db, user, contacts)
    removed = _delete_contacts(db, user.id, gone) if gone else 0
    gone_set = set(gone)
    keep = [c for c in contacts if c.email not in gone_set]

    products = db.execute(select(Product).where(Product.user_id == user.id)).scalars().all()
    db.execute(delete(EmailContactMatch).where(EmailContactMatch.user_id == user.id))
    created = 0
    for product in products:
        profile = ln.icp_profile(db, product)
        scored = []
        for contact in keep:
            score, icp_part, rel_part, reasons = score_contact(profile, contact, now)
            if score >= MATCH_THRESHOLD:
                scored.append((score, icp_part, rel_part, contact, reasons))
        scored.sort(key=lambda x: (not x[3].two_way, -x[0], x[3].full_name or x[3].email))
        for score, icp_part, rel_part, contact, reasons in scored[:MAX_MATCHES_PER_PRODUCT]:
            db.add(EmailContactMatch(
                user_id=user.id, contact_id=contact.id, product_id=product.id, score=score,
                icp_score=icp_part, relationship_score=rel_part, reasons_json=reasons,
                analyzed_at=now,
                segment=f"{ln.seniority(contact.title)} - {ln.function_of(contact.title)}"))
            created += 1
    db.commit()
    return {"products": len(products), "contacts": len(keep), "removed": removed,
            "matches": created}


def casl_block(contact: EmailContact, now: datetime | None = None) -> str | None:
    """A Canadian (.ca) address whose last TWO-WAY exchange is more than two
    years old, or unknown, is refused for campaign use. CASL s.10(10) implied
    consent from an existing business relationship lasts two years; a two-way
    email exchange is the only evidence this tool has, and it is only a proxy
    (needs founder/legal confirmation). Non-.ca Canadians are not detected."""
    if not contact.domain.endswith(".ca"):
        return None
    last = _aware(contact.last_seen)
    if contact.two_way and last is not None and (now or _now()) - last <= CASL_WINDOW:
        return None
    return ("Canadian address with no two-way email in the last two years: under "
            "Canada's anti-spam law (CASL) implied consent from a business "
            "relationship lasts two years, so it cannot be added to a campaign.")


def contact_out(contact: EmailContact, now: datetime | None = None) -> dict:
    return {
        "contact_id": str(contact.id), "email": contact.email,
        "full_name": contact.full_name, "company": contact.company,
        "company_is_guess": contact.company_from_domain, "title": contact.title,
        "sent_to_count": contact.sent_to_count, "received_from_count":
            contact.received_from_count, "two_way": contact.two_way,
        "first_seen": contact.first_seen, "last_seen": contact.last_seen,
        "in_contacts_file": contact.in_contacts_file,
        "casl_block": casl_block(contact, now),
    }


def recommendations(db: Session, user: User, *, product_id=None, min_score: int = MATCH_THRESHOLD,
                    limit: int = 50) -> list[dict]:
    q = select(Product).where(Product.user_id == user.id).order_by(Product.created_at)
    if product_id:
        q = q.where(Product.id == product_id)
    now = _now()
    out = []
    for product in db.execute(q).scalars().all():
        rows = db.execute(
            select(EmailContactMatch, EmailContact)
            .join(EmailContact, EmailContact.id == EmailContactMatch.contact_id)
            .where(EmailContactMatch.user_id == user.id, EmailContact.user_id == user.id,
                   EmailContactMatch.product_id == product.id,
                   EmailContactMatch.score >= min_score)
            .order_by(EmailContact.two_way.desc(), EmailContactMatch.score.desc(),
                      EmailContact.full_name, EmailContact.email)
        ).all()
        # Read-time re-check: someone unsubscribed / excluded since the last
        # analysis is not shown (the next analysis deletes the row).
        lists = flt.load_blocklists(db, user.id, [c.email for _, c in rows])
        rows = [(mt, c) for mt, c in rows
                if lists.reason(c.email, None if c.company_from_domain else c.company) is None]
        segments = Counter(mt.segment for mt, _ in rows)
        out.append({
            "product_id": str(product.id), "product_name": product.name,
            "total_matches": len(rows),
            "segments": [{"segment": s, "count": n} for s, n in segments.most_common()],
            "matches": [{**contact_out(c, now), "score": mt.score, "icp_score": mt.icp_score,
                         "relationship_score": mt.relationship_score, "segment": mt.segment,
                         "reasons": mt.reasons_json} for mt, c in rows[:limit]],
        })
    return out


# --------------------------------------------------------------------------
# Status, erasure, weekly refresh
# --------------------------------------------------------------------------


def last_import(db: Session, user_id) -> EmailNetworkImport | None:
    return db.execute(select(EmailNetworkImport)
                      .where(EmailNetworkImport.user_id == user_id,
                             EmailNetworkImport.kind != "gmail_scan")
                      .order_by(EmailNetworkImport.created_at.desc(),
                                EmailNetworkImport.id.desc())).scalars().first()


def contact_count(db: Session, user_id) -> int:
    return db.execute(select(func.count(EmailContact.id))
                      .where(EmailContact.user_id == user_id)).scalar_one()


def erase_user_network(db: Session, user: User) -> dict:
    """DELETE /email-network: everything this account imported. Campaign
    leads created from contacts are ordinary leads and are not touched; a
    lead whose ATTACHED first email is deleted here gets its campaign first
    email HELD for review instead of silently written by AI."""
    held = flag_deleted_openers(db, EmailNetworkMessage.user_id == user.id)
    msgs = db.execute(delete(EmailNetworkMessage)
                      .where(EmailNetworkMessage.user_id == user.id)).rowcount
    matches = db.execute(delete(EmailContactMatch)
                         .where(EmailContactMatch.user_id == user.id)).rowcount
    contacts = db.execute(delete(EmailContact)
                          .where(EmailContact.user_id == user.id)).rowcount
    imports = db.execute(delete(EmailNetworkImport)
                         .where(EmailNetworkImport.user_id == user.id)).rowcount
    db.commit()
    return {"deleted_contacts": contacts, "deleted_matches": matches,
            "deleted_messages": msgs, "deleted_imports": imports,
            "first_emails_held_for_review": held}


def erase_person(db: Session, user_id, *, email: str | None, lead_id=None) -> int:
    """A lead's GDPR erasure (app/api/leads.py): the same person's contact
    row in THIS account's email network goes too, with its scores and any
    draft, and any draft attached to that lead. Does not commit."""
    removed = 0
    if lead_id is not None:
        removed += db.execute(delete(EmailNetworkMessage).where(
            EmailNetworkMessage.user_id == user_id,
            EmailNetworkMessage.lead_id == lead_id)).rowcount or 0
    normalized = flt.normalize_email(email)
    if normalized:
        removed += _delete_contacts(db, user_id, [normalized])
        scrub_scan_tallies(db, [normalized], user_id=user_id)
    return removed


def refresh_all(db: Session) -> dict:
    """Weekly. ALWAYS (whatever the flag or the plan): fail Gmail scans that
    stopped responding and clear their tallies, and delete stored contacts
    that may no longer be kept (unsubscribed, erased, excluded). Then, with the
    flag on, re-score eligible accounts. No model, no network."""
    from app.services import email_network_gmail as eng  # noqa: PLC0415

    stale_scans = eng.sweep_stale(db)
    purged = 0
    user_ids = db.execute(select(EmailContact.user_id).distinct()).scalars().all()
    for uid in user_ids:
        user = db.get(User, uid)
        if user is not None:
            purged += purge_blocked(db, user)
    if not enabled(db):
        return {"users": 0, "skipped_ineligible": 0, "disabled": True,
                "purged": purged, "stale_scans": stale_scans}
    done = skipped = 0
    for uid in user_ids:
        user = db.get(User, uid)
        if user is None or user.is_suspended or not is_eligible(user):
            skipped += 1
            continue
        analyze_user(db, user)
        done += 1
    return {"users": done, "skipped_ineligible": skipped, "purged": purged,
            "stale_scans": stale_scans}


def stale(db: Session, user_id) -> bool:
    last = db.execute(select(func.max(EmailNetworkImport.created_at))
                      .where(EmailNetworkImport.user_id == user_id,
                             or_(EmailNetworkImport.status == "done",
                                 EmailNetworkImport.kind != "gmail_scan"))).scalar_one()
    if last is None:
        return True
    return _now() - _aware(last) > timedelta(days=STALE_AFTER_DAYS)

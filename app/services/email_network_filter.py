"""Who in an email network is NEVER stored or recommended -- one deterministic
module, one reason per excluded person (docs/features/email-network.md, C).

The email network is for warm B2B contacts the user already knows. Everyone
else is filtered out with exactly one reason, checked in this order:

  invalid           not a usable address
  own_address       the user's own addresses, and colleagues on the user's own
                    (non-consumer) domain(s)
  personal_domain   consumer mailboxes (gmail.com, yahoo.com, ...): the feature
                    is B2B only (PECR / ePrivacy: corporate subscribers only)
  role_inbox        info@, support@, sales@, ... -- a team, not a person
  automated         no-reply style senders, and senders seen only through
                    mailing-list / bulk / auto-submitted mail the user never
                    wrote back to (List-Unsubscribe, List-Id, Precedence
                    bulk|list|junk, Auto-Submitted other than "no", Gmail's
                    Promotions / Social / Updates / Forums tabs)
  suppressed        on the global suppression list: unsubscribed, bounced,
                    erased on request (GDPR) -- never contacted again
  excluded          on THIS account's F05 exclusion lists (customers, open
                    deals, do-not-contact, ...) by address, domain or company

Excluded people are never written to the database; only counts by reason
(and, during a running Gmail scan, a hash of the address so a person is
counted once). Nothing here reads or stores a subject, a body or a Message-ID.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

INVALID = "invalid"
OWN_ADDRESS = "own_address"
PERSONAL_DOMAIN = "personal_domain"
ROLE_INBOX = "role_inbox"
AUTOMATED = "automated"
SUPPRESSED = "suppressed"
EXCLUDED = "excluded"

#: Every reason, in the order they are checked (and shown).
REASONS = (INVALID, OWN_ADDRESS, PERSONAL_DOMAIN, ROLE_INBOX, AUTOMATED, SUPPRESSED,
           EXCLUDED)

#: The words the page shows for each reason.
LABELS = {
    INVALID: "not a valid address",
    OWN_ADDRESS: "you or your colleagues",
    PERSONAL_DOMAIN: "personal email domains",
    ROLE_INBOX: "role inboxes (info@, support@ ...)",
    AUTOMATED: "newsletters / automated senders",
    SUPPRESSED: "unsubscribed, bounced or erased",
    EXCLUDED: "on your exclusion lists",
}


def _consumer_domains() -> frozenset[str]:
    """ONE maintained list: guardrails.CONSUMER_DOMAINS (shared with F05 and
    Reply Copilot), plus the ISP / regional mailbox providers below. The
    extras live here, not in guardrails, so F05's refusal of a domain
    exclusion does not change as a side effect of this feature."""
    from app.services.guardrails import CONSUMER_DOMAINS  # noqa: PLC0415

    return CONSUMER_DOMAINS | _EXTRA_CONSUMER_DOMAINS


_EXTRA_CONSUMER_DOMAINS = frozenset({
    "pm.me", "proton.ch", "tutanota.com", "tuta.io", "zohomail.com", "rocketmail.com",
    "yahoo.ca", "yahoo.com.au", "yahoo.co.in", "yahoo.fr", "yahoo.de", "yahoo.es",
    "yahoo.it", "hotmail.fr", "hotmail.de", "hotmail.it", "hotmail.es", "live.co.uk",
    "live.ca", "outlook.fr", "outlook.de", "outlook.es", "outlook.it", "aim.com",
    "comcast.net", "verizon.net", "att.net", "sbcglobal.net", "bellsouth.net",
    "cox.net", "charter.net", "earthlink.net", "optonline.net", "btinternet.com",
    "virginmedia.com", "sky.com", "talktalk.net", "orange.fr", "free.fr", "laposte.net",
    "sfr.fr", "wanadoo.fr", "t-online.de", "freenet.de", "libero.it", "virgilio.it",
    "rediffmail.com", "mail.ru", "inbox.ru", "list.ru", "bk.ru", "naver.com",
    "daum.net", "hanmail.net", "126.com", "yeah.net", "sina.com", "foxmail.com",
    "rogers.com", "shaw.ca", "sympatico.ca", "bigpond.com", "optusnet.com.au",
    "seznam.cz", "wp.pl", "o2.pl", "interia.pl", "onet.pl", "icloud.co",
    # review round 2026-10-12
    "hotmail.ca", "protonmail.ch", "yahoo.co.jp", "outlook.co.uk", "gmx.at",
    "hotmail.com.br", "uol.com.br", "bol.com.br", "terra.com.br", "live.de", "aol.co.uk",
    "ukr.net", "i.ua", "meta.ua", "abv.bg", "mail.bg", "web.de", "inbox.lv", "inbox.lt",
    "walla.co.il", "yandex.ua", "ya.ru", "rambler.ru",
})

#: Mailbox brands whose regional variants (yahoo.co.uk, hotmail.com.br,
#: outlook.jp, gmx.ch, protonmail.ch ...) are all consumer domains: matched by
#: pattern -- the brand label followed only by short TLD-like labels, so a
#: business domain such as live.example.com or outlook-partners.com is NOT hit.
_CONSUMER_BRANDS = ("yahoo", "ymail", "hotmail", "outlook", "live", "gmx", "aol", "msn",
                    "windowslive")

#: The consumer-domain list this feature applies.
CONSUMER_DOMAINS: frozenset[str] = _consumer_domains()

#: Local parts that address a team or a function, not a person.
ROLE_LOCAL_PARTS = frozenset({
    "info", "information", "support", "sales", "hello", "hi", "admin", "administrator",
    "billing", "contact", "contactus", "team", "office", "help", "helpdesk", "accounts",
    "accounting", "accountspayable", "ap", "ar", "finance", "careers", "jobs", "hr",
    "recruiting", "recruitment", "talent", "marketing", "press", "media", "pr",
    "webmaster", "hostmaster", "abuse", "security", "privacy", "legal", "compliance",
    "service", "services", "customerservice", "customercare", "care", "enquiries",
    "enquiry", "inquiries", "inquiry", "orders", "order", "invoices", "invoice",
    "feedback", "reception", "frontdesk", "booking", "bookings", "reservations",
    "partners", "partnerships", "ops", "operations", "it", "dev", "devops", "root",
    "community", "events", "membership", "members", "studio", "shop", "store",
    "general", "mail", "email", "all", "staff", "everyone", "board", "investors",
    "ir", "purchasing", "procurement", "vendors", "suppliers", "dispatch", "scheduling",
    "appointments", "estimates", "quotes", "service-desk", "servicedesk", "it-support",
    "techsupport", "tech", "noc", "registrar", "dpo", "gdpr",
})

#: No-reply and machine local parts (prefix match on the part before any
#: '+', '.', '-' or '_' tag, and a few full forms).
_AUTOMATED_LOCAL = re.compile(
    r"^(no-?reply|no_reply|do-?not-?reply|do_not_reply|donotreply|noreply|mailer-daemon|"
    r"postmaster|bounces?|notifications?|notify|alerts?|updates?|newsletters?|news|"
    r"digest|auto-?reply|auto-?responder|automated|automailer|system|robot|daemon|"
    r"calendar-notification|calendar|invitations?|reminders?|receipts?|"
    r"marketing-?(email|emails)?|mailer|mailers|campaigns?|emails?|e-?news|"
    r"comments?-?noreply|support-noreply|reply|replies|unsubscribe)"
    r"([+.\-_][^@]*)?$", re.I)

_EMAIL_RE = re.compile(r"^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
                       r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")

#: RFC 5321 / 1035 limits. The domain limit is also the column size
#: (email_contacts.domain VARCHAR(253)): a longer one would be a database
#: error on PostgreSQL, not a stored row.
MAX_LOCAL = 64
MAX_DOMAIN = 253
MAX_LABEL = 63


def normalize_email(value: str | None) -> str | None:
    """'  Jane.Doe@Acme.COM ' -> 'jane.doe@acme.com', or None if unusable."""
    raw = (value or "").strip().strip("<>").strip().lower()
    if not raw or len(raw) > 320 or not _EMAIL_RE.match(raw):
        return None
    local, domain = raw.rsplit("@", 1)
    if (len(local) > MAX_LOCAL or len(domain) > MAX_DOMAIN
            or any(len(label) > MAX_LABEL for label in domain.split("."))):
        return None
    if not re.search(r"[a-z]", raw.rsplit(".", 1)[-1]):
        return None              # an IP literal, not a domain
    return raw


def domain_of(email: str) -> str:
    return email.rsplit("@", 1)[1]


def local_of(email: str) -> str:
    return email.rsplit("@", 1)[0]


def is_personal_domain(domain: str) -> bool:
    if domain in CONSUMER_DOMAINS:
        return True
    labels = domain.split(".")
    brand, rest = labels[0], labels[1:]
    if not rest or len(rest) > 2 or any(len(x) > 3 for x in rest):
        return False
    return brand in _CONSUMER_BRANDS or bool(re.fullmatch(r"proton(mail)?", brand))


#: Words that, joined by - . or _, still name a team (sales-team@, help-desk@).
_ROLE_WORDS = ROLE_LOCAL_PARTS | frozenset({
    "team", "desk", "dept", "department", "group", "customer", "customers", "client",
    "clients", "payable", "receivable", "payables", "receivables", "us", "na", "eu",
    "uk", "global", "intl", "online", "web", "main", "central", "notices", "notice",
})


def is_role_inbox(email: str) -> bool:
    """info@, sales@ and their variants: customer-service@, help-desk@,
    sales-team@, accounts.payable@, info1@, support_2@."""
    base = re.split(r"[+]", local_of(email), maxsplit=1)[0]
    base = re.sub(r"[-._]?\d+$", "", base)              # info1@, support-2@
    if not base:
        return False
    if base in ROLE_LOCAL_PARTS or re.sub(r"[-._]", "", base) in ROLE_LOCAL_PARTS:
        return True
    words = [w for w in re.split(r"[-._]", base) if w]
    return len(words) > 1 and all(w in _ROLE_WORDS for w in words) and any(
        w in ROLE_LOCAL_PARTS for w in words)


def is_automated_address(email: str) -> bool:
    local = local_of(email)
    return bool(_AUTOMATED_LOCAL.match(local)
                or _AUTOMATED_LOCAL.match(local.replace(".", "")))


def email_hash(email: str) -> str:
    """For counting a person once while their address is not stored."""
    return hashlib.sha256(email.encode("utf-8")).hexdigest()[:24]


# --------------------------------------------------------------------------
# Header signals of bulk / automated mail (RFC 2369 List-*, RFC 2919 List-Id,
# RFC 3834 Auto-Submitted, the de-facto Precedence header)
# --------------------------------------------------------------------------

AUTOMATED_LABELS = frozenset({"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_UPDATES",
                              "CATEGORY_FORUMS"})


def headers_say_automated(headers: dict[str, str], labels=()) -> bool:
    """`headers` maps LOWER-CASE header names to values."""
    if headers.get("list-unsubscribe") or headers.get("list-id"):
        return True
    precedence = (headers.get("precedence") or "").strip().lower()
    if precedence in ("bulk", "list", "junk"):
        return True
    auto = (headers.get("auto-submitted") or "").strip().lower()
    if auto and auto != "no":
        return True
    return bool(AUTOMATED_LABELS & set(labels or ()))


# --------------------------------------------------------------------------
# Own addresses
# --------------------------------------------------------------------------


@dataclass
class Own:
    addresses: set[str] = field(default_factory=set)
    domains: set[str] = field(default_factory=set)

    def is_own(self, email: str) -> bool:
        """The user's own address, or anyone on their own domain(s) or a
        subdomain of one (pat@eu.mycorp.com is a colleague of me@mycorp.com)."""
        if email in self.addresses:
            return True
        domain = domain_of(email)
        return any(domain == d or domain.endswith("." + d) for d in self.domains)


def own_identity(db: Session, user, extra=()) -> Own:
    """The account email, the connected Gmail address and any addresses the
    user typed. Their non-consumer domains count as 'colleagues'."""
    from app.db.models import GmailAccount  # noqa: PLC0415

    found = [getattr(user, "email", None)]
    found += list(db.execute(select(GmailAccount.email_address)
                             .where(GmailAccount.user_id == user.id)).scalars())
    found += list(extra or ())
    own = Own()
    for raw in found:
        email = normalize_email(raw)
        if not email:
            continue
        own.addresses.add(email)
        if not is_personal_domain(domain_of(email)):
            own.domains.add(domain_of(email))
    return own


def parse_own_addresses(raw: str | list | None) -> list[str]:
    """'a@x.com, b@y.com' or a list -> the valid addresses (max 20)."""
    items = raw if isinstance(raw, list) else re.split(r"[\s,;]+", raw or "")
    out = []
    for item in items:
        email = normalize_email(item)
        if email and email not in out:
            out.append(email)
    return out[:20]


# --------------------------------------------------------------------------
# The fixed rules (no database)
# --------------------------------------------------------------------------


def static_reason(email: str | None, own: Own) -> str | None:
    """The first fixed-rule reason that excludes this address, or None.
    `email` must already be normalised (None = invalid)."""
    if not email:
        return INVALID
    if own.is_own(email):
        return OWN_ADDRESS
    if is_personal_domain(domain_of(email)):
        return PERSONAL_DOMAIN
    if is_role_inbox(email):
        return ROLE_INBOX
    if is_automated_address(email):
        return AUTOMATED
    return None


def automated_by_traffic(automated_received: int, sent_to: int) -> bool:
    """A sender seen through list / bulk / auto-submitted mail is automated
    UNLESS the user wrote to them (a real person who once mailed via a list
    is kept)."""
    return automated_received > 0 and sent_to == 0


# --------------------------------------------------------------------------
# The database rules (suppression list, F05 exclusion lists)
# --------------------------------------------------------------------------


@dataclass
class Blocklists:
    suppressed: set[str]
    contact: set[str]
    domain: set[str]
    company: set[str]

    def reason(self, email: str, company: str | None = None) -> str | None:
        from app.services import guardrails  # noqa: PLC0415

        if email in self.suppressed:
            return SUPPRESSED
        if email in self.contact:
            return EXCLUDED
        if guardrails._domain_candidates(domain_of(email)) & self.domain:  # noqa: SLF001
            return EXCLUDED
        key = guardrails.normalize_company(company) if company else None
        if key and key in self.company:
            return EXCLUDED
        return None


def load_blocklists(db: Session, user_id, emails) -> Blocklists:
    """Suppression for these addresses (global list, chunked IN queries) and
    THIS account's active F05 exclusions (all kinds, loaded once). The F05
    lists are applied whether or not guardrails_enabled is on: hiding a
    person the user marked do-not-contact is always safe; the send path keeps
    its own rule."""
    from app.db.models import GuardrailExclusion, SuppressionEntry  # noqa: PLC0415
    from app.services import guardrails  # noqa: PLC0415

    wanted = sorted({e for e in emails if e})
    suppressed: set[str] = set()
    for i in range(0, len(wanted), 500):
        chunk = wanted[i:i + 500]
        suppressed |= set(db.execute(select(SuppressionEntry.email)
                                     .where(SuppressionEntry.email.in_(chunk))).scalars())
    rows = db.execute(select(GuardrailExclusion.kind, GuardrailExclusion.value)
                      .where(GuardrailExclusion.user_id == user_id,
                             GuardrailExclusion.removed_at.is_(None))).all()
    lists = Blocklists(suppressed=suppressed, contact=set(), domain=set(), company=set())
    for kind, value in rows:
        if kind == guardrails.CONTACT:
            lists.contact.add(value)
        elif kind == guardrails.DOMAIN:
            lists.domain.add(value)
        elif kind == guardrails.COMPANY:
            lists.company.add(value)
    return lists


def summary(counts: dict[str, int]) -> list[dict]:
    """[{reason, label, count}] in the fixed order, zero counts dropped."""
    return [{"reason": r, "label": LABELS[r], "count": int(counts.get(r, 0))}
            for r in REASONS if counts.get(r)]


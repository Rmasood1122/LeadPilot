"""Read an email network: contacts files and mailbox HEADERS (never bodies).

Formats, detected from the CONTENT (never the file name):
  * Google Contacts CSV (new "First Name / E-mail 1 - Value / Organization
    Name / Organization Title" and old "Name / E-mail 1 - Value / Organization
    1 - Name / Organization 1 - Title" headers; several addresses in one cell
    separated by ' ::: ')
  * Outlook CSV ("First Name", "Last Name", "E-mail Address", "E-mail 2
    Address", "Company", "Job Title")
  * any other CSV with an e-mail column (comma, semicolon or tab separated)
  * vCard 2.1 / 3 / 4 (FN, N, EMAIL, ORG, TITLE; folded lines, quoted-printable
    names, several cards per file)
  * mbox (Google Takeout and others), STREAMED: header blocks are read field
    by field and only From / To / Cc / Date / List-Unsubscribe / List-Id /
    Precedence / Auto-Submitted are kept -- a Subject, a Message-ID, any other
    header and the whole body are dropped as they are read, never stored.

What comes out is a Tally: per correspondent (lower-cased address) a display
name, how many messages the user SENT to them, how many were RECEIVED from
them, how many of those were automated, and first / last seen. People a fixed
rule excludes (email_network_filter.static_reason) never enter the tally; they
are counted once each, by reason, through a hash of the address.
"""

from __future__ import annotations

import csv
import io
import quopri
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.utils import getaddresses, parsedate_to_datetime

from app.services import email_network_filter as flt

MBOX_MAX_BYTES = 300 * 1024 * 1024        # a mailbox export
CONTACTS_MAX_BYTES = 20 * 1024 * 1024     # a contacts CSV / vCard file
MAX_MESSAGES = 50_000                     # mbox messages read per upload
MAX_CONTACT_ROWS = 50_000                 # contacts-file rows read per upload
MAX_HEADER_BLOCK = 256 * 1024             # one message's kept header bytes
MAX_LINE = 1024 * 1024                    # one physical line
# Hard memory / work bounds (review round H1). An upload can name far more
# people than any real network; past these the rest is NOT read, and the
# import says so (cap_note).
MAX_PEOPLE_PER_IMPORT = 50_000            # unique people kept in one tally
MAX_EXCLUDED_HASHES = 200_000             # hashes kept to count excluded people once
MAX_RECIPIENTS_PER_MESSAGE = 50           # a message to more is a mass mailing
ADDRESS_HEADER_MAX = 16_384               # characters of one To / Cc / From parsed
MAX_ADDRESSES_PER_CELL = 10               # addresses read from one CSV cell
MAX_CONTACT_ADDRESSES = 100_000           # addresses read from one contacts file
NAME_MAX = 300

#: The ONLY header fields ever read from a message. Anything else -- Subject,
#: Message-ID, References, Received, every X-* -- is dropped as it is read.
WANTED_HEADERS = ("from", "to", "cc", "date", "list-unsubscribe", "list-id",
                  "precedence", "auto-submitted")


class ParseError(ValueError):
    """The file cannot be used. `user_message` is one of OUR fixed sentences
    (never text from the file or a library), shown to the user as-is."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


# --------------------------------------------------------------------------
# The tally
# --------------------------------------------------------------------------


@dataclass
class Person:
    name: str | None = None
    sent: int = 0
    received: int = 0
    automated: int = 0
    first: datetime | None = None
    last: datetime | None = None

    def seen(self, when: datetime | None) -> None:
        if when is None:
            return
        if self.first is None or when < self.first:
            self.first = when
        if self.last is None or when > self.last:
            self.last = when


@dataclass
class ContactRow:
    email: str
    name: str | None
    company: str | None
    title: str | None


@dataclass
class Tally:
    own: flt.Own
    people: dict[str, Person] = field(default_factory=dict)
    excluded: dict[str, set] = field(default_factory=dict)
    messages: int = 0
    skipped_messages: int = 0
    max_people: int | None = None
    people_capped: bool = False
    big_messages: int = 0            # messages whose recipient list was cut
    excluded_overflow: dict[str, int] = field(default_factory=dict)
    #: people added to or updated since this Tally was built (not persisted):
    #: a Gmail chunk re-checks exactly these against suppression / exclusions.
    touched: set = field(default_factory=set)

    @property
    def people_limit(self) -> int:
        return MAX_PEOPLE_PER_IMPORT if self.max_people is None else self.max_people

    def _hash_count(self) -> int:
        return sum(len(h) for h in self.excluded.values())

    def _exclude(self, reason: str, email: str | None) -> None:
        digest = flt.email_hash(email or "?invalid")
        bucket = self.excluded.setdefault(reason, set())
        if digest in bucket:
            return
        if self._hash_count() >= MAX_EXCLUDED_HASHES:
            # Bounded memory: past the cap people are counted, not deduplicated.
            self.excluded_overflow[reason] = self.excluded_overflow.get(reason, 0) + 1
            return
        bucket.add(digest)

    def excluded_counts(self) -> dict[str, int]:
        out = {r: len(h) for r, h in self.excluded.items()}
        for r, n in self.excluded_overflow.items():
            out[r] = out.get(r, 0) + n
        return out

    def drop(self, email: str, reason: str) -> None:
        """Remove a kept person (suppressed / erased since): counted by reason."""
        if self.people.pop(email, None) is not None:
            self._exclude(reason, email)

    def _touch(self, raw_email: str | None, name: str | None) -> Person | None:
        email = flt.normalize_email(raw_email)
        reason = flt.static_reason(email, self.own)
        if reason is not None:
            self._exclude(reason, email or raw_email)
            return None
        person = self.people.get(email)
        if person is None:
            if len(self.people) >= self.people_limit:
                self.people_capped = True
                return None
            person = self.people[email] = Person()
        if name and not person.name:
            person.name = name[:NAME_MAX]
        self.touched.add(email)
        return person

    def add_message(self, sender: tuple[str, str] | None, recipients: list[tuple[str, str]],
                    when: datetime | None, automated: bool, sent_label: bool = False) -> None:
        """One message's From / To+Cc. Outgoing (From is one of the user's
        own addresses, or Gmail's SENT label): each recipient was written TO.
        Incoming: the sender wrote to the user. Other recipients of incoming
        mail are not a relationship and are ignored."""
        from_email = flt.normalize_email(sender[1]) if sender else None
        if from_email is None and not sent_label:
            self.skipped_messages += 1
            return
        self.messages += 1
        outgoing = sent_label or (from_email in self.own.addresses)
        if len(recipients) > MAX_RECIPIENTS_PER_MESSAGE:
            self.big_messages += 1
            recipients = recipients[:MAX_RECIPIENTS_PER_MESSAGE]
        if outgoing:
            for name, addr in recipients:
                person = self._touch(addr, name)
                if person is not None:
                    person.sent += 1
                    person.seen(when)
        else:
            person = self._touch(sender[1], sender[0])
            if person is not None:
                person.received += 1
                if automated:
                    person.automated += 1
                person.seen(when)

    # ---- (de)serialisation for a Gmail scan that runs in chunks -----------
    def to_json(self) -> dict:
        return {
            "people": {e: [p.name, p.sent, p.received, p.automated,
                           p.first.isoformat() if p.first else None,
                           p.last.isoformat() if p.last else None]
                       for e, p in self.people.items()},
            "excluded": {r: sorted(h) for r, h in self.excluded.items()},
            "excluded_overflow": dict(self.excluded_overflow),
            "messages": self.messages, "skipped": self.skipped_messages,
            "people_capped": self.people_capped, "big_messages": self.big_messages,
        }

    @classmethod
    def from_json(cls, data: dict | None, own: flt.Own) -> "Tally":
        tally = cls(own=own)
        data = data or {}
        for email, row in (data.get("people") or {}).items():
            name, sent, received, automated, first, last = row
            tally.people[email] = Person(name=name, sent=int(sent), received=int(received),
                                         automated=int(automated),
                                         first=_iso(first), last=_iso(last))
        tally.excluded = {r: set(h) for r, h in (data.get("excluded") or {}).items()}
        tally.excluded_overflow = {r: int(n) for r, n in
                                   (data.get("excluded_overflow") or {}).items()}
        tally.messages = int(data.get("messages") or 0)
        tally.skipped_messages = int(data.get("skipped") or 0)
        tally.people_capped = bool(data.get("people_capped"))
        tally.big_messages = int(data.get("big_messages") or 0)
        return tally


def _iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        out = datetime.fromisoformat(value)
    except ValueError:
        return None
    return out if out.tzinfo else out.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Header values (shared by mbox and Gmail)
# --------------------------------------------------------------------------


def _decode_words(value: str) -> str:
    """RFC 2047 encoded-words -> text. Never raises."""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001 -- malformed encodings are common
        return value


def parse_addresses(value: str | None) -> list[tuple[str, str]]:
    """'"Doe, Jane" <jane@acme.com>, =?utf-8?q?Ren=C3=A9?= <rene@x.io>' ->
    [('Doe, Jane', 'jane@acme.com'), ('René', 'rene@x.io')]."""
    if not value:
        return []
    out = []
    for name, addr in getaddresses([value]):
        addr = (addr or "").strip()
        if "@" not in addr:
            continue
        name = " ".join(_decode_words(name or "").split()).strip().strip('"').strip()
        if name and "@" in name and flt.normalize_email(name) == flt.normalize_email(addr):
            name = ""                                    # "jane@acme.com" <jane@acme.com>
        out.append((name, addr))
    return out


_FUTURE_SLACK = timedelta(days=2)
_EARLIEST = datetime(1990, 1, 1, tzinfo=timezone.utc)


def parse_date(value: str | None, now: datetime | None = None) -> datetime | None:
    if not value:
        return None
    try:
        when = parsedate_to_datetime(value.strip())
    except (TypeError, ValueError, IndexError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    when = when.astimezone(timezone.utc)
    now = now or datetime.now(timezone.utc)
    if when < _EARLIEST or when > now + _FUTURE_SLACK:
        return None
    return when


def message_from_headers(tally: Tally, headers: dict[str, str], *, labels=(),
                         when: datetime | None = None, now: datetime | None = None) -> None:
    """Add one message, given its kept headers (lower-case names)."""
    if "DRAFT" in set(labels or ()):
        return                                           # a draft is not an exchange
    senders = parse_addresses((headers.get("from") or "")[:ADDRESS_HEADER_MAX])
    # Bounded work: only the first ADDRESS_HEADER_MAX characters of To / Cc
    # are parsed (far more than MAX_RECIPIENTS_PER_MESSAGE addresses); the
    # rest of a mass mailing's list is never looked at.
    recipients = (parse_addresses((headers.get("to") or "")[:ADDRESS_HEADER_MAX])
                  + parse_addresses((headers.get("cc") or "")[:ADDRESS_HEADER_MAX]))
    when = when or parse_date(headers.get("date"), now)
    tally.add_message(senders[0] if senders else None, recipients, when,
                      automated=flt.headers_say_automated(headers, labels),
                      sent_label="SENT" in set(labels or ()))


# --------------------------------------------------------------------------
# mbox, streamed
# --------------------------------------------------------------------------

_FIELD = re.compile(rb"^([!-9;-~]+)[ \t]*:")


class MboxStream:
    """Feed it the upload chunk by chunk. Keeps only the wanted header fields
    of each message; body lines are skipped as they arrive."""

    def __init__(self, tally: Tally, *, max_messages: int | None = None,
                 now: datetime | None = None):
        self.tally = tally
        self.max_messages = MAX_MESSAGES if max_messages is None else max_messages
        self.now = now
        self._partial = b""
        self._state = "start"       # start | headers | body
        self._prev_blank = True
        self._fields: list[list[bytes]] = []   # [[name, value bytes], ...]
        self._keep = False                     # is the current field wanted?
        self._header_bytes = 0
        self._from_line_date: datetime | None = None
        self.messages_seen = 0
        self.capped = False
        self.bytes_read = 0

    # ---- input ---------------------------------------------------------
    def feed(self, chunk: bytes) -> None:
        if self.capped or not chunk:
            return
        self.bytes_read += len(chunk)
        data = self._partial + chunk
        lines = data.split(b"\n")
        self._partial = lines.pop()
        if len(self._partial) > MAX_LINE:
            self._partial = b""     # an absurd line (a base64 blob): drop it
        for line in lines:
            self._line(line.rstrip(b"\r"))
            if self.capped:
                return

    def close(self) -> None:
        if self._partial and not self.capped:
            self._line(self._partial.rstrip(b"\r"))
        self._partial = b""
        if self._state == "headers":
            self._end_headers()

    # ---- the state machine ----------------------------------------------
    def _line(self, line: bytes) -> None:
        if line.startswith(b"From ") and (self._prev_blank or self._state == "start") \
                and is_from_line(line):
            if self._state == "headers":
                self._end_headers()
                if self.capped:
                    return
            self._begin(line)
            self._prev_blank = False
            return
        self._prev_blank = (line == b"")
        if self._state == "start":
            raise ParseError("This does not look like a mailbox (.mbox) file.")
        if self._state == "body":
            return                                       # never read, never kept
        # headers
        if line == b"":
            self._end_headers()
            return
        if line[:1] in (b" ", b"\t"):
            if self._keep and self._fields:
                self._add_bytes(line)
                if self._keep:
                    self._fields[-1][1] += b" " + line.strip()
            return
        match = _FIELD.match(line)
        if not match:
            self._keep = False                           # not a header line: ignore
            return
        name = match.group(1).decode("ascii", "replace").lower()
        self._keep = name in WANTED_HEADERS
        if self._keep:
            self._add_bytes(line)
            if self._keep:
                self._fields.append([name.encode(), line[match.end():].strip()])

    def _add_bytes(self, line: bytes) -> None:
        self._header_bytes += len(line)
        if self._header_bytes > MAX_HEADER_BLOCK:
            self._keep = False

    def _begin(self, from_line: bytes) -> None:
        self._state = "headers"
        self._fields = []
        self._keep = False
        self._header_bytes = 0
        tail = from_line[5:].decode("ascii", "replace").split(None, 1)
        self._from_line_date = _asctime(tail[1]) if len(tail) == 2 else None

    def _end_headers(self) -> None:
        self._state = "body"
        if not self._fields:
            return
        if self.messages_seen >= self.max_messages:
            self.capped = True
            return
        self.messages_seen += 1
        headers: dict[str, str] = {}
        for name, value in self._fields:
            key = name.decode()
            text = value.decode("utf-8", "replace")
            # repeated To / Cc lines are concatenated; others keep the first
            if key in headers and key in ("to", "cc"):
                headers[key] += ", " + text
            elif key not in headers:
                headers[key] = text
        self._fields = []
        when = parse_date(headers.get("date"), self.now) or self._from_line_date
        message_from_headers(self.tally, headers, when=when, now=self.now)


def is_from_line(line: bytes) -> bool:
    """A real mbox separator: 'From <sender> <asctime date>' and nothing
    else, e.g. 'From 1780@xxx Sat Oct 10 12:00:00 +0000 2026' (Takeout) or
    'From - Mon Oct  5 10:00:00 2026' (Thunderbird). An unescaped body line
    such as 'From what we saw in 2025 ...' is NOT one (review round M1)."""
    if not line.startswith(b"From ") or len(line) > 1000:
        return False
    try:
        text = line[5:].decode("ascii").rstrip()
    except UnicodeDecodeError:
        return False
    parts = text.split(None, 1)
    if len(parts) != 2:
        return False
    match = _ASCTIME.match(parts[1].strip())
    return bool(match) and match.end() == len(parts[1].strip())


_ASCTIME = re.compile(r"([A-Z][a-z]{2})\s+([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})"
                      r"(?:\s+([+-]\d{4}))?\s+(\d{4})")


def _asctime(text: str) -> datetime | None:
    """The date on an mbox 'From ' line: 'Mon Oct  5 10:00:00 2026' or
    'Mon Oct 05 10:00:00 +0000 2026'."""
    match = _ASCTIME.search(text)
    if not match:
        return None
    _, mon, day, clock, _, year = match.groups()
    try:
        when = datetime.strptime(f"{day} {mon} {year} {clock}", "%d %b %Y %H:%M:%S")
    except ValueError:
        return None
    return when.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Format detection + text decoding
# --------------------------------------------------------------------------

MBOX, VCARD, CSV_FILE = "mbox", "vcard", "csv"


def detect(head: bytes) -> str:
    """From the first bytes of the upload. Raises ParseError."""
    text = head.lstrip(b"\xef\xbb\xbf")
    if text[:2] in (b"\xff\xfe", b"\xfe\xff"):
        sample = head.decode("utf-16", "replace")
    else:
        sample = text.decode("utf-8", "replace")
    stripped = sample.lstrip()
    if stripped.upper().startswith("BEGIN:VCARD"):
        return VCARD
    if text.startswith(b"From ") and is_from_line(text.split(b"\n", 1)[0].rstrip(b"\r")):
        return MBOX
    first = stripped.split("\n", 1)[0].lower()
    if ("mail" in first) and any(sep in first for sep in (",", ";", "\t")):
        return CSV_FILE
    raise ParseError(
        "This file was not recognised. Upload a Google Contacts or Outlook CSV, "
        "a vCard (.vcf) file, or a mailbox (.mbox) export.")


def decode_text(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", "replace")
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", "replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", "replace")


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------


@dataclass
class ContactsResult:
    kind: str
    rows: list[ContactRow] = field(default_factory=list)
    rows_in_file: int = 0
    capped: bool = False


def _clean(value: str | None, limit: int = NAME_MAX) -> str | None:
    value = " ".join((value or "").split())
    return value[:limit] or None


def _split_cell(value: str | None) -> list[str]:
    """At most MAX_ADDRESSES_PER_CELL addresses from one cell; a cell holding
    thousands is not one person's addresses."""
    out = []
    for v in re.split(r"\s*:::\s*|\s*;\s*", (value or "")[:20_000]):
        if v.strip():
            out.append(v.strip())
            if len(out) >= MAX_ADDRESSES_PER_CELL:
                break
    return out


CSV_UNREADABLE = ("This CSV file could not be read: a cell is too large (over 128 KB) or "
                  "the file is malformed. Export the contacts again without notes, or "
                  "remove the large column.")


def parse_csv(text: str, *, max_rows: int = MAX_CONTACT_ROWS) -> ContactsResult:
    lines = text.splitlines()
    if not lines:
        raise ParseError("The file is empty.")
    header_line = lines[0]
    delimiter = max((",", ";", "\t"), key=header_line.count)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = [h.strip().lower() for h in next(reader)]
    except StopIteration:
        raise ParseError("The file is empty.") from None
    except csv.Error:
        raise ParseError(CSV_UNREADABLE) from None
    index = {name: i for i, name in enumerate(header) if name}

    def cols(*names: str) -> list[int]:
        return [index[n] for n in names if n in index]

    google = [i for n, i in index.items() if re.fullmatch(r"e-mail \d+ - value", n)]
    outlook = cols("e-mail address", "e-mail 2 address", "e-mail 3 address")
    if google:
        kind, email_cols = "google_csv", google
    elif outlook:
        kind, email_cols = "outlook_csv", outlook
    else:
        email_cols = [i for n, i in index.items()
                      if re.search(r"(^|[\s_-])(e-?mail)([\s_-]|$)", n) or n in ("email", "e-mail")]
        kind = "csv"
    if not email_cols:
        raise ParseError("No e-mail column was found in this CSV file.")

    first = cols("first name", "given name")
    middle = cols("middle name", "additional name")
    last = cols("last name", "family name", "surname")
    full = cols("name", "display name", "full name")
    company = cols("organization name", "organization 1 - name", "company", "organization",
                   "company name")
    title = cols("organization title", "organization 1 - title", "job title", "title")

    def pick(row: list[str], indices: list[int]) -> str | None:
        for i in indices:
            if i < len(row) and row[i].strip():
                return row[i]
        return None

    result = ContactsResult(kind=kind)
    for row in _safe_rows(reader):
        if not any(cell.strip() for cell in row):
            continue
        result.rows_in_file += 1
        if result.rows_in_file > max_rows:
            result.capped = True
            result.rows_in_file -= 1
            break
        name = _clean(pick(row, full)) or _clean(" ".join(
            p for p in (pick(row, first), pick(row, middle), pick(row, last)) if p))
        org = _clean(pick(row, company))
        role = _clean(pick(row, title))
        for i in email_cols:
            if i >= len(row):
                continue
            for addr in _split_cell(row[i]):
                result.rows.append(ContactRow(email=addr, name=name, company=org, title=role))
        if len(result.rows) >= MAX_CONTACT_ADDRESSES:
            result.capped = True
            break
    return result


def _safe_rows(reader):
    """csv.reader, with its errors (a field over 128 KiB, a NUL byte) turned
    into our own fixed sentence instead of an unhandled 500 (review M7)."""
    while True:
        try:
            yield next(reader)
        except StopIteration:
            return
        except csv.Error:
            raise ParseError(CSV_UNREADABLE) from None


# --------------------------------------------------------------------------
# vCard
# --------------------------------------------------------------------------


#: The only vCard properties ever read. Everything else -- PHOTO, LOGO, KEY,
#: SOUND (base64 blobs of megabytes), NOTE, ADR ... -- is skipped with its
#: continuation lines, without being assembled (review round M8).
_VCARD_WANTED = frozenset({"BEGIN", "END", "FN", "N", "EMAIL", "ORG", "TITLE"})
_VCARD_VALUE_MAX = 4000


def _vcard_name(line: str) -> str:
    head = re.split(r"[;:]", line, maxsplit=1)[0]
    return head.split(".")[-1].strip().upper()


def _vcard_lines(text: str):
    """Unfold RFC 6350 continuation lines and vCard 2.1 quoted-printable soft
    line breaks into logical lines -- linear time: fragments are collected
    in a list and joined once, and unwanted properties are never assembled."""
    parts: list[str] = []
    keep = False
    qp = False
    size = 0

    def flush():
        return "".join(parts) if keep and parts else None

    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        continuation = line[:1] in (" ", "\t")
        soft_break = qp and parts and parts[-1].endswith("=")
        if (continuation or soft_break) and (parts or not keep):
            if keep and size < _VCARD_VALUE_MAX:
                if soft_break and not continuation:
                    parts[-1] = parts[-1][:-1]
                    parts.append(line)
                else:
                    parts.append(line[1:])
                size += len(line)
            continue
        done = flush()
        if done is not None:
            yield done
        keep = _vcard_name(line) in _VCARD_WANTED
        head = line.split(":", 1)[0].upper()
        qp = "QUOTED-PRINTABLE" in head
        parts = [line[:_VCARD_VALUE_MAX]] if keep else []
        size = len(parts[0]) if parts else 0
    done = flush()
    if done is not None:
        yield done


def _unescape(value: str) -> str:
    return (value.replace("\\n", " ").replace("\\N", " ").replace("\\,", ",")
            .replace("\\;", ";").replace("\\\\", "\\"))


def _split_unescaped(value: str, sep: str = ";") -> list[str]:
    parts, buf, escaped = [], "", False
    for ch in value:
        if escaped:
            buf += "\\" + ch
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == sep:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    parts.append(buf)
    return [_unescape(p) for p in parts]


def _property(line: str) -> tuple[str, dict, str] | None:
    if ":" not in line:
        return None
    head, value = line.split(":", 1)
    bits = head.split(";")
    name = bits[0].split(".")[-1].strip().upper()      # drop an "item1." group
    params: dict[str, str] = {}
    for bit in bits[1:]:
        if "=" in bit:
            k, v = bit.split("=", 1)
            params[k.strip().upper()] = v.strip().strip('"')
        else:
            params.setdefault("TYPE", bit.strip())
    if params.get("ENCODING", "").upper() in ("QUOTED-PRINTABLE", "Q"):
        charset = params.get("CHARSET", "utf-8")
        try:
            value = quopri.decodestring(value.encode("latin-1", "replace")).decode(
                charset, "replace")
        except LookupError:
            value = quopri.decodestring(value.encode("latin-1", "replace")).decode(
                "utf-8", "replace")
    return name, params, value


def parse_vcard(text: str, *, max_rows: int = MAX_CONTACT_ROWS) -> ContactsResult:
    result = ContactsResult(kind="vcard")
    card: dict | None = None
    for line in _vcard_lines(text):
        prop = _property(line)
        if prop is None:
            continue
        name, params, value = prop
        if name == "BEGIN" and value.strip().upper() == "VCARD":
            card = {"emails": []}
            continue
        if card is None:
            continue
        if name == "END" and value.strip().upper() == "VCARD":
            result.rows_in_file += 1
            if result.rows_in_file > max_rows:
                result.capped = True
                result.rows_in_file -= 1
                break
            display = card.get("fn") or card.get("n")
            for addr in card["emails"]:
                result.rows.append(ContactRow(email=addr, name=_clean(display),
                                              company=_clean(card.get("org")),
                                              title=_clean(card.get("title"))))
            card = None
            continue
        if name == "FN":
            card["fn"] = _unescape(value)
        elif name == "N":
            parts = _split_unescaped(value) + [""] * 5
            family, given, middle = parts[0], parts[1], parts[2]
            card["n"] = " ".join(p for p in (given, middle, family) if p.strip())
        elif name == "EMAIL":
            addr = _unescape(value).strip()
            if addr.lower().startswith("mailto:"):
                addr = addr[7:]
            if addr:
                card["emails"].append(addr)
        elif name == "ORG":
            card["org"] = _split_unescaped(value)[0]
        elif name == "TITLE":
            card["title"] = _unescape(value)
    if result.rows_in_file == 0 and not result.capped:
        raise ParseError("No contacts were found in this vCard file.")
    return result


def parse_contacts(data: bytes) -> ContactsResult:
    """A whole contacts file (CSV or vCard), already size-capped."""
    kind = detect(data[:4096])
    if kind == MBOX:
        raise ParseError("A mailbox file must be streamed (internal error).")
    text = decode_text(data)
    return parse_vcard(text) if kind == VCARD else parse_csv(text)


def contacts_into(tally: Tally, rows: list[ContactRow]) -> dict[str, ContactRow]:
    """Apply the fixed rules to contacts-file rows. Returns the kept rows by
    normalised address (a later row for the same address fills gaps)."""
    kept: dict[str, ContactRow] = {}
    for row in rows:
        email = flt.normalize_email(row.email)
        reason = flt.static_reason(email, tally.own)
        if reason is not None:
            tally._exclude(reason, email or row.email)  # noqa: SLF001
            continue
        current = kept.get(email)
        if current is None:
            if len(kept) >= tally.people_limit:
                tally.people_capped = True
                continue
            kept[email] = ContactRow(email=email, name=row.name, company=row.company,
                                     title=row.title)
        else:
            current.name = current.name or row.name
            current.company = current.company or row.company
            current.title = current.title or row.title
    return kept


# --------------------------------------------------------------------------
# Company from a domain (no website is ever fetched)
# --------------------------------------------------------------------------

_SECOND_LEVEL = frozenset({
    "co.uk", "org.uk", "ac.uk", "gov.uk", "ltd.uk", "plc.uk", "me.uk", "com.au", "net.au",
    "org.au", "co.nz", "co.in", "co.za", "com.br", "com.mx", "com.pk", "com.sg", "co.jp",
    "com.cn", "com.hk", "com.tr", "com.ar", "co.il", "co.kr", "com.my", "com.ph", "com.ng",
})


def company_from_domain(domain: str) -> str | None:
    labels = domain.lower().split(".")
    if len(labels) < 2:
        return None
    if len(labels) >= 3 and ".".join(labels[-2:]) in _SECOND_LEVEL:
        stem = labels[-3]
    else:
        stem = labels[-2]
    words = [w for w in re.split(r"[-_]+", stem) if w]
    if not words:
        return None
    return " ".join(w.capitalize() for w in words)[:NAME_MAX]

"""Email threading headers (RFC 5322 section 3.6.4) for replies we send.

WHY. A Reply Copilot answer used to be sent with Gmail's `threadId` only.
That keeps it in the thread in the SENDER's Gmail, but the prospect's client
(Outlook, Apple Mail, Gmail on another account...) threads by the
`In-Reply-To` and `References` headers, which were never set -- so the answer
arrived as a new, unrelated email. A reply to a message must carry:

    In-Reply-To: <the parent's Message-ID>
    References:  <the parent's References, or its In-Reply-To> <parent's Message-ID>

WHAT IS STORED. The inbound reply's own Message-ID and References chain
(InboundReply.rfc_message_id / rfc_references, migration 0086), captured by
the Gmail adapter. Replies stored before that migration have neither; their
answers still go out (Gmail threadId only), exactly as before.

SAFETY. These values come from a stranger's email and end up in OUR outgoing
headers, so only angle-bracketed ids made of printable ASCII (no spaces, no
CR/LF, no nested brackets) survive. Anything else is dropped -- never a
header-injection vector -- and an absent or malformed Message-ID means no
threading headers at all rather than a wrong one.
"""

from __future__ import annotations

import re

#: One msg-id: "<" printable-ASCII-without-angle-brackets-or-space ">".
_MSG_ID = re.compile(r"<[\x21-\x3b\x3d\x3f-\x7e]{1,500}>")
#: Bound on the References chain we keep and send (the first id plus the most
#: recent ones, as RFC 5322 suggests when trimming).
MAX_REFERENCES = 20
#: Column sizes (app/db/models.py InboundReply).
MAX_ID_LENGTH = 502


def message_ids(raw: str | None) -> list[str]:
    """Every well-formed msg-id in `raw`, in order, without duplicates."""
    seen: list[str] = []
    for token in _MSG_ID.findall(raw or ""):
        if token not in seen:
            seen.append(token)
    return seen


def clean_message_id(raw: str | None) -> str | None:
    """The first well-formed msg-id in a Message-ID header value, or None."""
    ids = message_ids(raw)
    return ids[0] if ids else None


def _trim(ids: list[str]) -> list[str]:
    if len(ids) <= MAX_REFERENCES:
        return ids
    return [ids[0], *ids[-(MAX_REFERENCES - 1):]]


def clean_references(references: str | None, in_reply_to: str | None = None) -> str | None:
    """The message's References chain as stored: its References header, or
    (RFC 5322: when there is none) its In-Reply-To. Sanitised and trimmed."""
    ids = message_ids(references) or message_ids(in_reply_to)
    return " ".join(_trim(ids)) or None


def reply_headers(parent_message_id: str | None,
                  parent_references: str | None) -> dict[str, str]:
    """{In-Reply-To, References} for a reply to the parent, or {} when the
    parent's Message-ID is unknown (or not well-formed)."""
    parent = clean_message_id(parent_message_id)
    if parent is None:
        return {}
    chain = [i for i in message_ids(parent_references) if i != parent]
    return {"In-Reply-To": parent, "References": " ".join(_trim([*chain, parent]))}

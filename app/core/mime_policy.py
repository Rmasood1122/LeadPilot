"""The email policy every outbound message is built with.

WHY (gaps-sweep-2 review, HIGH). `EmailMessage()` defaults to
`email.policy.default`, whose max_line_length is 78. A header value with no
folding point longer than that -- the List-Unsubscribe URL with its ~200
character encrypted token, or a Microsoft 365 Message-ID in In-Reply-To /
References -- is then RFC 2047 encoded on output:

    List-Unsubscribe: =?utf-8?q?=3Chttps=3A//api=2E...?=
     =?utf-8?q?...?=

RFC 2369 / RFC 8058 header values are URIs in angle brackets; an encoded word
is not one, so receivers (Gmail, Yahoo) cannot use the one-click unsubscribe,
and an encoded msg-id does not thread. RFC 5322 allows a line of up to 998
characters, so with `max_line_length=998` such headers go out raw and
unfolded. Non-ASCII text (a Subject with an accent) is still encoded, as it
must be. Line endings stay "\n" as before (the default policy's): the Gmail
API and smtplib both accept them, and the sealed test that the Gmail channel
sends exactly build_mime compares the parsed bytes with the built message.

Use OUTBOUND_POLICY for every EmailMessage that leaves the system:
app/integrations/gmail.py (build_mime, Gmail drafts) and
app/services/email_sender.py (SMTP system mail).
"""

from __future__ import annotations

import email.policy

#: RFC 5322 line limit (2.1.1).
OUTBOUND_POLICY = email.policy.default.clone(max_line_length=998)


def raw_header_lines(raw: bytes, name: str) -> list[list[str]]:
    """Every occurrence of header `name` in the RAW header block of `raw`, as
    its physical lines (first line + any folded continuation lines). Used to
    check what is actually transmitted, not what a parser decodes it to."""
    head = raw.replace(b"\r\n", b"\n").split(b"\n\n", 1)[0].decode("ascii", "replace")
    lines = head.split("\n")
    found: list[list[str]] = []
    prefix = name.lower() + ":"
    for i, line in enumerate(lines):
        if line.lower().startswith(prefix):
            block = [line]
            for nxt in lines[i + 1:]:
                if nxt[:1] in (" ", "\t"):
                    block.append(nxt)
                else:
                    break
            found.append(block)
    return found


def raw_header_value(raw: bytes, name: str) -> str | None:
    """The raw value of the first `name` header, exactly as transmitted on a
    single line, or None when it is missing, folded or RFC 2047 encoded."""
    blocks = raw_header_lines(raw, name)
    if not blocks or len(blocks[0]) != 1:
        return None
    value = blocks[0][0].split(":", 1)[1].strip()
    return None if "=?" in value else value

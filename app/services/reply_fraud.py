"""Reply fraud detection: is this "reply" a machine? (Feature Group 9)

An auto-acknowledgement ("we received your message, ticket #4411"), a
no-reply bot or a helpdesk system classified as `interested` or `question`
would stop a sequence, mark the lead REPLIED and inflate reply rates, the
sentiment chart and the learning loop. So after the normal classification,
any ENGAGED class (interested / question / objection / not_interested) gets
a second pass:

  1. heuristics -- a no-reply style sender or an auto-reply subject is
     conclusive on its own; two weaker body signals together are too;
  2. one weak signal -> a short Claude check ("automated or human?");
  3. no signal -> human. The model is never asked about an ordinary reply,
     so this adds no cost to the common case.

A reply judged automated is stored with classification
`automated_response`: it is visible in the lead's inbox, but it is not a
reply -- no REPLIED outcome, no status change, the sequence neither stops
nor advances, and it is excluded from every engagement metric.
Out-of-office replies keep their own class (they pause the sequence).
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

AUTOMATED = "automated_response"
ENGAGED = frozenset({"interested", "question", "objection", "not_interested"})

_FROM = re.compile(r"^(no-?reply|do-?not-?reply|donotreply|mailer-daemon|postmaster|bounces?|"
                   r"notifications?|auto-?reply|auto-?responder|system|support-noreply)"
                   r"([+.\-_][^@]*)?@", re.I)
_SUBJECT = re.compile(r"^\s*(\[?auto(matic)?[ -]?(reply|response|answer)\]?|autoreply|auto:|"
                      r"automatische antwort|r[ée]ponse automatique|respuesta autom[áa]tica|"
                      r"risposta automatica|delivery status notification)", re.I)
_BODY = [re.compile(p, re.I) for p in (
    r"this is an? (automated|automatic) (message|response|reply|e-?mail)",
    r"(please )?do not reply to this (e-?mail|message)",
    r"(we|i) (have )?received your (e-?mail|message|request|enquiry|inquiry)",
    r"\bticket\s*(number|no\.?|#|id)\b",
    r"thank you for (contacting|reaching out to) (us|our)",
    r"your (request|message) has been (received|logged|forwarded)",
    r"(this|the) (mailbox|inbox) is (not|un)monitored",
    r"one of our (team|agents|representatives) will (get back|respond|be in touch)",
)]

DETECTOR_SYSTEM = (
    "You are LeadPilot's automated-reply detector. Decide whether an inbound "
    "email was written by a PERSON or sent automatically (auto-acknowledgement, "
    "helpdesk/ticket system, no-reply bot, newsletter, vacation responder). "
    'Respond with ONLY JSON: {"automated": true|false, "reason": "<short>"}.'
)


def signals(from_address: str | None, subject: str | None, body: str | None) -> list[str]:
    found = []
    if from_address and _FROM.match(from_address.strip()):
        found.append("from:no-reply sender")
    if subject and _SUBJECT.match(subject):
        found.append("subject:auto-reply subject")
    text = (body or "")[:4000]
    found.extend(f"body:{p.pattern[:40]}" for p in _BODY if p.search(text))
    return found


def is_automated(from_address: str | None, subject: str | None, body: str | None, *,
                 use_model: bool = True) -> tuple[bool, str]:
    found = signals(from_address, subject, body)
    strong = any(s.startswith(("from:", "subject:")) for s in found)
    if strong or len(found) >= 2:
        return True, "; ".join(found)
    if found and use_model:
        try:
            from app.services.anthropic_client import get_client  # noqa: PLC0415

            data = get_client().complete_json(
                system=DETECTOR_SYSTEM, max_tokens=200,
                prompt=(f"FROM: {from_address}\nSUBJECT: {subject or '(none)'}\n\n"
                        f"BODY:\n{(body or '')[:3000]}\n\nAutomated or human?"))
            if bool(data.get("automated")):
                return True, str(data.get("reason") or found[0])[:200]
        except Exception:  # noqa: BLE001 -- when unsure, it is a human reply
            logger.warning("automated-reply check failed; treating as human")
    return False, ""


def second_pass(classification: str, from_address: str | None, subject: str | None,
                body: str | None, *, enabled: bool = True) -> str:
    """The final class: `automated_response` if an engaged reply is a machine."""
    if not enabled or classification not in ENGAGED:
        return classification
    automated, reason = is_automated(from_address, subject, body)
    if automated:
        logger.info("reply from %s reclassified %s -> automated_response (%s)",
                    from_address, classification, reason)
        return AUTOMATED
    return classification

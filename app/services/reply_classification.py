"""Reply classification — one Claude call per inbound message.

Classes and their routing (implemented in app/services/sequence_engine.py
+ app/workers/outreach_tasks.py):
    interested / question / objection / not_interested
        -> sequence stops, lead becomes REPLIED, reply stored for the user
    unsubscribe_request  -> EXACTLY like an unsubscribe click: suppression
                            + hard stop, immediately
    out_of_office        -> sequence pauses and reschedules (does not stop)
    bounce               -> bounce outcome + campaign bounce-rate check

LeadPilot does NOT auto-reply to humans in M3.
"""

import logging

from app.services.anthropic_client import get_client

logger = logging.getLogger(__name__)

REPLY_CLASSES = [
    "interested",
    "question",
    "objection",
    "not_interested",
    "unsubscribe_request",
    "out_of_office",
    "bounce",
]

_SYSTEM = (
    "You are LeadPilot's inbound reply classifier. Classify one inbound "
    "email into exactly one class. Respond with ONLY a JSON object: "
    '{"classification": "<class>"} where <class> is one of: '
    + ", ".join(REPLY_CLASSES) + ". "
    "Rules: any request to stop contacting (e.g. 'stop emailing me', "
    "'remove me', 'take me off your list') is unsubscribe_request. "
    "Automated delivery-failure notices (mailer-daemon, 'address not "
    "found', 'undeliverable') are bounce. Auto-replies about absence are "
    "out_of_office."
)

_PROMPT = """FROM: {from_address}
SUBJECT: {subject}

BODY:
{body}

Classify this inbound email."""


def classify_reply(from_address: str, subject: str | None, body: str) -> str:
    """Returns one of REPLY_CLASSES; unparseable/unknown answers degrade to
    'question' (safe: stops the sequence and asks the human to look)."""
    try:
        data = get_client().complete_json(
            system=_SYSTEM,
            prompt=_PROMPT.format(
                from_address=from_address,
                subject=subject or "(none)",
                body=body[:4000],
            ),
        )
        cls = str(data.get("classification", "")).strip().lower()
        if cls in REPLY_CLASSES:
            return cls
        logger.warning("classifier returned unknown class %r — using 'question'", cls)
    except Exception:
        logger.exception("reply classification failed — using 'question'")
    return "question"

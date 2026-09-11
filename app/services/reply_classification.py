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
    # Feature Group 9: a machine, not a person (see app/services/reply_fraud.py).
    "automated_response",
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
    "out_of_office. Other automatic messages -- receipt acknowledgements, "
    "helpdesk tickets, no-reply bots -- are automated_response."
)

_PROMPT = """FROM: {from_address}
SUBJECT: {subject}

BODY:
{body}

Classify this inbound email."""


def classify_reply(from_address: str, subject: str | None, body: str,
                   session=None) -> str:
    """Returns one of REPLY_CLASSES; unparseable/unknown answers degrade to
    'question' (safe: stops the sequence and asks the human to look).

    Feature Group 9: an engaged class then gets the automated-reply second
    pass (reply_fraud.second_pass), unless the admin turned
    `reply_fraud_detection_enabled` off."""
    from app.services import reply_fraud  # noqa: PLC0415

    enabled = True
    if session is not None:
        from app.services import system_settings  # noqa: PLC0415

        enabled = bool(system_settings.get(session, "reply_fraud_detection_enabled"))
    return reply_fraud.second_pass(_classify(from_address, subject, body),
                                   from_address, subject, body, enabled=enabled)


def _classify(from_address: str, subject: str | None, body: str) -> str:
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

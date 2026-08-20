"""Pattern recognition — Flow 1's engine room.

Takes free-text past-client details + acquisition story and extracts the
seven structured patterns from the project knowledge (section B, Flow 1):
industry, company_size, buyer_role, deal_size, acquisition_channel,
trigger_event, sales_cycle_length. The result is stored on
past_clients.extracted_patterns_json and anchors the Flow 1 strategy.
"""

import logging

from app.services.anthropic_client import get_client

logger = logging.getLogger(__name__)

PATTERN_KEYS = [
    "industry",
    "company_size",
    "buyer_role",
    "deal_size",
    "acquisition_channel",
    "trigger_event",
    "sales_cycle_length",
]

_SYSTEM = (
    "You are a B2B sales analyst. You extract structured acquisition "
    "patterns from a founder's description of a past client. Respond with "
    "ONLY a single JSON object — no prose, no markdown fences."
)

_PROMPT = """From the past-client description below, extract these fields.
Use null for anything not stated or safely inferable. Keep values short
(a few words each).

Required JSON keys:
- industry: the client's industry/vertical
- company_size: employee count or bracket (e.g. "11-50")
- buyer_role: title/role of the decision maker who bought
- deal_size: amount + currency, or bracket
- acquisition_channel: how the client was acquired (e.g. "referral",
  "cold email", "LinkedIn", "inbound")
- trigger_event: what prompted them to buy (e.g. "failed audit",
  "new funding", "compliance deadline")
- sales_cycle_length: first contact to close (e.g. "3 weeks")
- confidence: object mapping each key above to "stated" | "inferred" | null

CLIENT DETAILS:
{details}

HOW THEY WERE ACQUIRED:
{acquisition_story}
"""


def extract_patterns(details: str, acquisition_story: str) -> dict:
    """Extract structured patterns for one past client.

    Always returns a dict containing every PATTERN_KEY (missing/failed
    extractions become None) plus `_extraction_error` when the model call
    or parsing failed, so intake never hard-fails on a bad extraction —
    the strategy pipeline treats None patterns as "unknown".
    """
    client = get_client()
    try:
        data = client.complete_json(
            system=_SYSTEM,
            prompt=_PROMPT.format(details=details, acquisition_story=acquisition_story),
        )
    except Exception as exc:  # extraction must never break intake
        logger.warning("pattern extraction failed: %s", exc)
        return {**{k: None for k in PATTERN_KEYS}, "_extraction_error": str(exc)}

    result = {k: data.get(k) for k in PATTERN_KEYS}
    if isinstance(data.get("confidence"), dict):
        result["confidence"] = data["confidence"]
    return result

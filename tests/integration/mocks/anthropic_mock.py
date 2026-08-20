"""
Anthropic API transport mock.

Returns deterministic, phase-appropriate outputs for the 72/144-step pipeline
and for each of the 10 verification passes. Outputs are minimal-but-valid JSON
so the pipeline engine can parse them and subsequent pipeline stages can consume
them (e.g., Phase 2 ICP output is later used to build Apollo search params).
"""
from __future__ import annotations

import json
import re
from typing import Any

import respx
from httpx import Request, Response

# ---------------------------------------------------------------------------
# Canonical phase outputs (consumed by downstream pipeline stages + assertions)
# ---------------------------------------------------------------------------

PHASE_OUTPUTS: dict[int, dict[str, Any]] = {
    1: {  # Product decomposition
        "value_prop": "AI-powered outreach automation",
        "differentiators": ["24/7 cloud operation", "self-learning playbook"],
        "pricing_logic": "SaaS per seat",
    },
    2: {  # ICP
        "firmographics": {
            "company_size": "11-200",
            "industries": ["SaaS", "professional services"],
            "revenue_range": "$1M-$50M",
        },
        "personas": [
            {"title": "VP Sales", "pain_points": ["manual prospecting", "low reply rates"]},
            {"title": "Founder", "pain_points": ["no sales team", "time-poor"]},
        ],
        "buying_triggers": ["new funding", "sales team expansion"],
    },
    3: {"tam_usd": 4_200_000_000, "segments": ["SMB SaaS", "Agencies"], "priority_segment": "SMB SaaS"},
    4: {"competitors": ["Outreach.io", "Apollo.io"], "positioning_gap": "AI-first SMB focus"},
    5: {
        "channel_ranking": ["email", "whatsapp", "linkedin"],
        "email": {"expected_open_rate": 0.28, "expected_reply_rate": 0.08},
    },
    6: {
        "subject_line_variants": ["Stop wasting hours on cold outreach", "AI that books meetings for you"],
        "offer": "14-day free pilot",
        "hook": "We found 3 companies in your ICP that replied this week",
        "playbook_context_key": "icp_smb_saas_email",  # must be present in Phase 6 prompt
    },
    7: {"objections": ["price", "integration effort"], "proof_assets": ["case studies", "free trial"]},
    8: {
        "sequence_steps": 5,
        "cadence_days": [0, 3, 7, 14, 21],
        "kpis": {"reply_rate_target": 0.08, "meeting_rate_target": 0.03},
        "playbook_context_key": "icp_smb_saas_email",  # must be present in Phase 8 prompt
    },
}

GTM_PHASE_OUTPUTS: dict[int, dict[str, Any]] = {
    1: {"positioning": "AI-first SMB outreach automation"},
    2: {"pricing_tiers": ["Starter $99/mo", "Growth $299/mo", "Enterprise custom"]},
    3: {"launch_week": "LinkedIn + ProductHunt", "sequence": ["soft launch", "hard launch", "follow-up"]},
    4: {"channel_budget": {"email": 0.4, "linkedin": 0.4, "content": 0.2}},
    5: {"content_plan": ["3 founder posts/week", "weekly case study", "email newsletter"]},
    6: {"partnerships": ["Apollo resellers", "HubSpot integrators"]},
    7: {"sales_motion": "PLG with sales assist above $1k ACV"},
    8: {"funnel_metrics": {"visitor_to_trial": 0.05, "trial_to_paid": 0.20}},
}

VERIFICATION_PASS_OUTPUTS: dict[int, dict[str, Any]] = {
    i: {"pass_number": i, "result": "PASS", "notes": f"Verification pass {i} completed"}
    for i in range(1, 11)
}

# pattern_recognition.PATTERN_KEYS -- the seven structured patterns Flow 1
# anchors on. Keys must match exactly; extract_patterns() drops anything else.
PAST_CLIENT_PATTERNS: dict[str, Any] = {
    "industry": "SaaS",
    "company_size": "11-50",
    "buyer_role": "VP Sales",
    "deal_size": "$12k ARR",
    "acquisition_channel": "cold email",
    "trigger_event": "new funding round",
    "sales_cycle_length": "3 weeks",
    "confidence": {
        "industry": "stated",
        "company_size": "stated",
        "buyer_role": "stated",
        "deal_size": "inferred",
        "acquisition_channel": "stated",
        "trigger_event": "inferred",
        "sales_cycle_length": "stated",
    },
}

# icp_extraction.extract_tactic_profile -- the closed tactic vocabulary that
# forms the second half of Strategy.pattern_key. Values must come from
# TACTIC_CHANNELS / TACTIC_MOTIONS / TACTIC_CADENCES or they are filtered out.
TACTIC_PROFILE: dict[str, Any] = {
    "channels": ["email", "whatsapp"],
    "sales_motion": "cold_outbound",
    "cadence": "standard",
}

# icp_extraction._PROMPT -- becomes the Apollo people-search params, so these
# values are what test_lead_sourcing_uses_icp_params_from_phase_2 asserts on.
ICP_CRITERIA: dict[str, Any] = {
    "titles": ["VP Sales", "Founder", "Head of Growth"],
    "industries": ["SaaS", "professional services"],
    "locations": ["North America, United States"],
    "company_size_ranges": ["11,200"],
    "keywords": ["outbound", "cold email", "pipeline"],
}


# ---------------------------------------------------------------------------
# Request routing
#
# Every Anthropic caller in the app sends a DISTINCT system prompt, and that is
# the only reliable discriminator. This mock used to regex the combined text
# for "step_no: N" / "pass N", which was wrong in both directions:
#
#   * the pipeline's PROMPT_TEMPLATE contains no step number at all -- only
#     "CURRENT PHASE: <title>" -- so the number the regex found came out of the
#     injected context block, where prior steps' JSON outputs carry their own
#     "step_no". Step 46 was therefore answered with Phase 1's output.
#   * the verification judge's prompt says "CRITERION #n", never "pass n", so
#     pass_no was always None, the judge got a step payload with no "result"
#     key, and all 10 passes failed 3 attempts each on every strategy -- which
#     is why nothing ever reached VERIFIED and every lead-sourcing test 409'd.
#
# Phase is now resolved by matching "CURRENT PHASE: <title>" against the real
# registry, so the mock and the pipeline can never drift apart silently.
# ---------------------------------------------------------------------------

from app.pipeline.registry import GTM_PHASES, STRATEGY_PHASES

_STRATEGY_PHASE_BY_TITLE = {title: i for i, (title, _) in enumerate(STRATEGY_PHASES, start=1)}
_GTM_PHASE_BY_TITLE = {title: i for i, (title, _) in enumerate(GTM_PHASES, start=1)}


def _current_phase(combined: str) -> tuple[str, int] | None:
    """('strategy'|'gtm', phase) for a pipeline research call, else None."""
    m = re.search(r"CURRENT PHASE:\s*(.+)", combined)
    if not m:
        return None
    title = m.group(1).strip()
    if title in _STRATEGY_PHASE_BY_TITLE:
        return "strategy", _STRATEGY_PHASE_BY_TITLE[title]
    if title in _GTM_PHASE_BY_TITLE:
        return "gtm", _GTM_PHASE_BY_TITLE[title]
    raise AssertionError(
        f"anthropic_mock: unknown CURRENT PHASE {title!r}. The pipeline "
        "registry changed; update the mock's phase outputs to match."
    )


def _criterion_no(combined: str) -> int | None:
    """Verification pass number from the judge prompt's 'CRITERION #n' line."""
    m = re.search(r"CRITERION #(\d+)", combined)
    return int(m.group(1)) if m else None


def _system_of(request_body: dict) -> str:
    sys_field = request_body.get("system", "")
    if isinstance(sys_field, list):
        return " ".join(b.get("text", "") for b in sys_field if isinstance(b, dict))
    return sys_field or ""


def _user_text(request_body: dict) -> str:
    """Just the user message(s) -- never the system prompt.

    The classifier branch must read ONLY this: the reply-classifier's SYSTEM
    prompt quotes its own examples ("stop emailing me", "remove me", "take me
    off your list"), so matching against system+user classified every reply,
    including "Yes, I would love to chat!", as unsubscribe_request.
    """
    messages = request_body.get("messages", [])
    return " ".join(
        (m.get("content", "") if isinstance(m.get("content"), str)
         else " ".join(c.get("text", "") for c in m.get("content", []) if isinstance(c, dict)))
        for m in messages
    )


def _classify_reply_body(user_text: str) -> str:
    """Mirror the documented classifier rules on the message body."""
    body = user_text.lower()
    if any(k in body for k in ("stop emailing", "remove me", "unsubscribe",
                               "take me off")):
        return "unsubscribe_request"
    if any(k in body for k in ("out of office", "on leave", "annual leave")):
        return "out_of_office"
    if any(k in body for k in ("mailer-daemon", "address not found",
                              "undeliverable", "delivery has failed")):
        return "bounce"
    if any(k in body for k in ("not interested", "no thanks", "please stop sending")):
        return "not_interested"
    if "?" in body and "love to chat" not in body:
        return "question"
    return "interested"


def _build_content_text(system: str, combined: str, user_text: str = "") -> str:
    """Answer as whichever caller sent this system prompt."""

    # --- 10x verification loop -------------------------------------------
    if "senior go-to-market reviewer" in system:
        pass_no = _criterion_no(combined)
        return json.dumps(VERIFICATION_PASS_OUTPUTS.get(
            pass_no or 0, {"result": "PASS"}))

    if "strategy editor" in system:
        # The fixer returns a whole revised document, not JSON.
        return "# Revised strategy document\n\nFinding resolved."

    # --- pattern recognition (Flow 1 intake) ------------------------------
    if "B2B sales analyst" in system:
        return json.dumps(PAST_CLIENT_PATTERNS)

    # --- ICP extraction (drives the Apollo search params) -----------------
    if "ICP extraction engine" in system:
        return json.dumps(ICP_CRITERIA)

    # --- tactic classification (the "/tactic" half of pattern_key) --------
    if "go-to-market classifier" in system:
        return json.dumps(TACTIC_PROFILE)

    # --- inbound reply classification -------------------------------------
    if "inbound reply classifier" in system:
        return json.dumps({"classification": _classify_reply_body(user_text)})

    # --- message personalization ------------------------------------------
    if _is_personalization(system + " " + combined):
        return json.dumps({
            "subject": "Quick question about your onboarding",
            "body": ("Noticed your team has been scaling fast. We help "
                     "companies like yours cut onboarding time in half. "
                     "Worth a short call next week?"),
        })

    # --- 72/144-step research pipeline ------------------------------------
    phase_info = _current_phase(combined)
    if phase_info is not None:
        pipeline, phase = phase_info
        table = GTM_PHASE_OUTPUTS if pipeline == "gtm" else PHASE_OUTPUTS
        output = table.get(phase, {"status": "complete"})
        return json.dumps({**output, "pipeline": pipeline, "phase": phase})

    return json.dumps({"result": "ok"})


def _is_personalization(combined: str) -> bool:
    """True for message_personalization.render_message() calls.

    Its system prompt names the personalization engine and demands
    {"subject": ..., "body": ...}. Without this branch the mock fell through
    to the generic {"result": "ok"}, and the send path raised
    ValueError("personalization returned an empty body") - so no email ever
    reached the Gmail mock and every send-related assertion saw zero sends.
    """
    lowered = combined.lower()
    return "personalization engine" in lowered or (
        '"subject"' in lowered and '"body"' in lowered
    )


def _combined_text(request_body: dict) -> str:
    messages = request_body.get("messages", [])
    full_text = " ".join(
        (m.get("content", "") if isinstance(m.get("content"), str)
         else " ".join(c.get("text", "") for c in m.get("content", []) if isinstance(c, dict)))
        for m in messages
    )
    return f"{_system_of(request_body)} {full_text}"


def anthropic_handler(request: Request) -> Response:
    """Transport-layer handler for all Anthropic API calls."""
    try:
        body = json.loads(request.content)
    except Exception:
        body = {}

    system = _system_of(body)
    combined = _combined_text(body)
    text_content = _build_content_text(system, combined, _user_text(body))

    response_body = {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-4-6",
        "content": [{"type": "text", "text": text_content}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }
    return Response(200, json=response_body)


def register(router: respx.MockRouter) -> None:
    """Register Anthropic routes on the given respx router."""
    router.post("https://api.anthropic.com/v1/messages").mock(side_effect=anthropic_handler)

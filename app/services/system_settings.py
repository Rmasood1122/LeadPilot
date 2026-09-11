"""Admin-controlled, deployment-wide feature settings (the `system_settings` table).

WHY A TABLE AND NOT MORE ENVIRONMENT VARIABLES
Every knob added by the feature expansion -- "is the consensus engine on",
"how many LinkedIn connection requests per account per day", "how many idle
days before a strategy mutates" -- is something an operator needs to change
while the product is running, usually because it is costing money or annoying
someone. An env var needs a redeploy (and on Render's free plan, a cold
start). A row needs a click in /admin/settings.

THE DEFAULTS BELOW ARE THE CONTRACT
A key with no row returns its default, so a fresh database behaves correctly
with an empty table, and `set()` refuses a value whose type does not match
the default's -- the admin UI sends JSON, and "20" stored where 20 was
expected is how a daily cap comparison silently becomes a string comparison.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

# key -> (default, one-line description shown in the admin panel)
DEFAULTS: dict[str, tuple[Any, str]] = {
    # Feature Group 7 -- meeting preparation
    "meeting_prep_enabled": (True, "Generate a meeting prep brief whenever a "
                             "meeting is booked."),
    "meeting_reminder_24h_enabled": (True, "Send the day-before meeting "
                                     "reminder (push + Slack)."),
    "meeting_reminder_1h_enabled": (True, "Send the one-hour reminder carrying "
                                    "the opening-60-seconds script."),
    # Feature Group 1 -- AI intelligence
    "consensus_enabled": (False, "Run strategy generation through Claude AND "
                          "GPT-4o and flag disagreements. Needs an OpenAI "
                          "key under Integrations."),
    "consensus_openai_model": ("gpt-4o", "OpenAI model used by the consensus "
                               "engine."),
    "competitor_intel_enabled": (True, "Pull live news + Apollo signals for "
                                 "the ICP before pipeline Phase 1."),
    "lead_scoring_enabled": (True, "Score every sourced lead's "
                             "ai_booking_likelihood with Claude."),
    "strategy_mutation_enabled": (True, "Mutate a campaign's strategy after "
                                  "N idle days with zero replies."),
    "strategy_mutation_idle_days": (7, "Days a campaign must run with zero "
                                    "replies before it mutates."),
    # Feature Group 2 -- personalization
    "linkedin_personalization_enabled": (True, "Fetch each lead's recent "
                                         "LinkedIn posts before writing "
                                         "their outreach."),
    "company_news_enabled": (True, "Inject last-30-day company news into "
                             "outreach hooks."),
    "loom_score_threshold": (75, "ai_booking_likelihood above which step 2 "
                             "gets a personalised Loom CTA."),
    # Feature Group 3 -- analytics
    "send_time_min_opens": (50, "Opens a campaign needs before smart "
                            "send-time windows are computed."),
    "objection_spike_threshold": (0.20, "Week-over-week objection-rate "
                                  "increase (0.20 = 20%) that alerts the "
                                  "user."),
    "objection_spike_min_replies": (10, "Human replies BOTH weeks need before "
                                    "an objection spike can alert (below "
                                    "this, one reply swings the rate)."),
    "open_tracking_enabled": (True, "Add a 1x1 open-tracking pixel to outreach "
                              "email. Never added for EU/EEA/UK leads "
                              "(ePrivacy: tracking pixels need consent)."),
    "open_prefetch_seconds": (60, "Pixel loads this soon after sending are "
                              "ignored -- mail security scanners fetch images "
                              "on delivery, before any human reads."),
    "send_time_max_delay_hours": (72, "Longest smart send time may hold a "
                                  "step to reach a top engagement window."),
    "claude_input_cost_per_mtok": (3.0, "USD per million Claude input tokens "
                                   "(estimate used for cost per meeting)."),
    "claude_output_cost_per_mtok": (15.0, "USD per million Claude output "
                                    "tokens."),
    "openai_input_cost_per_mtok": (2.5, "USD per million OpenAI input tokens "
                                   "(consensus engine)."),
    "openai_output_cost_per_mtok": (10.0, "USD per million OpenAI output "
                                    "tokens."),
    "voice_cost_per_minute": (0.15, "USD per AI-call minute, all-in "
                              "(Vapi/ElevenLabs + telephony)."),
    # Feature Group 5 -- LinkedIn
    "linkedin_daily_connection_limit": (20, "Connection requests per LinkedIn "
                                        "account per day."),
    "linkedin_daily_message_limit": (50, "LinkedIn messages (incl. InMail) "
                                     "per account per day."),
    # Feature Group 6 -- calling
    "phone_calling_enabled": (False, "Allow the AI phone channel. Calls cost "
                              "real money per minute, and AI-voice calls are "
                              "regulated (US TCPA). LeadPilot does NOT check "
                              "national Do-Not-Call registries -- do that "
                              "before enabling."),
    "phone_require_consent": (True, "Only AI-call leads with recorded phone "
                              "consent. Turning this off is a legal decision "
                              "for your jurisdiction, not a product one."),
    "phone_daily_call_limit": (40, "AI calls per account per day."),
    # Feature Group 9 -- deliverability & safety
    "deliverability_health_threshold": (70, "Email health score below which "
                                        "a campaign launch is warned."),
    "blacklist_monitoring_enabled": (True, "Daily sending-domain blacklist "
                                     "check; auto-pauses campaigns on a "
                                     "hit."),
    "reply_fraud_detection_enabled": (True, "Second-pass check that drops "
                                      "automated replies (OOO, bots, spam "
                                      "traps) from engagement metrics."),
    # Feature Group 8 -- white label
    "white_label_allowed": (True, "Allow workspace owners to enable "
                            "white-label mode."),
}


class SettingTypeError(ValueError):
    pass


def _coerce(key: str, value: Any) -> Any:
    default, _ = DEFAULTS[key]
    # bool is a subclass of int: check it first, or True would validate as an
    # int setting and False as a float.
    if isinstance(default, bool):
        if not isinstance(value, bool):
            raise SettingTypeError(f"{key} must be true or false")
        return value
    if isinstance(default, int):
        if isinstance(value, bool) or not isinstance(value, int):
            raise SettingTypeError(f"{key} must be a whole number")
        if value < 0:
            raise SettingTypeError(f"{key} must not be negative")
        return value
    if isinstance(default, float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SettingTypeError(f"{key} must be a number")
        return float(value)
    if isinstance(default, str):
        if not isinstance(value, str) or not value.strip():
            raise SettingTypeError(f"{key} must be a non-empty string")
        return value.strip()[:200]
    return value


def get(db: Session, key: str) -> Any:
    """The stored value, or the default. Unknown keys raise KeyError."""
    from app.db.models import SystemSetting  # noqa: PLC0415

    if key not in DEFAULTS:
        raise KeyError(f"unknown system setting {key!r}")
    row = db.execute(
        select(SystemSetting).where(SystemSetting.key == key)
    ).scalar_one_or_none()
    if row is None:
        return DEFAULTS[key][0]
    try:
        return _coerce(key, (row.value_json or {}).get("v"))
    except SettingTypeError:
        # A row written by something other than set() (a psql session, a
        # migration) with the wrong type must not take a feature down.
        return DEFAULTS[key][0]


def set(db: Session, key: str, value: Any, *, actor_user_id=None) -> Any:  # noqa: A001
    from app.db.models import SystemSetting  # noqa: PLC0415

    if key not in DEFAULTS:
        raise KeyError(f"unknown system setting {key!r}")
    value = _coerce(key, value)
    row = db.execute(
        select(SystemSetting).where(SystemSetting.key == key)
    ).scalar_one_or_none()
    if row is None:
        row = SystemSetting(key=key)
        db.add(row)
    row.value_json = {"v": value}
    row.updated_by_user_id = actor_user_id
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    return value


def all_settings(db: Session) -> list[dict]:
    from app.db.models import SystemSetting  # noqa: PLC0415

    stored = {r.key: r for r in db.execute(select(SystemSetting)).scalars()}
    out = []
    for key, (default, description) in DEFAULTS.items():
        row = stored.get(key)
        out.append({
            "key": key,
            "value": get(db, key),
            "default": default,
            "type": type(default).__name__,
            "description": description,
            "is_default": row is None,
            "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
        })
    return out

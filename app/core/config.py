"""
Application settings — M8 Chunk 4+5 additions.

Adds to the M8-C3 base:
  PLAYBOOK_SCORE_HALF_LIFE_DAYS  — score decay half-life (default 90)
  MV_MAX_VARIANTS                — max variants in multi-variate test (default 5)
  RATE_LIMIT_STRATEGIES          — POST /strategies per hour per user (default 2)
  RATE_LIMIT_LEADS_SOURCE        — POST /leads/source per hour per user (default 5)
  RATE_LIMIT_PLAYBOOK_RECOMPUTE  — POST /playbook/recompute per hour admin (default 3)
  RATE_LIMIT_WA_TEMPLATES        — POST /whatsapp/templates per hour per user (default 20)
  RATE_LIMIT_GET                 — GET endpoints per minute per user (default 300)
  RATE_LIMIT_AUTH                — POST /auth/* per 15-min window (default 10)
  RATE_LIMIT_SUPPORT_CHAT        — POST /support/chat per DAY per user (default 20)
  RATE_LIMIT_CRM_WRITE           — CRM writes per hour per user (default 600)
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ---------------------------------------------------------------------------
    # Core application
    # ---------------------------------------------------------------------------
    APP_ENV: str = "development"
    # Empty, NOT "change-me-in-production". Nothing reads this field — the real
    # JWT signing key is app/config.py::jwt_secret (aliased to the same
    # SECRET_KEY env var), which app/services/auth.py uses. A hardcoded,
    # publicly-known default sitting on an unused-but-importable Settings field
    # is a trap: the first code that reaches for `settings.SECRET_KEY` would
    # silently sign tokens with a value published in this repository. Empty
    # fails loudly instead, and app/core/production_guard.py rejects an unset
    # or placeholder SECRET_KEY at startup in production.
    SECRET_KEY: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    LOG_LEVEL: str = "INFO"
    ADMIN_EMAIL: Optional[str] = None

    # ---------------------------------------------------------------------------
    # Database
    # ---------------------------------------------------------------------------
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/clienthunter"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # ---------------------------------------------------------------------------
    # Redis
    # ---------------------------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"

    # ---------------------------------------------------------------------------
    # Celery
    # ---------------------------------------------------------------------------
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    CELERY_ALWAYS_EAGER: bool = False
    CELERY_EAGER_PROPAGATES: bool = False
    CELERY_CONCURRENCY: int = 4

    # ---------------------------------------------------------------------------
    # Anthropic
    # ---------------------------------------------------------------------------
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    ANTHROPIC_MAX_TOKENS: int = 4096

    # ---------------------------------------------------------------------------
    # Integration API keys
    # ---------------------------------------------------------------------------
    APOLLO_API_KEY: str = ""
    HUNTER_API_KEY: str = ""

    # ---------------------------------------------------------------------------
    # Gmail OAuth
    # ---------------------------------------------------------------------------
    GMAIL_CLIENT_ID: str = ""
    GMAIL_CLIENT_SECRET: str = ""
    GMAIL_REDIRECT_URI: str = "http://localhost:8000/integrations/gmail/callback"
    """Must match a redirect URI registered in Google Cloud Console.

    NOT /api/v1/... — app/main.py mounts every router UNPREFIXED, so the
    real path is /integrations/gmail/callback. The /api/v1 form pointed at
    a route that has never existed (verified: 0 of 78 mounted paths start
    with /api/v1), which meant Google would redirect the user to a 404 and
    the OAuth flow could never complete."""

    # ---------------------------------------------------------------------------
    # WhatsApp
    # ---------------------------------------------------------------------------
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_WABA_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_APP_SECRET: str = ""

    # ---------------------------------------------------------------------------
    # Calendly
    # ---------------------------------------------------------------------------
    CALENDLY_CLIENT_ID: str = ""
    CALENDLY_CLIENT_SECRET: str = ""
    CALENDLY_WEBHOOK_SECRET: str = ""

    # ---------------------------------------------------------------------------
    # Firebase
    # ---------------------------------------------------------------------------
    FIREBASE_PROJECT_ID: str = ""
    FIREBASE_CREDENTIALS_JSON: str = "{}"

    # ---------------------------------------------------------------------------
    # Encryption (M8-C3)
    # ---------------------------------------------------------------------------
    ENCRYPTION_KEY: str = ""
    ENCRYPTION_KEY_PREVIOUS: Optional[str] = None

    # ---------------------------------------------------------------------------
    # Circuit breaker (M8-C3)
    # ---------------------------------------------------------------------------
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = 60

    # ---------------------------------------------------------------------------
    # Pipeline monitoring (M8-C3)
    # ---------------------------------------------------------------------------
    PIPELINE_STEP_TIMEOUT_MINUTES: int = 10

    # ---------------------------------------------------------------------------
    # Learning loop (M8-C1+C2)
    # ---------------------------------------------------------------------------
    PLAYBOOK_MIN_SAMPLE: int = 30
    AB_MIN_LIFT: float = 0.10
    AB_SIGNIFICANCE_THRESHOLD: float = 0.05
    # Max harm-metric rate (bounces + spam + opt-outs per send) the winning
    # variant may carry before auto-promotion is blocked -- ab_testing.py
    # gate 4. Undeclared until now, so extra="ignore" dropped the env var
    # and getattr() always fell through to its hardcoded 0.05 default:
    # AB_HARM_CEILING in .env has never had any effect.
    AB_HARM_CEILING: float = 0.05
    PLAYBOOK_AGGREGATION_UTC_HOUR: int = 2  # 02:00 UTC / 07:00 PKT

    # ---------------------------------------------------------------------------
    # Score decay (M8-C4)
    # ---------------------------------------------------------------------------
    PLAYBOOK_SCORE_HALF_LIFE_DAYS: int = 90
    """
    Half-life for exponential score decay.
    A score from PLAYBOOK_SCORE_HALF_LIFE_DAYS ago counts half as much as today.
    Default: 90 days. Lower = faster forgetting; higher = more weight on history.
    """

    # ---------------------------------------------------------------------------
    # Multi-variate testing (M8-C4)
    # ---------------------------------------------------------------------------
    MV_MAX_VARIANTS: int = 5
    """Maximum number of variants in a multi-variate test. Default: 5."""

    # ---------------------------------------------------------------------------
    # Rate limiting (M8-C5)
    # ---------------------------------------------------------------------------
    RATE_LIMIT_STRATEGIES: int = 2
    """Max POST /products/*/strategies calls per user per hour. Default: 2.

    RAISE THIS ONCE REAL USAGE IS KNOWN — it is deliberately conservative for
    launch, and this docstring plus .env.production.example are the two places
    to change.

    Lowered from 10 on 2026-08-20. Two reasons, both measured rather than
    guessed:

    1. The limit scale in this class is ordered by cost — wa_templates (one
       Claude call) 20/hr, leads_source (paid external API) 5/hr,
       playbook_recompute (heavy DB aggregation, admin-only) 3/hr. Strategy
       generation is a 72- or 144-step pipeline plus 10 verification passes:
       the 2026-08-19 Phase C run measured ~150 Claude calls for ONE strategy,
       and up to ~180 when passes retry. At 10/hr it was the MOST permissive
       limit in the system while being by far the most expensive operation —
       the scale was inverted.
    2. Throughput makes a high limit meaningless anyway. That same run took
       ~62 minutes of pipeline time (144 steps at ~26s) plus ~10 minutes of
       verification. One strategy occupies a pipeline worker for over an hour,
       so allowing 10 per hour per user only builds a multi-hour queue.

    2 (not 1) so a user who misconfigures a product can immediately retry
    without a support ticket, while capping worst-case spend at two full
    pipelines per user per hour.
    """

    RATE_LIMIT_LEADS_SOURCE: int = 5
    """Max POST /strategies/*/leads/source calls per user per hour. Default: 5."""

    RATE_LIMIT_PLAYBOOK_RECOMPUTE: int = 3
    """Max POST /playbook/recompute calls per admin per hour. Default: 3."""

    RATE_LIMIT_WA_TEMPLATES: int = 20
    """Max POST /whatsapp/templates/generate calls per user per hour. Default: 20."""

    RATE_LIMIT_PUBLIC_BOOKING: int = 30
    """Max public booking-page writes per IP per hour (Engagement Hub).

    Scoped to the IP, not a user, because there is no user: POST
    /calendar/booking-pages/{slug}/book is the one write in this API that an
    unauthenticated stranger can make. Without a limit, a booking page is a
    free way to fill a founder's calendar with junk and their inbox with
    confirmation emails sent from OUR domain -- a deliverability problem as
    much as a nuisance.

    30/hour is loose for a human (who books once) and tight for a script. The
    slots endpoint is NOT limited by this: it is a read, it is what the page
    calls on every date click, and limiting it would break the booking flow
    for a person who is simply browsing dates.

    NOTE: read from app/core/config.py, not app/config.py.
    """

    RATE_LIMIT_CALENDAR_WRITE: int = 300
    """Max authenticated calendar/meeting writes per user per hour.

    Sized like RATE_LIMIT_CRM_WRITE and for the same reason -- these are rows
    in PostgreSQL, not external spend -- but half of it, because the traffic
    is a person editing availability and typing meeting notes rather than
    working through a grid of five thousand leads. The meeting-notes autosave
    fires at most once every 10 seconds per open meeting, which is 360/hour
    for somebody in back-to-back calls all day; the two ceilings that matter
    are set above that.

    NOTE: read from app/core/config.py, not app/config.py.
    """

    RATE_LIMIT_PUBLIC_VIDEO: int = 120
    # Feature Group 3: loads of ONE open pixel per hour (keyed by token, not
    # IP -- Gmail proxies every recipient's images through shared IPs).
    RATE_LIMIT_OPEN_PIXEL: int = 30
    """Max GET /public/video per client IP per hour (Feature Group 2). The
    endpoint is unauthenticated -- a prospect opens it from an email -- and
    returns only a first name, a company and a Loom embed id, behind an
    encrypted token; the limit stops it being used to brute-force tokens.

    NOTE: read from app/core/config.py, not app/config.py.
    """

    RATE_LIMIT_AI_ACTION: int = 60
    """Max user-triggered AI generations per user per hour (feature expansion):
    regenerating a meeting prep brief, logging a meeting outcome (which drafts
    a follow-up), rescoring a lead, extracting a style profile. Each is one
    Claude call billed to the deployment's key, so this is a spend ceiling
    like RATE_LIMIT_SUPPORT_CHAT, sized for a busy day of calls rather than
    for a script.

    NOTE: read from app/core/config.py, not app/config.py.
    """

    RATE_LIMIT_CRM_WRITE: int = 600
    """Max CRM write calls per user per hour (M9). Default: 600.

    Deliberately the LOOSEST limit in this class, because it is the only one
    whose governed operation costs nothing external. Every other RATE_LIMIT_*
    here is a spend ceiling -- strategies burn ~150 Claude calls, leads_source
    spends Apollo and Hunter credits, support_chat spends the Anthropic key.
    A CRM write is one row in PostgreSQL.

    600/hour is 10 per minute sustained. The traffic shape this governs is
    inline cell editing in the data grid: a user working a list of leads
    types a value, tabs to the next cell, types again. A burst of twenty
    edits in a minute is somebody doing their job, not abuse, and a limit
    tight enough to catch abuse here would mostly catch that user instead --
    with a 429 in the middle of a row they were halfway through editing.

    What it does still bound: a runaway client loop, and a script pointed at
    the bulk endpoint. Note that ONE bulk call may touch up to 500 leads and
    costs ONE slot -- the limit counts requests, not rows, so the honest
    high-volume path (select many, act once) is the cheap one and the abusive
    path (500 individual PATCHes) is the expensive one. That is the right way
    round.

    Raise it if a legitimate user reports a 429 while editing; it is a single
    env var, and nothing about it protects a paid resource.
    """

    RATE_LIMIT_GET: int = 300
    """Max GET endpoint calls per user per minute. Default: 300."""

    RATE_LIMIT_AUTH: int = 10
    # Feature 3: AI support chat messages per user per DAY. Every message
    # spends the account's Anthropic key, so this is a cost ceiling as much as
    # an abuse control. Window is 86400s, set at the call site.
    #
    # 20, lowered from 30 on 2026-08-30 at the product owner's instruction.
    # The case for 30 was that a user troubleshooting a real problem sends
    # 15-20 messages in one sitting, and cutting them off mid-thread pushes
    # them into a support ticket -- the outcome the chat exists to avoid. At 20
    # that user is now cut off right at the edge of a normal session, so expect
    # some tickets that a higher cap would have absorbed. The ceiling was
    # chosen over that risk deliberately; raise this value if ticket volume
    # from exhausted sessions shows up.
    #
    # The cap is enforced identically in mock mode, where a message costs
    # nothing. That is on purpose: a user must not build a habit against a
    # limit that tightens the day a real key is added.
    RATE_LIMIT_SUPPORT_CHAT: int = 20
    """Max login/signup attempts per 15-minute window. Default: 10.

    Wired 2026-08-20 (it had been inert since M8-C5: defined, documented, and
    referenced by zero routes, so login and signup accepted unlimited
    credential guesses). Applied in app/api/auth.py to TWO independent keys,
    both governed by this one number:

      per IP       "ip:<addr>"    — one host brute-forcing passwords
      per account  "acct:<email>" — credential stuffing spread across many
                                    IPs at a single account, which a per-IP
                                    limit alone does nothing about

    Why 10, security-based rather than cost-based:

    * A legitimate user needs 1-3 attempts. Mistyping a password four times
      in 15 minutes already means going to a reset, not a fifth guess, so 10
      leaves ~3x headroom over the worst realistic honest case.
    * An attacker gets 10 guesses per 15 minutes = 960/day per key. Against
      even a weak six-character lowercase password (~3.1e8 combinations) that
      is on the order of a million years. The point is not to make guessing
      hard, it is to make ONLINE guessing useless, and any limit in this range
      does that; 10 buys it without inconveniencing real users.
    * The window is 15 minutes, not an hour, so a locked-out honest user waits
      minutes rather than most of an hour. See AUTH_WINDOW_SECONDS in
      app/core/rate_limiting.py.

    KNOWN TRADE-OFF: attempts are counted whether they succeed or fail, so an
    office behind one NAT IP shares the per-IP bucket — 11 people logging in
    inside the same 15 minutes would see a 429 with Retry-After. Real logins
    are roughly once or twice a day (clients hold a refresh token rather than
    re-authenticating), so this is unlikely but not impossible. If a customer
    reports it, RAISE THIS VALUE — it is a single env var. The alternative,
    counting only failed attempts, needs a check-then-conditionally-record
    split the limiter does not have and would mean two divergent mechanisms.

    /auth/refresh is deliberately NOT limited: legitimate clients hit it every
    time a 15-minute access token expires, and a signed refresh token is not
    brute-forceable.
    """

    # ---------------------------------------------------------------------------
    # Sending limits (M8-C3)
    # ---------------------------------------------------------------------------
    GMAIL_DAILY_SEND_CAP: int = 500
    GMAIL_BOUNCE_PAUSE_THRESHOLD: float = 0.03
    GMAIL_WARMUP_START_DAILY: int = 20

    # ---------------------------------------------------------------------------
    # Frontend / CORS
    # ---------------------------------------------------------------------------
    FRONTEND_URL: str = "http://localhost:3000"
    # CORS_ORIGINS has TWO readers that disagreed on format, and each format
    # broke the other:
    #   * app/main.py (the one that actually configures CORSMiddleware) does
    #     os.getenv("CORS_ORIGINS").split(",")  -> wants comma-separated
    #   * this field, typed list[str], made pydantic-settings JSON-decode it
    #     -> wanted ["https://a.com","https://b.com"]
    # A JSON value satisfied pydantic but produced origins like '["https://a.com"'
    # in main.py, which never match a browser Origin: the API returns 200, every
    # healthcheck passes, and only the browser sees a CORS error. A plain CSV
    # value fixed main.py but made this field raise SettingsError at import.
    # Comma-separated is now the single canonical format.
    #
    # Typed `str`, NOT `list[str]`, on purpose: for complex types
    # pydantic-settings json.loads() the value inside the env/dotenv SOURCE,
    # before any field_validator can normalise it, so a comma-separated value
    # raised SettingsError at import no matter what validator was attached.
    # Keeping it a plain string means the source never decodes it; use
    # `cors_origins_list` for the parsed form. app/main.py remains the
    # authoritative reader that configures CORSMiddleware.
    CORS_ORIGINS: str = "http://localhost:3000"

    # ---------------------------------------------------------------------------
    # Android
    # ---------------------------------------------------------------------------
    ANDROID_PACKAGE_NAME: str = "io.clienthunter.app"

    # ---------------------------------------------------------------------------
    # Computed helpers
    # ---------------------------------------------------------------------------

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_testing(self) -> bool:
        return self.APP_ENV == "testing" or os.getenv("TESTING") == "1"

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS_ORIGINS parsed the same way app/main.py parses it.

        Tolerates the legacy JSON-array form so an old .env does not silently
        yield origins with brackets baked into them.
        """
        raw = (self.CORS_ORIGINS or "").strip()
        if not raw:
            return []
        if raw.startswith("["):
            import json

            try:
                return [str(o).strip() for o in json.loads(raw)]
            except (ValueError, TypeError):
                return []
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def validate_encryption_key(cls, v: str) -> str:
        if not v and os.getenv("TESTING") != "1" and os.getenv("APP_ENV") != "testing":
            import warnings
            warnings.warn(
                "ENCRYPTION_KEY is not set — integration tokens will NOT be encrypted at rest.",
                stacklevel=2,
            )
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

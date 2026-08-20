"""Central application configuration.

Every value comes from environment variables (or a local .env file in
development). Nothing secret is ever hard-coded. See `.env.example` at the
repo root for documentation of every variable.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App -----------------------------------------------------------
    app_name: str = "LeadPilot"
    app_env: str = "development"  # development | production | test
    # DEDICATED flag for app/api/debug.py. Deliberately separate from app_env,
    # is_test and log_level so that no unrelated configuration change can turn
    # the test-only debug router on as a side effect. Defaults False; it is set
    # nowhere in .env.production.example, docker-compose.prod.yml or the
    # Dockerfile, and app/main.py additionally refuses to mount the router when
    # app_env is production. Never set this true in a deployed environment.
    enable_debug_routes: bool = False
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    # --- Database ------------------------------------------------------
    database_url: str = "postgresql+psycopg2://leadpilot:leadpilot@localhost:5432/leadpilot"

    # --- Redis / Celery --------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None   # defaults to redis_url if unset
    celery_result_backend: str | None = None  # defaults to redis_url if unset

    # --- Anthropic (the ONLY external API used in Milestone 1) ----------
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_max_tokens: int = 4096
    # Retry behaviour for transient API errors inside pipeline steps
    anthropic_max_retries: int = 3

    # --- External API plumbing (M2+: Apollo, Hunter, ...) ----------------
    external_max_retries: int = 3
    external_backoff_base_seconds: float = 2.0
    circuit_failure_threshold: int = 5
    circuit_cooldown_seconds: int = 300
    cache_ttl_search_seconds: int = 86400        # 1 day
    cache_ttl_enrichment_seconds: int = 2592000  # 30 days — never pay twice

    # --- Lead sourcing providers (M2) ------------------------------------
    apollo_api_key: str = ""
    hunter_api_key: str = ""
    lead_source_provider: str = "apollo"
    email_verifier_provider: str = "hunter"
    leads_max_per_run: int = 200
    apollo_page_size: int = 25  # per_page for paginated search

    # --- Gmail OAuth (M3) --------------------------------------------------
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/integrations/gmail/callback"
    # NOTE: OAuth-token encryption goes through app/core/crypto.py, which
    # also reads this same ENCRYPTION_KEY var. Aliased here (rather than to
    # the old TOKEN_ENCRYPTION_KEY name) so both config modules always agree
    # on one key — this field itself is not read anywhere, it's kept only
    # for backward-compat callers.
    token_encryption_key: str = Field(default="", alias="ENCRYPTION_KEY")
    # Refresh the access token when it expires within this many seconds.
    gmail_token_refresh_leeway_seconds: int = 120

    # --- Outreach compliance & sending (M3) --------------------------------
    public_base_url: str = "http://localhost:8000"  # used in unsubscribe links
    sender_identity: str = "LeadPilot User, 123 Main St, City, Country"  # CAN-SPAM footer identity
    gmail_daily_cap: int = 100
    gmail_warmup_start_sends: int = 10
    gmail_warmup_daily_increment: int = 10
    send_window_start_hour: int = 9
    send_window_end_hour: int = 17
    send_window_timezone: str = "UTC"   # fallback when a lead has no timezone
    send_window_skip_weekends: bool = True
    bounce_rate_pause_threshold: float = 0.03
    bounce_min_sends: int = 10          # don't judge bounce rate on tiny samples
    reply_poll_interval_seconds: int = 300
    dispatch_interval_seconds: int = 60
    ooo_reschedule_days: int = 7        # out-of-office: pause + retry after N days

    # --- Calendly (M3) -------------------------------------------------------
    calendly_api_token: str = ""
    # Aliased to CALENDLY_WEBHOOK_SECRET — the single env var name used by
    # both config modules and documented in .env.example. (Previously this
    # field looked for a different name, CALENDLY_WEBHOOK_SIGNING_KEY, which
    # silently left it empty and made every Calendly webhook 401.)
    calendly_webhook_signing_key: str = Field(default="", alias="CALENDLY_WEBHOOK_SECRET")

    # --- WhatsApp Business Cloud API (M4) -------------------------------------
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    # Token YOU invent and paste into Meta's webhook config (GET handshake).
    # Aliased to WHATSAPP_VERIFY_TOKEN — the single env var name used by both
    # config modules and documented in .env.example. (Previously this field
    # looked for WHATSAPP_WEBHOOK_VERIFY_TOKEN, which silently left it empty
    # and made Meta's webhook verification handshake always fail. The field was
    # fixed then, but docker-compose.yml, `clienthunter serve`'s .env template,
    # docs/DEPLOY.md and tests/conftest.py all kept SETTING the dead name, so
    # the handshake still failed everywhere except a hand-written .env. Those
    # are fixed too -- if you add a new setter, use WHATSAPP_VERIFY_TOKEN.)
    whatsapp_webhook_verify_token: str = Field(default="", alias="WHATSAPP_VERIFY_TOKEN")
    # Meta App secret — used to validate X-Hub-Signature-256 on deliveries.
    whatsapp_app_secret: str = ""
    # TODO: verify against current WhatsApp Cloud API docs (latest version)
    whatsapp_api_version: str = "v20.0"
    # TODO: verify against current WhatsApp docs (body component limit)
    whatsapp_template_body_max_chars: int = 1024
    # Per-channel daily cap + warm-up (M4 Chunk 3). Deferred, never dropped.
    whatsapp_daily_cap: int = 100
    whatsapp_warmup_start_sends: int = 10
    whatsapp_warmup_daily_increment: int = 10

    # --- Auth (M5) ---------------------------------------------------------
    # Aliased to SECRET_KEY — the single env var name used by both config
    # modules and documented in .env.example. (Previously this field looked
    # for JWT_SECRET, which was never set, so every server restart silently
    # generated a fresh random secret and logged every user out.)
    jwt_secret: str = Field(default="", alias="SECRET_KEY")  # REQUIRED in production
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 1209600  # 14 days
    # Where theme background images are stored + served from.
    media_dir: str = "media"

    # --- Pipeline engine -------------------------------------------------
    pipeline_step_timeout_seconds: int = 300
    # Verification loop: max fix→re-run attempts per pass before the
    # strategy is marked needs_human_review (project knowledge, section D).
    verification_max_retries_per_pass: int = 3
    # Output ceiling for the verification FIXER, which is asked to emit the
    # complete revised strategy document.
    #
    # Was hardcoded at 8000 against a document measured at ~8,234 tokens, so the
    # rewrite could not physically fit: 7 of 8 fixer calls in the 2026-08-19 run
    # returned exactly out_tokens=8000 and each truncated result was written
    # over strategy_document.
    #
    # 18,432 = ~2.2x the largest real document observed (8,234 tokens), and
    # deliberately just under the SDK's non-streaming cut-off. The SDK refuses a
    # non-streaming request whose max_tokens implies >10 minutes of generation
    # (measured: 21,333 accepted, 32,000 refused), and 32,000 made every
    # run_pipeline call crash-retry until the integration suite caught it.
    #
    # This is one of three layers, not a lone guess: if a document ever outgrows
    # this, _generate_fix retries once at double (which streams, since it is
    # past the cut-off), and if THAT truncates the loop refuses to persist the
    # partial text. The model's own cap is 128,000, confirmed live via the
    # Models API, so there is room to raise this — but raising it past ~20,000
    # means the primary call streams, and the integration mock does not speak
    # SSE yet.
    verification_fixer_max_tokens: int = 18_432

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — import this everywhere, never Settings()."""
    return Settings()


settings = get_settings()
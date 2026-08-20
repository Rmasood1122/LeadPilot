"""
ClientHunter Enterprise — FastAPI application entry point.
Combined build: all milestones M1–M8 wired.

M1–M4  core API, pipeline, verification, Gmail, WhatsApp
M5     web UI support (themes, analytics, ui-support)
M6     GET /strategies (CLI list endpoint — sdk/backend_additions)
M7     Capacitor CORS origins + /devices router (FCM tokens)
M8     admin, playbook, onboarding, webhook targets, rich health,
       request-ID logging, global error handler
"""

import logging
from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings

# M1–M5 routers (module-level absolute paths, no prefixes)
from app.api.auth import router as auth_router
from app.api.analytics import router as analytics_router
from app.api.ui_support import router as ui_support_router
from app.api.integrations import router as integrations_router
from app.api.sequences import router as sequences_router
from app.api.unsubscribe import router as unsubscribe_router
from app.api.webhooks import router as webhooks_router                    # Calendly inbound (M3)
from app.api.webhooks_whatsapp import router as whatsapp_webhooks_router  # WhatsApp inbound (M4)
from app.api.whatsapp_templates import router as whatsapp_templates_router
from app.api.whatsapp_optin import router as whatsapp_optin_router
from app.api.leads import router as leads_router
from app.api.products import router as products_router
from app.api.strategies import router as strategies_router

# M7
from app.api.devices import router as devices_router

# M8 (prefixed routers)
from app.api.health import router as health_router
from app.api.admin import router as admin_router
from app.api.playbook import router as playbook_router
from app.api.onboarding import router as onboarding_router
from app.api.webhook_targets import router as webhook_targets_router
from app.api.strategies_advanced import router as strategies_advanced_router
from app.api.strategies_advanced import plans_router

from app.core.errors import global_exception_handler
from app.core.logging import RequestIDMiddleware

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Application startup/shutdown.

    `@app.on_event("startup")` is deprecated on FastAPI 0.111, so new startup
    work goes here.

    ADMIN_EMAIL bootstrap: without it a freshly deployed database has no admin
    at all and no way to make one over HTTP (signup cannot self-promote, by
    design), so every /admin route and /playbook/aggregate is unreachable.
    Idempotent, never downgrades another admin, and never blocks startup — see
    app/core/admin_bootstrap.py for why it promotes but does not create.
    """
    from app.core.admin_bootstrap import bootstrap_admin
    from app.core.production_guard import validate_production_config

    # BEFORE anything else: refuse to serve traffic from a production process
    # whose SECRET_KEY / ENCRYPTION_KEY / CORS_ORIGINS are unset or unsafe.
    # Each of those fails quietly rather than crashing — see production_guard.
    # No-op outside APP_ENV=production/prod/live.
    validate_production_config()

    bootstrap_admin()
    yield


app = FastAPI(
    lifespan=_lifespan,
    title="ClientHunter Enterprise API",
    version="1.0.0",
    description=(
        "End-to-end client acquisition: strategy → research → outreach → booked "
        "meeting. Runs 24/7 in the cloud — clients (web, mobile, CLI) are windows "
        "into it, not the engine."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ── Middleware ────────────────────────────────────────────────────────────────
# Request-ID first so every log line (including CORS rejections) carries one.
app.add_middleware(RequestIDMiddleware)

# CORS: env-configured web origins + Capacitor origins (M7).
_ENV_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]
_CAPACITOR_ORIGINS: list[str] = [
    "https://localhost",       # Capacitor Android (androidScheme: 'https')
    "capacitor://localhost",   # Capacitor fallback scheme
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=list({*_ENV_ORIGINS, *_CAPACITOR_ORIGINS}),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Request-ID"],
)

# ── Error handling (M8-C3): safe responses, full structured logs ─────────────
# The catch-all is registered for the LAST-RESORT case only. Registering the
# application's own exception types explicitly matters: a handler bound to bare
# `Exception` is served by Starlette's ServerErrorMiddleware, which re-raises
# after building the response, so a ComplianceError surfaced as an unhandled
# 500-path exception instead of the documented 422 under any ASGI transport
# that propagates app exceptions (httpx ASGITransport, TestClient). Bound by
# concrete type they go through ExceptionMiddleware and return a real response.
from app.core.exceptions import (  # noqa: E402
    ClientHunterError,
    ComplianceError,
    ForbiddenError,
    ResourceNotFoundError,
)

for _exc_type in (ComplianceError, ResourceNotFoundError, ForbiddenError,
                  ClientHunterError):
    app.add_exception_handler(_exc_type, global_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# ── Static media (theme background uploads) ───────────────────────────────────
_MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "media"))
_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(_MEDIA_DIR)), name="media")

# ── Routers ───────────────────────────────────────────────────────────────────
# M8 health router (prefix=/health) replaces the M1 inline /health endpoint.
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(analytics_router)
app.include_router(ui_support_router)
app.include_router(products_router)
app.include_router(strategies_router)            # M5 core strategy routes
app.include_router(strategies_advanced_router)   # M8-C4/C5 additions (/strategies/*)
app.include_router(plans_router)                 # GET /plans (public)
app.include_router(leads_router)
app.include_router(integrations_router)
app.include_router(sequences_router)
app.include_router(unsubscribe_router)
app.include_router(webhooks_router)              # POST /webhooks/calendly (M3)
app.include_router(whatsapp_webhooks_router)     # GET/POST /webhooks/whatsapp (M4)
app.include_router(webhook_targets_router)       # /webhooks/targets (M8-C5)
app.include_router(whatsapp_templates_router)
app.include_router(whatsapp_optin_router)
app.include_router(devices_router, prefix="/devices", tags=["devices"])  # M7
app.include_router(admin_router)                 # /admin/* (M8-C3)
app.include_router(playbook_router)              # /playbook/* (M8)
app.include_router(onboarding_router)            # /onboarding/* (M8-C5)


# ---------------------------------------------------------------------------
# Test-only debug router — NEVER mounted in a deployed environment.
# ---------------------------------------------------------------------------
# Gated on a DEDICATED flag (settings.enable_debug_routes, app/config.py) that
# controls nothing else, so no unrelated config change can enable it as a side
# effect — notably NOT app_env/is_test/log_level. The import lives INSIDE the
# conditional: when the flag is off, app.api.debug is never imported, so its
# routes cannot exist on this ASGI app under any code path. The extra app_env
# check is defence in depth for an operator who wrongly sets the flag in prod
# (app/api/debug.py also raises at import time in that case).
_debug_settings = get_settings()
if (
    _debug_settings.enable_debug_routes
    and (_debug_settings.app_env or "").strip().lower()
    not in {"production", "prod", "live"}
):
    from app.api.debug import router as debug_router

    app.include_router(debug_router)
    logging.getLogger(__name__).warning(
        "TEST-ONLY /debug routes are mounted (enable_debug_routes=True, "
        "app_env=%s). This must never happen in production.",
        _debug_settings.app_env,
    )


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {"name": "ClientHunter Enterprise API", "docs": "/docs", "health": "/health"}

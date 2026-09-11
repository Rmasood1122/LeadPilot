"""Tool integration endpoints — AegisAudit, PostIQ, SIGNALFORGE.

Admin endpoints (workspace-level, one instance per deployment):
  GET    /integrations/tools/aegisaudit          status + config
  PUT    /integrations/tools/aegisaudit          save config
  POST   /integrations/tools/aegisaudit/test     health check

  GET    /integrations/tools/signalforge         status + config (key masked)
  PUT    /integrations/tools/signalforge         save config
  POST   /integrations/tools/signalforge/test    reachability + key check
  DELETE /integrations/tools/signalforge         disconnect -> 204

Per-user endpoints (PostIQ is per-user because the Web App URL is personal):
  GET    /integrations/tools/postiq              status
  PUT    /integrations/tools/postiq              save webapp_url + token
  POST   /integrations/tools/postiq/test         reachability + token check
  DELETE /integrations/tools/postiq              disconnect -> 204
  GET    /integrations/tools/postiq/drafts       501 — PostIQ has no read API

Secrets (PostIQ token, SIGNALFORGE operator key) are write-only: no endpoint
returns them.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.db.base import get_db
from app.db.models import User
from app.integrations import aegisaudit, postiq, signalforge
from app.services import tool_integrations as svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations/tools", tags=["tool-integrations"])


# ══════════════════════════════════════════════════════════════
# AEGISAUDIT (admin-level)
# ══════════════════════════════════════════════════════════════

class AegisAuditConfigIn(BaseModel):
    host: str = Field(default="127.0.0.1", min_length=1, max_length=253,
                      pattern=r"^[A-Za-z0-9.\-]+$")
    port: str = Field(default="8787", pattern=r"^\d{1,5}$")
    default_mode: str = Field(default="deep", pattern="^(standard|deep|forensic|maximum)$")
    enabled: bool = True

    @field_validator("port")
    @classmethod
    def _port_range(cls, v: str) -> str:
        if not 1 <= int(v) <= 65535:
            raise ValueError("port must be 1-65535")
        return v


@router.get("/aegisaudit")
def aegisaudit_status(db: Session = Depends(get_db),
                      _admin: User = Depends(require_admin)) -> dict:
    cfg = svc.get_aegisaudit_config(db)
    return {
        "configured": True,
        "enabled": cfg["enabled"],
        "host": cfg["host"],
        "port": cfg["port"],
        "base_url": cfg["base_url"],
        "default_mode": cfg["default_mode"],
    }


@router.put("/aegisaudit")
def aegisaudit_save(body: AegisAuditConfigIn, db: Session = Depends(get_db),
                    _admin: User = Depends(require_admin)) -> dict:
    svc.save_aegisaudit_config(db, host=body.host, port=body.port,
                               default_mode=body.default_mode, enabled=body.enabled)
    return {"saved": True}


@router.post("/aegisaudit/test")
def aegisaudit_test(db: Session = Depends(get_db),
                    _admin: User = Depends(require_admin)) -> dict:
    cfg = svc.get_aegisaudit_config(db)
    if not aegisaudit.health_check(cfg["base_url"]):
        raise HTTPException(status_code=503,
                            detail=f"AegisAudit not reachable or degraded at {cfg['base_url']}")
    return {"connected": True, "base_url": cfg["base_url"]}


# ══════════════════════════════════════════════════════════════
# POSTIQ (per-user)
# ══════════════════════════════════════════════════════════════

class PostIQConfigIn(BaseModel):
    webapp_url: str = Field(min_length=10, max_length=500)
    token: str = Field(min_length=8, max_length=500)

    @field_validator("webapp_url")
    @classmethod
    def _apps_script_only(cls, v: str) -> str:
        return postiq.validate_webapp_url(v)


@router.get("/postiq")
def postiq_status(db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> dict:
    cfg = svc.get_postiq_config(db, current_user.id)
    if not cfg:
        return {"connected": False}
    return {"connected": True, "webapp_url": cfg["webapp_url"], "token_configured": True}


@router.put("/postiq")
def postiq_save(body: PostIQConfigIn, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)) -> dict:
    svc.save_postiq_config(db, current_user.id, webapp_url=body.webapp_url, token=body.token)
    return {"saved": True}


@router.post("/postiq/test")
def postiq_test(db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)) -> dict:
    cfg = svc.get_postiq_config(db, current_user.id)
    if not cfg:
        raise HTTPException(status_code=404, detail=(
            "PostIQ is not configured. Add your webapp URL and token first."))
    if not postiq.health_check(webapp_url=cfg["webapp_url"]):
        raise HTTPException(status_code=503, detail=(
            "PostIQ Web App is not reachable — check the URL and that it is deployed with "
            "access 'Anyone'."))
    try:
        postiq.verify_token(webapp_url=cfg["webapp_url"], token=cfg["token"])
    except postiq.PostIQError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"connected": True, "token_valid": True}


@router.delete("/postiq", status_code=204)
def postiq_disconnect(db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)) -> Response:
    svc.delete_postiq_config(db, current_user.id)
    return Response(status_code=204)


@router.get("/postiq/drafts")
def postiq_get_drafts(_user: User = Depends(get_current_user)) -> dict:
    raise HTTPException(status_code=501, detail=(
        "PostIQ has no API for reading generated drafts. It delivers them to you "
        "automatically on Telegram / WhatsApp."))


# ══════════════════════════════════════════════════════════════
# SIGNALFORGE (admin-level)
# ══════════════════════════════════════════════════════════════

class SignalForgeConfigIn(BaseModel):
    base_url: str = Field(default="http://127.0.0.1:8000", max_length=500)
    operator_key: str = Field(min_length=8, max_length=500)

    @field_validator("base_url")
    @classmethod
    def _http_url(cls, v: str) -> str:
        parsed = urlparse(v.strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("base_url must be an http(s) URL")
        return v.strip().rstrip("/")


@router.get("/signalforge")
def signalforge_status(db: Session = Depends(get_db),
                       _admin: User = Depends(require_admin)) -> dict:
    cfg = svc.get_signalforge_config(db)
    if not cfg:
        return {"configured": False}
    return {
        "configured": True,
        "base_url": cfg["base_url"],
        "key_preview": f"{cfg['operator_key'][:4]}••••",
    }


@router.put("/signalforge")
def signalforge_save(body: SignalForgeConfigIn, db: Session = Depends(get_db),
                     _admin: User = Depends(require_admin)) -> dict:
    svc.save_signalforge_config(db, base_url=body.base_url, operator_key=body.operator_key)
    return {"saved": True}


@router.post("/signalforge/test")
def signalforge_test(db: Session = Depends(get_db),
                     _admin: User = Depends(require_admin)) -> dict:
    cfg = svc.get_signalforge_config(db)
    if not cfg:
        raise HTTPException(status_code=404, detail="SIGNALFORGE is not configured.")
    if not signalforge.health_check(base_url=cfg["base_url"], operator_key=cfg["operator_key"]):
        raise HTTPException(status_code=503, detail=(
            f"SIGNALFORGE Control API not reachable at {cfg['base_url']} or key is invalid."))
    return {"connected": True, "base_url": cfg["base_url"]}


@router.delete("/signalforge", status_code=204)
def signalforge_disconnect(db: Session = Depends(get_db),
                           _admin: User = Depends(require_admin)) -> Response:
    svc.delete_signalforge_config(db)
    return Response(status_code=204)

"""
Admin API — M8-C3 base + M8-C5 additions.

New endpoints:
  GET  /admin/rate-limits/{user_id}        — current Redis counters
  POST /admin/rate-limits/reset/{user_id}  — clear counters
  GET  /admin/webhook-deliveries           — delivery log with retry detail
  POST /admin/users/{id}/plan             — update user plan (with audit log)

All others from M8-C3 unchanged.
"""
from __future__ import annotations

from typing import Any, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import get_db
from app.core.logging import get_logger
from app.services.admin_service import AdminService
from app.core.circuit_breaker import get_all_states, _registry as cb_registry
from app.workers.monitoring import get_celery_stats
from app.core.plans import PLANS
from app.core.rate_limiting import get_user_rate_limit_state, reset_user_rate_limits

logger = get_logger("api.admin")
router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class UserSummary(BaseModel):
    id: str
    email: str
    is_admin: bool
    is_suspended: bool
    plan: Optional[str]
    created_at: Optional[datetime]
    strategy_count: int
    active_campaign_count: int
    last_active_at: Optional[datetime]
    class Config:
        from_attributes = True


class SuspendRequest(BaseModel):
    reason: str = ""


class TaskErrorSummary(BaseModel):
    id: str
    task_name: str
    task_id: Optional[str]
    error_type: Optional[str]
    error_message: Optional[str]
    args_summary: Optional[str]
    ts: datetime
    resolved_at: Optional[datetime]
    resolved_by: Optional[str]
    resolution_note: Optional[str]
    class Config:
        from_attributes = True


class TaskErrorResolveRequest(BaseModel):
    resolution_note: str


class SuppressionEntry(BaseModel):
    # `Optional[str]` WITHOUT a default is still a required field in pydantic
    # v2 - it only permits the value None. Both were therefore mandatory, so
    # the admin UI's addSuppression({email, reason}) got
    # "phone: Field required" 422 on every call. Suppression needs either an
    # email or a phone (the model enforces that with a CheckConstraint), so
    # both default to None.
    email: Optional[str] = None
    phone: Optional[str] = None
    reason: str
    source: str = "admin"


class PlanUpdateRequest(BaseModel):
    plan: str
    reason: str = ""


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

@router.get("/users", response_model=list[UserSummary])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> list[Any]:
    return AdminService.list_users(db, page=page, page_size=page_size)


@router.get("/users/{user_id}", response_model=UserSummary)
async def get_user_detail(
    user_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> Any:
    user = AdminService.get_user_detail(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/users/{user_id}/suspend")
async def suspend_user(
    user_id: str,
    body: SuspendRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
) -> dict:
    success = AdminService.suspend_user(db, user_id=user_id, reason=body.reason, suspended_by=admin.email)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    logger.info("admin.user_suspended", user_id=user_id, by=admin.email)
    return {"status": "suspended", "user_id": user_id}


@router.post("/users/{user_id}/unsuspend")
async def unsuspend_user(
    user_id: str,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
) -> dict:
    success = AdminService.unsuspend_user(db, user_id=user_id, resumed_by=admin.email)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "active", "user_id": user_id}


@router.post("/users/{user_id}/plan")
async def update_user_plan(
    user_id: str,
    body: PlanUpdateRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
) -> dict:
    """Update user plan. Validates against PLANS. Writes audit log entry."""
    if body.plan not in PLANS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown plan '{body.plan}'. Valid plans: {list(PLANS.keys())}",
        )
    from sqlalchemy import text
    import datetime
    row = db.execute(text("SELECT id, email FROM users WHERE id = :uid"), {"uid": user_id}).first()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    db.execute(text("UPDATE users SET plan = :plan, updated_at = NOW() WHERE id = :uid"),
               {"plan": body.plan, "uid": user_id})

    # Audit log
    db.execute(text("""
        INSERT INTO task_errors (task_name, task_id, args_summary, error_type, error_message, ts)
        VALUES ('admin.plan_update', :uid, :summary, 'AuditLog', :msg, NOW())
    """), {
        "uid": user_id,
        "summary": f"user_id={user_id}",
        "msg": f"Plan changed to '{body.plan}' by {admin.email}. Reason: {body.reason}",
    })
    db.commit()
    logger.info("admin.plan_updated", user_id=user_id, plan=body.plan, by=admin.email)
    return {"status": "updated", "user_id": user_id, "plan": body.plan}


# ---------------------------------------------------------------------------
# Suppression list
# ---------------------------------------------------------------------------

@router.get("/suppression-list")
async def list_suppression(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> dict:
    items, total = AdminService.list_suppression(db, page=page, page_size=page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/suppression-list", status_code=201)
async def add_to_suppression(
    entry: SuppressionEntry,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
) -> dict:
    AdminService.add_suppression(db, email=entry.email, phone=entry.phone,
                                 reason=entry.reason, source="admin", added_by=admin.email)
    return {"status": "added"}


@router.delete("/suppression-list/{email}")
async def remove_from_suppression(
    email: str,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
) -> dict:
    removed = AdminService.remove_suppression(db, email=email, removed_by=admin.email)
    if not removed:
        raise HTTPException(status_code=404, detail="Email not in suppression list")
    return {"status": "removed", "email": email}


# ---------------------------------------------------------------------------
# Task errors
# ---------------------------------------------------------------------------

@router.get("/task-errors", response_model=list[TaskErrorSummary])
async def list_task_errors(
    unresolved_only: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> list[Any]:
    return AdminService.list_task_errors(db, unresolved_only=unresolved_only, page=page, page_size=page_size)


@router.post("/task-errors/{error_id}/resolve")
async def resolve_task_error(
    error_id: str,
    body: TaskErrorResolveRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
) -> dict:
    success = AdminService.resolve_task_error(db, error_id=error_id, resolved_by=admin.email, note=body.resolution_note)
    if not success:
        raise HTTPException(status_code=404, detail="Task error not found")
    return {"status": "resolved", "error_id": error_id}


# ---------------------------------------------------------------------------
# Circuit breakers
# ---------------------------------------------------------------------------

@router.get("/circuit-breakers")
async def list_circuit_breakers(_admin=Depends(require_admin)) -> list[dict]:
    return get_all_states()


@router.post("/circuit-breakers/{provider}/reset")
async def reset_circuit_breaker(provider: str, admin=Depends(require_admin)) -> dict:
    cb = cb_registry.get(provider)
    if not cb:
        raise HTTPException(status_code=404, detail=f"No circuit breaker for '{provider}'")
    cb.record_success()
    logger.info("admin.circuit_breaker_reset", provider=provider, by=admin.email)
    return {"status": "reset", "provider": provider, "new_state": "CLOSED"}


# ---------------------------------------------------------------------------
# Playbook
# ---------------------------------------------------------------------------

@router.get("/playbook/scores")
async def list_playbook_scores(
    user_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    degrading_only: bool = Query(False, description="Show only patterns where effective_n < min_sample"),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> dict:
    """Returns all playbook scores, including decay metadata. Supports degrading_only filter."""
    from app.core.config import settings
    from sqlalchemy import text

    offset = (page - 1) * page_size
    where_clauses = []
    params: dict = {"limit": page_size, "offset": offset, "min_sample": settings.PLAYBOOK_MIN_SAMPLE}

    if user_id:
        where_clauses.append("ps.user_id = :user_id")
        params["user_id"] = user_id
    if degrading_only:
        where_clauses.append("ps.effective_sample_size < :min_sample AND ps.sample_size >= :min_sample")

    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    try:
        rows = db.execute(text(f"""
            SELECT ps.pattern_key, ps.variant, ps.reply_rate, ps.booking_rate,
                   ps.sample_size, ps.effective_sample_size, ps.is_reliable,
                   ps.decay_half_life_days, ps.oldest_outcome_ts, ps.trend,
                   ps.last_aggregated_at
            FROM playbook_scores ps
            {where}
            ORDER BY ps.last_aggregated_at DESC NULLS LAST
            LIMIT :limit OFFSET :offset
        """), params).mappings().all()
        return {"scores": [dict(r) for r in rows]}
    except Exception as e:
        logger.error("admin.playbook_scores_failed", error=str(e))
        return {"scores": []}


@router.post("/playbook/recompute")
async def recompute_playbook(admin=Depends(require_admin)) -> dict:
    from app.workers.learning_tasks import run_strategy_aggregation
    run_strategy_aggregation.delay()
    logger.info("admin.playbook_recompute_triggered", by=admin.email)
    return {"status": "triggered"}


# ---------------------------------------------------------------------------
# Rate limiting (NEW — C5)
# ---------------------------------------------------------------------------

@router.get("/rate-limits/{user_id}")
async def get_rate_limits(
    user_id: str,
    _admin=Depends(require_admin),
) -> dict:
    """Current Redis rate-limit counters for a user."""
    return {"user_id": user_id, "limits": get_user_rate_limit_state(user_id)}


@router.post("/rate-limits/reset/{user_id}")
async def reset_rate_limits(
    user_id: str,
    admin=Depends(require_admin),
) -> dict:
    """Clear all rate-limit counters for a user (support action)."""
    deleted = reset_user_rate_limits(user_id)
    logger.info("admin.rate_limits_reset", user_id=user_id, keys_deleted=deleted, by=admin.email)
    return {"status": "reset", "user_id": user_id, "keys_deleted": deleted}


# ---------------------------------------------------------------------------
# Webhook deliveries (NEW — C5)
# ---------------------------------------------------------------------------

@router.get("/webhook-deliveries")
async def list_webhook_deliveries(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> list[dict]:
    """Outbound webhook delivery log with retry counts and error details."""
    from app.services.webhook_delivery import get_deliveries
    return get_deliveries(db, status=status, limit=limit)


# ---------------------------------------------------------------------------
# Celery stats
# ---------------------------------------------------------------------------

@router.get("/celery-stats")
async def celery_stats(_admin=Depends(require_admin)) -> dict:
    return get_celery_stats()


# ---------------------------------------------------------------------------
# Encryption key rotation
# ---------------------------------------------------------------------------

@router.post("/rotate-encryption-key")
async def rotate_encryption_key(
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
) -> dict:
    from app.core.crypto import rotate_all_secrets
    logger.info("admin.encryption_key_rotation_started", by=admin.email)
    result = rotate_all_secrets(db)
    logger.info("admin.encryption_key_rotation_completed", **result, by=admin.email)
    return {**result, "status": "ok"}

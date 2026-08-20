"""
Global error handling for the FastAPI application.

- Unhandled exceptions → logged at ERROR with full structured traceback
- Client receives: {"error": "internal_server_error", "request_id": "..."} (no stack trace)
- ComplianceError → 422 with compliance_code exposed to client (not a secret)
- Known HTTP exceptions pass through unchanged

Register with: app.add_exception_handler(Exception, global_exception_handler)
"""
from __future__ import annotations

import traceback
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import ComplianceError, ResourceNotFoundError, ForbiddenError
from app.core.logging import get_logger, get_request_id

logger = get_logger("core.errors")


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all for unhandled exceptions. Logs full detail, returns safe response.
    """
    request_id = get_request_id() or request.headers.get("X-Request-ID", "")

    if isinstance(exc, StarletteHTTPException):
        # Known HTTP exceptions (e.g., from Depends that raise HTTPException)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail, "request_id": request_id},
        )

    if isinstance(exc, ComplianceError):
        logger.warning(
            "compliance_error",
            compliance_code=exc.compliance_code,
            message=str(exc),
            path=str(request.url.path),
            request_id=request_id,
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": "compliance_error",
                "compliance_code": exc.compliance_code,
                "message": str(exc),
                "request_id": request_id,
            },
        )

    if isinstance(exc, ResourceNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "message": str(exc), "request_id": request_id},
        )

    if isinstance(exc, ForbiddenError):
        return JSONResponse(
            status_code=403,
            content={"error": "forbidden", "message": str(exc), "request_id": request_id},
        )

    # Truly unhandled — log full traceback, return minimal safe response
    tb = traceback.format_exc()
    logger.error(
        "unhandled_exception",
        error=str(exc),
        error_type=type(exc).__name__,
        path=str(request.url.path),
        method=request.method,
        traceback=tb,
        request_id=request_id,
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "request_id": request_id,
            # Stack trace deliberately withheld from client response
        },
    )


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle Pydantic validation errors with structured 422."""
    from fastapi.exceptions import RequestValidationError
    request_id = get_request_id()
    if isinstance(exc, RequestValidationError):
        logger.warning(
            "validation_error",
            errors=exc.errors(),
            path=str(request.url.path),
            request_id=request_id,
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "detail": exc.errors(),
                "request_id": request_id,
            },
        )
    return await global_exception_handler(request, exc)

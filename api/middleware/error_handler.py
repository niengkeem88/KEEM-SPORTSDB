"""Custom exception handlers and error-response middleware for FastAPI."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DatabaseError, InterfaceError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured error response body
# ---------------------------------------------------------------------------

def _error_response(status_code: int, message: str, detail: Any = None) -> JSONResponse:
    body: dict[str, Any] = {
        "error": {
            "status_code": status_code,
            "message": message,
        }
    }
    if detail is not None:
        body["error"]["detail"] = detail
    return JSONResponse(status_code=status_code, content=body)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle standard HTTP exceptions (4xx, 5xx)."""
    return _error_response(
        status_code=exc.status_code,
        message=exc.detail if isinstance(exc.detail, str) else "HTTP error",
        detail=exc.detail,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle Pydantic / request-body validation errors."""
    errors = []
    for err in exc.errors():
        errors.append({
            "field": " -> ".join(str(loc) for loc in err.get("loc", [])),
            "message": err.get("msg", ""),
            "type": err.get("type", ""),
        })

    logger.warning("Validation error: %s", errors)
    return _error_response(
        status_code=422,
        message="Request validation failed",
        detail=errors,
    )


async def database_error_handler(request: Request, exc: DatabaseError) -> JSONResponse:
    """Handle SQLAlchemy database errors gracefully.

    Logs the full exception internally but returns a sanitised 503 to clients.
    """
    logger.exception("Database error: %s", exc)
    return _error_response(
        status_code=503,
        message="Database service unavailable. Please retry later.",
    )


async def interface_error_handler(request: Request, exc: InterfaceError) -> JSONResponse:
    """Handle connection-level database errors."""
    logger.exception("Database interface error: %s", exc)
    return _error_response(
        status_code=503,
        message="Database connection lost. Please retry later.",
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for any unhandled exception.

    Returns a 500 without leaking internal details.
    """
    logger.exception("Unhandled exception: %s", exc)
    return _error_response(
        status_code=500,
        message="Internal server error.",
    )


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def register_error_handlers(app: FastAPI) -> None:
    """Attach all custom exception handlers to the FastAPI application."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(DatabaseError, database_error_handler)
    app.add_exception_handler(InterfaceError, interface_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

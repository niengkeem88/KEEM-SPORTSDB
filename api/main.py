"""FastAPI application factory — entrypoint for the soccer data REST API.

Run with (from the repo root)::

    uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

Or directly::

    python -m api.main
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI

from api.config import api_settings
from api.database import dispose_db
from api.middleware.error_handler import register_error_handlers
from api.redis_client import close_redis
from api.routers import fixtures as fixtures_router
from api.routers import leagues as leagues_router

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler.

    Startup: log the bind address.
    Shutdown: gracefully close the database pool and Redis connection.
    """
    logger.info(
        "Soccer API starting — host=%s port=%d debug=%s",
        api_settings.host,
        api_settings.port,
        api_settings.debug,
    )
    yield
    logger.info("Shutting down — closing connections...")
    await dispose_db()
    await close_redis()
    logger.info("All connections closed.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Construct and configure the FastAPI application instance."""
    app = FastAPI(
        title="Soccer Data API",
        description=(
            "High-performance read API for the global soccer tracking database. "
            "Serves league, fixture, and live-match data backed by PostgreSQL "
            "and Redis caching."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── Error handlers ──────────────────────────────────────────────────
    register_error_handlers(app)

    # ── Routers ─────────────────────────────────────────────────────────
    app.include_router(leagues_router.router)
    app.include_router(fixtures_router.router)

    # ── Root health-check ───────────────────────────────────────────────
    @app.get("/health", tags=["System"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "soccer-api"}

    return app


# ---------------------------------------------------------------------------
# Module-level app instance (imported by uvicorn)
# ---------------------------------------------------------------------------

app = create_app()


# ---------------------------------------------------------------------------
# Direct execution
# ---------------------------------------------------------------------------

def _configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, api_settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        stream=sys.stdout,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def main() -> None:
    _configure_logging()
    uvicorn.run(
        "api.main:app",
        host=api_settings.host,
        port=api_settings.port,
        reload=api_settings.debug,
        log_level=api_settings.log_level,
    )


if __name__ == "__main__":
    main()

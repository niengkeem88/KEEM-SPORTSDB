"""API-layer configuration — loaded from environment or .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Final


@dataclass(frozen=True)
class APISettings:
    # -- Server ---------------------------------------------------------------
    host: str = field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    port: int = int(os.getenv("API_PORT", "8000"))
    debug: bool = os.getenv("API_DEBUG", "false").lower() in ("1", "true", "yes")
    log_level: str = field(default_factory=lambda: os.getenv("API_LOG_LEVEL", "info"))

    # -- Database (read-optimised pool) ---------------------------------------
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://user:pass@localhost:5432/soccerdb",
        )
    )
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "20"))
    db_max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "40"))

    # -- Redis (cache layer) --------------------------------------------------
    redis_url: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
    # TTLs in seconds
    cache_ttl_live_s: int = int(os.getenv("CACHE_TTL_LIVE_S", "30"))
    cache_ttl_historical_s: int = int(os.getenv("CACHE_TTL_HISTORICAL_S", "86400"))  # 24 h
    cache_ttl_leagues_s: int = int(os.getenv("CACHE_TTL_LEAGUES_S", "3600"))         # 1 h
    cache_ttl_fixtures_date_s: int = int(os.getenv("CACHE_TTL_FIXTURES_DATE_S", "120"))  # 2 min

    # -- Live status list (mirrors config.py in ingestion) --------------------
    live_statuses: frozenset[str] = frozenset({"1H", "HT", "2H", "ET", "P"})


api_settings: Final[APISettings] = APISettings()

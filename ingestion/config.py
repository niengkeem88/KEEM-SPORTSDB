"""Application configuration — sourced from environment variables with sensible defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Final


@dataclass(frozen=True)
class Settings:
    # -- API-Football ---------------------------------------------------------
    api_base_url: str = field(
        default_factory=lambda: os.getenv("API_FOOTBALL_BASE_URL", "https://v3.football.api-sports.io")
    )
    api_key: str = field(
        default_factory=lambda: os.getenv("API_FOOTBALL_KEY", "")
    )
    api_rate_limit_rps: float = float(
        os.getenv("API_RATE_LIMIT_RPS", "9.0")       # Free tier: 10 req/s; keep 10% headroom
    )
    api_request_timeout_s: int = int(
        os.getenv("API_REQUEST_TIMEOUT_S", "30")
    )

    # -- Database -------------------------------------------------------------
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/soccerdb")
    )
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "10"))
    db_max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))

    # -- Sync schedules (seconds) ---------------------------------------------
    weekly_fixtures_interval_s: int = int(
        os.getenv("WEEKLY_FIXTURES_INTERVAL_S", "86400")    # 24 h
    )
    pre_match_lineups_window_s: int = int(
        os.getenv("PRE_MATCH_LINEUPS_WINDOW_S", "2700")     # 45 min
    )
    live_engine_poll_s: int = int(
        os.getenv("LIVE_ENGINE_POLL_S", "60")               # 60 s
    )

    # -- Look-ahead windows for weekly sync -----------------------------------
    weekly_fixtures_days_ahead: int = int(
        os.getenv("WEEKLY_FIXTURES_DAYS_AHEAD", "7")
    )

    # -- Fixture status constants ---------------------------------------------
    LIVE_STATUSES: set[str] = frozenset({"1H", "HT", "2H", "ET", "P"})
    FINISHED_STATUSES: set[str] = frozenset({"FT", "AET", "AP", "AWD", "WO"})


# Single global settings instance
settings: Final[Settings] = Settings()

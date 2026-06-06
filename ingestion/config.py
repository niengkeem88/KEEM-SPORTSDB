"""Application configuration — sourced from environment variables with sensible defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Final


@dataclass(frozen=True)
class Settings:
    # -- Scorebat API ---------------------------------------------------------
    api_base_url: str = field(
        default_factory=lambda: os.getenv("SCOREBAT_BASE_URL", "https://www.scorebat.com/v3/api")
    )
    api_key: str = field(
        default_factory=lambda: os.getenv("SCOREBAT_TOKEN", "")
    )
    # Scorebat free tier: ~100 req/day. Keep a safe 1 req / 6 s = ~14 400/day.
    api_rate_limit_rps: float = float(
        os.getenv("API_RATE_LIMIT_RPS", "0.16")       # ~1 request every 6 seconds
    )
    api_request_timeout_s: int = int(
        os.getenv("API_REQUEST_TIMEOUT_S", "30")
    )
    # Scorebat returns ALL matches in a single call, so we need a broader window.
    fetch_window_days: int = int(os.getenv("SCOREBAT_FETCH_WINDOW_DAYS", "14"))

    # -- Database -------------------------------------------------------------
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/soccerdb")
    )
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "10"))
    db_max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))

    # -- Sync schedules (seconds) ---------------------------------------------
    weekly_fixtures_interval_s: int = int(
        os.getenv("WEEKLY_FIXTURES_INTERVAL_S", "43200")    # 12 h (Scorebat has no per-league endpoint)
    )
    pre_match_lineups_window_s: int = int(
        os.getenv("PRE_MATCH_LINEUPS_WINDOW_S", "0")       # Not supported by Scorebat free tier
    )
    live_engine_poll_s: int = int(
        os.getenv("LIVE_ENGINE_POLL_S", "30")              # 30 s (Scorebat returns all live in one call)
    )

    # -- Fixture status constants ---------------------------------------------
    # Scorebat uses: "UPCOMING", "LIVE", "HALFTIME", "FINISHED", "CANCELED", etc.
    # Mapped to our internal schema codes.
    SCOREBAT_STATUS_MAP: dict[str, str] = field(default_factory=lambda: {
        "UPCOMING": "NS",
        "LIVE": "1H",
        "HALFTIME": "HT",
        "FINISHED": "FT",
        "CANCELED": "CANC",
        "POSTPONED": "SUSP",
        "ABANDONED": "ABD",
        "NOT_STARTED": "NS",
        "INTERRUPTED": "INT",
        "AWARDED": "AWD",
        "WALKOVER": "WO",
        "": "NS",
    })

    LIVE_STATUSES: set[str] = frozenset({"1H", "HT", "2H", "ET", "P"})
    FINISHED_STATUSES: set[str] = frozenset({"FT", "AET", "AP", "AWD", "WO"})


# Single global settings instance
settings: Final[Settings] = Settings()

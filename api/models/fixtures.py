"""Pydantic models for fixture endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class FixtureSummary(BaseModel):
    """Compact fixture representation for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    league_id: int
    season_id: int
    home_team_id: int
    away_team_id: int
    match_status: str
    start_time: datetime
    home_score: Optional[int] = None
    away_score: Optional[int] = None


class FixtureDetail(FixtureSummary):
    """Full fixture detail including the live events timeline."""

    live_events_cache: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class FixtureListResponse(BaseModel):
    """Wrapper for a list of fixtures."""

    data: list[FixtureDetail]
    total: int

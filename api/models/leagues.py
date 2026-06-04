"""Pydantic models for league endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, HttpUrl


class LeagueResponse(BaseModel):
    """Public representation of a league."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    country: str
    logo_url: Optional[str] = None
    type: str  # "League" | "Cup"
    created_at: datetime
    updated_at: datetime


class LeagueListResponse(BaseModel):
    """Wrapper for a list of leagues."""

    data: list[LeagueResponse]
    total: int

"""/api/v1/leagues endpoint handler."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.leagues import LeagueListResponse, LeagueResponse
from api.models.leagues import League  # ORM model
from api.redis_client import (
    get_cached_leagues,
    set_cached_leagues,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/leagues", tags=["Leagues"])


@router.get("", response_model=LeagueListResponse)
async def get_leagues(session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Return all tracked leagues.

    Results are cached in Redis for 1 hour to reduce database load.
    """
    # ── Check Redis ─────────────────────────────────────────────────────
    cached = await get_cached_leagues()
    if cached is not None:
        logger.debug("Leagues cache hit (%d items).", len(cached))
        return {"data": cached, "total": len(cached)}

    # ── Cache miss — query PostgreSQL ───────────────────────────────────
    result = await session.execute(select(League).order_by(League.name))
    leagues = result.scalars().all()

    serialised = [LeagueResponse.model_validate(l).model_dump(mode="json") for l in leagues]

    # ── Write-through cache ─────────────────────────────────────────────
    await set_cached_leagues(serialised)

    return {"data": serialised, "total": len(serialised)}

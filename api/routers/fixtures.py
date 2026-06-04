"""/api/v1/fixtures/* endpoint handlers with Redis caching."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import api_settings
from api.database import get_db
from api.models.fixtures import FixtureDetail, FixtureListResponse, FixtureSummary
from ingestion.models import Fixture  # ORM model
from api.redis_client import (
    get_cached_fixture,
    get_cached_fixtures_by_date,
    get_cached_live_fixtures,
    set_cached_fixture,
    set_cached_fixtures_by_date,
    set_cached_live_fixtures,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/fixtures", tags=["Fixtures"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _fixture_is_live(fxt: Fixture) -> bool:
    return fxt.match_status in api_settings.live_statuses


def _fixture_is_historical(fxt: Fixture) -> bool:
    """Consider a fixture historical if it's finished or its start is >1 h ago and not live."""
    finished = fxt.match_status in {"FT", "AET", "AP", "AWD", "WO"}
    if finished:
        return True
    # Past kick-off by more than an hour and not currently live
    if fxt.start_time < _now_utc() - __import__("datetime").timedelta(hours=1):
        return not _fixture_is_live(fxt)
    return False


def _serialise_fixture_detail(fxt: Fixture) -> dict[str, Any]:
    return {
        "id": fxt.id,
        "league_id": fxt.league_id,
        "season_id": fxt.season_id,
        "home_team_id": fxt.home_team_id,
        "away_team_id": fxt.away_team_id,
        "match_status": fxt.match_status,
        "start_time": fxt.start_time.isoformat(),
        "home_score": fxt.home_score,
        "away_score": fxt.away_score,
        "live_events_cache": fxt.live_events_cache,
        "created_at": fxt.created_at.isoformat(),
        "updated_at": fxt.updated_at.isoformat(),
    }


def _serialise_fixture_summary(fxt: Fixture) -> dict[str, Any]:
    return {
        "id": fxt.id,
        "league_id": fxt.league_id,
        "season_id": fxt.season_id,
        "home_team_id": fxt.home_team_id,
        "away_team_id": fxt.away_team_id,
        "match_status": fxt.match_status,
        "start_time": fxt.start_time.isoformat(),
        "home_score": fxt.home_score,
        "away_score": fxt.away_score,
    }


# ---------------------------------------------------------------------------
# GET /fixtures/date/{date}
# ---------------------------------------------------------------------------

@router.get("/date/{date}", response_model=FixtureListResponse)
async def get_fixtures_by_date(
    date: str = Path(..., description="Date in YYYY-MM-DD format"),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return all fixtures for the given *date*, ordered by start time.

    The response is cached in Redis for 2 minutes because fixture schedules
    rarely shift within a single day.
    """
    # Validate date format
    try:
        parsed = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format '{date}'; expected YYYY-MM-DD.",
        )

    # ── Check Redis ─────────────────────────────────────────────────────
    cached = await get_cached_fixtures_by_date(date)
    if cached is not None:
        logger.debug("Cache hit for fixtures/date/%s (%d items).", date, len(cached))
        return {"data": cached, "total": len(cached)}

    # ── Cache miss — query PostgreSQL ───────────────────────────────────
    day_start = datetime.combine(parsed, __import__("datetime").time.min, tzinfo=timezone.utc)
    day_end = datetime.combine(parsed, __import__("datetime").time.max, tzinfo=timezone.utc)

    result = await session.execute(
        select(Fixture)
        .where(Fixture.start_time.between(day_start, day_end))
        .order_by(Fixture.start_time.asc())
    )
    fixtures: list[Fixture] = list(result.scalars().all())

    serialised = [_serialise_fixture_detail(f) for f in fixtures]

    # ── Write-through cache ─────────────────────────────────────────────
    await set_cached_fixtures_by_date(date, serialised)

    return {"data": serialised, "total": len(serialised)}


# ---------------------------------------------------------------------------
# GET /fixtures/live
# ---------------------------------------------------------------------------

@router.get("/live", response_model=FixtureListResponse)
async def get_live_fixtures(
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return all currently in-play fixtures with live scores and events.

    **Caching strategy:** Redis with 30-second TTL. The ``live_engine_polling``
    worker in the ingestion service updates these rows every 60 s, so 30 s
    ensures clients never see data older than two ingestion cycles.
    """
    # ── Check Redis ─────────────────────────────────────────────────────
    cached = await get_cached_live_fixtures()
    if cached is not None:
        logger.debug("Cache hit for fixtures/live (%d items).", len(cached))
        return {"data": cached, "total": len(cached)}

    # ── Cache miss — query PostgreSQL ───────────────────────────────────
    result = await session.execute(
        select(Fixture)
        .where(Fixture.match_status.in_(api_settings.live_statuses))  # type: ignore[union-attr]
        .order_by(Fixture.start_time.asc())
    )
    fixtures: list[Fixture] = list(result.scalars().all())

    serialised = [_serialise_fixture_detail(f) for f in fixtures]

    # ── Write-through cache with short TTL ──────────────────────────────
    await set_cached_live_fixtures(serialised)

    return {"data": serialised, "total": len(serialised)}


# ---------------------------------------------------------------------------
# GET /fixtures/{id}
# ---------------------------------------------------------------------------

@router.get("/{fixture_id}", response_model=FixtureDetail)
async def get_fixture_by_id(
    fixture_id: int = Path(..., description="API provider fixture identifier"),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return full details for a single fixture, including the live events
    timeline from the JSONB ``live_events_cache``.

    **Caching strategy:**
    - **Active / live fixture** → Redis with 30-second TTL.
    - **Historical / finished fixture** → Redis with 24-hour TTL.
    This guarantees that clients polling a live match always see fresh data,
    while archived match details are served from cache for a full day.
    """
    # ── Check Redis ─────────────────────────────────────────────────────
    cached = await get_cached_fixture(fixture_id)
    if cached is not None:
        logger.debug("Cache hit for fixture/%d.", fixture_id)
        return cached  # type: ignore[return-value]

    # ── Cache miss — query PostgreSQL ───────────────────────────────────
    result = await session.execute(
        select(Fixture).where(Fixture.id == fixture_id)
    )
    fxt: Fixture | None = result.scalar_one_or_none()

    if fxt is None:
        raise HTTPException(
            status_code=404,
            detail=f"Fixture {fixture_id} not found.",
        )

    is_live = _fixture_is_live(fxt)

    serialised = _serialise_fixture_detail(fxt)

    # ── Write-through cache ─────────────────────────────────────────────
    await set_cached_fixture(fixture_id, serialised, live=is_live)

    return serialised

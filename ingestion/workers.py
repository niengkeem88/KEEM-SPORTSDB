"""Multi-tier synchronisation workers for API-Football v3 data ingestion.

Provides three core async workers:

1. ``sync_weekly_fixtures`` — fetch & upsert fixtures for the next N days.
2. ``sync_pre_match_lineups`` — fetch lineups for fixtures starting within
   the pre-match window (default 45 min).
3. ``live_engine_polling`` — continuous poll of live-match endpoints,
   updating scores and overwriting the JSONB event cache.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ingestion.client import ApiFootballClient
from ingestion.config import settings
from ingestion.database import AsyncSessionFactory, upsert_fixtures
from ingestion.models import Fixture, League, Season

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

API_DATE_FMT = "%Y-%m-%d"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _today_utc() -> date:
    return _now_utc().date()


def _extract_fixture_rows(raw_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalise API-Football fixture responses into column-value dicts.

    The API returns a nested structure::

        {
            "fixture": {"id": ..., "date": ..., "status": {"short": ...}},
            "league": {"id": ...},
            "teams": {"home": {"id": ...}, "away": {"id": ...}},
            "goals": {"home": ..., "away": ...},
            "score": { ... },          // extended scoring detail
        }
    """
    rows: list[dict[str, Any]] = []
    for item in raw_list:
        fixture = item.get("fixture", {})
        league = item.get("league", {})
        teams = item.get("teams", {})
        goals = item.get("goals", {})

        home_score = goals.get("home")
        away_score = goals.get("away")

        row = {
            "id": fixture["id"],
            "league_id": league["id"],
            "season_id": league.get("season"),
            "home_team_id": teams.get("home", {}).get("id"),
            "away_team_id": teams.get("away", {}).get("id"),
            "match_status": fixture.get("status", {}).get("short", "NS"),
            "start_time": _parse_fixture_date(fixture.get("date")),
            "home_score": home_score,
            "away_score": away_score,
            "live_events_cache": _build_events_cache(item),
        }
        rows.append(row)
    return rows


def _parse_fixture_date(raw: str | None) -> datetime | None:
    """Parse ISO-8601 fixture date from the API."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt
    except (ValueError, TypeError):
        logger.warning("Cannot parse fixture date: %s", raw)
        return None


def _build_events_cache(raw_fixture: dict[str, Any]) -> dict[str, Any]:
    """Assemble the raw API payload into the ``live_events_cache`` JSONB document.

    This is the *complete* live-match payload so that consumers can render
    timelines without additional API calls.  Included sub-objects:

    - ``events``: goals, cards, substitutions, penalties
    - ``statistics``: ball possession, shots, etc.
    - ``lineups``: starting XI & formations (populated by pre-match worker)
    - ``score``: extended scoreboard (halftime, fulltime, extra, penalties)
    """
    return {
        "events": raw_fixture.get("events", []),
        "statistics": raw_fixture.get("statistics", []),
        "lineups": raw_fixture.get("lineups", []),
        "score": raw_fixture.get("score", {}),
        "fixture": raw_fixture.get("fixture", {}),
        "teams": raw_fixture.get("teams", {}),
        "goals": raw_fixture.get("goals", {}),
    }


# ---------------------------------------------------------------------------
# 1. Weekly fixtures sync  (daily cron)
# ---------------------------------------------------------------------------

async def sync_weekly_fixtures(
    client: ApiFootballClient,
    session: AsyncSession,
    *,
    days_ahead: int = settings.weekly_fixtures_days_ahead,
) -> int:
    """Fetch and upsert fixtures for the next *days_ahead* days.

    Iterates over all leagues that have a ``current`` season in the database
    so that every relevant competition is covered.

    Returns the total number of upserted fixtures.
    """
    today = _today_utc()
    until = today + timedelta(days=days_ahead)
    date_from = today.strftime(API_DATE_FMT)
    date_to = until.strftime(API_DATE_FMT)

    # Discover active leagues & seasons
    result = await session.execute(
        select(Season).where(Season.is_current.is_(True))   # type: ignore[union-attr]
    )
    current_seasons: list[Season] = list(result.scalars().all())

    if not current_seasons:
        logger.warning("No current-season entries found; skipping weekly fixture sync.")
        return 0

    total = 0
    for s in current_seasons:
        try:
            raw = await client.fetch_fixtures(
                league_id=s.league_id,
                season=s.year,
                date_from=date_from,
                date_to=date_to,
            )
        except Exception:
            logger.exception("Failed to fetch fixtures for league %s / season %s", s.league_id, s.year)
            continue

        rows = _extract_fixture_rows(raw)
        if not rows:
            logger.debug("No new fixtures for league %s / season %s", s.league_id, s.year)
            continue

        # Enrich with league/season FKs (already present from extract, but ensure correct)
        for row in rows:
            row.setdefault("season_id", s.id)

        upserted = await upsert_fixtures(session, rows)
        total += upserted
        logger.info("Weekly sync — league %s: %d fixtures upserted", s.league_id, upserted)

    logger.info("Weekly fixtures sync complete: %d total upserted.", total)
    return total


# ---------------------------------------------------------------------------
# 2. Pre-match lineups sync  (triggered ~45 min before kick-off)
# ---------------------------------------------------------------------------

async def sync_pre_match_lineups(
    client: ApiFootballClient,
    session: AsyncSession,
) -> int:
    """Fetch lineups & formations for fixtures starting within the pre-match window.

    Finds fixtures whose ``match_status`` is ``'NS'`` and whose kick-off is
    within the next ``PRE_MATCH_LINEUPS_WINDOW_S`` seconds (default 45 min).

    The lineups are written directly into the fixture's ``live_events_cache``
    JSONB column so they are available the moment the match goes live.
    """
    now = _now_utc()
    window_end = now + timedelta(seconds=settings.pre_match_lineups_window_s)

    result = await session.execute(
        select(Fixture).where(
            Fixture.match_status == "NS",
            Fixture.start_time.between(now, window_end),   # type: ignore[arg-type]
        )
    )
    fixtures: list[Fixture] = list(result.scalars().all())

    if not fixtures:
        logger.debug("Pre-match lineups: no fixtures in the upcoming window.")
        return 0

    updated_count = 0
    for fxt in fixtures:
        try:
            raw_lineups = await client.fetch_fixture_lineups(fxt.id)
        except Exception:
            logger.exception("Failed to fetch lineups for fixture %s", fxt.id)
            continue

        if not raw_lineups:
            continue

        # Merge lineups into the existing (or new) events cache
        cache = dict(fxt.live_events_cache) if fxt.live_events_cache else {}
        cache["lineups"] = raw_lineups
        fxt.live_events_cache = cache

        session.add(fxt)
        updated_count += 1

    await session.commit()
    logger.info("Pre-match lineups updated for %d fixtures.", updated_count)
    return updated_count


# ---------------------------------------------------------------------------
# 3. Live engine polling  (every 60 s)
# ---------------------------------------------------------------------------

async def _fetch_and_update_live_fixture(
    client: ApiFootballClient,
    session: AsyncSession,
    fixture_id: int,
) -> bool:
    """Fetch a single live fixture's data and update scores + events cache.

    Returns ``True`` if the row was updated.
    """
    try:
        raw_list = await client.fetch_fixtures(ids=str(fixture_id))
    except Exception:
        logger.exception("Live poll failed for fixture %s", fixture_id)
        return False

    if not raw_list:
        logger.warning("Live poll returned no data for fixture %s", fixture_id)
        return False

    raw = raw_list[0]
    fixture_data = raw.get("fixture", {})
    goals = raw.get("goals", {})
    status_short = fixture_data.get("status", {}).get("short", "NS")

    home_score = goals.get("home")
    away_score = goals.get("away")

    # Fetch the current ORM object
    fxt = await session.get(Fixture, fixture_id)
    if fxt is None:
        logger.warning("Fixture %s not found in database; skipping.", fixture_id)
        return False

    # Update score & status
    fxt.match_status = status_short
    if home_score is not None:
        fxt.home_score = home_score
    if away_score is not None:
        fxt.away_score = away_score

    # **Completely overwrite** the events cache with the latest API payload
    fxt.live_events_cache = _build_events_cache(raw)

    session.add(fxt)
    return True


async def live_engine_polling(
    client: ApiFootballClient,
    session: AsyncSession,
) -> None:
    """One iteration of the live engine: update every fixture with an active status.

    This is designed to be called in a loop (every ``LIVE_ENGINE_POLL_S``
    seconds) from the orchestrator.
    """
    # Discover currently-live fixtures from the DB
    result = await session.execute(
        select(Fixture).where(Fixture.match_status.in_(settings.LIVE_STATUSES))  # type: ignore[union-attr]
    )
    live_fixtures: list[Fixture] = list(result.scalars().all())

    if not live_fixtures:
        logger.debug("Live engine: no active fixtures to poll.")
        return

    logger.info("Live engine polling %d fixtures.", len(live_fixtures))

    updated = 0
    for fxt in live_fixtures:
        ok = await _fetch_and_update_live_fixture(client, session, fxt.id)
        if ok:
            updated += 1

    await session.commit()
    logger.info("Live engine: %d / %d fixtures updated.", updated, len(live_fixtures))


# ---------------------------------------------------------------------------
# Async generator that yields fixture IDs going live soon (for pre-match)
# ---------------------------------------------------------------------------

async def iter_impending_fixtures(
    session: AsyncSession,
    *,
    look_ahead_s: int = 3600,
) -> AsyncIterator[Fixture]:
    """Yield fixtures whose kick-off is within the next *look_ahead_s* seconds.

    Useful for scheduling pre-match work without polling a separate endpoint.
    """
    now = _now_utc()
    window_end = now + timedelta(seconds=look_ahead_s)

    result = await session.execute(
        select(Fixture)
        .where(Fixture.match_status == "NS", Fixture.start_time.between(now, window_end))
        .order_by(Fixture.start_time.asc())
    )
    for fxt in result.scalars():
        yield fxt

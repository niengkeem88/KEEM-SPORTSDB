"""Multi-tier synchronisation workers for the Scorebat v3 API.

Scorebat provides match data, scores, and video highlights via a single
``/matches`` endpoint.  Unlike API-Football, there are no separate endpoints
for leagues, teams, or lineups — all metadata is embedded in the match object.

The workers adapt Scorebat's simpler API to our existing database schema by
extracting leagues, teams, and seasons from the match payload and upserting
them alongside the fixtures themselves.

Workers
-------
1. ``sync_weekly_fixtures`` — fetch all matches within a rolling window and
   upsert leagues, teams, seasons, and fixtures.
2. ``sync_pre_match_lineups`` — **disabled** for Scorebat (free tier does not
   provide lineup data).  Logs a single startup warning.
3. ``live_engine_polling`` — fetch all matches, filter to live-status ones,
   and update scores / events cache.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ingestion.client import ScorebatClient
from ingestion.config import settings
from ingestion.database import (
    AsyncSessionFactory,
    upsert_fixtures,
    upsert_leagues,
    upsert_seasons,
    upsert_teams,
)
from ingestion.models import Fixture, League, Season

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_DATE_FMT = "%Y-%m-%d"
SCOREBAT_TO_INTERNAL_STATUS: dict[str, str] = dict(settings.SCOREBAT_STATUS_MAP)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _today_utc() -> date:
    return _now_utc().date()


# ---------------------------------------------------------------------------
# Helpers — extraction & mapping
# ---------------------------------------------------------------------------

def _map_status(scorebat_status: str | None) -> str:
    """Map Scorebat status string to our internal match_status code."""
    raw = (scorebat_status or "").strip().upper()
    return SCOREBAT_TO_INTERNAL_STATUS.get(raw, "NS")


def _parse_datetime(raw: str | None) -> datetime | None:
    """Parse ISO-8601 date string from Scorebat."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        logger.warning("Cannot parse Scorebat date: %s", raw)
        return None


def _extract_league_rows(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract unique league/competition records from Scorebat matches."""
    seen: set[int] = set()
    rows: list[dict[str, Any]] = []
    for m in matches:
        comp = m.get("competition") or {}
        cid = comp.get("id")
        if cid is None or cid in seen:
            continue
        seen.add(cid)
        country_info = comp.get("country") or {}
        rows.append({
            "id": cid,
            "name": comp.get("name", f"Competition {cid}"),
            "country": country_info.get("name", "Unknown"),
            "logo_url": comp.get("logo") or comp.get("url"),
            "type": "League",
        })
    return rows


def _extract_team_rows(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract unique team records from Scorebat matches."""
    seen: set[int] = set()
    rows: list[dict[str, Any]] = []
    for m in matches:
        for side in ("homeTeam", "awayTeam"):
            team = m.get(side) or {}
            tid = team.get("id")
            if tid is None or tid in seen:
                continue
            seen.add(tid)
            rows.append({
                "id": tid,
                "name": team.get("name", f"Team {tid}"),
                "short_code": team.get("shortName") or team.get("slug", "").upper()[:10],
                "logo_url": team.get("logo") or team.get("crest"),
            })
    return rows


def _extract_season_rows(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive season records from match dates.

    Scorebat doesn't provide an explicit season ID, so we construct one
    from the competition id + year and mark it as current.
    """
    seen: set[tuple[int, int]] = set()
    rows: list[dict[str, Any]] = []
    for m in matches:
        comp = m.get("competition") or {}
        league_id = comp.get("id")
        if league_id is None:
            continue

        dt = _parse_datetime(m.get("start") or m.get("date"))
        if dt is None:
            continue

        year = dt.year
        # If we're in the first half of the year, the *season* year usually
        # refers to the previous calendar year (e.g. 2025/2026 season).
        # Scorebat doesn't give us a season identifier, so we use the
        # competition year as a proxy.
        season_key = (league_id, year)
        if season_key in seen:
            continue
        seen.add(season_key)

        # Build a synthetic season ID from league_id and year
        synthetic_id = int(f"{league_id}{year % 100:02d}")

        rows.append({
            "id": synthetic_id,
            "league_id": league_id,
            "year": year,
            "start_date": f"{year}-01-01",
            "end_date": f"{year}-12-31",
            "is_current": True,
        })
    return rows


def _extract_fixture_rows(
    matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalise Scorebat match objects into fixture column-value dicts.

    Scorebat match structure::

        {
            "id": 12345,
            "title": "Team A vs Team B",
            "date": "2026-06-06T20:00:00+00:00",
            "start": "2026-06-06T20:00:00+00:00",
            "competition": {"id": 123, "name": "..."},
            "homeTeam": {"id": 456, "name": "..."},
            "awayTeam": {"id": 789, "name": "..."},
            "score": {"home": 2, "away": 1, "halftime": {...}},
            "status": "LIVE" | "FINISHED" | "UPCOMING",
            "videos": [...],
        }
    """
    rows: list[dict[str, Any]] = []
    for item in matches:
        fixture_id = item.get("id")
        if fixture_id is None:
            continue

        comp = item.get("competition") or {}
        league_id = comp.get("id")
        if league_id is None:
            continue

        home = item.get("homeTeam") or {}
        away = item.get("awayTeam") or {}
        score = item.get("score") or {}
        dt = _parse_datetime(item.get("start") or item.get("date"))

        # Build synthetic season ID the same way as _extract_season_rows
        year = dt.year if dt else _now_utc().year
        season_id = int(f"{league_id}{year % 100:02d}")

        raw_status = item.get("status") or item.get("statusCode") or "UPCOMING"
        match_status = _map_status(raw_status)

        home_score = score.get("home")
        away_score = score.get("away")

        # Build events cache from Scorebat data
        events_cache = _build_events_cache(item)

        rows.append({
            "id": fixture_id,
            "league_id": league_id,
            "season_id": season_id,
            "home_team_id": home.get("id"),
            "away_team_id": away.get("id"),
            "match_status": match_status,
            "start_time": dt.isoformat() if dt else _now_utc().isoformat(),
            "home_score": home_score,
            "away_score": away_score,
            "live_events_cache": events_cache,
        })
    return rows


def _build_events_cache(raw_match: dict[str, Any]) -> dict[str, Any]:
    """Assemble the raw Scorebat match payload into a JSONB cache document.

    This mirrors the same structure expected by the API layer so that
    downstream consumers (Android client) can parse it consistently.
    """
    score = raw_match.get("score") or {}
    return {
        "fixture": {
            "id": raw_match.get("id"),
            "date": raw_match.get("start") or raw_match.get("date"),
            "status": {
                "short": _map_status(raw_match.get("status")),
                "long": raw_match.get("status", ""),
            },
        },
        "teams": {
            "home": raw_match.get("homeTeam"),
            "away": raw_match.get("awayTeam"),
        },
        "goals": {
            "home": score.get("home"),
            "away": score.get("away"),
        },
        "score": {
            "halftime": score.get("halftime"),
            "fulltime": score.get("fulltime"),
            "extratime": score.get("extratime"),
            "penalty": score.get("penalty"),
        },
        "events": raw_match.get("videos", []),   # Scorebat provides video highlights, not timeline events
        "statistics": [],
        "lineups": [],
        "raw_scorebat": raw_match,                # Preserve original payload for debugging
    }


# ---------------------------------------------------------------------------
# 1. Weekly fixtures sync
# ---------------------------------------------------------------------------

async def sync_weekly_fixtures(
    client: ScorebatClient,
    session: AsyncSession,
    *,
    window_days: int = settings.weekly_fixtures_interval_s // 3600 * 2,
) -> int:
    """Fetch all matches in a rolling window and upsert leagues, teams,
    seasons, and fixtures into the database.

    Scorebat returns all matches in a single call, so we fetch everything
    within a window of *window_days* days centred on today.
    """
    today = _today_utc()
    date_from = today.strftime(API_DATE_FMT)
    date_to = (today + timedelta(days=14)).strftime(API_DATE_FMT)  # Scorebat looks ahead ~2 weeks max

    logger.info("Fetching Scorebat matches from %s to %s ...", date_from, date_to)

    try:
        matches = await client.fetch_matches(date_from=date_from, date_to=date_to)
    except Exception:
        logger.exception("Failed to fetch matches from Scorebat")
        return 0

    if not matches:
        logger.info("No matches returned by Scorebat for the window.")
        return 0

    logger.info("Received %d matches from Scorebat.", len(matches))

    # --- Step 1: Upsert leagues ---
    league_rows = _extract_league_rows(matches)
    if league_rows:
        await upsert_leagues(session, league_rows)
        logger.info("Upserted %d leagues.", len(league_rows))
    else:
        logger.warning("No leagues extracted from Scorebat data.")

    # --- Step 2: Upsert teams ---
    team_rows = _extract_team_rows(matches)
    if team_rows:
        await upsert_teams(session, team_rows)
        logger.info("Upserted %d teams.", len(team_rows))

    # --- Step 3: Upsert seasons ---
    season_rows = _extract_season_rows(matches)
    if season_rows:
        await upsert_seasons(session, season_rows)
        logger.info("Upserted %d seasons.", len(season_rows))

    # --- Step 4: Upsert fixtures ---
    fixture_rows = _extract_fixture_rows(matches)
    if fixture_rows:
        total = await upsert_fixtures(session, fixture_rows)
        logger.info("Weekly sync complete: %d fixtures upserted.", total)
        return total

    return 0


# ---------------------------------------------------------------------------
# 2. Pre-match lineups sync  — DISABLED for Scorebat
# ---------------------------------------------------------------------------

_disabled_warning_logged = False


async def sync_pre_match_lineups(
    client: ScorebatClient,
    session: AsyncSession,
) -> int:
    """Lineup fetch is **not supported** by Scorebat's free tier.

    This worker is a no-op that logs a single warning so operators know
    lineups are unavailable.
    """
    global _disabled_warning_logged
    if not _disabled_warning_logged:
        logger.warning(
            "sync_pre_match_lineups is disabled — Scorebat free tier "
            "does not provide lineup data."
        )
        _disabled_warning_logged = True
    return 0


# ---------------------------------------------------------------------------
# 3. Live engine polling
# ---------------------------------------------------------------------------

async def live_engine_polling(
    client: ScorebatClient,
    session: AsyncSession,
) -> None:
    """One iteration of the live engine.

    Fetch all matches from Scorebat for today, filter to those with a live
    status in our system, and update scores + events cache in PostgreSQL.
    """
    today_str = _today_utc().strftime(API_DATE_FMT)

    try:
        matches = await client.fetch_matches_by_date(today_str)
    except Exception:
        logger.exception("Live engine: failed to fetch matches from Scorebat.")
        return

    if not matches:
        logger.debug("Live engine: no matches returned by Scorebat.")
        return

    updated = 0
    for raw in matches:
        fixture_id = raw.get("id")
        if fixture_id is None:
            continue

        mapped_status = _map_status(raw.get("status"))
        if mapped_status not in settings.LIVE_STATUSES:
            continue

        # Fetch existing fixture from DB
        fxt = await session.get(Fixture, fixture_id)
        if fxt is None:
            logger.debug("Live engine: fixture %s not in DB; skipping.", fixture_id)
            continue

        score = raw.get("score") or {}
        home_score = score.get("home")
        away_score = score.get("away")

        # Update score & status
        fxt.match_status = mapped_status
        if home_score is not None:
            fxt.home_score = home_score
        if away_score is not None:
            fxt.away_score = away_score

        # Overwrite events cache
        fxt.live_events_cache = _build_events_cache(raw)
        session.add(fxt)
        updated += 1

    await session.commit()
    logger.info("Live engine: %d live fixtures updated.", updated)


# ---------------------------------------------------------------------------
# Helper: iterate upcoming fixtures (used by the orchestrator)
# ---------------------------------------------------------------------------

async def iter_impending_fixtures(
    session: AsyncSession,
    *,
    look_ahead_s: int = 3600,
) -> AsyncIterator[Fixture]:
    """Yield fixtures starting within the next *look_ahead_s* seconds.

    This is a stub for Scorebat — lineups are unavailable so the consumer
    should not expect pre-match data.
    """
    now = _now_utc()
    window_end = now + timedelta(seconds=look_ahead_s)

    result = await session.execute(
        select(Fixture)
        .where(
            Fixture.match_status == "NS",
            Fixture.start_time.between(now, window_end),
        )
        .order_by(Fixture.start_time.asc())
    )
    for fxt in result.scalars():
        yield fxt

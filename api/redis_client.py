"""Async Redis cache client with connection pooling and typed helpers."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any, Optional

import redis.asyncio as aioredis

from api.config import api_settings

logger = logging.getLogger(__name__)

# Module-level pool — created once, shared across all requests
_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return the shared Redis client (created lazily)."""
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(
            api_settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
            retry_on_timeout=True,
        )
        logger.info("Redis client connected: %s", api_settings.redis_url)
    return _pool


async def close_redis() -> None:
    """Close the Redis connection pool (called on app shutdown)."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
        logger.info("Redis client closed.")


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_key(*, prefix: str, suffix: str = "") -> str:
    """Build a namespaced cache key to avoid collisions.

    Examples::

        _cache_key(prefix="fixture", suffix="123")   → "soccer:fixture:123"
        _cache_key(prefix="fixtures:live")            → "soccer:fixtures:live"
    """
    key = f"soccer:{prefix}"
    if suffix:
        key = f"{key}:{suffix}"
    return key


async def cache_get(key: str) -> Optional[dict[str, Any]]:
    """Fetch a JSON value from Redis. Returns ``None`` on cache miss."""
    try:
        r = await get_redis()
        raw = await r.get(key)
        if raw is not None:
            return json.loads(raw)
    except Exception:
        logger.warning("Redis cache GET failed (key=%s).", key, exc_info=True)
    return None


async def cache_set(key: str, value: dict[str, Any] | list[dict[str, Any]], ttl: int) -> None:
    """Store a JSON-serialisable value in Redis with the given *ttl* (seconds).

    Errors are logged but never raised — a failure to write to the cache
    must not degrade the API response.
    """
    try:
        r = await get_redis()
        raw = json.dumps(value, default=str)
        await r.setex(key, ttl, raw)
    except Exception:
        logger.warning("Redis cache SET failed (key=%s).", key, exc_info=True)


# ---------------------------------------------------------------------------
# Domain-specific cache helpers
# ---------------------------------------------------------------------------

async def get_cached_fixture(fixture_id: int) -> Optional[dict[str, Any]]:
    return await cache_get(_cache_key(prefix="fixture", suffix=str(fixture_id)))


async def set_cached_fixture(fixture_id: int, data: dict[str, Any], *, live: bool) -> None:
    ttl = api_settings.cache_ttl_live_s if live else api_settings.cache_ttl_historical_s
    await cache_set(_cache_key(prefix="fixture", suffix=str(fixture_id)), data, ttl)


async def get_cached_live_fixtures() -> Optional[list[dict[str, Any]]]:
    data = await cache_get(_cache_key(prefix="fixtures:live"))
    return data  # type: ignore[return-value]


async def set_cached_live_fixtures(data: list[dict[str, Any]]) -> None:
    await cache_set(_cache_key(prefix="fixtures:live"), data, api_settings.cache_ttl_live_s)


async def get_cached_leagues() -> Optional[list[dict[str, Any]]]:
    data = await cache_get(_cache_key(prefix="leagues"))
    return data  # type: ignore[return-value]


async def set_cached_leagues(data: list[dict[str, Any]]) -> None:
    await cache_set(_cache_key(prefix="leagues"), data, api_settings.cache_ttl_leagues_s)


async def get_cached_fixtures_by_date(date_str: str) -> Optional[list[dict[str, Any]]]:
    data = await cache_get(_cache_key(prefix="fixtures:date", suffix=date_str))
    return data  # type: ignore[return-value]


async def set_cached_fixtures_by_date(date_str: str, data: list[dict[str, Any]]) -> None:
    await cache_set(
        _cache_key(prefix="fixtures:date", suffix=date_str),
        data,
        api_settings.cache_ttl_fixtures_date_s,
    )

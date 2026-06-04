"""Async HTTP client wrapper for API-Football v3 with built-in rate limiting and robust error handling."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Generic, TypeVar

import httpx

from ingestion.config import settings

logger = logging.getLogger(__name__)

ResponseT = TypeVar("ResponseT")


class RateLimiter:
    """Simple sliding-window rate limiter.

    Tracks request timestamps and sleeps if the current window would exceed
    the configured requests-per-second threshold.
    """

    def __init__(self, max_rps: float) -> None:
        self._max_rps = max_rps
        self._window_s = 1.0
        self._max_requests = int(max_rps) if max_rps >= 1 else 1
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Block until a request slot is available."""
        now = asyncio.get_event_loop().time()
        async with self._lock:
            # Purge timestamps outside the current window
            cutoff = now - self._window_s
            self._timestamps = [t for t in self._timestamps if t > cutoff]

            if len(self._timestamps) >= self._max_requests:
                sleep_for = self._timestamps[0] + self._window_s - now
                if sleep_for > 0:
                    logger.debug("Rate limit reached; sleeping %.2f s", sleep_for)
                    await asyncio.sleep(sleep_for)
                # Recalculate after sleep
                now = asyncio.get_event_loop().time()
                cutoff = now - self._window_s
                self._timestamps = [t for t in self._timestamps if t > cutoff]

            self._timestamps.append(now)


class ApiFootballClientError(Exception):
    """Base exception for API-Football client errors."""


class ApiFootballClient(Generic[ResponseT]):
    """Async HTTP client for the API-Football v3 API.

    Usage::

        async with ApiFootballClient(api_key="...") as client:
            leagues = await client.get("/leagues", params={"current": "true"})
    """

    BASE_URL: str = settings.api_base_url
    REQUEST_TIMEOUT_S: int = settings.api_request_timeout_s

    def __init__(self, api_key: str, max_rps: float = settings.api_rate_limit_rps) -> None:
        self._api_key = api_key
        self._client: httpx.AsyncClient | None = None
        self._rate_limiter = RateLimiter(max_rps)

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------
    async def __aenter__(self) -> ApiFootballClient:
        headers = {
            "x-apisports-key": self._api_key,
            "Accept": "application/json",
        }
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers=headers,
            timeout=httpx.Timeout(self.REQUEST_TIMEOUT_S, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=20),
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Client not started; use 'async with ApiFootballClient(...)'")
        return self._client

    # ----------------------------------------------------------------
    # Public helpers
    # ----------------------------------------------------------------
    async def request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Send a signed request, respecting rate limits.

        Raises:
            ApiFootballClientError: on HTTP errors, timeouts, or malformed responses.
        """
        await self._rate_limiter.acquire()
        url = endpoint.lstrip("/")

        try:
            response = await self.client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise ApiFootballClientError(
                f"Request timeout [{method} {url}]: {exc}"
            ) from exc
        except httpx.TransportError as exc:
            raise ApiFootballClientError(
                f"Transport error [{method} {url}]: {exc}"
            ) from exc

        # --- Status-code handling ---
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "60")
            logger.warning("429 rate-limited; sleeping %s s", retry_after)
            await asyncio.sleep(int(retry_after))
            return await self.request(method, endpoint, **kwargs)  # retry once

        if response.status_code == 403:
            raise ApiFootballClientError("403 Forbidden — check your API key.")

        if response.status_code >= 500:
            raise ApiFootballClientError(
                f"API server error [{response.status_code}] {method} {url}"
            )

        # --- Parse JSON ---
        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise ApiFootballClientError(f"Non-JSON response: {exc}") from exc

        # API-Football wraps results in { "get": ..., "parameters": ..., "results": N, "response": [...] }
        return payload

    async def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Convenience wrapper for GET requests."""
        return await self.request("GET", endpoint, params=params)

    # ----------------------------------------------------------------
    # Domain-specific API methods
    # ----------------------------------------------------------------
    async def fetch_leagues(self, *, current: bool = True) -> list[dict[str, Any]]:
        """Fetch all leagues (optionally only current ones)."""
        payload = await self.get("/leagues", params={"current": "true" if current else "false"})
        return payload.get("response", [])

    async def fetch_seasons(self) -> list[int]:
        """Fetch list of available season years."""
        payload = await self.get("/leagues/seasons")
        return payload.get("response", [])

    async def fetch_league_teams(self, league_id: int, season: int) -> list[dict[str, Any]]:
        """Fetch teams participating in a given league/season."""
        payload = await self.get(
            "/teams",
            params={"league": league_id, "season": season},
        )
        return payload.get("response", [])

    async def fetch_fixtures(
        self,
        *,
        league_id: int | None = None,
        season: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        status: str | None = None,
        ids: str | None = None,
        live: str | None = "all",
    ) -> list[dict[str, Any]]:
        """Fetch fixtures matching the given filters.

        Supports the ``live=all`` shortcut to get all currently in-play fixtures.
        """
        params: dict[str, Any] = {}
        if league_id is not None:
            params["league"] = league_id
        if season is not None:
            params["season"] = season
        if date_from is not None:
            params["from"] = date_from
        if date_to is not None:
            params["to"] = date_to
        if status is not None:
            params["status"] = status
        if ids is not None:
            params["ids"] = ids
        if live is not None:
            params["live"] = live

        payload = await self.get("/fixtures", params=params or None)
        return payload.get("response", [])

    async def fetch_fixture_lineups(self, fixture_id: int) -> list[dict[str, Any]]:
        """Fetch lineups & formation for a single fixture."""
        payload = await self.get("/fixtures/lineups", params={"fixture": fixture_id})
        return payload.get("response", [])

    async def fetch_live_fixtures(self) -> list[dict[str, Any]]:
        """Shorthand to get all currently live fixtures."""
        return await self.fetch_fixtures(live="all")

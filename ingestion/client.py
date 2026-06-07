"""Async HTTP client wrapper for the Scorebat v3 API with rate limiting and error handling."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from ingestion.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple sliding-window rate limiter.

    Tracks request timestamps and sleeps if the current window would exceed
    the configured requests-per-second threshold.
    """

    def __init__(self, max_rps: float) -> None:
        self._max_rps = max_rps
        self._window_s = 1.0
        self._max_requests = max(int(max_rps), 1) if max_rps >= 0.1 else 1
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


class ScorebatClientError(Exception):
    """Base exception for Scorebat client errors."""


class ScorebatClient:
    """Async HTTP client for the Scorebat v3 API.

    Scorebat is a football data provider that returns match information,
    scores, and video highlights.

    Usage::

        async with ScorebatClient(token="...") as client:
            matches = await client.fetch_matches()
    """

    BASE_URL: str = settings.api_base_url.rstrip("/")
    REQUEST_TIMEOUT_S: int = settings.api_request_timeout_s

    def __init__(self, token: str, max_rps: float = settings.api_rate_limit_rps) -> None:
        self._token = token
        self._client: httpx.AsyncClient | None = None
        self._rate_limiter = RateLimiter(max_rps)

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------
    async def __aenter__(self) -> ScorebatClient:
        headers = {
            "Accept": "application/json",
            "User-Agent": "KEEM-SportsDB/1.0",
        }
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers=headers,
            timeout=httpx.Timeout(self.REQUEST_TIMEOUT_S, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=3, max_connections=10),
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Client not started; use 'async with ScorebatClient(...)'")
        return self._client

    # ----------------------------------------------------------------
    # Generic request
    # ----------------------------------------------------------------
    async def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Send a GET request with the API token attached.

        Scorebat authenticates via ``?token=...`` query parameter on every request.
        """
        await self._rate_limiter.acquire()

        request_params = dict(params or {})
        request_params["token"] = self._token

        url = endpoint.lstrip("/")

        # Log the actual full URL for debugging
        req = self.client.build_request("GET", url, params=request_params)
        logger.info("Scorebat request URL: %s", req.url)

        try:
            response = await self.client.get(url, params=request_params)
        except httpx.TimeoutException as exc:
            raise ScorebatClientError(f"Request timeout [{url}]: {exc}") from exc
        except httpx.TransportError as exc:
            raise ScorebatClientError(f"Transport error [{url}]: {exc}") from exc

        # --- Status-code handling ---
        if response.status_code == 429:
            logger.warning("429 rate-limited; sleeping 30 s...")
            await asyncio.sleep(30)
            return await self._get(endpoint, params)  # retry once

        if response.status_code == 403:
            raise ScorebatClientError("403 Forbidden — check your Scorebat token.")

        if response.status_code >= 500:
            raise ScorebatClientError(
                f"Server error [{response.status_code}] {url}"
            )

        # --- Debug: log response info on failure ---
        content_type = response.headers.get("content-type", "")
        logger.debug("Scorebat response: %s %s [%s]", response.status_code, content_type, url)

        # --- Parse JSON ---
        if response.status_code == 204 or not response.content:
            raise ScorebatClientError(f"Empty response ({response.status_code}) from {url}")

        if "application/json" not in content_type and response.status_code >= 400:
            preview = response.text[:300]
            raise ScorebatClientError(
                f"HTTP {response.status_code} (non-JSON) from {url}: {preview}"
            )

        try:
            return response.json()
        except ValueError as exc:
            preview = response.text[:300]
            raise ScorebatClientError(
                f"Non-JSON response ({response.status_code}) from {url}: {preview}"
            ) from exc

    # ----------------------------------------------------------------
    # Domain-specific API methods
    # ----------------------------------------------------------------
    async def fetch_matches(
        self,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all matches from Scorebat, optionally filtered by date range.

        Scorebat's ``/matches`` endpoint returns matches with video highlights.
        It can be filtered by:
        - ``from`` / ``to`` — date range (``YYYY-MM-DD``)

        The response is a JSON array of match objects.
        """
        params: dict[str, Any] = {}
        if date_from is not None:
            params["from"] = date_from
        if date_to is not None:
            params["to"] = date_to

        payload = await self._get("/matches", params=params)

        # Scorebat returns a JSON array directly, or sometimes wrapped
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            # Some versions wrap in {"response": [...]} or {"data": [...]}
            return payload.get("response", payload.get("data", []))
        return []

    async def fetch_matches_by_date(self, date: str) -> list[dict[str, Any]]:
        """Convenience: fetch matches for a single date."""
        return await self.fetch_matches(date_from=date, date_to=date)

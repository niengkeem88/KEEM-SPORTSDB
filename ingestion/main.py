"""Async orchestrator entrypoint for the Scorebat v3 ingestion service.

Launches three concurrent workers:

- ``weekly_fixtures`` — daily sync of upcoming match schedules.
- ``pre_match_lineups`` — runs every 60 s, dispatches lineup fetches for
  fixtures whose kick-off is within the 45-minute window.
- ``live_engine`` — polls active matches every 60 s, updating scores and
  overwriting the JSONB event cache.

Run::

    $ python -m ingestion.main
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from collections.abc import Awaitable, Callable
from typing import NoReturn

from ingestion.client import ScorebatClient
from ingestion.config import settings
from ingestion.database import AsyncSessionFactory, dispose_db, init_db
from ingestion.workers import (
    live_engine_polling,
    sync_pre_match_lineups,
    sync_weekly_fixtures,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        stream=sys.stdout,
    )
    # Quiet noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Shutdown helpers
# ---------------------------------------------------------------------------

_shutdown_event = asyncio.Event()


def _handle_signal(signum: int, _frame: object) -> None:
    logger.info("Received signal %d; shutting down gracefully...", signum)
    _shutdown_event.set()


def _register_signals() -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except (ValueError, OSError):
            pass  # Not all signals are available on every platform


# ---------------------------------------------------------------------------
# Periodic runner helper
# ---------------------------------------------------------------------------

async def run_periodic(
    name: str,
    interval_s: int,
    work: Callable[[ScorebatClient], Awaitable[None]],
    client: ScorebatClient,
) -> NoReturn:
    """Execute *work* immediately, then every *interval_s* seconds until shutdown."""
    logger.info("%s worker started (interval=%ds).", name, interval_s)
    while not _shutdown_event.is_set():
        try:
            async with AsyncSessionFactory() as session:
                await work(client, session)
        except Exception:
            logger.exception("%s worker encountered an unhandled error; will retry.", name)
        # Wait for the interval or until shutdown is signalled
        try:
            await asyncio.wait_for(
                _shutdown_event.wait(),
                timeout=interval_s,
            )
            break  # Shutdown requested
        except asyncio.TimeoutError:
            continue  # Interval elapsed; run again

    logger.info("%s worker exiting.", name)


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

async def amain() -> None:
    _configure_logging()
    _register_signals()

    logger.info("Initialising database...")
    await init_db()

        token = settings.api_key
        if not token:
        logger.error("SCOREBAT_TOKEN not set. Set it in the environment or config.")
        sys.exit(1)

        async with ScorebatClient(token) as client:
        logger.info(
            "Starting ingestion service — weekly interval=%ds, "
            "pre-match window=%ds, live poll interval=%ds.",
            settings.weekly_fixtures_interval_s,
            settings.pre_match_lineups_window_s,
            settings.live_engine_poll_s,
        )

        # Launch three workers concurrently
        workers = [
            asyncio.create_task(
                run_periodic(
                    "weekly_fixtures",
                    settings.weekly_fixtures_interval_s,
                    sync_weekly_fixtures,
                    client,
                )
            ),
            asyncio.create_task(
                run_periodic(
                    "pre_match_lineups",
                    settings.pre_match_lineups_window_s,
                    sync_pre_match_lineups,
                    client,
                )
            ),
            asyncio.create_task(
                run_periodic(
                    "live_engine",
                    settings.live_engine_poll_s,
                    live_engine_polling,
                    client,
                )
            ),
        ]

        # Block until a shutdown signal is received
        await _shutdown_event.wait()

        logger.info("Shutting down workers...")
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    await dispose_db()
    logger.info("Ingestion service stopped.")


def main() -> None:
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()

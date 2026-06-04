"""Database engine, async session factory, and upsert engine for PostgreSQL."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, TypeVar

from sqlalchemy import Dialect
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.sql import ColumnCollection

from ingestion.config import settings
from ingestion.models import (
    Base,
    Fixture,
    League,
    Season,
    Standing,
    Team,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine & session factory
# ---------------------------------------------------------------------------

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    echo=False,
    future=True,
)

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all tables defined by ORM models (idempotent — uses IF NOT EXISTS)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured.")


async def dispose_db() -> None:
    """Dispose of the connection pool (graceful shutdown)."""
    await engine.dispose()


# ---------------------------------------------------------------------------
# Generic upsert helpers
# ---------------------------------------------------------------------------

ModelT = TypeVar("ModelT", League, Season, Team, Fixture, Standing)


def _conflict_target(model: type[ModelT]) -> ColumnCollection | None:
    """Return the conflict-target columns for upsert based on model type.

    For tables whose PK is the external API id, we use the PK column.
    For ``Standing`` the unique constraint is (season_id, team_id).
    """
    if model is Standing:
        return Standing.__table__.uq_standings_season_team.columns  # type: ignore[union-attr]
    # All other tables use their single-column PK (the API provider id).
    pk = model.__table__.primary_key
    if pk is not None and len(pk.columns) == 1:
        return pk.columns
    msg = f"Upsert conflict target not defined for {model.__name__}"
    raise ValueError(msg)


def build_upsert_stmt(model: type[ModelT], values: list[dict[str, Any]]) -> Any:
    """Build an ``INSERT … ON CONFLICT DO UPDATE`` statement.

    Parameters
    ----------
    model
        The ORM model class (e.g. ``Fixture``).
    values
        List of row dicts keyed by column names.

    Returns
    -------
    A SQLAlchemy ``Insert`` statement with ``on_conflict_do_update`` attached.
    """
    stmt = pg_insert(model).values(values)

    target = _conflict_target(model)

    # Columns to exclude from the update half of the upsert
    # (created_at should only ever be set once)
    exclude = {"created_at", "id"}

    update_dict = {
        col.name: getattr(stmt.excluded, col.name)
        for col in model.__table__.columns
        if col.name not in exclude and col.name not in target
    }

    stmt = stmt.on_conflict_do_update(
        constraint=target,
        set_=update_dict,
    )
    return stmt


async def upsert_rows(
    session: AsyncSession,
    model: type[ModelT],
    rows: list[dict[str, Any]],
    *,
    commit: bool = True,
) -> int:
    """Insert or update a batch of rows for the given *model*.

    Returns the number of rows affected.
    """
    if not rows:
        return 0

    stmt = build_upsert_stmt(model, rows)
    result = await session.execute(stmt)
    rowcount = result.rowcount if result.rowcount is not None else len(rows)

    if commit:
        await session.commit()

    logger.debug("Upserted %d rows into %s", rowcount, model.__tablename__)
    return rowcount


# ---------------------------------------------------------------------------
# Convenience upsert functions (one per domain model)
# ---------------------------------------------------------------------------

async def upsert_leagues(session: AsyncSession, rows: list[dict[str, Any]]) -> int:
    return await upsert_rows(session, League, rows)


async def upsert_seasons(session: AsyncSession, rows: list[dict[str, Any]]) -> int:
    return await upsert_rows(session, Season, rows)


async def upsert_teams(session: AsyncSession, rows: list[dict[str, Any]]) -> int:
    return await upsert_rows(session, Team, rows)


async def upsert_fixtures(session: AsyncSession, rows: list[dict[str, Any]]) -> int:
    return await upsert_rows(session, Fixture, rows)


async def upsert_standings(session: AsyncSession, rows: list[dict[str, Any]]) -> int:
    return await upsert_rows(session, Standing, rows)

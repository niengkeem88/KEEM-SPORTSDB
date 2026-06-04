"""Async SQLAlchemy engine & session dependency for FastAPI."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from api.config import api_settings

# Read-optimised connection pool — larger pool size, longer timeout
engine = create_async_engine(
    api_settings.database_url,
    pool_size=api_settings.db_pool_size,
    max_overflow=api_settings.db_max_overflow,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False,
)

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session.

    The session is automatically closed when the request finishes.
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
        finally:
            await session.close()


async def dispose_db() -> None:
    """Gracefully close the connection pool (called on app shutdown)."""
    await engine.dispose()

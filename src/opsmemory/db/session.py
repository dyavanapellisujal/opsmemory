"""Async database engine and session factory management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from opsmemory.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Create the application's async database engine.

    Args:
        settings: Application settings providing the database URL.
    """
    return create_async_engine(
        settings.database_url,
        echo=settings.database_echo,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to the given engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Provide a transactional session scope.

    Commits on success, rolls back on error, and always closes the session.
    """
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

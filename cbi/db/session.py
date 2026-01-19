"""
Async database session management for CBI.

Provides:
- Async engine creation
- AsyncSession factory
- Context manager for sessions
- Lifecycle functions for app startup/shutdown
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from cbi.config import get_logger, get_settings

settings = get_settings()
logger = get_logger(__name__)

# Global engine and session factory
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """
    Get the async database engine.

    Returns:
        AsyncEngine instance.

    Raises:
        RuntimeError: If database has not been initialized.
    """
    if _engine is None:
        raise RuntimeError(
            "Database not initialized. Call init_db() first."
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Get the async session factory.

    Returns:
        async_sessionmaker instance.

    Raises:
        RuntimeError: If database has not been initialized.
    """
    if _async_session_factory is None:
        raise RuntimeError(
            "Database not initialized. Call init_db() first."
        )
    return _async_session_factory


async def init_db(
    *,
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_pre_ping: bool = True,
    echo: bool = False,
) -> None:
    """
    Initialize the database engine and session factory.

    Should be called during application startup.

    Args:
        pool_size: Number of connections to keep in the pool.
        max_overflow: Maximum overflow connections above pool_size.
        pool_pre_ping: Test connections before use.
        echo: Log all SQL statements (debug only).
    """
    global _engine, _async_session_factory

    if _engine is not None:
        logger.warning("Database already initialized, skipping")
        return

    database_url = settings.database_url.get_secret_value()

    # Create async engine
    _engine = create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=pool_pre_ping,
        echo=echo if settings.is_development else False,
    )

    # Create session factory
    _async_session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    logger.info(
        "Database initialized",
        pool_size=pool_size,
        max_overflow=max_overflow,
    )


async def close_db() -> None:
    """
    Close the database engine and clean up connections.

    Should be called during application shutdown.
    """
    global _engine, _async_session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        logger.info("Database connection closed")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database sessions.

    Automatically handles commit on success and rollback on error.

    Yields:
        AsyncSession instance.

    Example:
        async with get_session() as session:
            result = await session.execute(select(Report))
            reports = result.scalars().all()
    """
    factory = get_session_factory()
    session = factory()

    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_session_dependency() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database sessions.

    Use with Depends() in route handlers.

    Yields:
        AsyncSession instance.

    Example:
        @app.get("/reports")
        async def get_reports(session: AsyncSession = Depends(get_session_dependency)):
            result = await session.execute(select(Report))
            return result.scalars().all()
    """
    async with get_session() as session:
        yield session


async def execute_raw(sql: str, params: dict[str, Any] | None = None) -> Any:
    """
    Execute raw SQL statement.

    Args:
        sql: SQL statement to execute.
        params: Optional parameters for the statement.

    Returns:
        Result of the execution.
    """
    from sqlalchemy import text

    async with get_session() as session:
        result = await session.execute(text(sql), params or {})
        return result


async def health_check() -> bool:
    """
    Check database connectivity.

    Returns:
        True if database is accessible, False otherwise.
    """
    try:
        await execute_raw("SELECT 1")
        return True
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return False

"""Database connection and session management."""

from collections.abc import AsyncGenerator
from typing import Any

from event_logging import setup_db_logging
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config.settings import settings

# Lazy initialization - only create engine when needed
_async_engine: AsyncEngine | None = None
_AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None


def _init_engine() -> None:
    """Initialize the async engine and session maker."""
    global _async_engine, _AsyncSessionLocal
    if _async_engine is None:
        database_url = settings.DATABASE_URL

        engine_kwargs: dict[str, Any] = {"echo": False}
        if "postgresql" in database_url or "postgres" in database_url:
            engine_kwargs.update(
                {
                    "pool_size": 20,
                    "max_overflow": 30,
                    "pool_timeout": 30,
                    "pool_recycle": 1800,
                    "pool_pre_ping": True,
                }
            )

        _async_engine = create_async_engine(database_url, **engine_kwargs)
        if "postgresql" in database_url or "postgres" in database_url:
            setup_db_logging(_async_engine, service_name=settings.SERVICE_NAME)
        _AsyncSessionLocal = async_sessionmaker(
            bind=_async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )


def get_async_engine() -> AsyncEngine:
    """Get or create the async database engine (public API)."""
    _init_engine()
    return _async_engine  # type: ignore[return-value]


# Initialize on first access
def __getattr__(name: str) -> Any:
    """Lazy attribute access for backward compatibility."""
    if name == "async_engine":
        _init_engine()
        return _async_engine
    if name == "AsyncSessionLocal":
        _init_engine()
        return _AsyncSessionLocal
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


async def get_db_session() -> AsyncGenerator[AsyncSession | Any, Any]:
    """Yields the async database session."""
    _init_engine()
    async with _AsyncSessionLocal() as session:  # type: ignore[misc]
        yield session

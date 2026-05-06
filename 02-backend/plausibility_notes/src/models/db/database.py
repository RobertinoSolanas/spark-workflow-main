"""Database connection and session management."""

from collections.abc import AsyncGenerator
from typing import Any

from event_logging import setup_db_logging
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config.settings import settings

async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=5,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
)

setup_db_logging(async_engine, service_name=settings.SERVICE_NAME)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession | Any, Any]:
    """Yields the async database session."""
    async with AsyncSessionLocal() as session:
        yield session

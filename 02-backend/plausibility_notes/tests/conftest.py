"""Test configuration and fixtures."""

import os

_TEST_ENV_VARS = {
    "CORS_ORIGINS": "http://localhost",
    "DB_USER": "test",
    "DB_PASSWORD": "test",
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
    "DB_NAME": "test_db",
    "SERVICE_NAME": "plausibility-notes-test",
    "DOCUMENT_MANAGEMENT_SERVICE_URL": "http://localhost:8000",
}
for key, value in _TEST_ENV_VARS.items():
    os.environ.setdefault(key, value)

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from src.models.db_models import Base

IN_MEMORY_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def async_engine() -> AsyncIterator[AsyncEngine]:
    """Create an in-memory SQLite engine for tests."""
    engine = create_async_engine(
        IN_MEMORY_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def session_factory(
    async_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Return a session factory bound to the in-memory engine."""
    return async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Provide an async session for tests."""
    async with session_factory() as session:
        yield session

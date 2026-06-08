from collections.abc import AsyncIterator

import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("pytest_asyncio")
pytest.importorskip("sqlalchemy")

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """A fresh in-memory SQLite session with the full schema (no Postgres required)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()

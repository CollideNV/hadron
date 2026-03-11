"""Tests for the database engine factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import sessionmaker

from hadron.db.engine import create_engine, create_session_factory


class TestCreateEngine:
    def test_returns_async_engine(self) -> None:
        engine = create_engine("postgresql+asyncpg://user:pass@localhost/db")
        assert isinstance(engine, AsyncEngine)
        assert engine.pool.size() == 5

    def test_pool_pre_ping_enabled(self) -> None:
        engine = create_engine("postgresql+asyncpg://user:pass@localhost/db")
        assert engine.pool._pre_ping is True


class TestCreateSessionFactory:
    def test_returns_session_factory(self) -> None:
        engine = create_engine("postgresql+asyncpg://user:pass@localhost/db")
        factory = create_session_factory(engine)
        assert isinstance(factory, sessionmaker)

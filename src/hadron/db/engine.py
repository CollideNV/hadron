"""Async SQLAlchemy engine factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


def create_engine(postgres_url: str) -> AsyncEngine:
    """Create an async SQLAlchemy engine.

    Args:
        postgres_url: Async postgres URL (postgresql+asyncpg://...).
    """
    return create_async_engine(
        postgres_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> sessionmaker:
    """Create an async session factory."""
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

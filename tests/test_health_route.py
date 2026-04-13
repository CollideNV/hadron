"""Tests for health check routes."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from hadron.controller.routes.health import router


def _make_app(session_factory=None, redis=None) -> FastAPI:
    app = FastAPI(version="0.1.0")
    app.include_router(router)
    app.state.session_factory = session_factory
    app.state.redis = redis
    return app


class TestLivez:
    @pytest.mark.asyncio
    async def test_returns_ok(self) -> None:
        app = _make_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/livez")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestHealthz:
    @pytest.mark.asyncio
    async def test_returns_version_and_uptime(self) -> None:
        app = _make_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/healthz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["version"] == "0.1.0"
        assert isinstance(body["uptime"], (int, float))
        assert body["uptime"] >= 0


class TestReadyz:
    @pytest.mark.asyncio
    async def test_ready_when_both_healthy(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock()

        @asynccontextmanager
        async def session_factory():
            yield session

        redis = AsyncMock()
        redis.ping = AsyncMock()

        app = _make_app(session_factory=session_factory, redis=redis)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/readyz")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["checks"]["postgres"] is True
        assert body["checks"]["redis"] is True

    @pytest.mark.asyncio
    async def test_not_ready_when_postgres_fails(self) -> None:
        @asynccontextmanager
        async def session_factory():
            session = AsyncMock()
            session.execute = AsyncMock(side_effect=ConnectionError("pg down"))
            yield session

        redis = AsyncMock()
        redis.ping = AsyncMock()

        app = _make_app(session_factory=session_factory, redis=redis)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/readyz")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["postgres"] is False
        assert body["checks"]["redis"] is True

    @pytest.mark.asyncio
    async def test_not_ready_when_redis_fails(self) -> None:
        @asynccontextmanager
        async def session_factory():
            yield AsyncMock()

        redis = AsyncMock()
        redis.ping = AsyncMock(side_effect=ConnectionError("redis down"))

        app = _make_app(session_factory=session_factory, redis=redis)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/readyz")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["postgres"] is True
        assert body["checks"]["redis"] is False

    @pytest.mark.asyncio
    async def test_not_ready_when_both_fail(self) -> None:
        @asynccontextmanager
        async def session_factory():
            session = AsyncMock()
            session.execute = AsyncMock(side_effect=ConnectionError("pg down"))
            yield session

        redis = AsyncMock()
        redis.ping = AsyncMock(side_effect=ConnectionError("redis down"))

        app = _make_app(session_factory=session_factory, redis=redis)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/readyz")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["postgres"] is False
        assert body["checks"]["redis"] is False

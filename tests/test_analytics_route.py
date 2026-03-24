"""Tests for analytics API routes."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from hadron.controller.routes.analytics import router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(session_factory) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.session_factory = session_factory
    return app


def _build_factory(rows):
    """Build a mock session factory where execute returns rows via .all()."""
    result_mock = MagicMock()
    result_mock.all.return_value = rows
    # Make result iterable (used by analytics_cost repo branch)
    result_mock.__iter__ = MagicMock(return_value=iter(rows))

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)

    @asynccontextmanager
    async def factory():
        yield session

    return factory, session


# ---------------------------------------------------------------------------
# GET /api/analytics/summary
# ---------------------------------------------------------------------------


class TestAnalyticsSummary:
    @pytest.mark.asyncio
    async def test_empty_db(self):
        factory, _ = _build_factory([])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/analytics/summary")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_runs"] == 0
        assert body["status_counts"] == {}
        assert body["success_rate"] == 0
        assert body["total_cost_usd"] == 0
        assert body["avg_cost_usd"] == 0

    @pytest.mark.asyncio
    async def test_mixed_statuses(self):
        rows = [
            SimpleNamespace(status="completed", cnt=5, cost=2.5),
            SimpleNamespace(status="failed", cnt=2, cost=0.8),
        ]
        factory, _ = _build_factory(rows)
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/analytics/summary")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_runs"] == 7
        assert body["status_counts"] == {"completed": 5, "failed": 2}
        assert body["success_rate"] == pytest.approx(5 / 7)
        assert body["total_cost_usd"] == pytest.approx(3.3)
        assert body["avg_cost_usd"] == pytest.approx(3.3 / 7, abs=1e-4)

    @pytest.mark.asyncio
    async def test_days_param(self):
        factory, session = _build_factory([])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/analytics/summary?days=7")

        assert resp.status_code == 200
        session.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# GET /api/analytics/cost
# ---------------------------------------------------------------------------


class TestAnalyticsCost:
    @pytest.mark.asyncio
    async def test_group_by_repo(self):
        rows = [
            SimpleNamespace(repo_name="acme-api", cost_usd=0.5, runs=3),
            SimpleNamespace(repo_name="acme-web", cost_usd=1.2, runs=7),
        ]
        factory, _ = _build_factory(rows)
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/analytics/cost?group_by=repo")

        assert resp.status_code == 200
        body = resp.json()
        assert body["group_by"] == "repo"
        assert body["total_cost_usd"] == pytest.approx(1.7)
        assert len(body["groups"]) == 2
        assert body["groups"][0]["key"] == "acme-api"
        assert body["groups"][0]["cost_usd"] == pytest.approx(0.5)
        assert body["groups"][0]["runs"] == 3
        assert body["groups"][1]["key"] == "acme-web"

    @pytest.mark.asyncio
    async def test_group_by_stage_stub(self):
        factory, _ = _build_factory([])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/analytics/cost?group_by=stage")

        assert resp.status_code == 200
        body = resp.json()
        assert body["group_by"] == "stage"
        assert body["groups"] == []
        assert body["total_cost_usd"] == 0

    @pytest.mark.asyncio
    async def test_empty_results(self):
        factory, _ = _build_factory([])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/analytics/cost?group_by=repo")

        assert resp.status_code == 200
        body = resp.json()
        assert body["groups"] == []
        assert body["total_cost_usd"] == 0

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


def _build_factory(rows, summary_rows=None):
    """Build a mock session factory.

    The summary endpoint now makes two execute() calls:
      1. CRRun status/cost aggregation -> rows via .all()
      2. RunSummary query -> summary_rows via .scalars().all()
    """
    if summary_rows is None:
        summary_rows = []

    # First call: CRRun aggregation
    cr_result = MagicMock()
    cr_result.all.return_value = rows

    # Second call: RunSummary query
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = summary_rows
    summary_result = MagicMock()
    summary_result.scalars.return_value = scalars_mock

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[cr_result, summary_result])

    @asynccontextmanager
    async def factory():
        yield session

    return factory, session


def _build_simple_factory(rows):
    """Build a factory for endpoints that do a single query (e.g., cost by repo)."""
    result_mock = MagicMock()
    result_mock.all.return_value = rows

    # Also support .scalars().all() for RunSummary queries
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = rows
    result_mock.scalars.return_value = scalars_mock

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
        assert body["stage_durations"] == []
        assert body["daily_stats"] == []

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
    async def test_days_validation_rejects_zero(self):
        factory, _ = _build_factory([])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/analytics/summary?days=0")

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_days_validation_rejects_over_365(self):
        factory, _ = _build_factory([])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/analytics/summary?days=366")

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_full_success_rate(self):
        rows = [SimpleNamespace(status="completed", cnt=10, cost=5.0)]
        factory, _ = _build_factory(rows)
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/analytics/summary")

        body = resp.json()
        assert body["success_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_zero_success_rate(self):
        rows = [SimpleNamespace(status="failed", cnt=3, cost=1.0)]
        factory, _ = _build_factory(rows)
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/analytics/summary")

        body = resp.json()
        assert body["success_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_stage_durations_from_summaries(self):
        """When RunSummary records exist, stage_durations are computed."""
        import datetime

        summary = SimpleNamespace(
            stage_timings={
                "intake": {"stage": "intake", "duration_s": 5.0},
                "implementation": {"stage": "implementation", "duration_s": 50.0},
            },
            started_at=datetime.datetime(2026, 3, 20, tzinfo=datetime.timezone.utc),
            completed_at=datetime.datetime(2026, 3, 20, 0, 1, tzinfo=datetime.timezone.utc),
            total_cost_usd=1.0,
            total_input_tokens=1000,
            total_output_tokens=500,
            final_status="completed",
            created_at=datetime.datetime(2026, 3, 20, tzinfo=datetime.timezone.utc),
        )
        rows = [SimpleNamespace(status="completed", cnt=1, cost=1.0)]
        factory, _ = _build_factory(rows, summary_rows=[summary])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/analytics/summary")

        body = resp.json()
        assert len(body["stage_durations"]) == 2
        stage_names = [s["stage"] for s in body["stage_durations"]]
        assert "intake" in stage_names
        assert "implementation" in stage_names


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
        factory, _ = _build_simple_factory(rows)
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
    async def test_group_by_stage_empty(self):
        factory, _ = _build_simple_factory([])
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
        factory, _ = _build_simple_factory([])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/analytics/cost?group_by=repo")

        assert resp.status_code == 200
        body = resp.json()
        assert body["groups"] == []
        assert body["total_cost_usd"] == 0

    @pytest.mark.asyncio
    async def test_group_by_model_empty(self):
        factory, _ = _build_simple_factory([])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/analytics/cost?group_by=model")

        assert resp.status_code == 200
        body = resp.json()
        assert body["group_by"] == "model"
        assert body["groups"] == []
        assert body["total_cost_usd"] == 0

    @pytest.mark.asyncio
    async def test_group_by_day_empty(self):
        factory, _ = _build_simple_factory([])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/analytics/cost?group_by=day")

        assert resp.status_code == 200
        body = resp.json()
        assert body["group_by"] == "day"
        assert body["groups"] == []
        assert body["total_cost_usd"] == 0

    @pytest.mark.asyncio
    async def test_invalid_group_by_rejected(self):
        factory, _ = _build_simple_factory([])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/analytics/cost?group_by=invalid")

        assert resp.status_code == 422

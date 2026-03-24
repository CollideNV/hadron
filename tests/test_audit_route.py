"""Tests for audit log API route."""

from __future__ import annotations

import datetime
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from hadron.controller.routes.audit import router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(session_factory) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.session_factory = session_factory
    return app


def _make_entry(id: int, action: str, cr_id: str | None = None, details: dict | None = None):
    return SimpleNamespace(
        id=id,
        cr_id=cr_id,
        action=action,
        details=details or {},
        timestamp=datetime.datetime(2026, 3, 17, 9, 0, 0, tzinfo=datetime.timezone.utc),
    )


def _build_factory(scalars_list, count: int = 0):
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = scalars_list

    mock_count_result = MagicMock()
    mock_count_result.scalar_one.return_value = count

    mock_query_result = MagicMock()
    mock_query_result.scalars.return_value = mock_scalars

    mock_session = AsyncMock()
    # First call: count query, second call: data query
    mock_session.execute = AsyncMock(side_effect=[mock_count_result, mock_query_result])

    @asynccontextmanager
    async def factory():
        yield mock_session

    return factory, mock_session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetAuditLog:
    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        factory, _ = _build_factory([], count=0)
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/audit-log")

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_returns_entries(self):
        entries = [
            _make_entry(1, "pipeline_triggered", cr_id="CR-001"),
            _make_entry(2, "model_settings_updated"),
        ]
        factory, _ = _build_factory(entries, count=2)
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/audit-log")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["items"][0]["action"] == "pipeline_triggered"
        assert data["items"][0]["cr_id"] == "CR-001"
        assert data["items"][1]["cr_id"] is None
        assert data["total"] == 2

    @pytest.mark.asyncio
    async def test_pagination_params_passed(self):
        factory, session = _build_factory([], count=0)
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/audit-log?page=2&page_size=10")

        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 2
        assert data["page_size"] == 10

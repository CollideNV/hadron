"""Tests for pipeline defaults API routes."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from hadron.controller.routes.settings import router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(session_factory) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.session_factory = session_factory
    return app


def _make_setting(key: str, value_json: dict):
    return SimpleNamespace(key=key, value_json=value_json)


def _build_factory_returning(scalars_list):
    mock_scalars = MagicMock()
    mock_scalars.__iter__ = lambda self: iter(scalars_list)

    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_result.scalar_one_or_none.return_value = scalars_list[0] if scalars_list else None

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result
    mock_session.add = MagicMock()

    @asynccontextmanager
    async def factory():
        yield mock_session

    return factory, mock_session


# ---------------------------------------------------------------------------
# GET /api/settings/pipeline-defaults
# ---------------------------------------------------------------------------


class TestGetPipelineDefaults:
    @pytest.mark.asyncio
    async def test_returns_hardcoded_defaults_when_no_db_row(self):
        factory, _ = _build_factory_returning([])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/settings/pipeline-defaults")

        assert resp.status_code == 200
        data = resp.json()
        assert data["max_verification_loops"] == 3
        assert data["max_review_dev_loops"] == 3
        assert data["max_cost_usd"] == 10.0
        assert data["delivery_strategy"] == "self_contained"
        assert data["agent_timeout"] == 300
        assert data["test_timeout"] == 120

    @pytest.mark.asyncio
    async def test_returns_db_values_when_present(self):
        custom = _make_setting("pipeline_defaults", {
            "max_verification_loops": 5,
            "max_review_dev_loops": 2,
            "max_cost_usd": 25.0,
            "default_backend": "openai",
            "default_model": "gpt-4o",
            "explore_model": "gpt-4o-mini",
            "plan_model": "gpt-4o",
            "delivery_strategy": "push_and_wait",
            "agent_timeout": 600,
            "test_timeout": 60,
        })
        factory, _ = _build_factory_returning([custom])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/settings/pipeline-defaults")

        assert resp.status_code == 200
        data = resp.json()
        assert data["max_cost_usd"] == 25.0
        assert data["delivery_strategy"] == "push_and_wait"
        assert data["default_model"] == "gpt-4o"


# ---------------------------------------------------------------------------
# PUT /api/settings/pipeline-defaults
# ---------------------------------------------------------------------------


class TestUpdatePipelineDefaults:
    @pytest.mark.asyncio
    async def test_creates_new_row_and_audit_log(self):
        factory, session = _build_factory_returning([])
        app = _make_app(factory)

        body = {
            "max_verification_loops": 5,
            "max_review_dev_loops": 4,
            "max_cost_usd": 20.0,
            "default_backend": "claude",
            "default_model": "claude-sonnet-4-6",
            "explore_model": "claude-haiku-4-5-20251001",
            "plan_model": "claude-opus-4-6",
            "delivery_strategy": "push_and_wait",
            "agent_timeout": 600,
            "test_timeout": 60,
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/settings/pipeline-defaults", json=body)

        assert resp.status_code == 200
        data = resp.json()
        assert data["max_cost_usd"] == 20.0
        assert data["delivery_strategy"] == "push_and_wait"
        # Two adds: PipelineSetting + AuditLog
        assert session.add.call_count == 2
        assert session.commit.called

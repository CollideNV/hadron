"""Tests for model settings API routes."""

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
    """Build a session factory mock returning scalars_list for queries."""
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
# GET /api/settings/models
# ---------------------------------------------------------------------------


class TestGetModelSettings:
    @pytest.mark.asyncio
    async def test_returns_defaults_when_no_db_rows(self):
        factory, _ = _build_factory_returning([])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/settings/models")

        assert resp.status_code == 200
        data = resp.json()
        assert data["default_backend"] == "claude"
        assert "implementation" in data["stages"]
        assert data["stages"]["implementation"]["explore"] is not None
        assert data["stages"]["implementation"]["plan"] is not None
        assert data["stages"]["intake"]["explore"] is None

    @pytest.mark.asyncio
    async def test_returns_db_values(self):
        settings = [
            _make_setting("default_backend", {"backend": "openai"}),
            _make_setting("stage_models", {
                "intake": {
                    "act": {"backend": "openai", "model": "gpt-4o"},
                    "explore": None,
                    "plan": None,
                },
            }),
        ]
        factory, _ = _build_factory_returning(settings)
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/settings/models")

        assert resp.status_code == 200
        data = resp.json()
        assert data["default_backend"] == "openai"
        assert data["stages"]["intake"]["act"]["backend"] == "openai"
        assert data["stages"]["intake"]["act"]["model"] == "gpt-4o"


# ---------------------------------------------------------------------------
# PUT /api/settings/models
# ---------------------------------------------------------------------------


class TestUpdateModelSettings:
    @pytest.mark.asyncio
    async def test_update_creates_entries(self):
        # First call returns no rows (for GET-like upsert), both scalar_one_or_none calls return None
        mock_session = AsyncMock()
        call_count = 0

        async def fake_execute(stmt):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            return mock_result

        mock_session.execute = fake_execute
        mock_session.add = MagicMock()

        @asynccontextmanager
        async def factory():
            yield mock_session

        app = _make_app(factory)

        payload = {
            "default_backend": "gemini",
            "stages": {
                "intake": {
                    "act": {"backend": "gemini", "model": "gemini-2.5-pro"},
                    "explore": None,
                    "plan": None,
                },
            },
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/settings/models", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["default_backend"] == "gemini"
        assert data["stages"]["intake"]["act"]["model"] == "gemini-2.5-pro"
        # Should have added: default_backend setting + stage_models setting + audit log = 3 adds
        assert mock_session.add.call_count == 3

    @pytest.mark.asyncio
    async def test_update_existing_entries(self):
        existing_backend = _make_setting("default_backend", {"backend": "claude"})
        existing_stages = _make_setting("stage_models", {})

        mock_session = AsyncMock()
        execute_calls = []

        async def fake_execute(stmt):
            execute_calls.append(stmt)
            mock_result = MagicMock()
            # First call: default_backend lookup, second: stage_models lookup
            if len(execute_calls) == 1:
                mock_result.scalar_one_or_none.return_value = existing_backend
            elif len(execute_calls) == 2:
                mock_result.scalar_one_or_none.return_value = existing_stages
            else:
                mock_result.scalar_one_or_none.return_value = None
            return mock_result

        mock_session.execute = fake_execute
        mock_session.add = MagicMock()

        @asynccontextmanager
        async def factory():
            yield mock_session

        app = _make_app(factory)

        payload = {
            "default_backend": "openai",
            "stages": {
                "intake": {
                    "act": {"backend": "openai", "model": "gpt-4o"},
                    "explore": None,
                    "plan": None,
                },
            },
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/settings/models", json=payload)

        assert resp.status_code == 200
        # Existing rows should have been updated in-place
        assert existing_backend.value_json == {"backend": "openai"}
        assert "intake" in existing_stages.value_json


# ---------------------------------------------------------------------------
# GET /api/settings/backends
# ---------------------------------------------------------------------------


class TestGetAvailableBackends:
    @pytest.mark.asyncio
    async def test_returns_backends(self):
        factory, _ = _build_factory_returning([])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/settings/backends")

        assert resp.status_code == 200
        data = resp.json()
        names = [b["name"] for b in data]
        assert "claude" in names
        assert "openai" in names
        assert "gemini" in names
        assert "opencode" in names

        claude = next(b for b in data if b["name"] == "claude")
        assert any("claude-sonnet" in m for m in claude["models"])
        assert claude["display_name"] == "Anthropic"

        opencode = next(b for b in data if b["name"] == "opencode")
        assert opencode["models"] == []

    @pytest.mark.asyncio
    async def test_includes_named_opencode_endpoints(self):
        endpoints = [
            {"slug": "local-ollama", "display_name": "Local Ollama", "base_url": "http://localhost:11434/v1", "models": ["qwen3:7b"]},
        ]
        factory, _ = _build_factory_returning([
            _make_setting("opencode_endpoints", endpoints),
        ])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/settings/backends")

        assert resp.status_code == 200
        data = resp.json()
        names = [b["name"] for b in data]
        assert "opencode:local-ollama" in names
        ep = next(b for b in data if b["name"] == "opencode:local-ollama")
        assert ep["display_name"] == "Local Ollama"
        assert ep["models"] == ["qwen3:7b"]


# ---------------------------------------------------------------------------
# GET /api/settings/opencode-endpoints
# ---------------------------------------------------------------------------


class TestOpenCodeEndpoints:
    @pytest.mark.asyncio
    async def test_get_empty(self):
        factory, _ = _build_factory_returning([])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/settings/opencode-endpoints")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_get_existing(self):
        endpoints = [
            {"slug": "gpu-server", "display_name": "GPU Server", "base_url": "http://gpu.internal/v1", "models": ["llama-70b"]},
        ]
        factory, _ = _build_factory_returning([
            _make_setting("opencode_endpoints", endpoints),
        ])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/settings/opencode-endpoints")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["slug"] == "gpu-server"
        assert data[0]["models"] == ["llama-70b"]

    @pytest.mark.asyncio
    async def test_put_creates_endpoints(self):
        mock_session = AsyncMock()

        async def fake_execute(stmt):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            return mock_result

        mock_session.execute = fake_execute
        mock_session.add = MagicMock()

        @asynccontextmanager
        async def factory():
            yield mock_session

        app = _make_app(factory)

        payload = [
            {"slug": "local-ollama", "display_name": "Local Ollama", "base_url": "http://localhost:11434/v1", "models": ["qwen3:7b"]},
            {"slug": "gpu-server", "display_name": "GPU Server", "base_url": "http://gpu.internal/v1", "models": ["llama-70b"]},
        ]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/settings/opencode-endpoints", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["slug"] == "local-ollama"
        # PipelineSetting + AuditLog = 2 adds
        assert mock_session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_put_rejects_duplicate_slugs(self):
        factory, _ = _build_factory_returning([])
        app = _make_app(factory)

        payload = [
            {"slug": "same", "display_name": "A", "base_url": "http://a", "models": []},
            {"slug": "same", "display_name": "B", "base_url": "http://b", "models": []},
        ]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/settings/opencode-endpoints", json=payload)

        assert resp.status_code == 422

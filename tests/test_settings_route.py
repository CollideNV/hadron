"""Tests for backend template and pipeline settings API routes."""

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


def _make_setting(key: str, value_json):
    return SimpleNamespace(key=key, value_json=value_json)


def _build_factory(scalar_one=None, scalars_list=None):
    """Build a session factory where execute returns consistent mocks.

    scalar_one: return value for scalar_one_or_none()
    scalars_list: iterable for scalars().__iter__
    """
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scalar_one
    if scalars_list is not None:
        mock_scalars = MagicMock()
        mock_scalars.__iter__ = lambda self: iter(scalars_list)
        mock_result.scalars.return_value = mock_scalars

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()

    @asynccontextmanager
    async def factory():
        yield mock_session

    return factory, mock_session


def _multi_query_factory(responses):
    """Build a factory that returns different results per execute() call.

    responses: list of (scalar_one_or_none, scalars_list) tuples.
    """
    mock_session = AsyncMock()
    call_idx = {"i": 0}

    async def fake_execute(stmt):
        idx = call_idx["i"]
        call_idx["i"] += 1
        scalar_one, scalars_list = responses[idx] if idx < len(responses) else (None, None)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = scalar_one
        if scalars_list is not None:
            mock_scalars = MagicMock()
            mock_scalars.__iter__ = lambda self: iter(scalars_list)
            mock_result.scalars.return_value = mock_scalars
        return mock_result

    mock_session.execute = fake_execute
    mock_session.add = MagicMock()

    @asynccontextmanager
    async def factory():
        yield mock_session

    return factory, mock_session


# ---------------------------------------------------------------------------
# GET /api/settings/templates
# ---------------------------------------------------------------------------


class TestGetTemplates:
    @pytest.mark.asyncio
    async def test_returns_builtins_when_no_db(self):
        """Built-in templates returned when DB has no overrides."""
        # Query 1: backend_templates → None, Query 2: default_template → None
        factory, _ = _multi_query_factory([(None, None), (None, None)])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/settings/templates")

        assert resp.status_code == 200
        data = resp.json()
        slugs = [t["slug"] for t in data]
        assert "anthropic" in slugs
        assert "openai" in slugs
        assert "gemini" in slugs
        assert len(data) == 3

        # Anthropic is default when no DB override
        anthropic = next(t for t in data if t["slug"] == "anthropic")
        assert anthropic["is_default"] is True
        assert anthropic["backend"] == "claude"
        assert len(anthropic["available_models"]) > 0
        assert any("claude-sonnet" in m for m in anthropic["available_models"])

        # Check stages exist with expected structure
        assert "implementation" in anthropic["stages"]
        assert anthropic["stages"]["implementation"]["explore"] is not None
        assert anthropic["stages"]["intake"]["explore"] is None

    @pytest.mark.asyncio
    async def test_db_overrides_builtin(self):
        """DB templates override built-in defaults."""
        db_templates = [
            {
                "slug": "anthropic",
                "display_name": "Custom Anthropic",
                "backend": "claude",
                "stages": {
                    "intake": {"act": {"backend": "claude", "model": "claude-opus-4-6"}, "explore": None, "plan": None},
                },
            }
        ]
        factory, _ = _multi_query_factory([
            (_make_setting("backend_templates", db_templates), None),
            (None, None),  # default_template
        ])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/settings/templates")

        data = resp.json()
        anthropic = next(t for t in data if t["slug"] == "anthropic")
        assert anthropic["display_name"] == "Custom Anthropic"
        assert anthropic["stages"]["intake"]["act"]["model"] == "claude-opus-4-6"

    @pytest.mark.asyncio
    async def test_includes_opencode_templates_from_db(self):
        """Custom OpenCode templates from DB are appended after builtins."""
        db_templates = [
            {
                "slug": "opencode-ollama",
                "display_name": "Local Ollama",
                "backend": "opencode",
                "stages": {},
                "base_url": "http://localhost:11434/v1",
                "available_models": ["qwen3:7b"],
            },
        ]
        factory, _ = _multi_query_factory([
            (_make_setting("backend_templates", db_templates), None),
            (None, None),
        ])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/settings/templates")

        data = resp.json()
        assert len(data) == 4  # 3 builtins + 1 opencode
        ollama = next(t for t in data if t["slug"] == "opencode-ollama")
        assert ollama["display_name"] == "Local Ollama"
        assert ollama["base_url"] == "http://localhost:11434/v1"
        assert ollama["available_models"] == ["qwen3:7b"]


# ---------------------------------------------------------------------------
# PUT /api/settings/templates
# ---------------------------------------------------------------------------


class TestUpdateTemplates:
    @pytest.mark.asyncio
    async def test_saves_templates(self):
        factory, mock_session = _multi_query_factory([
            (None, None),  # upsert backend_templates
            (None, None),  # re-load (GET after PUT)
            (None, None),  # default_template for re-load
        ])
        app = _make_app(factory)

        payload = [
            {
                "slug": "anthropic",
                "display_name": "Anthropic",
                "backend": "claude",
                "stages": {"intake": {"act": {"backend": "claude", "model": "claude-sonnet-4-6"}, "explore": None, "plan": None}},
                "is_default": False,
            },
        ]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/settings/templates", json=payload)

        assert resp.status_code == 200
        # Should have added PipelineSetting + AuditLog = 2
        assert mock_session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_persists_available_models_for_opencode_templates(self):
        """Custom opencode templates must round-trip available_models.

        Built-in templates re-derive the list from the cost table, but opencode
        templates have no such fallback — if the handler strips available_models
        it is lost forever.
        """
        # Capture whatever the handler writes to PipelineSetting.value_json.
        added: list = []
        mock_session = AsyncMock()
        mock_session.add = MagicMock(side_effect=lambda obj: added.append(obj))

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # no existing row
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def factory():
            yield mock_session

        app = _make_app(factory)

        payload = [
            {
                "slug": "opencode-ollama",
                "display_name": "Local Ollama",
                "backend": "opencode",
                "stages": {
                    "intake": {
                        "act": {"backend": "opencode", "model": "qwen3:7b"},
                        "explore": None,
                        "plan": None,
                    },
                },
                "base_url": "http://localhost:11434/v1",
                "available_models": ["qwen3:7b", "llama3.2"],
                "is_default": False,
            },
        ]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/settings/templates", json=payload)

        assert resp.status_code == 200
        # The PipelineSetting that was added should carry available_models through.
        setting = next(o for o in added if getattr(o, "key", None) == "backend_templates")
        persisted = setting.value_json[0]
        assert persisted["slug"] == "opencode-ollama"
        assert persisted["available_models"] == ["qwen3:7b", "llama3.2"]

    @pytest.mark.asyncio
    async def test_rejects_duplicate_slugs(self):
        factory, _ = _build_factory()
        app = _make_app(factory)

        payload = [
            {"slug": "same", "display_name": "A", "backend": "claude", "stages": {}, "is_default": False},
            {"slug": "same", "display_name": "B", "backend": "claude", "stages": {}, "is_default": False},
        ]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/settings/templates", json=payload)

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET/PUT /api/settings/templates/default
# ---------------------------------------------------------------------------


class TestDefaultTemplate:
    @pytest.mark.asyncio
    async def test_get_default_falls_back_to_anthropic(self):
        factory, _ = _build_factory(scalar_one=None)
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/settings/templates/default")

        assert resp.status_code == 200
        assert resp.json()["slug"] == "anthropic"

    @pytest.mark.asyncio
    async def test_get_default_from_db(self):
        factory, _ = _build_factory(scalar_one=_make_setting("default_template", {"slug": "openai"}))
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/settings/templates/default")

        assert resp.status_code == 200
        assert resp.json()["slug"] == "openai"

    @pytest.mark.asyncio
    async def test_set_default_valid_slug(self):
        """Setting default to a known slug succeeds."""
        factory, mock_session = _multi_query_factory([
            (None, None),  # _load_templates: backend_templates
            (None, None),  # _load_default_slug inside set_default
            (None, None),  # upsert default_template
        ])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/settings/templates/default", json={"slug": "openai"})

        assert resp.status_code == 200
        assert resp.json()["slug"] == "openai"
        # PipelineSetting + AuditLog = 2
        assert mock_session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_set_default_unknown_slug_rejected(self):
        """Setting default to an unknown slug returns 422."""
        factory, _ = _multi_query_factory([
            (None, None),  # _load_templates
        ])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/settings/templates/default", json={"slug": "nonexistent"})

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET/PUT /api/settings/pipeline-defaults
# ---------------------------------------------------------------------------


class TestPipelineDefaults:
    @pytest.mark.asyncio
    async def test_get_returns_hardcoded_defaults(self):
        factory, _ = _build_factory(scalar_one=None)
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/settings/pipeline-defaults")

        assert resp.status_code == 200
        data = resp.json()
        assert data["max_verification_loops"] == 3
        assert data["max_cost_usd"] == 10.0
        assert data["delivery_strategy"] == "self_contained"
        assert data["default_template"] == "anthropic"
        # Model fields should NOT be present
        assert "default_model" not in data
        assert "explore_model" not in data
        assert "plan_model" not in data
        assert "default_backend" not in data

    @pytest.mark.asyncio
    async def test_put_updates_defaults(self):
        factory, mock_session = _multi_query_factory([(None, None)])
        app = _make_app(factory)

        payload = {
            "max_verification_loops": 5,
            "max_review_dev_loops": 4,
            "max_cost_usd": 25.0,
            "default_template": "openai",
            "delivery_strategy": "push_and_wait",
            "agent_timeout": 600,
            "test_timeout": 240,
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/settings/pipeline-defaults", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["max_verification_loops"] == 5
        assert data["default_template"] == "openai"
        assert data["delivery_strategy"] == "push_and_wait"
        # PipelineSetting + AuditLog
        assert mock_session.add.call_count == 2

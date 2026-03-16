"""Tests for prompt template management — PromptComposer + API routes."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from hadron.agent.prompt import PromptComposer
from hadron.controller.routes.prompts import router


# ---------------------------------------------------------------------------
# PromptComposer unit tests
# ---------------------------------------------------------------------------


class TestPromptComposerCache:
    def test_from_snapshot_uses_cache(self):
        prompts = {"spec_writer": "custom content", "explorer": "explore content"}
        composer = PromptComposer.from_snapshot(prompts)
        result = composer.compose_system_prompt("spec_writer")
        assert result == "custom content"

    def test_from_snapshot_unknown_role_falls_back_to_disk(self):
        composer = PromptComposer.from_snapshot({"spec_writer": "custom"})
        result = composer.compose_system_prompt("explorer")
        assert "Codebase Explorer" in result

    def test_default_composer_reads_from_disk(self):
        composer = PromptComposer()
        result = composer.compose_system_prompt("spec_writer")
        assert "Behaviour Specification Writer" in result

    def test_cache_overrides_disk(self):
        composer = PromptComposer()
        composer._cache["spec_writer"] = "overridden"
        result = composer.compose_system_prompt("spec_writer")
        assert result == "overridden"

    def test_compose_system_prompt_with_repo_context(self):
        composer = PromptComposer.from_snapshot({"spec_writer": "# Writer"})
        result = composer.compose_system_prompt("spec_writer", repo_context="repo info")
        assert "# Writer" in result
        assert "Repository Context" in result
        assert "repo info" in result


class TestPromptComposerLoadAll:
    @pytest.mark.asyncio
    async def test_load_all_populates_cache(self):
        mock_row1 = SimpleNamespace(role="spec_writer", content="db content 1")
        mock_row2 = SimpleNamespace(role="explorer", content="db content 2")

        mock_scalars = MagicMock()
        mock_scalars.__iter__ = lambda self: iter([mock_row1, mock_row2])

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        @asynccontextmanager
        async def factory():
            yield mock_session

        composer = PromptComposer()
        await composer.load_all(factory)

        assert composer._cache["spec_writer"] == "db content 1"
        assert composer._cache["explorer"] == "db content 2"


# ---------------------------------------------------------------------------
# API route tests
# ---------------------------------------------------------------------------


def _make_app(session_factory) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.session_factory = session_factory
    return app


def _make_template(role="spec_writer", content="# Test", description="Test desc", version=1):
    from datetime import datetime, timezone

    return SimpleNamespace(
        role=role,
        content=content,
        description=description,
        version=version,
        updated_at=datetime(2026, 3, 16, tzinfo=timezone.utc),
    )


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


class TestListPrompts:
    @pytest.mark.asyncio
    async def test_list_prompts_returns_all(self):
        templates = [
            _make_template("explorer", "# Explorer", "Codebase Explorer"),
            _make_template("spec_writer", "# Writer", "Spec Writer"),
        ]
        factory, _ = _build_factory_returning(templates)
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/prompts")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["role"] == "explorer"
        assert "content" not in data[0]

    @pytest.mark.asyncio
    async def test_list_prompts_empty(self):
        factory, _ = _build_factory_returning([])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/prompts")

        assert resp.status_code == 200
        assert resp.json() == []


class TestGetPrompt:
    @pytest.mark.asyncio
    async def test_get_prompt_found(self):
        template = _make_template("spec_writer", "# Full content here", "Writer")
        factory, _ = _build_factory_returning([template])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/prompts/spec_writer")

        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "spec_writer"
        assert data["content"] == "# Full content here"
        assert data["version"] == 1

    @pytest.mark.asyncio
    async def test_get_prompt_not_found(self):
        factory, _ = _build_factory_returning([])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/prompts/nonexistent")

        assert resp.status_code == 404


class TestUpdatePrompt:
    @pytest.mark.asyncio
    async def test_update_prompt_success(self):
        template = _make_template("spec_writer", "# Old content", "Writer", version=1)
        factory, mock_session = _build_factory_returning([template])

        async def fake_refresh(obj):
            obj.version = 2
            obj.content = "# New content"

        mock_session.refresh = fake_refresh

        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put(
                "/api/prompts/spec_writer",
                json={"content": "# New content"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 2
        assert data["content"] == "# New content"
        mock_session.add.assert_called()

    @pytest.mark.asyncio
    async def test_update_prompt_not_found(self):
        factory, _ = _build_factory_returning([])
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put(
                "/api/prompts/nonexistent",
                json={"content": "# Updated"},
            )

        assert resp.status_code == 404

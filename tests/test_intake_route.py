"""Tests for the intake route's multi-repo worker spawning."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from hadron.controller.routes.intake import router

# Minimal valid CR payload.
_BASE_CR = {"title": "Test CR", "description": "Implement feature X"}


def _make_app(
    session_factory: object,
    job_spawner: object,
) -> FastAPI:
    """Build a minimal FastAPI app wired to the intake router."""
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.session_factory = session_factory
    app.state.job_spawner = job_spawner
    app.state.redis = None
    return app


def _mock_session_factory(*, existing_external_id: str | None = None):
    """Return an async context-manager session factory backed by mocks.

    The mock session records ``add`` calls and simulates a duplicate-check
    query when *existing_external_id* matches.
    """
    session = AsyncMock()
    session.added: list = []  # type: ignore[attr-defined]

    original_add = MagicMock()

    def _track_add(obj: object) -> None:
        session.added.append(obj)  # type: ignore[attr-defined]
        original_add(obj)

    session.add = MagicMock(side_effect=_track_add)

    # Simulate the SELECT for duplicate external_id.
    result_mock = MagicMock()
    if existing_external_id:
        # Return a truthy sentinel so the route raises 409.
        result_mock.scalar_one_or_none.return_value = object()
    else:
        result_mock.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result_mock)

    @asynccontextmanager
    async def factory():
        yield session

    return factory, session


class TestSingleRepo:
    """Single repo URL triggers one RepoRun and one worker spawn."""

    async def test_single_repo(self) -> None:
        factory, session = _mock_session_factory()
        spawner = AsyncMock()
        app = _make_app(factory, spawner)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/pipeline/trigger",
                json={**_BASE_CR, "repo_urls": ["https://github.com/org/repo"]},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "pending"
        assert len(body["workers"]) == 1
        assert body["workers"][0]["repo_url"] == "https://github.com/org/repo"
        assert body["workers"][0]["repo_name"] == "repo"

        # One CRRun + one RepoRun added.
        from hadron.db.models import CRRun, RepoRun

        added_types = [type(o).__name__ for o in session.added]
        assert added_types.count("CRRun") == 1
        assert added_types.count("RepoRun") == 1

        # Spawner called once with correct args.
        spawner.spawn.assert_awaited_once()
        call_kwargs = spawner.spawn.call_args
        assert call_kwargs.kwargs["repo_url"] == "https://github.com/org/repo"
        assert call_kwargs.kwargs["repo_name"] == "repo"
        assert call_kwargs.kwargs["default_branch"] == "main"


class TestMultipleRepos:
    """Multiple repo URLs spawn N workers and create N RepoRuns."""

    async def test_multiple_repos(self) -> None:
        urls = [
            "https://github.com/org/auth",
            "https://github.com/org/api",
            "https://github.com/org/frontend",
        ]
        factory, session = _mock_session_factory()
        spawner = AsyncMock()
        app = _make_app(factory, spawner)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/pipeline/trigger",
                json={**_BASE_CR, "repo_urls": urls},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["workers"]) == 3

        from hadron.db.models import RepoRun

        repo_runs_added = [o for o in session.added if type(o).__name__ == "RepoRun"]
        assert len(repo_runs_added) == 3

        assert spawner.spawn.await_count == 3
        spawned_urls = [c.kwargs["repo_url"] for c in spawner.spawn.call_args_list]
        assert spawned_urls == urls


class TestEmptyRepoUrls:
    """Empty repo_urls is valid but spawns zero workers."""

    async def test_empty_repos(self) -> None:
        factory, session = _mock_session_factory()
        spawner = AsyncMock()
        app = _make_app(factory, spawner)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/pipeline/trigger",
                json={**_BASE_CR, "repo_urls": []},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["workers"] == []

        from hadron.db.models import RepoRun

        repo_runs_added = [o for o in session.added if type(o).__name__ == "RepoRun"]
        assert len(repo_runs_added) == 0
        spawner.spawn.assert_not_awaited()


class TestDuplicateExternalId:
    """Duplicate external_id returns 409."""

    async def test_duplicate_external_id(self) -> None:
        factory, _ = _mock_session_factory(existing_external_id="JIRA-123")
        spawner = AsyncMock()
        app = _make_app(factory, spawner)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/pipeline/trigger",
                json={**_BASE_CR, "external_id": "JIRA-123"},
            )

        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]
        spawner.spawn.assert_not_awaited()


class TestSpawnerArgs:
    """Spawner receives correct repo_url, repo_name, and default_branch."""

    async def test_spawner_args_custom_branch(self) -> None:
        factory, _ = _mock_session_factory()
        spawner = AsyncMock()
        app = _make_app(factory, spawner)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/pipeline/trigger",
                json={
                    **_BASE_CR,
                    "repo_urls": ["https://github.com/org/my-service"],
                    "repo_default_branch": "develop",
                },
            )

        assert resp.status_code == 200
        spawner.spawn.assert_awaited_once()
        _, kwargs = spawner.spawn.call_args
        assert kwargs["repo_url"] == "https://github.com/org/my-service"
        assert kwargs["repo_name"] == "my-service"
        assert kwargs["default_branch"] == "develop"

    async def test_repo_name_extracted_from_url(self) -> None:
        """Trailing slashes are stripped when extracting repo_name."""
        factory, _ = _mock_session_factory()
        spawner = AsyncMock()
        app = _make_app(factory, spawner)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/pipeline/trigger",
                json={
                    **_BASE_CR,
                    "repo_urls": ["https://github.com/org/my-service/"],
                },
            )

        assert resp.status_code == 200
        _, kwargs = spawner.spawn.call_args
        assert kwargs["repo_name"] == "my-service"


class TestConfigSnapshotExcludesApiKeys:
    """Config snapshot must never contain API keys."""

    async def test_snapshot_has_no_api_keys(self) -> None:
        factory, session = _mock_session_factory()
        spawner = AsyncMock()
        app = _make_app(factory, spawner)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/pipeline/trigger",
                json={**_BASE_CR, "repo_urls": ["https://github.com/org/repo"]},
            )

        assert resp.status_code == 200
        cr_runs = [o for o in session.added if type(o).__name__ == "CRRun"]
        assert len(cr_runs) == 1
        snapshot = cr_runs[0].config_snapshot_json
        snapshot_str = str(snapshot)
        for key_field in ("anthropic_api_key", "openai_api_key", "gemini_api_key", "api_keys"):
            assert key_field not in snapshot_str

    async def test_spawner_receives_extra_env(self) -> None:
        """Spawner is called with extra_env containing resolved keys."""
        factory, _ = _mock_session_factory()
        spawner = AsyncMock()
        app = _make_app(factory, spawner)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/pipeline/trigger",
                json={**_BASE_CR, "repo_urls": ["https://github.com/org/repo"]},
            )

        assert resp.status_code == 200
        spawner.spawn.assert_awaited_once()
        call_kwargs = spawner.spawn.call_args.kwargs
        # extra_env should be present (may be empty if no keys set)
        assert "extra_env" in call_kwargs


class TestTemplateSlug:
    """template_slug is frozen into config snapshot."""

    async def test_template_slug_in_config_snapshot(self) -> None:
        factory, session = _mock_session_factory()
        spawner = AsyncMock()
        app = _make_app(factory, spawner)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/pipeline/trigger",
                json={**_BASE_CR, "template_slug": "openai"},
            )

        assert resp.status_code == 200
        # Find the CRRun object that was added
        from hadron.db.models import CRRun
        cr_runs = [o for o in session.added if type(o).__name__ == "CRRun"]
        assert len(cr_runs) == 1
        snapshot = cr_runs[0].config_snapshot_json
        assert snapshot["pipeline"]["template_slug"] == "openai"

    async def test_null_template_uses_default(self) -> None:
        """When no template_slug provided, falls back to system default."""
        factory, session = _mock_session_factory()
        spawner = AsyncMock()
        app = _make_app(factory, spawner)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/pipeline/trigger",
                json=_BASE_CR,
            )

        assert resp.status_code == 200
        from hadron.db.models import CRRun
        cr_runs = [o for o in session.added if type(o).__name__ == "CRRun"]
        assert len(cr_runs) == 1
        snapshot = cr_runs[0].config_snapshot_json
        # Falls back to "anthropic" when no DB default
        assert snapshot["pipeline"]["template_slug"] == "anthropic"

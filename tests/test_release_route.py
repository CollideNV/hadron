"""Tests for release coordination routes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from hadron.controller.routes.release import router
from hadron.db.models import CRRun, RepoRun


def _make_app(session_factory: AsyncMock, event_bus: AsyncMock | None = None) -> FastAPI:
    """Build a minimal FastAPI app with the release router and mocked state."""
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.session_factory = session_factory
    app.state.event_bus = event_bus
    return app


def _make_cr(cr_id: str = "cr-1", status: str = "running") -> CRRun:
    """Create a CRRun-like object (using SimpleNamespace to avoid DB coupling)."""
    return SimpleNamespace(cr_id=cr_id, status=status)


def _make_repo(
    cr_id: str = "cr-1",
    repo_name: str = "repo-a",
    status: str = "completed",
    **kwargs,
) -> RepoRun:
    """Create a RepoRun-like object."""
    defaults = {
        "id": 1,
        "cr_id": cr_id,
        "repo_url": f"https://github.com/org/{repo_name}",
        "repo_name": repo_name,
        "status": status,
        "branch_name": f"hadron/{cr_id}",
        "pr_url": f"https://github.com/org/{repo_name}/pull/42",
        "pr_description": None,
        "cost_usd": 0.05,
        "error": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _build_session_factory(cr_run, repo_runs):
    """Build a mock async session factory that returns cr_run / repo_runs.

    The release routes execute two queries per session context:
      1. select(CRRun).where(...)  -> scalar_one_or_none()
      2. select(RepoRun).where(...) -> scalars().all()

    We track call order via side_effect on session.execute.
    """
    session = AsyncMock()

    cr_result = MagicMock()
    cr_result.scalar_one_or_none.return_value = cr_run

    repo_result = MagicMock()
    repo_result.scalars.return_value.all.return_value = repo_runs

    session.execute = AsyncMock(side_effect=[cr_result, repo_result])
    session.commit = AsyncMock()

    # session_factory() returns an async context manager yielding session
    factory = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory.return_value = ctx

    return factory, session


def _build_session_factory_for_approve(cr_run, repo_runs):
    """Build a factory for the approve endpoint which opens two session blocks:
      Block 1: select CR, select repos (read)
      Block 2: update CR status (write + commit)
    """
    session_read = AsyncMock()
    cr_result = MagicMock()
    cr_result.scalar_one_or_none.return_value = cr_run
    repo_result = MagicMock()
    repo_result.scalars.return_value.all.return_value = repo_runs
    session_read.execute = AsyncMock(side_effect=[cr_result, repo_result])

    session_write = AsyncMock()
    session_write.execute = AsyncMock()
    session_write.commit = AsyncMock()

    ctx_read = AsyncMock()
    ctx_read.__aenter__ = AsyncMock(return_value=session_read)
    ctx_read.__aexit__ = AsyncMock(return_value=False)

    ctx_write = AsyncMock()
    ctx_write.__aenter__ = AsyncMock(return_value=session_write)
    ctx_write.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock()
    factory.return_value = MagicMock()  # placeholder
    # First call returns read context, second returns write context
    factory.side_effect = [ctx_read, ctx_write]

    return factory, session_write


# ---------------------------------------------------------------------------
# GET /api/pipeline/{cr_id}/release
# ---------------------------------------------------------------------------


class TestGetReleaseStatus:
    @pytest.mark.asyncio
    async def test_cr_not_found_returns_404(self) -> None:
        factory, _ = _build_session_factory(cr_run=None, repo_runs=[])
        app = _make_app(factory)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/pipeline/cr-missing/release")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "CR not found"

    @pytest.mark.asyncio
    async def test_all_repos_completed_ready_for_release(self) -> None:
        cr = _make_cr("cr-1", status="running")
        repos = [
            _make_repo("cr-1", "backend", "completed"),
            _make_repo("cr-1", "frontend", "completed"),
        ]
        factory, _ = _build_session_factory(cr, repos)
        app = _make_app(factory)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/pipeline/cr-1/release")

        assert resp.status_code == 200
        body = resp.json()
        assert body["ready_for_release"] is True
        assert body["any_failed"] is False
        assert body["total_repos"] == 2
        assert body["completed_repos"] == 2

    @pytest.mark.asyncio
    async def test_some_repos_still_running_not_ready(self) -> None:
        cr = _make_cr("cr-1")
        repos = [
            _make_repo("cr-1", "backend", "completed"),
            _make_repo("cr-1", "frontend", "running"),
        ]
        factory, _ = _build_session_factory(cr, repos)
        app = _make_app(factory)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/pipeline/cr-1/release")

        assert resp.status_code == 200
        body = resp.json()
        assert body["ready_for_release"] is False
        assert body["any_failed"] is False
        assert body["completed_repos"] == 1

    @pytest.mark.asyncio
    async def test_some_repos_failed_any_failed_true(self) -> None:
        cr = _make_cr("cr-1")
        repos = [
            _make_repo("cr-1", "backend", "completed"),
            _make_repo("cr-1", "frontend", "failed", error="OOM"),
        ]
        factory, _ = _build_session_factory(cr, repos)
        app = _make_app(factory)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/pipeline/cr-1/release")

        assert resp.status_code == 200
        body = resp.json()
        assert body["ready_for_release"] is False
        assert body["any_failed"] is True
        assert body["repos"][1]["error"] == "OOM"


# ---------------------------------------------------------------------------
# POST /api/pipeline/{cr_id}/release/approve
# ---------------------------------------------------------------------------


class TestApproveRelease:
    @pytest.mark.asyncio
    async def test_cr_not_found_returns_404(self) -> None:
        factory, _ = _build_session_factory_for_approve(cr_run=None, repo_runs=[])
        app = _make_app(factory, event_bus=AsyncMock())

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/pipeline/cr-missing/release/approve")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "CR not found"

    @pytest.mark.asyncio
    async def test_all_completed_and_approved_merges(self) -> None:
        cr = _make_cr("cr-1", status="running")
        repos = [
            _make_repo("cr-1", "backend", "completed"),
            _make_repo("cr-1", "frontend", "completed"),
        ]
        factory, session_write = _build_session_factory_for_approve(cr, repos)
        event_bus = AsyncMock()
        app = _make_app(factory, event_bus=event_bus)

        with patch("hadron.controller.routes.release.is_pr_approved", AsyncMock(return_value=True)), \
             patch("hadron.controller.routes.release.merge_pull_request", AsyncMock(return_value={"sha": "abc", "message": "ok"})):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post("/api/pipeline/cr-1/release/approve")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "released"
        assert set(body["repos_merged"]) == {"backend", "frontend"}

        # Verify CR status was updated
        session_write.execute.assert_called_once()
        session_write.commit.assert_called_once()

        # Verify event was emitted
        event_bus.emit.assert_called_once()
        emitted_event = event_bus.emit.call_args[0][0]
        assert emitted_event.cr_id == "cr-1"
        assert emitted_event.event_type.value == "pipeline_completed"

    @pytest.mark.asyncio
    async def test_unapproved_pr_returns_409(self) -> None:
        cr = _make_cr("cr-1", status="running")
        repos = [
            _make_repo("cr-1", "backend", "completed"),
            _make_repo("cr-1", "frontend", "completed"),
        ]
        factory, _ = _build_session_factory_for_approve(cr, repos)
        app = _make_app(factory, event_bus=AsyncMock())

        with patch("hadron.controller.routes.release.is_pr_approved", AsyncMock(return_value=False)):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post("/api/pipeline/cr-1/release/approve")

        assert resp.status_code == 409
        assert "not yet approved" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_merge_failure_returns_409(self) -> None:
        cr = _make_cr("cr-1", status="running")
        repos = [_make_repo("cr-1", "backend", "completed")]
        factory, _ = _build_session_factory_for_approve(cr, repos)
        app = _make_app(factory, event_bus=AsyncMock())

        from hadron.git.github import GitHubAPIError

        with patch("hadron.controller.routes.release.is_pr_approved", AsyncMock(return_value=True)), \
             patch("hadron.controller.routes.release.merge_pull_request", AsyncMock(side_effect=GitHubAPIError(405, "conflict"))):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post("/api/pipeline/cr-1/release/approve")

        assert resp.status_code == 409
        assert "Merge failed" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_missing_pr_url_skipped(self) -> None:
        cr = _make_cr("cr-1", status="running")
        repos = [_make_repo("cr-1", "backend", "completed", pr_url=None)]
        factory, session_write = _build_session_factory_for_approve(cr, repos)
        event_bus = AsyncMock()
        app = _make_app(factory, event_bus=event_bus)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/pipeline/cr-1/release/approve")

        assert resp.status_code == 200
        body = resp.json()
        assert body["repos_merged"] == []
        assert body["repos_skipped"] == ["backend"]

    @pytest.mark.asyncio
    async def test_not_all_completed_returns_409(self) -> None:
        cr = _make_cr("cr-1")
        repos = [
            _make_repo("cr-1", "backend", "completed"),
            _make_repo("cr-1", "frontend", "running"),
        ]
        factory, _ = _build_session_factory_for_approve(cr, repos)
        app = _make_app(factory, event_bus=AsyncMock())

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/pipeline/cr-1/release/approve")

        assert resp.status_code == 409
        assert "Not all repos are ready" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_no_repos_returns_409(self) -> None:
        cr = _make_cr("cr-1")
        factory, _ = _build_session_factory_for_approve(cr, repo_runs=[])
        app = _make_app(factory, event_bus=AsyncMock())

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/pipeline/cr-1/release/approve")

        assert resp.status_code == 409
        assert resp.json()["detail"] == "No repos found for this CR"

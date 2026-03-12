"""Tests for pipeline status, intervention, nudge, resume, conversation, and logs routes."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from hadron.controller.routes.pipeline import router
from hadron.db.models import CRRun, RepoRun


def _make_app(
    session_factory=None,
    redis=None,
    intervention_mgr=None,
    event_bus=None,
    job_spawner=None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.session_factory = session_factory
    app.state.redis = redis
    app.state.intervention_mgr = intervention_mgr
    app.state.event_bus = event_bus
    app.state.job_spawner = job_spawner
    return app


def _make_cr(cr_id="cr-1", status="running", raw_cr_json=None, **kwargs):
    defaults = {
        "cr_id": cr_id,
        "status": status,
        "source": "api",
        "external_id": None,
        "cost_usd": 0.0,
        "error": None,
        "created_at": None,
        "updated_at": None,
        "raw_cr_json": raw_cr_json or {"title": "Test CR"},
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_repo(cr_id="cr-1", repo_name="backend", status="running", **kwargs):
    defaults = {
        "cr_id": cr_id,
        "repo_name": repo_name,
        "repo_url": f"https://github.com/org/{repo_name}",
        "status": status,
        "branch_name": f"hadron/{cr_id}",
        "pr_url": None,
        "cost_usd": 0.0,
        "error": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _build_factory_single_query(result_value, *, scalar=True):
    """Factory for routes that do one query (scalar_one_or_none)."""
    result_mock = MagicMock()
    if scalar:
        result_mock.scalar_one_or_none.return_value = result_value
    else:
        result_mock.scalars.return_value.all.return_value = result_value

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)

    @asynccontextmanager
    async def factory():
        yield session

    return factory, session


def _build_factory_two_queries(cr_run, repo_runs):
    """Factory for routes that do two queries: CR lookup + repo listing."""
    cr_result = MagicMock()
    cr_result.scalar_one_or_none.return_value = cr_run

    repo_result = MagicMock()
    repo_result.scalars.return_value.all.return_value = repo_runs

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[cr_result, repo_result])

    @asynccontextmanager
    async def factory():
        yield session

    return factory, session


# ---------------------------------------------------------------------------
# GET /api/pipeline/list
# ---------------------------------------------------------------------------


class TestListPipelines:
    @pytest.mark.asyncio
    async def test_list_returns_runs(self) -> None:
        cr = _make_cr("cr-1")
        factory, _ = _build_factory_single_query([cr], scalar=False)
        app = _make_app(session_factory=factory)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/pipeline/list")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["cr_id"] == "cr-1"
        assert body[0]["title"] == "Test CR"

    @pytest.mark.asyncio
    async def test_list_empty(self) -> None:
        factory, _ = _build_factory_single_query([], scalar=False)
        app = _make_app(session_factory=factory)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/pipeline/list")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_extract_title_no_title_in_json(self) -> None:
        cr = _make_cr("cr-2", raw_cr_json={"description": "no title key"})
        factory, _ = _build_factory_single_query([cr], scalar=False)
        app = _make_app(session_factory=factory)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/pipeline/list")

        assert resp.status_code == 200
        assert resp.json()[0]["title"] == ""

    @pytest.mark.asyncio
    async def test_extract_title_null_raw_cr_json(self) -> None:
        """raw_cr_json is None (not a dict)."""
        cr = _make_cr("cr-3")
        cr.raw_cr_json = None
        factory, _ = _build_factory_single_query([cr], scalar=False)
        app = _make_app(session_factory=factory)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/pipeline/list")

        assert resp.status_code == 200
        assert resp.json()[0]["title"] == ""


# ---------------------------------------------------------------------------
# GET /api/pipeline/{cr_id}
# ---------------------------------------------------------------------------


class TestGetPipelineStatus:
    @pytest.mark.asyncio
    async def test_found(self) -> None:
        cr = _make_cr("cr-1")
        repos = [_make_repo("cr-1", "backend"), _make_repo("cr-1", "frontend")]
        factory, _ = _build_factory_two_queries(cr, repos)
        app = _make_app(session_factory=factory)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/pipeline/cr-1")

        assert resp.status_code == 200
        body = resp.json()
        assert body["cr_id"] == "cr-1"
        assert len(body["repos"]) == 2
        assert body["repos"][0]["repo_name"] == "backend"

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        factory, _ = _build_factory_single_query(None)
        app = _make_app(session_factory=factory)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/pipeline/cr-missing")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/pipeline/{cr_id}/intervene
# ---------------------------------------------------------------------------


class TestSetIntervention:
    @pytest.mark.asyncio
    async def test_intervention_set(self) -> None:
        factory, _ = _build_factory_single_query(_make_cr())
        intervention_mgr = AsyncMock()
        app = _make_app(session_factory=factory, intervention_mgr=intervention_mgr)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/pipeline/cr-1/intervene",
                json={"instructions": "Stop and fix tests"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "intervention_set"
        intervention_mgr.set_intervention.assert_awaited_once_with(
            "cr-1", "Stop and fix tests"
        )

    @pytest.mark.asyncio
    async def test_intervention_cr_not_found(self) -> None:
        factory, _ = _build_factory_single_query(None)
        intervention_mgr = AsyncMock()
        app = _make_app(session_factory=factory, intervention_mgr=intervention_mgr)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/pipeline/cr-missing/intervene",
                json={"instructions": "noop"},
            )

        assert resp.status_code == 404
        intervention_mgr.set_intervention.assert_not_awaited()


# ---------------------------------------------------------------------------
# POST /api/pipeline/{cr_id}/nudge
# ---------------------------------------------------------------------------


class TestSendNudge:
    @pytest.mark.asyncio
    async def test_nudge_set(self) -> None:
        factory, _ = _build_factory_single_query(_make_cr())
        intervention_mgr = AsyncMock()
        app = _make_app(session_factory=factory, intervention_mgr=intervention_mgr)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/pipeline/cr-1/nudge",
                json={"role": "tdd_developer", "message": "Focus on edge cases"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "nudge_set"
        assert body["role"] == "tdd_developer"
        intervention_mgr.set_nudge.assert_awaited_once_with(
            "cr-1", "tdd_developer", "Focus on edge cases"
        )

    @pytest.mark.asyncio
    async def test_nudge_cr_not_found(self) -> None:
        factory, _ = _build_factory_single_query(None)
        intervention_mgr = AsyncMock()
        app = _make_app(session_factory=factory, intervention_mgr=intervention_mgr)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/pipeline/cr-missing/nudge",
                json={"role": "tdd_developer", "message": "hi"},
            )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/pipeline/{cr_id}/conversation
# ---------------------------------------------------------------------------


class TestGetConversation:
    @pytest.mark.asyncio
    async def test_valid_key(self) -> None:
        conv_data = [{"role": "user", "content": "hello"}]
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps(conv_data).encode())
        factory, _ = _build_factory_single_query(_make_cr())
        app = _make_app(session_factory=factory, redis=redis)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/pipeline/cr-1/conversation",
                params={"key": "hadron:cr:cr-1:conv:tdd:repo:123"},
            )

        assert resp.status_code == 200
        assert resp.json() == conv_data

    @pytest.mark.asyncio
    async def test_invalid_key_prefix(self) -> None:
        redis = AsyncMock()
        factory, _ = _build_factory_single_query(_make_cr())
        app = _make_app(session_factory=factory, redis=redis)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/pipeline/cr-1/conversation",
                params={"key": "wrong:prefix:key"},
            )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_conversation_not_found(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        factory, _ = _build_factory_single_query(_make_cr())
        app = _make_app(session_factory=factory, redis=redis)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/pipeline/cr-1/conversation",
                params={"key": "hadron:cr:cr-1:conv:tdd:repo:123"},
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_malformed_json(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=b"not json{{{")
        factory, _ = _build_factory_single_query(_make_cr())
        app = _make_app(session_factory=factory, redis=redis)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/pipeline/cr-1/conversation",
                params={"key": "hadron:cr:cr-1:conv:tdd:repo:123"},
            )

        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/pipeline/{cr_id}/logs
# ---------------------------------------------------------------------------


class TestGetWorkerLogs:
    @pytest.mark.asyncio
    async def test_logs_found(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=b"line 1\nline 2\n")

        # Logs route queries RepoRun for repo names, then fetches from Redis
        repo_result = MagicMock()
        repo_result.all.return_value = [("backend",)]
        session = AsyncMock()
        session.execute = AsyncMock(return_value=repo_result)

        @asynccontextmanager
        async def factory():
            yield session

        app = _make_app(session_factory=factory, redis=redis)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/pipeline/cr-1/logs")

        assert resp.status_code == 200
        assert "line 1" in resp.text

    @pytest.mark.asyncio
    async def test_no_logs(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)

        repo_result = MagicMock()
        repo_result.all.return_value = [("backend",)]
        session = AsyncMock()
        session.execute = AsyncMock(return_value=repo_result)

        @asynccontextmanager
        async def factory():
            yield session

        app = _make_app(session_factory=factory, redis=redis)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/pipeline/cr-1/logs")

        assert resp.status_code == 200
        assert "No logs" in resp.text


# ---------------------------------------------------------------------------
# POST /api/pipeline/{cr_id}/resume
# ---------------------------------------------------------------------------


class TestResumePipeline:
    @pytest.mark.asyncio
    async def test_resume_paused_cr(self) -> None:
        cr = _make_cr("cr-1", status="paused")
        repos = [_make_repo("cr-1", "backend", status="paused")]

        # Context 1: check CR exists + status
        cr_result = MagicMock()
        cr_result.scalar_one_or_none.return_value = cr

        # Context 2: select paused repos
        repo_result = MagicMock()
        repo_result.scalars.return_value.all.return_value = repos

        # Context 3: update CRRun + update RepoRun + commit
        update_result = MagicMock()

        sessions = []
        for side_effects in [[cr_result], [repo_result], [update_result, update_result]]:
            s = AsyncMock()
            s.execute = AsyncMock(side_effect=side_effects)
            s.commit = AsyncMock()
            sessions.append(s)

        call_idx = {"i": 0}

        @asynccontextmanager
        async def factory():
            idx = call_idx["i"]
            call_idx["i"] += 1
            yield sessions[idx]

        spawner = AsyncMock()
        event_bus = AsyncMock()
        redis = AsyncMock()

        app = _make_app(
            session_factory=factory,
            redis=redis,
            job_spawner=spawner,
            event_bus=event_bus,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/pipeline/cr-1/resume",
                json={"state_overrides": {}},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "resumed"
        spawner.spawn.assert_awaited_once()
        event_bus.emit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resume_not_found(self) -> None:
        factory, _ = _build_factory_single_query(None)
        app = _make_app(
            session_factory=factory,
            redis=AsyncMock(),
            job_spawner=AsyncMock(),
            event_bus=AsyncMock(),
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/pipeline/cr-missing/resume",
                json={},
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_resume_running_returns_409(self) -> None:
        cr = _make_cr("cr-1", status="running")
        factory, _ = _build_factory_single_query(cr)
        app = _make_app(
            session_factory=factory,
            redis=AsyncMock(),
            job_spawner=AsyncMock(),
            event_bus=AsyncMock(),
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/pipeline/cr-1/resume",
                json={},
            )

        assert resp.status_code == 409
        assert "running" in resp.json()["detail"]

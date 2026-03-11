"""Tests for the InterventionManager."""

from __future__ import annotations

import pytest

from hadron.events.interventions import InterventionManager


class _FakeRedis:
    """Minimal fake Redis for testing interventions."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def set(self, key: str, value: str) -> None:
        self._data[key] = value

    def pipeline(self) -> "_FakePipeline":
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: _FakeRedis) -> None:
        self._redis = redis
        self._ops: list[tuple[str, str]] = []

    def get(self, key: str) -> None:
        self._ops.append(("get", key))

    def delete(self, key: str) -> None:
        self._ops.append(("delete", key))

    async def execute(self) -> list:
        results = []
        for op, key in self._ops:
            if op == "get":
                val = self._redis._data.get(key)
                results.append(val.encode() if val is not None else None)
            elif op == "delete":
                deleted = 1 if key in self._redis._data else 0
                self._redis._data.pop(key, None)
                results.append(deleted)
        return results


class TestInterventionManager:
    @pytest.mark.asyncio
    async def test_set_and_poll_intervention(self) -> None:
        mgr = InterventionManager(_FakeRedis())
        await mgr.set_intervention("cr-1", "stop and fix")
        result = await mgr.poll_intervention("cr-1")
        assert result == "stop and fix"

    @pytest.mark.asyncio
    async def test_poll_consumes_intervention(self) -> None:
        mgr = InterventionManager(_FakeRedis())
        await mgr.set_intervention("cr-1", "fix it")
        await mgr.poll_intervention("cr-1")
        result = await mgr.poll_intervention("cr-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_poll_returns_none_when_empty(self) -> None:
        mgr = InterventionManager(_FakeRedis())
        result = await mgr.poll_intervention("cr-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_overwrites_previous(self) -> None:
        mgr = InterventionManager(_FakeRedis())
        await mgr.set_intervention("cr-1", "first")
        await mgr.set_intervention("cr-1", "second")
        result = await mgr.poll_intervention("cr-1")
        assert result == "second"

    @pytest.mark.asyncio
    async def test_set_and_poll_nudge(self) -> None:
        mgr = InterventionManager(_FakeRedis())
        await mgr.set_nudge("cr-1", "tdd", "focus on edge cases")
        result = await mgr.poll_nudge("cr-1", "tdd")
        assert result == "focus on edge cases"

    @pytest.mark.asyncio
    async def test_poll_nudge_consumes(self) -> None:
        mgr = InterventionManager(_FakeRedis())
        await mgr.set_nudge("cr-1", "reviewer", "be stricter")
        await mgr.poll_nudge("cr-1", "reviewer")
        result = await mgr.poll_nudge("cr-1", "reviewer")
        assert result is None

    @pytest.mark.asyncio
    async def test_nudge_scoped_by_role(self) -> None:
        mgr = InterventionManager(_FakeRedis())
        await mgr.set_nudge("cr-1", "tdd", "msg for tdd")
        await mgr.set_nudge("cr-1", "reviewer", "msg for reviewer")
        assert await mgr.poll_nudge("cr-1", "tdd") == "msg for tdd"
        assert await mgr.poll_nudge("cr-1", "reviewer") == "msg for reviewer"

"""Tests for the global-stream SSE endpoint."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from hadron.controller.routes.events import _global_event_generator, _infer_current_stage
from hadron.events.bus import NoOpEventBus
from hadron.models.events import EventType, PipelineEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeCR:
    def __init__(self, cr_id: str, status: str = "running", title: str = ""):
        self.cr_id = cr_id
        self.status = status
        self.raw_cr_json = {"title": title} if title else None


class _StubEventBus:
    """Event bus that replays canned events and blocks on subscribe."""

    def __init__(self, replay_events: dict[str, list[PipelineEvent]] | None = None):
        self._replay = replay_events or {}

    async def emit(self, event: PipelineEvent) -> None:
        pass

    async def subscribe(self, cr_id: str, last_id: str = "0") -> AsyncIterator[tuple[PipelineEvent, str]]:
        await asyncio.Event().wait()
        return  # pragma: no cover
        yield  # pragma: no cover

    async def replay(self, cr_id: str, from_id: str = "0") -> tuple[list[tuple[PipelineEvent, str]], str]:
        events = self._replay.get(cr_id, [])
        pairs = [(e, f"0-{i+1}") for i, e in enumerate(events)]
        last_id = f"0-{len(events)}" if events else "0"
        return pairs, last_id


def _mock_session_factory(crs: list[_FakeCR]):
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = crs
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)

    @asynccontextmanager
    async def factory():
        yield session

    return factory


class _FakeRequest:
    """Minimal request stub for generator tests."""

    def __init__(self):
        self._disconnected = False

    async def is_disconnected(self) -> bool:
        return self._disconnected


async def _collect_from_generator(gen: AsyncIterator[dict], max_items: int = 10, timeout: float = 2.0) -> list[dict]:
    """Collect items from an async generator with a timeout."""
    collected: list[dict] = []

    async def _read():
        async for item in gen:
            collected.append(item)
            if len(collected) >= max_items:
                return

    try:
        await asyncio.wait_for(_read(), timeout=timeout)
    except asyncio.TimeoutError:
        pass

    return collected


# ---------------------------------------------------------------------------
# Tests — _infer_current_stage
# ---------------------------------------------------------------------------


class TestInferCurrentStage:
    @pytest.mark.asyncio
    async def test_returns_last_stage_entered(self) -> None:
        bus = _StubEventBus(replay_events={
            "cr-1": [
                PipelineEvent(cr_id="cr-1", event_type=EventType.STAGE_ENTERED, stage="intake"),
                PipelineEvent(cr_id="cr-1", event_type=EventType.AGENT_COMPLETED, stage="intake"),
                PipelineEvent(cr_id="cr-1", event_type=EventType.STAGE_ENTERED, stage="review"),
            ],
        })
        assert await _infer_current_stage("cr-1", bus) == "review"

    @pytest.mark.asyncio
    async def test_empty_replay_returns_empty(self) -> None:
        bus = _StubEventBus()
        assert await _infer_current_stage("cr-none", bus) == ""


# ---------------------------------------------------------------------------
# Tests — _global_event_generator
# ---------------------------------------------------------------------------


class TestGlobalEventGenerator:
    @pytest.mark.asyncio
    async def test_sends_cr_status_snapshots(self) -> None:
        """Active CRs are sent as cr_status events at the start."""
        crs = [
            _FakeCR("CR-001", "running", "Fix login bug"),
            _FakeCR("CR-002", "paused", "Add search"),
        ]
        replay_events = {
            "CR-001": [PipelineEvent(cr_id="CR-001", event_type=EventType.STAGE_ENTERED, stage="implementation")],
            "CR-002": [PipelineEvent(cr_id="CR-002", event_type=EventType.STAGE_ENTERED, stage="review")],
        }
        factory = _mock_session_factory(crs)
        bus = _StubEventBus(replay_events=replay_events)
        request = _FakeRequest()

        gen = _global_event_generator(request, bus, factory)
        collected = await _collect_from_generator(gen, max_items=2)

        assert len(collected) == 2

        # Both should be cr_status events
        assert all(c["event"] == "cr_status" for c in collected)

        # Parse data payloads
        data = [json.loads(c["data"]) for c in collected]
        cr_ids = {d["cr_id"] for d in data}
        assert cr_ids == {"CR-001", "CR-002"}

        cr1_data = next(d for d in data if d["cr_id"] == "CR-001")
        assert cr1_data["stage"] == "implementation"
        assert cr1_data["title"] == "Fix login bug"

        cr2_data = next(d for d in data if d["cr_id"] == "CR-002")
        assert cr2_data["stage"] == "review"
        assert cr2_data["status"] == "paused"

    @pytest.mark.asyncio
    async def test_empty_active_crs(self) -> None:
        """No active CRs — generator doesn't yield any events."""
        factory = _mock_session_factory([])
        bus = _StubEventBus()
        request = _FakeRequest()

        gen = _global_event_generator(request, bus, factory)
        collected = await _collect_from_generator(gen, timeout=1.0)

        assert collected == []

    @pytest.mark.asyncio
    async def test_cr_without_title_uses_empty_string(self) -> None:
        """CR with no raw_cr_json still sends a valid snapshot."""
        cr = _FakeCR("CR-003", "running")
        cr.raw_cr_json = None
        factory = _mock_session_factory([cr])
        bus = _StubEventBus()
        request = _FakeRequest()

        gen = _global_event_generator(request, bus, factory)
        collected = await _collect_from_generator(gen, max_items=1)

        assert len(collected) == 1
        data = json.loads(collected[0]["data"])
        assert data["cr_id"] == "CR-003"
        assert data["title"] == ""

    @pytest.mark.asyncio
    async def test_respects_disconnected(self) -> None:
        """Generator stops when the client disconnects."""
        crs = [_FakeCR("CR-005", "running", "Test")]
        factory = _mock_session_factory(crs)
        bus = _StubEventBus(replay_events={
            "CR-005": [PipelineEvent(cr_id="CR-005", event_type=EventType.STAGE_ENTERED, stage="intake")],
        })
        request = _FakeRequest()
        request._disconnected = True  # Already disconnected

        gen = _global_event_generator(request, bus, factory)
        collected = await _collect_from_generator(gen, timeout=1.0)

        # Should get 0 events since disconnected before yielding
        assert len(collected) == 0

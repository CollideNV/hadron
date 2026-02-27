"""Tests for RedisEventBus — replay returns cursor, subscribe uses it."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from hadron.models.events import EventType, PipelineEvent
from hadron.events.bus import EventBus, RedisEventBus


# ---------------------------------------------------------------------------
# Fake Redis implementation for unit tests (no real Redis required)
# ---------------------------------------------------------------------------

class _FakeRedis:
    """Minimal Redis Streams + Pub/Sub fake for testing EventBus logic."""

    def __init__(self) -> None:
        self._streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self._counter = 0
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    async def xadd(self, key: str, fields: dict[str, str]) -> str:
        self._counter += 1
        msg_id = f"0-{self._counter}"
        self._streams.setdefault(key, []).append((msg_id, fields))
        # Wake up any blocking xread waiters
        for q in self._subscribers.get(key, []):
            q.put_nowait(True)
        return msg_id

    async def publish(self, channel: str, message: str) -> int:
        return 0  # pub/sub not needed for these tests

    async def xrange(
        self, key: str, min: str = "-", max: str = "+"
    ) -> list[tuple[str, dict[str, str]]]:
        entries = self._streams.get(key, [])
        if min == "0" or min == "-":
            return entries[:]
        return [(mid, f) for mid, f in entries if mid > min]

    async def xread(
        self,
        streams: dict[str, str],
        block: int = 0,
        count: int | None = None,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        # Resolve "$" to the current last ID so retries after blocking work
        resolved: dict[str, str] = {}
        for key, last_id in streams.items():
            if last_id == "$":
                entries = self._streams.get(key, [])
                resolved[key] = entries[-1][0] if entries else "0"
            else:
                resolved[key] = last_id

        result = []
        for key, last_id in resolved.items():
            entries = self._streams.get(key, [])
            if last_id == "0":
                new = entries[:]
            else:
                new = [(mid, f) for mid, f in entries if mid > last_id]

            if new:
                result.append((key, new[:count] if count else new))

        if result:
            return result

        # Block until something arrives (with timeout for tests)
        if block > 0:
            key = next(iter(resolved))
            q: asyncio.Queue = asyncio.Queue()
            self._subscribers.setdefault(key, []).append(q)
            try:
                await asyncio.wait_for(q.get(), timeout=block / 1000)
            except asyncio.TimeoutError:
                return []
            finally:
                self._subscribers[key].remove(q)
            # Retry after wakeup with resolved IDs (not "$")
            return await self.xread(resolved, block=0, count=count)

        return []


def _make_event(cr_id: str = "cr-1", event_type: EventType = EventType.STAGE_ENTERED, **kwargs: Any) -> PipelineEvent:
    return PipelineEvent(cr_id=cr_id, event_type=event_type, **kwargs)


@pytest.fixture
def bus() -> RedisEventBus:
    return RedisEventBus(redis=_FakeRedis())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# replay() tests
# ---------------------------------------------------------------------------


class TestReplay:
    @pytest.mark.asyncio
    async def test_empty_stream_returns_empty_and_zero(self, bus: RedisEventBus) -> None:
        events, last_id = await bus.replay("cr-none")
        assert events == []
        assert last_id == "0"

    @pytest.mark.asyncio
    async def test_emit_then_replay_returns_events_and_last_id(self, bus: RedisEventBus) -> None:
        await bus.emit(_make_event(stage="intake"))
        await bus.emit(_make_event(stage="tdd"))

        events, last_id = await bus.replay("cr-1")
        assert len(events) == 2
        assert events[0].stage == "intake"
        assert events[1].stage == "tdd"
        assert last_id == "0-2"  # second message

    @pytest.mark.asyncio
    async def test_last_id_matches_final_entry(self, bus: RedisEventBus) -> None:
        for i in range(5):
            await bus.emit(_make_event(stage=f"stage-{i}"))

        events, last_id = await bus.replay("cr-1")
        assert len(events) == 5
        assert last_id == "0-5"


# ---------------------------------------------------------------------------
# subscribe() from replayed cursor — no gaps
# ---------------------------------------------------------------------------


class TestSubscribeFromCursor:
    @pytest.mark.asyncio
    async def test_subscribe_from_last_replayed_picks_up_new_events(
        self, bus: RedisEventBus
    ) -> None:
        # Emit two events, then replay
        await bus.emit(_make_event(stage="a"))
        await bus.emit(_make_event(stage="b"))
        _, last_id = await bus.replay("cr-1")

        # Emit a third event (simulates an event arriving during replay)
        await bus.emit(_make_event(stage="c"))

        # Subscribe from the replay cursor — should get event "c" immediately
        collected = []
        async for event in bus.subscribe("cr-1", last_id=last_id):
            collected.append(event)
            if len(collected) >= 1:
                break

        assert len(collected) == 1
        assert collected[0].stage == "c"

    @pytest.mark.asyncio
    async def test_roundtrip_no_gaps(self, bus: RedisEventBus) -> None:
        """Full round-trip: emit, replay, emit more, subscribe — no events lost."""
        # Phase 1: emit initial events
        await bus.emit(_make_event(stage="1"))
        await bus.emit(_make_event(stage="2"))

        # Phase 2: replay (client connects)
        replayed, cursor = await bus.replay("cr-1")
        assert len(replayed) == 2

        # Phase 3: events emitted during/after replay
        await bus.emit(_make_event(stage="3"))
        await bus.emit(_make_event(stage="4"))

        # Phase 4: subscribe from cursor
        live: list[PipelineEvent] = []
        async for event in bus.subscribe("cr-1", last_id=cursor):
            live.append(event)
            if len(live) >= 2:
                break

        # All events accounted for
        all_stages = [e.stage for e in replayed] + [e.stage for e in live]
        assert all_stages == ["1", "2", "3", "4"]

    @pytest.mark.asyncio
    async def test_subscribe_with_dollar_misses_concurrent_events(
        self, bus: RedisEventBus
    ) -> None:
        """Demonstrates the old bug: subscribe with '$' misses events emitted before subscribe."""
        await bus.emit(_make_event(stage="a"))

        # Emit a second event concurrently after a short delay so the
        # subscriber (using "$") is already blocking when it arrives.
        async def _delayed_emit() -> None:
            await asyncio.sleep(0.05)
            await bus.emit(_make_event(stage="b"))

        collected: list[PipelineEvent] = []

        async def _consume() -> None:
            async for event in bus.subscribe("cr-1", last_id="$"):
                collected.append(event)
                if len(collected) >= 1:
                    break

        # Run consumer and delayed emitter concurrently
        await asyncio.gather(_consume(), _delayed_emit())

        # Only "b" is seen — "a" was lost (this is the bug the fix addresses)
        assert len(collected) == 1
        assert collected[0].stage == "b"

"""Event bus — Redis Streams implementation for pipeline event distribution."""

from __future__ import annotations

import json
from typing import AsyncIterator, Protocol

import redis.asyncio as aioredis

from hadron.models.events import PipelineEvent


class EventBus(Protocol):
    """Protocol for event distribution."""

    async def emit(self, event: PipelineEvent) -> None: ...

    async def subscribe(self, cr_id: str, last_id: str = "0") -> AsyncIterator[PipelineEvent]: ...

    async def replay(self, cr_id: str, from_id: str = "0") -> tuple[list[PipelineEvent], str]: ...


def _stream_key(cr_id: str) -> str:
    return f"hadron:cr:{cr_id}:events"


class RedisEventBus:
    """Event bus backed by Redis Streams (XADD/XREAD/XRANGE) + Pub/Sub for wakeups."""

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def emit(self, event: PipelineEvent) -> None:
        """Append event to the CR's stream and notify subscribers via pub/sub."""
        key = _stream_key(event.cr_id)
        payload = event.model_dump_json()
        await self._redis.xadd(key, {"data": payload})
        await self._redis.publish(f"{key}:notify", "1")

    async def subscribe(
        self, cr_id: str, last_id: str = "0"
    ) -> AsyncIterator[PipelineEvent]:
        """Yield events from the stream, blocking on new entries.

        Starts from last_id (exclusive). Use "0" to get all events from the beginning.
        """
        key = _stream_key(cr_id)
        current_id = last_id
        while True:
            entries = await self._redis.xread({key: current_id}, block=5000, count=50)
            if entries:
                for _stream_name, messages in entries:
                    for msg_id, fields in messages:
                        current_id = msg_id
                        raw = fields.get(b"data") or fields.get("data")
                        if raw:
                            if isinstance(raw, bytes):
                                raw = raw.decode()
                            yield PipelineEvent.model_validate_json(raw)

    async def replay(self, cr_id: str, from_id: str = "0") -> tuple[list[PipelineEvent], str]:
        """Return all events in the stream from from_id (inclusive) and the last stream ID.

        Returns:
            Tuple of (events, last_stream_id). last_stream_id is "0" if the stream
            is empty, suitable for passing directly to subscribe().
        """
        key = _stream_key(cr_id)
        entries = await self._redis.xrange(key, min=from_id)
        events = []
        last_id = "0"
        for msg_id, fields in entries:
            last_id = msg_id if isinstance(msg_id, str) else msg_id.decode()
            raw = fields.get(b"data") or fields.get("data")
            if raw:
                if isinstance(raw, bytes):
                    raw = raw.decode()
                events.append(PipelineEvent.model_validate_json(raw))
        return events, last_id

"""Intervention manager — atomic get-and-delete for human override instructions."""

from __future__ import annotations

import redis.asyncio as aioredis


def _intervention_key(cr_id: str) -> str:
    return f"hadron:cr:{cr_id}:intervention"


class InterventionManager:
    """Manages human interventions for pipeline runs.

    Interventions are stored in Redis and consumed atomically (get + delete).
    A pipeline node checks for an intervention before starting work.
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def set_intervention(self, cr_id: str, instructions: str) -> None:
        """Write an intervention for a CR. Overwrites any existing intervention."""
        await self._redis.set(_intervention_key(cr_id), instructions)

    async def poll_intervention(self, cr_id: str) -> str | None:
        """Atomically get and delete the intervention. Returns None if no intervention."""
        key = _intervention_key(cr_id)
        pipe = self._redis.pipeline()
        pipe.get(key)
        pipe.delete(key)
        results = await pipe.execute()
        value = results[0]
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else value

    async def set_nudge(self, cr_id: str, role: str, message: str) -> None:
        """Set an agent-level nudge (picked up between tool-use rounds)."""
        key = f"hadron:cr:{cr_id}:nudge:{role}"
        await self._redis.set(key, message)

    async def poll_nudge(self, cr_id: str, role: str) -> str | None:
        """Atomically get+delete a nudge for a specific agent role."""
        key = f"hadron:cr:{cr_id}:nudge:{role}"
        pipe = self._redis.pipeline()
        pipe.get(key)
        pipe.delete(key)
        results = await pipe.execute()
        value = results[0]
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else value

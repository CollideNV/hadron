"""Worker infrastructure setup — connection factories for all dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis

from hadron.agent.claude import ClaudeAgentBackend
from hadron.db.engine import create_engine, create_session_factory
from hadron.events.bus import RedisEventBus
from hadron.events.interventions import InterventionManager


@dataclass
class WorkerInfra:
    """Infrastructure connections for a worker run."""

    engine: Any
    session_factory: Any
    redis_client: aioredis.Redis
    event_bus: RedisEventBus
    intervention_mgr: InterventionManager
    agent_backend: ClaudeAgentBackend

    async def close(self) -> None:
        await self.redis_client.aclose()
        await self.engine.dispose()


def connect(cfg: Any) -> WorkerInfra:
    """Create all infrastructure connections from bootstrap config."""
    engine = create_engine(cfg.postgres_url)
    session_factory = create_session_factory(engine)
    redis_client = aioredis.from_url(cfg.redis_url)
    return WorkerInfra(
        engine=engine,
        session_factory=session_factory,
        redis_client=redis_client,
        event_bus=RedisEventBus(redis_client),
        intervention_mgr=InterventionManager(redis_client),
        agent_backend=ClaudeAgentBackend(cfg.anthropic_api_key),
    )

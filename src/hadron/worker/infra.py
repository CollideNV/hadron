"""Worker infrastructure setup — connection factories for all dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import redis.asyncio as aioredis

from hadron.agent.factory import create_agent_backend
from hadron.db.engine import create_engine, create_session_factory
from hadron.events.bus import RedisEventBus
from hadron.events.interventions import InterventionManager


class BackendPool:
    """Lazily creates and caches agent backends by name."""

    def __init__(self, cfg: Any) -> None:
        self._cfg = cfg
        self._cache: dict[str, Any] = {}

    def get(self, name: str) -> Any:
        if name not in self._cache:
            self._cache[name] = create_agent_backend(
                name,
                anthropic_api_key=getattr(self._cfg, "anthropic_api_key", ""),
                gemini_api_key=getattr(self._cfg, "gemini_api_key", ""),
                openai_api_key=getattr(self._cfg, "openai_api_key", ""),
                opencode_base_url=getattr(self._cfg, "opencode_base_url", ""),
            )
        return self._cache[name]


@dataclass
class WorkerInfra:
    """Infrastructure connections for a worker run."""

    engine: Any
    session_factory: Any
    redis_client: aioredis.Redis
    event_bus: RedisEventBus
    intervention_mgr: InterventionManager
    backend_pool: BackendPool
    default_backend_name: str = "claude"

    @property
    def agent_backend(self) -> Any:
        """Default agent backend (backwards compatible)."""
        return self.backend_pool.get(self.default_backend_name)

    async def close(self) -> None:
        await self.redis_client.aclose()
        await self.engine.dispose()


def connect(cfg: Any) -> WorkerInfra:
    """Create all infrastructure connections from bootstrap config."""
    engine = create_engine(cfg.postgres_url)
    session_factory = create_session_factory(engine)
    redis_client = aioredis.from_url(cfg.redis_url)
    default_backend_name = getattr(cfg, "agent_backend", "claude")
    pool = BackendPool(cfg)
    return WorkerInfra(
        engine=engine,
        session_factory=session_factory,
        redis_client=redis_client,
        event_bus=RedisEventBus(redis_client),
        intervention_mgr=InterventionManager(redis_client),
        backend_pool=pool,
        default_backend_name=default_backend_name,
    )

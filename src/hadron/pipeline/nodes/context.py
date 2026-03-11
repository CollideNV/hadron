"""Typed context for pipeline nodes — replaces untyped configurable dict extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.types import RunnableConfig

from hadron.config.defaults import DEFAULT_MODEL, DEFAULT_WORKSPACE_DIR
from hadron.events.bus import EventBus, NoOpEventBus


@dataclass
class NodeContext:
    """Typed access to infrastructure services available to pipeline nodes.

    Constructed once per node invocation via ``NodeContext.from_config(config)``.
    ``event_bus`` is always non-None (uses NoOpEventBus when no real bus is available),
    so callers never need ``if ctx.event_bus:`` guards.
    """

    event_bus: EventBus
    agent_backend: Any  # AgentBackend
    workspace_dir: str
    redis: Any  # redis.asyncio.Redis | None
    model: str
    explore_model: str
    plan_model: str
    intervention_mgr: Any  # InterventionManager | None

    @classmethod
    def from_config(cls, config: RunnableConfig) -> NodeContext:
        """Extract a typed NodeContext from LangGraph's RunnableConfig."""
        configurable = config.get("configurable", {})
        return cls(
            event_bus=configurable.get("event_bus") or NoOpEventBus(),
            agent_backend=configurable.get("agent_backend"),
            workspace_dir=configurable.get("workspace_dir", DEFAULT_WORKSPACE_DIR),
            redis=configurable.get("redis"),
            model=configurable.get("model", DEFAULT_MODEL),
            explore_model=configurable.get("explore_model", ""),
            plan_model=configurable.get("plan_model", ""),
            intervention_mgr=configurable.get("intervention_manager"),
        )

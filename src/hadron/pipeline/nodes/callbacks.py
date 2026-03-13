"""Event callback factories for pipeline nodes."""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Awaitable

import redis.asyncio as aioredis

from hadron.agent.base import AgentResult, OnAgentEvent, OnToolCall
from hadron.events.bus import REDIS_STREAM_PREFIX, EventBus
from hadron.models.events import EventType, PipelineEvent


def make_tool_call_emitter(
    event_bus: EventBus, cr_id: str, stage: str, role: str, repo: str = "",
) -> OnToolCall:
    """Create an on_tool_call callback that emits AGENT_TOOL_CALL events."""

    async def _on_tool_call(
        tool_name: str, tool_input: dict[str, Any], result_snippet: str,
    ) -> None:
        await event_bus.emit(PipelineEvent(
                cr_id=cr_id,
                event_type=EventType.AGENT_TOOL_CALL,
                stage=stage,
                data={
                    "role": role,
                    "repo": repo,
                    "tool": tool_name,
                    "input": {k: v[:2000] if isinstance(v, str) else v for k, v in tool_input.items()},
                    "result_snippet": result_snippet[:5000],
                },
            ))

    return _on_tool_call


def make_agent_event_emitter(
    event_bus: EventBus, cr_id: str, stage: str, role: str, repo: str = "",
) -> OnAgentEvent:
    """Create an on_event callback that emits rich agent events."""

    async def _on_event(event_type: str, data: dict[str, Any]) -> None:
        if event_type == "output":
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id,
                event_type=EventType.AGENT_OUTPUT,
                stage=stage,
                data={"role": role, "repo": repo, "text": data["text"], "round": data.get("round", 0)},
            ))
        elif event_type == "tool_call":
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id,
                event_type=EventType.AGENT_TOOL_CALL,
                stage=stage,
                data={
                    "role": role, "repo": repo,
                    "tool": data["tool"], "input": data["input"],
                    "round": data.get("round", 0), "type": "call",
                },
            ))
        elif event_type == "tool_result":
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id,
                event_type=EventType.AGENT_TOOL_CALL,
                stage=stage,
                data={
                    "role": role, "repo": repo,
                    "tool": data["tool"], "result": data["result"][:10_000],
                    "round": data.get("round", 0), "type": "result",
                },
            ))
        elif event_type == "prompt":
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id,
                event_type=EventType.AGENT_PROMPT,
                stage=stage,
                data={"role": role, "repo": repo, "text": data["text"][:5000]},
            ))
        elif event_type == "nudge":
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id,
                event_type=EventType.AGENT_NUDGE,
                stage=stage,
                data={"role": role, "repo": repo, "text": data["text"]},
            ))
        elif event_type == "phase_started":
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id,
                event_type=EventType.PHASE_STARTED,
                stage=stage,
                data={"role": role, "repo": repo, **data},
            ))
        elif event_type == "phase_completed":
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id,
                event_type=EventType.PHASE_COMPLETED,
                stage=stage,
                data={"role": role, "repo": repo, **data},
            ))

    return _on_event


def make_nudge_poller(
    redis_client: aioredis.Redis, cr_id: str, role: str,
) -> Callable[[], Awaitable[str | None]]:
    """Create an async callable that atomically gets+deletes a nudge for a specific agent role."""

    async def _poll() -> str | None:
        key = f"{REDIS_STREAM_PREFIX}:{cr_id}:nudge:{role}"
        pipe = redis_client.pipeline()
        pipe.get(key)
        pipe.delete(key)
        results = await pipe.execute()
        value = results[0]
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else value

    return _poll


async def store_conversation(
    redis_client: aioredis.Redis,
    cr_id: str,
    role: str,
    repo: str,
    conversation: list[dict[str, Any]],
) -> str:
    """Store agent conversation in Redis with 7-day TTL. Returns the key."""
    ts = int(time.time())
    key = f"{REDIS_STREAM_PREFIX}:{cr_id}:conv:{role}:{repo}:{ts}"
    await redis_client.set(key, json.dumps(conversation, default=str), ex=604800)
    return key


async def emit_cost_update(
    event_bus: EventBus, cr_id: str, stage: str, result: AgentResult, prior_cost: float = 0.0,
) -> None:
    """Emit a COST_UPDATE event after an agent execution."""
    await event_bus.emit(PipelineEvent(
        cr_id=cr_id,
        event_type=EventType.COST_UPDATE,
        stage=stage,
        data={
            "delta_usd": result.cost_usd,
            "total_cost_usd": prior_cost + result.cost_usd,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        },
    ))

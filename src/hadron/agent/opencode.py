"""OpenCode agent backend — delegates to an opencode serve instance via the SDK."""

from __future__ import annotations

import os
from typing import Any

import structlog

from hadron.agent.base import OnAgentEvent
from hadron.agent.base_backend import BaseAgentBackend
from hadron.agent.tool_loop import ToolLoopConfig, _PhaseResult
from hadron.config.limits import MAX_TOOL_RESULT_CALLBACK_CHARS

logger = structlog.stdlib.get_logger(__name__)

_DEFAULT_BASE_URL = "http://127.0.0.1:4096"

# Map Hadron tool names → OpenCode built-in tool names.
# OpenCode's tools are controlled via a dict[str, bool] on session.chat().
_HADRON_TO_OPENCODE_TOOLS: dict[str, str] = {
    "read_file": "read",
    "write_file": "write",
    "list_directory": "read",
    "run_command": "terminal",
    "delete_file": "write",
}


def _map_tools(hadron_tools: list[dict]) -> dict[str, bool]:
    """Convert Hadron tool defs to OpenCode tool enable/disable dict."""
    enabled: set[str] = set()
    for tool in hadron_tools:
        name = tool.get("name", "")
        oc_name = _HADRON_TO_OPENCODE_TOOLS.get(name)
        if oc_name:
            enabled.add(oc_name)
    return {name: True for name in enabled}


class OpenCodeAgentBackend(BaseAgentBackend):
    """Agent backend that delegates to an opencode serve instance.

    OpenCode manages the full tool loop internally (LLM → tool → LLM → done).
    Each phase (explore/plan/act) creates a separate session.
    """

    def __init__(
        self,
        base_url: str | None = None,
        provider_id: str = "",
    ) -> None:
        super().__init__()
        self._base_url = (
            base_url
            or os.environ.get("HADRON_OPENCODE_BASE_URL")
            or _DEFAULT_BASE_URL
        )
        self._provider_id = (
            provider_id
            or os.environ.get("HADRON_OPENCODE_PROVIDER_ID")
            or "ollama"
        )
        # Lazy import so the opencode-ai dep is optional
        from opencode_ai import AsyncOpencode  # noqa: F811

        self._client = AsyncOpencode(base_url=self._base_url)

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    async def _call_tool_loop(self, cfg: ToolLoopConfig) -> _PhaseResult:
        """Delegate the full tool loop to OpenCode."""
        session = await self._client.session.create()
        session_id = session.id
        try:
            return await self._run_session(session_id, cfg)
        finally:
            try:
                await self._client.session.delete(session_id)
            except Exception:
                logger.debug("session_delete_failed", session_id=session_id)

    async def _call_plan(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> _PhaseResult:
        """Single call with no tools for the plan phase."""
        session = await self._client.session.create()
        session_id = session.id
        try:
            result = await self._client.session.chat(
                session_id,
                provider_id=self._provider_id,
                model_id=model,
                parts=[{"type": "text", "text": user_prompt}],
                system=system_prompt,
                tools={},  # No tools for plan phase
            )
            output = await self._extract_output(session_id)
            return _PhaseResult(
                output=output,
                model=model,
                input_tokens=int(result.tokens.input),
                output_tokens=int(result.tokens.output),
                cost_usd=result.cost,
                tool_calls=[],
                conversation=[
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": output},
                ],
                round_count=1,
                cache_creation_tokens=int(result.tokens.cache.write),
                cache_read_tokens=int(result.tokens.cache.read),
            )
        finally:
            try:
                await self._client.session.delete(session_id)
            except Exception:
                logger.debug("session_delete_failed", session_id=session_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_session(self, session_id: str, cfg: ToolLoopConfig) -> _PhaseResult:
        """Run a chat session and extract results."""
        tools = _map_tools(cfg.tools) if cfg.tools else {}

        result = await self._client.session.chat(
            session_id,
            provider_id=self._provider_id,
            model_id=cfg.model,
            parts=[{"type": "text", "text": cfg.user_prompt}],
            system=cfg.system_prompt,
            tools=tools,
        )

        # Extract conversation details from session messages
        tool_calls, conversation, output, round_count = await self._extract_conversation(
            session_id, cfg.on_event,
        )

        return _PhaseResult(
            output=output,
            model=cfg.model,
            input_tokens=int(result.tokens.input),
            output_tokens=int(result.tokens.output),
            cost_usd=result.cost,
            tool_calls=tool_calls,
            conversation=conversation,
            round_count=max(round_count, 1),
            cache_creation_tokens=int(result.tokens.cache.write),
            cache_read_tokens=int(result.tokens.cache.read),
        )

    async def _extract_output(self, session_id: str) -> str:
        """Extract the final text output from a session's messages."""
        messages = await self._client.session.messages(session_id)
        # Walk messages in reverse to find the last assistant text
        for msg_item in reversed(messages):
            if msg_item.info.role == "assistant":
                texts = [
                    p.text for p in msg_item.parts
                    if getattr(p, "type", None) == "text" and hasattr(p, "text")
                ]
                if texts:
                    return "\n".join(texts)
        return ""

    async def _extract_conversation(
        self,
        session_id: str,
        on_event: OnAgentEvent | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, int]:
        """Extract tool calls, conversation, output text, and round count."""
        messages = await self._client.session.messages(session_id)

        tool_calls: list[dict[str, Any]] = []
        conversation: list[dict[str, Any]] = []
        output = ""
        round_count = 0

        for msg_item in messages:
            role = msg_item.info.role
            if role == "assistant":
                round_count += 1

            texts: list[str] = []
            for part in msg_item.parts:
                part_type = getattr(part, "type", None)

                if part_type == "text" and hasattr(part, "text"):
                    texts.append(part.text)
                    if on_event and role == "assistant":
                        await on_event("output", {"text": part.text, "round": round_count})

                elif part_type == "tool":
                    tool_name = getattr(part, "tool", "unknown")
                    state = getattr(part, "state", None)
                    tool_input = {}
                    tool_output = ""
                    if state and hasattr(state, "input"):
                        tool_input = dict(state.input) if state.input else {}
                    if state and hasattr(state, "output"):
                        tool_output = str(state.output) if state.output else ""

                    tool_calls.append({"name": tool_name, "input": tool_input})

                    if on_event:
                        await on_event("tool_use", {
                            "name": tool_name,
                            "input": tool_input,
                            "result": tool_output[:MAX_TOOL_RESULT_CALLBACK_CHARS],
                        })

            if texts:
                content = "\n".join(texts)
                conversation.append({"role": role, "content": content})
                if role == "assistant":
                    output = content  # Last assistant message wins
            elif role == "user":
                conversation.append({"role": role, "content": ""})

        return tool_calls, conversation, output, round_count

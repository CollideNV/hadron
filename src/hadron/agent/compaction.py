"""Conversation compaction and context reset for long-running agent sessions.

Two strategies for managing context growth:
- **Compaction** (80k tokens): Summarize middle messages in-place. Fast, cheap,
  preserves conversation continuity. Used for normal context growth.
- **Context reset** (150k tokens): Start a completely fresh conversation with a
  structured handoff document. Eliminates "context anxiety" where models rush to
  finish as the window fills up. More expensive but produces better results for
  very long sessions.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from hadron.agent.base import OnAgentEvent

logger = logging.getLogger(__name__)

_HANDOFF_SYSTEM_PROMPT = (
    "You are creating a structured handoff document for an AI agent that will "
    "continue this work in a fresh conversation. The handoff must contain ALL "
    "information needed to resume seamlessly.\n\n"
    "Produce a document with these sections:\n"
    "## Progress\n"
    "What has been accomplished so far — list every completed step.\n\n"
    "## Files Modified\n"
    "Every file path that was created, modified, or deleted, with a one-line "
    "description of each change.\n\n"
    "## Files Read\n"
    "Key files that were read for context (only those the next agent will need).\n\n"
    "## Current State\n"
    "Where the work stands right now — what was the last action taken?\n\n"
    "## Remaining Work\n"
    "What still needs to be done to complete the task.\n\n"
    "## Errors & Decisions\n"
    "Any errors encountered and how they were resolved, plus key decisions "
    "made during the work.\n\n"
    "## Test Status\n"
    "Last known test results — which tests pass, which fail, any patterns.\n\n"
    "Be precise with file paths and command outputs. The next agent has NO "
    "access to this conversation — only the handoff document."
)


def _extract_conversation_text(messages: list[dict[str, Any]]) -> str:
    """Build a text representation of messages for summarization."""
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(f"[{role}]: {content[:2000]}")
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(f"[{role}]: {item['text'][:2000]}")
                    elif item.get("type") == "tool_use":
                        parts.append(f"[tool_call]: {item.get('name', '?')}({json.dumps(item.get('input', {}))[:200]})")
                    elif item.get("type") == "tool_result":
                        parts.append(f"[tool_result]: {str(item.get('content', ''))[:500]}")
                elif hasattr(item, "type"):
                    if item.type == "text":
                        parts.append(f"[{role}]: {item.text[:2000]}")
                    elif item.type == "tool_use":
                        parts.append(f"[tool_call]: {item.name}({json.dumps(item.input)[:200]})")
    return "\n".join(parts)


async def compact_messages(
    client: Any,
    messages: list[dict[str, Any]],
    *,
    phase: str,
    on_event: OnAgentEvent | None = None,
) -> list[dict[str, Any]]:
    """Summarize conversation history to reduce token count.

    Keeps the first user message (original task) and the last assistant+tool
    exchange intact. Everything in between is summarized by a cheap Haiku call.

    Parameters
    ----------
    client:
        The ``anthropic.AsyncAnthropic`` client instance.
    messages:
        Full conversation message list.
    phase:
        Current phase label (for logging/events).
    on_event:
        Optional event callback.
    """
    # Need at least: original user + some middle + latest exchange
    if len(messages) < 5:
        return messages

    original_user = messages[0]
    # Keep last 2 messages (assistant response + tool results)
    tail = messages[-2:]
    middle = messages[1:-2]

    middle_text = _extract_conversation_text(middle)

    if on_event:
        await on_event("compaction", {
            "phase": phase,
            "messages_before": len(messages),
            "middle_messages": len(middle),
        })

    logger.info(
        "Compacting conversation [%s]: %d messages → summarizing %d middle messages",
        phase, len(messages), len(middle),
    )

    try:
        summary_response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8192,
            system="Summarize the following agent conversation history concisely. "
                   "You MUST preserve: (1) every file path that was read or written, "
                   "(2) every command that was run and whether it succeeded or failed, "
                   "(3) the current progress status and what has been accomplished, "
                   "(4) any errors encountered and how they were resolved. "
                   "Drop: verbatim file contents, full command outputs, and redundant details.",
            messages=[{"role": "user", "content": middle_text}],
        )
        summary = summary_response.content[0].text
    except Exception as e:
        logger.warning("Compaction failed [%s], keeping original messages: %s", phase, e)
        return messages

    compacted = [
        original_user,
        {"role": "assistant", "content": f"[Conversation compacted — summary of {len(middle)} prior messages]\n\n{summary}"},
        {"role": "user", "content": "Continue from where you left off. Do NOT re-explore the codebase or restart your work — pick up from the progress described in the summary above."},
        *tail,
    ]

    if on_event:
        await on_event("compaction", {
            "phase": phase,
            "messages_before": len(messages),
            "messages_after": len(compacted),
            "summary_length": len(summary),
        })

    logger.info(
        "Compaction complete [%s]: %d → %d messages, summary=%d chars",
        phase, len(messages), len(compacted), len(summary),
    )
    return compacted


async def context_reset(
    client: Any,
    messages: list[dict[str, Any]],
    *,
    original_task: str,
    phase: str,
    on_event: OnAgentEvent | None = None,
) -> list[dict[str, Any]]:
    """Full context reset — start fresh with a structured handoff.

    Unlike compaction (which summarizes in-place), this produces a handoff
    document from the entire conversation and starts a brand new message
    list. This eliminates "context anxiety" where models rush to finish
    as the context window fills up.

    Parameters
    ----------
    client:
        The ``anthropic.AsyncAnthropic`` client instance.
    messages:
        Full conversation message list.
    original_task:
        The original user prompt / task description (used as the base of
        the new conversation).
    phase:
        Current phase label (for logging/events).
    on_event:
        Optional event callback.
    """
    if len(messages) < 3:
        return messages

    conversation_text = _extract_conversation_text(messages)

    if on_event:
        await on_event("context_reset", {
            "phase": phase,
            "messages_before": len(messages),
        })

    logger.info(
        "Context reset [%s]: generating handoff from %d messages",
        phase, len(messages),
    )

    try:
        handoff_response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=16384,
            system=_HANDOFF_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": conversation_text}],
        )
        handoff = handoff_response.content[0].text
    except Exception as e:
        logger.warning("Context reset failed [%s], falling back to compaction: %s", phase, e)
        return await compact_messages(client, messages, phase=phase, on_event=on_event)

    reset_messages = [
        {"role": "user", "content": (
            f"{original_task}\n\n"
            "---\n\n"
            "## Handoff from Previous Session\n\n"
            "A previous agent session worked on this task but ran out of context. "
            "Below is a structured handoff of everything accomplished so far. "
            "Continue from where it left off — do NOT redo completed work.\n\n"
            f"{handoff}"
        )},
    ]

    if on_event:
        await on_event("context_reset", {
            "phase": phase,
            "messages_before": len(messages),
            "messages_after": len(reset_messages),
            "handoff_length": len(handoff),
        })

    logger.info(
        "Context reset complete [%s]: %d messages → fresh start, handoff=%d chars",
        phase, len(messages), len(handoff),
    )
    return reset_messages

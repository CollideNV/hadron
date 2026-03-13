"""Conversation compaction — summarize long tool-use conversations to reduce token count."""

from __future__ import annotations

import json
import logging
from typing import Any

from hadron.agent.base import OnAgentEvent

logger = logging.getLogger(__name__)


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

    # Build a text representation of the middle for summarization
    middle_text_parts: list[str] = []
    for msg in middle:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, str):
            middle_text_parts.append(f"[{role}]: {content[:2000]}")
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        middle_text_parts.append(f"[{role}]: {item['text'][:2000]}")
                    elif item.get("type") == "tool_use":
                        middle_text_parts.append(f"[tool_call]: {item.get('name', '?')}({json.dumps(item.get('input', {}))[:200]})")
                    elif item.get("type") == "tool_result":
                        middle_text_parts.append(f"[tool_result]: {str(item.get('content', ''))[:500]}")
                elif hasattr(item, "type"):
                    if item.type == "text":
                        middle_text_parts.append(f"[{role}]: {item.text[:2000]}")
                    elif item.type == "tool_use":
                        middle_text_parts.append(f"[tool_call]: {item.name}({json.dumps(item.input)[:200]})")

    middle_text = "\n".join(middle_text_parts)

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

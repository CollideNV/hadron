"""Message serialization helpers for agent conversations."""

from __future__ import annotations

from typing import Any


def _serialize_messages(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert messages to JSON-serializable format."""
    result = []
    for msg in msgs:
        entry: dict[str, Any] = {"role": msg["role"]}
        content = msg.get("content")
        if isinstance(content, str):
            entry["content"] = content
        elif isinstance(content, list):
            serialized = []
            for item in content:
                if isinstance(item, dict):
                    serialized.append(item)
                elif hasattr(item, "type"):
                    if item.type == "text":
                        serialized.append({"type": "text", "text": item.text})
                    elif item.type == "tool_use":
                        serialized.append({
                            "type": "tool_use", "id": item.id,
                            "name": item.name, "input": item.input,
                        })
                else:
                    serialized.append(str(item))
            entry["content"] = serialized
        else:
            entry["content"] = str(content) if content else ""
        result.append(entry)
    return result

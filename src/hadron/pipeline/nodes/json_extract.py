"""JSON extraction from LLM output."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_json(text: str, *, context: str = "") -> dict[str, Any] | None:
    """Extract a JSON object from LLM text output.

    Tries multiple strategies in order:
      1. ```json ... ``` fenced block
      2. ``` ... ``` generic fenced block
      3. First ``{`` to last ``}`` substring
      4. Raw text as-is

    Returns the parsed dict, or None if all strategies fail.
    Logs the failure with *context* for debugging.
    """
    strategies: list[tuple[str, Any]] = [
        ("json-fence", lambda t: t.split("```json")[1].split("```")[0] if "```json" in t else None),
        ("generic-fence", lambda t: t.split("```")[1].split("```")[0] if "```" in t else None),
        ("brace-scan", lambda t: t[t.index("{"):t.rindex("}") + 1] if "{" in t else None),
        ("raw", lambda t: t),
    ]
    for name, extract in strategies:
        try:
            candidate = extract(text)
            if candidate:
                return json.loads(candidate.strip())
        except (json.JSONDecodeError, IndexError, ValueError) as exc:
            logger.debug("extract_json strategy %s failed (%s): %s", name, context, exc)
            continue
    logger.error("Failed to extract JSON from LLM output (%s): %.500s", context, text)
    return None

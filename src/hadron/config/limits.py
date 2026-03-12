"""Centralized truncation and size limits for the pipeline.

All truncation thresholds live here so the overall strategy is visible
in one place and changes propagate automatically.
"""

from __future__ import annotations

# --- Agent tool execution ---
MAX_COMMAND_OUTPUT_CHARS = 50_000
MAX_READ_FILE_CHARS = 100_000

# --- Agent event / callback payloads ---
MAX_TOOL_RESULT_EVENT_CHARS = 10_000
MAX_TOOL_RESULT_CALLBACK_CHARS = 5_000

# --- Pipeline context injection ---
MAX_CONTEXT_CHARS = 24_000  # ~6k tokens — keep injected context lean

# --- Code review ---
MAX_DIFF_CHARS = 30_000

# --- Conversation compaction ---
# Compact conversation when a single round's input tokens exceed this threshold.
COMPACT_INPUT_TOKEN_THRESHOLD = 80_000

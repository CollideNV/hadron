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

# --- Stage diff events ---
MAX_DIFF_EVENT_CHARS = 50_000
MAX_FEATURE_CONTENT_EVENT_CHARS = 30_000

# --- Test output truncation ---
TEST_OUTPUT_TAIL_CHARS = 3_000   # Last N chars of test output in implementation payload
TEST_OUTPUT_BRIEF_CHARS = 2_000  # Abbreviated test output stored in dev/delivery results
TEST_OUTPUT_EVENT_CHARS = 500    # Test output snippet emitted in pipeline events
REBASE_OUTPUT_TAIL_CHARS = 500   # Post-rebase test failure log snippet

# --- E2E testing ---
MAX_E2E_RETRIES = 2
E2E_TEST_TIMEOUT_SECONDS = 300

# --- Conversation compaction ---
# Compact conversation when a single round's input tokens exceed this threshold.
COMPACT_INPUT_TOKEN_THRESHOLD = 80_000
# Full context reset when input tokens exceed this higher threshold.
# Unlike compaction (which summarizes in-place), a reset starts a fresh
# conversation with a structured handoff — eliminating "context anxiety"
# where models rush to finish as the window fills up.
CONTEXT_RESET_TOKEN_THRESHOLD = 150_000

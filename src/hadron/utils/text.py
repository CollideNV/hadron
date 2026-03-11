"""Centralized text truncation utilities.

All truncation in the pipeline goes through these functions so the strategy
is consistent and changes propagate from a single place.
"""

from __future__ import annotations


def truncate(text: str, max_chars: int, *, suffix: str = "\n... (truncated)") -> str:
    """Truncate *text* to *max_chars*, appending *suffix* if truncated."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + suffix

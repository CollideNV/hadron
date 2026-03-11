"""Reusable rate-limit retry logic for Anthropic API calls."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, TypeVar

import anthropic

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

# Retry settings
MAX_RETRIES = 5
BASE_WAIT_SECONDS = 60


async def call_with_retry(
    api_call: Callable[[], Any],
    *,
    label: str,
    on_retry: Callable[[int], Any] | None = None,
    max_retries: int = MAX_RETRIES,
    base_wait: int = BASE_WAIT_SECONDS,
) -> _T:
    """Call *api_call* with exponential back-off on rate-limit errors.

    Args:
        api_call: Async callable (no args) that makes the Anthropic API call.
        label: Human-readable label for log messages (e.g. "explore", "plan").
        on_retry: Optional async callback invoked with the wait-seconds on each
            retry, allowing callers to emit events / yield before sleeping.
        max_retries: Maximum number of attempts before re-raising.
        base_wait: Base wait time in seconds (multiplied by attempt number).

    Returns:
        The value returned by *api_call*.
    """
    for attempt in range(max_retries):
        try:
            return await api_call()
        except anthropic.RateLimitError as e:
            if attempt == max_retries - 1:
                raise
            wait = base_wait * (attempt + 1)
            logger.warning(
                "Rate limited [%s] (attempt %d/%d), waiting %ds: %s",
                label, attempt + 1, max_retries, wait, e,
            )
            if on_retry:
                await on_retry(wait)
            await asyncio.sleep(wait)
    # Unreachable — the final attempt either returns or re-raises.
    raise AssertionError("unreachable")  # pragma: no cover

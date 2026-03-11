"""Reusable rate-limit retry logic for Anthropic API calls."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

import anthropic

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

# Retry settings
MAX_RETRIES = 8
BASE_WAIT_SECONDS = 10
MIN_WAIT_SECONDS = 2
MAX_WAIT_SECONDS = 120


def _extract_retry_after(error: anthropic.RateLimitError) -> float | None:
    """Extract Retry-After header from the API error response, if available."""
    try:
        response = getattr(error, "response", None)
        if response is None:
            return None
        headers = getattr(response, "headers", None)
        if headers is None:
            return None
        value = headers.get("retry-after")
        if value is None:
            return None
        return float(value)
    except (ValueError, TypeError):
        return None


@dataclass
class RetryResult(Generic[_T]):
    """Result from call_with_retry, including throttle statistics."""

    value: _T
    throttle_count: int = 0
    throttle_seconds: float = 0.0


async def call_with_retry(
    api_call: Callable[[], Awaitable[_T]],
    *,
    label: str,
    on_retry: Callable[[int], Awaitable[None]] | None = None,
    max_retries: int = MAX_RETRIES,
    base_wait: int = BASE_WAIT_SECONDS,
) -> RetryResult[_T]:
    """Call *api_call* with back-off on rate-limit errors.

    Uses the server's ``Retry-After`` header when available, falling back to
    exponential back-off based on *base_wait*.

    Args:
        api_call: Async callable (no args) that makes the Anthropic API call.
        label: Human-readable label for log messages (e.g. "explore", "plan").
        on_retry: Optional async callback invoked with the wait-seconds on each
            retry, allowing callers to emit events / yield before sleeping.
        max_retries: Maximum number of attempts before re-raising.
        base_wait: Base wait time in seconds for fallback exponential back-off.

    Returns:
        A RetryResult containing the value returned by *api_call* and throttle stats.
    """
    throttle_count = 0
    throttle_seconds = 0.0

    for attempt in range(max_retries):
        try:
            value = await api_call()
            return RetryResult(
                value=value,
                throttle_count=throttle_count,
                throttle_seconds=throttle_seconds,
            )
        except anthropic.RateLimitError as e:
            if attempt == max_retries - 1:
                raise
            # Prefer server-provided Retry-After, fall back to exponential backoff
            retry_after = _extract_retry_after(e)
            if retry_after is not None:
                wait = max(MIN_WAIT_SECONDS, min(retry_after, MAX_WAIT_SECONDS))
            else:
                wait = min(base_wait * (attempt + 1), MAX_WAIT_SECONDS)
            throttle_count += 1
            throttle_seconds += wait
            logger.warning(
                "Rate limited [%s] (attempt %d/%d), waiting %.0fs%s: %s",
                label, attempt + 1, max_retries, wait,
                " (from Retry-After)" if retry_after is not None else "",
                e,
            )
            if on_retry:
                await on_retry(int(wait))
            await asyncio.sleep(wait)
    # Unreachable — the final attempt either returns or re-raises.
    raise AssertionError("unreachable")  # pragma: no cover

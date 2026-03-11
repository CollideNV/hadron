"""Tests for the rate limiter retry logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import pytest

from hadron.agent.rate_limiter import (
    MAX_WAIT_SECONDS,
    MIN_WAIT_SECONDS,
    RetryResult,
    _extract_retry_after,
    call_with_retry,
)


def _make_rate_limit_error(retry_after: str | None = None) -> anthropic.RateLimitError:
    """Create a RateLimitError with optional Retry-After header."""
    headers = {"retry-after": retry_after} if retry_after else {}
    return anthropic.RateLimitError(
        message="rate limited",
        response=MagicMock(status_code=429, headers=headers),
        body=None,
    )


class TestExtractRetryAfter:
    def test_extracts_numeric_header(self) -> None:
        err = _make_rate_limit_error("5")
        assert _extract_retry_after(err) == 5.0

    def test_extracts_float_header(self) -> None:
        err = _make_rate_limit_error("2.5")
        assert _extract_retry_after(err) == 2.5

    def test_returns_none_when_missing(self) -> None:
        err = _make_rate_limit_error(None)
        assert _extract_retry_after(err) is None

    def test_returns_none_for_invalid_value(self) -> None:
        err = _make_rate_limit_error("not-a-number")
        assert _extract_retry_after(err) is None

    def test_returns_none_when_no_response(self) -> None:
        err = _make_rate_limit_error()
        # Simulate missing response attr
        err.response = None  # type: ignore[assignment]
        assert _extract_retry_after(err) is None


class TestCallWithRetry:
    @pytest.mark.asyncio
    async def test_success_on_first_try(self) -> None:
        api_call = AsyncMock(return_value="ok")
        result = await call_with_retry(api_call, label="test")
        assert isinstance(result, RetryResult)
        assert result.value == "ok"
        assert result.throttle_count == 0
        assert result.throttle_seconds == 0.0
        api_call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit_with_fallback_backoff(self) -> None:
        api_call = AsyncMock(
            side_effect=[_make_rate_limit_error(), "ok"]
        )
        with patch("hadron.agent.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await call_with_retry(
                api_call, label="test", max_retries=3, base_wait=5
            )
        assert result.value == "ok"
        assert result.throttle_count == 1
        assert result.throttle_seconds == 5.0  # base_wait * (attempt + 1) = 5 * 1
        mock_sleep.assert_awaited_once_with(5.0)
        assert api_call.await_count == 2

    @pytest.mark.asyncio
    async def test_uses_retry_after_header(self) -> None:
        api_call = AsyncMock(
            side_effect=[_make_rate_limit_error("3"), "ok"]
        )
        with patch("hadron.agent.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await call_with_retry(
                api_call, label="test", max_retries=3, base_wait=60
            )
        assert result.value == "ok"
        assert result.throttle_count == 1
        assert result.throttle_seconds == 3.0  # from Retry-After header, not base_wait
        mock_sleep.assert_awaited_once_with(3.0)

    @pytest.mark.asyncio
    async def test_retry_after_clamped_to_min(self) -> None:
        api_call = AsyncMock(
            side_effect=[_make_rate_limit_error("0.5"), "ok"]
        )
        with patch("hadron.agent.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await call_with_retry(
                api_call, label="test", max_retries=3, base_wait=60
            )
        assert result.throttle_seconds == MIN_WAIT_SECONDS
        mock_sleep.assert_awaited_once_with(float(MIN_WAIT_SECONDS))

    @pytest.mark.asyncio
    async def test_retry_after_clamped_to_max(self) -> None:
        api_call = AsyncMock(
            side_effect=[_make_rate_limit_error("999"), "ok"]
        )
        with patch("hadron.agent.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await call_with_retry(
                api_call, label="test", max_retries=3, base_wait=10
            )
        assert result.throttle_seconds == MAX_WAIT_SECONDS
        mock_sleep.assert_awaited_once_with(float(MAX_WAIT_SECONDS))

    @pytest.mark.asyncio
    async def test_fallback_backoff_clamped_to_max(self) -> None:
        api_call = AsyncMock(
            side_effect=[_make_rate_limit_error(), _make_rate_limit_error(), "ok"]
        )
        with patch("hadron.agent.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await call_with_retry(
                api_call, label="test", max_retries=5, base_wait=100
            )
        # attempt 0: min(100*1, 120) = 100, attempt 1: min(100*2, 120) = 120
        assert result.throttle_seconds == 100 + MAX_WAIT_SECONDS

    @pytest.mark.asyncio
    async def test_exhausts_retries(self) -> None:
        api_call = AsyncMock(side_effect=_make_rate_limit_error())
        with patch("hadron.agent.rate_limiter.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(anthropic.RateLimitError):
                await call_with_retry(
                    api_call, label="test", max_retries=2, base_wait=1
                )
        assert api_call.await_count == 2

    @pytest.mark.asyncio
    async def test_on_retry_callback(self) -> None:
        api_call = AsyncMock(
            side_effect=[_make_rate_limit_error("7"), "ok"]
        )
        on_retry = AsyncMock()
        with patch("hadron.agent.rate_limiter.asyncio.sleep", new_callable=AsyncMock):
            result = await call_with_retry(
                api_call, label="test", on_retry=on_retry, max_retries=3, base_wait=10
            )
        on_retry.assert_awaited_once_with(7)  # int(7.0) from Retry-After
        assert result.throttle_count == 1
        assert result.throttle_seconds == 7.0

    @pytest.mark.asyncio
    async def test_non_rate_limit_error_not_retried(self) -> None:
        api_call = AsyncMock(side_effect=ValueError("bad input"))
        with pytest.raises(ValueError, match="bad input"):
            await call_with_retry(api_call, label="test")
        api_call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multiple_retries_accumulate_throttle_stats(self) -> None:
        api_call = AsyncMock(
            side_effect=[
                _make_rate_limit_error("3"),
                _make_rate_limit_error("5"),
                "ok",
            ]
        )
        with patch("hadron.agent.rate_limiter.asyncio.sleep", new_callable=AsyncMock):
            result = await call_with_retry(
                api_call, label="test", max_retries=5, base_wait=10
            )
        assert result.value == "ok"
        assert result.throttle_count == 2
        assert result.throttle_seconds == 8.0  # 3 + 5

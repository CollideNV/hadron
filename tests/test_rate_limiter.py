"""Tests for the rate limiter retry logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import anthropic
import pytest

from hadron.agent.rate_limiter import call_with_retry


class TestCallWithRetry:
    @pytest.mark.asyncio
    async def test_success_on_first_try(self) -> None:
        api_call = AsyncMock(return_value="ok")
        result = await call_with_retry(api_call, label="test")
        assert result == "ok"
        api_call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit(self) -> None:
        api_call = AsyncMock(
            side_effect=[
                anthropic.RateLimitError(
                    message="rate limited",
                    response=AsyncMock(status_code=429, headers={}),
                    body=None,
                ),
                "ok",
            ]
        )
        with patch("hadron.agent.rate_limiter.asyncio.sleep", new_callable=AsyncMock):
            result = await call_with_retry(
                api_call, label="test", max_retries=3, base_wait=1
            )
        assert result == "ok"
        assert api_call.await_count == 2

    @pytest.mark.asyncio
    async def test_exhausts_retries(self) -> None:
        err = anthropic.RateLimitError(
            message="rate limited",
            response=AsyncMock(status_code=429, headers={}),
            body=None,
        )
        api_call = AsyncMock(side_effect=err)
        with patch("hadron.agent.rate_limiter.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(anthropic.RateLimitError):
                await call_with_retry(
                    api_call, label="test", max_retries=2, base_wait=1
                )
        assert api_call.await_count == 2

    @pytest.mark.asyncio
    async def test_on_retry_callback(self) -> None:
        api_call = AsyncMock(
            side_effect=[
                anthropic.RateLimitError(
                    message="rate limited",
                    response=AsyncMock(status_code=429, headers={}),
                    body=None,
                ),
                "ok",
            ]
        )
        on_retry = AsyncMock()
        with patch("hadron.agent.rate_limiter.asyncio.sleep", new_callable=AsyncMock):
            await call_with_retry(
                api_call, label="test", on_retry=on_retry, max_retries=3, base_wait=10
            )
        on_retry.assert_awaited_once_with(10)  # base_wait * (attempt + 1) = 10 * 1

    @pytest.mark.asyncio
    async def test_non_rate_limit_error_not_retried(self) -> None:
        api_call = AsyncMock(side_effect=ValueError("bad input"))
        with pytest.raises(ValueError, match="bad input"):
            await call_with_retry(api_call, label="test")
        api_call.assert_awaited_once()

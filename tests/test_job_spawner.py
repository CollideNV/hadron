"""Tests for SubprocessJobSpawner."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hadron.controller.job_spawner import SubprocessJobSpawner, K8sJobSpawner


class _AsyncLineIter:
    """Async iterator over lines for mocking proc.stdout."""

    def __init__(self, lines: list[bytes]):
        self._lines = iter(lines)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._lines)
        except StopIteration:
            raise StopAsyncIteration


class TestSubprocessJobSpawner:
    @pytest.mark.asyncio
    async def test_spawn_creates_subprocess(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"output", None))
        mock_proc.returncode = 0

        with patch(
            "hadron.controller.job_spawner.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ) as mock_exec:
            spawner = SubprocessJobSpawner()
            await spawner.spawn("cr-1", "https://github.com/org/repo", "repo")

            mock_exec.assert_awaited_once()
            args = mock_exec.call_args
            # Check command args include expected flags
            assert any("--cr-id=cr-1" in str(a) for a in args[0])
            assert any("--repo-url=https://github.com/org/repo" in str(a) for a in args[0])

    @pytest.mark.asyncio
    async def test_spawn_extracts_repo_name(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", None))
        mock_proc.returncode = 0

        with patch(
            "hadron.controller.job_spawner.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ):
            spawner = SubprocessJobSpawner()
            await spawner.spawn("cr-1", "https://github.com/org/my-service")

            # Check it stored process with extracted repo name
            assert "cr-1:my-service" in spawner._processes

    @pytest.mark.asyncio
    async def test_log_output_stores_in_redis(self) -> None:
        redis = AsyncMock()
        mock_proc = AsyncMock()
        # _log_output reads proc.stdout as an async iterator line-by-line
        mock_proc.stdout = _AsyncLineIter([b"test output\n"])
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0

        spawner = SubprocessJobSpawner(redis=redis)
        await spawner._log_output("cr-1:repo", mock_proc)

        redis.append.assert_awaited_once()
        call_args = redis.append.call_args
        assert "worker_log" in call_args[0][0]
        redis.expire.assert_awaited_once()
        assert redis.expire.call_args[0][1] == 86400

    @pytest.mark.asyncio
    async def test_log_output_handles_redis_failure(self) -> None:
        redis = AsyncMock()
        redis.append = AsyncMock(side_effect=ConnectionError("redis down"))
        mock_proc = AsyncMock()
        mock_proc.stdout = _AsyncLineIter([b"output\n"])
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0

        spawner = SubprocessJobSpawner(redis=redis)
        # Should not raise
        await spawner._log_output("cr-1:repo", mock_proc)

    @pytest.mark.asyncio
    async def test_log_output_no_redis(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.stdout = _AsyncLineIter([b"output\n"])
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0

        spawner = SubprocessJobSpawner(redis=None)
        # Should not raise
        await spawner._log_output("cr-1:repo", mock_proc)

    @pytest.mark.asyncio
    async def test_log_output_cleans_up_process(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.stdout = _AsyncLineIter([b""])
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0

        spawner = SubprocessJobSpawner()
        spawner._processes["cr-1:repo"] = mock_proc
        await spawner._log_output("cr-1:repo", mock_proc)
        assert "cr-1:repo" not in spawner._processes


class TestK8sJobSpawner:
    def test_init_defaults(self) -> None:
        spawner = K8sJobSpawner()
        assert spawner._namespace == "hadron"
        assert spawner._worker_image == "hadron-worker:latest"

    def test_init_custom(self) -> None:
        spawner = K8sJobSpawner(namespace="prod", worker_image="myimage:v2")
        assert spawner._namespace == "prod"
        assert spawner._worker_image == "myimage:v2"

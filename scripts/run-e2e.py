#!/usr/bin/env python3
"""E2E runner entry point.

Runs inside a dedicated K8s Job pod (image `hadron-e2e-runner:latest`),
scoped to one (CR, repo). Loops on a Redis queue:

  BLPOP hadron:e2e:{cr_id}:{repo_name}:queue
    → GET  hadron:e2e:{run_id}:src      (tarball)
    → GET  hadron:e2e:{run_id}:cmd      (JSON contract)
    → wipe /workspace/repo, extract tarball
    → npx playwright install chromium   (no-op on version match)
    → run setup[] sequentially
    → start services[] in their own process groups, wait for readiness
    → run command, capture result
    → SIGTERM/SIGKILL service process groups
    → SET hadron:e2e:{run_id}:result    (JSON)

Every stdout/stderr line is teed to `hadron:cr:{cr_id}:{repo_name}:worker_log`
with an `[E2E]` prefix so the dashboard shows them interleaved with worker
logs — no new endpoint needed.

A sentinel payload `__hadron_shutdown__` on the queue exits the loop cleanly.
A 3600 s BLPOP timeout + K8s Job TTL back each other up for leaked pods.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import shlex
import shutil
import signal
import socket
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis

WORKSPACE = Path(os.environ.get("HADRON_WORKSPACE_DIR", "/workspace")) / "repo"
OUTPUT_TAIL_CHARS = 8192
BLPOP_TIMEOUT_S = 3600
SENTINEL = "__hadron_shutdown__"
SERVICE_TERM_GRACE_S = 5

# Chunk stdout into bounded log lines — we don't want a multi-MB line
# choking the Redis log key.
LOG_LINE_MAX = 4096


# ---------------------------------------------------------------------------
# Logging — tee everything to Redis so the dashboard shows runner output
# ---------------------------------------------------------------------------


class RedisLogger:
    """Append log lines to the shared worker_log Redis key with `[E2E] ` prefix."""

    def __init__(self, redis: aioredis.Redis, log_key: str) -> None:
        self._redis = redis
        self._key = log_key

    async def write(self, line: str) -> None:
        if not line:
            return
        chunk = f"[E2E] {line.rstrip()}\n"
        try:
            await self._redis.append(self._key, chunk)
            await self._redis.expire(self._key, 86400)
        except Exception:
            pass  # best-effort — never let logging kill the run

    async def info(self, line: str) -> None:
        await self.write(line)
        print(line, flush=True)


# ---------------------------------------------------------------------------
# Process group helpers
# ---------------------------------------------------------------------------


async def _stream_to_logger(stream: asyncio.StreamReader, logger: RedisLogger) -> None:
    """Drain a subprocess pipe into the Redis logger, line by line."""
    while True:
        line = await stream.readline()
        if not line:
            return
        text = line.decode(errors="replace")
        if len(text) > LOG_LINE_MAX:
            text = text[:LOG_LINE_MAX] + "...[truncated]"
        await logger.write(text)


async def _run_command(
    cmd: str,
    cwd: Path,
    env: dict[str, str],
    logger: RedisLogger,
    timeout: int | None,
) -> tuple[int, str]:
    """Run a command in its own process group, teeing stdout to Redis.

    Returns (exit_code, captured_output). On timeout, kills the whole process
    group with SIGTERM then SIGKILL.
    """
    await logger.info(f"$ {cmd}")
    captured: list[str] = []

    class _Tee(RedisLogger):
        async def write(self, line: str) -> None:  # type: ignore[override]
            await super().write(line)
            captured.append(line)

    tee = _Tee(logger._redis, logger._key)

    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,  # own process group for clean killpg
    )

    pump = asyncio.create_task(_stream_to_logger(proc.stdout, tee))  # type: ignore[arg-type]

    try:
        exit_code = await asyncio.wait_for(proc.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        await logger.info(f"TIMEOUT after {timeout}s — killing process group")
        _killpg(proc.pid, signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), timeout=SERVICE_TERM_GRACE_S)
        except asyncio.TimeoutError:
            _killpg(proc.pid, signal.SIGKILL)
            await proc.wait()
        exit_code = proc.returncode if proc.returncode is not None else 124

    await pump
    output = "".join(captured)
    return exit_code, output


async def _start_service(
    spec: dict[str, Any],
    cwd: Path,
    base_env: dict[str, str],
    logger: RedisLogger,
) -> asyncio.subprocess.Process:
    """Start a long-running service in its own process group."""
    name = spec.get("name", "service")
    cmd = spec["command"]
    env = {**base_env, **spec.get("env", {})}
    await logger.info(f"[service:{name}] starting: {cmd}")
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    # Stream service logs in the background
    asyncio.create_task(_stream_to_logger(proc.stdout, logger))  # type: ignore[arg-type]
    return proc


def _killpg(pid: int, sig: int) -> None:
    try:
        os.killpg(os.getpgid(pid), sig)
    except (ProcessLookupError, PermissionError):
        pass


async def _stop_service(
    proc: asyncio.subprocess.Process, name: str, logger: RedisLogger,
) -> None:
    await logger.info(f"[service:{name}] stopping (SIGTERM)")
    _killpg(proc.pid, signal.SIGTERM)
    try:
        await asyncio.wait_for(proc.wait(), timeout=SERVICE_TERM_GRACE_S)
    except asyncio.TimeoutError:
        await logger.info(f"[service:{name}] SIGKILL after {SERVICE_TERM_GRACE_S}s")
        _killpg(proc.pid, signal.SIGKILL)
        await proc.wait()


async def _wait_ready(spec: dict[str, Any], logger: RedisLogger) -> bool:
    """Poll wait_url (preferred) or wait_tcp until it answers.

    Returns True if ready within wait_timeout, else False.
    """
    name = spec.get("name", "service")
    timeout = spec.get("wait_timeout", 60)
    url = spec.get("wait_url")
    tcp = spec.get("wait_tcp")
    deadline = time.monotonic() + timeout

    if not url and not tcp:
        await logger.info(f"[service:{name}] no readiness probe declared — skipping wait")
        return True

    while time.monotonic() < deadline:
        if url:
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if 200 <= resp.status < 500:
                        await logger.info(f"[service:{name}] ready @ {url}")
                        return True
            except (urllib.error.URLError, OSError, ValueError):
                pass
        elif tcp:
            try:
                with socket.create_connection(("127.0.0.1", int(tcp)), timeout=2):
                    await logger.info(f"[service:{name}] TCP ready @ :{tcp}")
                    return True
            except OSError:
                pass
        await asyncio.sleep(1)

    await logger.info(f"[service:{name}] NOT ready within {timeout}s")
    return False


# ---------------------------------------------------------------------------
# Per-run execution
# ---------------------------------------------------------------------------


async def _execute_run(
    redis: aioredis.Redis,
    run_id: str,
    logger: RedisLogger,
) -> None:
    """Fetch source + contract, execute, write result."""
    src_key = f"hadron:e2e:{run_id}:src"
    cmd_key = f"hadron:e2e:{run_id}:cmd"
    result_key = f"hadron:e2e:{run_id}:result"

    await logger.info(f"=== run {run_id} starting ===")

    tarball = await redis.get(src_key)
    cmd_json = await redis.get(cmd_key)
    if tarball is None or cmd_json is None:
        await _write_result(redis, result_key, False, "missing src or cmd key in Redis", 2, logger)
        return

    contract: dict[str, Any] = json.loads(cmd_json)
    setup: list[str] = contract.get("setup", []) or []
    services: list[dict[str, Any]] = contract.get("services", []) or []
    command: str = contract.get("command", "")
    timeout: int = int(contract.get("timeout", 600))
    extra_env: dict[str, str] = contract.get("env", {}) or {}

    # Wipe and extract
    if WORKSPACE.exists():
        shutil.rmtree(WORKSPACE)
    WORKSPACE.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as tf:
        tf.extractall(WORKSPACE)  # noqa: S202 — trusted tarball from our own worker
    await logger.info(f"extracted {len(tarball)} bytes into {WORKSPACE}")

    env = {**os.environ, **extra_env}
    env.setdefault("CI", "true")
    env.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/ms-playwright")

    # Refresh Chromium to match the target repo's pinned Playwright version.
    # No-op when versions match the baked-in one (common case).
    if (WORKSPACE / "package.json").exists():
        rc, _ = await _run_command(
            "npx --yes playwright install chromium",
            WORKSPACE, env, logger, timeout=300,
        )
        if rc != 0:
            await logger.info("playwright install returned non-zero; continuing anyway")

    # Setup steps — fail fast
    for step in setup:
        rc, output = await _run_command(step, WORKSPACE, env, logger, timeout=timeout)
        if rc != 0:
            await _write_result(redis, result_key, False,
                                f"setup step failed ({rc}): {step}\n{_tail(output)}",
                                rc, logger)
            return

    # Services — start all, then wait for each
    service_procs: list[tuple[str, asyncio.subprocess.Process]] = []
    try:
        for spec in services:
            proc = await _start_service(spec, WORKSPACE, env, logger)
            service_procs.append((spec.get("name", "service"), proc))
        for spec, (name, proc) in zip(services, service_procs):
            if not await _wait_ready(spec, logger):
                await _write_result(redis, result_key, False,
                                    f"service {name} did not become ready", 1, logger)
                return

        # The test command
        rc, output = await _run_command(command, WORKSPACE, env, logger, timeout=timeout)
        await _write_result(redis, result_key, rc == 0, _tail(output), rc, logger)
    finally:
        for name, proc in reversed(service_procs):
            await _stop_service(proc, name, logger)


def _tail(s: str) -> str:
    return s[-OUTPUT_TAIL_CHARS:] if len(s) > OUTPUT_TAIL_CHARS else s


async def _write_result(
    redis: aioredis.Redis,
    key: str,
    passed: bool,
    output: str,
    exit_code: int,
    logger: RedisLogger,
) -> None:
    payload = json.dumps({"passed": passed, "output": output, "exit_code": exit_code})
    await redis.set(key, payload, ex=3600)
    await logger.info(f"=== run result: passed={passed} exit_code={exit_code} ===")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


async def main() -> None:
    cr_id = os.environ["HADRON_CR_ID"]
    repo = os.environ["HADRON_REPO_NAME"]
    redis_url = os.environ["HADRON_REDIS_URL"]

    redis = await aioredis.from_url(redis_url)
    log_key = f"hadron:cr:{cr_id}:{repo}:worker_log"
    queue_key = f"hadron:e2e:{cr_id}:{repo}:queue"
    logger = RedisLogger(redis, log_key)

    await logger.info(f"runner ready: cr={cr_id} repo={repo} queue={queue_key}")

    try:
        while True:
            try:
                popped = await redis.blpop([queue_key], timeout=BLPOP_TIMEOUT_S)
            except Exception as e:
                await logger.info(f"BLPOP error: {e} — retrying in 5s")
                await asyncio.sleep(5)
                continue

            if popped is None:
                await logger.info(f"idle {BLPOP_TIMEOUT_S}s with no work — exiting")
                return

            _, payload = popped
            run_id = payload.decode() if isinstance(payload, bytes) else str(payload)
            if run_id == SENTINEL:
                await logger.info("sentinel received — exiting cleanly")
                return

            try:
                await _execute_run(redis, run_id, logger)
            except Exception as e:
                await logger.info(f"runner error: {e!r}")
                result_key = f"hadron:e2e:{run_id}:result"
                await _write_result(redis, result_key, False, f"runner exception: {e}", 1, logger)
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())

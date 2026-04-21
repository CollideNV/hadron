"""Worker infrastructure setup — connection factories for all dependencies."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import redis.asyncio as aioredis
import structlog

from hadron.agent.factory import create_agent_backend
from hadron.db.engine import create_engine, create_session_factory
from hadron.events.bus import RedisEventBus
from hadron.events.interventions import InterventionManager

logger = structlog.stdlib.get_logger(__name__)


class OpencodeServeManager:
    """Manages an ``opencode serve`` subprocess lifecycle.

    Spawns the process, waits for it to be healthy, and tears it down on close.
    """

    def __init__(
        self,
        cwd: str,
        *,
        provider_id: str = "ollama",
        provider_base_url: str = "http://host.docker.internal:11434/v1",
        port: int = 0,
    ) -> None:
        self._cwd = cwd
        self._provider_id = provider_id
        self._provider_base_url = provider_base_url
        self._port = port  # 0 = OS picks a free port
        self._process: asyncio.subprocess.Process | None = None
        self._actual_port: int | None = None
        self._config_dir: str | None = None

    @property
    def base_url(self) -> str:
        if self._actual_port is None:
            raise RuntimeError("OpencodeServeManager has not been started")
        return f"http://127.0.0.1:{self._actual_port}"

    async def start(self) -> str:
        """Start ``opencode serve`` and return its base URL when healthy."""
        # Write provider config into a temp directory so opencode picks it up.
        self._config_dir = tempfile.mkdtemp(prefix="hadron-opencode-")
        config = self._build_config()
        Path(self._config_dir, "opencode.json").write_text(json.dumps(config))

        self._process = await asyncio.create_subprocess_exec(
            "opencode", "serve",
            "--port", str(self._port),
            "--hostname", "127.0.0.1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._config_dir,
        )

        # Discover the actual port.  When --port 0 is used, opencode prints
        # the listening address on stdout.  We also try a port-scan fallback.
        self._actual_port = await self._discover_port()

        # Wait for the server to be reachable.
        url = f"http://127.0.0.1:{self._actual_port}"
        await self._wait_healthy(url, timeout=30)
        logger.info("opencode_serve_ready", url=url, pid=self._process.pid)
        return url

    async def stop(self) -> None:
        """Terminate the subprocess gracefully."""
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            logger.info("opencode_serve_stopped", pid=self._process.pid)
        if self._config_dir:
            shutil.rmtree(self._config_dir, ignore_errors=True)

    def _build_config(self) -> dict:
        return {
            "provider": {
                self._provider_id: {
                    "npm": "@ai-sdk/openai-compatible",
                    "options": {"baseURL": self._provider_base_url},
                },
            },
        }

    async def _discover_port(self) -> int:
        """Read the listening port from stdout or fall back to the requested port."""
        if self._port != 0:
            return self._port

        assert self._process and self._process.stdout
        # opencode prints something like "listening on 127.0.0.1:12345"
        try:
            line = await asyncio.wait_for(self._process.stdout.readline(), timeout=10)
            text = line.decode().strip()
            # Try to parse port from the line
            if ":" in text:
                port_str = text.rsplit(":", 1)[-1].strip().rstrip("/")
                if port_str.isdigit():
                    return int(port_str)
        except (asyncio.TimeoutError, ValueError):
            pass

        raise RuntimeError(
            "Could not discover opencode serve port.  "
            "Pass an explicit --port to OpencodeServeManager."
        )

    @staticmethod
    async def _wait_healthy(url: str, timeout: float = 30) -> None:
        deadline = asyncio.get_event_loop().time() + timeout
        async with httpx.AsyncClient() as http:
            while asyncio.get_event_loop().time() < deadline:
                try:
                    resp = await http.get(f"{url}/health", timeout=2)
                    if resp.status_code < 500:
                        return
                except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException):
                    pass
                await asyncio.sleep(0.5)
        raise RuntimeError(f"opencode serve did not become healthy at {url} within {timeout}s")


class BackendPool:
    """Lazily creates and caches agent backends by name."""

    def __init__(self, cfg: Any, opencode_endpoints: list[dict] | None = None) -> None:
        self._cfg = cfg
        self._cache: dict[str, Any] = {}
        self._opencode_endpoints: dict[str, dict] = {
            f"opencode:{ep['slug']}": ep for ep in (opencode_endpoints or [])
        }

    def set_opencode_endpoints(self, endpoints: list[dict]) -> None:
        """Update endpoints (called after config snapshot is loaded)."""
        self._opencode_endpoints = {f"opencode:{ep['slug']}": ep for ep in endpoints}
        # Invalidate cached opencode endpoint backends
        for key in list(self._cache):
            if key.startswith("opencode:"):
                del self._cache[key]

    def get(self, name: str) -> Any:
        if name not in self._cache:
            opencode_url = getattr(self._cfg, "opencode_base_url", "")
            if name in self._opencode_endpoints:
                opencode_url = self._opencode_endpoints[name]["base_url"]
            self._cache[name] = create_agent_backend(
                name,
                anthropic_api_key=getattr(self._cfg, "anthropic_api_key", ""),
                gemini_api_key=getattr(self._cfg, "gemini_api_key", ""),
                openai_api_key=getattr(self._cfg, "openai_api_key", ""),
                opencode_base_url=opencode_url,
            )
        return self._cache[name]


@dataclass
class WorkerInfra:
    """Infrastructure connections for a worker run."""

    engine: Any
    session_factory: Any
    redis_client: aioredis.Redis
    event_bus: RedisEventBus
    intervention_mgr: InterventionManager
    backend_pool: BackendPool
    default_backend_name: str = "claude"
    opencode_serve: OpencodeServeManager | None = None

    @property
    def agent_backend(self) -> Any:
        """Default agent backend (backwards compatible)."""
        return self.backend_pool.get(self.default_backend_name)

    async def close(self) -> None:
        if self.opencode_serve:
            await self.opencode_serve.stop()
        await self.redis_client.aclose()
        await self.engine.dispose()


def connect(cfg: Any) -> WorkerInfra:
    """Create all infrastructure connections from bootstrap config."""
    engine = create_engine(cfg.postgres_url)
    session_factory = create_session_factory(engine)
    redis_client = aioredis.from_url(cfg.redis_url)
    default_backend_name = getattr(cfg, "agent_backend", "claude")
    pool = BackendPool(cfg)
    return WorkerInfra(
        engine=engine,
        session_factory=session_factory,
        redis_client=redis_client,
        event_bus=RedisEventBus(redis_client),
        intervention_mgr=InterventionManager(redis_client),
        backend_pool=pool,
        default_backend_name=default_backend_name,
    )

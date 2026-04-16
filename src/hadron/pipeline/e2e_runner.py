"""E2E runner lifecycle — CR-scoped Playwright runner pod management.

A single runner pod is spawned at Worktree Setup when E2E is detected, lives
through the CR's Review ↔ Rework iterations, and is terminated by sentinel
at the Release node. Workers communicate with the pod via Redis:

  hadron:e2e:{cr_id}:{repo_name}:queue   LIST — run IDs (or sentinel)
  hadron:e2e:{run_id}:src                BYTES — gzipped worktree tarball
  hadron:e2e:{run_id}:cmd                JSON — {setup, services, command, timeout, env}
  hadron:e2e:{run_id}:result             JSON — {passed, output, exit_code}

The worker pod requires RBAC to create Jobs + read pod logs (granted by the
`hadron-worker` ServiceAccount bound to the existing `hadron-job-manager`
Role). See k8s/base/rbac.yaml.

Design notes:
- `ensure_running` is idempotent — label lookup first, so worker pods that
  resume after a checkpoint-and-terminate cycle re-attach to the existing
  runner rather than spawning a new one.
- `submit` streams the whole tarball through Redis (typical webapp worktree
  is 5–50 MB gzipped — well under the 512 MB value-size ceiling).
- `shutdown` pushes a sentinel string; the K8s Job's `ttl_seconds_after_finished`
  is the backstop if any terminal path forgets to call it.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import tarfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from hadron.observability.tracing import inject_trace_context

logger = logging.getLogger(__name__)

# Runner loop exit signal (must match SENTINEL in scripts/run-e2e.py)
SENTINEL = "__hadron_shutdown__"

# Result polling — wait a bit past the per-run timeout for the runner to write back
_RESULT_POLL_S = 2
_RESULT_GRACE_S = 60

# Tarball excludes — keep payload to source-only, runner reinstalls deps
_TAR_EXCLUDES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "target",
    "build",
    "dist",
    ".next",
    ".svelte-kit",
    "test-results",
    "playwright-report",
    ".gradle",
}


StackHint = Literal["node", "node_python", "node_jvm", "node_jvm_python"]


@dataclass
class ServiceSpec:
    """A long-running service the runner must start before the test command."""

    name: str
    command: str
    wait_url: str | None = None
    wait_tcp: int | None = None
    wait_timeout: int = 60
    env: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "command": self.command,
                             "wait_timeout": self.wait_timeout}
        if self.wait_url:
            d["wait_url"] = self.wait_url
        if self.wait_tcp is not None:
            d["wait_tcp"] = self.wait_tcp
        if self.env:
            d["env"] = self.env
        return d


@dataclass
class E2EContract:
    """What the worker sends to the runner for one test execution."""

    command: str
    setup: list[str] = field(default_factory=list)
    services: list[ServiceSpec] = field(default_factory=list)
    timeout: int = 600
    env: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "command": self.command,
            "setup": self.setup,
            "services": [s.to_dict() for s in self.services],
            "timeout": self.timeout,
            "env": self.env,
        })


# ---------------------------------------------------------------------------
# Stack-hint → resources table
# ---------------------------------------------------------------------------


_RESOURCES: dict[StackHint, dict[str, dict[str, str]]] = {
    "node":              {"requests": {"memory": "512Mi",  "cpu": "250m"}, "limits": {"memory": "1536Mi", "cpu": "1"}},
    "node_python":       {"requests": {"memory": "768Mi",  "cpu": "250m"}, "limits": {"memory": "2Gi",    "cpu": "1"}},
    "node_jvm":          {"requests": {"memory": "1536Mi", "cpu": "500m"}, "limits": {"memory": "3Gi",    "cpu": "2"}},
    "node_jvm_python":   {"requests": {"memory": "1792Mi", "cpu": "500m"}, "limits": {"memory": "3584Mi", "cpu": "2"}},
}


def derive_stack_hint(languages: list[str], worktree_path: str) -> StackHint:
    """Pick the tightest resource tier that covers the detected stack.

    We treat "node" as always present because Playwright is npm-based even
    when the backend is Java or Python. JVM presence is detected by pom.xml /
    build.gradle; Python by pyproject.toml / requirements.txt.
    """
    base = Path(worktree_path)
    has_jvm = any(
        (base / f).exists() or any(base.glob(f"**/{f}"))
        for f in ("pom.xml", "build.gradle", "build.gradle.kts")
    )
    has_python = "python" in languages or any(
        (base / f).exists()
        for f in ("pyproject.toml", "setup.py", "requirements.txt")
    )
    if has_jvm and has_python:
        return "node_jvm_python"
    if has_jvm:
        return "node_jvm"
    if has_python:
        return "node_python"
    return "node"


# ---------------------------------------------------------------------------
# Contract builder — turns detection output into a defensive contract
# ---------------------------------------------------------------------------


_WEBSERVER_RE = re.compile(r"webServer\s*:", re.MULTILINE)


def _has_playwright_webserver(worktree_path: Path) -> bool:
    """Scan for a `webServer:` block in any playwright.config.* file.

    If present, the target repo handles server lifecycle itself via Playwright —
    we leave `services` empty.
    """
    for name in ("playwright.config.ts", "playwright.config.js", "playwright.config.mjs"):
        for cfg in [worktree_path / name, *worktree_path.glob(f"*/{name}")]:
            if cfg.is_file():
                try:
                    if _WEBSERVER_RE.search(cfg.read_text(errors="replace")):
                        return True
                except OSError:
                    pass
    return False


def build_e2e_contract(
    worktree_path: str,
    command: str,
    env: dict[str, str],
    timeout: int,
    languages: list[str],
) -> E2EContract:
    """Turn detection output + the E2E command into a runner contract.

    Precedence:
      1. playwright.config.* declares `webServer:` → trust Playwright, no services.
      2. Else synthesize defensive services from stack markers (Java jar, etc.).
      3. Otherwise empty — runner just runs `command` and hopes target repo handles it.
    """
    base = Path(worktree_path)
    setup: list[str] = []
    services: list[ServiceSpec] = []

    if not _has_playwright_webserver(base):
        # No webServer block — worker synthesizes server startup.
        # Stack markers live at root or one directory deep (monorepo layout).
        backend_port = env.get("HADRON_TEST_BACKEND_PORT", "8080")

        if (base / "pom.xml").exists():
            setup.append("mvn -q -DskipTests package")
            services.append(ServiceSpec(
                name="backend",
                command="java -jar target/*.jar",
                wait_tcp=int(backend_port),
                wait_timeout=90,
                env={"SERVER_PORT": backend_port},
            ))
        elif (base / "build.gradle").exists() or (base / "build.gradle.kts").exists():
            setup.append("./gradlew --no-daemon -x test build")
            services.append(ServiceSpec(
                name="backend",
                command="./gradlew --no-daemon bootRun",
                wait_tcp=int(backend_port),
                wait_timeout=120,
                env={"SERVER_PORT": backend_port},
            ))
        # Python/Node backends: leave services empty and let `command` handle
        # them — uvicorn/flask/node servers are usually started by the test
        # harness itself. We'll add defensive fallbacks if usage data shows
        # they're needed.

    return E2EContract(
        command=command,
        setup=setup,
        services=services,
        timeout=timeout,
        env=env,
    )


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def _label_safe(s: str) -> str:
    """K8s labels: lowercase alphanumeric + '-'; max 63 chars."""
    s = re.sub(r"[^A-Za-z0-9-]+", "-", s).lower().strip("-")
    return s[:63] or "x"


class E2ERunnerLifecycle:
    """CR-scoped Playwright runner. Idempotent ensure/submit/shutdown by label."""

    def __init__(
        self,
        namespace: str = "hadron",
        image: str | None = None,
        service_account: str = "hadron-worker",
        redis: Any = None,
    ) -> None:
        self._namespace = namespace
        self._image = image or os.environ.get("HADRON_E2E_RUNNER_IMAGE", "hadron-e2e-runner:latest")
        self._sa = service_account
        self._redis = redis

    # -- K8s plumbing ------------------------------------------------------

    def _k8s_batch(self) -> Any:
        from kubernetes import client, config as k8s_config
        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            k8s_config.load_kube_config()
        return client.BatchV1Api()

    def _job_name(self, cr_id: str, repo_name: str) -> str:
        return f"hadron-e2e-runner-{_label_safe(cr_id)}-{_label_safe(repo_name)}"[:63]

    def _queue_key(self, cr_id: str, repo_name: str) -> str:
        return f"hadron:e2e:{cr_id}:{repo_name}:queue"

    async def _job_exists(self, cr_id: str, repo_name: str) -> bool:
        batch = self._k8s_batch()
        selector = f"app=hadron-e2e-runner,cr-id={_label_safe(cr_id)},repo-name={_label_safe(repo_name)}"
        loop = asyncio.get_event_loop()
        jobs = await loop.run_in_executor(
            None,
            lambda: batch.list_namespaced_job(namespace=self._namespace, label_selector=selector),
        )
        for job in jobs.items:
            status = job.status or None
            if status and status.failed and (status.failed or 0) > 0 and not status.active:
                continue
            return True
        return False

    # -- Public API --------------------------------------------------------

    async def ensure_running(
        self,
        cr_id: str,
        repo_name: str,
        stack_hint: StackHint,
    ) -> None:
        """Create the runner Job if one isn't already alive for this CR-repo."""
        if await self._job_exists(cr_id, repo_name):
            logger.info("E2E runner for %s:%s already exists", cr_id, repo_name)
            return

        from kubernetes import client

        res = _RESOURCES[stack_hint]
        name = self._job_name(cr_id, repo_name)

        env = [
            client.V1EnvVar(name="HADRON_CR_ID", value=cr_id),
            client.V1EnvVar(name="HADRON_REPO_NAME", value=repo_name),
            client.V1EnvVar(
                name="HADRON_ANTHROPIC_API_KEY",
                value_from=client.V1EnvVarSource(
                    secret_key_ref=client.V1SecretKeySelector(
                        name="hadron-secrets", key="anthropic-api-key", optional=True,
                    ),
                ),
            ),
        ] + [
            client.V1EnvVar(name=k, value=v)
            for k, v in inject_trace_context().items()
        ]

        labels = {
            "app": "hadron-e2e-runner",
            "cr-id": _label_safe(cr_id),
            "repo-name": _label_safe(repo_name),
        }

        job = client.V1Job(
            metadata=client.V1ObjectMeta(
                name=name, namespace=self._namespace, labels=labels,
            ),
            spec=client.V1JobSpec(
                backoff_limit=1,
                ttl_seconds_after_finished=3600,
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels=labels),
                    spec=client.V1PodSpec(
                        restart_policy="Never",
                        service_account_name=self._sa,
                        containers=[
                            client.V1Container(
                                name="runner",
                                image=self._image,
                                image_pull_policy="IfNotPresent",
                                env_from=[
                                    client.V1EnvFromSource(
                                        config_map_ref=client.V1ConfigMapEnvSource(
                                            name="hadron-config",
                                        ),
                                    ),
                                ],
                                env=env,
                                resources=client.V1ResourceRequirements(
                                    requests=res["requests"],
                                    limits=res["limits"],
                                ),
                            ),
                        ],
                    ),
                ),
            ),
        )

        batch = self._k8s_batch()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: batch.create_namespaced_job(namespace=self._namespace, body=job),
        )
        logger.info("E2E runner Job %s created (stack=%s)", name, stack_hint)

    async def submit(
        self,
        cr_id: str,
        repo_name: str,
        worktree_path: str,
        contract: E2EContract,
    ) -> tuple[bool, str]:
        """Push tarball + contract, enqueue run_id, wait for result."""
        if self._redis is None:
            return False, "E2ERunnerLifecycle: no redis client configured"

        run_id = uuid.uuid4().hex
        src_key = f"hadron:e2e:{run_id}:src"
        cmd_key = f"hadron:e2e:{run_id}:cmd"
        result_key = f"hadron:e2e:{run_id}:result"
        queue_key = self._queue_key(cr_id, repo_name)

        tarball = await asyncio.get_event_loop().run_in_executor(
            None, _tar_worktree, worktree_path,
        )
        logger.info("E2E submit cr=%s repo=%s run=%s tar=%d bytes",
                    cr_id, repo_name, run_id, len(tarball))

        await self._redis.set(src_key, tarball, ex=3600)
        await self._redis.set(cmd_key, contract.to_json(), ex=3600)
        await self._redis.lpush(queue_key, run_id)

        deadline = time.monotonic() + contract.timeout + _RESULT_GRACE_S
        try:
            while time.monotonic() < deadline:
                raw = await self._redis.get(result_key)
                if raw is not None:
                    data = json.loads(raw)
                    return bool(data.get("passed", False)), str(data.get("output", ""))
                await asyncio.sleep(_RESULT_POLL_S)
            return False, f"E2E runner timed out after {contract.timeout + _RESULT_GRACE_S}s (no result)"
        finally:
            # Leave result_key so a second reader could see it; we delete to
            # keep Redis clean. TTL covers any exception path.
            try:
                await self._redis.delete(src_key, cmd_key, result_key)
            except Exception:
                pass

    async def shutdown(self, cr_id: str, repo_name: str) -> None:
        """Send the sentinel so the runner exits its loop cleanly."""
        if self._redis is None:
            return
        queue_key = self._queue_key(cr_id, repo_name)
        try:
            await self._redis.lpush(queue_key, SENTINEL)
            logger.info("E2E runner shutdown sentinel sent for %s:%s", cr_id, repo_name)
        except Exception as e:
            logger.warning("E2E runner shutdown signal failed for %s:%s: %s",
                           cr_id, repo_name, e)


# ---------------------------------------------------------------------------
# Tarball helper (worker → runner transport)
# ---------------------------------------------------------------------------


def _tar_worktree(worktree_path: str) -> bytes:
    """Tar + gzip a worktree, excluding build artefacts and caches."""
    base = Path(worktree_path)
    buf = io.BytesIO()

    def _filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
        parts = Path(info.name).parts
        for p in parts:
            if p in _TAR_EXCLUDES:
                return None
        return info

    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=6) as tf:
        tf.add(str(base), arcname=".", filter=_filter)

    return buf.getvalue()

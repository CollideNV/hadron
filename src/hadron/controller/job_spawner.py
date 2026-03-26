"""Job spawner — spawns worker processes/Jobs for pipeline execution."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Protocol

from hadron.git.url import extract_repo_name

logger = logging.getLogger(__name__)


class JobSpawner(Protocol):
    """Protocol for job spawner implementations."""

    async def spawn(
        self, cr_id: str, repo_url: str, repo_name: str = "",
        default_branch: str = "main", extra_env: dict[str, str] | None = None,
    ) -> None: ...


class SubprocessJobSpawner:
    """Spawns workers as local subprocesses. For local dev and testing."""

    def __init__(self, redis: Any = None) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._redis = redis

    async def spawn(
        self, cr_id: str, repo_url: str, repo_name: str = "",
        default_branch: str = "main", extra_env: dict[str, str] | None = None,
    ) -> None:
        """Spawn a worker subprocess for a single repo within a CR."""
        if not repo_name:
            repo_name = extract_repo_name(repo_url)
        worker_key = f"{cr_id}:{repo_name}"
        logger.info("Spawning subprocess worker for CR %s, repo %s", cr_id, repo_name)
        env = dict(os.environ)
        if extra_env:
            env.update(extra_env)
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "hadron.worker.main",
            f"--cr-id={cr_id}",
            f"--repo-url={repo_url}",
            f"--repo-name={repo_name}",
            f"--default-branch={default_branch}",
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self._processes[worker_key] = proc

        # Fire and forget — log output in background
        asyncio.create_task(self._log_output(worker_key, proc))

    async def _log_output(self, worker_key: str, proc: asyncio.subprocess.Process) -> None:
        """Stream worker output line-by-line to logs and Redis."""
        redis_key = f"hadron:cr:{worker_key}:worker_log"
        try:
            assert proc.stdout is not None
            # Clear any stale log from a previous run
            if self._redis:
                try:
                    await self._redis.delete(redis_key)
                except Exception:
                    logger.warning("Failed to clear stale worker log in Redis for %s", worker_key, exc_info=True)

            async for raw_line in proc.stdout:
                line = raw_line.decode(errors="replace").rstrip("\n")
                logger.info("[worker:%s] %s", worker_key, line)
                # Append each line to Redis so the UI can poll incrementally
                if self._redis:
                    try:
                        await self._redis.append(redis_key, line + "\n")
                        await self._redis.expire(redis_key, 86400)
                    except Exception:
                        logger.debug("Failed to write worker log line to Redis for %s", worker_key, exc_info=True)

            await proc.wait()
            logger.info("Worker %s exited with code %s", worker_key, proc.returncode)
        except Exception as e:
            logger.error("Error logging worker output for %s: %s", worker_key, e)
        finally:
            self._processes.pop(worker_key, None)


class K8sJobSpawner:
    """Spawns workers as Kubernetes Jobs. For production/K8s deployment."""

    def __init__(
        self,
        namespace: str = "hadron",
        worker_image: str = "hadron-worker:latest",
    ) -> None:
        self._namespace = namespace
        self._worker_image = worker_image

    async def spawn(
        self, cr_id: str, repo_url: str, repo_name: str = "",
        default_branch: str = "main", extra_env: dict[str, str] | None = None,
    ) -> None:
        """Create a K8s Job for a single repo within a CR."""
        from kubernetes import client, config as k8s_config

        if not repo_name:
            repo_name = extract_repo_name(repo_url)

        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            k8s_config.load_kube_config()

        batch_v1 = client.BatchV1Api()

        safe_name = f"{cr_id}-{repo_name}".lower().replace("_", "-")
        job_name = f"hadron-worker-{safe_name}"

        job = client.V1Job(
            metadata=client.V1ObjectMeta(
                name=job_name,
                namespace=self._namespace,
                labels={"app": "hadron-worker", "cr-id": cr_id, "repo-name": repo_name},
            ),
            spec=client.V1JobSpec(
                backoff_limit=1,
                ttl_seconds_after_finished=3600,
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(
                        labels={"app": "hadron-worker", "cr-id": cr_id, "repo-name": repo_name},
                    ),
                    spec=client.V1PodSpec(
                        restart_policy="Never",
                        service_account_name="hadron-controller",
                        containers=[
                            client.V1Container(
                                name="worker",
                                image=self._worker_image,
                                image_pull_policy="Never",
                                command=[
                                    "python", "-m", "hadron.worker.main",
                                    f"--cr-id={cr_id}",
                                    f"--repo-url={repo_url}",
                                    f"--repo-name={repo_name}",
                                    f"--default-branch={default_branch}",
                                ],
                                env_from=[
                                    client.V1EnvFromSource(
                                        config_map_ref=client.V1ConfigMapEnvSource(
                                            name="hadron-config",
                                        )
                                    ),
                                ],
                                env=[
                                    client.V1EnvVar(
                                        name="HADRON_ANTHROPIC_API_KEY",
                                        value_from=client.V1EnvVarSource(
                                            secret_key_ref=client.V1SecretKeySelector(
                                                name="hadron-secrets",
                                                key="anthropic-api-key",
                                            )
                                        ),
                                    ),
                                    client.V1EnvVar(
                                        name="GITHUB_TOKEN",
                                        value_from=client.V1EnvVarSource(
                                            secret_key_ref=client.V1SecretKeySelector(
                                                name="hadron-secrets",
                                                key="github-token",
                                                optional=True,
                                            )
                                        ),
                                    ),
                                ] + [
                                    # DB-stored keys override K8s secrets when set
                                    client.V1EnvVar(name=k, value=v)
                                    for k, v in (extra_env or {}).items()
                                ],
                                resources=client.V1ResourceRequirements(
                                    requests={"memory": "512Mi", "cpu": "500m"},
                                    limits={"memory": "2Gi", "cpu": "2"},
                                ),
                            )
                        ],
                    ),
                ),
            ),
        )

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: batch_v1.create_namespaced_job(namespace=self._namespace, body=job),
        )
        logger.info("K8s Job %s created for CR %s", job_name, cr_id)

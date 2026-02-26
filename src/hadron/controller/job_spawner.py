"""Job spawner — spawns worker processes/Jobs for pipeline execution."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class JobSpawner(Protocol):
    """Protocol for job spawner implementations."""

    async def spawn(self, cr_id: str) -> None: ...


class SubprocessJobSpawner:
    """Spawns workers as local subprocesses. For local dev and testing."""

    def __init__(self, redis: Any = None) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._redis = redis

    async def spawn(self, cr_id: str) -> None:
        """Spawn a worker subprocess for the given CR."""
        logger.info("Spawning subprocess worker for CR %s", cr_id)
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "hadron.worker.main", f"--cr-id={cr_id}",
            env=dict(os.environ),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self._processes[cr_id] = proc

        # Fire and forget — log output in background
        asyncio.create_task(self._log_output(cr_id, proc))

    async def _log_output(self, cr_id: str, proc: asyncio.subprocess.Process) -> None:
        """Log worker output in background and store in Redis."""
        try:
            stdout, _ = await proc.communicate()
            full_output = ""
            if stdout:
                full_output = stdout.decode(errors="replace")
                for line in full_output.splitlines():
                    logger.info("[worker:%s] %s", cr_id, line)
            logger.info("Worker for CR %s exited with code %s", cr_id, proc.returncode)

            # Store in Redis for log retrieval (24h TTL)
            if self._redis and full_output:
                try:
                    await self._redis.set(
                        f"hadron:cr:{cr_id}:worker_log", full_output, ex=86400,
                    )
                except Exception as e:
                    logger.warning("Failed to store worker log in Redis for CR %s: %s", cr_id, e)
        except Exception as e:
            logger.error("Error logging worker output for CR %s: %s", cr_id, e)
        finally:
            self._processes.pop(cr_id, None)


class K8sJobSpawner:
    """Spawns workers as Kubernetes Jobs. For production/K8s deployment."""

    def __init__(
        self,
        namespace: str = "hadron",
        worker_image: str = "hadron-worker:latest",
    ) -> None:
        self._namespace = namespace
        self._worker_image = worker_image

    async def spawn(self, cr_id: str) -> None:
        """Create a K8s Job for the given CR."""
        from kubernetes import client, config as k8s_config

        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            k8s_config.load_kube_config()

        batch_v1 = client.BatchV1Api()

        job_name = f"hadron-worker-{cr_id.lower().replace('_', '-')}"

        job = client.V1Job(
            metadata=client.V1ObjectMeta(
                name=job_name,
                namespace=self._namespace,
                labels={"app": "hadron-worker", "cr-id": cr_id},
            ),
            spec=client.V1JobSpec(
                backoff_limit=1,
                ttl_seconds_after_finished=3600,
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(
                        labels={"app": "hadron-worker", "cr-id": cr_id},
                    ),
                    spec=client.V1PodSpec(
                        restart_policy="Never",
                        containers=[
                            client.V1Container(
                                name="worker",
                                image=self._worker_image,
                                command=["python", "-m", "hadron.worker.main", f"--cr-id={cr_id}"],
                                env_from=[
                                    client.V1EnvFromSource(
                                        config_map_ref=client.V1ConfigMapEnvSource(
                                            name="hadron-config",
                                        )
                                    )
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

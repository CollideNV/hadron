"""Job spawner — spawns worker processes/Jobs for pipeline execution."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, Protocol

import structlog

from hadron.git.url import extract_repo_name
from hadron.observability.tracing import inject_trace_context
from hadron.pipeline.e2e_runner import workspace_pvc_name

logger = structlog.stdlib.get_logger(__name__)


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
        env.update(inject_trace_context())
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
        """Drain worker stdout to the controller log.

        The worker writes its own logs directly to Redis via RedisLogHandler,
        so this method only needs to drain the pipe (preventing the worker
        from blocking on a full stdout buffer) and echo to the controller log.
        """
        try:
            assert proc.stdout is not None
            async for raw_line in proc.stdout:
                line = raw_line.decode(errors="replace").rstrip("\n")
                logger.info("[worker:%s] %s", worker_key, line)

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
        worker_image: str | None = None,
        redis: Any = None,
    ) -> None:
        self._namespace = namespace
        self._worker_image = worker_image or os.environ.get("HADRON_WORKER_IMAGE", "hadron-worker:latest")
        self._redis = redis

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
        core_v1 = client.CoreV1Api()

        safe_name = f"{cr_id}-{repo_name}".lower().replace("_", "-")
        job_name = f"hadron-worker-{safe_name}"
        pvc_name = workspace_pvc_name(cr_id, repo_name)

        # Create shared workspace PVC (idempotent — skip if it already exists
        # from a previous run or checkpoint-resume).
        pvc_size = os.environ.get("HADRON_WORKSPACE_PVC_SIZE", "10Gi")
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                lambda: core_v1.read_namespaced_persistent_volume_claim(
                    name=pvc_name, namespace=self._namespace,
                ),
            )
        except client.ApiException as e:
            if e.status == 404:
                pvc = client.V1PersistentVolumeClaim(
                    metadata=client.V1ObjectMeta(
                        name=pvc_name,
                        namespace=self._namespace,
                        labels={
                            "app": "hadron-workspace",
                            "cr-id": cr_id,
                            "repo-name": repo_name,
                        },
                    ),
                    spec=client.V1PersistentVolumeClaimSpec(
                        access_modes=["ReadWriteOnce"],
                        resources=client.V1VolumeResourceRequirements(
                            requests={"storage": pvc_size},
                        ),
                    ),
                )
                await loop.run_in_executor(
                    None,
                    lambda: core_v1.create_namespaced_persistent_volume_claim(
                        namespace=self._namespace, body=pvc,
                    ),
                )
                logger.info("workspace_pvc_created", pvc=pvc_name, size=pvc_size)
            else:
                raise

        worker_labels = {"app": "hadron-worker", "cr-id": cr_id, "repo-name": repo_name}

        job = client.V1Job(
            metadata=client.V1ObjectMeta(
                name=job_name,
                namespace=self._namespace,
                labels=worker_labels,
            ),
            spec=client.V1JobSpec(
                backoff_limit=1,
                ttl_seconds_after_finished=3600,
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels=worker_labels),
                    spec=client.V1PodSpec(
                        restart_policy="Never",
                        service_account_name="hadron-worker",
                        containers=[
                            client.V1Container(
                                name="worker",
                                image=self._worker_image,
                                image_pull_policy="IfNotPresent",
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
                                                optional=True,
                                            )
                                        ),
                                    ),
                                    client.V1EnvVar(
                                        name="HADRON_GEMINI_API_KEY",
                                        value_from=client.V1EnvVarSource(
                                            secret_key_ref=client.V1SecretKeySelector(
                                                name="hadron-secrets",
                                                key="gemini-api-key",
                                                optional=True,
                                            )
                                        ),
                                    ),
                                    client.V1EnvVar(
                                        name="HADRON_OPENAI_API_KEY",
                                        value_from=client.V1EnvVarSource(
                                            secret_key_ref=client.V1SecretKeySelector(
                                                name="hadron-secrets",
                                                key="openai-api-key",
                                                optional=True,
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
                                    # Trace context propagation (controller → worker)
                                    client.V1EnvVar(name=k, value=v)
                                    for k, v in inject_trace_context().items()
                                ] + [
                                    # DB-stored keys override K8s secrets when set
                                    client.V1EnvVar(name=k, value=v)
                                    for k, v in (extra_env or {}).items()
                                ],
                                resources=client.V1ResourceRequirements(
                                    requests={"memory": "512Mi", "cpu": "500m"},
                                    limits={"memory": "2Gi", "cpu": "2"},
                                ),
                                volume_mounts=[
                                    client.V1VolumeMount(
                                        name="workspace",
                                        mount_path="/workspace",
                                    ),
                                ],
                            )
                        ],
                        volumes=[
                            client.V1Volume(
                                name="workspace",
                                persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                    claim_name=pvc_name,
                                ),
                            ),
                        ],
                    ),
                ),
            ),
        )

        await loop.run_in_executor(
            None,
            lambda: batch_v1.create_namespaced_job(namespace=self._namespace, body=job),
        )
        logger.info("worker_job_created", job=job_name, cr_id=cr_id, pvc=pvc_name)

        # Stream pod logs to Redis in the background so the UI can display them
        if self._redis:
            worker_key = f"{cr_id}:{repo_name}"
            asyncio.create_task(self._stream_pod_logs(worker_key, job_name))

    async def _stream_pod_logs(self, worker_key: str, job_name: str) -> None:
        """Tail K8s pod logs and write them to Redis, mirroring SubprocessJobSpawner."""
        from kubernetes import client, config as k8s_config, watch

        redis_key = f"hadron:cr:{worker_key}:worker_log"
        try:
            try:
                k8s_config.load_incluster_config()
            except k8s_config.ConfigException:
                k8s_config.load_kube_config()

            v1 = client.CoreV1Api()

            # Wait for the pod to be created (up to 60s)
            pod_name = None
            for _ in range(30):
                pods = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: v1.list_namespaced_pod(
                        namespace=self._namespace,
                        label_selector=f"job-name={job_name}",
                    ),
                )
                if pods.items:
                    pod_name = pods.items[0].metadata.name
                    break
                await asyncio.sleep(2)

            if not pod_name:
                logger.warning("No pod found for job %s, cannot stream logs", job_name)
                return

            # Wait for container to be running
            for _ in range(30):
                pod = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: v1.read_namespaced_pod(name=pod_name, namespace=self._namespace),
                )
                phase = pod.status.phase
                if phase in ("Running", "Succeeded", "Failed"):
                    break
                await asyncio.sleep(2)

            # Clear stale logs
            try:
                await self._redis.delete(redis_key)
            except Exception:
                pass

            # Stream logs using the K8s API follow mode
            def _follow_logs() -> None:
                w = watch.Watch()
                for line in w.stream(
                    v1.read_namespaced_pod_log,
                    name=pod_name,
                    namespace=self._namespace,
                    follow=True,
                ):
                    # write synchronously — will be called from executor
                    pass  # yield lines to caller

            # Poll recent logs using since_seconds to bound memory usage.
            # Each iteration fetches only logs from the last interval,
            # preventing unbounded memory growth on long-running pods.
            poll_interval = 3
            while True:
                try:
                    pod = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: v1.read_namespaced_pod(name=pod_name, namespace=self._namespace),
                    )
                    phase = pod.status.phase

                    logs = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: v1.read_namespaced_pod_log(
                            name=pod_name,
                            namespace=self._namespace,
                            since_seconds=poll_interval + 1,
                        ),
                    )
                    if logs:
                        await self._redis.append(redis_key, logs)
                        await self._redis.expire(redis_key, 86400)

                    if phase in ("Succeeded", "Failed"):
                        break
                except Exception:
                    break

                await asyncio.sleep(poll_interval)

            logger.info("Log streaming finished for %s", worker_key)
        except Exception as e:
            logger.error("Error streaming pod logs for %s: %s", worker_key, e)

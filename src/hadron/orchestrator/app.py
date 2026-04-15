"""FastAPI application factory for the Hadron Orchestrator.

Handles pipeline mutations: intake, resume, CI results, interventions,
nudges, and release approval. Designed for KEDA-managed 0→N scaling —
wakes up when there is work to do, scales to zero when idle.

Usage:
    uvicorn hadron.orchestrator.app:create_app --factory --port 8002
"""

from __future__ import annotations

import asyncio
import json as _json
import os

from dotenv import load_dotenv

load_dotenv()
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI

from hadron.config.bootstrap import load_bootstrap_config
from hadron.controller.job_spawner import K8sJobSpawner, SubprocessJobSpawner
from hadron.db.engine import create_engine, create_session_factory
from hadron.events.bus import RedisEventBus
from hadron.events.interventions import InterventionManager
from hadron.observability.logging import configure_logging
from hadron.observability.metrics import METRICS_CHANNEL, record_worker_metrics, metrics_available
from hadron.observability.tracing import configure_tracing

logger = structlog.stdlib.get_logger(__name__)


def _running_in_k8s() -> bool:
    """Detect whether we are running inside a Kubernetes pod."""
    return Path("/var/run/secrets/kubernetes.io/serviceaccount/token").exists()


async def _metrics_listener(redis_client: Any) -> None:
    """Subscribe to the worker metrics channel and record payloads."""
    try:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(METRICS_CHANNEL)
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    payload = _json.loads(message["data"])
                    record_worker_metrics(payload)
                except Exception:
                    logger.debug("Invalid metrics payload", exc_info=True)
    except asyncio.CancelledError:
        return
    except Exception:
        logger.warning("Metrics listener stopped", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage DB + Redis + job spawner across app lifecycle."""
    cfg = load_bootstrap_config()
    configure_logging(level=cfg.log_level, log_format=cfg.log_format)
    configure_tracing(
        enabled=cfg.otel_enabled,
        otlp_endpoint=cfg.otlp_endpoint,
        service_name="hadron-orchestrator",
    )

    engine = create_engine(cfg.postgres_url)
    session_factory = create_session_factory(engine)
    redis_client = aioredis.from_url(cfg.redis_url)

    app.state.config = cfg
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.redis = redis_client
    app.state.event_bus = RedisEventBus(redis_client)
    app.state.intervention_mgr = InterventionManager(redis_client)

    if _running_in_k8s() or os.environ.get("HADRON_USE_K8S", "").lower() in ("1", "true", "yes"):
        logger.info("Using K8sJobSpawner")
        app.state.job_spawner = K8sJobSpawner(redis=redis_client)
    else:
        logger.info("Using SubprocessJobSpawner")
        app.state.job_spawner = SubprocessJobSpawner(redis=redis_client)

    # Background listener for worker metrics via Redis pub/sub
    metrics_task = None
    if metrics_available():
        metrics_task = asyncio.create_task(_metrics_listener(redis_client))

    logger.info("orchestrator_started", port=os.environ.get("PORT", "8002"))

    yield

    if metrics_task:
        metrics_task.cancel()
    await redis_client.aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    """Create the Orchestrator FastAPI application."""
    app = FastAPI(
        title="Hadron Orchestrator",
        description="Pipeline orchestration service — intake, interventions, release",
        version="0.1.0",
        lifespan=lifespan,
    )

    from hadron.observability.middleware import RequestIdMiddleware

    app.add_middleware(RequestIdMiddleware)

    from hadron.controller.routes.intake import router as intake_router
    from hadron.controller.routes.metrics import router as metrics_router
    from hadron.controller.routes.pipeline_ops import router as pipeline_ops_router
    from hadron.controller.routes.release_ops import router as release_ops_router

    app.include_router(metrics_router)
    app.include_router(intake_router, prefix="/api")
    app.include_router(pipeline_ops_router, prefix="/api")
    app.include_router(release_ops_router, prefix="/api")

    # Instrument FastAPI with OpenTelemetry if available
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from hadron.observability.tracing import tracing_available

        if tracing_available():
            FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        pass

    # Health endpoints for K8s probes
    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok", "service": "orchestrator"}

    @app.get("/livez")
    async def livez() -> dict:
        return {"status": "ok"}

    return app

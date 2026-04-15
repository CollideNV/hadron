"""FastAPI application factory for the Hadron controller."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()  # read .env before anything else
import asyncio
import json as _json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from hadron.config.bootstrap import load_bootstrap_config
from hadron.db.engine import create_engine, create_session_factory
from hadron.events.bus import RedisEventBus
from hadron.controller.job_spawner import K8sJobSpawner, SubprocessJobSpawner
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
    """Manage DB + Redis connections across app lifecycle."""
    cfg = load_bootstrap_config()
    configure_logging(level=cfg.log_level, log_format=cfg.log_format)
    configure_tracing(
        enabled=cfg.otel_enabled,
        otlp_endpoint=cfg.otlp_endpoint,
        service_name="hadron-controller",
    )

    engine = create_engine(cfg.postgres_url)
    session_factory = create_session_factory(engine)
    redis_client = aioredis.from_url(cfg.redis_url)

    app.state.config = cfg
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.redis = redis_client
    app.state.event_bus = RedisEventBus(redis_client)

    # Only set up orchestrator dependencies when orchestrator is embedded
    metrics_task = None
    if cfg.embed_orchestrator:
        if _running_in_k8s() or os.environ.get("HADRON_USE_K8S", "").lower() in ("1", "true", "yes"):
            logger.info("Using K8sJobSpawner")
            app.state.job_spawner = K8sJobSpawner(redis=redis_client)
        else:
            logger.info("Using SubprocessJobSpawner")
            app.state.job_spawner = SubprocessJobSpawner(redis=redis_client)

        app.state.intervention_mgr = InterventionManager(redis_client)

        # Start background listener for worker metrics via Redis pub/sub
        if metrics_available():
            metrics_task = asyncio.create_task(_metrics_listener(redis_client))
    else:
        logger.info("Orchestrator routes disabled (running as Dashboard API)")

    yield

    if metrics_task:
        metrics_task.cancel()
    await redis_client.aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Hadron Pipeline Controller",
        description="AI-powered SDLC pipeline by Collide",
        version="0.1.0",
        lifespan=lifespan,
    )

    from hadron.observability.middleware import RequestIdMiddleware

    app.add_middleware(RequestIdMiddleware)

    # --- Dashboard routes (always included) ---
    from hadron.controller.routes.analytics import router as analytics_router
    from hadron.controller.routes.audit import router as audit_router
    from hadron.controller.routes.health import router as health_router
    from hadron.controller.routes.metrics import router as metrics_router
    from hadron.controller.routes.pipeline_queries import router as pipeline_queries_router
    from hadron.controller.routes.prompts import router as prompts_router
    from hadron.controller.routes.release_queries import router as release_queries_router
    from hadron.controller.routes.settings import router as settings_router

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(analytics_router, prefix="/api")
    app.include_router(audit_router, prefix="/api")
    app.include_router(pipeline_queries_router, prefix="/api")
    app.include_router(release_queries_router, prefix="/api")
    app.include_router(prompts_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")

    # SSE routes are embedded by default (local dev). When running a separate
    # SSE gateway (K8s), set HADRON_EMBED_SSE=false to exclude them.
    cfg = load_bootstrap_config()
    if cfg.embed_sse:
        from hadron.controller.routes.events import router as events_router
        app.include_router(events_router, prefix="/api")

    # Orchestrator routes are embedded by default (local dev). When running a
    # separate orchestrator (K8s), set HADRON_EMBED_ORCHESTRATOR=false.
    if cfg.embed_orchestrator:
        from hadron.controller.routes.intake import router as intake_router
        from hadron.controller.routes.pipeline_ops import router as pipeline_ops_router
        from hadron.controller.routes.release_ops import router as release_ops_router

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

    # Mount frontend static files (after API routes so they don't shadow them)
    frontend_dir = os.environ.get(
        "HADRON_FRONTEND_DIR",
        str(Path(__file__).resolve().parents[3] / "frontend" / "dist"),
    )
    if Path(frontend_dir).is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return app

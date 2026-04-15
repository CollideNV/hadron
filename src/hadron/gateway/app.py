"""FastAPI application factory for the Hadron SSE Gateway.

A minimal, always-on service that handles:
1. SSE event streaming (long-lived connections for the dashboard)
2. CI webhook proxy (accepts webhooks and forwards to the controller,
   ensuring webhooks are never lost even when the controller is at zero)

Designed to run alongside the main controller so that the controller
can scale to zero via KEDA without dropping dashboard connections or
missing external webhooks.

Usage:
    uvicorn hadron.gateway.app:create_app --factory --port 8001
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hadron.config.bootstrap import load_bootstrap_config
from hadron.db.engine import create_engine, create_session_factory
from hadron.events.bus import RedisEventBus
from hadron.observability.logging import configure_logging
from hadron.observability.middleware import RequestIdMiddleware

logger = structlog.stdlib.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage Redis + DB connections for the gateway."""
    cfg = load_bootstrap_config()
    configure_logging(level=cfg.log_level, log_format=cfg.log_format)

    engine = create_engine(cfg.postgres_url)
    session_factory = create_session_factory(engine)
    redis_client = aioredis.from_url(cfg.redis_url)

    app.state.config = cfg
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.redis = redis_client
    app.state.event_bus = RedisEventBus(redis_client)

    # HTTP client for proxying CI webhooks to the orchestrator
    orchestrator_url = os.environ.get(
        "HADRON_ORCHESTRATOR_URL",
        "http://hadron-orchestrator:8002",
    )
    app.state.orchestrator_url = orchestrator_url
    app.state.http_client = httpx.AsyncClient(base_url=orchestrator_url, timeout=30.0)

    logger.info("gateway_started", port=os.environ.get("PORT", "8001"))

    yield

    await app.state.http_client.aclose()
    await redis_client.aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    """Create the SSE Gateway FastAPI application."""
    app = FastAPI(
        title="Hadron SSE Gateway",
        description="Lightweight event streaming and webhook gateway for the Hadron dashboard",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(RequestIdMiddleware)

    # SSE event routes
    from hadron.controller.routes.events import router as events_router

    app.include_router(events_router, prefix="/api")

    # CI webhook proxy — accepts the webhook on the always-on gateway and
    # forwards it to the controller, which KEDA will wake up if needed.
    @app.post("/api/pipeline/{cr_id}/ci-result")
    async def proxy_ci_result(cr_id: str, request: Request) -> JSONResponse:
        """Proxy CI result webhook to the controller.

        The gateway is always-on, so external CI systems (GitHub Actions, etc.)
        can reliably deliver webhooks even when the controller is scaled to zero.
        The controller will be woken by KEDA to handle the actual respawn.
        """
        body = await request.body()
        try:
            resp = await request.app.state.http_client.post(
                f"/api/pipeline/{cr_id}/ci-result",
                content=body,
                headers={"Content-Type": "application/json"},
            )
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
        except httpx.ConnectError:
            logger.warning("controller_unreachable", cr_id=cr_id)
            # Store the webhook payload in Redis so it's not lost.
            # The controller can pick it up when it wakes.
            await request.app.state.redis.set(
                f"hadron:cr:{cr_id}:pending_ci_result",
                body,
                ex=3600,
            )
            return JSONResponse(
                content={"status": "queued", "detail": "Controller waking up, webhook queued"},
                status_code=202,
            )

    # Health endpoints for K8s probes
    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok", "service": "gateway"}

    @app.get("/livez")
    async def livez() -> dict:
        return {"status": "ok"}

    return app

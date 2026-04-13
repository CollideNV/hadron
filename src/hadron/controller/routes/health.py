"""Health check endpoints for Kubernetes probes."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

_START_TIME = time.monotonic()


@router.get("/livez")
async def livez() -> dict:
    """Liveness probe — confirms the server process is running."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    """Readiness probe — verifies DB and Redis connections.

    Returns 503 when any dependency is unreachable.
    """
    checks = {"postgres": False, "redis": False}

    try:
        async with request.app.state.session_factory() as session:
            await session.execute(text("SELECT 1"))
            checks["postgres"] = True
    except Exception as e:
        logger.debug("Postgres readiness check failed: %s", e)

    try:
        await request.app.state.redis.ping()
        checks["redis"] = True
    except Exception as e:
        logger.debug("Redis readiness check failed: %s", e)

    ready = all(checks.values())
    status_code = 200 if ready else 503
    return JSONResponse(
        content={"status": "ready" if ready else "not_ready", "checks": checks},
        status_code=status_code,
    )


@router.get("/healthz")
async def healthz(request: Request) -> dict:
    """Health endpoint — application version and uptime."""
    return {
        "status": "ok",
        "version": request.app.version,
        "uptime": round(time.monotonic() - _START_TIME, 1),
    }

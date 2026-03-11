"""Health check endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from sqlalchemy import text

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> dict:
    """Readiness check — verifies DB and Redis connections."""
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
    return {"status": "ready" if ready else "not_ready", "checks": checks}

"""Health check endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

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
            await session.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
            checks["postgres"] = True
    except Exception:
        pass

    try:
        await request.app.state.redis.ping()
        checks["redis"] = True
    except Exception:
        pass

    ready = all(checks.values())
    return {"status": "ready" if ready else "not_ready", "checks": checks}

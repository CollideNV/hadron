"""FastAPI application factory for the Hadron controller."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import redis.asyncio as aioredis
from fastapi import FastAPI

from hadron.config.bootstrap import load_bootstrap_config
from hadron.db.engine import create_engine, create_session_factory
from hadron.events.bus import RedisEventBus
from hadron.events.interventions import InterventionManager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage DB + Redis connections across app lifecycle."""
    cfg = load_bootstrap_config()

    engine = create_engine(cfg.postgres_url)
    session_factory = create_session_factory(engine)
    redis_client = aioredis.from_url(cfg.redis_url)

    app.state.config = cfg
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.redis = redis_client
    app.state.event_bus = RedisEventBus(redis_client)
    app.state.intervention_mgr = InterventionManager(redis_client)

    yield

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

    from hadron.controller.routes.health import router as health_router
    from hadron.controller.routes.intake import router as intake_router
    from hadron.controller.routes.events import router as events_router
    from hadron.controller.routes.pipeline import router as pipeline_router

    app.include_router(health_router)
    app.include_router(intake_router, prefix="/api")
    app.include_router(events_router, prefix="/api")
    app.include_router(pipeline_router, prefix="/api")

    return app

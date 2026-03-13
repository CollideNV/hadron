"""FastAPI dependency injection for controller routes.

Centralizes access to app.state so routes declare explicit dependencies
instead of reaching into ``request.app.state`` directly.
"""

from __future__ import annotations

from fastapi import Request
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hadron.controller.job_spawner import JobSpawner
from hadron.events.bus import EventBus
from hadron.events.interventions import InterventionManager


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """Provide the async session factory."""
    return request.app.state.session_factory


def get_event_bus(request: Request) -> EventBus:
    """Provide the event bus."""
    return request.app.state.event_bus


def get_job_spawner(request: Request) -> JobSpawner:
    """Provide the job spawner."""
    return request.app.state.job_spawner


def get_redis(request: Request) -> aioredis.Redis:
    """Provide the Redis client."""
    return request.app.state.redis


def get_intervention_mgr(request: Request) -> InterventionManager:
    """Provide the intervention manager."""
    return request.app.state.intervention_mgr

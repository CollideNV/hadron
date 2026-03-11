"""FastAPI dependency injection for controller routes.

Centralizes access to app.state so routes declare explicit dependencies
instead of reaching into ``request.app.state`` directly.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from hadron.events.bus import EventBus
from hadron.events.interventions import InterventionManager


def get_session_factory(request: Request) -> Any:
    """Provide the async session factory."""
    return request.app.state.session_factory


def get_event_bus(request: Request) -> EventBus:
    """Provide the event bus."""
    return request.app.state.event_bus


def get_job_spawner(request: Request) -> Any:
    """Provide the job spawner."""
    return request.app.state.job_spawner


def get_redis(request: Request) -> Any:
    """Provide the Redis client."""
    return request.app.state.redis


def get_intervention_mgr(request: Request) -> InterventionManager:
    """Provide the intervention manager."""
    return request.app.state.intervention_mgr

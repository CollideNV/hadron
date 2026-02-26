"""Configuration routes."""

from __future__ import annotations

from fastapi import APIRouter

from hadron.config.providers import list_available_models, PROVIDER_REGISTRY

router = APIRouter(tags=["config"])


@router.get("/config/models")
async def get_models() -> dict[str, list]:
    """Return list of available AI models."""
    return {"models": list_available_models()}


@router.get("/config/providers")
async def get_providers() -> dict[str, list]:
    """Return list of supported providers."""
    providers = []
    for key, val in PROVIDER_REGISTRY.items():
        providers.append({
            "id": key,
            "name": val["name"],
            "configured": True,  # MVP: assume configured if in registry
        })
    return {"providers": providers}

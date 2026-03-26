"""Backend template and pipeline settings management routes."""

from __future__ import annotations

import copy
import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hadron.agent.cost import _MODEL_COSTS
from hadron.config.api_keys import API_KEY_REGISTRY, DB_SETTING_KEY, _load_encrypted_keys
from hadron.config.defaults import PIPELINE_DEFAULTS
from hadron.controller.dependencies import get_session_factory
from hadron.db.models import AuditLog, PipelineSetting
from hadron.security.crypto import decrypt_value, encrypt_value, mask_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class PhaseModel(BaseModel):
    backend: str
    model: str


class StageConfig(BaseModel):
    act: PhaseModel
    explore: PhaseModel | None = None
    plan: PhaseModel | None = None


class BackendTemplate(BaseModel):
    slug: str
    display_name: str
    backend: str
    stages: dict[str, StageConfig]
    base_url: str | None = None
    available_models: list[str] | None = None
    is_default: bool = False


class DefaultTemplateResponse(BaseModel):
    slug: str


class DefaultTemplateUpdate(BaseModel):
    slug: str


# ---------------------------------------------------------------------------
# Built-in templates (fallback when no DB rows exist)
# ---------------------------------------------------------------------------


def _make_stages(backend: str, act_model: str, explore_model: str | None, plan_model: str | None) -> dict[str, dict]:
    """Build stage configs where all stages use the same backend."""
    def _phase(model: str) -> dict:
        return {"backend": backend, "model": model}

    impl_explore = {"backend": backend, "model": explore_model} if explore_model else None
    impl_plan = {"backend": backend, "model": plan_model} if plan_model else None

    return {
        "intake": {"act": _phase(act_model), "explore": None, "plan": None},
        "behaviour_translation": {"act": _phase(act_model), "explore": None, "plan": None},
        "behaviour_verification": {"act": _phase(act_model), "explore": None, "plan": None},
        "implementation": {"act": _phase(act_model), "explore": impl_explore, "plan": impl_plan},
        "review:security_reviewer": {"act": _phase(act_model), "explore": None, "plan": None},
        "review:quality_reviewer": {"act": _phase(act_model), "explore": None, "plan": None},
        "review:spec_compliance_reviewer": {"act": _phase(act_model), "explore": None, "plan": None},
        "rework": {"act": _phase(act_model), "explore": None, "plan": None},
        "rebase": {"act": _phase(act_model), "explore": None, "plan": None},
    }


# Anthropic template uses differentiated models per stage (the original _DEFAULT_STAGES)
_ANTHROPIC_STAGES: dict[str, dict] = {
    "intake": {"act": {"backend": "claude", "model": "claude-haiku-4-5-20251001"}, "explore": None, "plan": None},
    "behaviour_translation": {"act": {"backend": "claude", "model": "claude-sonnet-4-6"}, "explore": None, "plan": None},
    "behaviour_verification": {"act": {"backend": "claude", "model": "claude-haiku-4-5-20251001"}, "explore": None, "plan": None},
    "implementation": {"act": {"backend": "claude", "model": "claude-sonnet-4-6"}, "explore": {"backend": "claude", "model": "claude-haiku-4-5-20251001"}, "plan": {"backend": "claude", "model": "claude-opus-4-6"}},
    "review:security_reviewer": {"act": {"backend": "claude", "model": "claude-sonnet-4-6"}, "explore": None, "plan": None},
    "review:quality_reviewer": {"act": {"backend": "claude", "model": "claude-haiku-4-5-20251001"}, "explore": None, "plan": None},
    "review:spec_compliance_reviewer": {"act": {"backend": "claude", "model": "claude-haiku-4-5-20251001"}, "explore": None, "plan": None},
    "rework": {"act": {"backend": "claude", "model": "claude-sonnet-4-6"}, "explore": None, "plan": None},
    "rebase": {"act": {"backend": "claude", "model": "claude-sonnet-4-6"}, "explore": None, "plan": None},
}

_BUILTIN_TEMPLATES: list[dict] = [
    {
        "slug": "anthropic",
        "display_name": "Anthropic",
        "backend": "claude",
        "stages": _ANTHROPIC_STAGES,
    },
    {
        "slug": "openai",
        "display_name": "OpenAI",
        "backend": "openai",
        "stages": _make_stages("openai", "gpt-4.1", "gpt-4.1-mini", "o3"),
    },
    {
        "slug": "gemini",
        "display_name": "Gemini",
        "backend": "gemini",
        "stages": _make_stages("gemini", "gemini-2.5-pro", "gemini-2.5-flash", None),
    },
]

_BUILTIN_SLUGS = {t["slug"] for t in _BUILTIN_TEMPLATES}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _models_for_backend(backend: str) -> list[str]:
    """Return known model names for a built-in backend from the cost table."""
    prefix_map = {
        "claude": ("claude-",),
        "openai": ("gpt-", "o3", "o4-"),
        "gemini": ("gemini-",),
    }
    prefixes = prefix_map.get(backend)
    if not prefixes:
        return []
    return sorted(m for m in _MODEL_COSTS if m.startswith(prefixes))


def _parse_stages(raw: dict | str) -> dict[str, StageConfig]:
    """Parse raw JSON stage data into StageConfig dict."""
    import json
    if isinstance(raw, str):
        raw = json.loads(raw)
    result: dict[str, StageConfig] = {}
    for stage_name, phase_dict in raw.items():
        if not isinstance(phase_dict, dict):
            continue
        result[stage_name] = StageConfig(
            act=PhaseModel(**phase_dict["act"]) if phase_dict.get("act") else PhaseModel(backend="claude", model="claude-sonnet-4-6"),
            explore=PhaseModel(**phase_dict["explore"]) if phase_dict.get("explore") else None,
            plan=PhaseModel(**phase_dict["plan"]) if phase_dict.get("plan") else None,
        )
    return result


async def _load_templates(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[BackendTemplate]:
    """Load templates: built-in defaults merged with DB overrides + OpenCode templates."""
    db_templates: dict[str, dict] = {}
    async with session_factory() as session:
        result = await session.execute(
            select(PipelineSetting).where(PipelineSetting.key == "backend_templates")
        )
        row = result.scalar_one_or_none()
        if row and isinstance(row.value_json, list):
            for t in row.value_json:
                db_templates[t["slug"]] = t

    templates: list[BackendTemplate] = []
    for builtin in _BUILTIN_TEMPLATES:
        data = db_templates.pop(builtin["slug"], None) or copy.deepcopy(builtin)
        templates.append(BackendTemplate(
            slug=data["slug"],
            display_name=data.get("display_name", builtin["display_name"]),
            backend=data.get("backend", builtin["backend"]),
            stages=_parse_stages(data.get("stages", builtin["stages"])),
            available_models=_models_for_backend(builtin["backend"]),
            is_default=False,  # set below
        ))

    # Append any remaining DB templates (OpenCode custom ones)
    for slug, data in db_templates.items():
        templates.append(BackendTemplate(
            slug=data["slug"],
            display_name=data["display_name"],
            backend=data.get("backend", "opencode"),
            stages=_parse_stages(data.get("stages", {})),
            base_url=data.get("base_url"),
            available_models=data.get("available_models", []),
            is_default=False,
        ))

    return templates


async def _load_default_slug(
    session_factory: async_sessionmaker[AsyncSession],
) -> str:
    """Load the default template slug from DB, falling back to 'anthropic'."""
    async with session_factory() as session:
        result = await session.execute(
            select(PipelineSetting).where(PipelineSetting.key == "default_template")
        )
        row = result.scalar_one_or_none()
        if row and isinstance(row.value_json, dict):
            return row.value_json.get("slug", "anthropic")
        if row and isinstance(row.value_json, str):
            return row.value_json
    return "anthropic"


# ---------------------------------------------------------------------------
# Template Routes
# ---------------------------------------------------------------------------


@router.get("/settings/templates")
async def get_templates(
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> list[BackendTemplate]:
    """Return all backend templates (built-in + custom)."""
    templates = await _load_templates(session_factory)
    default_slug = await _load_default_slug(session_factory)
    for t in templates:
        t.is_default = t.slug == default_slug
    return templates


@router.put("/settings/templates")
async def update_templates(
    body: list[BackendTemplate],
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> list[BackendTemplate]:
    """Save all templates. Validates unique slugs."""
    slugs = [t.slug for t in body]
    if len(slugs) != len(set(slugs)):
        raise HTTPException(status_code=422, detail="Duplicate template slugs")

    templates_json = []
    for t in body:
        data = t.model_dump()
        # Convert StageConfig objects to plain dicts for JSON storage
        data["stages"] = {
            stage: cfg.model_dump() if hasattr(cfg, "model_dump") else cfg
            for stage, cfg in data["stages"].items()
        }
        # Don't persist computed fields
        data.pop("available_models", None)
        data.pop("is_default", None)
        templates_json.append(data)

    async with session_factory() as session:
        result = await session.execute(
            select(PipelineSetting).where(PipelineSetting.key == "backend_templates")
        )
        row = result.scalar_one_or_none()
        if row:
            row.value_json = templates_json
        else:
            session.add(PipelineSetting(key="backend_templates", value_json=templates_json))

        session.add(AuditLog(
            action="backend_templates_updated",
            details={"slugs": slugs},
        ))
        await session.commit()

    # Re-load to get computed fields (available_models, is_default)
    return await get_templates(session_factory)


@router.get("/settings/templates/default")
async def get_default_template(
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> DefaultTemplateResponse:
    """Return the default template slug."""
    slug = await _load_default_slug(session_factory)
    return DefaultTemplateResponse(slug=slug)


@router.put("/settings/templates/default")
async def set_default_template(
    body: DefaultTemplateUpdate,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> DefaultTemplateResponse:
    """Set the default template slug. Validates slug exists."""
    # Verify slug exists in current templates
    templates = await _load_templates(session_factory)
    known_slugs = {t.slug for t in templates}
    if body.slug not in known_slugs:
        raise HTTPException(status_code=422, detail=f"Unknown template slug: {body.slug}")

    async with session_factory() as session:
        result = await session.execute(
            select(PipelineSetting).where(PipelineSetting.key == "default_template")
        )
        row = result.scalar_one_or_none()
        if row:
            row.value_json = {"slug": body.slug}
        else:
            session.add(PipelineSetting(key="default_template", value_json={"slug": body.slug}))

        session.add(AuditLog(
            action="default_template_updated",
            details={"slug": body.slug},
        ))
        await session.commit()

    return DefaultTemplateResponse(slug=body.slug)


# ---------------------------------------------------------------------------
# Pipeline Defaults
# ---------------------------------------------------------------------------


class PipelineDefaultsResponse(BaseModel):
    max_verification_loops: int
    max_review_dev_loops: int
    max_cost_usd: float
    default_template: str
    delivery_strategy: str
    agent_timeout: int
    test_timeout: int


class PipelineDefaultsUpdate(BaseModel):
    max_verification_loops: int
    max_review_dev_loops: int
    max_cost_usd: float
    default_template: str
    delivery_strategy: str
    agent_timeout: int
    test_timeout: int


@router.get("/settings/pipeline-defaults")
async def get_pipeline_defaults(
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> PipelineDefaultsResponse:
    """Return current pipeline defaults (falls back to hardcoded defaults)."""
    values = {**PIPELINE_DEFAULTS}

    async with session_factory() as session:
        result = await session.execute(
            select(PipelineSetting).where(PipelineSetting.key == "pipeline_defaults")
        )
        row = result.scalar_one_or_none()
        if row and isinstance(row.value_json, dict):
            values.update(row.value_json)

    return PipelineDefaultsResponse(**values)


@router.put("/settings/pipeline-defaults")
async def update_pipeline_defaults(
    body: PipelineDefaultsUpdate,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> PipelineDefaultsResponse:
    """Update pipeline defaults. Writes AuditLog entry."""
    values = body.model_dump()

    async with session_factory() as session:
        result = await session.execute(
            select(PipelineSetting).where(PipelineSetting.key == "pipeline_defaults")
        )
        row = result.scalar_one_or_none()
        if row:
            row.value_json = values
        else:
            session.add(PipelineSetting(key="pipeline_defaults", value_json=values))

        session.add(AuditLog(
            action="pipeline_defaults_updated",
            details=values,
        ))

        await session.commit()

    return PipelineDefaultsResponse(**values)


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------


class ApiKeyStatus(BaseModel):
    key_name: str
    display_name: str
    is_configured: bool
    masked_value: str
    source: str  # "database" | "environment" | "none"


class ApiKeyUpdate(BaseModel):
    key_name: str
    value: str


def _key_status(key_name: str, info: dict[str, str], encrypted: dict[str, str]) -> ApiKeyStatus:
    """Build an ApiKeyStatus for a single key."""
    display_name = info["display_name"]

    # Check DB first
    ciphertext = encrypted.get(key_name)
    if ciphertext:
        try:
            plaintext = decrypt_value(ciphertext)
            return ApiKeyStatus(
                key_name=key_name,
                display_name=display_name,
                is_configured=True,
                masked_value=mask_key(plaintext),
                source="database",
            )
        except Exception:
            return ApiKeyStatus(
                key_name=key_name,
                display_name=display_name,
                is_configured=True,
                masked_value="(encrypted, cannot decrypt)",
                source="database",
            )

    # Env var fallback
    env_val = os.environ.get(info["env_var"]) or os.environ.get(info["env_fallback"], "")
    if env_val:
        return ApiKeyStatus(
            key_name=key_name,
            display_name=display_name,
            is_configured=True,
            masked_value=mask_key(env_val),
            source="environment",
        )

    return ApiKeyStatus(
        key_name=key_name,
        display_name=display_name,
        is_configured=False,
        masked_value="",
        source="none",
    )


@router.get("/settings/api-keys")
async def get_api_keys(
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> list[ApiKeyStatus]:
    """Return status of all known API keys (masked, never plaintext)."""
    encrypted = await _load_encrypted_keys(session_factory)
    return [
        _key_status(key_name, info, encrypted)
        for key_name, info in API_KEY_REGISTRY.items()
    ]


@router.put("/settings/api-keys")
async def set_api_key(
    body: ApiKeyUpdate,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> ApiKeyStatus:
    """Encrypt and store a single API key."""
    if body.key_name not in API_KEY_REGISTRY:
        raise HTTPException(status_code=422, detail=f"Unknown key name: {body.key_name}")
    if not body.value.strip():
        raise HTTPException(status_code=422, detail="API key value must not be empty")

    try:
        ciphertext = encrypt_value(body.value)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    async with session_factory() as session:
        result = await session.execute(
            select(PipelineSetting).where(PipelineSetting.key == DB_SETTING_KEY)
        )
        row = result.scalar_one_or_none()
        keys_dict: dict = row.value_json if row and isinstance(row.value_json, dict) else {}
        keys_dict[body.key_name] = ciphertext

        if row:
            row.value_json = keys_dict
        else:
            session.add(PipelineSetting(key=DB_SETTING_KEY, value_json=keys_dict))

        session.add(AuditLog(
            action="api_key_updated",
            details={"key_name": body.key_name},
        ))
        await session.commit()

    info = API_KEY_REGISTRY[body.key_name]
    return ApiKeyStatus(
        key_name=body.key_name,
        display_name=info["display_name"],
        is_configured=True,
        masked_value=mask_key(body.value),
        source="database",
    )


@router.delete("/settings/api-keys/{key_name}")
async def clear_api_key(
    key_name: str,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> ApiKeyStatus:
    """Remove a DB-stored API key, falling back to env var."""
    if key_name not in API_KEY_REGISTRY:
        raise HTTPException(status_code=422, detail=f"Unknown key name: {key_name}")

    async with session_factory() as session:
        result = await session.execute(
            select(PipelineSetting).where(PipelineSetting.key == DB_SETTING_KEY)
        )
        row = result.scalar_one_or_none()
        if row and isinstance(row.value_json, dict):
            keys_dict = dict(row.value_json)
            keys_dict.pop(key_name, None)
            row.value_json = keys_dict

        session.add(AuditLog(
            action="api_key_cleared",
            details={"key_name": key_name},
        ))
        await session.commit()

    # Return current status (will reflect env var fallback if any)
    info = API_KEY_REGISTRY[key_name]
    return _key_status(key_name, info, {})

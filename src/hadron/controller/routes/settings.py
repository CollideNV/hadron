"""Model and pipeline settings management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hadron.agent.cost import _MODEL_COSTS
from hadron.config.defaults import PIPELINE_DEFAULTS
from hadron.controller.dependencies import get_session_factory
from hadron.db.models import AuditLog, PipelineSetting

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


class ModelSettingsResponse(BaseModel):
    default_backend: str
    stages: dict[str, StageConfig]


class ModelSettingsUpdate(BaseModel):
    default_backend: str
    stages: dict[str, StageConfig]


class BackendModels(BaseModel):
    name: str
    display_name: str
    models: list[str]


class OpenCodeEndpoint(BaseModel):
    slug: str
    display_name: str
    base_url: str
    models: list[str]


# ---------------------------------------------------------------------------
# Defaults (fallback when no DB rows exist)
# ---------------------------------------------------------------------------

_DEFAULT_BACKEND = "claude"
_DEFAULT_STAGES: dict[str, dict] = {
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _build_backends_list(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[BackendModels]:
    """Derive available backends and their models from the cost table + DB endpoints."""
    groups: dict[str, list[str]] = {
        "claude": [],
        "openai": [],
        "gemini": [],
    }
    for model_name in sorted(_MODEL_COSTS):
        if model_name.startswith("claude-"):
            groups["claude"].append(model_name)
        elif model_name.startswith(("gpt-", "o3", "o4-")):
            groups["openai"].append(model_name)
        elif model_name.startswith("gemini-"):
            groups["gemini"].append(model_name)

    backends = [
        BackendModels(name="claude", display_name="Anthropic", models=groups["claude"]),
        BackendModels(name="openai", display_name="OpenAI", models=groups["openai"]),
        BackendModels(name="gemini", display_name="Gemini", models=groups["gemini"]),
        BackendModels(name="opencode", display_name="OpenCode", models=[]),
    ]

    # Append named OpenCode endpoints from DB
    async with session_factory() as session:
        result = await session.execute(
            select(PipelineSetting).where(PipelineSetting.key == "opencode_endpoints")
        )
        row = result.scalar_one_or_none()
        if row and isinstance(row.value_json, list):
            for ep in row.value_json:
                backends.append(BackendModels(
                    name=f"opencode:{ep['slug']}",
                    display_name=ep["display_name"],
                    models=ep.get("models", []),
                ))

    return backends


def _parse_stages(raw: dict | str) -> dict[str, StageConfig]:
    """Parse raw JSON stage_models into StageConfig dict."""
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/settings/models")
async def get_model_settings(
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> ModelSettingsResponse:
    """Return current model settings (falls back to hardcoded defaults)."""
    default_backend = _DEFAULT_BACKEND
    stages_raw = _DEFAULT_STAGES

    async with session_factory() as session:
        result = await session.execute(
            select(PipelineSetting).where(
                PipelineSetting.key.in_(["default_backend", "stage_models"])
            )
        )
        for setting in result.scalars():
            if setting.key == "default_backend":
                val = setting.value_json
                if isinstance(val, dict):
                    default_backend = val.get("backend", _DEFAULT_BACKEND)
                elif isinstance(val, str):
                    default_backend = val
            elif setting.key == "stage_models":
                stages_raw = setting.value_json

    return ModelSettingsResponse(
        default_backend=default_backend,
        stages=_parse_stages(stages_raw),
    )


@router.put("/settings/models")
async def update_model_settings(
    body: ModelSettingsUpdate,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> ModelSettingsResponse:
    """Update model settings. Writes AuditLog entry."""
    stages_json = {
        stage: cfg.model_dump() for stage, cfg in body.stages.items()
    }

    async with session_factory() as session:
        # Upsert default_backend
        result = await session.execute(
            select(PipelineSetting).where(PipelineSetting.key == "default_backend")
        )
        row = result.scalar_one_or_none()
        if row:
            row.value_json = {"backend": body.default_backend}
        else:
            session.add(PipelineSetting(
                key="default_backend",
                value_json={"backend": body.default_backend},
            ))

        # Upsert stage_models
        result = await session.execute(
            select(PipelineSetting).where(PipelineSetting.key == "stage_models")
        )
        row = result.scalar_one_or_none()
        if row:
            row.value_json = stages_json
        else:
            session.add(PipelineSetting(
                key="stage_models",
                value_json=stages_json,
            ))

        session.add(AuditLog(
            action="model_settings_updated",
            details={"default_backend": body.default_backend, "stages": list(stages_json.keys())},
        ))

        await session.commit()

    return ModelSettingsResponse(
        default_backend=body.default_backend,
        stages=_parse_stages(stages_json),
    )


@router.get("/settings/backends")
async def get_available_backends(
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> list[BackendModels]:
    """Return available backends with their model lists."""
    return await _build_backends_list(session_factory)


# ---------------------------------------------------------------------------
# OpenCode Endpoints
# ---------------------------------------------------------------------------


@router.get("/settings/opencode-endpoints")
async def get_opencode_endpoints(
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> list[OpenCodeEndpoint]:
    """Return named OpenCode endpoints."""
    async with session_factory() as session:
        result = await session.execute(
            select(PipelineSetting).where(PipelineSetting.key == "opencode_endpoints")
        )
        row = result.scalar_one_or_none()
        if row and isinstance(row.value_json, list):
            return [OpenCodeEndpoint(**ep) for ep in row.value_json]
    return []


@router.put("/settings/opencode-endpoints")
async def update_opencode_endpoints(
    body: list[OpenCodeEndpoint],
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> list[OpenCodeEndpoint]:
    """Replace all named OpenCode endpoints. Validates unique slugs."""
    # Validate unique slugs
    slugs = [ep.slug for ep in body]
    if len(slugs) != len(set(slugs)):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Duplicate endpoint slugs")

    endpoints_json = [ep.model_dump() for ep in body]

    async with session_factory() as session:
        result = await session.execute(
            select(PipelineSetting).where(PipelineSetting.key == "opencode_endpoints")
        )
        row = result.scalar_one_or_none()
        if row:
            row.value_json = endpoints_json
        else:
            session.add(PipelineSetting(
                key="opencode_endpoints",
                value_json=endpoints_json,
            ))

        session.add(AuditLog(
            action="opencode_endpoints_updated",
            details={"slugs": slugs},
        ))

        await session.commit()

    return body


# ---------------------------------------------------------------------------
# Pipeline Defaults
# ---------------------------------------------------------------------------


class PipelineDefaultsResponse(BaseModel):
    max_verification_loops: int
    max_review_dev_loops: int
    max_cost_usd: float
    default_backend: str
    default_model: str
    explore_model: str
    plan_model: str
    delivery_strategy: str
    agent_timeout: int
    test_timeout: int


class PipelineDefaultsUpdate(BaseModel):
    max_verification_loops: int
    max_review_dev_loops: int
    max_cost_usd: float
    default_backend: str
    default_model: str
    explore_model: str
    plan_model: str
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

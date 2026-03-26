"""API key registry and resolution — DB first, env var fallback."""

from __future__ import annotations

import logging
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hadron.db.models import PipelineSetting
from hadron.security.crypto import decrypt_value

logger = logging.getLogger(__name__)

API_KEY_REGISTRY: dict[str, dict[str, str]] = {
    "anthropic_api_key": {
        "display_name": "Anthropic",
        "env_var": "HADRON_ANTHROPIC_API_KEY",
        "env_fallback": "ANTHROPIC_API_KEY",
    },
    "openai_api_key": {
        "display_name": "OpenAI",
        "env_var": "HADRON_OPENAI_API_KEY",
        "env_fallback": "OPENAI_API_KEY",
    },
    "gemini_api_key": {
        "display_name": "Gemini",
        "env_var": "HADRON_GEMINI_API_KEY",
        "env_fallback": "GEMINI_API_KEY",
    },
}

# Maps key_name → env var name for worker distribution.
KEY_TO_ENV_VAR: dict[str, str] = {
    name: info["env_var"] for name, info in API_KEY_REGISTRY.items()
}

DB_SETTING_KEY = "api_keys"


async def _load_encrypted_keys(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, str]:
    """Load the raw encrypted key dict from the DB.  Returns ``{}`` if absent."""
    async with session_factory() as session:
        result = await session.execute(
            select(PipelineSetting).where(PipelineSetting.key == DB_SETTING_KEY)
        )
        row = result.scalar_one_or_none()
        if row and isinstance(row.value_json, dict):
            return row.value_json
    return {}


async def resolve_api_keys(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, str]:
    """Return resolved plaintext API keys: DB first, then env var fallback.

    The returned dict maps *key_name* (e.g. ``"anthropic_api_key"``) to a
    plaintext value.  Only keys that have a value from either source are
    included.
    """
    encrypted = await _load_encrypted_keys(session_factory)
    resolved: dict[str, str] = {}

    for key_name, info in API_KEY_REGISTRY.items():
        # Try DB first
        ciphertext = encrypted.get(key_name)
        if ciphertext:
            try:
                resolved[key_name] = decrypt_value(ciphertext)
                continue
            except Exception:
                logger.warning("Failed to decrypt DB-stored key %s, falling back to env var", key_name)

        # Env var fallback
        value = os.environ.get(info["env_var"]) or os.environ.get(info["env_fallback"], "")
        if value:
            resolved[key_name] = value

    return resolved


def resolved_keys_as_env(resolved: dict[str, str]) -> dict[str, str]:
    """Map resolved key_names to their ``HADRON_*`` env var names for worker injection."""
    return {KEY_TO_ENV_VAR[k]: v for k, v in resolved.items() if k in KEY_TO_ENV_VAR}

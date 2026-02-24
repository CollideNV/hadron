"""Load bootstrap configuration from environment variables."""

from __future__ import annotations

import os

from hadron.models.config import BootstrapConfig

_ENV_PREFIX = "HADRON_"

_FIELD_MAP = {
    "postgres_url": "POSTGRES_URL",
    "postgres_url_sync": "POSTGRES_URL_SYNC",
    "redis_url": "REDIS_URL",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "workspace_dir": "WORKSPACE_DIR",
    "controller_host": "CONTROLLER_HOST",
    "controller_port": "CONTROLLER_LISTEN_PORT",
    "log_level": "LOG_LEVEL",
}


def load_bootstrap_config() -> BootstrapConfig:
    """Build BootstrapConfig from env vars (prefixed HADRON_) with defaults."""
    overrides: dict[str, str] = {}
    for field_name, env_suffix in _FIELD_MAP.items():
        env_key = f"{_ENV_PREFIX}{env_suffix}"
        val = os.environ.get(env_key)
        if val is not None:
            overrides[field_name] = val
    return BootstrapConfig(**overrides)

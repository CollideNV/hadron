"""Tests for bootstrap config loading from environment variables."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from hadron.config.bootstrap import load_bootstrap_config
from hadron.models.config import BootstrapConfig


class TestBootstrapConfig:
    """BootstrapConfig Pydantic model."""

    def test_defaults(self) -> None:
        cfg = BootstrapConfig()
        assert "asyncpg" in cfg.postgres_url
        assert "psycopg" in cfg.postgres_url_sync
        assert cfg.redis_url == "redis://localhost:6379/0"
        assert cfg.anthropic_api_key == ""
        assert cfg.controller_host == "0.0.0.0"
        assert cfg.controller_port == 8000
        assert cfg.log_level == "INFO"

    def test_override_fields(self) -> None:
        cfg = BootstrapConfig(
            anthropic_api_key="sk-test",
            controller_port=9000,
            log_level="DEBUG",
        )
        assert cfg.anthropic_api_key == "sk-test"
        assert cfg.controller_port == 9000
        assert cfg.log_level == "DEBUG"

    def test_port_coerced_from_string(self) -> None:
        cfg = BootstrapConfig(controller_port="3000")
        assert cfg.controller_port == 3000


class TestLoadBootstrapConfig:
    """load_bootstrap_config() reads HADRON_* env vars."""

    def test_returns_defaults_when_no_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            cfg = load_bootstrap_config()
        assert isinstance(cfg, BootstrapConfig)
        assert cfg.controller_port == 8000

    def test_reads_hadron_prefixed_vars(self) -> None:
        env = {
            "HADRON_ANTHROPIC_API_KEY": "sk-from-env",
            "HADRON_CONTROLLER_LISTEN_PORT": "4000",
            "HADRON_LOG_LEVEL": "DEBUG",
            "HADRON_REDIS_URL": "redis://custom:6380/1",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = load_bootstrap_config()
        assert cfg.anthropic_api_key == "sk-from-env"
        assert cfg.controller_port == 4000
        assert cfg.log_level == "DEBUG"
        assert cfg.redis_url == "redis://custom:6380/1"

    def test_ignores_non_hadron_vars(self) -> None:
        env = {"SOME_OTHER_KEY": "value", "HADRON_LOG_LEVEL": "WARNING"}
        with patch.dict(os.environ, env, clear=True):
            cfg = load_bootstrap_config()
        assert cfg.log_level == "WARNING"
        # Default values still apply for unset vars
        assert cfg.controller_port == 8000

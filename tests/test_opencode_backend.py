"""Tests for OpenCodeAgentBackend — env var defaults and base_url wiring."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest


def _install_openai_mock():
    """Install a mock openai module into sys.modules."""
    mock_openai = MagicMock()
    mock_openai.RateLimitError = type("RateLimitError", (Exception,), {})
    mock_openai.InternalServerError = type("InternalServerError", (Exception,), {})
    mock_client = MagicMock()
    mock_openai.AsyncOpenAI.return_value = mock_client
    sys.modules["openai"] = mock_openai
    return mock_openai, mock_client


@pytest.fixture(autouse=True)
def _mock_openai():
    """Install and clean up openai mock for every test."""
    mock_openai, mock_client = _install_openai_mock()
    # Clear cached modules so they reimport with mocked openai
    sys.modules.pop("hadron.agent.openai_backend", None)
    sys.modules.pop("hadron.agent.opencode", None)
    yield mock_openai, mock_client
    sys.modules.pop("openai", None)
    sys.modules.pop("hadron.agent.openai_backend", None)
    sys.modules.pop("hadron.agent.opencode", None)


class TestOpenCodeDefaults:
    def test_default_base_url(self, _mock_openai) -> None:
        mock_openai, mock_client = _mock_openai
        from hadron.agent.opencode import OpenCodeAgentBackend
        backend = OpenCodeAgentBackend()
        # Check that AsyncOpenAI was called with a localhost base_url
        call_kwargs = mock_openai.AsyncOpenAI.call_args
        assert "localhost" in str(call_kwargs)

    def test_custom_base_url(self, _mock_openai) -> None:
        mock_openai, mock_client = _mock_openai
        from hadron.agent.opencode import OpenCodeAgentBackend
        backend = OpenCodeAgentBackend(base_url="http://myserver:8080/v1")
        call_kwargs = mock_openai.AsyncOpenAI.call_args
        assert "myserver" in str(call_kwargs)

    def test_env_var_base_url(self, _mock_openai) -> None:
        mock_openai, mock_client = _mock_openai
        from hadron.agent.opencode import OpenCodeAgentBackend
        with patch.dict(os.environ, {"HADRON_OPENCODE_BASE_URL": "http://env-server:9090/v1"}):
            backend = OpenCodeAgentBackend()
        call_kwargs = mock_openai.AsyncOpenAI.call_args
        assert "env-server" in str(call_kwargs)

    def test_explicit_overrides_env(self, _mock_openai) -> None:
        mock_openai, mock_client = _mock_openai
        from hadron.agent.opencode import OpenCodeAgentBackend
        with patch.dict(os.environ, {"HADRON_OPENCODE_BASE_URL": "http://env-server:9090/v1"}):
            backend = OpenCodeAgentBackend(base_url="http://explicit:1234/v1")
        call_kwargs = mock_openai.AsyncOpenAI.call_args
        assert "explicit" in str(call_kwargs)

    def test_api_key_defaults_to_not_needed(self, _mock_openai) -> None:
        mock_openai, mock_client = _mock_openai
        from hadron.agent.opencode import OpenCodeAgentBackend
        backend = OpenCodeAgentBackend()
        call_kwargs = mock_openai.AsyncOpenAI.call_args
        assert "not-needed" in str(call_kwargs)

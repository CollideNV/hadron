"""Tests for the agent backend factory."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from hadron.agent.factory import create_agent_backend


class TestFactoryDefault:
    def test_default_is_claude(self) -> None:
        backend = create_agent_backend()
        from hadron.agent.claude import ClaudeAgentBackend
        assert isinstance(backend, ClaudeAgentBackend)

    def test_explicit_claude(self) -> None:
        backend = create_agent_backend("claude")
        from hadron.agent.claude import ClaudeAgentBackend
        assert isinstance(backend, ClaudeAgentBackend)

    def test_env_var_override(self) -> None:
        with patch.dict(os.environ, {"HADRON_AGENT_BACKEND": "claude"}):
            backend = create_agent_backend()
        from hadron.agent.claude import ClaudeAgentBackend
        assert isinstance(backend, ClaudeAgentBackend)

    def test_case_insensitive(self) -> None:
        backend = create_agent_backend("Claude")
        from hadron.agent.claude import ClaudeAgentBackend
        assert isinstance(backend, ClaudeAgentBackend)


class TestFactoryOpenAI:
    def test_creates_openai_backend(self) -> None:
        mock_openai = MagicMock()
        mock_openai.RateLimitError = type("RateLimitError", (Exception,), {})
        mock_openai.InternalServerError = type("InternalServerError", (Exception,), {})
        mock_openai.AsyncOpenAI.return_value = MagicMock()
        sys.modules["openai"] = mock_openai
        sys.modules.pop("hadron.agent.openai_backend", None)
        try:
            backend = create_agent_backend("openai", openai_api_key="test-key")
            from hadron.agent.openai_backend import OpenAIAgentBackend
            assert isinstance(backend, OpenAIAgentBackend)
        finally:
            sys.modules.pop("openai", None)
            sys.modules.pop("hadron.agent.openai_backend", None)


class TestFactoryOpenCode:
    def test_creates_opencode_backend(self) -> None:
        mock_openai = MagicMock()
        mock_openai.RateLimitError = type("RateLimitError", (Exception,), {})
        mock_openai.InternalServerError = type("InternalServerError", (Exception,), {})
        mock_openai.AsyncOpenAI.return_value = MagicMock()
        sys.modules["openai"] = mock_openai
        sys.modules.pop("hadron.agent.openai_backend", None)
        sys.modules.pop("hadron.agent.opencode", None)
        try:
            backend = create_agent_backend("opencode")
            from hadron.agent.opencode import OpenCodeAgentBackend
            assert isinstance(backend, OpenCodeAgentBackend)
        finally:
            sys.modules.pop("openai", None)
            sys.modules.pop("hadron.agent.openai_backend", None)
            sys.modules.pop("hadron.agent.opencode", None)


class TestFactoryGemini:
    def test_creates_gemini_backend(self) -> None:
        backend = create_agent_backend("gemini", gemini_api_key="test-key")
        from hadron.agent.gemini import GeminiAgentBackend
        assert isinstance(backend, GeminiAgentBackend)


class TestFactoryUnknown:
    def test_unknown_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown agent backend"):
            create_agent_backend("nonexistent")

"""Tests for OpenCodeAgentBackend — SDK-based backend using opencode serve."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hadron.agent.tool_loop import ToolLoopConfig, _PhaseResult


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _make_tokens(inp: float = 100, out: float = 50, cache_read: float = 0, cache_write: float = 0):
    return SimpleNamespace(
        input=inp,
        output=out,
        cache=SimpleNamespace(read=cache_read, write=cache_write),
        reasoning=0.0,
    )


def _make_assistant_message(cost: float = 0.0, tokens=None):
    return SimpleNamespace(
        id="msg-1",
        cost=cost,
        tokens=tokens or _make_tokens(),
        role="assistant",
        session_id="sess-1",
    )


def _make_text_part(text: str, role: str = "assistant"):
    return SimpleNamespace(type="text", text=text, message_id="m1", session_id="s1")


def _make_tool_part(tool_name: str, inp: dict, output: str = "ok"):
    return SimpleNamespace(
        type="tool",
        tool=tool_name,
        state=SimpleNamespace(input=inp, output=output, status="completed"),
        message_id="m1",
        session_id="s1",
    )


def _make_msg_item(role: str, parts: list):
    return SimpleNamespace(info=SimpleNamespace(role=role), parts=parts)


def _make_session(session_id: str = "sess-1"):
    return SimpleNamespace(id=session_id)


def _install_opencode_mock():
    """Install a mock opencode_ai module into sys.modules and return the mock client."""
    mock_client = AsyncMock()
    mock_client.session.create = AsyncMock(return_value=_make_session())
    mock_client.session.delete = AsyncMock()
    mock_client.session.chat = AsyncMock(return_value=_make_assistant_message())
    mock_client.session.messages = AsyncMock(return_value=[])

    mock_module = MagicMock()
    mock_module.AsyncOpencode.return_value = mock_client
    sys.modules["opencode_ai"] = mock_module
    return mock_module, mock_client


@pytest.fixture(autouse=True)
def _mock_opencode():
    mock_module, mock_client = _install_opencode_mock()
    sys.modules.pop("hadron.agent.opencode", None)
    yield mock_module, mock_client
    sys.modules.pop("opencode_ai", None)
    sys.modules.pop("hadron.agent.opencode", None)


# ---------------------------------------------------------------------------
# Construction & env var tests
# ---------------------------------------------------------------------------

class TestOpenCodeDefaults:
    def test_default_base_url(self, _mock_opencode) -> None:
        mock_module, _ = _mock_opencode
        from hadron.agent.opencode import OpenCodeAgentBackend
        backend = OpenCodeAgentBackend()
        call_kwargs = mock_module.AsyncOpencode.call_args
        assert "127.0.0.1:4096" in str(call_kwargs)

    def test_custom_base_url(self, _mock_opencode) -> None:
        mock_module, _ = _mock_opencode
        from hadron.agent.opencode import OpenCodeAgentBackend
        OpenCodeAgentBackend(base_url="http://myserver:8080")
        call_kwargs = mock_module.AsyncOpencode.call_args
        assert "myserver" in str(call_kwargs)

    def test_env_var_base_url(self, _mock_opencode) -> None:
        mock_module, _ = _mock_opencode
        from hadron.agent.opencode import OpenCodeAgentBackend
        with patch.dict(os.environ, {"HADRON_OPENCODE_BASE_URL": "http://env-server:9090"}):
            OpenCodeAgentBackend()
        call_kwargs = mock_module.AsyncOpencode.call_args
        assert "env-server" in str(call_kwargs)

    def test_explicit_overrides_env(self, _mock_opencode) -> None:
        mock_module, _ = _mock_opencode
        from hadron.agent.opencode import OpenCodeAgentBackend
        with patch.dict(os.environ, {"HADRON_OPENCODE_BASE_URL": "http://env-server:9090"}):
            OpenCodeAgentBackend(base_url="http://explicit:1234")
        call_kwargs = mock_module.AsyncOpencode.call_args
        assert "explicit" in str(call_kwargs)

    def test_default_provider_id(self, _mock_opencode) -> None:
        from hadron.agent.opencode import OpenCodeAgentBackend
        backend = OpenCodeAgentBackend()
        assert backend._provider_id == "ollama"

    def test_env_provider_id(self, _mock_opencode) -> None:
        from hadron.agent.opencode import OpenCodeAgentBackend
        with patch.dict(os.environ, {"HADRON_OPENCODE_PROVIDER_ID": "anthropic"}):
            backend = OpenCodeAgentBackend()
        assert backend._provider_id == "anthropic"


# ---------------------------------------------------------------------------
# Tool mapping tests
# ---------------------------------------------------------------------------

class TestToolMapping:
    def test_map_tools(self, _mock_opencode) -> None:
        from hadron.agent.opencode import _map_tools
        tools = [
            {"name": "read_file", "description": "...", "input_schema": {}},
            {"name": "write_file", "description": "...", "input_schema": {}},
            {"name": "run_command", "description": "...", "input_schema": {}},
        ]
        result = _map_tools(tools)
        assert result == {"read": True, "write": True, "terminal": True}

    def test_map_tools_empty(self, _mock_opencode) -> None:
        from hadron.agent.opencode import _map_tools
        assert _map_tools([]) == {}


# ---------------------------------------------------------------------------
# _call_tool_loop tests
# ---------------------------------------------------------------------------

class TestCallToolLoop:
    async def test_basic_tool_loop(self, _mock_opencode) -> None:
        _, mock_client = _mock_opencode
        from hadron.agent.opencode import OpenCodeAgentBackend

        mock_client.session.chat.return_value = _make_assistant_message(
            cost=0.05,
            tokens=_make_tokens(inp=500, out=200, cache_read=10, cache_write=5),
        )
        mock_client.session.messages.return_value = [
            _make_msg_item("user", [_make_text_part("do something", role="user")]),
            _make_msg_item("assistant", [
                _make_tool_part("write", {"path": "foo.py"}, "wrote file"),
                _make_text_part("Done! I wrote foo.py"),
            ]),
        ]

        backend = OpenCodeAgentBackend()
        cfg = ToolLoopConfig(
            model="qwen3-coder-30b",
            system_prompt="You are a coder.",
            user_prompt="Write foo.py",
            tools=[{"name": "write_file"}],
            working_dir="/workspace",
            max_rounds=10,
            max_tokens=4096,
        )
        result = await backend._call_tool_loop(cfg)

        assert isinstance(result, _PhaseResult)
        assert result.input_tokens == 500
        assert result.output_tokens == 200
        assert result.cost_usd == 0.05
        assert result.cache_read_tokens == 10
        assert result.cache_creation_tokens == 5
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "write"
        assert result.output == "Done! I wrote foo.py"
        assert result.round_count >= 1

        # Session should be created and deleted
        mock_client.session.create.assert_awaited_once()
        mock_client.session.delete.assert_awaited_once_with("sess-1")

    async def test_tool_loop_emits_events(self, _mock_opencode) -> None:
        _, mock_client = _mock_opencode
        from hadron.agent.opencode import OpenCodeAgentBackend

        mock_client.session.chat.return_value = _make_assistant_message()
        mock_client.session.messages.return_value = [
            _make_msg_item("assistant", [_make_text_part("hello")]),
        ]

        events: list[tuple] = []

        async def on_event(event_type: str, data: dict):
            events.append((event_type, data))

        backend = OpenCodeAgentBackend()
        cfg = ToolLoopConfig(
            model="test",
            system_prompt="",
            user_prompt="hi",
            tools=[],
            working_dir=".",
            max_rounds=1,
            max_tokens=4096,
            on_event=on_event,
        )
        await backend._call_tool_loop(cfg)

        assert any(e[0] == "output" for e in events)

    async def test_session_deleted_on_error(self, _mock_opencode) -> None:
        _, mock_client = _mock_opencode
        from hadron.agent.opencode import OpenCodeAgentBackend

        mock_client.session.chat.side_effect = RuntimeError("boom")

        backend = OpenCodeAgentBackend()
        cfg = ToolLoopConfig(
            model="test", system_prompt="", user_prompt="hi",
            tools=[], working_dir=".", max_rounds=1, max_tokens=4096,
        )
        with pytest.raises(RuntimeError, match="boom"):
            await backend._call_tool_loop(cfg)

        mock_client.session.delete.assert_awaited_once()


# ---------------------------------------------------------------------------
# _call_plan tests
# ---------------------------------------------------------------------------

class TestCallPlan:
    async def test_plan_no_tools(self, _mock_opencode) -> None:
        _, mock_client = _mock_opencode
        from hadron.agent.opencode import OpenCodeAgentBackend

        mock_client.session.chat.return_value = _make_assistant_message(
            cost=0.01, tokens=_make_tokens(inp=300, out=150),
        )
        mock_client.session.messages.return_value = [
            _make_msg_item("assistant", [_make_text_part("Here is the plan...")]),
        ]

        backend = OpenCodeAgentBackend()
        result = await backend._call_plan(
            model="qwen3-coder-30b",
            system_prompt="You are a planner.",
            user_prompt="Plan the work.",
            max_tokens=4096,
        )

        assert result.output == "Here is the plan..."
        assert result.tool_calls == []
        assert result.input_tokens == 300
        assert result.cost_usd == 0.01

        # Verify tools={} was passed (no tools for plan)
        chat_call = mock_client.session.chat.call_args
        assert chat_call.kwargs.get("tools") == {} or (
            len(chat_call.args) > 5 and chat_call.args[5] == {}
        )

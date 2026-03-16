"""Tests for make_tools_openai() and make_tools_gemini() format converters."""

from __future__ import annotations

from hadron.agent.tools import make_tools, make_tools_openai, make_tools_gemini


ALLOWED = ["read_file", "write_file", "list_directory", "run_command", "delete_file"]


class TestMakeToolsOpenAI:
    def test_returns_function_type_wrapper(self) -> None:
        tools = make_tools_openai(ALLOWED, "/tmp")
        assert len(tools) == 5
        for t in tools:
            assert t["type"] == "function"
            assert "function" in t
            fn = t["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn

    def test_names_match_anthropic(self) -> None:
        anthropic_tools = make_tools(ALLOWED, "/tmp")
        openai_tools = make_tools_openai(ALLOWED, "/tmp")
        anthropic_names = {t["name"] for t in anthropic_tools}
        openai_names = {t["function"]["name"] for t in openai_tools}
        assert anthropic_names == openai_names

    def test_parameters_match_input_schema(self) -> None:
        anthropic_tools = make_tools(ALLOWED, "/tmp")
        openai_tools = make_tools_openai(ALLOWED, "/tmp")
        for at, ot in zip(anthropic_tools, openai_tools):
            assert ot["function"]["parameters"] == at["input_schema"]

    def test_unknown_tool_skipped(self) -> None:
        tools = make_tools_openai(["read_file", "nonexistent"], "/tmp")
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "read_file"

    def test_empty_allowed(self) -> None:
        assert make_tools_openai([], "/tmp") == []


class TestMakeToolsGemini:
    def test_returns_flat_declarations(self) -> None:
        tools = make_tools_gemini(ALLOWED, "/tmp")
        assert len(tools) == 5
        for t in tools:
            assert "name" in t
            assert "description" in t
            assert "parameters" in t
            # Should NOT have "type" key (that's OpenAI-specific)
            assert "type" not in t

    def test_names_match_anthropic(self) -> None:
        anthropic_tools = make_tools(ALLOWED, "/tmp")
        gemini_tools = make_tools_gemini(ALLOWED, "/tmp")
        anthropic_names = {t["name"] for t in anthropic_tools}
        gemini_names = {t["name"] for t in gemini_tools}
        assert anthropic_names == gemini_names

    def test_parameters_match_input_schema(self) -> None:
        anthropic_tools = make_tools(ALLOWED, "/tmp")
        gemini_tools = make_tools_gemini(ALLOWED, "/tmp")
        for at, gt in zip(anthropic_tools, gemini_tools):
            assert gt["parameters"] == at["input_schema"]

    def test_unknown_tool_skipped(self) -> None:
        tools = make_tools_gemini(["read_file", "nonexistent"], "/tmp")
        assert len(tools) == 1

    def test_empty_allowed(self) -> None:
        assert make_tools_gemini([], "/tmp") == []

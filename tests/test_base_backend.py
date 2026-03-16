"""Tests for BaseAgentBackend three-phase orchestration via a mock subclass."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from hadron.agent.base import AgentCallbacks, AgentTask, PhaseConfig
from hadron.agent.base_backend import BaseAgentBackend, _ResultAccumulator
from hadron.agent.tool_loop import ToolLoopConfig, _PhaseResult


class FakeBackend(BaseAgentBackend):
    """Minimal concrete subclass for testing the orchestration logic."""

    def __init__(self) -> None:
        super().__init__()
        self.tool_loop_calls: list[ToolLoopConfig] = []
        self.plan_calls: list[dict] = []
        self._tool_loop_results: list[_PhaseResult] = []
        self._plan_result: _PhaseResult | None = None

    def set_tool_loop_results(self, *results: _PhaseResult) -> None:
        self._tool_loop_results = list(results)

    def set_plan_result(self, result: _PhaseResult) -> None:
        self._plan_result = result

    async def _call_tool_loop(self, cfg: ToolLoopConfig) -> _PhaseResult:
        self.tool_loop_calls.append(cfg)
        return self._tool_loop_results.pop(0)

    async def _call_plan(self, *, model, system_prompt, user_prompt, max_tokens) -> _PhaseResult:
        self.plan_calls.append({
            "model": model, "system_prompt": system_prompt,
            "user_prompt": user_prompt, "max_tokens": max_tokens,
        })
        assert self._plan_result is not None
        return self._plan_result


def _phase_result(output: str = "done", model: str = "m", inp: int = 100, out: int = 50) -> _PhaseResult:
    return _PhaseResult(
        output=output, model=model,
        input_tokens=inp, output_tokens=out, cost_usd=0.01,
        tool_calls=[], conversation=[], round_count=1,
    )


class TestSinglePhase:
    @pytest.mark.asyncio
    async def test_no_phases_runs_only_act(self, tmp_workdir: Path) -> None:
        backend = FakeBackend()
        backend.set_tool_loop_results(_phase_result("Act done"))

        task = AgentTask(
            role="test", system_prompt="sys", user_prompt="do it",
            working_directory=str(tmp_workdir),
            phases=PhaseConfig(explore_model="", plan_model=""),
        )
        result = await backend.execute(task)

        assert result.output == "Act done"
        assert len(backend.tool_loop_calls) == 1
        assert len(backend.plan_calls) == 0

    @pytest.mark.asyncio
    async def test_user_prompt_passed_unchanged(self, tmp_workdir: Path) -> None:
        backend = FakeBackend()
        backend.set_tool_loop_results(_phase_result())

        task = AgentTask(
            role="test", system_prompt="sys", user_prompt="original prompt",
            working_directory=str(tmp_workdir),
            phases=PhaseConfig(explore_model="", plan_model=""),
        )
        await backend.execute(task)

        assert backend.tool_loop_calls[0].user_prompt == "original prompt"


class TestThreePhases:
    @pytest.mark.asyncio
    async def test_all_three_phases_run(self, tmp_workdir: Path) -> None:
        backend = FakeBackend()
        backend.set_tool_loop_results(
            _phase_result("Exploration summary"),  # explore
            _phase_result("Act done"),             # act
        )
        backend.set_plan_result(_phase_result("The plan"))

        task = AgentTask(
            role="test", system_prompt="sys", user_prompt="task",
            working_directory=str(tmp_workdir),
            model="act-model",
            phases=PhaseConfig(
                explore_model="explore-model",
                plan_model="plan-model",
            ),
        )
        result = await backend.execute(task)

        assert len(backend.tool_loop_calls) == 2  # explore + act
        assert len(backend.plan_calls) == 1
        assert result.output == "Act done"

    @pytest.mark.asyncio
    async def test_explore_model_passed_to_tool_loop(self, tmp_workdir: Path) -> None:
        backend = FakeBackend()
        backend.set_tool_loop_results(
            _phase_result("Summary"),
            _phase_result("Done"),
        )
        backend.set_plan_result(_phase_result("Plan"))

        task = AgentTask(
            role="test", system_prompt="sys", user_prompt="task",
            working_directory=str(tmp_workdir),
            phases=PhaseConfig(explore_model="haiku", plan_model="opus"),
        )
        await backend.execute(task)

        assert backend.tool_loop_calls[0].model == "haiku"

    @pytest.mark.asyncio
    async def test_plan_receives_exploration_summary(self, tmp_workdir: Path) -> None:
        backend = FakeBackend()
        backend.set_tool_loop_results(
            _phase_result("Found src/ and tests/"),
            _phase_result("Done"),
        )
        backend.set_plan_result(_phase_result("Plan"))

        task = AgentTask(
            role="test", system_prompt="sys", user_prompt="task",
            working_directory=str(tmp_workdir),
            phases=PhaseConfig(explore_model="haiku", plan_model="opus"),
        )
        await backend.execute(task)

        plan_user = backend.plan_calls[0]["user_prompt"]
        assert "Found src/ and tests/" in plan_user
        assert "task" in plan_user

    @pytest.mark.asyncio
    async def test_act_receives_plan_and_exploration(self, tmp_workdir: Path) -> None:
        backend = FakeBackend()
        backend.set_tool_loop_results(
            _phase_result("Exploration context"),
            _phase_result("Done"),
        )
        backend.set_plan_result(_phase_result("Step 1: do X"))

        task = AgentTask(
            role="test", system_prompt="sys", user_prompt="task",
            working_directory=str(tmp_workdir),
            phases=PhaseConfig(explore_model="haiku", plan_model="opus"),
        )
        await backend.execute(task)

        act_user = backend.tool_loop_calls[1].user_prompt
        assert "Step 1: do X" in act_user
        assert "Exploration context" in act_user


class TestCostAggregation:
    @pytest.mark.asyncio
    async def test_costs_aggregated_across_phases(self, tmp_workdir: Path) -> None:
        backend = FakeBackend()
        backend.set_tool_loop_results(
            _phase_result(inp=1000, out=500),
            _phase_result(inp=3000, out=1500),
        )
        backend.set_plan_result(_phase_result(inp=2000, out=1000))

        task = AgentTask(
            role="test", system_prompt="sys", user_prompt="task",
            working_directory=str(tmp_workdir),
            phases=PhaseConfig(explore_model="haiku", plan_model="opus"),
        )
        result = await backend.execute(task)

        assert result.input_tokens == 6000
        assert result.output_tokens == 3000
        assert result.cost_usd == pytest.approx(0.03)


class TestPhaseEvents:
    @pytest.mark.asyncio
    async def test_phase_events_emitted(self, tmp_workdir: Path) -> None:
        backend = FakeBackend()
        backend.set_tool_loop_results(
            _phase_result("Summary"),
            _phase_result("Done"),
        )
        backend.set_plan_result(_phase_result("Plan"))

        events: list[tuple[str, dict]] = []

        async def capture(event_type: str, data: dict) -> None:
            events.append((event_type, data))

        task = AgentTask(
            role="test", system_prompt="sys", user_prompt="task",
            working_directory=str(tmp_workdir),
            phases=PhaseConfig(explore_model="haiku", plan_model="opus"),
            callbacks=AgentCallbacks(on_event=capture),
        )
        await backend.execute(task)

        phase_started = [d for t, d in events if t == "phase_started"]
        phase_completed = [d for t, d in events if t == "phase_completed"]

        assert len(phase_started) == 3
        assert len(phase_completed) == 3
        assert phase_started[0]["phase"] == "explore"
        assert phase_started[1]["phase"] == "plan"
        assert phase_started[2]["phase"] == "act"

    @pytest.mark.asyncio
    async def test_no_phase_events_when_single_phase(self, tmp_workdir: Path) -> None:
        backend = FakeBackend()
        backend.set_tool_loop_results(_phase_result("Done"))

        events: list[tuple[str, dict]] = []

        async def capture(event_type: str, data: dict) -> None:
            events.append((event_type, data))

        task = AgentTask(
            role="test", system_prompt="sys", user_prompt="task",
            working_directory=str(tmp_workdir),
            phases=PhaseConfig(explore_model="", plan_model=""),
            callbacks=AgentCallbacks(on_event=capture),
        )
        await backend.execute(task)

        phase_events = [e for e in events if e[0].startswith("phase_")]
        assert len(phase_events) == 0


class TestStreamNotSupported:
    @pytest.mark.asyncio
    async def test_stream_raises(self, tmp_workdir: Path) -> None:
        backend = FakeBackend()
        task = AgentTask(
            role="test", system_prompt="sys", user_prompt="task",
            working_directory=str(tmp_workdir),
        )
        with pytest.raises(NotImplementedError, match="FakeBackend"):
            async for _ in backend.stream(task):
                pass

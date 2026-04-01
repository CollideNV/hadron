"""Tests for pipeline graph structure."""

from __future__ import annotations

from langgraph.graph import END

from hadron.pipeline.graph import build_pipeline_graph


EXPECTED_NODES = {
    "intake",
    "repo_id",
    "worktree_setup",
    "translation",
    "verification",
    "implementation",
    "rework",
    "e2e_testing",
    "review",
    "rebase",
    "delivery",
    "release",
    "paused",
}


class TestGraphNodes:
    def test_has_exactly_expected_nodes(self) -> None:
        graph = build_pipeline_graph()
        assert set(graph.nodes.keys()) == EXPECTED_NODES

    def test_does_not_have_release_gate(self) -> None:
        graph = build_pipeline_graph()
        assert "release_gate" not in graph.nodes

    def test_does_not_have_retrospective(self) -> None:
        graph = build_pipeline_graph()
        assert "retrospective" not in graph.nodes


class TestEntryPoint:
    def test_entry_point_is_intake(self) -> None:
        graph = build_pipeline_graph()
        compiled = graph.compile()
        # The compiled graph exposes the first node via get_graph()
        fg = compiled.get_graph()
        # __start__ node should have a single edge to intake
        start_edges = [e for e in fg.edges if e.source == "__start__"]
        assert len(start_edges) == 1
        assert start_edges[0].target == "intake"


class TestLinearEdges:
    """Verify the non-conditional (linear) edges in the graph."""

    def _get_plain_edges(self) -> set[tuple[str, str]]:
        graph = build_pipeline_graph()
        compiled = graph.compile()
        fg = compiled.get_graph()
        return {(e.source, e.target) for e in fg.edges if not e.conditional}

    def test_intake_to_repo_id(self) -> None:
        assert ("intake", "repo_id") in self._get_plain_edges()

    def test_repo_id_to_worktree_setup(self) -> None:
        assert ("repo_id", "worktree_setup") in self._get_plain_edges()

    def test_worktree_setup_to_translation(self) -> None:
        assert ("worktree_setup", "translation") in self._get_plain_edges()

    def test_translation_to_verification(self) -> None:
        assert ("translation", "verification") in self._get_plain_edges()

    def test_delivery_to_release(self) -> None:
        assert ("delivery", "release") in self._get_plain_edges()

    def test_release_to_end(self) -> None:
        assert ("release", "__end__") in self._get_plain_edges()

    def test_paused_to_end(self) -> None:
        assert ("paused", "__end__") in self._get_plain_edges()


class TestConditionalEdges:
    """Verify that conditional edges exist after verification, review, and rebase."""

    def _get_conditional_sources(self) -> set[str]:
        graph = build_pipeline_graph()
        compiled = graph.compile()
        fg = compiled.get_graph()
        return {e.source for e in fg.edges if e.conditional}

    def test_verification_has_conditional_edge(self) -> None:
        assert "verification" in self._get_conditional_sources()

    def test_review_has_conditional_edge(self) -> None:
        assert "review" in self._get_conditional_sources()

    def test_rebase_has_conditional_edge(self) -> None:
        assert "rebase" in self._get_conditional_sources()

    def test_implementation_has_conditional_edge(self) -> None:
        assert "implementation" in self._get_conditional_sources()

    def test_rework_has_conditional_edge(self) -> None:
        assert "rework" in self._get_conditional_sources()

    def test_e2e_testing_has_conditional_edge(self) -> None:
        assert "e2e_testing" in self._get_conditional_sources()

    def test_conditional_edge_count(self) -> None:
        """Verification, review, rebase, implementation, rework, and e2e_testing should have conditional edges."""
        assert self._get_conditional_sources() == {
            "verification", "review", "rebase", "implementation", "rework", "e2e_testing",
        }

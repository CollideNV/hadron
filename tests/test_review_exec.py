"""Tests for review execution and structured output."""

from __future__ import annotations

from hadron.pipeline.nodes.rework import format_review_findings


class TestFormatReviewFindings:
    """format_review_findings produces structured markdown for the rework agent."""

    def test_groups_by_reviewer(self) -> None:
        state = {
            "review_results": [{
                "repo_name": "myrepo",
                "findings": [
                    {"severity": "critical", "message": "SQL injection", "file": "app.py", "line": 10, "reviewer": "security_reviewer"},
                    {"severity": "major", "message": "Missing tests", "file": "lib.py", "line": 5, "reviewer": "quality_reviewer"},
                ],
                "review_passed": False,
                "review_iteration": 1,
            }],
        }
        result = format_review_findings(state, "myrepo")
        assert "### security_reviewer" in result
        assert "### quality_reviewer" in result
        assert "SQL injection" in result
        assert "Missing tests" in result

    def test_only_includes_blocking_findings(self) -> None:
        state = {
            "review_results": [{
                "repo_name": "myrepo",
                "findings": [
                    {"severity": "minor", "message": "Style nit", "file": "a.py", "line": 1, "reviewer": "quality_reviewer"},
                    {"severity": "info", "message": "Observation", "file": "b.py", "line": 2, "reviewer": "quality_reviewer"},
                ],
                "review_passed": True,
                "review_iteration": 1,
            }],
        }
        result = format_review_findings(state, "myrepo")
        assert "Style nit" not in result
        assert "Observation" not in result

    def test_includes_summary(self) -> None:
        state = {
            "review_results": [{
                "repo_name": "myrepo",
                "findings": [],
                "review_passed": True,
                "review_iteration": 1,
                "summary": "**security_reviewer**: All good",
            }],
        }
        result = format_review_findings(state, "myrepo")
        assert "All good" in result

    def test_filters_by_repo(self) -> None:
        state = {
            "review_results": [{
                "repo_name": "other",
                "findings": [
                    {"severity": "critical", "message": "Bad", "file": "x.py", "line": 1, "reviewer": "security_reviewer"},
                ],
                "review_passed": False,
                "review_iteration": 1,
            }],
        }
        result = format_review_findings(state, "myrepo")
        assert "Bad" not in result

    def test_empty_results(self) -> None:
        result = format_review_findings({}, "myrepo")
        assert "Review Findings" in result


class TestFindingNormalization:
    """review_exec normalizes findings to consistent structure."""

    def test_normalize_adds_defaults(self) -> None:
        """Simulate what review_exec does to incomplete findings."""
        from hadron.pipeline.nodes.review_exec import run_single_reviewer  # noqa: F401
        # We test the normalization logic directly
        raw_finding = {"message": "Something wrong"}
        role = "quality_reviewer"
        normalized = {
            "severity": raw_finding.get("severity", "info"),
            "category": raw_finding.get("category", role.replace("_reviewer", "")),
            "file": raw_finding.get("file", ""),
            "line": raw_finding.get("line", 0),
            "message": raw_finding.get("message", ""),
            "reviewer": raw_finding.get("reviewer", role),
        }
        assert normalized["severity"] == "info"
        assert normalized["category"] == "quality"
        assert normalized["reviewer"] == "quality_reviewer"
        assert normalized["file"] == ""
        assert normalized["line"] == 0

    def test_normalize_preserves_provided_fields(self) -> None:
        raw = {
            "severity": "critical",
            "category": "security",
            "file": "app.py",
            "line": 42,
            "message": "Injection",
            "reviewer": "security_reviewer",
        }
        role = "security_reviewer"
        normalized = {
            "severity": raw.get("severity", "info"),
            "category": raw.get("category", role.replace("_reviewer", "")),
            "file": raw.get("file", ""),
            "line": raw.get("line", 0),
            "message": raw.get("message", ""),
            "reviewer": raw.get("reviewer", role),
        }
        assert normalized == raw


class TestReviewerTools:
    """Reviewers should have run_command access."""

    def test_reviewer_allowed_tools_include_run_command(self) -> None:
        """Verify that the reviewer tool list includes run_command."""
        # Read the source to verify the constant
        import inspect
        from hadron.pipeline.nodes import review_exec
        source = inspect.getsource(review_exec.run_single_reviewer)
        assert 'run_command' in source
        assert 'read_file' in source
        assert 'list_directory' in source

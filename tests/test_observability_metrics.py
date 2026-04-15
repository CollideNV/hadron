"""Tests for Prometheus metrics module."""

from __future__ import annotations

import pytest

from hadron.observability.metrics import (
    AGENT_RUNS_TOTAL,
    AGENT_TOKENS,
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION,
    PIPELINE_COST_USD,
    PIPELINE_RUNS_TOTAL,
    generate_metrics,
    metrics_available,
    record_worker_metrics,
)


class TestMetricsAvailability:
    """metrics_available() depends on prometheus-client install."""

    def test_reports_availability(self) -> None:
        # Just verify it returns a bool — actual value depends on environment
        assert isinstance(metrics_available(), bool)


class TestGenerateMetrics:
    """generate_metrics() returns Prometheus text format."""

    @pytest.mark.skipif(not metrics_available(), reason="prometheus-client not installed")
    def test_returns_bytes(self) -> None:
        output = generate_metrics()
        assert isinstance(output, bytes)

    def test_returns_empty_when_unavailable(self) -> None:
        if not metrics_available():
            assert generate_metrics() == b""


class TestRecordWorkerMetrics:
    """record_worker_metrics() processes payloads from workers."""

    @pytest.mark.skipif(not metrics_available(), reason="prometheus-client not installed")
    def test_records_pipeline_run(self) -> None:
        payload = {
            "status": "completed",
            "cr_id": "CR-TEST",
            "repo_name": "test-repo",
            "stage": "review",
            "role": "reviewer",
            "model": "claude-sonnet-4-20250514",
            "input_tokens": 1000,
            "output_tokens": 500,
            "cost_usd": 0.05,
            "duration_seconds": 30.0,
        }
        # Should not raise
        record_worker_metrics(payload)

    def test_handles_empty_payload(self) -> None:
        # Should not raise even with minimal data
        record_worker_metrics({})

    def test_handles_missing_fields(self) -> None:
        record_worker_metrics({"status": "failed"})

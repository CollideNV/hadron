"""Tests for hadron.observability.error_classifier."""

from __future__ import annotations

import pytest

from hadron.observability.error_classifier import classify_error


class TestClassifyError:
    def test_completed_returns_none(self):
        assert classify_error({"status": "completed"}) is None

    def test_budget_exceeded(self):
        assert classify_error({
            "status": "paused",
            "pause_reason": "budget_exceeded",
        }) == "budget_exceeded"

    def test_rebase_conflict(self):
        assert classify_error({
            "status": "paused",
            "pause_reason": "rebase_conflict",
        }) == "rebase_conflict"

    def test_review_circuit_breaker(self):
        result = classify_error({
            "status": "paused",
            "pause_reason": "circuit_breaker",
            "review_loop_count": 3,
            "verification_loop_count": 0,
            "config_snapshot": {"pipeline": {"max_review_dev_loops": 3}},
        })
        assert result == "review_circuit_breaker"

    def test_verification_circuit_breaker(self):
        result = classify_error({
            "status": "paused",
            "pause_reason": "circuit_breaker",
            "review_loop_count": 0,
            "verification_loop_count": 3,
            "config_snapshot": {"pipeline": {"max_verification_loops": 3}},
        })
        assert result == "verification_circuit_breaker"

    def test_generic_circuit_breaker(self):
        result = classify_error({
            "status": "paused",
            "pause_reason": "circuit_breaker",
        })
        assert result == "circuit_breaker"

    def test_api_error_from_text(self):
        assert classify_error({
            "status": "failed",
            "error": "APIError: 503 Service Unavailable",
        }) == "api_error"

    def test_rate_limit_error(self):
        assert classify_error({
            "status": "failed",
            "error": "Rate limit exceeded for model",
        }) == "api_error"

    def test_timeout_error(self):
        assert classify_error({
            "status": "failed",
            "error": "Connection timeout after 30s",
        }) == "api_error"

    def test_test_failure(self):
        assert classify_error({
            "status": "paused",
            "error": "Tests did not pass after 3 attempts",
        }) == "test_failure"

    def test_agent_crash_generic_error(self):
        assert classify_error({
            "status": "failed",
            "error": "KeyError: 'missing_key'",
        }) == "agent_crash"

    def test_unknown_when_no_error(self):
        assert classify_error({"status": "paused"}) == "unknown"

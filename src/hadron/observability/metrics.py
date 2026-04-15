"""Prometheus metrics for Hadron.

All metrics are defined lazily so that the module can be imported safely even
when ``prometheus-client`` is not installed (the ``[observability]`` extra is
optional).  Functions that record metrics silently no-op if the library is
missing.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

    REGISTRY = CollectorRegistry()

    # ── HTTP metrics (recorded by RequestIdMiddleware) ──────────────────────

    HTTP_REQUESTS_TOTAL = Counter(
        "hadron_http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status"],
        registry=REGISTRY,
    )

    HTTP_REQUEST_DURATION = Histogram(
        "hadron_http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "path"],
        buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
        registry=REGISTRY,
    )

    # ── Pipeline metrics ────────────────────────────────────────────────────

    PIPELINE_RUNS_TOTAL = Counter(
        "hadron_pipeline_runs_total",
        "Total pipeline runs started",
        ["status"],
        registry=REGISTRY,
    )

    PIPELINE_STAGE_DURATION = Histogram(
        "hadron_pipeline_stage_duration_seconds",
        "Duration of individual pipeline stages",
        ["stage"],
        buckets=(1, 5, 10, 30, 60, 120, 300, 600),
        registry=REGISTRY,
    )

    PIPELINE_COST_USD = Counter(
        "hadron_pipeline_cost_usd_total",
        "Cumulative LLM spend in USD",
        ["cr_id", "stage"],
        registry=REGISTRY,
    )

    # ── Agent metrics ───────────────────────────────────────────────────────

    AGENT_RUNS_TOTAL = Counter(
        "hadron_agent_runs_total",
        "Agent invocations",
        ["role", "model"],
        registry=REGISTRY,
    )

    AGENT_TOKENS = Counter(
        "hadron_agent_tokens_total",
        "Token usage by direction",
        ["direction", "model"],
        registry=REGISTRY,
    )

    AGENT_TOOL_CALLS = Counter(
        "hadron_agent_tool_calls_total",
        "Tool calls by tool name",
        ["tool"],
        registry=REGISTRY,
    )

    AGENT_DURATION = Histogram(
        "hadron_agent_duration_seconds",
        "Agent execution time",
        ["role"],
        buckets=(1, 5, 10, 30, 60, 120, 300, 600),
        registry=REGISTRY,
    )

    # ── Worker gauge ────────────────────────────────────────────────────────

    ACTIVE_WORKERS = Gauge(
        "hadron_active_workers",
        "Number of currently running worker pods/processes",
        registry=REGISTRY,
    )

    _AVAILABLE = True

except ImportError:
    _AVAILABLE = False
    REGISTRY = None  # type: ignore[assignment]

    # Stubs so callers don't need to guard every access
    class _Stub:  # type: ignore[no-redef]
        """No-op stand-in when prometheus-client is not installed."""
        def labels(self, **_: Any) -> "_Stub":
            return self
        def inc(self, _: float = 1) -> None: ...
        def dec(self, _: float = 1) -> None: ...
        def observe(self, _: float) -> None: ...
        def set(self, _: float) -> None: ...

    _s = _Stub()
    HTTP_REQUESTS_TOTAL = _s  # type: ignore[assignment]
    HTTP_REQUEST_DURATION = _s  # type: ignore[assignment]
    PIPELINE_RUNS_TOTAL = _s  # type: ignore[assignment]
    PIPELINE_STAGE_DURATION = _s  # type: ignore[assignment]
    PIPELINE_COST_USD = _s  # type: ignore[assignment]
    AGENT_RUNS_TOTAL = _s  # type: ignore[assignment]
    AGENT_TOKENS = _s  # type: ignore[assignment]
    AGENT_TOOL_CALLS = _s  # type: ignore[assignment]
    AGENT_DURATION = _s  # type: ignore[assignment]
    ACTIVE_WORKERS = _s  # type: ignore[assignment]


def metrics_available() -> bool:
    """Return True if prometheus-client is installed and metrics are live."""
    return _AVAILABLE


def generate_metrics() -> bytes:
    """Serialize all registered metrics in Prometheus text exposition format."""
    if not _AVAILABLE:
        return b""
    return generate_latest(REGISTRY)


# ── Worker → Controller relay via Redis pub/sub ─────────────────────────────

METRICS_CHANNEL = "hadron:metrics"


async def publish_worker_metrics(redis: Any, payload: dict[str, Any]) -> None:
    """Publish a metrics payload from a worker to the controller via Redis."""
    import json

    await redis.publish(METRICS_CHANNEL, json.dumps(payload))


def record_worker_metrics(payload: dict[str, Any]) -> None:
    """Record a metrics payload received from a worker (called on the controller).

    Expected payload keys:
        status, cr_id, repo_name, stage, role, model,
        input_tokens, output_tokens, cost_usd, tool_calls_count,
        duration_seconds
    """
    if not _AVAILABLE:
        return

    status = payload.get("status", "completed")
    PIPELINE_RUNS_TOTAL.labels(status=status).inc()

    stage = payload.get("stage", "")
    if stage and "duration_seconds" in payload:
        PIPELINE_STAGE_DURATION.labels(stage=stage).observe(payload["duration_seconds"])

    cr_id = payload.get("cr_id", "")
    cost = payload.get("cost_usd", 0.0)
    if cost and cr_id:
        PIPELINE_COST_USD.labels(cr_id=cr_id, stage=stage).inc(cost)

    role = payload.get("role", "")
    model = payload.get("model", "")
    if role:
        AGENT_RUNS_TOTAL.labels(role=role, model=model).inc()

    input_tokens = payload.get("input_tokens", 0)
    output_tokens = payload.get("output_tokens", 0)
    if input_tokens:
        AGENT_TOKENS.labels(direction="input", model=model).inc(input_tokens)
    if output_tokens:
        AGENT_TOKENS.labels(direction="output", model=model).inc(output_tokens)

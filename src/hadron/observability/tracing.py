"""OpenTelemetry tracing for Hadron.

Disabled by default (``otel_enabled=False``).  When enabled, exports spans
via OTLP gRPC to the configured ``otlp_endpoint``.  Zero overhead when off —
all span helpers return no-op contexts.

Span hierarchy:
    pipeline_node (stage) → run_agent (role) → base_backend phase (explore/plan/act)
        → tool_loop (LLM API call) → tool_loop (tool execution)

Trace context is propagated from the controller to the worker via the
``TRACEPARENT`` environment variable so that the entire CR lifecycle appears
as a single distributed trace.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Generator

_AVAILABLE = False
_tracer: Any = None  # Will be a real or no-op Tracer

try:
    from opentelemetry import trace
    from opentelemetry.context.contextvars_context import ContextVarsRuntimeContext
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _OTEL_SDK = True
except ImportError:
    _OTEL_SDK = False


def configure_tracing(
    *,
    enabled: bool = False,
    otlp_endpoint: str = "http://localhost:4317",
    service_name: str = "hadron",
) -> None:
    """Initialise the OpenTelemetry tracer provider.

    Call once at process startup (controller lifespan or worker main).
    Safe to call even when the ``[observability]`` extra is not installed —
    does nothing in that case.
    """
    global _AVAILABLE, _tracer

    if not enabled or not _OTEL_SDK:
        _AVAILABLE = False
        _tracer = _NoOpTracer()
        return

    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    _tracer = trace.get_tracer("hadron")
    _AVAILABLE = True

    # Restore propagated trace context from the controller (if present)
    _restore_propagated_context()


def get_tracer() -> Any:
    """Return the configured tracer (real or no-op)."""
    if _tracer is None:
        return _NoOpTracer()
    return _tracer


def tracing_available() -> bool:
    """Return True when OTel tracing is enabled and configured."""
    return _AVAILABLE


# ── Span helpers ────────────────────────────────────────────────────────────


@contextmanager
def span(name: str, attributes: dict[str, Any] | None = None) -> Generator[Any, None, None]:
    """Start a new span as a context manager.

    When tracing is disabled this is a zero-cost no-op.
    """
    if not _AVAILABLE:
        yield None
        return

    tracer = get_tracer()
    with tracer.start_as_current_span(name, attributes=attributes or {}) as s:
        yield s


def set_span_attributes(s: Any, attrs: dict[str, Any]) -> None:
    """Safely set attributes on a span (no-ops if span is None)."""
    if s is None:
        return
    for k, v in attrs.items():
        if isinstance(v, (str, int, float, bool)):
            s.set_attribute(k, v)


def record_span_error(s: Any, error: Exception) -> None:
    """Record an exception on the current span."""
    if s is None:
        return
    s.set_status(trace.StatusCode.ERROR, str(error))
    s.record_exception(error)


# ── Trace context propagation (controller → worker) ────────────────────────


def inject_trace_context() -> dict[str, str]:
    """Extract current trace context as env-var-safe key-value pairs.

    The controller calls this before spawning a worker to propagate
    the trace context via environment variables.
    """
    if not _AVAILABLE:
        return {}

    from opentelemetry import context
    from opentelemetry.propagators.textmap import DictGetter
    from opentelemetry.propagate import inject

    carrier: dict[str, str] = {}
    inject(carrier)
    # Convert to env vars: TRACEPARENT, TRACESTATE
    env = {}
    for k, v in carrier.items():
        env[k.upper().replace("-", "")] = v
    return env


def _restore_propagated_context() -> None:
    """Restore trace context from environment variables set by the controller."""
    traceparent = os.environ.get("TRACEPARENT")
    if not traceparent or not _AVAILABLE:
        return

    from opentelemetry.propagate import extract

    carrier = {"traceparent": traceparent}
    tracestate = os.environ.get("TRACESTATE")
    if tracestate:
        carrier["tracestate"] = tracestate

    ctx = extract(carrier)
    from opentelemetry import context

    context.attach(ctx)


# ── No-op fallback ──────────────────────────────────────────────────────────


class _NoOpSpan:
    """Minimal no-op span for when tracing is disabled."""

    def set_attribute(self, key: str, value: Any) -> None: ...
    def set_status(self, *args: Any, **kwargs: Any) -> None: ...
    def record_exception(self, exception: Exception) -> None: ...
    def end(self) -> None: ...
    def __enter__(self) -> "_NoOpSpan":
        return self
    def __exit__(self, *args: Any) -> None: ...


class _NoOpTracer:
    """Minimal no-op tracer for when tracing is disabled."""

    def start_as_current_span(
        self, name: str, **kwargs: Any,
    ) -> _NoOpSpan:
        return _NoOpSpan()

    def start_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()

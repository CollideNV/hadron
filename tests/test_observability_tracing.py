"""Tests for OpenTelemetry tracing module."""

from __future__ import annotations

from hadron.observability.tracing import (
    _NoOpSpan,
    _NoOpTracer,
    configure_tracing,
    get_tracer,
    inject_trace_context,
    record_span_error,
    set_span_attributes,
    span,
    tracing_available,
)


class TestTracingDisabledByDefault:
    """When otel_enabled=False (default), everything is a no-op."""

    def test_not_available_by_default(self) -> None:
        configure_tracing(enabled=False)
        assert tracing_available() is False

    def test_get_tracer_returns_noop(self) -> None:
        configure_tracing(enabled=False)
        tracer = get_tracer()
        assert isinstance(tracer, _NoOpTracer)

    def test_span_context_manager_noop(self) -> None:
        configure_tracing(enabled=False)
        with span("test.span", {"key": "value"}) as s:
            assert s is None

    def test_inject_trace_context_empty(self) -> None:
        configure_tracing(enabled=False)
        ctx = inject_trace_context()
        assert ctx == {}


class TestNoOpSpan:
    """_NoOpSpan methods do nothing and don't raise."""

    def test_set_attribute(self) -> None:
        s = _NoOpSpan()
        s.set_attribute("key", "value")

    def test_context_manager(self) -> None:
        s = _NoOpSpan()
        with s as inner:
            assert inner is s

    def test_record_exception(self) -> None:
        s = _NoOpSpan()
        s.record_exception(ValueError("test"))


class TestSpanHelpers:
    """set_span_attributes / record_span_error handle None spans."""

    def test_set_attributes_none(self) -> None:
        set_span_attributes(None, {"key": "value"})

    def test_record_error_none(self) -> None:
        record_span_error(None, ValueError("test"))

"""Tests for structured logging configuration."""

from __future__ import annotations

import json
import logging
from io import StringIO

import structlog

from hadron.observability.logging import (
    bind_contextvars,
    clear_contextvars,
    configure_logging,
)


class TestConfigureLogging:
    """configure_logging() sets up structlog + stdlib."""

    def test_json_format(self) -> None:
        configure_logging(level="DEBUG", log_format="json")
        buf = StringIO()
        root = logging.getLogger()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(root.handlers[0].formatter)
        root.addHandler(handler)
        try:
            logger = structlog.stdlib.get_logger("test_json")
            logger.info("hello", key="val")
            output = buf.getvalue()
            parsed = json.loads(output.strip())
            assert parsed["event"] == "hello"
            assert parsed["key"] == "val"
            assert parsed["level"] == "info"
        finally:
            root.removeHandler(handler)

    def test_text_format(self) -> None:
        configure_logging(level="INFO", log_format="text")
        root = logging.getLogger()
        # Should have exactly one handler (the stderr one)
        assert len(root.handlers) == 1
        assert root.level == logging.INFO

    def test_level_respected(self) -> None:
        configure_logging(level="WARNING", log_format="text")
        assert logging.getLogger().level == logging.WARNING

    def test_noisy_loggers_quieted(self) -> None:
        configure_logging(level="DEBUG", log_format="text")
        for name in ("httpcore", "httpx", "urllib3", "asyncio"):
            assert logging.getLogger(name).level >= logging.WARNING


class TestContextvars:
    """bind/clear contextvars helpers."""

    def test_bind_and_clear(self) -> None:
        configure_logging(level="DEBUG", log_format="json")
        clear_contextvars()
        bind_contextvars(cr_id="CR-1", stage="review")
        buf = StringIO()
        root = logging.getLogger()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(root.handlers[0].formatter)
        root.addHandler(handler)
        try:
            logger = structlog.stdlib.get_logger("test_ctx")
            logger.info("ctx_test")
            output = buf.getvalue()
            parsed = json.loads(output.strip())
            assert parsed["cr_id"] == "CR-1"
            assert parsed["stage"] == "review"
        finally:
            root.removeHandler(handler)
            clear_contextvars()

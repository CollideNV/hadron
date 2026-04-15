"""Structured logging configuration using structlog.

Provides a single ``configure_logging()`` entry-point that sets up structlog
wrapping stdlib logging.  Output is either human-friendly coloured text
(default, ``log_format="text"``) or machine-parseable JSON
(``log_format="json"``).

The Redis log handler always emits JSON regardless of the console format so
that dashboard log viewers can parse entries reliably.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_logging(
    *,
    level: str = "INFO",
    log_format: str = "text",
) -> None:
    """Configure structlog + stdlib logging for the entire process.

    Parameters
    ----------
    level:
        Root log level name (e.g. ``"INFO"``, ``"DEBUG"``).
    log_format:
        ``"text"`` for coloured human-friendly output,
        ``"json"`` for newline-delimited JSON.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Shared processors applied to every log entry
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.ExtraAdder(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if log_format == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    # Configure structlog
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib root logger with a structlog formatter
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    # Quiet noisy third-party loggers
    for name in ("httpcore", "httpx", "urllib3", "asyncio"):
        logging.getLogger(name).setLevel(max(log_level, logging.WARNING))


def bind_contextvars(**kwargs: Any) -> None:
    """Bind key-value pairs to the structlog context for the current task/thread.

    These will appear in every subsequent log entry until explicitly cleared.
    Typical usage: ``bind_contextvars(cr_id="CR-42", stage="review")``.
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_contextvars() -> None:
    """Remove all structlog context variables for the current task/thread."""
    structlog.contextvars.clear_contextvars()

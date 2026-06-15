"""Centralized logging configuration for Odysseus — structlog + stdlib.

Two output streams:
  Console (stdout): human-readable colored/plain text, always active.
  File (rotating) : plain text in stdlib format (TIMESTAMP - NAME - LEVEL - MSG),
                    compatible with the diagnostics log terminal UI in settings.

Two modes:
  Normal (default): INFO to console + file.
  Debug (ODYSSEUS_DEBUG=1): DEBUG to console + file, with optional
  per-subsystem filtering via ODYSSEUS_DEBUG_SUBSYSTEMS.

structlog wraps stdlib logging, so libraries using logging.getLogger()
(uvicorn, httpx, etc.) are processed through the same pipeline.
Odysseus code uses structlog.get_logger() for bound context.

Environment variables:
  ODYSSEUS_DEBUG=1                     enable debug mode
  ODYSSEUS_DEBUG_SUBSYSTEMS=odysseus.llm,odysseus.agent
                                        per-subsystem debug (comma-separated)
  ODYSSEUS_LOG_FORMAT=text|json        console format
  ODYSSEUS_LOG_FILE=path               override log file path
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys

import structlog

from src.constants import LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT
from src.log_context import contextvals_to_log
from src.log_redaction import redact_sensitive

DEBUG_MODE = os.getenv("ODYSSEUS_DEBUG", "0") not in ("0", "", "false", "no")
DEBUG_SUBSYSTEMS = [
    s.strip()
    for s in os.getenv("ODYSSEUS_DEBUG_SUBSYSTEMS", "").split(",")
    if s.strip()
]
CONSOLE_FMT = os.getenv("ODYSSEUS_LOG_FORMAT", "text")


def _console_handler() -> logging.StreamHandler:
    h = logging.StreamHandler(sys.stdout)
    return h


def _file_handler() -> logging.handlers.RotatingFileHandler:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    return logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT,
    )


def _console_renderer():
    """Human-readable console output."""
    if CONSOLE_FMT == "json":
        return structlog.dev.ConsoleRenderer(colors=False)
    return structlog.dev.ConsoleRenderer(
        colors=sys.stdout.isatty(),
        exception_formatter=structlog.dev.plain_traceback,
    )


def _file_renderer(logger, method, event_dict):
    """Render to stdlib-compatible plain text: TIMESTAMP - NAME - LEVEL - MSG [k=v ...]

    This format is required by the diagnostics log terminal UI, which parses
    ' - INFO - ', ' - WARNING - ', ' - ERROR - ', ' - DEBUG - ' for colorization.
    """
    ts = event_dict.pop("timestamp", "")
    name = event_dict.pop("logger", "") or ""
    level = (event_dict.pop("level", method) or method).upper()
    event = event_dict.pop("event", "")
    extras = {k: v for k, v in event_dict.items() if not k.startswith("_")}
    suffix = "  " + "  ".join(f"{k}={v}" for k, v in sorted(extras.items())) if extras else ""
    return f"{ts} - {name} - {level} - {event}{suffix}"


def setup_logging() -> None:
    """Configure structlog + stdlib logging. Call once at startup."""

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        contextvals_to_log,
        redact_sensitive,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=_console_renderer(),
        foreign_pre_chain=shared_processors,
    )

    file_formatter = structlog.stdlib.ProcessorFormatter(
        processor=_file_renderer,
        foreign_pre_chain=shared_processors,
    )

    root = logging.getLogger()
    root.handlers.clear()

    ch = _console_handler()
    ch.setFormatter(formatter)
    root.addHandler(ch)

    fh = _file_handler()
    fh.setFormatter(file_formatter)
    root.addHandler(fh)

    if DEBUG_MODE:
        root.setLevel(logging.DEBUG)
        if DEBUG_SUBSYSTEMS:
            for name in DEBUG_SUBSYSTEMS:
                logging.getLogger(name).setLevel(logging.DEBUG)
            for name in list(root.manager.loggerDict):
                if not any(name.startswith(s) for s in DEBUG_SUBSYSTEMS):
                    existing = logging.getLogger(name)
                    if not existing.handlers:
                        existing.setLevel(logging.INFO)
    else:
        root.setLevel(logging.INFO)

    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

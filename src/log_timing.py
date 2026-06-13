"""Performance timing context manager for critical-path operations.

Usage:
    from src.log_timing import timed_operation

    with timed_operation("llm_inference", model="gpt-4"):
        response = await call_llm(...)

Logs at DEBUG level with operation name, duration_ms, and any extra kwargs.
"""

from __future__ import annotations

import time

import structlog


def timed_operation(operation: str, **extra):
    """Context manager that logs operation duration at DEBUG level.

    Not intended for universal use — only for critical paths where
    timing data is valuable for debugging (LLM calls, tool execution,
    agent loop rounds, context building).
    """
    class _Timer:
        def __enter__(self):
            self.start = time.monotonic()
            return self

        def __exit__(self, *exc):
            duration_ms = (time.monotonic() - self.start) * 1000
            structlog.get_logger().debug(
                "timed_operation",
                operation=operation,
                duration_ms=round(duration_ms, 1),
                **extra,
            )

    return _Timer()

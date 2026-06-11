"""Request-scoped context for structlog Correlation IDs.

Uses contextvars so values are automatically propagated through async
call chains without passing them explicitly. The AccessLoggingMiddleware
binds request_id / session_key at the start of each request; every log
call within that request's scope automatically includes them.

Usage:
    from src.log_context import bind_request_context, clear_request_context

    bind_request_context(request_id="abc-123", session_key="sess-456")
    # ... all log calls now include request_id and session_key ...
    clear_request_context()
"""

from __future__ import annotations

import contextvars
import uuid

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)
_session_key: contextvars.ContextVar[str] = contextvars.ContextVar(
    "session_key", default=""
)
_user_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "user_id", default=""
)


def bind_request_context(
    request_id: str | None = None,
    session_key: str | None = None,
    user_id: str | None = None,
) -> str:
    """Bind request-scoped values to the current context.

    Returns the request_id (generated if not provided). The caller
    should store this to include in the X-Request-ID response header.
    """
    rid = request_id or uuid.uuid4().hex[:12]
    _request_id.set(rid)
    if session_key is not None:
        _session_key.set(session_key)
    if user_id is not None:
        _user_id.set(user_id)
    return rid


def clear_request_context() -> None:
    """Clear request-scoped values. Call at the end of each request."""
    _request_id.set("")
    _session_key.set("")
    _user_id.set("")


def get_request_id() -> str:
    return _request_id.get()


def get_session_key() -> str:
    return _session_key.get()


def get_user_id() -> str:
    return _user_id.get()


def contextvals_to_log(logger, method_name, event_dict):
    """structlog processor: inject contextvars into every log event.

    Added to the processor chain in logging_config.setup_logging().
    """
    if req_id := _request_id.get():
        event_dict["request_id"] = req_id
    if sid := _session_key.get():
        event_dict["session_key"] = sid
    if uid := _user_id.get():
        event_dict["user_id"] = uid
    return event_dict

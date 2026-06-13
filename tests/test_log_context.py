"""Tests for src/log_context.py — request-scoped contextvars correlation."""

import pytest
import contextvars
from src.log_context import (
    bind_request_context, clear_request_context,
    get_request_id, get_session_key, get_user_id,
    contextvals_to_log,
)


class TestBindRequestContext:
    def test_generates_request_id(self):
        clear_request_context()
        req_id = bind_request_context()
        assert req_id != ""
        assert len(req_id) == 12  # hex[:12]

    def test_accepts_custom_request_id(self):
        clear_request_context()
        req_id = bind_request_context(request_id="my-custom-id")
        assert req_id == "my-custom-id"
        assert get_request_id() == "my-custom-id"

    def test_binds_session_key(self):
        clear_request_context()
        bind_request_context(session_key="sess-abc")
        assert get_session_key() == "sess-abc"

    def test_binds_user_id(self):
        clear_request_context()
        bind_request_context(user_id="user-xyz")
        assert get_user_id() == "user-xyz"

    def test_clears_context(self):
        bind_request_context(request_id="test-123", session_key="sess-456")
        clear_request_context()
        assert get_request_id() == ""
        assert get_session_key() == ""
        assert get_user_id() == ""


class TestContextvalsToLog:
    def test_injects_request_id_into_event(self):
        clear_request_context()
        bind_request_context(request_id="req-abc")
        event_dict = {"event": "test"}
        result = contextvals_to_log(None, "info", event_dict)
        assert result["request_id"] == "req-abc"
        clear_request_context()

    def test_injects_session_key_into_event(self):
        clear_request_context()
        bind_request_context(session_key="sess-xyz")
        event_dict = {"event": "test"}
        result = contextvals_to_log(None, "info", event_dict)
        assert result["session_key"] == "sess-xyz"
        clear_request_context()

    def test_no_context_leaves_event_unchanged(self):
        clear_request_context()
        event_dict = {"event": "test"}
        result = contextvals_to_log(None, "info", event_dict)
        assert "request_id" not in result
        assert "session_key" not in result
        assert result == {"event": "test"}

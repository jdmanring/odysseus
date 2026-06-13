"""Tests for src/log_redaction.py — key-name-based sensitive data redaction."""

import pytest
from src.log_redaction import redact_sensitive, _is_sensitive_key, _redact_dict


class TestIsSensitiveKey:
    @pytest.mark.parametrize("key", [
        "password", "Password", "PASSWORD",
        "api_key", "apikey", "api-key", "ApiKey",
        "token", "access_token", "refresh_token", "auth_token",
        "secret", "private_key", "ssh_key",
        "cookie", "csrf",
        "ssn", "credit_card", "cvv",
        "authorization", "x_api_key",
    ])
    def test_sensitive_keys_detected(self, key):
        assert _is_sensitive_key(key) is True

    @pytest.mark.parametrize("key", [
        "username", "email", "name", "message",
        "method", "path", "status", "duration_ms",
        "model", "temperature", "max_tokens",
        "timestamp", "level", "logger",
    ])
    def test_non_sensitive_keys_pass(self, key):
        assert _is_sensitive_key(key) is False


class TestRedactDict:
    def test_redacts_password_value(self):
        result = _redact_dict({"password": "secret123"})
        assert result["password"] == "<REDACTED>"

    def test_redacts_api_key_value(self):
        result = _redact_dict({"api_key": "sk-abc123def456"})
        assert result["api_key"] == "<REDACTED>"

    def test_redacts_nested_dict(self):
        result = _redact_dict({
            "user": {"name": "alice", "password": "secret"},
            "status": "ok",
        })
        assert result["user"]["password"] == "<REDACTED>"
        assert result["user"]["name"] == "alice"
        assert result["status"] == "ok"

    def test_preserves_non_sensitive_values(self):
        result = _redact_dict({
            "method": "POST",
            "path": "/api/chat",
            "status": 200,
            "duration_ms": 142.5,
        })
        assert result == {
            "method": "POST",
            "path": "/api/chat",
            "status": 200,
            "duration_ms": 142.5,
        }

    def test_truncates_long_secrets(self):
        long_secret = "a" * 64
        result = _redact_dict({"api_key": long_secret})
        assert result["api_key"] == "aaaa...aaaa"


class TestRedactSensitiveProcessor:
    """Test the structlog processor interface."""

    def test_processor_redacts_event_dict(self):
        event_dict = {
            "event": "user_login",
            "password": "secret123",
            "username": "alice",
        }
        result = redact_sensitive(None, "info", event_dict)
        assert result["password"] == "<REDACTED>"
        assert result["username"] == "alice"
        assert result["event"] == "user_login"

    def test_processor_preserves_event_key(self):
        event_dict = {"event": "http_request", "status": 200}
        result = redact_sensitive(None, "info", event_dict)
        assert result["event"] == "http_request"
        assert result["status"] == 200

    def test_processor_handles_empty_dict(self):
        result = redact_sensitive(None, "info", {})
        assert result == {}

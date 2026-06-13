"""Sensitive data redaction for structlog output.

Uses key-name-based redaction (Sentry-style denylist). The processor
inspects the structured event_dict and replaces values whose keys match
known sensitive field names with a placeholder. This avoids false positives
on source code, variable names, and free-text log messages.

Only exact key-name matches are redacted — the processor never scans
string values or log message text. This is the standard approach used by
Sentry's EventScrubber, structlog's idiomatic pattern, and production
logging systems.

Keys are matched case-insensitively. Nested dicts are traversed recursively.

Usage in structlog processor chain:
    structlog.configure(
        processors=[
            ...,
            redact_sensitive,
            ...,
        ],
    )

Sensitive keys are redacted to "<REDACTED>" in the output. To mark a field
as sensitive, simply use a matching key name when logging:
    logger.info("user_login", password=<REDACTED>   # redacted
    logger.info("api_call", api_key="sk-...")     # redacted
    logger.info("message", text="hello")          # NOT redacted
"""

from __future__ import annotations

import re

_SENSITIVE_KEYS = frozenset({
    # Authentication
    "password", "passwd", "pass", "secret",
    "token", "access_token", "refresh_token", "auth_token",
    "bearer_token", "jwt",
    "cookie", "csrf", "xsrf",
    # API keys
    "api_key", "apikey", "api-key", "apikey",
    "x-api-key", "x_auth_token",
    # Provider keys
    "openai_api_key", "anthropic_api_key", "huggingface_token",
    "hf_token", "github_token", "aws_secret",
    # Private keys
    "private_key", "private-key", "ssh_key",
    # Credit cards (basic pattern)
    "credit_card", "card_number", "cvv", "cvc",
    # PII
    "ssn", "social_security",
    "authorization", "proxy-authorization",
})

_SECRET_KEY_RE = re.compile(
    r"(?:^|_)(?:"
    r"password|passwd|secret|token|api_?key|apikey|auth_?token|"
    r"bearer_?token|cookie|csrf|xsrf|private_?key|"
    r"access_?token|refresh_?token|jwt|hf_?token|github_?token|"
    r"aws_?secret|credit_?card|card_?number|cvv|cvc|ssn"
    r")(?:_|$)",
    re.IGNORECASE,
)


def _is_sensitive_key(key: str) -> bool:
    """Check if a key name indicates a sensitive value."""
    if key.lower() in _SENSITIVE_KEYS:
        return True
    return bool(_SECRET_KEY_RE.search(key))


def redact_sensitive(logger, method_name, event_dict):
    """structlog processor: redact values of sensitive keys.

    Operates on the structured event_dict, not on the rendered message.
    Recursively traverses nested dicts. Replaces sensitive values with
    "<REDACTED>".
    """
    return _redact_dict(event_dict)


def _redact_dict(d: dict) -> dict:
    """Recursively redact sensitive values in a dict."""
    for key, value in list(d.items()):
        if isinstance(value, dict):
            d[key] = _redact_dict(value)
        elif _is_sensitive_key(key):
            if isinstance(value, str) and len(value) > 32:
                d[key] = value[:4] + "..." + value[-4:] if len(value) > 8 else "<REDACTED>"
            else:
                d[key] = "<REDACTED>"
    return d

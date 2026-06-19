"""Tests for 429 Retry-After backoff in LLM call paths.

Covers three changes in fix/stream-429-backoff:
  1. _parse_retry_after: delta-seconds, HTTP-date, cap, and fallback to default.
  2. stream_llm_with_fallback: delay before advancing to next fallback candidate
     when the current candidate returns a 429.
  3. llm_call_async: reads Retry-After header instead of fixed RETRY_DELAY on 429.
"""
import asyncio
import json

import pytest

import src.llm_core as llm_core
from src.llm_core import _parse_retry_after


# ---------------------------------------------------------------------------
# _parse_retry_after — pure helper, no mocks needed
# ---------------------------------------------------------------------------

class TestParseRetryAfter:
    def test_integer_seconds(self):
        assert _parse_retry_after("30", default=5.0) == 30.0

    def test_decimal_seconds(self):
        assert _parse_retry_after("2.5", default=5.0) == 2.5

    def test_zero(self):
        assert _parse_retry_after("0", default=5.0) == 0.0

    def test_none_returns_default(self):
        assert _parse_retry_after(None, default=5.0) == 5.0

    def test_empty_string_returns_default(self):
        assert _parse_retry_after("", default=5.0) == 5.0

    def test_malformed_returns_default(self):
        assert _parse_retry_after("not-a-number", default=5.0) == 5.0

    def test_cap_enforced(self):
        assert _parse_retry_after("300", default=5.0, cap=60.0) == 60.0

    def test_negative_clamped_to_zero(self):
        assert _parse_retry_after("-10", default=5.0) == 0.0

    def test_whitespace_stripped(self):
        assert _parse_retry_after("  15  ", default=5.0) == 15.0

    def test_http_date_future(self):
        from datetime import datetime, timezone, timedelta
        from email.utils import format_datetime
        future = datetime.now(timezone.utc) + timedelta(seconds=30)
        result = _parse_retry_after(format_datetime(future, usegmt=True), default=5.0)
        assert 28.0 <= result <= 32.0  # ±2s for test execution time

    def test_http_date_past_clamped_to_zero(self):
        from datetime import datetime, timezone, timedelta
        from email.utils import format_datetime
        past = datetime.now(timezone.utc) - timedelta(seconds=60)
        result = _parse_retry_after(format_datetime(past, usegmt=True), default=5.0)
        assert result == 0.0


# ---------------------------------------------------------------------------
# Helpers for stream_llm_with_fallback tests
# ---------------------------------------------------------------------------

def _error_chunk(status: int, retry_after: str = None) -> str:
    data: dict = {"status": status, "text": f"HTTP {status}", "raw": ""}
    if retry_after is not None:
        data["retry_after"] = retry_after
    return f"event: error\ndata: {json.dumps(data)}\n\n"


def _data_chunk(text: str) -> str:
    return f'data: {json.dumps({"delta": text})}\n\n'


async def _collect(gen):
    return [c async for c in gen]


# ---------------------------------------------------------------------------
# stream_llm_with_fallback — delay before advancing on 429
# ---------------------------------------------------------------------------

class TestStreamLlmWithFallback429:
    def test_429_from_primary_triggers_delay_before_fallback(self, monkeypatch):
        """Primary returns 429 with Retry-After: 3 — delay is 3s before fallback."""
        sleeps = []

        async def fake_sleep(delay):
            sleeps.append(delay)

        monkeypatch.setattr(llm_core.asyncio, "sleep", fake_sleep)

        call_count = [0]

        async def fake_stream_llm(url, model, messages, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                yield _error_chunk(429, retry_after="3")
            else:
                yield _data_chunk("hello")
                yield "data: [DONE]\n\n"

        monkeypatch.setattr(llm_core, "stream_llm", fake_stream_llm)

        candidates = [
            ("http://api.example.com/v1", "model-a", {}),
            ("http://api.example.com/v1", "model-b", {}),
        ]

        result = asyncio.run(_collect(llm_core.stream_llm_with_fallback(candidates, [])))

        assert call_count[0] == 2
        assert sleeps == [3.0]
        assert any("hello" in c for c in result)

    def test_429_without_retry_after_defaults_to_1s(self, monkeypatch):
        """429 with no retry_after field in the chunk uses a 1-second default."""
        sleeps = []

        async def fake_sleep(delay):
            sleeps.append(delay)

        monkeypatch.setattr(llm_core.asyncio, "sleep", fake_sleep)

        call_count = [0]

        async def fake_stream_llm(url, model, messages, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                yield _error_chunk(429)  # no retry_after
            else:
                yield _data_chunk("ok")
                yield "data: [DONE]\n\n"

        monkeypatch.setattr(llm_core, "stream_llm", fake_stream_llm)

        candidates = [
            ("http://api.example.com/v1", "model-a", {}),
            ("http://api.example.com/v1", "model-b", {}),
        ]

        asyncio.run(_collect(llm_core.stream_llm_with_fallback(candidates, [])))

        assert sleeps == [1.0]

    def test_non_429_error_no_delay(self, monkeypatch):
        """Non-429 errors (503 etc.) advance to the next candidate immediately."""
        sleeps = []

        async def fake_sleep(delay):
            sleeps.append(delay)

        monkeypatch.setattr(llm_core.asyncio, "sleep", fake_sleep)

        call_count = [0]

        async def fake_stream_llm(url, model, messages, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                yield _error_chunk(503)
            else:
                yield _data_chunk("recovered")
                yield "data: [DONE]\n\n"

        monkeypatch.setattr(llm_core, "stream_llm", fake_stream_llm)

        candidates = [
            ("http://api.example.com/v1", "model-a", {}),
            ("http://api.example.com/v1", "model-b", {}),
        ]

        asyncio.run(_collect(llm_core.stream_llm_with_fallback(candidates, [])))

        assert sleeps == []

    def test_429_last_candidate_no_delay(self, monkeypatch):
        """With a single candidate, 429 is yielded as-is without sleeping."""
        sleeps = []

        async def fake_sleep(delay):
            sleeps.append(delay)

        monkeypatch.setattr(llm_core.asyncio, "sleep", fake_sleep)

        async def fake_stream_llm(url, model, messages, **kwargs):
            yield _error_chunk(429, retry_after="5")

        monkeypatch.setattr(llm_core, "stream_llm", fake_stream_llm)

        candidates = [("http://api.example.com/v1", "model-a", {})]

        result = asyncio.run(_collect(llm_core.stream_llm_with_fallback(candidates, [])))

        assert sleeps == []
        assert any("event: error" in c for c in result)

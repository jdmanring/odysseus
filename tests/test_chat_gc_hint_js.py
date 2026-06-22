# Source-text contract tests for the deferred GC hint in chat.js.
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC  = (_REPO / "static/js/chat.js").read_text(encoding="utf-8")


def _gc_block() -> str:
    """Extract the outer GC setTimeout block.

    Finds the outermost setTimeout that contains `_gcPending = true` by walking
    back to the last `setTimeout(function () {` before that marker.  The outer
    close is `}, 2500);`; inner timeouts use 3000ms so there is no ambiguity.
    """
    marker = "_gcPending = true"
    start  = _SRC.rindex("setTimeout(function () {", 0, _SRC.index(marker))
    end    = _SRC.index("}, 2500);", start) + len("}, 2500);")
    return _SRC[start:end]


# ---------------------------------------------------------------------------
# Guard variables
# ---------------------------------------------------------------------------

def test_gc_pending_declared():
    assert "let _gcPending = false" in _SRC


def test_gc_missed_declared():
    # _gcMissed tracks responses that completed while a GC cycle was running.
    # Accepts one- or two-space alignment with _gcPending.
    assert "let _gcMissed" in _SRC and ("_gcMissed  = false" in _SRC or "_gcMissed = false" in _SRC)


# ---------------------------------------------------------------------------
# Primary GC block structure
# ---------------------------------------------------------------------------

def test_gc_pending_checked_before_gc_call():
    # The primary gc() call must be inside a !_gcPending branch, not unconditional.
    body = _gc_block()
    guard_pos = body.index("!_gcPending")
    gc_pos    = body.index("gc({ type: 'major'")
    assert guard_pos < gc_pos, "!_gcPending guard must precede gc() call"


def test_gc_called_with_async_execution():
    body = _gc_block()
    assert "gc({ type: 'major', execution: 'async' })" in body


def test_gc_feature_detected():
    # gc() must be guarded by typeof so it no-ops in regular browsers.
    body = _gc_block()
    assert "typeof gc === 'function'" in body


def test_gc_pending_set_before_gc_call():
    body = _gc_block()
    set_pos = body.index("_gcPending = true")
    gc_pos  = body.index("gc({ type: 'major'")
    assert set_pos < gc_pos, "_gcPending must be set true before gc() call"


def test_gc_pending_cleared_after_timeout():
    body = _gc_block()
    gc_pos    = body.index("gc({ type: 'major'")
    reset_pos = body.index("_gcPending = false", gc_pos)
    assert reset_pos > gc_pos, "_gcPending must be cleared in a nested setTimeout after gc()"


def test_gc_dispatched_with_delay():
    # The outer setTimeout ensures the final render settles before GC starts.
    body = _gc_block()
    assert "}, 2500)" in body


def test_gc_noop_fallback_present():
    # requestIdleCallback fallback for environments without gc() avoids a stall.
    body = _gc_block()
    assert "requestIdleCallback" in body


def test_gc_primary_log_line_present():
    # The primary dispatch must be identifiable by log prefix in wrapper_system.log.
    body = _gc_block()
    assert "[GC] major async dispatched" in body


# ---------------------------------------------------------------------------
# Missed-GC catch-up mechanism
# ---------------------------------------------------------------------------

def test_gc_missed_set_true_when_blocked():
    # When GC is running, a completing response must flag _gcMissed = true.
    body = _gc_block()
    assert "_gcMissed = true" in body


def test_gc_blocked_logs_catchup_queued():
    # The blocked path must emit a log so wrapper_system.log shows the event.
    body = _gc_block()
    assert "[GC] blocked" in body


def test_gc_catchup_dispatched():
    # A catch-up gc() call fires once when the primary cycle completes with _gcMissed set.
    body = _gc_block()
    assert "catch-up dispatched" in body


def test_gc_catchup_gated_on_missed_flag():
    # The catch-up must be gated on `if (_gcMissed`, not unconditional.
    body = _gc_block()
    check_pos   = body.index("if (_gcMissed")
    catchup_pos = body.index("catch-up dispatched")
    assert check_pos < catchup_pos, "catch-up gc() must be gated by _gcMissed check"


def _check_bg_block() -> str:
    start = _SRC.index("export function checkBackgroundStream(")
    end = _SRC.index("\n  export function ", start + 1)
    return _SRC[start:end]


def test_check_background_stream_purges_stale():
    """checkBackgroundStream must purge stale Map entries on every session switch."""
    assert "_purgeStaleBackgroundStreams()" in _check_bg_block()

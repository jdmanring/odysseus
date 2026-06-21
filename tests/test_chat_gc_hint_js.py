"""Static validation of the cooperative GC hint in chat.js.

chat.js is browser-coupled and cannot be imported in pytest. These checks
analyse the source text to lock in the structural contracts for the async GC
hint and its stacking guard:

  Embedded Chromium environments (PyQt, Electron, native wrappers) do not
  receive OS memory-pressure signals that trigger Oilpan's automatic
  collection in regular browsers. The deferred gc() call after each response
  is a cooperative hint for those environments. _gcPending prevents stacking
  concurrent incremental GC cycles, and requestIdleCallback provides a
  graceful fallback when gc() is unavailable.

Root: docs/fork/memory-explosion-research.md
"""

from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC  = (_REPO / "static/js/chat.js").read_text(encoding="utf-8")


def _gc_block() -> str:
    """The setTimeout GC block in the finally handler."""
    marker = "_gcPending = true"
    start  = _SRC.rindex("setTimeout(function () {", 0, _SRC.index(marker))
    end    = _SRC.index("}, 2500);", start) + len("}, 2500);")
    return _SRC[start:end]


# ---------------------------------------------------------------------------
# _gcPending guard variable
# ---------------------------------------------------------------------------

def test_gc_pending_declared():
    assert "let _gcPending = false" in _SRC


# ---------------------------------------------------------------------------
# GC block structure
# ---------------------------------------------------------------------------

def test_gc_pending_checked_before_gc_call():
    body = _gc_block()
    assert "!_gcPending" in body


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


def test_gc_log_line_present():
    body = _gc_block()
    assert "[GC]" in body

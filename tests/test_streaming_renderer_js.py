"""Static validation of the renderTail call counter in streamingRenderer.js.

streamingRenderer.js is browser-coupled (uses DOM) and cannot be imported
in pytest. These checks analyse the source text to lock in the structural
contract for the renderTail() allocation counter:

  renderTail() fires once per SSE token and allocates a holder div each call.
  _rtCalls measures this DOM allocation pressure. finalize() logs the total and
  resets it, so every response produces one '[streamRenderer]' log line that
  verifies how many holder-div allocations occurred during streaming.

Root: docs/fork/memory-explosion-research.md
"""

from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC  = (_REPO / "static/js/streamingRenderer.js").read_text(encoding="utf-8")


def _render_tail_body() -> str:
    start = _SRC.index("function renderTail(")
    end   = _SRC.index("\n  }", start) + 4
    return _SRC[start:end]


def _finalize_body() -> str:
    start = _SRC.index("function finalize()")
    end   = _SRC.index("\n  return { update, finalize }", start)
    return _SRC[start:end]


# ---------------------------------------------------------------------------
# Counter declaration
# ---------------------------------------------------------------------------

def test_rendertail_counter_declared():
    assert "let _rtCalls = 0" in _SRC


# ---------------------------------------------------------------------------
# Counter incremented at top of renderTail()
# ---------------------------------------------------------------------------

def test_rendertail_counter_incremented():
    body = _render_tail_body()
    assert "_rtCalls++" in body


def test_rendertail_counter_incremented_before_early_returns():
    # The increment must appear before the appendOpenFence early-return so every
    # call (including fence-streaming calls) is counted.
    body = _render_tail_body()
    incr_pos  = body.index("_rtCalls++")
    fence_pos = body.index("appendOpenFence")
    assert incr_pos < fence_pos, "_rtCalls++ must precede appendOpenFence early-return"


# ---------------------------------------------------------------------------
# Counter logged and reset in finalize()
# ---------------------------------------------------------------------------

def test_rendertail_counter_logged_in_finalize():
    body = _finalize_body()
    assert "[streamRenderer]" in body
    assert "_rtCalls" in body


def test_rendertail_counter_log_guarded_by_nonzero():
    # Avoid a spurious '[streamRenderer] renderTail calls=0' for responses that
    # never stream (e.g. instant errors).
    body = _finalize_body()
    assert "_rtCalls > 0" in body


def test_rendertail_counter_reset_after_log():
    body = _finalize_body()
    log_pos   = body.index("[streamRenderer]")
    reset_pos = body.index("_rtCalls = 0", log_pos)
    assert reset_pos > log_pos, "_rtCalls must be reset after the log, not before"

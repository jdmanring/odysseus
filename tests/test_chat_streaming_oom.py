"""Static validation of streaming OOM fixes in chat.js.

chat.js is browser-coupled and cannot be imported in pytest. These checks
analyse the source text to lock in the structural contracts that matter for
fix/dom-oom-streaming-throttle:

  Fix A  — thinking-block textContent during streaming (not innerHTML=mdToHtml)
  Fix A2 — rAF throttle for normal _renderStream() calls
  Fix C1 — StreamRenderer closure nulled out after final re-render
  Fix C3 — idle scheduler (scheduler.postTask / requestIdleCallback) in finally
  Fix C4 — background stream accumulated/sourcesHtml/findingsData cleared on [DONE]

Root: docs/fork/memory-explosion-research.md
"""

from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC  = (_REPO / "static/js/chat.js").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers for extracting code sections
# ---------------------------------------------------------------------------

def _think_stream_body() -> str:
    """Source of the else-if (hasUnclosedThink && isThinking) handler."""
    marker = "} else if (hasUnclosedThink && isThinking) {"
    start  = _SRC.index(marker)
    # End at the next else-if / else at the same indent level
    end    = _SRC.index("} else if (!hasUnclosedThink && isThinking) {", start)
    return _SRC[start:end]


def _think_close_body() -> str:
    """Source of the else-if (!hasUnclosedThink && isThinking) handler."""
    marker = "} else if (!hasUnclosedThink && isThinking) {"
    start  = _SRC.index(marker)
    end    = _SRC.index("} else {", start)
    return _SRC[start:end]


def _normal_stream_body() -> str:
    """Source of the else { // Normal streaming } block."""
    marker = "} else {\n                  // Normal streaming"
    start  = _SRC.index(marker)
    end    = _SRC.index("} else if (json.type === 'research_progress')", start)
    return _SRC[start:end]


def _finally_body() -> str:
    """Source of the finally { ... } block."""
    start = _SRC.index("    } finally {\n      clearResponseTimeout();")
    end   = _SRC.index("\n  }\n\n  /**\n   * Abort current chat request", start)
    return _SRC[start:end]


def _bg_done_body() -> str:
    """Source of the [DONE] handling block for background streams."""
    start = _SRC.index("if (data === '[DONE]') {")
    end   = _SRC.index("// Force-close thinking if still open", start)
    return _SRC[start:end]


# ---------------------------------------------------------------------------
# Fix A — thinking block textContent during streaming
# ---------------------------------------------------------------------------

def test_think_stream_uses_textcontent_not_innerhtml():
    # Per-token render used to call innerHTML = mdToHtml(thinkText), producing
    # ~50 MB old-gen garbage per thinking response.  The fix uses textContent.
    body = _think_stream_body()
    assert "textContent = thinkText" in body or ".textContent = thinkText" in body


def test_think_stream_does_not_call_mdtohtml_per_token():
    # mdToHtml must NOT be called inside the streaming (unclosed) thinking handler.
    body = _think_stream_body()
    assert "mdToHtml(thinkText)" not in body


def test_think_stream_sets_whitespace_pre_wrap():
    # textContent flattens whitespace; pre-wrap preserves it during streaming.
    body = _think_stream_body()
    assert "pre-wrap" in body


def test_think_close_does_rich_render():
    # When the thinking block closes, a single full mdToHtml render replaces
    # the plain-text content.
    body = _think_close_body()
    assert "mdToHtml(" in body
    assert "innerHTML" in body


def test_think_close_clears_whitespace_style():
    # The pre-wrap style set during streaming must be cleared before the rich render.
    body = _think_close_body()
    assert "whiteSpace" in body


# ---------------------------------------------------------------------------
# Fix A2 — rAF throttle for normal streaming
# ---------------------------------------------------------------------------

def test_render_raf_id_variable_declared():
    # _renderRafId must be declared before the while(true) loop so it is
    # accessible in the finally block to cancel any pending frame.
    while_start = _SRC.index("      while (true) {")
    before      = _SRC[:while_start]
    assert "_renderRafId" in before


def test_normal_streaming_uses_raf_throttle():
    # _renderStream() is now guarded by a requestAnimationFrame — at most one
    # render fires per frame instead of one per SSE delta.
    body = _normal_stream_body()
    assert "requestAnimationFrame" in body
    assert "_renderRafId" in body


def test_raf_cancelled_in_finally():
    # If a pending rAF is in-flight when the stream ends, cancel it so the
    # final synchronous re-render (after the loop) is not double-fired.
    body = _finally_body()
    assert "cancelAnimationFrame" in body
    assert "_renderRafId" in body


# ---------------------------------------------------------------------------
# Fix C1 — StreamRenderer closure nulled after final re-render
# ---------------------------------------------------------------------------

def test_stream_renderer_nulled_after_final_render():
    # The _streamRenderer closure holds lastText (full response string) and a
    # detached tailMarker comment node.  Null it after the final innerHTML
    # re-render so V8 can collect the closure.
    assert "_streamRenderer = null" in _SRC


# ---------------------------------------------------------------------------
# Fix C3 — idle scheduler in finally block
# ---------------------------------------------------------------------------

def test_finally_has_idle_callback_fallback():
    # This branch's finally yields to idle (scheduler.postTask / requestIdleCallback)
    # so the completion work doesn't block the frame. The gc()/_gcPending *dispatch*
    # is a separate concern owned by perf/agent-gc-catchup (and covered by
    # test_chat_gc_hint_js.py) — not asserted here.
    body = _finally_body()
    assert "requestIdleCallback" in body


# ---------------------------------------------------------------------------
# Fix C4 — background stream field cleanup on [DONE]
# ---------------------------------------------------------------------------

def test_bg_done_clears_accumulated():
    body = _bg_done_body()
    assert "bgDone.accumulated = ''" in body or "bgDone.accumulated=''" in body


def test_bg_done_clears_sources_html():
    body = _bg_done_body()
    assert "bgDone.sourcesHtml" in body


def test_bg_done_clears_findings_data():
    body = _bg_done_body()
    assert "bgDone.findingsData = null" in body

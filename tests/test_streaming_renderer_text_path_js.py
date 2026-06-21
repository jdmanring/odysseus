# Static-analysis tests for the text-only append fast path in streamingRenderer.js.
# This path avoids creating a holder div when the tail is growing by plain prose
# (no markdown structural characters in the new suffix).
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC  = (_REPO / "static/js/streamingRenderer.js").read_text(encoding="utf-8")


def _render_tail_body() -> str:
    marker = "function renderTail(tailText) {"
    start  = _SRC.index(marker)
    # End at the closing brace of renderTail — next top-level function
    end    = _SRC.index("\n  function appendOpenFence(", start)
    return _SRC[start:end]


def _text_path_block() -> str:
    body   = _render_tail_body()
    marker = "// Text-only append fast path:"
    start  = body.index(marker)
    end    = body.index("clearTail();", start)
    return body[start:end]


# ---------------------------------------------------------------------------
# State variable declaration
# ---------------------------------------------------------------------------

def test_last_tail_text_var_declared():
    assert "let _lastTailText = null;" in _SRC


# ---------------------------------------------------------------------------
# Reset points: start() and fence branch
# ---------------------------------------------------------------------------

def test_last_tail_text_reset_in_start():
    marker = "function start() {"
    start  = _SRC.index(marker)
    end    = _SRC.index("\n  }", start) + 4
    start_body = _SRC[start:end]
    assert "_lastTailText = null" in start_body


def test_last_tail_text_reset_in_fence_branch():
    body = _render_tail_body()
    fence_marker = "if (fence) {"
    fence_start  = body.index(fence_marker)
    fence_end    = body.index("appendOpenFence(", fence_start)
    fence_block  = body[fence_start:fence_end]
    assert "_lastTailText = null" in fence_block


# ---------------------------------------------------------------------------
# Text-only fast path conditions
# ---------------------------------------------------------------------------

def test_text_path_checks_starts_with():
    block = _text_path_block()
    assert ".startsWith(_lastTailText)" in block


def test_text_path_checks_last_tail_text_not_null():
    block = _text_path_block()
    assert "_lastTailText !== null" in block


def test_text_path_structural_char_guard():
    # Must reject tokens that contain markdown structural characters.
    block = _text_path_block()
    assert "!/[*_`#\\[\\]<>\\n\\\\{]/.test(suffix)" in block or \
           "!/[*_`" in block, "structural char regex must be present"


def test_text_path_checks_last_child_is_text_node():
    block = _text_path_block()
    assert "Node.TEXT_NODE" in block


def test_text_path_appends_to_data():
    block = _text_path_block()
    assert ".appendData(suffix)" in block


def test_text_path_updates_last_tail_text():
    block = _text_path_block()
    assert "_lastTailText = tailText" in block


def test_text_path_returns_early():
    block = _text_path_block()
    assert "return;" in block


# ---------------------------------------------------------------------------
# Full-render path: _lastTailText updated and reset
# ---------------------------------------------------------------------------

def test_full_path_sets_last_tail_text():
    body = _render_tail_body()
    # _lastTailText = tailText must appear after the holder append loop
    append_pos   = body.index("while (holder.firstChild)")
    set_pos      = body.index("_lastTailText = tailText", append_pos)
    assert set_pos > append_pos, "_lastTailText = tailText must follow the append loop"


def test_empty_tail_clears_last_tail_text():
    body = _render_tail_body()
    # When tailText is empty we clear the tail and null _lastTailText
    if_empty = body[body.index("if (!tailText)"):]
    brace_end = if_empty.index("\n    }") + 6
    empty_block = if_empty[:brace_end]
    assert "_lastTailText = null" in empty_block

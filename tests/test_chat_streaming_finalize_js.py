"""Static validation of the streaming final-render fast path in chat.js.

chat.js is browser-coupled and cannot be imported in pytest. These checks
analyse the source text to lock in the structural contracts for the [DONE]
handler optimisation:

  For plain responses (no thinking block, no sources, no findings), the
  streaming renderer already holds the correct final content. The fast path
  calls finalize() to freeze the remaining tail in-place and unwraps the
  stream-content div, eliminating the detached DOM subtree that a full
  innerHTML re-render would create.

  The existing full re-render path (thinking responses, sources, findings)
  must be preserved unchanged.

Root: docs/fork/memory-explosion-research.md
"""

from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC  = (_REPO / "static/js/chat.js").read_text(encoding="utf-8")


def _done_finalize_block() -> str:
    """The else-if / else section of the [DONE] body4 finalisation."""
    marker = "} else if (!_liveReplyEl && !_sourcesData && !_findingsData && !_sourcesHtml) {"
    start  = _SRC.index(marker)
    # End just after the closing brace of the subsequent full-rerender else block.
    end    = _SRC.index("} else if (_sourcesHtml) {", start)
    return _SRC[start:end]


def _fast_path_body() -> str:
    """The inner body of the fast-path else-if (including the degraded fallback else)."""
    block  = _done_finalize_block()
    start  = block.index("{", block.index("!_sourcesHtml) {")) + 1
    # The outer full-rerender else is identified by its distinctive comment.
    end    = block.index("} else {\n            // Full re-render")
    return block[start:end]


def _full_rerender_body() -> str:
    """The inner body of the existing full-rerender else block."""
    block  = _done_finalize_block()
    marker = "} else {\n            // Full re-render"
    start  = block.index(marker) + len(marker)
    return block[start:]


# ---------------------------------------------------------------------------
# Fast-path condition
# ---------------------------------------------------------------------------

def test_fast_path_guards_all_four_variables():
    block = _done_finalize_block()
    assert "!_liveReplyEl" in block
    assert "!_sourcesData" in block
    assert "!_findingsData" in block
    assert "!_sourcesHtml" in block


# ---------------------------------------------------------------------------
# Fast-path body: finalize, null, unwrap, remove
# ---------------------------------------------------------------------------

def test_fast_path_calls_stream_renderer_finalize():
    body = _fast_path_body()
    assert "_streamRenderer.finalize()" in body


def test_fast_path_nulls_stream_renderer_after_finalize():
    body = _fast_path_body()
    finalize_pos = body.index("_streamRenderer.finalize()")
    null_pos     = body.index("_streamRenderer = null", finalize_pos)
    assert null_pos > finalize_pos, "_streamRenderer must be nulled after finalize()"


def test_fast_path_moves_children_before_remove():
    body = _fast_path_body()
    move_pos   = body.index("insertBefore")
    remove_pos = body.index(".remove()", move_pos)
    assert remove_pos > move_pos, "children must be moved before stream-content is removed"


def test_fast_path_has_degraded_fallback():
    # When _streamRenderer is absent (degraded mode), fall back to full innerHTML.
    body = _fast_path_body()
    assert "processWithThinking" in body


# ---------------------------------------------------------------------------
# Full re-render path preserved
# ---------------------------------------------------------------------------

def test_full_rerender_path_still_exists():
    body = _full_rerender_body()
    assert "processWithThinking" in body
    assert "_body4.innerHTML" in body


def test_full_rerender_includes_sources_and_findings():
    body = _full_rerender_body()
    assert "_sourcesData" in body
    assert "_findingsData" in body

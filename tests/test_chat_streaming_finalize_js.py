# Source-text contract tests for the [DONE] handler fast path in chat.js.
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC  = (_REPO / "static/js/chat.js").read_text(encoding="utf-8")


def _done_finalize_block() -> str:
    marker = "} else if (!_liveReplyEl && !_sourcesData && !_findingsData && !_sourcesHtml) {"
    start  = _SRC.index(marker)
    end    = _SRC.index("} else if (_sourcesHtml) {", start)
    return _SRC[start:end]


def _fast_path_body() -> str:
    block  = _done_finalize_block()
    start  = block.index("{", block.index("!_sourcesHtml) {")) + 1
    end    = block.index("} else {\n            // If Reset 1 already finalized")
    return block[start:end]


def _full_rerender_body() -> str:
    block  = _done_finalize_block()
    marker = "} else {\n              // Full re-render (reply empty or no live-reply container, no in-place content)"
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

"""Static validation of in-place tail patching in streamingRenderer.js.

streamingRenderer.js is browser-coupled (uses DOM) and cannot be imported
in pytest. These checks analyse the source text to lock in the structural
contracts for the Oilpan OOM fix: instead of clearTail() + full DOM rebuild
on every SSE token, renderTail() patches existing nodes in-place when the
block structure is unchanged.

Root: docs/fork/memory-explosion-research.md
"""

from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC  = (_REPO / "static/js/streamingRenderer.js").read_text(encoding="utf-8")


def _render_tail_body() -> str:
    start = _SRC.index("function renderTail(")
    end   = _SRC.index("\n  }", start) + 4
    return _SRC[start:end]


def _start_body() -> str:
    start = _SRC.index("function start()")
    end   = _SRC.index("\n  }", start) + 4
    return _SRC[start:end]


def _clear_tail_body() -> str:
    start = _SRC.index("function clearTail()")
    end   = _SRC.index("\n  }", start) + 4
    return _SRC[start:end]


# ---------------------------------------------------------------------------
# _tailNodes lifecycle
# ---------------------------------------------------------------------------

def test_tail_nodes_declared():
    assert "_tailNodes = []" in _SRC


def test_start_resets_tail_nodes():
    assert "_tailNodes = []" in _start_body()


def test_clear_tail_resets_tail_nodes():
    assert "_tailNodes = []" in _clear_tail_body()


# ---------------------------------------------------------------------------
# In-place patch fast path
# ---------------------------------------------------------------------------

def test_render_tail_checks_nodename():
    # Structure match uses nodeName comparison to decide between patch and rebuild.
    body = _render_tail_body()
    assert "nodeName" in body


def test_render_tail_patches_text_node_data():
    # Text nodes are patched via .data, not innerHTML (zero DOM churn).
    body = _render_tail_body()
    assert ".data = " in body


def test_render_tail_patches_element_inner_html():
    # Element nodes are patched via .innerHTML (avoids outer node create/destroy).
    body = _render_tail_body()
    assert ".innerHTML = " in body


def test_render_tail_still_has_full_rebuild_fallback():
    # When block structure changes, the old clear+rebuild path must still run.
    body = _render_tail_body()
    assert "clearTail()" in body
    assert "fadeNewText(" in body


def test_render_tail_pushes_to_tail_nodes_on_rebuild():
    # After a full rebuild, _tailNodes must be populated for next-cycle patching.
    body = _render_tail_body()
    assert "_tailNodes.push(" in body

# Source-text contract tests for streamingRenderer.js (_tailNodes lifecycle, hljs defer, _rtCalls counter).
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


def _freeze_body() -> str:
    start = _SRC.index("function freeze(")
    end   = _SRC.index("\n  }", start) + 4
    return _SRC[start:end]


def _finalize_body() -> str:
    start = _SRC.index("function finalize()")
    end   = _SRC.index("\n  return { update, finalize }", start)
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


# ---------------------------------------------------------------------------
# Deferred hljs highlighting in freeze()
# ---------------------------------------------------------------------------

def test_freeze_imports_defer_highlight():
    # hljsDefer.js must be imported so deferHighlight is in scope.
    assert "hljsDefer.js" in _SRC


def test_freeze_collects_code_blocks_before_insert():
    # Code block refs must be captured while still in holder (before DOM move),
    # so IntersectionObserver gets live nodes after insertion.
    body = _freeze_body()
    assert "querySelectorAll('pre code')" in body or 'querySelectorAll("pre code")' in body


def test_freeze_inserts_before_observing():
    # Insertion (insertBefore) must come before the deferHighlight loop so the
    # observer can measure viewport position on live DOM nodes.
    body = _freeze_body()
    insert_pos  = body.index("insertBefore")
    observe_pos = body.index("deferHighlight")
    assert insert_pos < observe_pos, "insertBefore must precede deferHighlight in freeze()"


def test_freeze_no_immediate_highlight():
    # The old highlight(holder) call must not appear in freeze() — we no longer
    # run hljs synchronously on a detached fragment.
    body = _freeze_body()
    assert "highlight(holder)" not in body
    assert "highlightElement" not in body


def test_full_render_keeps_immediate_highlight():
    # fullRender() is the degraded fallback — it must still highlight immediately
    # since we can't rely on observer firing in an already-broken renderer state.
    start = _SRC.index("function fullRender(")
    end   = _SRC.index("\n  }", start) + 4
    body  = _SRC[start:end]
    assert "highlightElement" in body


# ---------------------------------------------------------------------------
# renderTail call counter (_rtCalls)
# ---------------------------------------------------------------------------

def test_rendertail_counter_declared():
    assert "let _rtCalls = 0" in _SRC


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


def test_rendertail_counter_logged_in_finalize():
    body = _finalize_body()
    assert "'[streamRenderer] renderTail calls=' + _rtCalls" in body


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

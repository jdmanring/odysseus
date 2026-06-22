from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC  = (_REPO / "static/js/chat.js").read_text(encoding="utf-8")


def _rewrite_fn_body() -> str:
    marker = "export async function rewriteWith("
    start  = _SRC.index(marker)
    # End at next top-level export
    end    = _SRC.index("\n  export async function continueFrom(", start)
    return _SRC[start:end]


def _delta_block() -> str:
    body = _rewrite_fn_body()
    marker = "if (data.delta) {"
    start  = body.index(marker)
    end    = body.index("} catch (e) {", start)
    return body[start:end]


def test_rw_renderer_var_declared():
    body = _rewrite_fn_body()
    assert "let _rwRenderer = null;" in body


def test_rw_delta_block_creates_stream_content():
    block = _delta_block()
    assert "className = 'stream-content'" in block


def test_rw_delta_block_uses_ensure_layout_or_querySelector():
    block = _delta_block()
    assert "querySelector('.stream-content')" in block


def test_rw_delta_block_uses_create_stream_renderer():
    block = _delta_block()
    assert "createStreamRenderer(" in block


def test_rw_delta_block_passes_render_fn():
    block = _delta_block()
    assert "processWithThinking(" in block


def test_rw_delta_block_calls_update():
    block = _delta_block()
    assert "_rwRenderer.update(newText)" in block


def test_rw_delta_block_no_body_innerhtml():
    block = _delta_block()
    assert "bodyEl.innerHTML" not in block


def test_rw_finalize_called_before_final_render():
    body = _rewrite_fn_body()
    finalize_pos = body.index("_rwRenderer.finalize()")
    final_render_pos = body.index("bodyEl.innerHTML = markdownModule.processWithThinking(")
    assert finalize_pos < final_render_pos


def test_rw_renderer_nulled_after_finalize():
    body = _rewrite_fn_body()
    finalize_pos  = body.index("_rwRenderer.finalize()")
    null_pos = body.index("_rwRenderer = null;", finalize_pos)
    final_render_pos = body.index("bodyEl.innerHTML = markdownModule.processWithThinking(")
    assert finalize_pos < null_pos < final_render_pos


def test_rw_final_single_innerhtml_exists():
    body = _rewrite_fn_body()
    assert "bodyEl.innerHTML = markdownModule.processWithThinking(" in body

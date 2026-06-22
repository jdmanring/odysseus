from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC  = (_REPO / "static/js/chat.js").read_text(encoding="utf-8")


def _reset1_block() -> str:
    marker = "if (dt.trim()) {\n                    var _body3 = roundHolder.querySelector('.body')"
    start  = _SRC.index(marker)
    end    = _SRC.index("} else {\n                    roundHolder.style.display = 'none'", start)
    return _SRC[start:end]


def _reset2_block() -> str:
    marker = "// If Reset 1 already finalized the renderer in-place"
    start  = _SRC.index(marker)
    end    = _SRC.index("} else if (_sourcesHtml) {", start)
    return _SRC[start:end]


def test_reset1_checks_stream_renderer():
    block = _reset1_block()
    assert "_contentEl3._streamRenderer" in block


def test_reset1_renderer_branch_calls_finalize():
    block = _reset1_block()
    assert "_contentEl3._streamRenderer.finalize()" in block


def test_reset1_renderer_branch_nulls_renderer():
    block = _reset1_block()
    assert "_contentEl3._streamRenderer = null;" in block


def test_reset1_fallback_uses_innerHTML():
    block = _reset1_block()
    assert "_contentEl3.innerHTML = markdownModule.processWithThinking(" in block


def test_reset1_fallback_is_in_else_branch():
    block = _reset1_block()
    finalize_pos = block.index("_contentEl3._streamRenderer.finalize()")
    null_pos     = block.index("_contentEl3._streamRenderer = null;")
    else_pos     = block.index("} else {", null_pos)
    html_pos     = block.index("_contentEl3.innerHTML")
    assert finalize_pos < null_pos < else_pos < html_pos


def test_reset1_hljs_called_after_both_paths():
    block = _reset1_block()
    # hljs highlight call appears after both renderer and innerHTML branches close
    hljs_pos = block.index("window.hljs) roundHolder.querySelectorAll")
    null_pos  = block.index("_contentEl3._streamRenderer = null;")
    html_pos  = block.index("_contentEl3.innerHTML")
    assert hljs_pos > null_pos
    assert hljs_pos > html_pos


def test_reset2_checks_stream_content():
    block = _reset2_block()
    assert "querySelector('.stream-content')" in block


def test_reset2_has_in_place_content_guard():
    block = _reset2_block()
    assert "_hasInPlaceContent" in block


def test_reset2_sources_injected_as_sibling():
    block = _reset2_block()
    # Sources should be inserted with insertBefore, not body innerHTML
    assert "_body4.insertBefore(" in block


def test_reset2_findings_injected_as_sibling():
    block = _reset2_block()
    assert "insertAdjacentHTML('beforeend'" in block


def test_reset2_fullrender_fallback_exists():
    block = _reset2_block()
    assert "_body4.innerHTML = (" in block


def test_reset1_logs_inplace():
    block = _reset1_block()
    assert "console.log('[chat] round-finalize: tool_start in-place')" in block


def test_reset2_logs_inplace():
    block = _reset2_block()
    assert "console.log('[chat] round-finalize: sources in-place')" in block

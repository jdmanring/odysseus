# Source-text contract tests for tool bubble in-place completion in chat.js.
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC  = (_REPO / "static/js/chat.js").read_text(encoding="utf-8")


def _tool_start_body() -> str:
    marker = 'node.innerHTML = `<div class="agent-thread-dot">'
    start  = _SRC.index(marker)
    end    = _SRC.index("threadWrap.appendChild(node)", start)
    return _SRC[start:end]


def _tool_complete_body() -> str:
    marker = "const _wasOpen = currentToolBubble.classList.contains('open')"
    start  = _SRC.index(marker)
    end    = _SRC.index("_lastToolName = ''", start)
    return _SRC[start:end]


# ---------------------------------------------------------------------------
# Refs cached at tool_start (after innerHTML, before appendChild)
# ---------------------------------------------------------------------------

def test_tool_start_caches_header_ref():
    body = _tool_start_body()
    assert "node._toolHeaderEl" in body
    assert "querySelector('.agent-thread-header')" in body


def test_tool_start_caches_icon_ref():
    body = _tool_start_body()
    assert "node._toolIconEl" in body
    assert "querySelector('.agent-thread-icon')" in body


def test_tool_start_caches_wave_ref():
    body = _tool_start_body()
    assert "node._toolWaveEl" in body
    assert "querySelector('.agent-thread-wave')" in body


def test_tool_start_caches_content_ref():
    body = _tool_start_body()
    assert "node._toolContentEl" in body
    assert "querySelector('.agent-thread-content')" in body


def test_tool_start_refs_cached_after_inner_html():
    body = _tool_start_body()
    html_pos   = body.index("node.innerHTML =")
    header_pos = body.index("node._toolHeaderEl")
    assert header_pos > html_pos, "Refs must be cached after innerHTML is set"


# ---------------------------------------------------------------------------
# In-place patch at tool_output
# ---------------------------------------------------------------------------

def test_tool_complete_patches_icon_text():
    body = _tool_complete_body()
    assert "_toolIconEl.textContent" in body


def test_tool_complete_removes_wave():
    body = _tool_complete_body()
    assert "_toolWaveEl.remove()" in body


def test_tool_complete_nulls_wave_after_removal():
    body = _tool_complete_body()
    remove_pos = body.index("_toolWaveEl.remove()")
    null_pos   = body.index("_toolWaveEl = null", remove_pos)
    assert null_pos > remove_pos, "_toolWaveEl must be nulled after remove()"


def test_tool_complete_removes_elapsed_span():
    body = _tool_complete_body()
    qs_pos = body.index("agent-thread-elapsed")
    rm_pos = body.index(".remove()", qs_pos)
    assert rm_pos > qs_pos


def test_tool_complete_updates_content_inner_html():
    body = _tool_complete_body()
    assert "_toolContentEl.innerHTML" in body


def test_tool_complete_no_full_bubble_inner_html_replace():
    # The old pattern replaced the entire bubble via currentToolBubble.innerHTML = `...`
    # With in-place patching this must not appear in the completion handler.
    body = _tool_complete_body()
    assert "currentToolBubble.innerHTML" not in body

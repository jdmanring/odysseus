# Static-analysis tests for the live-reply in-place finalize path in chat.js.
# Covers the if (_liveReplyEl && _finalReply) block that was previously doing
# _liveReplyEl.innerHTML = mdToHtml() even when _streamRenderer already held
# the correct content from incremental streaming.
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC  = (_REPO / "static/js/chat.js").read_text(encoding="utf-8")


def _live_reply_block() -> str:
    marker = "if (_liveReplyEl && _finalReply) {"
    start  = _SRC.index(marker)
    # Block ends at the matching "} else {" that covers the sourcesHtml path
    end    = _SRC.index("} else if (_sourcesHtml) {", start)
    return _SRC[start:end]


def _renderer_branch() -> str:
    block  = _live_reply_block()
    start  = block.index("if (_liveReplyEl._streamRenderer) {")
    end    = block.index("} else {", start)
    return block[start:end]


def _fallback_branch() -> str:
    block  = _live_reply_block()
    marker = "} else {\n              // No streaming renderer"
    start  = block.index(marker)
    end    = block.index("}", start + len(marker)) + 1
    return block[start:end]


# ---------------------------------------------------------------------------
# Renderer branch: update → finalize → null
# ---------------------------------------------------------------------------

def test_live_reply_renderer_branch_calls_update():
    body = _renderer_branch()
    assert "_streamRenderer.update(_finalReply)" in body


def test_live_reply_renderer_branch_calls_finalize():
    body = _renderer_branch()
    assert "_streamRenderer.finalize()" in body


def test_live_reply_renderer_update_before_finalize():
    body = _renderer_branch()
    update_pos   = body.index("_streamRenderer.update(")
    finalize_pos = body.index("_streamRenderer.finalize()", update_pos)
    assert finalize_pos > update_pos, "update() must precede finalize()"


def test_live_reply_renderer_nulled_after_finalize():
    body = _renderer_branch()
    finalize_pos = body.index("_streamRenderer.finalize()")
    null_pos     = body.index("_streamRenderer = null", finalize_pos)
    assert null_pos > finalize_pos, "_streamRenderer must be nulled after finalize()"


# ---------------------------------------------------------------------------
# Fallback branch: innerHTML path preserved when no renderer
# ---------------------------------------------------------------------------

def test_live_reply_fallback_uses_md_to_html():
    body = _fallback_branch()
    assert "mdToHtml" in body


def test_live_reply_fallback_uses_inner_html():
    body = _fallback_branch()
    assert "_liveReplyEl.innerHTML" in body


# ---------------------------------------------------------------------------
# Shared: class removal after both branches
# ---------------------------------------------------------------------------

def test_live_reply_renderer_logs_finalize():
    # console.log in the renderer branch provides observability in wrapper_system.log
    # to confirm the in-place path fires during real sessions.
    body = _renderer_branch()
    assert "console.log('[chat] live-reply: finalized in-place')" in body


def test_live_reply_class_removed_unconditionally():
    block = _live_reply_block()
    # classList.remove must appear after the if/else branches close
    class_pos    = block.index("classList.remove('live-reply-content')")
    renderer_pos = block.index("_streamRenderer = null")
    fallback_pos = block.index("_liveReplyEl.innerHTML")
    assert class_pos > renderer_pos
    assert class_pos > fallback_pos

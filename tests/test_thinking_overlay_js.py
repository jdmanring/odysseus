"""The Thinking indicator must be a zero-footprint sticky overlay.

An in-flow indicator moves the document's bottom edge on every show, replace,
and remove -- layout jumps the stick-to-bottom machinery then has to repair.
The overlay contract: height:0 sticky anchor as the log's LAST child (bottom
edge never moves), bubble absolutely positioned above it, role=status for AT,
still inside #chat-history so cleanup queries and the log's aria-busy
ownership check keep seeing the `agent-thinking-dots` class, and no
transform/will-change (it must not cost a compositor layer).
"""
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_CHAT = (_REPO / "static/js/chat.js").read_text(encoding="utf-8")
_CSS = (_REPO / "static/style.css").read_text(encoding="utf-8")


def _show_body() -> str:
    start = _CHAT.index("function _showThinkingSpinner")
    return _CHAT[start:_CHAT.index("\n      }", start)]


def test_overlay_classes_and_role():
    body = _show_body()
    assert "'agent-thinking-dots agent-thinking-overlay'" in body
    assert "setAttribute('role', 'status')" in body


def test_overlay_is_not_an_inflow_message():
    body = _show_body()
    assert "msg msg-ai" not in body, (
        "the indicator must not be an in-flow .msg (message chrome + "
        "content-visibility placeholder + bottom-edge movement)")


def test_overlay_does_not_scroll_history():
    body = _show_body()
    assert "uiModule.scrollHistory()" not in body, (
        "zero-footprint overlay moves nothing; a scroll call would reintroduce "
        "position churn on show/replace")


def test_overlay_kept_inside_chat_history():
    body = _show_body()
    assert "getElementById('chat-history').appendChild" in body, (
        "the overlay must stay inside the log so aria-busy ownership and "
        "cleanup queries keep working")


def _overlay_css() -> str:
    start = _CSS.index(".agent-thinking-overlay {")
    end = _CSS.index("}", _CSS.index(".agent-thinking-overlay .body"))
    return _CSS[start:end]


def test_overlay_css_zero_footprint_sticky():
    css = _overlay_css()
    assert "position: sticky" in css
    assert re.search(r"height:\s*0", css)
    assert "overflow: visible" in css


def test_overlay_css_no_compositor_layer():
    css = _overlay_css()
    assert "will-change" not in css
    assert "transform" not in css, (
        "no transform in the overlay: it must not be compositor-promoted "
        "(GPU memory discipline)")


def test_bubble_absolutely_positioned():
    start = _CSS.index(".agent-thinking-overlay .body")
    block = _CSS[start:_CSS.index("}", start)]
    assert "position: absolute" in block

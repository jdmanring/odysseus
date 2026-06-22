# Source-text contract tests for the rAF-coalesced autoResize in ui.js.
from pathlib import Path

_SRC = (Path(__file__).resolve().parent.parent / "static/js/ui.js").read_text(
    encoding="utf-8"
)


def _auto_resize_block() -> str:
    start = _SRC.index("export function autoResize(")
    end = _SRC.index("\nexport function debounce(", start)
    return _SRC[start:end]


def test_auto_resize_uses_raf_coalescing():
    # requestAnimationFrame coalesces rapid keystrokes so at most one layout
    # reflow fires per animation frame regardless of typing speed.
    assert "requestAnimationFrame" in _auto_resize_block()


def test_auto_resize_height_auto_for_measurement():
    # Setting height to 'auto' releases the fixed height so textarea.scrollHeight
    # reports the natural content height without a hidden clone.
    assert "'auto'" in _auto_resize_block()


def test_auto_resize_reads_scroll_height():
    assert "scrollHeight" in _auto_resize_block()


def test_auto_resize_no_clone_creation():
    # The clone-based approach (cloneNode + offsetWidth + clone.scrollHeight)
    # caused 2 forced layout reflows per keystroke; it has been removed.
    assert "cloneNode" not in _auto_resize_block()


def test_auto_resize_sets_overflow():
    assert "overflow" in _auto_resize_block()

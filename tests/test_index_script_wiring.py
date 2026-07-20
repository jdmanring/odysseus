"""Guard: every consumer-referenced bootstrap script is actually loaded.

The qt-bridge.js tag was silently deleted from index.html by an unrelated
June 2026 commit (9b469344) — the file, the wrapper's QWebChannel side, and
the colorPicker consumer all survived, so window.qtBridge was simply never
defined and the native color picker died without an error. Same partial-
amputation family as the lost aria2c launcher and resolve-gguf route.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INDEX = (REPO / "static" / "index.html").read_text(encoding="utf-8")


def test_qt_bridge_script_is_loaded():
    assert '<script src="/static/js/qt-bridge.js"></script>' in INDEX
    assert (REPO / "static" / "js" / "qt-bridge.js").exists()
    # the consumer that dies silently without it
    color_picker = (REPO / "static" / "js" / "colorPicker.js").read_text(encoding="utf-8")
    assert "window.qtBridge" in color_picker


def test_every_local_script_src_exists():
    """No script tag may point at a file that isn't shipped."""
    import re
    for src in re.findall(r'<script[^>]+src="/static/([^"?]+)', INDEX):
        assert (REPO / "static" / src).exists(), f"index.html loads missing file: {src}"

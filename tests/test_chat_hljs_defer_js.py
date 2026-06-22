"""Static-analysis tests: all hljs highlight calls use deferHighlightAll in chat.js."""
import re
from pathlib import Path

_SRC = (Path(__file__).resolve().parent.parent / "static/js/chat.js").read_text(encoding="utf-8")


def test_no_direct_highlight_element_calls():
    """All window.hljs.highlightElement calls replaced with deferHighlightAll."""
    assert "window.hljs.highlightElement" not in _SRC


def test_hljs_defer_import_present():
    assert "import { deferHighlightAll" in _SRC


def test_defer_highlight_all_call_count():
    """deferHighlightAll called at 8+ sites: 1 original + 7 new replacements."""
    assert len(re.findall(r'deferHighlightAll\(', _SRC)) >= 8

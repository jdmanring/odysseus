"""Guard: platform wrappers enable JS clipboard WRITES, never READS.

QtWebEngine ships with JavascriptCanAccessClipboard off, which makes
navigator.clipboard.writeText reject with NotAllowedError AND makes the
document.execCommand('copy') fallback return false — both silently, so every
copy button in the app no-ops with a success checkmark (live CDP probe,
2026-07-20). The wrapper must enable clipboard writes. JavascriptCanPaste
must stay off: it would let page JS READ the system clipboard.
"""
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_WRAPPERS = [p for p in ("qt_wrapper.py", "mac_wrapper.py", "windows_wrapper.py")
             if (_ROOT / p).is_file()]


@pytest.mark.parametrize("wrapper", _WRAPPERS)
def test_wrapper_enables_js_clipboard_writes(wrapper):
    src = (_ROOT / wrapper).read_text(encoding="utf-8")
    assert "JavascriptCanAccessClipboard, True" in src, (
        f"{wrapper}: JS clipboard writes disabled — every copy button no-ops"
    )


@pytest.mark.parametrize("wrapper", _WRAPPERS)
def test_wrapper_keeps_js_clipboard_reads_off(wrapper):
    src = (_ROOT / wrapper).read_text(encoding="utf-8")
    stripped = src.replace("enabling JavascriptCanPaste", "")
    assert "JavascriptCanPaste" not in stripped, (
        f"{wrapper}: JavascriptCanPaste must stay off (pages could read the clipboard)"
    )

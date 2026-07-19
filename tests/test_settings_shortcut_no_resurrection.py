"""The settings keybind must never reopen a remembered tool window.

_toggleActiveWindow used to track the last tool window it closed
(_lastWindow) and reopen it when the shortcut fired with nothing open.
Close Brain with the shortcut once, and every later press resurrected
Brain on its last tab — windows appearing to open themselves.
"""
import pathlib

SRC = (pathlib.Path(__file__).resolve().parent.parent
       / "static/js/keyboard-shortcuts.js").read_text(encoding="utf-8")


def test_no_last_window_memory():
    assert "_lastWindow" not in SRC, (
        "the settings keybind must not remember/reopen the last tool window"
    )


def test_nothing_open_path_opens_settings():
    body = SRC[SRC.index("const _toggleActiveWindow"):]
    body = body[:body.index("};")]
    # Exactly one else-branch, and it opens Settings.
    assert "settingsModule.open()" in body
    assert "t.click()" not in body.split("} else {")[1], (
        "the nothing-open branch must open Settings, never click a remembered trigger"
    )

"""Idle-quiescence guards (#117): ambient animations pause when backgrounded.

A backgrounded/unfocused window should not run decorative animations. ui.js
toggles `html.app-blurred` on window blur / page hide; CSS pauses the notes
quick-add pulse/caret under it. Static assertions only — no browser needed.
"""
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_UI = (_ROOT / "static" / "js" / "ui.js").read_text(encoding="utf-8")
_CSS = (_ROOT / "static" / "style.css").read_text(encoding="utf-8")


def test_ui_toggles_app_blurred_on_blur_and_hide():
    # The reusable primitive: drive the class off both signals.
    assert "classList.toggle('app-blurred'" in _UI
    assert "document.hidden" in _UI and "hasFocus()" in _UI
    assert "addEventListener('blur'" in _UI
    assert "addEventListener('visibilitychange'" in _UI


def test_css_pauses_notes_animations_when_blurred():
    assert "html.app-blurred .notes-quick-add" in _CSS
    # Must pause (not disable) so it resumes cleanly on refocus.
    idx = _CSS.index("html.app-blurred .notes-quick-add")
    block = _CSS[idx: idx + 220]
    assert "animation-play-state: paused" in block


def test_gate_covers_element_and_both_pseudo_elements():
    # Robust across the box-shadow (element) and #108 opacity (::after) variants.
    assert "html.app-blurred .notes-quick-add::after" in _CSS
    assert "html.app-blurred .notes-quick-add::before" in _CSS

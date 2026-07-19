"""Chat column width preference — static wiring guards.

The chat renders in a monospace font by default, so column width is exactly a
characters-per-line choice: the historical hard-coded 800px column gives 63
characters; 1000px gives 80. The preference chain is:

    localStorage 'odysseus-chat-width'
      -> --chat-max-user on <html> (early inline apply + theme.js applyChatWidth)
      -> .chat-history { --chat-max: var(--chat-max-user, 800px) }
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = (ROOT / "static/style.css").read_text(encoding="utf-8")
HTML = (ROOT / "static/index.html").read_text(encoding="utf-8")
THEME = (ROOT / "static/js/theme.js").read_text(encoding="utf-8")


def test_css_chat_max_reads_user_var_with_800_default():
    assert "--chat-max: var(--chat-max-user, 800px);" in CSS
    # The old hard-coded form must be gone, or the var chain is dead code.
    assert re.search(r"--chat-max:\s*800px\s*;", CSS) is None


def test_theme_apply_function_clamps():
    block = THEME[THEME.index("export function applyChatWidth"):]
    block = block[:block.index("\n}")]
    assert "Math.max(600, Math.min(1600," in block, "width must be clamped to sane bounds"
    assert "removeProperty('--chat-max-user')" in block, (
        "the default must remove the override, not pin 800px inline "
        "(keeps the CSS fallback the single source of the default)"
    )


def test_theme_wires_select_with_persistence():
    assert "theme-chat-width-select" in THEME
    assert "localStorage.setItem(CHAT_WIDTH_KEY" in THEME
    assert "applyChatWidth(ncw.value)" in THEME


def test_index_has_early_apply_before_dom_ready():
    # Same no-flash rationale as ui-scale: the inline boot script must apply
    # the stored width before first paint.
    assert "localStorage.getItem('odysseus-chat-width')" in HTML
    early = HTML.index("localStorage.getItem('odysseus-chat-width')")
    assert early < HTML.index("<body"), "early apply must be in the head boot script"


def test_index_select_offers_80_columns():
    assert 'id="theme-chat-width-select"' in HTML
    assert 'value="1000">80 columns' in HTML
    assert 'value="800">Default' in HTML


def test_early_apply_clamps_same_bounds_as_runtime():
    m = re.search(r"Math\.max\(600, Math\.min\(1600, _cw\)\)", HTML)
    assert m, "inline early-apply must clamp with the same 600..1600 bounds as applyChatWidth"

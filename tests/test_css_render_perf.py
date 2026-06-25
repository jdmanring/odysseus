"""CSS regression guards for fix/css-render-perf.

Locks in the five categories of CSS changes made by the render performance pass:

  1. will-change removed from three always-on elements (permanent GPU layer waste)
  2. CSS containment added to three high-churn containers
  3. Global prefers-reduced-motion catch-all added at end of file
  4. touch-action: manipulation added to interactive elements
  5. filter:brightness hover rules wrapped in @media (hover: hover) and (pointer: fine)

No browser required — all checks are static assertions on style.css, index.html,
and theme.js.
"""
from pathlib import Path
import re

_CSS = (Path(__file__).resolve().parents[1] / "static" / "style.css").read_text(encoding="utf-8")
_IDX = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text(encoding="utf-8")
_THEME_JS = (Path(__file__).resolve().parents[1] / "static" / "js" / "theme.js").read_text(encoding="utf-8")


def _block(anchor: str, window: int = 700) -> str:
    """Return window chars of CSS starting from anchor."""
    idx = _CSS.index(anchor)
    return _CSS[idx : idx + window]


# ---------------------------------------------------------------------------
# 1. will-change removed from always-visible elements
# ---------------------------------------------------------------------------

def test_model_picker_wrap_no_will_change():
    # .chat-input-top > .model-picker-wrap was permanently holding a GPU compositor
    # layer with will-change: opacity, transform even when not animating.
    block = _block(".chat-input-top > .model-picker-wrap {")
    rule_end = block.index("}")
    assert "will-change" not in block[:rule_end]


def test_doc_line_number_content_no_will_change():
    # .doc-line-number-content had will-change: transform on every line-number
    # row in the document editor — one permanent GPU layer allocation per row.
    block = _block(".doc-line-number-content {")
    rule_end = block.index("}")
    assert "will-change" not in block[:rule_end]


def test_email_lib_fab_no_will_change():
    # #email-lib-modal .email-lib-fab had will-change: padding, transform set
    # permanently rather than only during the 420ms expand transition.
    # Rule is ~40 lines long (inside a @media block); use a wide window.
    idx = _CSS.index("#email-lib-modal .email-lib-fab {")
    assert "will-change" not in _CSS[idx : idx + 2000]


# ---------------------------------------------------------------------------
# 2. CSS containment — layout style scoping without paint isolation
# ---------------------------------------------------------------------------

def test_sidebar_no_contain():
    # Sidebar is opaque with overflow:hidden — no scroll layer, no paint
    # isolation needed. Adding contain:layout creates a stacking context that
    # alters how its box-shadow renders in the compositor, producing a visually
    # expanded separator. No contain is correct here.
    block = _block(".sidebar {")
    rule_end = block.index("}")
    assert "contain" not in block[:rule_end]
    assert "contain: content" not in block[:rule_end]


def test_html_element_has_explicit_bg():
    # The html element carries an explicit background-color: var(--bg) so the
    # root layer is never transparent and never falls through to Qt's
    # system-palette base colour (lighter than --bg) during any paint gap.
    # Cheap, harmless theming hygiene — kept independent of any Chromium flag.
    # (The earlier "tile-eviction fill" rationale was disproven: the lighter
    # rectangle was --enable-low-end-device-mode's raster path, since removed.)
    idx = _CSS.index("html {")
    block = _CSS[idx : idx + 300]
    rule_end = block.index("}")
    assert "background-color: var(--bg)" in block[:rule_end]


def test_chat_history_has_contain_layout_style():
    # contain: layout style (NOT contain: paint/content) — paint containment
    # broke backdrop-filter on the frosted sidebar and made the transparent
    # chat-history render opaque in the Qt compositor. See jdmanring#93.
    block = _block(".chat-history {")
    rule_end = block.index("}")
    assert "contain: layout style" in block[:rule_end]
    assert "contain: content" not in block[:rule_end]


def test_chat_history_has_explicit_bg():
    # .chat-history carries an explicit background: var(--bg) so the scroll
    # area paints the theme background directly rather than relying on the
    # body showing through. Simple theming correctness; not tied to any
    # Chromium raster flag.
    block = _block(".chat-history {")
    rule_end = block.index("}")
    assert "background: var(--bg)" in block[:rule_end]


def test_welcome_active_uses_container_padding_not_input_bar_margin():
    # The 30vh welcome gap is expressed as padding-bottom on
    # .chat-container.welcome-active rather than margin-bottom on
    # .chat-input-bar, so the spacing stays inside the container's own box
    # rather than the container-type:inline-size compositor layer of the input
    # bar. (Originally framed as a tile-eviction fix; kept because container
    # padding is the cleaner place for the gap regardless.)
    welcome_block = _block(".chat-container.welcome-active {")
    rule_end = welcome_block.index("}")
    assert "padding-bottom: 30vh" in welcome_block[:rule_end]
    # margin-bottom:30vh must not appear on the input bar override — that was
    # the rule that created the problematic compositor layer extension.
    assert "margin-bottom:30vh" not in _CSS
    assert "margin-bottom: 30vh" not in _CSS


def test_modal_content_has_contain_layout_style():
    # Conservative variant (not paint) because provider picker menus can overflow
    # the modal boundary visually. Scopes layout without introducing clipping.
    block = _block(".modal-content {")
    rule_end = block.index("}")
    assert "contain: layout style" in block[:rule_end]


def test_init_script_sets_html_background_color_inline():
    # The init script sets document.documentElement.style.backgroundColor
    # directly (not only via the --bg custom property) so html paints the theme
    # background immediately, before the author stylesheet loads — avoiding a
    # first-paint flash of the CSS default (#282c34). Harmless base-colour sync.
    start = _IDX.index("s.setProperty('--bg', c.bg)")
    block = _IDX[start : start + 700]
    assert "s.backgroundColor = c.bg" in block


def test_apply_colors_sets_html_background_color_inline():
    # applyColors mirrors the init-script approach so live theme changes also
    # update html.style.backgroundColor, keeping the root background in sync
    # with the new theme. Harmless base-colour sync.
    start = _THEME_JS.index("s.setProperty('--bg', colors.bg)")
    block = _THEME_JS[start : start + 300]
    assert "s.backgroundColor = colors.bg" in block


# ---------------------------------------------------------------------------
# 3. Global prefers-reduced-motion catch-all
# ---------------------------------------------------------------------------

_REDUCED_MOTION_BLOCK = (
    "@media (prefers-reduced-motion: reduce) {\n"
    "  *, *::before, *::after {\n"
    "    animation-duration: 0.01ms !important;\n"
    "    animation-iteration-count: 1 !important;\n"
    "    transition-duration: 0.01ms !important;\n"
    "    scroll-behavior: auto !important;\n"
    "  }\n"
    "}"
)


def test_global_reduced_motion_catch_all_present():
    # Catches the ~130 @keyframe animations and hundreds of transitions that the
    # 17 existing per-component blocks left uncovered. 0.01ms (not 0) preserves
    # animationend/transitionend JS event delivery.
    assert _REDUCED_MOTION_BLOCK in _CSS


def test_global_reduced_motion_is_last_rule():
    # Must be at the end of the file so its universal selector (*) doesn't
    # accidentally shadow more-specific per-component blocks.
    catch_all_idx = _CSS.rindex(_REDUCED_MOTION_BLOCK)
    # Only whitespace after the catch-all
    assert _CSS[catch_all_idx + len(_REDUCED_MOTION_BLOCK):].strip() == ""


def test_global_reduced_motion_uses_01ms_not_zero():
    # duration: 0 can suppress animationend/transitionend in some browsers.
    # 0.01ms lets the events fire while making motion imperceptible.
    block_idx = _CSS.index(_REDUCED_MOTION_BLOCK)
    block = _CSS[block_idx : block_idx + len(_REDUCED_MOTION_BLOCK)]
    assert "0.01ms" in block
    assert "duration: 0;" not in block and "duration: 0 " not in block


# ---------------------------------------------------------------------------
# 4. touch-action: manipulation on interactive elements
# ---------------------------------------------------------------------------

def test_button_base_rule_has_touch_action_manipulation():
    # Removes the 300ms tap-delay browsers impose for double-tap zoom detection.
    # pan/pinch-zoom are preserved (manipulation ≠ none). WCAG-safe.
    assert "touch-action: manipulation" in _CSS


def test_touch_action_covers_interactive_group():
    # The grouped rule extends manipulation to links, [role="button"], list
    # items, and dropdown items. Assert the exact rule, not just its components.
    assert (
        'button, a, [role="button"], .list-item, .dropdown-item '
        '{ touch-action: manipulation; }'
    ) in _CSS


# ---------------------------------------------------------------------------
# 5. filter:brightness hover rules inside pointer media query guard
# ---------------------------------------------------------------------------

def test_brightness_hover_rules_inside_pointer_media_guard():
    # After the fix, every filter:brightness rule that applies on :hover must
    # be inside @media (hover: hover) and (pointer: fine).  This prevents the
    # sticky-hover bug on touch (tap fires a synthetic hover that persists).
    violations = []
    for m in re.finditer(r"filter\s*:\s*brightness", _CSS):
        idx = m.start()
        # Look back up to 300 chars for a :hover context
        pre = _CSS[max(0, idx - 300) : idx]
        if ":hover" not in pre:
            continue  # not a hover rule
        # Walk back further for the @media wrapper (up to 600 chars)
        outer = _CSS[max(0, idx - 600) : idx]
        if "(hover: hover)" not in outer or "(pointer: fine)" not in outer:
            # Grab the rule text for the error message
            snippet = _CSS[max(0, idx - 80) : idx + 60].replace("\n", " ").strip()
            violations.append(f"char {idx}: {snippet!r}")
    assert not violations, (
        "filter:brightness :hover rules found outside @media (hover: hover) and "
        "(pointer: fine) guard:\n" + "\n".join(violations)
    )


def test_active_states_added_for_touch_feedback():
    # For each guarded hover rule an :active fallback was added outside the
    # guard so touch users still get press feedback. Assert the specific rules
    # that replaced the hover-only brightness brightening.
    assert ".confirm-btn-primary:active { opacity: 0.85; }" in _CSS
    assert ".cmp-btn-primary:active:not(:disabled) { opacity: 0.88; }" in _CSS
    assert ".task-status-badge:active { opacity: 0.85; }" in _CSS
    assert ".doc-suggestion-accept:active { opacity: 0.85; }" in _CSS

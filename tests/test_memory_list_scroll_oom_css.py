"""
Regression tests for hover raster-tile accumulation fixes on the Brain memory list.

Root cause addressed: the base .memory-item carries `transition: all 0.15s`. In
#memory-list, hover entry/exit animates background and border-color — neither is
compositor-promoted. Each transition deposited raster tile frames at 60 fps. Qt
never evicts tiles without OS memory pressure, so they accumulated without bound.

Fix: override with `transition: opacity 0.15s` in the list context. Opacity is
compositor-promoted (zero raster cost); background and border-color transitions
are eliminated. Primary bounding is done by the Chromium tile budget flag
(--enable-low-end-device-mode) and content-visibility:auto on list items.

Previous suppression-based fixes (hover background/border-color matching,
always-visible opacity:1 buttons, transition:none) have been reverted now that
proper engine-level tile management is in place.
"""

import re
from pathlib import Path

_CSS_PATH = Path(__file__).resolve().parents[1] / "static" / "style.css"


def _css() -> str:
    return _CSS_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Transition override (kept — compositor-safe alternative to suppression)
# ---------------------------------------------------------------------------

def test_memory_list_overrides_transition_all():
    """#memory-list .memory-item must not inherit transition: all."""
    css = _css()
    assert "#memory-list .memory-item" in css
    idx = css.index("#memory-list .memory-item {")
    block = css[idx:idx + 800]
    assert "transition: opacity" in block


def test_base_memory_item_transition_all_still_present():
    """Base .memory-item keeps transition: all for non-list contexts."""
    css = _css()
    idx = css.index(".memory-item {")
    block = css[idx:idx + 400]
    assert "transition: all" in block


def test_memory_list_transition_not_all():
    """
    #memory-list .memory-item must not apply transition: all.
    The override replaces the broad shorthand with a property-specific value.
    Checks the rule block with comments stripped so the description of the
    bug in the comment does not trigger a false positive.
    """
    css = _css()
    idx = css.index("#memory-list .memory-item {")
    block = css[idx:idx + 800]
    block_no_comments = re.sub(r"/\*.*?\*/", "", block, flags=re.DOTALL)
    assert "transition: all" not in block_no_comments


def test_memory_list_transition_is_compositor_promoted():
    """
    The transition property in #memory-list .memory-item context must target
    only compositor-promoted properties (opacity, transform) or none at all.
    background and border-color transitions require main-thread painting and
    are the source of the raster-tile accumulation.
    """
    css = _css()
    idx = css.index("#memory-list .memory-item {")
    block = css[idx:idx + 800]
    assert "transition: background" not in block
    assert "transition: border" not in block


def test_memory_list_item_no_isolation_isolate():
    """
    #memory-list .memory-item must NOT have isolation: isolate.
    isolation: isolate was added for the ::before z-index:-1 approach, which
    was removed because it caused compositor layer explosion. Regression guard.
    """
    css = _css()
    idx = css.index("#memory-list .memory-item {")
    block = css[idx:idx + 800]
    block_no_comments = re.sub(r"/\*.*?\*/", "", block, flags=re.DOTALL)
    assert "isolation: isolate" not in block_no_comments


# ---------------------------------------------------------------------------
# Suppression revert guards (ensure the old approach is not re-introduced)
# ---------------------------------------------------------------------------

def test_hover_background_suppression_not_present():
    """
    The old approach of setting #memory-list .memory-item:hover background
    to match the non-hover value has been reverted. Hover UX is restored.
    Primary tile bounding is now --enable-low-end-device-mode.
    """
    css = _css()
    assert "Suppress paint-inducing background/border-color" not in css


def test_action_buttons_opacity_suppression_not_present():
    """
    The old approach of fixing #memory-list .memory-item-actions opacity at 1
    and removing its transition has been reverted. Buttons now reveal on hover
    normally; tile eviction is handled at the engine level.
    """
    css = _css()
    assert "#memory-list .memory-item-actions {\n  opacity: 1" not in css


def test_menu_btn_opacity_suppression_not_present():
    """
    The old approach of fixing #memory-list .memory-menu-btn opacity at 1
    has been reverted. Hover reveal animation is restored.
    """
    css = _css()
    assert "#memory-list .memory-menu-btn {\n  opacity: 1" not in css

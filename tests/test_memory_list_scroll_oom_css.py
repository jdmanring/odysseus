"""
Regression tests for hover raster-tile accumulation fixes on the Brain memory list.

Two root causes addressed:

1. Transition animation (phase 1 fix):
   The base .memory-item carries `transition: all 0.15s`. In #memory-list, hover
   entry/exit animates background and border-color — neither is compositor-promoted.
   Each transition deposited ~9 raster tile frames at 60 fps. Qt never evicts tiles
   without OS memory pressure, so they accumulated without bound.
   Fix: override with `transition: opacity 0.15s` in the list context.

2. Hover paint itself (phase 2 fix):
   Even with no transition, the base .memory-item:hover rule changes background and
   border-color on every hover entry/exit, generating 1 raster tile frame per event.
   Across many hover cycles with 20+ items, tiles accumulate significantly.
   Fix: suppress the paint-causing hover properties in the list context (set them to
   their non-hover computed values — Chromium skips paint when values are unchanged)
   and replace the hover visual with a ::before overlay whose opacity transitions
   from 0→1. Opacity is compositor-promoted: zero tiles generated on hover.
   isolation: isolate on the item creates a stacking context so ::before with
   z-index: -1 is contained (above item background, below flow content, below ::after).
"""

import re
from pathlib import Path

_CSS_PATH = Path(__file__).resolve().parents[1] / "static" / "style.css"


def _css() -> str:
    return _CSS_PATH.read_text(encoding="utf-8")


def test_memory_list_overrides_transition_all():
    """#memory-list .memory-item must not inherit transition: all."""
    css = _css()
    assert "#memory-list .memory-item" in css
    idx = css.index("#memory-list .memory-item {")
    block = css[idx:idx + 1100]
    # The override must exist inside the scoped rule.
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
    # Window must be large enough to capture the full rule body (incl. comments).
    block = css[idx:idx + 1100]
    block_no_comments = re.sub(r"/\*.*?\*/", "", block, flags=re.DOTALL)
    # The list context must not set transition: all (the source of the bug).
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
    block = css[idx:idx + 1100]
    # No transition on main-thread paint properties in this context.
    assert "transition: background" not in block
    assert "transition: border" not in block


# ---------------------------------------------------------------------------
# Phase 2: hover paint suppression + ::before compositor overlay
# ---------------------------------------------------------------------------

def test_memory_list_item_has_isolation_isolate():
    """
    #memory-list .memory-item must have isolation: isolate.
    This creates a stacking context so ::before with z-index:-1 is contained
    within the item (above item background, below static content children).
    """
    css = _css()
    idx = css.index("#memory-list .memory-item {")
    block = css[idx:idx + 1100]
    assert "isolation: isolate" in block


def test_memory_list_before_overlay_present():
    """#memory-list .memory-item::before must exist as the hover overlay."""
    css = _css()
    assert "#memory-list .memory-item::before" in css


def test_memory_list_before_overlay_opacity_zero():
    """::before overlay must start at opacity 0 (invisible when not hovered)."""
    css = _css()
    idx = css.index("#memory-list .memory-item::before")
    block = css[idx:idx + 400]
    assert "opacity: 0" in block


def test_memory_list_before_overlay_transition_opacity():
    """::before must transition only opacity (compositor-promoted — no paint)."""
    css = _css()
    idx = css.index("#memory-list .memory-item::before")
    block = css[idx:idx + 400]
    assert "transition: opacity" in block


def test_memory_list_before_has_negative_z_index():
    """
    ::before must have z-index: -1 to sit below static content children
    but above the item's own background within the isolation stacking context.
    """
    css = _css()
    idx = css.index("#memory-list .memory-item::before")
    block = css[idx:idx + 400]
    assert "z-index: -1" in block


def test_memory_list_before_pointer_events_none():
    """::before overlay must not capture pointer events."""
    css = _css()
    idx = css.index("#memory-list .memory-item::before")
    block = css[idx:idx + 400]
    assert "pointer-events: none" in block


def test_memory_list_hover_before_opacity_one():
    """On hover, ::before opacity becomes 1 — the compositor fade-in."""
    css = _css()
    assert "#memory-list .memory-item:hover::before" in css
    idx = css.index("#memory-list .memory-item:hover::before")
    block = css[idx:idx + 100]
    assert "opacity: 1" in block


def test_memory_list_hover_suppresses_background_paint():
    """
    #memory-list .memory-item:hover must set background to the same computed
    value as the non-hover state. This prevents Chromium from marking the element
    dirty for repaint when the base .memory-item:hover rule fires.
    """
    css = _css()
    assert "#memory-list .memory-item:hover {" in css
    idx = css.index("#memory-list .memory-item:hover {")
    block = css[idx:idx + 200]
    # Must match the non-hover value exactly so no paint is triggered.
    assert "background: color-mix(in srgb, var(--fg) 3%, transparent)" in block


def test_memory_list_hover_suppresses_border_paint():
    """
    #memory-list .memory-item:hover must reset border-color to var(--border)
    (the non-hover value), suppressing the paint-inducing border change.
    """
    css = _css()
    idx = css.index("#memory-list .memory-item:hover {")
    block = css[idx:idx + 200]
    assert "border-color: var(--border)" in block


# ---------------------------------------------------------------------------
# Phase 3: will-change pre-promotion for opacity-animated descendants
# ---------------------------------------------------------------------------

def test_memory_list_before_has_will_change_opacity():
    """
    ::before must have will-change: opacity so the compositor layer is
    pre-promoted at load time. Without it, each hover cycle creates and
    destroys a compositor layer, leaving orphaned raster tiles in the Qt
    tile cache (no OS memory pressure signal — tiles never evicted).
    """
    css = _css()
    idx = css.index("#memory-list .memory-item::before")
    block = css[idx:idx + 500]
    assert "will-change: opacity" in block


def test_memory_list_item_actions_will_change_opacity():
    """
    .memory-item-actions in the list context must be pre-promoted with
    will-change: opacity. It transitions opacity 0→1 on item hover; without
    pre-promotion the layer is created/destroyed every hover cycle.
    """
    css = _css()
    assert "#memory-list .memory-item-actions" in css
    idx = css.index("#memory-list .memory-item-actions")
    block = css[idx:idx + 200]
    assert "will-change: opacity" in block


def test_memory_list_menu_btn_will_change_opacity():
    """
    .memory-menu-btn in the list context must be pre-promoted with
    will-change: opacity for the same reason as .memory-item-actions.
    """
    css = _css()
    assert "#memory-list .memory-menu-btn" in css
    idx = css.index("#memory-list .memory-menu-btn")
    block = css[idx:idx + 200]
    assert "will-change: opacity" in block


def test_memory_list_menu_btn_transition_only_opacity():
    """
    .memory-menu-btn in the list context must not carry transition: background
    or transition: border-color. The base rule has these; in #memory-list only
    opacity changes on item hover — the paint-inducing properties must be
    suppressed.
    """
    css = _css()
    idx = css.index("#memory-list .memory-menu-btn")
    block = css[idx:idx + 200]
    block_no_comments = re.sub(r"/\*.*?\*/", "", block, flags=re.DOTALL)
    assert "transition: background" not in block_no_comments
    assert "transition: border" not in block_no_comments

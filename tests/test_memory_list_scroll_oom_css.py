"""
Regression tests for hover raster-tile accumulation fixes on the Brain memory list.

Three root causes addressed:

1. Transition animation (phase 1 fix):
   The base .memory-item carries `transition: all 0.15s`. In #memory-list, hover
   entry/exit animates background and border-color — neither is compositor-promoted.
   Each transition deposited ~9 raster tile frames at 60 fps. Qt never evicts tiles
   without OS memory pressure, so they accumulated without bound.
   Fix: override with `transition: opacity 0.15s` in the list context.

2. Hover paint itself (phase 2 fix):
   Even with no transition, the base .memory-item:hover rule changes background and
   border-color on every hover entry/exit, generating 1 raster tile frame per event.
   Fix: set them to the same computed values as the non-hover state — Chromium's
   paint-invalidation check skips repaint when computed values are unchanged.

3. Opacity-animated descendants (phase 3 fix):
   The base rules hide .memory-item-actions and .memory-menu-btn at opacity:0 and
   reveal them on :hover. Each opacity 0→1→0 cycle creates and destroys a compositor
   layer in Qt's embedded Chromium (no OS memory pressure reaches cc::TileManager,
   so orphaned tiles from each destroyed layer accumulate without eviction).
   Fix: always-visible at opacity:1 in the list context. The hover rule computes to
   1→1 — Chromium detects no change and skips rasterization entirely.
"""

import re
from pathlib import Path

_CSS_PATH = Path(__file__).resolve().parents[1] / "static" / "style.css"


def _css() -> str:
    return _CSS_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Phase 1: transition override
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


# ---------------------------------------------------------------------------
# Phase 2: hover paint suppression
# ---------------------------------------------------------------------------

def test_memory_list_item_no_isolation_isolate():
    """
    #memory-list .memory-item must NOT have isolation: isolate.
    isolation: isolate was added for the ::before z-index:-1 approach (phase 2),
    which was removed because it caused compositor layer explosion. Regression
    guard: ensure it is not re-introduced.
    """
    css = _css()
    idx = css.index("#memory-list .memory-item {")
    block = css[idx:idx + 800]
    block_no_comments = re.sub(r"/\*.*?\*/", "", block, flags=re.DOTALL)
    assert "isolation: isolate" not in block_no_comments


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
# Phase 3: always-visible action buttons (no opacity cycle per hover)
# ---------------------------------------------------------------------------

def test_memory_list_item_actions_always_visible():
    """
    .memory-item-actions in the list context must be at opacity:1 always.
    The base rule hides it at opacity:0; revealing it on hover via opacity 0→1→0
    creates/destroys a compositor layer each cycle — orphaned tiles accumulate in
    Qt's tile cache (no OS pressure signal). opacity:1 makes the hover rule a
    no-op: Chromium's paint-invalidation check sees no change, zero tiles.
    """
    css = _css()
    assert "#memory-list .memory-item-actions" in css
    idx = css.index("#memory-list .memory-item-actions")
    block = css[idx:idx + 200]
    assert "opacity: 1" in block


def test_memory_list_item_actions_no_transition():
    """
    .memory-item-actions in the list context must have transition: none.
    The base rule carries transition: opacity 0.15s — removing it in the list
    context eliminates any transition machinery even if opacity were to change.
    """
    css = _css()
    idx = css.index("#memory-list .memory-item-actions")
    block = css[idx:idx + 200]
    assert "transition: none" in block


def test_memory_list_menu_btn_always_visible():
    """
    .memory-menu-btn in the list context must be at opacity:1 always.
    Same rationale as .memory-item-actions: the 0→1→0 opacity cycle destroys
    and recreates compositor layers, leaving orphaned tiles in Qt's tile cache.
    """
    css = _css()
    assert "#memory-list .memory-menu-btn" in css
    idx = css.index("#memory-list .memory-menu-btn")
    block = css[idx:idx + 200]
    assert "opacity: 1" in block


def test_memory_list_menu_btn_no_transition():
    """
    .memory-menu-btn in the list context must have transition: none.
    The base rule carries transition: opacity 0.15s, background 0.15s,
    border-color 0.15s. All three are suppressed since no property on this
    element changes on hover in the list context.
    """
    css = _css()
    idx = css.index("#memory-list .memory-menu-btn {")
    block = css[idx:idx + 200]
    block_no_comments = re.sub(r"/\*.*?\*/", "", block, flags=re.DOTALL)
    assert "transition: none" in block_no_comments


# ---------------------------------------------------------------------------
# Phase 4: button hover paint suppression
# ---------------------------------------------------------------------------

def test_memory_list_menu_btn_hover_suppressed():
    """
    #memory-list .memory-menu-btn:hover must set background, border-color, and
    color to the same non-hover values. The base rule changes all three on hover
    (background: 7% fg, border-color: var(--border), color: var(--fg)) —
    each change rasterizes new tiles. Qt never evicts tiles without OS pressure.
    """
    css = _css()
    assert "#memory-list .memory-menu-btn:hover" in css
    idx = css.index("#memory-list .memory-menu-btn:hover")
    block = css[idx:idx + 200]
    assert "background: none" in block
    assert "border-color: transparent" in block
    assert "color: var(--color-muted)" in block


def test_memory_list_item_btn_no_transition():
    """
    .memory-item-btn in the list context must have transition: none.
    The base rule carries transition: all 0.15s — on hover, background,
    border-color, and color all transition, generating ~9 raster tile frames
    each pass. transition: none eliminates the multi-frame accumulation.
    """
    css = _css()
    assert "#memory-list .memory-item-btn" in css
    idx = css.index("#memory-list .memory-item-btn {")
    block = css[idx:idx + 200]
    assert "transition: none" in block


def test_memory_list_item_btn_hover_suppressed():
    """
    #memory-list .memory-item-btn:hover must set background, border-color, and
    color to the same non-hover values — Chromium skips repaint when computed
    values are unchanged. Covers all button variants (.delete, .save, etc.)
    since #memory-list id specificity beats all class-only variant selectors.
    """
    css = _css()
    assert "#memory-list .memory-item-btn:hover" in css
    idx = css.index("#memory-list .memory-item-btn:hover")
    block = css[idx:idx + 200]
    assert "background: none" in block
    assert "border-color: transparent" in block
    assert "color: var(--color-muted)" in block

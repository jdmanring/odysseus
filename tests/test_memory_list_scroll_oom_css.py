"""
Regression tests for the scroll-triggered raster-tile accumulation fix
on the Brain memory list.

Root cause: the base .memory-item class carries `transition: all 0.15s`.
In #memory-list, as the cursor passes over items during scroll each item
cycles through enter-hover and leave-hover state, animating background
and border-color. Neither property is compositor-promoted; each transition
deposits ~9 frames of raster tiles at 60 fps. Qt does not forward OS
memory pressure to the renderer so the tiles are never evicted.

Fix: #memory-list .memory-item overrides the base transition with
`transition: opacity 0.15s`, limiting animated changes to the one
compositor-promoted property used in that context.
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
    idx = css.index("#memory-list .memory-item")
    block = css[idx:idx + 600]
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
    idx = css.index("#memory-list .memory-item")
    block = css[idx:idx + 600]
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
    idx = css.index("#memory-list .memory-item")
    block = css[idx:idx + 600]
    # No transition on main-thread paint properties in this context.
    assert "transition: background" not in block
    assert "transition: border" not in block

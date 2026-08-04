"""Regression guards for fix/css-contain-paint-transparent-rendering (#93).

Root cause: using contain:paint (via contain:content) on elements that either
(a) use backdrop-filter in a theme overlay or (b) are transparent scroll
containers in a composited pipeline causes two bugs:

  1. backdrop-filter on .sidebar reads from the element's own compositor layer
     instead of the composited background behind it — the frosted-glass blur
     effect fails or renders incorrectly.

  2. .chat-history (transparent, overflow-y:auto, contain:paint) gets promoted
     to an independent compositor layer. In Qt WebEngine with
     --enable-low-end-device-mode the layer's evicted tiles render as a solid
     colour instead of passing through to the canvas/body background, so the
     chat area shows wrong colours instead of the background animation.

Fix: use contain:layout style (not contain:content / contain:paint) on both
elements. Layout and style containment scope style recalculation correctly
without creating paint isolation or an independent compositor layer.

Matches the existing .modal-content pattern, which uses contain:layout style
precisely because it must not create paint clipping (overlapping content must
not be clipped at the element's border-box).
"""

from pathlib import Path

_CSS_PATH = Path(__file__).resolve().parents[1] / "static" / "style.css"


def _css() -> str:
    return _CSS_PATH.read_text(encoding="utf-8")


def _block(anchor: str, window: int = 700) -> str:
    css = _css()
    idx = css.index(anchor)
    return css[idx : idx + window]


# ---------------------------------------------------------------------------
# .sidebar — contain:layout style (not contain:paint)
# ---------------------------------------------------------------------------

def test_sidebar_contain_layout_style():
    """contain:layout style on .sidebar scopes style recalculation to the
    sidebar subtree without creating paint isolation. contain:paint would break
    backdrop-filter in the frosted theme (body.theme-frosted #sidebar) by
    compositing the sidebar into its own layer, making the blur read from that
    layer rather than the composited scene behind it."""
    block = _block(".sidebar {")
    rule_end = block.index("}")
    assert "contain: layout style" in block[:rule_end]


def test_sidebar_no_contain_paint():
    """contain:paint must not appear on .sidebar. The frosted theme applies
    backdrop-filter: blur(24px) to #sidebar — paint containment breaks that."""
    block = _block(".sidebar {")
    rule_end = block.index("}")
    assert "contain: content" not in block[:rule_end]
    assert "contain: paint" not in block[:rule_end]


# ---------------------------------------------------------------------------
# .chat-history — contain:layout style (not contain:paint)
# ---------------------------------------------------------------------------

def test_chat_history_contain_layout_style():
    """contain:layout style on .chat-history scopes addMessage() style
    recalculation to the chat area without creating paint isolation. The chat
    area has no background — it must composite transparently against the
    canvas/body background. contain:paint promotes it to a compositor layer;
    with --enable-low-end-device-mode's small tile budget, evicted tiles render
    as solid colour instead of transparent, hiding the background animation."""
    block = _block(".chat-history {")
    rule_end = block.index("}")
    assert "contain: layout style" in block[:rule_end]


def test_chat_history_no_contain_paint():
    """contain:paint must not appear on .chat-history to prevent opaque tile
    rendering over the transparent background area."""
    block = _block(".chat-history {")
    rule_end = block.index("}")
    assert "contain: content" not in block[:rule_end]
    assert "contain: paint" not in block[:rule_end]



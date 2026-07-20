"""Full-viewport dialog overlays must not use backdrop-filter.

In QtWebEngine (the app's actual runtime) a full-screen backdrop-filter blur
forces the compositor to re-rasterize the entire backdrop every frame — the
clear-all confirmation dialog flickered wildly on mouse move (2026-07-20).
A flat rgba dim is visually equivalent and costs nothing per frame. The
sidebar dropped its backdrop-filter for the same class of bug.
"""

import re
from pathlib import Path

CSS = re.sub(
    r"/\*.*?\*/",
    "",
    (Path(__file__).parent.parent / "static" / "style.css").read_text(),
    flags=re.S,
)

FULLSCREEN_OVERLAYS = [
    "#styled-confirm-overlay",
    "#cookbook-gguf-delete-overlay",
    "#styled-prompt-overlay",
]


def _blocks(selector):
    out = []
    for m in re.finditer(re.escape(selector) + r"[^{]*\{([^}]*)\}", CSS):
        out.append(m.group(1))
    return out


def test_fullscreen_overlays_have_no_backdrop_filter():
    for sel in FULLSCREEN_OVERLAYS:
        blocks = _blocks(sel)
        assert blocks, f"{sel} rule missing from style.css"
        for body in blocks:
            for decl in body.split(";"):
                if "backdrop-filter" in decl:
                    assert "none" in decl, f"{sel} uses backdrop-filter: {decl.strip()}"


def test_backdrop_filter_only_in_frosted_theme():
    """backdrop-filter re-samples its backdrop every invalidated frame. The
    only sanctioned user is the opt-in theme-frosted skin, where the blur IS
    the feature. Everything else uses flat translucency (2026-07-20 sweep)."""
    for m in re.finditer(r"([^{}]+)\{([^}]*)\}", CSS):
        body = m.group(2)
        for decl in body.split(";"):
            if "backdrop-filter" in decl and "none" not in decl:
                sel = m.group(1).strip()
                assert "theme-frosted" in sel, \
                    f"backdrop-filter outside theme-frosted: {sel.splitlines()[-1].strip()!r}"


def test_fullscreen_overlays_keep_a_dim():
    # Dropping the blur must not drop the dim itself.
    for sel in FULLSCREEN_OVERLAYS:
        assert any("rgba(0,0,0" in b for b in _blocks(sel)), f"{sel} lost its dim background"

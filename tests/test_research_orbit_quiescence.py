"""Research panel: the animated border "orbit" ring is removed (#115).

The ring required a dedicated compositor layer — a ~32 MB GPU texture on a hi-res
pane — for pure decoration. In an app that runs LOCAL models, video memory is the
scarce resource (that VRAM is the model's context window), so spending it on a
border effect is the wrong trade for any device. Job activity is already signalled
by the rail pulse / running dots / round counter. These guards prevent the
VRAM-costly decoration (or a will-change layer like it) from being re-added.
"""
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_JS = (_ROOT / "static" / "js" / "research" / "panel.js").read_text(encoding="utf-8")
_CSS = (_ROOT / "static" / "style.css").read_text(encoding="utf-8")


def test_orbit_dom_and_class_removed():
    assert "research-orbit" not in _JS
    assert "orbit-active" not in _JS


def test_orbit_css_removed():
    assert "research-orbit-spin" not in _CSS
    assert "@keyframes research-orbit-spin" not in _CSS
    assert "--research-orbit-angle" not in _CSS  # the old per-frame paint var, also gone


def test_no_will_change_layer_in_research_pane_styles():
    # A dedicated compositor layer for decoration is the VRAM cost we removed —
    # guard the research pane region against re-introducing one.
    idx = _CSS.find(".research-pane {")
    region = _CSS[idx: idx + 4000] if idx >= 0 else ""
    assert "will-change" not in region

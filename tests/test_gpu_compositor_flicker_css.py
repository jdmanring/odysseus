"""CSS regression guards for fix/gpu-compositor-flicker.

backdrop-filter: blur() was removed from ten elements whose backgrounds are
already opaque or near-opaque (so the blur result was hidden by the fill color,
but the GPU compositor work still ran). Each test below names the element and
explains why the blur was invisible, so a future change that re-adds the
property will fail with clear context.

filter: saturate() was also removed from the cookbook-modal-enter keyframe,
where it triggered a compositor layer teardown flash on the final frame.

No browser required — all checks are static assertions on style.css.
"""
from pathlib import Path

_CSS = (Path(__file__).resolve().parents[1] / "static" / "style.css").read_text(encoding="utf-8")


def _near(anchor: str, prop: str, window: int = 900) -> bool:
    """Return True if prop appears within window chars after the first anchor."""
    idx = _CSS.find(anchor)
    return idx >= 0 and prop in _CSS[idx : idx + window]


def _any_near(anchor: str, prop: str, window: int = 900) -> bool:
    """Return True if prop appears near ANY occurrence of anchor."""
    pos = 0
    while True:
        idx = _CSS.find(anchor, pos)
        if idx < 0:
            return False
        if prop in _CSS[idx : idx + window]:
            return True
        pos = idx + 1
    return False


# ---------------------------------------------------------------------------
# backdrop-filter: blur removed from elements with opaque backgrounds
# ---------------------------------------------------------------------------

def test_sidebar_no_backdrop_filter():
    # background: var(--sidebar-bg, var(--panel)) is fully opaque.
    # blur(10px) was firing on every sidebar item hover — most frequent trigger.
    assert not _near(".sidebar {", "backdrop-filter: blur")


def test_dropdown_no_backdrop_filter():
    # background: var(--panel) is fully opaque. blur(12px) was firing on
    # every dropdown open/close.
    assert not _near(".dropdown {", "backdrop-filter: blur")


def test_toast_no_backdrop_filter():
    # .toast is the notification banner (background: var(--panel), fully opaque).
    # blur(12px) was re-compositing on every toast show/hide.
    assert not _near(".toast {", "backdrop-filter: blur")


def test_styled_confirm_overlay_no_backdrop_filter():
    # background: rgba(0,0,0,0.5) — a 4px blur through 50% black is imperceptible.
    # The blur result was invisible; the layer promotion was not.
    assert not _near("#styled-confirm-overlay {", "backdrop-filter: blur")


def test_styled_prompt_overlay_no_backdrop_filter():
    # Same reasoning as the confirm overlay.
    assert not _near("#styled-prompt-overlay {", "backdrop-filter: blur")


def test_search_overlay_no_backdrop_filter():
    # background: rgba(0,0,0,0.6) — 6px blur through 60% black is imperceptible.
    assert not _near(".search-overlay {", "backdrop-filter: blur")


def test_recording_indicator_no_backdrop_filter():
    # #recording-indicator appears twice in style.css (two layout contexts).
    # background: rgba(0,0,0,0.8) on both — blur invisible at 80% opacity.
    assert not _any_near("#recording-indicator {", "backdrop-filter: blur")


def test_md_toolbar_overflow_menu_no_backdrop_filter():
    # background: var(--panel) is fully opaque.
    assert not _near(".md-toolbar-overflow-menu {", "backdrop-filter: blur")


def test_import_prompt_banner_no_backdrop_filter():
    # background: var(--panel) is fully opaque.
    assert not _near(".import-prompt-banner {", "backdrop-filter: blur")


# ---------------------------------------------------------------------------
# filter: saturate removed from cookbook-modal-enter keyframe
# ---------------------------------------------------------------------------

def test_cookbook_modal_enter_no_filter_saturate():
    # Animating filter from saturate(0.85)/saturate(1.05) → none at 100%
    # triggered a compositor layer teardown on the final animation frame,
    # producing a one-frame flash. The saturation shift (±15%) was imperceptible;
    # opacity + transform continue to animate identically.
    assert not _near("@keyframes cookbook-modal-enter {", "filter: saturate")


# ---------------------------------------------------------------------------
# Verdict reversal (per-frame decoration sweep): these two blurs were first
# judged "faint but intentional — kept". The sweep reversed that: a blur
# behind a 96% opaque background is invisible while still re-sampling its
# backdrop every invalidated frame, and the album button floats over gallery
# images. Both now use flat translucency; assert the blur stays gone.
# ---------------------------------------------------------------------------

def _no_active_backdrop_filter(anchor):
    # Match only real declarations, not the word inside explanatory comments.
    import re as _re
    idx = _CSS.index(anchor)
    block = _CSS[idx:_CSS.index("}", idx)]
    block = _re.sub(r"/\*.*?\*/", "", block, flags=_re.S)
    return not any(
        "backdrop-filter" in d and "none" not in d for d in block.split(";")
    )


def test_gallery_album_menu_btn_has_no_backdrop_filter():
    assert _no_active_backdrop_filter(".gallery-album-menu-btn {")


def test_ge_transform_popup_has_no_backdrop_filter():
    assert _no_active_backdrop_filter(".ge-transform-popup {")

# NOTE: memory-synapse-sweep tests intentionally live in
# test_brain_panel_oom_css.py, not here. They were previously duplicated in this
# file, which coupled the gpu-compositor-flicker (backdrop-filter) work to the
# brain-panel-oom (#108) animation work — two unrelated concerns. Per "one thing
# per PR", this file now guards only the backdrop-filter removals.

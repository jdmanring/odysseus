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
# Sanity: elements with legitimate translucency still have backdrop-filter
# ---------------------------------------------------------------------------

def test_gallery_album_menu_btn_retains_backdrop_filter():
    # .gallery-album-card album menu button has opacity:0 (nearly transparent).
    # Its backdrop-filter was intentionally kept — the blur is visible on hover.
    assert _near(".gallery-album-menu-btn {", "backdrop-filter")


def test_ge_transform_popup_retains_backdrop_filter():
    # .ge-transform-popup has background: color-mix(in srgb, var(--panel) 96%, transparent).
    # 4% translucency — blur is faint but intentional. Kept.
    assert _near(".ge-transform-popup {", "backdrop-filter")


# ---------------------------------------------------------------------------
# Brain panel sweep animation — must use transform, not @property custom property
# ---------------------------------------------------------------------------

def test_memory_sweep_uses_no_css_property_registration():
    # @property --sweep forced main-thread style recalculation every frame for
    # every memory item, filling Oilpan with raster tiles that QtWebEngine never
    # GCs (no OS memory pressure signals reach the renderer process). This caused
    # 14–18 GB RSS spikes when the Brain panel was open. The fix uses
    # transform: translateX() which is fully GPU-composited.
    assert "@property --sweep" not in _CSS
    assert "syntax: '<percentage>'" not in _CSS


def test_memory_sweep_animation_uses_transform():
    # The memory-synapse-sweep keyframe must animate transform (GPU-composited),
    # not the --sweep custom property (main-thread, triggers raster tile churn).
    idx = _CSS.find("@keyframes memory-synapse-sweep {")
    assert idx >= 0, "memory-synapse-sweep keyframe must exist"
    block = _CSS[idx : idx + 400]
    assert "transform" in block, "sweep must animate transform"
    assert "--sweep" not in block, "sweep must not animate --sweep custom property"


def test_memory_sweep_hover_does_not_use_animation_none():
    # `animation: none` on hover destroys the compositor layer and recreates it
    # on mouse-leave, causing a gray-frame flash. The hover rule must suppress
    # the sweep with opacity only (compositor-friendly) instead.
    idx = _CSS.find("#memory-list .memory-item:hover::after")
    assert idx >= 0, "hover rule for sweep must exist"
    rule = _CSS[idx : idx + 200]
    assert "animation: none" not in rule, (
        "hover must not use animation:none — use opacity:0 to avoid "
        "compositor layer teardown and the resulting gray-frame flash"
    )
    assert "opacity: 0" in rule or "opacity:0" in rule

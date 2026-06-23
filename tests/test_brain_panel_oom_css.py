"""CSS regression guards for fix/brain-panel-oom.

Root cause
----------
The memory-synapse-sweep animation on #memory-list .memory-item::after used
@property --sweep (a registered CSS custom property) to animate gradient stop
positions. Every frame the browser had to recompute the full linear-gradient()
for every visible memory item because --sweep changed — main-thread style
recalculation running at ~60 fps multiplied by N items. The -webkit-mask
added a second main-thread compositor pass per item per frame.

Each repaint cycle produced Oilpan-managed raster tiles. Under a real browser
these are periodically evicted by OS memory pressure signals. QtWebEngine
receives no such signals — the raster tiles accumulated without bound, causing
the 14–18 GB RSS spikes observed when the Brain panel was open with many
memories visible.

A second symptom: the hover rule used `animation: none` to suppress the sweep.
This destroyed the compositor layer promoted for the animation and recreated it
when the cursor left the item — the gray-frame flash users saw while mousing
over memory entries.

Fix
---
Replace @property + gradient animation with transform: translateX() (fully
GPU-composited, zero main-thread involvement). The parent's overflow: hidden
clips the strip off-screen during the idle phase, so no opacity transition is
needed — the compositor layer stays up continuously and there is no teardown.
Hover uses opacity: 0 instead of animation: none to suppress the sweep without
triggering a layer teardown.

All checks are static assertions on style.css — no browser required.
"""
from pathlib import Path

_CSS = (Path(__file__).resolve().parents[1] / "static" / "style.css").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# @property --sweep must be gone — it was the root cause of raster-tile OOM
# ---------------------------------------------------------------------------

def test_no_css_property_registration_for_sweep():
    """@property --sweep forced main-thread style recalculation every frame
    for every memory item in the Brain panel list. Removing it is the primary
    fix for the Oilpan raster-tile accumulation that caused 14-18 GB RSS."""
    assert "@property --sweep" not in _CSS, (
        "@property --sweep re-introduced — this triggers main-thread gradient "
        "recalculation every frame for every memory item, filling Oilpan with "
        "raster tiles that QtWebEngine never GCs without OS memory pressure."
    )


def test_no_sweep_custom_property_syntax_declaration():
    """Belt-and-suspenders: the syntax: '<percentage>' declaration is the
    payload of the @property block. If the block header slips past the previous
    test under a different spelling, this catches the payload."""
    assert "syntax: '<percentage>'" not in _CSS


# ---------------------------------------------------------------------------
# Keyframe must animate transform, not the custom property
# ---------------------------------------------------------------------------

def test_memory_sweep_keyframe_animates_transform():
    """The replacement keyframe must drive transform: translateX() so the GPU
    compositor owns every frame — no main-thread involvement."""
    idx = _CSS.find("@keyframes memory-synapse-sweep {")
    assert idx >= 0, "memory-synapse-sweep keyframe must exist"
    block = _CSS[idx : idx + 400]
    assert "transform" in block, (
        "memory-synapse-sweep must animate transform (GPU-composited)"
    )


def test_memory_sweep_keyframe_does_not_animate_custom_property():
    """The keyframe must not contain --sweep: ... — that's the main-thread path."""
    idx = _CSS.find("@keyframes memory-synapse-sweep {")
    assert idx >= 0
    block = _CSS[idx : idx + 400]
    assert "--sweep" not in block, (
        "memory-synapse-sweep must not animate --sweep custom property — "
        "use transform: translateX() for GPU-composited animation"
    )


def test_memory_sweep_keyframe_does_not_animate_background_position():
    """background-position animation is also main-thread. The keyframe must
    not use it as an alternative to the custom-property approach."""
    idx = _CSS.find("@keyframes memory-synapse-sweep {")
    assert idx >= 0
    block = _CSS[idx : idx + 400]
    assert "background-position" not in block


# ---------------------------------------------------------------------------
# Hover rule must not trigger compositor layer teardown
# ---------------------------------------------------------------------------

def test_memory_sweep_hover_uses_opacity_not_animation_none():
    """`animation: none` on hover destroys the promoted compositor layer.
    When the cursor leaves, the layer is recreated — the gray-frame flash.
    The fix uses opacity: 0 to hide the sweep without stopping the animation."""
    idx = _CSS.find("#memory-list .memory-item:hover::after")
    assert idx >= 0, "hover rule for sweep suppression must exist"
    rule = _CSS[idx : idx + 200]
    assert "animation: none" not in rule, (
        "hover must not use animation:none — it destroys the compositor layer "
        "and recreates it on mouse-leave, producing a gray-frame flash. "
        "Use opacity:0 to suppress the sweep without teardown."
    )
    assert "opacity: 0" in rule or "opacity:0" in rule, (
        "hover rule must set opacity:0 to suppress the sweep visually"
    )


# ---------------------------------------------------------------------------
# Mask approach must be gone — was the second main-thread compositor pass
# ---------------------------------------------------------------------------

def test_no_webkit_mask_on_memory_sweep():
    """-webkit-mask on the ::after pseudo-element forced a second compositor
    pass per item per frame alongside the @property gradient computation.
    The transform approach makes the mask unnecessary."""
    idx = _CSS.find("#memory-list .memory-item::after {")
    assert idx >= 0
    block = _CSS[idx : idx + 600]
    assert "-webkit-mask" not in block, (
        "-webkit-mask re-added to the sweep pseudo-element — "
        "this forces a second main-thread compositor pass per item per frame"
    )
    assert "mask-composite" not in block


# ---------------------------------------------------------------------------
# will-change declared so the compositor promotes the layer up front
# ---------------------------------------------------------------------------

def test_memory_sweep_declares_will_change_transform():
    """will-change: transform tells the compositor to promote the layer before
    the first animation frame, avoiding the one-frame layout cost on first paint."""
    idx = _CSS.find("#memory-list .memory-item::after {")
    assert idx >= 0
    block = _CSS[idx : idx + 900]
    assert "will-change: transform" in block, (
        "::after element should declare will-change:transform so the compositor "
        "promotes its layer before the first animation frame"
    )


# ---------------------------------------------------------------------------
# prefers-reduced-motion still suppresses the animation for accessibility
# ---------------------------------------------------------------------------

def test_prefers_reduced_motion_still_suppresses_sweep():
    """The animation must still be silenced for users who opt out of motion."""
    idx = _CSS.find("@media (prefers-reduced-motion: reduce)")
    found = False
    while idx >= 0:
        block = _CSS[idx : idx + 300]
        if "memory-item::after" in block and "animation: none" in block:
            found = True
            break
        idx = _CSS.find("@media (prefers-reduced-motion: reduce)", idx + 1)
    assert found, (
        "prefers-reduced-motion block must still suppress #memory-list "
        ".memory-item::after animation"
    )


# ---------------------------------------------------------------------------
# Pattern A: notes-quick-add hover/focus must not destroy compositor layer
# ---------------------------------------------------------------------------

def test_notes_quick_pulse_hover_uses_paused_not_none():
    """`animation: none` on hover destroys the compositor layer promoted for
    the quick-add pulse animation; the layer is recreated on mouse-leave,
    causing a gray-frame flash. Use animation-play-state: paused instead so
    the layer stays promoted and no teardown occurs."""
    idx = _CSS.find(".notes-quick-add:hover {")
    assert idx >= 0, ".notes-quick-add:hover rule must exist"
    block = _CSS[idx : idx + 300]
    assert "animation: none" not in block, (
        ".notes-quick-add:hover must not use animation:none — it destroys the "
        "compositor layer and recreates it on mouse-leave, producing a "
        "gray-frame flash. Use animation-play-state:paused instead."
    )
    assert "animation-play-state: paused" in block, (
        ".notes-quick-add:hover must set animation-play-state:paused to "
        "suppress the pulse animation without tearing down the compositor layer"
    )


def test_notes_quick_pulse_focus_uses_paused_not_none():
    """`animation: none` on :focus-within has the same layer-teardown problem
    as on :hover — use animation-play-state: paused instead."""
    idx = _CSS.find(".notes-quick-add:focus-within {")
    assert idx >= 0, ".notes-quick-add:focus-within rule must exist"
    block = _CSS[idx : idx + 300]
    assert "animation: none" not in block, (
        ".notes-quick-add:focus-within must not use animation:none — it "
        "destroys the compositor layer and recreates it when focus leaves, "
        "producing a gray-frame flash. Use animation-play-state:paused instead."
    )
    assert "animation-play-state: paused" in block, (
        ".notes-quick-add:focus-within must set animation-play-state:paused to "
        "suppress the pulse animation without tearing down the compositor layer"
    )


# ---------------------------------------------------------------------------
# Pattern B: note-ai-shine keyframe must not use filter: drop-shadow()
# ---------------------------------------------------------------------------

def test_note_ai_shine_no_filter_drop_shadow():
    """`filter: drop-shadow()` on SVGs forces software rendering of the
    filtered image every frame. When applied to many note-card AI chips
    simultaneously the raster tiles accumulate in Oilpan. The drop-shadow
    is invisible at the 0% stop (scale 0) anyway — removing filter from the
    keyframe eliminates the per-frame software-render cost with no visible
    change at the ends of the animation cycle."""
    idx = _CSS.find("@keyframes note-ai-shine {")
    assert idx >= 0, "@keyframes note-ai-shine must exist"
    block = _CSS[idx : idx + 300]
    assert "filter:" not in block, (
        "@keyframes note-ai-shine must not animate filter: — drop-shadow() on "
        "SVGs forces software rendering every frame for every AI chip in the "
        "note list, filling Oilpan with raster tiles that QtWebEngine never GCs"
    )


# ---------------------------------------------------------------------------
# Pattern C: notes-drag-shimmer must use transform, not background-position
# ---------------------------------------------------------------------------

def test_notes_drag_shimmer_uses_transform_not_background_position():
    """`background-position` animation repaints the gradient on every card
    every frame. With 30 note cards visible during drag that is 30 gradient
    repaints per frame, each producing Oilpan raster tiles that QtWebEngine
    never evicts. The fix animates transform: translateX() instead — fully
    GPU-composited, zero main-thread involvement — with overflow:hidden on
    the parent clipping the strip while it is off-screen."""
    idx = _CSS.find("@keyframes notes-drag-shimmer {")
    assert idx >= 0, "@keyframes notes-drag-shimmer must exist"
    block = _CSS[idx : idx + 300]
    assert "background-position" not in block, (
        "@keyframes notes-drag-shimmer must not animate background-position — "
        "this repaints the gradient on every visible note card every frame, "
        "filling Oilpan with raster tiles that QtWebEngine never GCs. "
        "Use transform: translateX() for GPU-composited animation instead."
    )
    assert "transform" in block, (
        "@keyframes notes-drag-shimmer must animate transform: translateX() "
        "so the GPU compositor owns every frame with no main-thread involvement"
    )

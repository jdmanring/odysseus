"""CSS regression guards for fix/brain-panel-oom.

Root cause
----------
The memory-synapse-sweep animation on #memory-list .memory-item::after animated
@property --sweep, a typed registered custom property (syntax: '<percentage>').
Typed custom properties participate in computed-value cascading, so every change
to --sweep invalidates and re-runs the style calculation for every element that
uses var(--sweep) in a computed value. At 60 fps across N visible items that is
60 * N style recalculations per second, each producing a fresh raster tile.

Qt does not forward OS memory pressure signals to the embedded Chromium renderer,
so the compositor's tile manager never receives eviction pressure. The 14-18 GB
RSS spikes occurred because raster tiles from these per-frame repaints accumulated
without bound while the Brain panel was open.

A secondary symptom: the hover rule suppressed the sweep with animation:none,
which destroys the compositor layer promoted for the animation. When the mouse
left the item the layer was recreated, producing the gray-frame flash users
reported when mousing over memory entries.

Fix
---
Replace @property + gradient animation with transform: translateX(). transform is
compositor-promoted; the main thread is not involved after the first paint.
The parent element's overflow:hidden clips the strip while it is positioned
off-screen, so no opacity toggle is needed and the compositor layer is never
torn down. Hover suppression uses opacity:0 instead of animation:none.

All assertions are static checks on style.css; no browser is required.
"""
from pathlib import Path

_CSS = (Path(__file__).resolve().parents[1] / "static" / "style.css").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# @property --sweep must be absent; it was the root cause of the raster-tile buildup
# ---------------------------------------------------------------------------

def test_no_css_property_registration_for_sweep():
    """The @property --sweep registration forced per-item style recalculation
    every frame. Its removal is the primary fix for the raster-tile accumulation
    that caused 14-18 GB RSS when the Brain panel was open."""
    assert "@property --sweep {" not in _CSS, (
        "@property --sweep re-introduced. Typed custom properties trigger style "
        "recalculation for every dependent element on every frame they change. "
        "Qt does not forward OS pressure to the renderer so tiles accumulate."
    )


def test_no_sweep_custom_property_syntax_declaration():
    """Belt-and-suspenders check: the syntax: '<percentage>' line is the
    payload of the @property block. Catches the payload if the block header
    appears under a different name."""
    assert "syntax: '<percentage>'" not in _CSS


# ---------------------------------------------------------------------------
# Keyframe must animate transform, not the custom property
# ---------------------------------------------------------------------------

def test_memory_sweep_keyframe_animates_transform():
    """The replacement keyframe must use transform: translateX() so the
    compositor owns every frame without main-thread involvement."""
    idx = _CSS.find("@keyframes memory-synapse-sweep {")
    assert idx >= 0, "memory-synapse-sweep keyframe must exist"
    block = _CSS[idx : idx + 400]
    assert "transform" in block, (
        "memory-synapse-sweep must animate transform (compositor-promoted)"
    )


def test_memory_sweep_keyframe_does_not_animate_custom_property():
    """The keyframe must not set --sweep; that is the main-thread path."""
    idx = _CSS.find("@keyframes memory-synapse-sweep {")
    assert idx >= 0
    block = _CSS[idx : idx + 400]
    assert "--sweep" not in block, (
        "memory-synapse-sweep must not animate --sweep. "
        "Use transform: translateX() so the compositor owns every frame."
    )


def test_memory_sweep_keyframe_does_not_animate_background_position():
    """background-position is also not compositor-promoted; the keyframe must
    not use it as an alternative to the custom-property approach."""
    idx = _CSS.find("@keyframes memory-synapse-sweep {")
    assert idx >= 0
    block = _CSS[idx : idx + 400]
    assert "background-position" not in block


# ---------------------------------------------------------------------------
# Hover rule must not cause compositor layer teardown
# ---------------------------------------------------------------------------

def test_memory_sweep_hover_uses_opacity_not_animation_none():
    """animation:none on hover destroys the promoted compositor layer.
    When the cursor leaves, the layer is recreated, causing a gray flash.
    The fix uses opacity:0 to hide the sweep without stopping the animation."""
    idx = _CSS.find("#memory-list .memory-item:hover::after")
    assert idx >= 0, "hover rule for sweep suppression must exist"
    rule = _CSS[idx : idx + 200]
    assert "animation: none" not in rule, (
        "hover must not use animation:none. animation:none destroys the promoted "
        "layer; recreation on mouse-leave produces a gray-frame flash. "
        "Use opacity:0 to suppress the sweep without layer teardown."
    )
    assert "opacity: 0" in rule or "opacity:0" in rule, (
        "hover rule must set opacity:0 to suppress the sweep visually"
    )


# ---------------------------------------------------------------------------
# Mask approach must be absent; it added a second compositor pass per item
# ---------------------------------------------------------------------------

def test_no_webkit_mask_on_memory_sweep():
    """-webkit-mask on the ::after element added a second compositor pass per
    item per frame on top of the @property gradient computation.
    The transform approach makes the mask unnecessary."""
    idx = _CSS.find("#memory-list .memory-item::after {")
    assert idx >= 0
    block = _CSS[idx : idx + 600]
    assert "-webkit-mask" not in block, (
        "-webkit-mask re-added to the sweep pseudo-element. "
        "This adds a second compositor pass per item per frame."
    )
    assert "mask-composite" not in block


# ---------------------------------------------------------------------------
# will-change declared so the compositor promotes the layer before first paint
# ---------------------------------------------------------------------------

def test_memory_sweep_declares_will_change_transform():
    """will-change: transform tells the compositor to promote the layer before
    the first animation frame, avoiding a one-frame layout cost on first paint."""
    idx = _CSS.find("#memory-list .memory-item::after {")
    assert idx >= 0
    block = _CSS[idx : idx + 900]
    assert "will-change: transform" in block, (
        "::after should declare will-change:transform so the compositor "
        "promotes its layer before the first animation frame"
    )


# ---------------------------------------------------------------------------
# prefers-reduced-motion must still suppress the animation
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
        "prefers-reduced-motion block must suppress #memory-list "
        ".memory-item::after animation"
    )


# ---------------------------------------------------------------------------
# notes-quick-add hover/focus must not destroy the compositor layer
# ---------------------------------------------------------------------------

def test_notes_quick_pulse_hover_uses_paused_not_none():
    """animation:none on hover destroys the compositor layer promoted for the
    quick-add pulse animation. The layer is recreated on mouse-leave, causing
    a gray flash. animation-play-state:paused freezes the animation at the
    current keyframe without removing the promoted layer."""
    idx = _CSS.find(".notes-quick-add:hover {")
    assert idx >= 0, ".notes-quick-add:hover rule must exist"
    block = _CSS[idx : idx + 300]
    assert "animation: none" not in block, (
        ".notes-quick-add:hover must not use animation:none. animation:none "
        "destroys the promoted layer; recreation on mouse-leave causes a gray "
        "flash. Use animation-play-state:paused instead."
    )
    assert "animation-play-state: paused" in block, (
        ".notes-quick-add:hover must set animation-play-state:paused"
    )


def test_notes_quick_pulse_focus_uses_paused_not_none():
    """animation:none on :focus-within has the same layer-teardown problem as
    on :hover. Use animation-play-state:paused instead."""
    idx = _CSS.find(".notes-quick-add:focus-within {")
    assert idx >= 0, ".notes-quick-add:focus-within rule must exist"
    block = _CSS[idx : idx + 300]
    assert "animation: none" not in block, (
        ".notes-quick-add:focus-within must not use animation:none. animation:none "
        "destroys the promoted layer; recreation when focus leaves causes a gray "
        "flash. Use animation-play-state:paused instead."
    )
    assert "animation-play-state: paused" in block, (
        ".notes-quick-add:focus-within must set animation-play-state:paused"
    )


# ---------------------------------------------------------------------------
# note-ai-shine keyframe must not animate filter
# ---------------------------------------------------------------------------

def test_note_ai_shine_no_filter_drop_shadow():
    """Animating filter: drop-shadow() requires the compositor to reapply the
    filter every frame as values change, preventing frame elision. Qt does not
    forward OS memory pressure to the renderer so raster tiles from the
    per-frame filter work accumulate without eviction. The drop-shadow is also
    invisible at 0% opacity, so removing it has no visual effect at the
    animation endpoints."""
    idx = _CSS.find("@keyframes note-ai-shine {")
    assert idx >= 0, "@keyframes note-ai-shine must exist"
    block = _CSS[idx : idx + 300]
    assert "filter:" not in block, (
        "@keyframes note-ai-shine must not animate filter. Animating filter "
        "prevents frame elision; Qt does not forward OS pressure so raster "
        "tiles from the per-frame filter work accumulate."
    )


# ---------------------------------------------------------------------------
# notes-drag-shimmer must use transform, not background-position
# ---------------------------------------------------------------------------

def test_notes_drag_shimmer_uses_transform_not_background_position():
    """background-position is not compositor-promoted; each frame re-rasterizes
    the gradient on every visible note card. Qt does not forward OS memory
    pressure to the renderer so raster tiles accumulate. The fix animates
    transform: translateX() instead, with overflow:hidden on the parent
    clipping the strip while it is off-screen."""
    idx = _CSS.find("@keyframes notes-drag-shimmer {")
    assert idx >= 0, "@keyframes notes-drag-shimmer must exist"
    block = _CSS[idx : idx + 300]
    assert "background-position" not in block, (
        "@keyframes notes-drag-shimmer must not animate background-position. "
        "background-position is not compositor-promoted; each frame re-rasterizes "
        "the gradient on every visible card. Use transform: translateX() instead."
    )
    assert "transform" in block, (
        "@keyframes notes-drag-shimmer must animate transform: translateX() "
        "so the compositor owns every frame"
    )

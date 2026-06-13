# PR Draft: fix/gpu-compositor-flicker

**Fork issue:** [#32](https://github.com/jdmanring/odysseus/issues/32)
**Branch:** `fix/gpu-compositor-flicker` (from `upstream-mirror`)
**Target:** `pewdiepie-archdaemon/odysseus:dev`

---

## Proposed title

`fix(css): remove backdrop-filter from opaque elements; drop saturate from cookbook animation`

---

## PR description (for upstream reviewers)

### Summary

Removes `backdrop-filter: blur()` from ten elements where the background is
already opaque or near-opaque, making the blur result invisible but keeping the
GPU compositor work. Also removes a `filter: saturate()` sequence from the
Cookbook open animation that was triggering a one-frame compositor flash on the
final frame.

Pure CSS deletion — no new properties, no visual change on any platform.

### The GPU cost of backdrop-filter on opaque backgrounds

`backdrop-filter: blur()` requires the browser to:

1. Promote the element to its own GPU compositor layer.
2. On every state change (hover in/out, show/hide, transition), sample the
   content *behind* the layer and apply a Gaussian blur kernel to it.
3. Composite the blurred result back onto the screen.

This is legitimate work when the element is actually transparent — the blurred
background is visible through it. When the background is already opaque
(`background: var(--panel)`, `rgba(0,0,0,0.8)`, etc.), the blur output is
completely hidden by the fill color. The compositor work still happens; the
result is never seen.

The cost is measurable on every platform:

- **Compositor layer promotion** holds a GPU texture allocation for the element
  for as long as `backdrop-filter` is declared, even when the element is hidden
  or has no visible blur effect.
- **Layer invalidation** on hover or visibility change re-runs the blur sample
  and composite cycle. For elements like `.sidebar` that change on every
  sidebar item hover, this fires on every mouse movement across the sidebar.
- **On Linux / NVIDIA proprietary + Wayland + QtWebEngine**: GPU layer
  invalidation can stall the Vulkan command queue (compounded by a now-fixed
  `DefaultANGLEVulkan` flag issue — see related PR). The stall produces
  black-screen flicker lasting one to several seconds on sidebar hover, dropdown
  open, and modal open. The backdrop-filter declarations on `.sidebar` and
  `.dropdown` were the direct trigger.

### Elements cleaned up

| Selector | Removed | Why invisible |
|----------|---------|---------------|
| `.sidebar` | `blur(10px)` | `background: var(--panel)` — fully opaque |
| `.dropdown` | `blur(12px)` | Solid panel background |
| Import notification banner | `blur(12px)` | Solid panel background |
| `#styled-confirm-overlay` | `blur(4px)` | `rgba(0,0,0,0.5)` — 4 px blur through 50% black is imperceptible |
| `#styled-prompt-overlay` | `blur(4px)` | Same |
| Recording indicator (×2) | `blur(10px)` | `rgba(0,0,0,0.8)` — blur invisible at 80% opacity |
| `.search-overlay` | `blur(6px)` | `rgba(0,0,0,0.6)` |
| `.popper-dropdown` | `blur(12px)` | Solid panel background |
| `.doc-suggestion-banner` | `blur(12px)` | Solid panel background |

### Cookbook animation flash

The `cookbook-modal-enter` keyframe animated `filter: saturate()` from `0.85`
at 0% to `1.05` at 65% to `none` at 100%. Transitioning `filter` from any
non-`none` value to `none` at the end of an animation triggers a compositor
layer teardown on the final frame, causing a one-frame flash (brief white or
background-colored flash) as the layer is removed and the element is composited
into the normal flow.

The opacity + transform part of the animation is unaffected and plays
identically. The saturation shift was subtle enough (±15%) that its removal
is not perceptible.

### No visual change

On standard desktop use none of these changes are visible:

- The blurred backgrounds were never visible through the opaque fills.
- The saturation animation was subtle and its absence is imperceptible.
- The only behavioral change is the elimination of GPU work and, on affected
  hardware configurations, the elimination of black-screen flicker.

### Testing

- Arch Linux, Wayland, NVIDIA GPU (proprietary drivers), QtWebEngine.
- Sidebar hover: no black-screen flicker, transitions intact.
- Downloads dropdown open: no flicker.
- Settings / Providers modal open: no flicker.
- Cookbook open: opacity + scale animation plays cleanly, no one-frame flash.
- Standard desktop (non-Qt browser): no visual difference from before.

### Related

This fix is CSS-only and independent of the companion `feat/qt-native-linux-app`
PR, which removes two problematic Chromium flags (`DefaultANGLEVulkan`,
`--enable-zero-copy`) that compounded the GPU stall on Linux/NVIDIA/Wayland.
Both fixes address the same symptom from different layers; each stands alone.

### Files changed

| File | Change |
|------|--------|
| `static/style.css` | 13 deletions — 10 `backdrop-filter` lines + 3 `filter: saturate()` lines |

---

## Filing notes

1. No upstream issue exists for this — open the PR directly.
2. Target branch: `dev` (not `main`).
3. Pure deletion — zero risk of introducing regressions. Reviewers can verify
   each removed line against the element's `background` declaration to confirm
   the blur was invisible.
4. The companion flag fix (removing `DefaultANGLEVulkan` etc.) is in
   `feat/qt-native-linux-app` — reference it as context for the severity of the
   Qt/NVIDIA/Wayland case, but make clear this CSS fix benefits all platforms.

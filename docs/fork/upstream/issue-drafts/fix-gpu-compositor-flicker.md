# Upstream Issue Draft: fix-gpu-compositor-flicker

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-gpu-compositor-flicker.md`
**Branch:** `fix/gpu-compositor-flicker`
**Type:** Bug

---

## Title

`[CSS] backdrop-filter on opaque elements causes GPU compositor flicker: black-screen stall on sidebar/dropdown/modal interactions`

---

## Body

**Install method:** Docker / manual Python / native

**OS / device:** Most visible on Linux + Wayland + NVIDIA GPU, but the unnecessary GPU work affects all platforms

**Browser (if applicable):** Any Chromium-based renderer (including QtWebEngine)

**Steps to Reproduce:**
1. Open the app.
2. Hover over items in the sidebar (session list, navigation items).
3. Open a dropdown or modal.

**Expected:** Smooth transitions with no visual glitching.

**Actual:** On Linux/Wayland/NVIDIA, hovering sidebar items or opening dropdowns produces black-screen flicker lasting one to several seconds. On all platforms, unnecessary GPU compositor layer work is triggered on every sidebar hover, dropdown open, and modal open.

**Logs / Error Output:**
No error logged; symptom is visible rendering glitch (black screen stall) on NVIDIA + Wayland, and invisible but measurable GPU overhead on other platforms.

**Additional context:** `backdrop-filter: blur()` is applied to ten elements (`.sidebar`, `.dropdown`, `.search-overlay`, overlays, recording indicators, etc.) whose backgrounds are already fully or near-fully opaque. When the background is opaque, the blur result is completely hidden by the fill color, but the GPU compositor work still runs. This includes:

- Promoting each element to its own GPU compositor layer (holding a GPU texture allocation permanently)
- Re-running the blur sample and composite cycle on every state change (hover, show/hide, transition)

For `.sidebar` specifically, this fires on every mouse movement across the sidebar. On Linux + NVIDIA + Wayland + QtWebEngine, GPU layer invalidation can stall the Vulkan command queue, producing the black-screen flicker.

Additionally, the `cookbook-modal-enter` keyframe animates `filter: saturate()` from a non-`none` value to `none` at 100%, which triggers a compositor layer teardown on the final frame, causing a one-frame flash as the layer is removed.

The fix is pure CSS deletion: removing `backdrop-filter` from elements where it has no visible effect, and removing the `saturate` step from the Cookbook animation. No visual change on any platform.

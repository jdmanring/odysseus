# Upstream Issue Draft: fix-research-orbit-quiescence

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-research-orbit-quiescence.md`
**Branch:** `fix/research-orbit-quiescence`
**Type:** Performance

---

## Title

`perf(research): orbit ring repaints the whole pane every frame while idle (perpetual conic-gradient + mask raster)`

---

## Body

**Area:** UI / Research panel / performance

**Problem**

The Research pane's animated accent ring is a perpetual per-frame **paint** producer.
`static/js/research/panel.js:_ensureOrbit()` runs a `requestAnimationFrame` loop that rewrites
`--research-orbit-angle` **every frame while the panel is open** — by design even when idle with
no research job running. That variable feeds `.research-pane::after`, a `conic-gradient(from
var(--research-orbit-angle), …)` over the full pane masked (`mask-composite: exclude`) to a 2px
ring. So every frame the browser recomputes a full-pane conic-gradient + re-applies the mask +
re-rasterizes — 60fps, forever.

On a healthy GPU this is steady background cost; under software rendering (e.g. a GPU-driver
failure → llvmpipe) a handful of such producers can saturate the CPU and freeze the UI.

**Expected:** the ring animates only while it's conveying something (an active research job),
and is quiescent otherwise.

**Fix:** drive the loop only while a job is active; pause on `document.hidden` /
`prefers-reduced-motion`; throttle the repaint. When idle, hold a static angle (still visible).

**Affected:** `static/js/research/panel.js`.

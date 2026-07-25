# PR Draft: perf(ui): rAF-coalesced autoResize, eliminate typing layout thrash

**Branch:** `perf/smooth-typing`
**Issue:** jdmanring/odysseus#81
**Base:** `upstream-mirror` (latest upstream commit)

---

## Problem

`autoResize` in `static/js/ui.js` is wired to the textarea's `input` event and fires on
every keystroke. The implementation uses a hidden clone to measure content height:

1. `getComputedStyle(textarea).lineHeight`: forces style recalculation
2. `textarea.offsetWidth`: forces layout reflow
3. `clone.scrollHeight`: forces a second layout reflow

This produces **2 forced DOM layout reflows per keystroke**. At typing speeds of 8+ chars/sec
that is 16+ forced layout reflows per second. In embedded Chromium environments (Electron,
PyQt WebEngine, native wrappers) where the rendering pipeline has more overhead than a
bare browser, this accumulates into perceptible input jank.

## Fix

Replace the clone-based measurement with a `requestAnimationFrame`-coalesced
`height: 'auto'` + `textarea.scrollHeight` approach:

```javascript
export function autoResize(textarea) {
  if (textarea._arRafId) return;
  textarea._arRafId = requestAnimationFrame(() => {
    textarea._arRafId = null;
    const lineHeight = parseInt(getComputedStyle(textarea).lineHeight) || 20;
    const maxHeight = window.innerWidth <= 768 ? 150 : lineHeight * 8;
    textarea.style.height = 'auto';
    const newHeight = Math.min(Math.max(textarea.scrollHeight, lineHeight), maxHeight);
    textarea.style.height = newHeight + 'px';
    textarea.style.overflow = newHeight >= maxHeight ? 'auto' : 'hidden';
  });
}
```

**Result:** N keystrokes arriving within a single 16 ms animation frame collapse to exactly
one layout reflow (the rAF callback fires once; the `_arRafId` guard drops subsequent
calls). A single `getComputedStyle` + `scrollHeight` read replaces the two-read clone
approach.

**Why `height: 'auto'` is safe inside rAF:** setting `height: 'auto'` releases the fixed
pixel height so the browser computes the natural content height. Reading `scrollHeight`
immediately after forces one layout pass. Setting the final `height: Npx` in the same
script execution queues a second style write that resolves at paint. Both mutations are
batched in a single frame, so there is no visible flicker.

**Clone cleanup:** the `_resizeClone`, `cloneNode`, and `offsetWidth` code is removed
entirely. Existing in-DOM clones from sessions that ran the old code are hidden/positioned
off-screen and are removed on page reload.

## Files changed

- `static/js/ui.js`: `autoResize` rewrite (−25 +16 lines)
- `tests/test_ui_auto_resize_js.py`: new file, 5 static-analysis tests

## Tests

5 new static-analysis tests in `tests/test_ui_auto_resize_js.py`:
- `test_auto_resize_uses_raf_coalescing`: `requestAnimationFrame` present
- `test_auto_resize_height_auto_for_measurement`: `'auto'` height reset present
- `test_auto_resize_reads_scroll_height`: `scrollHeight` read present
- `test_auto_resize_no_clone_creation`: `cloneNode` absent (old approach removed)
- `test_auto_resize_sets_overflow`: `overflow` property set

## Embedding context

This fix benefits all Odysseus deployments, not just embedded wrappers. Repeated forced
layout reflows are wasteful in any browser, but the impact is most visible in embedded
Chromium builds where the rendering pipeline has higher per-reflow overhead.

The `requestAnimationFrame`-coalesce pattern is standard for input-driven layout work and
is the same approach used elsewhere in the codebase (see `_renderRafId` in streaming).

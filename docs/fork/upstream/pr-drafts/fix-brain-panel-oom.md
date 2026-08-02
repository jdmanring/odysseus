# PR Draft: fix/brain-panel-oom

**Branch**: `fix/brain-panel-oom` (from `upstream-mirror`)
**Issue**: jdmanring/odysseus-workbench#TBD (file before submitting)
**Base**: `upstream-mirror` (latest upstream commit)
**Status**: Ready to file

---

## Title

`fix(css): eliminate raster-tile accumulation from Brain and Notes animations`

---

## Summary

Four CSS animations in the Brain and Notes panels produce unbounded raster-tile growth in Qt-embedded Chromium. Qt does not forward OS memory pressure to the renderer, so the compositor's tile manager never receives eviction signals. Any animation that forces per-frame main-thread painting deposits tiles that accumulate for the lifetime of the session.

This PR replaces each main-thread animation pattern with a compositor-promoted equivalent.

---

## Fix A: @property --sweep (memory-synapse-sweep)

**File**: `static/style.css`

**Before**: `@property --sweep { syntax: '<percentage>'; }` animated the gradient stop positions in `#memory-list .memory-item::after`. Typed registered custom properties participate in computed-value cascading; every frame `--sweep` changed forced style recalculation for every visible memory item. The `-webkit-mask` on the same element added a second compositor pass per item per frame.

The hover rule set `animation: none` to suppress the sweep, destroying the promoted layer. It was recreated on mouse-leave, producing a gray-frame flash.

**After**: Animate `transform: translateX()` instead. The gradient strip starts off-screen left (`inset: 0 0 0 -40%; width: 40%`) and sweeps right in the first ~12% of the cycle, then parks off-screen via `overflow: hidden` on the parent. No layer teardown during the idle phase. Hover uses `opacity: 0` instead of `animation: none`; the promoted layer stays up and no flash occurs.

Note: `will-change: transform` is intentionally absent from `#memory-list .memory-item::after`. A continuously running `transform` animation auto-promotes the composited layer; adding `will-change` is redundant for visible items and forces GPU backing texture allocation for off-screen items throughout the scrollable list. The browser promotes the layer lazily when an item is animating, which is the correct behavior for a scroll container.

---

## Fix B: filter: drop-shadow() (note-ai-shine)

**File**: `static/style.css`

**Before**: `@keyframes note-ai-shine` animated `filter: drop-shadow()` on `.note-card-ai-chip svg`. Animating `filter` requires the compositor to reapply it every frame as values change, preventing frame elision. The drop-shadow at `0%` and `100%` (where opacity is 0.85) is effectively invisible at those endpoints.

**After**: Remove `filter` from the keyframe; animate `opacity` only. `opacity` is compositor-promoted. No visual change at the animation endpoints.

---

## Fix C: animation: none on hover/focus (notes-quick-pulse)

**File**: `static/style.css`

**Before**: `.notes-quick-add:hover` and `.notes-quick-add:focus-within` both set `animation: none`, destroying the compositor layer promoted for `notes-quick-pulse`. The layer was recreated on mouse-leave and focus-leave, producing a flash on every interaction.

**After**: Use `animation-play-state: paused` instead. The animation freezes at the current keyframe without removing the promoted layer. No flash.

---

## Fix D: background-position (notes-drag-shimmer)

**File**: `static/style.css`

**Before**: `@keyframes notes-drag-shimmer` animated `background-position` across a 250%-wide gradient on every `.note-card::after` during drag. `background-position` is not compositor-promoted; each frame re-rasterizes the gradient on every visible card. With 30 cards visible that is 30 gradient repaints per frame.

**After**: Same approach as Fix A. The gradient strip starts off-screen left (`inset: 0 0 0 -60%; width: 60%`), sweeps right via `transform: translateX()`, and parks off-screen via `overflow: hidden` on the parent. `will-change: transform` pre-promotes the layer.

---

## Files changed

- `static/style.css`: all four fixes
- `tests/test_brain_panel_oom_css.py`: new file, 13 regression tests

---

## Tests

13 static-analysis tests in `tests/test_brain_panel_oom_css.py`:

Pattern A:
- `@property --sweep {` declaration absent
- `syntax: '<percentage>'` absent
- memory-synapse-sweep keyframe animates `transform`
- memory-synapse-sweep keyframe does not set `--sweep`
- memory-synapse-sweep keyframe does not set `background-position`
- hover rule uses `opacity: 0`, not `animation: none`
- `-webkit-mask` absent from `::after` block
- `will-change: transform` present in `::after` block
- `prefers-reduced-motion` still suppresses the animation

Pattern C:
- `.notes-quick-add:hover` uses `animation-play-state: paused`, not `animation: none`
- `.notes-quick-add:focus-within` uses `animation-play-state: paused`, not `animation: none`

Pattern B:
- `@keyframes note-ai-shine` does not contain `filter:`

Pattern D:
- `@keyframes notes-drag-shimmer` does not contain `background-position`
- `@keyframes notes-drag-shimmer` contains `transform`

---

## Manual verification

1. Open the Brain panel with 10+ memories. Let it idle for 60 seconds. RSS should remain stable.
2. Hover over memory items. No gray flash on mouse-over or mouse-leave.
3. Open the Notes panel with 10+ cards. Enable drag mode. RSS should remain stable.
4. Hover over and click into the quick-add input. No flash on hover or focus transitions.
5. Run `python -m pytest tests/test_brain_panel_oom_css.py -v`; 13 passed.

---

## Notes

- All four patterns share the same root cause: Qt does not forward OS memory pressure to the embedded Chromium renderer, so raster tiles from per-frame repaints accumulate without eviction. The fix in every case is to use only compositor-promoted properties (`transform`, `opacity`) so the main thread is not involved after the first paint.
- `prefers-reduced-motion` continues to suppress the memory sweep animation (already worked; verified by test).
- The `--sweep` custom property and its `@property` registration are removed entirely. Any future animation on these elements should use `transform` or `opacity`.

# PR Draft — fix/memory-list-scroll-oom

**Branch**: `fix/memory-list-scroll-oom` (from `upstream-mirror`)
**Issue**: jdmanring/odysseus#88 (file upstream issue before submitting)
**Base**: `upstream-mirror` (latest upstream commit)
**Status**: Ready to file

---

## Title

`fix(css): override transition: all in #memory-list to stop scroll-hover raster-tile buildup`

---

## Summary

The base `.memory-item` class applies `transition: all 0.15s`. In the Brain memory list, as the cursor moves over items during scroll each item cycles through enter-hover and leave-hover, animating `background` and `border-color`. Both properties require main-thread painting. At 60 fps with a 0.15 s transition, each hover entry/exit deposits approximately 9 frames of raster tiles per item. Qt does not forward OS memory pressure to the embedded Chromium renderer; the compositor's tile manager never receives eviction signals, so these tiles accumulate without bound. Around 1 GB of growth is reproducible from repeated scroll passes over a list of 20+ memories.

---

## Fix

**File**: `static/style.css`

**Before**: `#memory-list .memory-item` inherited `transition: all 0.15s` from the base class with no override.

**After**: Added `transition: opacity 0.15s` to `#memory-list .memory-item`. This overrides `transition: all` in the list context, limiting animated changes to `opacity` — the only compositor-promoted property involved in hover rules in this context. Background and border-color changes take effect immediately (no transition) instead of depositing raster tiles per frame.

The base `.memory-item` rule retains `transition: all 0.15s` for use in other contexts (task list, skill rows, etc.) where the list is not a scroll container receiving continuous hover events.

---

## Related: will-change on ::after (also in this branch set)

A companion change on `fix/brain-panel-oom` removes `will-change: transform` from `#memory-list .memory-item::after`. A continuously running `transform` animation auto-promotes the composited layer; the `will-change` hint is redundant for visible items and forces GPU backing texture allocation for off-screen items in the scrollable list. This is a separate concern from the transition issue above and is tracked on the `fix/brain-panel-oom` branch.

---

## Files changed

- `static/style.css` — `transition: opacity 0.15s` override in `#memory-list .memory-item`
- `tests/test_memory_list_scroll_oom_css.py` — new file, 4 regression tests

---

## Tests

4 static-analysis tests in `tests/test_memory_list_scroll_oom_css.py`:

- `#memory-list .memory-item` block contains `transition: opacity`
- Base `.memory-item` still has `transition: all` (non-list contexts unaffected)
- `#memory-list .memory-item` block does not contain `transition: all` (comment-stripped check)
- `#memory-list .memory-item` block does not contain `transition: background` or `transition: border`

---

## Manual verification

1. Open the Brain panel with 20+ memories.
2. Move the cursor slowly up and down over the list for 60 seconds.
3. RSS should remain stable. Before this fix, growth of several hundred MB is observable in that time.
4. Hover effects (background and border change) still occur immediately on mouse-over — the transition is gone but the visual state change is not.
5. Run `python -m pytest tests/test_memory_list_scroll_oom_css.py -v` — 4 passed.

---

## Notes

- The root cause is shared with the fixes in `fix/brain-panel-oom`: Qt does not forward OS memory pressure to the renderer, so raster tiles from main-thread paint operations accumulate indefinitely. The fix is the same: use only compositor-promoted properties (`opacity`, `transform`) for animated state changes in the list context.
- Hover state changes in `#memory-list` (`background` and `border-color`) are instantaneous after this fix. The animated sweep on `::after` remains the primary hover-interactive visual.

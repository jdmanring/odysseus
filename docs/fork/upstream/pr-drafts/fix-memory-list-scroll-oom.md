# PR Draft — fix/memory-list-scroll-oom

**Branch**: `fix/memory-list-scroll-oom` (from `upstream-mirror`)
**Issue**: jdmanring/odysseus#88 (file upstream issue before submitting)
**Base**: `upstream-mirror` (latest upstream commit)
**Status**: Ready to file

---

## Title

`fix(css): eliminate hover raster-tile accumulation in Brain memory list`

---

## Summary

Moving the cursor over the Brain memory list causes continuous RSS growth — up to ~1 GB from repeated passes over 20+ items. Two root causes combine: an inherited `transition: all` that generates ~9 raster frames per hover event, and the hover paint itself that generates 1 raster frame per hover entry/exit even without a transition. Qt-embedded Chromium never receives OS memory pressure signals, so `cc::TileManager` never evicts accumulated tiles. Memory returns only when the panel is hidden and the compositor discards off-screen layer tiles.

---

## Fix

Two phases, both in `static/style.css`.

### Phase 1: transition animation (commit `f43c69c2`)

The base `.memory-item` carries `transition: all 0.15s`. In the Brain memory list, hover entry/exit animates `background` and `border-color` — neither is compositor-promoted. Each transition deposits ~9 raster tile frames at 60 fps.

Added `transition: opacity 0.15s` to `#memory-list .memory-item`, overriding `transition: all` in the list context. Base class retains `transition: all` for other contexts (task list, skill rows) that are not continuous-hover scroll containers.

### Phase 2: hover paint (commit `90e21d62`)

Even with no transition, the base `.memory-item:hover` rule changes `background` and `border-color` on every hover entry/exit, generating 1 raster frame each time. Three changes working together:

**`isolation: isolate`** on `#memory-list .memory-item` creates a CSS stacking context (no GPU memory cost) so the `::before` overlay can sit at `z-index: -1` above the item's own background layer but below static content children and the `::after` sweep animation.

**`::before` hover overlay** with `opacity: 0 → 1` on hover. Opacity is compositor-promoted — the GPU handles the fade without rasterizing new tiles. Background is `color-mix(in srgb, var(--fg) 2%, transparent)`; alpha-composited over the base 3% it produces ≈5% total, matching the original hover background exactly.

**`#memory-list .memory-item:hover` override** sets `background` and `border-color` to the same computed values as the non-hover state. Chromium's paint-invalidation check skips repaint when computed values are unchanged — zero raster tiles generated on hover entry/exit.

Reduced-motion block updated to disable the `::before` transition (`transition: none`).

---

## Related: will-change on ::after (companion branch)

`fix/brain-panel-oom` removes `will-change: transform` from `#memory-list .memory-item::after`. A continuously running `transform` animation is self-promoting; the `will-change` hint is redundant for visible items and forces GPU backing texture allocation for off-screen items. Separate branch, same root cause.

---

## Files changed

- `static/style.css` — phase 1 transition override; phase 2 `isolation`, `::before` overlay, hover suppression, reduced-motion update
- `tests/test_memory_list_scroll_oom_css.py` — 13 regression tests (4 phase 1 + 9 phase 2)

---

## Tests

13 static-analysis tests in `tests/test_memory_list_scroll_oom_css.py`:

**Phase 1 (transition):**
- `#memory-list .memory-item` block contains `transition: opacity`
- Base `.memory-item` still has `transition: all` (non-list contexts unaffected)
- `#memory-list .memory-item` block does not contain `transition: all` (comment-stripped)
- `#memory-list .memory-item` block has no `transition: background` or `transition: border`

**Phase 2 (hover paint):**
- `isolation: isolate` present in `#memory-list .memory-item`
- `#memory-list .memory-item::before` block exists
- `::before` has `opacity: 0`, `transition: opacity`, `z-index: -1`, `pointer-events: none`
- `#memory-list .memory-item:hover::before` has `opacity: 1`
- `#memory-list .memory-item:hover` contains background at non-hover computed value
- `#memory-list .memory-item:hover` contains `border-color: var(--border)`

---

## Manual verification

1. Open the Brain panel with 20+ memories.
2. Enable DevTools → Rendering → Paint flashing (green flash = repaint). Hover over list items — **no green flash** confirms zero paint on hover entry/exit.
3. Move the cursor up and down over the list for 60 seconds. Check RSS via DevTools Task Manager or `ps aux`. Growth should be flat.
4. Confirm hover highlight still appears (subtle background tint on hover items — visually identical to before).
5. Confirm sweep animation still appears on non-hovered items and suppresses on hover.
6. `python -m pytest tests/test_memory_list_scroll_oom_css.py -v` — 13 passed.

---

## Notes

- Qt does not forward OS memory pressure to the embedded Chromium renderer. The `cc::TileManager` relies on these signals for tile eviction; without them, raster tiles from main-thread paint accumulate without bound. The only correct fix is to eliminate the paints, not to try to trigger eviction.
- The `::before` opacity approach is the standard technique for hover highlights in paint-sensitive contexts. It moves the entire hover visual onto the GPU compositing layer.
- Chromium's paint-skip optimization (comparing computed values before invalidating) is well-established and documented in the Blink rendering pipeline. Setting hover properties to their non-hover values is a reliable way to prevent paint from the base hover rule.

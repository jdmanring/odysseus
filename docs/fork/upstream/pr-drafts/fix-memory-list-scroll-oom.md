# PR Draft: fix/memory-list-scroll-oom

**Branch**: `fix/memory-list-scroll-oom` (from `upstream-mirror`)
**Issue**: jdmanring/odysseus#88 (file upstream issue before submitting)
**Base**: `upstream-mirror` (latest upstream commit)
**Status**: Ready to file

---

## Title

`fix(css): eliminate hover raster-tile accumulation in Brain memory list`

---

## Summary

Moving the cursor over the Brain memory list causes continuous RSS growth: up to ~1 GB from repeated passes over 20+ items. Three root causes combine: an inherited `transition: all` that generates ~9 raster frames per hover event; the hover paint itself that generates 1 frame per hover entry/exit; and the opacity `0->1->0` cycle on action buttons and the menu button that creates and destroys compositor layers on each hover, leaving orphaned raster tiles in the tile cache. Qt-embedded Chromium never receives OS memory pressure signals, so `cc::TileManager` never evicts accumulated tiles. Memory returns only when the panel is hidden and the compositor discards off-screen layer tiles.

---

## Fix

Three phases, all in `static/style.css`.

### Phase 1: transition animation (commit `f43c69c2`)

The base `.memory-item` carries `transition: all 0.15s`. In the Brain memory list, hover entry/exit animates `background` and `border-color`: neither is compositor-promoted. Each transition deposits ~9 raster tile frames at 60 fps.

Added `transition: opacity 0.15s` to `#memory-list .memory-item`, overriding `transition: all` in the list context. Base class retains `transition: all` for other contexts (task list, skill rows) that are not continuous-hover scroll containers.

### Phase 2: hover paint suppression (commit `90e21d62`)

Even with no transition, the base `.memory-item:hover` rule changes `background` and `border-color` on every hover entry/exit, generating 1 raster frame each time.

`#memory-list .memory-item:hover` overrides both properties to the same computed values as the non-hover state (`background: color-mix(in srgb, var(--fg) 3%, transparent); border-color: var(--border)`). Chromium's paint-invalidation check compares computed values before issuing a repaint: when values are unchanged, repaint is skipped entirely.

### Phase 3: eliminate action-button compositor layer cycling (commit `ca2bcc27`)

The base rules hide `.memory-item-actions` and `.memory-menu-btn` at `opacity: 0` and reveal them via `:hover` at `opacity: 1`. Each hover entry/exit is an opacity `0->1->0` cycle. Without a persistent compositor layer, each cycle:
1. Creates a compositor layer for the element (rasterizes it: deposits tiles)
2. Transitions opacity to 1 (compositor-only)
3. Transitions back to 0 (compositor-only)
4. Destroys the compositor layer

In Qt-embedded Chromium, `cc::TileManager` never receives `OnMemoryPressure` calls from the OS, so the orphaned tiles from step 4 accumulate in the tile cache on every hover cycle over every item.

`will-change: opacity` was attempted first but did not prevent layer destruction in this Qt Chromium build: the engine still destroys compositor layers when opacity returns to `0`.

**Fix:** In `#memory-list`, override `.memory-item-actions` to `opacity: 1; transition: none` and `.memory-menu-btn` to `opacity: 1`. The base `:hover` rules also set `opacity: 1`, identical computed values at all times. Chromium detects no change and skips rasterization on every hover cycle. Zero tile allocation per hover after initial load.

The action buttons and menu button are always visible in the list context. The `::after` sweep animation (self-promoted via its active `transform` animation) continues to suppress on hover via `opacity: 0`; this is compositor-only and does not generate tiles.

---

## Related: ::after animation OOM fix (companion branch)

`fix/brain-panel-oom` replaces the `@property --sweep` gradient animation with `transform: translateX()` in `::after`. A continuously running `@property` typed custom property fires style recalculation for every item every frame. Separate branch, same root cause.

---

## Files changed

- `static/style.css`: in the `#memory-list` context, `transition: all` is overridden with a compositor-promoted `transition: opacity` (the retained fix). An earlier paint-suppression approach (hover background/border suppression, always-visible action and menu buttons) was reverted to preserve hover UX, now that the tile budget and content-visibility work bound the memory.
- `tests/test_memory_list_scroll_oom_css.py`: 8 regression tests (NEW FILE)

---

## Tests

8 static-analysis tests in `tests/test_memory_list_scroll_oom_css.py`:

**Transition override (the retained fix):**
- `#memory-list .memory-item` overrides `transition: all` with `transition: opacity`.
- Base `.memory-item` still has `transition: all` (non-list contexts unaffected).
- The `#memory-list .memory-item` block does not contain `transition: all`.
- The override is compositor-promoted (opacity, not `transition: background`/`border`).
- Regression guard: the `#memory-list .memory-item` block does not re-add `isolation: isolate`.

**Reverted-suppression guards:** the earlier paint-suppression approach was backed out;
these assert it stays out, so hover UX is preserved:
- No hover background/border suppression on `#memory-list .memory-item:hover`.
- No always-visible `opacity: 1` override on `#memory-list .memory-item-actions`.
- No always-visible `opacity: 1` override on `#memory-list .memory-menu-btn`.

---

## Manual verification

1. Open the Brain panel with 20+ memories.
2. Enable DevTools -> Rendering -> Paint flashing (green flash = repaint). Hover over list items: **no green flash** confirms zero paint on hover entry/exit.
3. Move the cursor up and down over the list for 60 seconds, including repeated passes over the same items. Check RSS via `ps aux` or DevTools Task Manager. Growth should be flat.
4. Confirm action buttons and the menu button reveal on hover normally (the earlier
   always-visible behaviour was reverted).
5. Confirm the sweep animation still appears on non-hovered items and suppresses on hover.
6. `python -m pytest tests/test_memory_list_scroll_oom_css.py -v` (8 passed).

---

## Notes

- Qt does not forward OS memory pressure to the embedded Chromium renderer. The `cc::TileManager` relies on these signals for tile eviction; without them, raster tiles accumulate without bound. The only correct fix is to eliminate the paints, not to try to trigger eviction.
- Chromium's paint-skip optimization (comparing computed values before invalidating) is well-established in the Blink rendering pipeline. Setting hover properties to their non-hover values reliably prevents paint from the base hover rule.
- `will-change: opacity` was attempted but proved insufficient: Qt's embedded Chromium destroys compositor layers when `opacity` returns to `0` even with `will-change: opacity` present, leaving orphaned tiles on each hover cycle. Making elements always-visible removes the `opacity: 0` state entirely; no layer is ever destroyed.

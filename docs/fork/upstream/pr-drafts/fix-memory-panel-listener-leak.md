# PR Draft: fix/memory-panel-listener-leak

**Branch**: `fix/memory-panel-listener-leak` (from `upstream-mirror`)
**Issue**: jdmanring/odysseus#89 (file upstream issue before submitting)
**Base**: `upstream-mirror` (latest upstream commit)
**Status**: Ready to file

---

## Title

`fix(memory): eliminate event listener accumulation and raster-tile retention in Brain panel`

---

## Summary

Three distinct sources cause ~956 MiB of permanent RSS growth in the Brain memory list:

1. **document.addEventListener accumulation**: `renderMemoryList()` added one non-removing document-level click listener per memory item per render call. 50 items x 10 renders = 500 persistent listeners on `document`, each holding a closure over a dropdown DOM element. When `innerHTML = ''` cleared the list, those dropdown closures blocked Oilpan from collecting the old nodes.

2. **No cross-render listener cleanup**: Item-level listeners (checkbox, pointer events, menu button, etc.) were registered with no corresponding removal. In Qt-embedded Chromium, which never receives OS memory pressure signals, Oilpan's major GC cycle runs rarely, so closure captures (memory IDs, dropdown refs) accumulated without bound across render passes.

3. **Animation continues when panel is hidden**: The `::after` sweep animation on `.memory-item` ran continuously even when `#memory-modal` had the `.hidden` class, maintaining compositor tile allocations for an invisible list.

---

## Fix

### static/js/memory.js

**AbortController per render pass:**

Module-level:
```javascript
let _listAbortCtrl = null;
let _activeDropdown = null;

function _closeActiveDropdown() {
  if (_activeDropdown && _activeDropdown.parentNode) _activeDropdown.remove();
  _activeDropdown = null;
}
```

Start of `renderMemoryList()` (before `innerHTML = ''`):
```javascript
if (_listAbortCtrl) _listAbortCtrl.abort();
_closeActiveDropdown();
_listAbortCtrl = new AbortController();
const _sig = _listAbortCtrl.signal;
```

All item-level `addEventListener` calls updated to carry `{ signal: _sig }`. When the controller is aborted at the start of the next render, all registered listeners are released synchronously, the old-school equivalent of freeing before reallocating.

**document.addEventListener fix:**

Moved from the `forEach` body (one per item per render) to inside the `menuBtn` click handler (one per open dropdown). Changed `{ once: false }` to `{ once: true, signal: _sig }`: two removal paths: one from the user's next click, one from the abort signal.

```javascript
menuBtn.addEventListener('click', (e) => {
  // ... build and show dropdown ...
  _activeDropdown = dropdown;
  document.addEventListener('click', () => {
    if (dropdown.parentNode) dropdown.remove();
    _activeDropdown = null;
  }, { once: true, signal: _sig });
}, { signal: _sig });
```

**Panel close cleanup (MutationObserver):**

Observes `attributeFilter: ['class']` on `#memory-modal`. When the panel gains `.hidden`, closes any open dropdown and triggers `gc()` (feature-detected; only available with `--js-flags=--expose-gc`). Does NOT abort `_listAbortCtrl` on close; that abort belongs at the start of the next `renderMemoryList()` call, immediately before `innerHTML` is cleared. Aborting on close would leave DOM items with dead handlers until the next memory-refresh event.

**odysseus:modal-closed event (modalManager.js):**

Added `_emitModalClosed(id, modal)` mirroring the existing `_emitModalOpened`. Fired in the MutationObserver when visibility transitions from true to false.

### static/style.css

```css
#memory-modal.hidden #memory-list .memory-item::after {
  animation-play-state: paused;
}
```

Halts the `::after` sweep animation when the Brain panel is hidden. No JavaScript required; resumes automatically when `.hidden` is removed.

---

## Files changed

- `static/js/memory.js`: AbortController pattern, document listener fix, panel close cleanup
- `static/js/modalManager.js`: `odysseus:modal-closed` event added
- `static/style.css`: `animation-play-state: paused` when modal hidden

---

## Tests

14 static-analysis tests in `tests/test_memory_panel_listener_leak.py`:

- `_listAbortCtrl` module-level declaration present
- `_listAbortCtrl.abort()` called at the start of `renderMemoryList()` (before re-render)
- `new AbortController()` created each render pass
- `_sig = _listAbortCtrl.signal` extracted for listener registration
- `{ once: true }` used on document click listener; `{ once: false }` absent
- document click listener is inside the `menuBtn` click handler (not at forEach level)
- document click listener carries `{ signal: _sig }`
- `_memModal.classList.contains('hidden')` observer present
- modal close handler does NOT call `_listAbortCtrl.abort()` (abort at render time, not close time; prevents dead-handler regression)
- `typeof gc` check present in modal close handler
- `_closeActiveDropdown()` called in modal close handler
- `odysseus:modal-closed` present in `modalManager.js`
- `_emitModalClosed` called on `!vis && _mmAutoStackLast` transition
- CSS `animation-play-state: paused` rule present for hidden modal

---

## Manual verification

1. Open DevTools -> Memory tab. Take a heap snapshot.
2. Open the Brain panel with 20+ memories.
3. Open and close item menus, change filters, hover over items. Take a second snapshot.
4. Compare: live document click listeners should not grow proportionally with memories or render counts.
5. Close the Brain panel. Observe `[memory] panel close: dropdown cleared, GC queued` in console.
6. `python -m pytest tests/test_memory_panel_listener_leak.py -v`: 14 passed.

---

## Notes

- The root cause of listener non-removal is that `document.addEventListener` without `once: true` or a corresponding `removeEventListener` accumulates indefinitely. Moving it inside the `menuBtn` handler ensures it is registered only when a dropdown is opened, and removed on the first subsequent document click.
- Qt-embedded Chromium never receives OS memory pressure signals, so Oilpan's major GC cycle is never triggered by the OS. The `gc()` hint after panel close is the only way to request collection promptly in this environment.
- Companion fixes: `fix/brain-panel-oom` (CSS animation patterns), `fix/memory-list-scroll-oom` (scroll-hover raster tiles) address the CSS side; this branch addresses the JavaScript listener side.

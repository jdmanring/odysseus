# PR Draft: fix/continue-btn-weakref → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/continue-btn-weakref`
**Issue:** [#78](https://github.com/jdmanring/odysseus/issues/78) (fork tracking)
**Status:** Ready to file

---

## Title

`fix(chat): use WeakRef for continue-button holder captures to prevent GC retention`

---

## Summary

### Problem

Three "Continue" buttons in `chat.js` capture the message holder element directly
in their click handler closures:

1. **Interrupted-message button** (inside the holder's subtree, ~line 375)
2. **Step-limit button** — appended to `_chatBox`, not the holder's subtree (~line 1898)
3. **Catch-block interrupted button** (inside the holder's subtree, ~line 2959)

Site 2 is a confirmed GC retention bug: the step-limit `contBtn` is appended to
`_chatBox`, which stays live in the DOM indefinitely. Its event listener is therefore
a GC root. The closure captures `currentHolder` directly, holding the entire evicted
holder subtree in memory for the lifetime of the session.

After `chatHistory.js` Phase 2 evicts the holder (removes it from the DOM), the
holder can never be collected because the `_chatBox` event listener holds a strong
reference to it. In a long session with multiple agent steps, each round's holder
is retained, compounding the memory growth measured in the OOM investigation.

Sites 1 and 3 are inside the holder's subtree. Cycle-tracing GC can collect them
in principle (no external root), but making the pattern explicit and consistent is
correct defensive practice.

### Fix

Replace the direct holder capture with a `WeakRef` at all three sites. The click
handler dereferences the WeakRef at call time and returns early if the holder has
been collected:

```javascript
// Site 2 (confirmed GC root — step-limit button in _chatBox):
const _holderRef = new WeakRef(currentHolder);
contBtn.addEventListener('click', () => {
  const _holder = _holderRef.deref();
  if (!_holder) return; // evicted — ignore click
  note.remove();
  _hideUserBubble = true;
  _pendingContinue = _holder;
  ...
});
```

`WeakRef` does not prevent GC of the referent. Once the holder is evicted and
collected, `deref()` returns `undefined`, the click handler returns without side
effects, and the closure itself becomes collectable as soon as the button is removed
from `_chatBox`.

### Verification

CDP `Memory.getDOMCounters` `jsEventListeners` count measured before and after a
Phase 2 eviction batch (via `_cdp_audit_listeners()` in `qt_wrapper.py`). Expected
result after this fix: `delta ≈ n_evicted` (one listener freed per evicted holder
with a continue button), versus near-zero delta before the fix.

---

## Files changed

- `static/js/chat.js` — WeakRef at three continue-button handler sites

## Tests

9 static-analysis tests in `tests/test_chat_continue_btn_js.py`:
- All three sites create a `WeakRef`
- All three sites call `.deref()`
- All three sites guard `_pendingContinue` assignment behind the null check

## Notes

- Depends on `fix/dom-oom-virtualization` for the Phase 2 eviction mechanism
  that makes this observable; the WeakRef fix is independently correct without it.
- Site 2 is the only confirmed retention path; sites 1 and 3 are defensive.

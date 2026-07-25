# Upstream Issue Draft: fix-continue-btn-weakref

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-continue-btn-weakref.md`
**Branch:** `fix/continue-btn-weakref`
**Type:** Bug

---

## Title

`[Memory] Step-limit "Continue" button retains evicted message holder in memory indefinitely`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Summary:**

After `chatHistory.js` Phase 2 eviction removes old message holders from the DOM, the step-limit "Continue" button keeps a strong reference to each evicted holder for the entire session lifetime, preventing GC from collecting them.

**Root cause:**

Three "Continue" buttons in `chat.js` capture `currentHolder` in their click handler closures. The step-limit button (site 2) is appended to `_chatBox`, which stays live in the DOM indefinitely:

```javascript
// Site 2 — appended to _chatBox, always live:
contBtn.addEventListener('click', () => {
  note.remove();
  _hideUserBubble = true;
  _pendingContinue = currentHolder;  // ← strong reference
  ...
});
```

Once `chatHistory.js` Phase 2 evicts `currentHolder` (removes it from the DOM), the event listener on `_chatBox` is a GC root. The closure holds a strong reference to the evicted holder, preventing GC from collecting it. In a long session with many agent steps, each round's holder is retained for the session lifetime.

**Impact:**

In a long session with 20 agent rounds that each trigger the step limit (common in deep research sessions), 20 full message holder subtrees are permanently retained in old-gen memory, each containing the full rendered response content. This directly compounds the OOM growth measured in long sessions.

**Steps to observe:**

1. Start a long agent session until Phase 2 eviction fires.
2. After eviction, open DevTools -> Memory and take a heap snapshot.
3. Search for `HTMLDivElement` nodes with the `message-holder` or equivalent class that are detached (not in the DOM but referenced by a live closure). With this bug, these count equals the number of step-limit Continue buttons that were created and not clicked.

**Expected:** After Phase 2 eviction, the evicted holders are collectable. The step-limit button's click handler should hold a `WeakRef` and dereference at call time, returning early if the holder has been collected.

**Affected file:** `static/js/chat.js`: three `contBtn.addEventListener('click', ...)` sites

# PR Draft: fix/tool-bubble-timer-leak → pewdiepie-archdaemon/odysseus:dev

**Branch:** `fix/tool-bubble-timer-leak`
**Issue:** [#73](https://github.com/jdmanring/odysseus/issues/73)
**Base:** `upstream-mirror` (latest upstream commit)
**Status:** Ready to file

---

## Title

`fix(chat): stop tool bubble timers before background-stream skip; guard evicted bubble writes`

---

## Summary

Two bugs in the tool bubble update path inside `chat.js`.

### Bug 1 — Timer leak before `_isBg` skip

The tool bubble update handler starts a wave animation timer (`_waveInterval`) and an elapsed-time ticker (`_elapsedTicker`) to animate the "thinking" indicator on tool calls. Both timers are started before the `_isBg` (is-background-stream) guard:

```javascript
// Before this fix:
currentHolder._waveInterval = setInterval(...);
currentHolder._elapsedTicker = setInterval(...);
if (_isBg) {
  // skip updating this UI — it's a background stream
  continue;
}
// ... update the tool bubble
```

When `_isBg` is true, the function continues to the next iteration without ever clearing the timers. The timers keep firing on a bubble that is no longer being updated, wasting CPU and holding a reference to `currentHolder` in each closure.

Fix: move the timer setup to after the `_isBg` guard so background-stream iterations exit cleanly before starting any timers.

### Bug 2 — Silent write failure after Phase 2 eviction

`chatHistory.js` Phase 2 eviction removes the holder from the DOM while a long tool call is in progress. After eviction, writes to the detached bubble (`currentToolBubble.innerHTML = ...`) silently fail — the DOM update is discarded and no error is thrown.

The handler had a null check (`if (!currentToolBubble)`) but not a connectivity check. A non-null detached element passes the null check; the write silently does nothing.

Fix: add `!currentToolBubble.isConnected` to the guard. When the bubble is detached, skip the update and log a warning:

```javascript
if (!currentToolBubble || !currentToolBubble.isConnected) {
  console.warn('[chat] tool_output: bubble evicted before completion, skipping update');
  continue;
}
```

---

## Files changed

- `static/js/chat.js` — timer setup moved after `_isBg` guard; `isConnected` check added to tool bubble null guard

## Tests

No dedicated test file for this branch. The `isConnected` guard is covered by `test_chat_history_js.py` (Phase 2 eviction tests) and by `test_chat_continue_btn_js.py` (evicted-element guard patterns). Structural tests for the timer-before-`_isBg` fix can be added in `tests/test_chat_tool_bubble_js.py`.

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Fixes # <!-- [add upstream issue number before filing] -->

## Type of Change

- [x] Bug fix (non-breaking, fixes a confirmed issue)
- [ ] New feature
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

1. **Timer leak:** Start a background stream (session with `checkBackgroundStream`). In DevTools → Performance, record during streaming. Confirm no `_waveInterval` or `_elapsedTicker` callbacks appear in the background-stream path.
2. **Evicted bubble:** Run a long agent session until Phase 2 eviction fires. When a tool call's bubble is evicted mid-execution, confirm `[chat] tool_output: bubble evicted before completion, skipping update` appears in the console and the tool call completes without a JS error.
3. Confirm tool bubbles still animate correctly in non-background, non-evicted sessions.

---

## Filing Notes

- Single commit: `ef8b82e4` (on branch), cherry-picked to develop as `773c7d51`.
- Branch: `fix/tool-bubble-timer-leak` — built from `upstream-mirror`.
- **File upstream issue first.** Add the upstream issue number to `Fixes #` above.
- Bug 2 (`isConnected` guard) is most impactful when paired with `fix/dom-oom-virtualization` (which introduces Phase 2 eviction). It is still a valid fix without it — any DOM removal of the bubble (e.g., session switch) triggers the same silent-write scenario.

## Visual / UI changes

None. Tool bubble animation behavior is unchanged in normal (non-evicted, non-background) sessions.

# Upstream Issue Draft: fix-tool-bubble-timer-leak

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-tool-bubble-timer-leak.md`
**Branch:** `fix/tool-bubble-timer-leak`
**Type:** Bug

---

## Title

`[Chat] Tool bubble timers start before background-stream guard; writes silently fail after Phase 2 eviction`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Bug 1 — Timers start before `_isBg` skip:**

The tool bubble update handler starts a wave animation timer (`_waveInterval`) and an elapsed-time ticker (`_elapsedTicker`) before checking whether the current stream is a background stream:

```javascript
currentHolder._waveInterval = setInterval(() => { ... }, 120);
currentHolder._elapsedTicker = setInterval(() => { ... }, 1000);
if (_isBg) {
  continue;  // ← skip the rest of this iteration
}
```

For background streams, `_isBg` is true and the handler continues to the next iteration without ever clearing the timers. Both timers keep firing against a bubble that is no longer receiving UI updates, wasting CPU and holding closure references to `currentHolder` that prevent GC.

**Bug 2 — Writes silently fail after Phase 2 eviction:**

When `chatHistory.js` Phase 2 eviction removes a message holder while a tool call is still in progress, subsequent `innerHTML` writes to `currentToolBubble` silently fail — the DOM update is discarded because the element is no longer connected.

The existing null check (`if (!currentToolBubble)`) does not catch this case. A non-null detached element passes the null check; the write silently does nothing, with no error thrown and no log emitted. This makes it difficult to distinguish "tool call completed correctly" from "tool call's bubble was evicted mid-execution."

**Steps to reproduce bug 2:**

1. Start a very long agent session (100+ messages) until Phase 2 eviction fires.
2. Have an active tool call in progress when eviction removes its holder.
3. Observe: no error in the console, but the tool bubble is gone from the DOM and its status is never visually updated.

**Expected:**
- Timers are created only after the `_isBg` guard confirms this is not a background stream.
- When the bubble's element is no longer connected, the update is skipped and a warning is logged: `[chat] tool_output: bubble evicted before completion, skipping update`.

**Affected file:** `static/js/chat.js` — tool bubble update loop (the block that processes `tool_output` SSE events)

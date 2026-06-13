# PR Draft: fix/streamingtts-scope → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/streamingtts-scope`
**Issue:** [#11](https://github.com/jdmanring/odysseus/issues/11) (fork tracking)
**Status:** Ready to file

---

## Title

`fix(chat): hoist streamingTTS to fix ReferenceError in catch block`

---

## Description

### Problem

In `static/js/chat.js`, `streamingTTS` is declared with `const` inside the
`try` block of the stream handler. The `catch` block references it to call
`window.aiTTSManager.streamingStop()` on error, but since `const` is
block-scoped, `streamingTTS` is not accessible in `catch`. This causes a
`ReferenceError: streamingTTS is not defined` on every stream error, which
aborts the catch block before the TTS stop and cleanup logic runs.

The result: when streaming fails (network error, server disconnect, model
timeout), TTS is left in a streaming state indefinitely and subsequent TTS
playback is broken until the page is reloaded.

### Fix

Hoist the declaration to `let` before the `try` block, and change the
`const` inside `try` to a plain assignment:

```diff
+    let streamingTTS = false; // hoisted — must be accessible in catch
+
     try {
       ...
-      const streamingTTS = !!(window.aiTTSManager && ...);
+      streamingTTS = !!(window.aiTTSManager && ...);
```

The `catch` block can now read `streamingTTS` correctly and stop TTS when
streaming errors.

### Testing

- Stream an LLM response, kill the server mid-stream — TTS now stops cleanly
  in the catch block with no `ReferenceError` in the console.
- Normal streaming (no error) is unaffected.

---

## Filing Notes (James)

- One commit, no squash needed.
- File issue on `pewdiepie-archdaemon/odysseus` first; add its number here
  before opening the PR.

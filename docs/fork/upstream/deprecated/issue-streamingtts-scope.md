# Upstream Issue Draft: fix-streamingtts-scope

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-streamingtts-scope.md`
**Branch:** `fix/streamingtts-scope`
**Type:** Bug

---

## Title

`[Chat] TTS left in broken state after stream error — ReferenceError: streamingTTS is not defined in catch block`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Browser (if applicable):** Any

**Steps to Reproduce:**
1. Enable TTS in Settings.
2. Start streaming an LLM response.
3. Interrupt the stream mid-response (kill the server process, cut the network connection, or trigger a server error that aborts the stream).

**Expected:** TTS stops cleanly when the stream errors. Subsequent TTS playback works normally.

**Actual:** TTS is left in a streaming state indefinitely. Subsequent TTS playback is broken until the page is reloaded. The browser console shows:

```
ReferenceError: streamingTTS is not defined
```

**Logs / Error Output:**
```
ReferenceError: streamingTTS is not defined
    at catch block in static/js/chat.js
```

**Additional context:** In `static/js/chat.js`, `streamingTTS` is declared with `const` inside the `try` block of the stream handler. The `catch` block references it to call `window.aiTTSManager.streamingStop()` on error. Since `const` is block-scoped, `streamingTTS` is not accessible in `catch`. The `ReferenceError` aborts the catch block before the TTS stop and cleanup logic runs, leaving TTS in a permanently broken state for the rest of the session.

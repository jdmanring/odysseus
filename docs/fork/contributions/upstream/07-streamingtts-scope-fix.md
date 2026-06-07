# [UPSTREAM] Fix streamingTTS ReferenceError on Every Stream Error

## Status
- [x] Root cause confirmed with log evidence (2026-06-06)
- [x] Upstream issue filed: pewdiepie-archdaemon/odysseus #TBD
- [x] Fix applied in fork's develop branch
- [ ] Upstream PR opened

## Problem

`streamingTTS` is declared with `const` at `chat.js:1077` inside the `try` block that
opens at line 604. The `catch` block at line 2895 references it at line 2923:

```javascript
// catch block — streamingTTS out of scope (declared with const inside try)
if (streamingTTS && window.aiTTSManager) window.aiTTSManager.stop();
```

`const` is block-scoped in JavaScript — the `try {}` and `catch {}` are separate blocks.
Any stream error (403, 503, network failure, abort) triggers this `ReferenceError`,
which aborts the catch handler early and skips downstream error-handling and cleanup code.

Confirmed in session logs (6 occurrences in one session):
```
[INFO:CONSOLE:2923] "Uncaught (in promise) ReferenceError: streamingTTS is not defined"
```

## Fix

Two-line change in `static/js/chat.js`:

```javascript
// BEFORE the try block (currently at ~line 604):
let streamingTTS = false;   // ← add this line

// Inside the try block (currently line 1077) — remove const:
streamingTTS = !!(window.aiTTSManager && window.aiTTSManager.autoPlay && window.aiTTSManager.available);
```

## Impact

- Stops silent abort of the catch block on every stream error
- Ensures TTS is correctly stopped on stream failure (the intended behavior)
- Does not change any behavior when no error occurs (the happy path is identical)
- Small, low-risk, independently verifiable change

## Applied in Fork

This fix is applied in the fork's `develop` branch. The upstream PR can be opened from
a clean branch off `upstream-mirror` containing only this two-line change.

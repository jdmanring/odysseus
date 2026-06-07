# [UPSTREAM] streamingTTS ReferenceError Aborts catch Block on Every Stream Error

## Status
- Issue filed: Not yet filed
- PR opened: Not yet opened
- Fix in fork: Applied — commit `9fabdc6` on `develop`

## Notes
Two-line change. No visual output changes — no screenshot needed. The upstream PR branch
must be built from `upstream-mirror` with only this two-line diff; do not include the
fork's other chat.js changes.

---

## Staged Issue
<!-- James: open https://github.com/pewdiepie-archdaemon/odysseus/issues/new?template=bug_report.yml and paste below -->

**Steps to Reproduce**

1. Start a streaming chat session.
2. Trigger any stream error: disconnect the network mid-stream, or use a model endpoint
   that returns 503/429, or abort with Escape.

**Expected Behaviour**

The catch block runs fully: TTS playback is stopped if it was active, error state is
cleaned up, and the user sees an appropriate error message.

**Actual Behaviour**

The catch block aborts early with an uncaught `ReferenceError` before reaching the TTS
cleanup and downstream error handling. In the browser console:

```
Uncaught (in promise) ReferenceError: streamingTTS is not defined
  at chat.js:2923
```

This error fires on every stream error, including routine ones (network blip, server
restart, rate limit). Confirmed 6 occurrences in a single session.

**Root Cause**

`streamingTTS` is declared with `const` at `chat.js:1077` inside the `try` block that
opens at line 604. The `catch` block references it at line 2923:

```javascript
// Inside catch block — streamingTTS is out of scope here
if (streamingTTS && window.aiTTSManager) window.aiTTSManager.stop();
```

`const` is block-scoped in JavaScript. The `try {}` and `catch {}` are separate blocks,
so `streamingTTS` is inaccessible in the catch handler. JavaScript throws `ReferenceError`
at runtime rather than failing at parse time, so this goes undetected without a stream error.

**Impact**

- TTS is not stopped on stream failure even when it was active (audio keeps playing)
- All error-handling code below line 2923 in the catch block is silently skipped
- Every stream error (network failure, 403, 503, abort) hits this path

**Proposed Fix**

Two-line change in `static/js/chat.js`:

```javascript
// Add before the try block (line ~604):
let streamingTTS = false;

// Inside the try block (line ~1077) — remove const:
streamingTTS = !!(window.aiTTSManager && window.aiTTSManager.autoPlay && window.aiTTSManager.available);
```

**Install Method:** Manual Python install

**OS:** Linux (confirmed); expected on all platforms

**Willing to submit a fix:** Yes — I can open a PR

---

## Staged PR
<!-- James: file the issue first, get the number, fill in Fixes #NNN below, then open PR -->

### Summary

`streamingTTS` is declared with `const` inside the `try` block at `chat.js:1077` but
referenced in the `catch` block at line 2923. `const` is block-scoped — this throws
`ReferenceError` on every stream error, aborting the catch handler early. TTS playback
is not stopped on stream failure and downstream error handling is silently skipped.
Confirmed 6 occurrences in one session. Two-line fix: hoist `let streamingTTS = false`
before the try block.

### Target branch
- [x] This PR targets **`dev`**, not `main`.

### Linked Issue

Fixes #

### Type of Change
- [x] Bug fix (non-breaking — fixes a confirmed issue)

### Checklist
- [x] Searched open issues and open PRs — not a duplicate
- [x] Targets `dev`
- [x] Changes limited to described scope — two lines only
- [ ] App run locally and verified end-to-end *(must do before filing)*

### How to Test

1. Start a streaming chat session with a model endpoint.
2. Disconnect network mid-stream (or set the endpoint to return 503).
3. Open browser DevTools → Console.
4. Confirm no `ReferenceError: streamingTTS is not defined` appears.
5. If TTS was active, confirm it stops on stream error.
6. Confirm the error UI renders correctly (chat shows an error state, not frozen).

### Visual / UI changes

None — this change has no effect on the happy path. The catch block now runs fully on
stream errors; the only visible difference is correct error state display and TTS stopping.

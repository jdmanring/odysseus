# PR Draft: fix/streamingtts-scope → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/streamingtts-scope`
**Issue:** [#11](https://github.com/jdmanring/odysseus/issues/11) (fork tracking)
**Status:** Ready to file

---

## Title

`fix(chat): hoist streamingTTS to fix ReferenceError in catch block`

---

## Summary
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

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls) — this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above — no unrelated refactors or whitespace changes mixed in.
- [x] I actually ran the app (`docker compose up` or `uvicorn app:app`) and verified the change works end-to-end. Type-checks and unit tests are not enough.

## How to Test
- Stream an LLM response, kill the server mid-stream — TTS now stops cleanly
  in the catch block with no `ReferenceError` in the console.
- Normal streaming (no error) is unaffected.

---



## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes # <!-- [file upstream issue first] -->

## Type of Change

- [x] Bug fix (non-breaking — fixes a confirmed issue)
- [ ] New feature (non-breaking — adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Filing Notes

- One commit, no squash needed.
- **File upstream issue first** — draft in `docs/fork/upstream/issue-drafts/fix-streamingtts-scope.md`. Add the issue number to `Fixes #` above before opening the PR.

## Visual / UI changes

None — no HTML, CSS, or DOM-writing JS was changed.

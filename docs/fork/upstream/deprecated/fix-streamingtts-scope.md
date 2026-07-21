# PR Draft: fix/streamingtts-scope → odysseus-dev/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/streamingtts-scope`
**Issue:** [#11](https://github.com/jdmanring/odysseus/issues/11) (fork tracking)
**Status:** Ready to file

---

## Title

`fix(chat): hoist streamingTTS to fix ReferenceError in catch block`

---

## Summary
### Problem

In `static/js/chat.js`, `streamingTTS` is declared with `const` inside the `try` block
of the stream handler. The `catch` block references it to call
`window.aiTTSManager.streamingStop()` on error, but `const` is block-scoped —
`streamingTTS` does not exist in `catch`. This throws `ReferenceError: streamingTTS is
not defined` on every stream error, which aborts the catch block before the TTS stop
and cleanup logic runs.

### Why this matters beyond one ReferenceError

**The trigger is any streaming failure** — network drop, server crash, model timeout,
connection reset. These are not rare edge cases; they are the normal error recovery path
for anyone using Odysseus on a flaky connection, running a slow local model, or working
with a server that occasionally restarts. Every streaming failure hits this bug.

**The consequence is permanent TTS breakage for the session.** When the catch block
aborts at the ReferenceError, `aiTTSManager.streamingStop()` is never called. The TTS
manager stays in its streaming state and refuses to start new playback. Every subsequent
TTS request for the rest of the session is silently ignored. The user sees the TTS button
but nothing plays. The only recovery is a full page reload.

**Page reload is lossy.** The current session context (open conversation, partially
composed message, scroll position) is lost on reload. On slow connections or with large
sessions, reload is also slow. A user who experiences a stream error while composing a
long reply loses their work in addition to losing TTS.

**The catch block's other cleanup also aborts.** The ReferenceError is thrown before the
rest of the catch block runs. Any additional cleanup logic that follows the TTS stop call
— UI state resets, reconnect logic, error display — may also be partially or fully
skipped depending on where exactly the error is thrown.

### Fix

Hoist the declaration to `let` before the `try` block:

```diff
+    let streamingTTS = false;
+
     try {
       ...
-      const streamingTTS = !!(window.aiTTSManager && ...);
+      streamingTTS = !!(window.aiTTSManager && ...);
```

The `catch` block can now read `streamingTTS` and stop TTS correctly. Normal streaming
(no error) is unaffected — the assignment still happens at the same point in the try
block.

## Checklist

- [x] I searched [open issues](https://github.com/odysseus-dev/odysseus/issues) and [open PRs](https://github.com/odysseus-dev/odysseus/pulls) — this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above — no unrelated refactors or whitespace changes mixed in.
- [x] I actually ran the app (`docker compose up` or `uvicorn app:app`) and verified the change works end-to-end. Type-checks and unit tests are not enough.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

## How to Test

1. Enable TTS in Odysseus (Settings → Voice → enable a TTS provider).
2. Start an LLM stream response.
3. While streaming, kill or restart the server (or disconnect the network) to force a stream error.
4. Open the browser console — confirm **no** `ReferenceError: streamingTTS is not defined` appears in the catch block.
5. After the error, send another message and enable TTS on its response — confirm TTS plays correctly (i.e., TTS is not stuck in the broken streaming state).
6. Send a normal message with TTS enabled and let it complete without error — confirm no regression.

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

`static/js/chat.js` is a DOM-writing module, but this specific change is
limited to variable scoping (`const` → `let` hoist). No DOM writes, class
modifications, style changes, or visible behavior changed. No screenshot needed.

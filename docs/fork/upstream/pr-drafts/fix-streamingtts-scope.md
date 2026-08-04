# PR Draft: fix/streamingtts-scope -> odysseus-dev/odysseus:dev

> **Note before filing (2026-08-03).** `develop` fixed this on 2026-06-21 in
> `02e8ed48` by declaring `var streamingTTS` (function-scoped, so the `catch`
> can reach it) rather than hoisting a `let`. **Upstream still has `const`**, so
> the bug is real there and this PR remains valid — but the premise "declared
> inside the try block" describes upstream, not develop.


**Branch:** `fix/streamingtts-scope`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 1 file, +3/-2

---

## Title

`fix(chat): hoist streamingTTS so the catch block can reach it`

---

## Summary

### Problem

`const streamingTTS` is declared **inside** the `try` block and referenced in the
`catch`. A `const` is scoped to the block it is declared in, so the reference
throws `ReferenceError` - and it throws *inside the error handler*, on every
stream failure: 503, network drop, user abort.

The second-order effect is the damaging one. The `ReferenceError` aborts the
catch handler at its first line, so everything after it is skipped: TTS is never
stopped and the downstream cleanup never runs. An error path that exists
specifically to tidy up instead leaves audio playing and state stale.

### Fix

Declare `let streamingTTS` before the `try`, assign inside as before. Three lines.

---

## Verification

**2 passed**, measured 2026-08-03, in `tests/test_chat_stream_scope.py` - a file
this repo already has, which already pins `_renderStream`,
`_cancelThinkingTimer` and `_removeThinkingSpinner` to the outer scope with the
same hoist-and-assign shape. `streamingTTS` is the fourth member of that family
and was the only one left out, which is how it regressed.

**Mutation-checked:** the new assertion fails against the current `chat.js` and
passes against the fixed one, so it is a guard rather than decoration.

Confirmed against session logs: **6 occurrences on 2026-06-06.**

---

## Scope

`static/js/chat.js`, +3/-2.

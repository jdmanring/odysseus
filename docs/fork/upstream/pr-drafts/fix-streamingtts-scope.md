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

Confirmed against session logs: **6 occurrences on 2026-06-06.**

### Fix

Declare `let streamingTTS` before the `try`, assign inside as before. Three lines.

---

## Verification

The branch carries **no test file**, which should be stated rather than glossed:
the fix is a two-line scope correction and the failure was identified from
production logs rather than a reproduction.

A regression test is straightforward if wanted - a static guard that the
declaration precedes the `try`, in the same shape as the suite's other
source-assertion tests - and can be added before merge on request.

---

## Scope

`static/js/chat.js`, +3/-2.

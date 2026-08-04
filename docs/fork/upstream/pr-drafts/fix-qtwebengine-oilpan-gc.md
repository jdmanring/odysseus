# PR Draft: fix/qtwebengine-oilpan-gc -> odysseus-dev/odysseus:dev

**Branch:** `fix/qtwebengine-oilpan-gc`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 2 files, +94

---

## Title

`fix(perf): hint an async GC after a response, without stacking cycles`

---

## Summary

### Problem

Embedded Chromium environments - PyQt, Electron, native wrappers - **do not
receive the OS memory-pressure signals** that prompt a regular browser to collect.
So the garbage produced by a long streaming response can sit uncollected for far
longer than it would in a tab, and the host process holds the memory.

This is the part worth stating clearly in review: it is not a leak and it is not
a Blink bug. It is a signal that never arrives because there is no browser UI
layer to deliver it.

### Fix

Hint a GC after a response completes, feature-detected so it is a no-op where
`gc()` is not exposed.

**The `_gcPending` guard is the substance.** An async major GC
(`gc({ type: 'major', execution: 'async' })`) runs incrementally over 3-6
seconds. Without a guard, a user who sends another message inside that window
stacks a second cycle on top of the first - turning a memory optimisation into
competing incremental collections during the next response, which is worse than
doing nothing.

So: set the flag before the call, clear it after, and skip while pending.

The 2.5 s outer delay keeps the hint away from the frame right after the response
lands, with a `requestIdleCallback` fallback. A `[GC]` log line makes the
dispatch observable rather than something you infer from an RSS graph.

---

## Verification

**9 passed**, measured 2026-08-03. The static tests lock each contract
individually: `_gcPending` declaration, feature detection, ordering
(set-before-call, clear-after-call), the 2.5 s outer delay, the
`requestIdleCallback` fallback, and the log line.

Ordering has its own assertions because a clear-before-call would silently
disable the guard while leaving all the code present.

---

## Scope

`static/js/chat.js` (+23) and one test file (+71).

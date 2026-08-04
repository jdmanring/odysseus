# PR Draft: fix/modal-zpromote-reduced-motion-oom -> odysseus-dev/odysseus:dev

**Branch:** `fix/modal-zpromote-reduced-motion-oom`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 2 commits, 2 files, +38/-1

---

## Title

`fix(ui): modal z-promote observer loops to renderer OOM under reduced motion`

---

## Summary

### Problem

With OS "reduce motion" active, the app crashes the renderer when opening a
modal. Reproduced deterministically; RSS climbs to ~2.4 GB in seconds and
Chromium reports `Target crashed`.

The chain is four unremarkable things that only combine under reduce-motion:

1. `style.css`'s accessibility catch-all sets `transition-duration: 0.01ms
   !important` while `transition-property` stays the default `all`. So **a
   z-index write starts a 10µs transition.**
2. The modal auto-promote `MutationObserver` guards against re-entry by
   comparing the **computed** `z-index` with what it just wrote.
3. During a transition, the computed value stays at the stylesheet value - so
   the guard never matches.
4. The observer storm runs as **microtasks**, and document time is frozen while
   the microtask queue drains, so the 10µs transition never completes.

Every write re-fires the observer, the guard never matches, and mutation records
allocate at roughly **60 MB/s** until the renderer dies.

Note that reduce-motion normally *removes* work. Here it creates an infinite
loop, which is why it went unnoticed: the setting is off on most machines.

### Fix

Read the **inline** style first, falling back to computed. The inline value
reflects the observer's own last write immediately and is immune to transition
interpolation, so the re-entry guard matches on the first re-fire.

One line of behaviour change; the rest is the comment explaining why, because
the next person to "simplify" this back to `getComputedStyle` will reintroduce a
renderer crash.

---

## Verification

Diagnosed on the macOS Tahoe bench with Reduce Motion enabled:
`Debugger.pause` caught `_promote`/observer as the busy stack, and a `[PMV]`
trace showed the computed value pinned at `cur=260` while the internal
`_zCounter` climbed freely - the guard comparing two values that could never
converge.

After the fix, Cookbook opens on that bench and renderer RSS is stable.

Static guard test: **1 passed**, measured 2026-08-03. It asserts the inline read
comes before the computed read, which is the property that matters.

---

## Scope

`static/js/ui.js` (+12/-1) and one test.

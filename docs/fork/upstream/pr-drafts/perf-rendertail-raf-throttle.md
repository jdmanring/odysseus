# PR Draft: perf/rendertail-raf-throttle -> odysseus-dev/odysseus:dev

> **Note before filing (2026-08-03).** `develop` already throttles, by a
> different mechanism: `_throttledRenderStream` uses a 16 ms interval
> (`_RENDER_INTERVAL`, from `02e8ed48`, 2026-06-21) rather than
> `requestAnimationFrame`. Both target 60 fps and `finalize()` covers the
> trailing edge in each, so this is an alternative implementation rather than a
> missing one. The rAF version's advantage is frame alignment: it cannot render
> twice within one frame and it runs when the browser is about to paint. Say so
> in the PR, because a reviewer who checks will find the interval version.


**Branch:** `perf/rendertail-raf-throttle`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 1 file, +12/-2

---

## Title

`perf(streaming): throttle live tail renders to one per animation frame`

---

## Summary

### Problem

At 150-200 tok/s the per-token `_renderStream()` -> `renderTail()` chain runs
every 5-7 ms. Each call allocates a holder div **and a full markdown-parsed DOM
subtree** (`innerHTML = render(tailText)`), which is discarded immediately after
the tail nodes are updated in place.

That is 150-200 ephemeral DOM trees per second handed to Oilpan - the primary
ongoing GC pressure source during streaming, and the work is thrown away by
construction.

The display cannot show any of it. A screen refreshes at most once per animation
frame, so at 60 fps roughly **two thirds to three quarters of those renders are
invisible** even when they complete.

### Fix

Gate the normal-streaming `_renderStream()` call behind a `requestAnimationFrame`
guard, capping renders at frame cadence.

**No tokens are lost.** `_renderStream` reads the *accumulated* text rather than
a per-token delta, so the rAF callback always renders the most recent state
regardless of how many tokens arrived since the last frame. Skipping a render is
skipping a redundant paint of intermediate text, not dropping content.

---

## Verification

The branch carries **no test file of its own**, and that should be said plainly.
The counter that measures the effect is on a companion branch:
`perf/gc-rendertail-instrumentation` adds `_rtCalls`, logged in `finalize()`, as a
direct measure of DOM allocation pressure. Its stated expectation is that a
working rAF throttle drops the count from roughly the token rate per second to
roughly 60 per second.

**Recommended filing order:** the instrumentation branch first, then this one, so
the counter exists to demonstrate the improvement rather than being asserted.
Reviewed the other way round, this PR asks to be taken on reasoning alone.

---

## Scope

`static/js/chat.js`, +12/-2.

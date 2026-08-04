# PR Draft: perf/gc-rendertail-instrumentation -> odysseus-dev/odysseus:dev

**Branch:** `perf/gc-rendertail-instrumentation`
**Status:** Ready to file — **file BEFORE `perf/rendertail-raf-throttle`**
**Base:** cut from `upstream-mirror`, 2 files, +75

---

## Title

`perf(streaming): count renderTail calls so allocation pressure is measurable`

---

## Summary

### Why instrumentation first

`renderTail()` fires once per SSE token and allocates a holder div on each call,
so the number of calls **is** a direct measure of DOM allocation pressure during
streaming. Today that number is invisible, which means any claim about streaming
allocation — including the companion rAF-throttle change — rests on reasoning
rather than measurement.

This branch adds the counter (`_rtCalls`), logged in `finalize()`. A working rAF
throttle should drop it from roughly the token rate per second (150-200) to
roughly 60 per second, and with this landed that becomes a number a reviewer can
read off their own session instead of taking on trust.

Filing this first is the point: it makes the next PR checkable.

### The tightened assertion

The branch also strengthens `test_rendertail_counter_logged_in_finalize`. The
original two-assertion form passed on any occurrence of **either** string
independently, so a refactor that split the log line still passed. It now
verifies the exact concatenation expression, so a changed log format is caught.

That is a small change worth flagging, because it is the difference between a
test that pins a contract and one that merely notices two words exist somewhere
in the file.

---

## Verification

**6 passed**, measured 2026-08-03. The static tests lock the counter contract:
declaration, increment order relative to the early-return paths, log format, and
the zero-guard.

---

## Scope

`static/js/streamingRenderer.js` (+9) and one test file (+66). Logging only — no
behaviour change to rendering.

# PR Draft: perf/hljs-deferred-highlight -> odysseus-dev/odysseus:dev

**Branch:** `perf/hljs-deferred-highlight`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 7 files, +263/-38

---

## Title

`perf(chat): defer syntax highlighting to the viewport`

---

## Summary

### Problem

Seven sites in `chat.js` called `window.hljs.highlightElement` directly,
synchronously highlighting **every** `pre > code` element in a container,
including ones far outside the viewport.

Highlighting is a parse plus a DOM rewrite per block. Doing it for off-screen
blocks is work whose result nobody sees until they scroll, if ever — and it lands
synchronously on the main thread at the worst moments.

Four of the seven sites highlight blocks that are typically far off-screen:
stop-stream, continue-message, variant switch, and the error catch path.

### Fix

Replace the direct calls with `deferHighlightAll(container)`, which uses the
shared `IntersectionObserver` from `hljsDefer.js` to highlight a block only once
it scrolls within 200px of the viewport.

**Visible blocks are not delayed in any perceptible way**: they highlight within
one observer tick, about 16 ms. What changes is that off-screen blocks stop being
highlighted eagerly.

### The part that makes it safe: `forgetNode()`

The branch also adds `forgetNode()` to release observer references **before DOM
eviction**. Without it, deferring highlighting would trade synchronous CPU for a
retained-node leak: the chat DOM is virtualized, so blocks are evicted while the
observer still holds references to them. This is the change that makes the
deferral net-positive rather than a different kind of cost, and it is the one to
review most closely.

---

## Verification

**21 passed**, measured 2026-08-03, across three test files: the seven call sites
route through `deferHighlightAll`, the observer contract, and the `forgetNode`
release on eviction.

---

## Scope

`static/js/chat.js`, `static/js/hljsDefer.js`, `static/js/streamingRenderer.js`
and three test files.

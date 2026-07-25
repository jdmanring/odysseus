# Upstream Issue Draft: perf-chathistory-gc-improvements

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/perf-chathistory-gc-improvements.md`
**Branch:** `perf/chathistory-gc-improvements`
**Type:** Performance
**Depends on:** `fix/dom-oom-virtualization` (chatHistory.js is introduced by that PR)

---

## Title

`[Performance] chatHistory.js: idle GC yield missing from _evictLive and _pruneBottom; timers not cleared before node removal`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Problem:**

Two cleanup gaps in `chatHistory.js` (introduced by `fix/dom-oom-virtualization`) that cause unnecessary GC pressure after DOM eviction.

**Gap 1: Missing idle GC yield after `_evictLive` and `_pruneBottom`:**

`_pruneTop` already yields to idle after removing a batch of nodes:

```javascript
if (typeof requestIdleCallback !== 'undefined') {
  requestIdleCallback(function () {}, { timeout: 3000 });
}
```

This gives V8/Oilpan a cooperative GC window to incrementally collect detached subtrees before the next frame. `_evictLive` (Phase 2 eviction) and `_pruneBottom` (scroll-up pruning) both create equivalent batches of detached nodes but have no corresponding yield. Without the hint, detached nodes from these operations accumulate in Oilpan until a full GC sweep fires.

**Gap 2: `_waveInterval`, `_elapsedTicker`, and `_streamRenderer` not cleared before removal in `_pruneTop` and `_pruneBottom`:**

`_evictLive` correctly clears all three before every `.remove()`:

```javascript
if (el._waveInterval)   { clearInterval(el._waveInterval);   el._waveInterval   = null; }
if (el._elapsedTicker)  { clearInterval(el._elapsedTicker);  el._elapsedTicker  = null; }
if (el._streamRenderer) { el._streamRenderer = null; }
// ... same walk over descendants
```

`_pruneTop` and `_pruneBottom` only call `hljsDeferForgetNode` before `.remove()`. They skip the timer and renderer cleanup entirely. After removal:
- `_waveInterval` and `_elapsedTicker` continue firing against detached nodes: wasted CPU, and the timer closure holds a reference to the detached element, preventing GC.
- `_streamRenderer` holds `lastText` (full response string) and a detached `tailMarker` comment node in old-gen indefinitely.

For a session with 100 pruned nodes, this is 100 live setInterval handles and 100 retained response strings after pruning.

**Proposed fix:**

Apply the same four-line teardown block from `_evictLive` before each `.remove()` call site in `_pruneTop` (2 sites: main loop + boundary cleanup) and `_pruneBottom` (2 sites: same structure). Add the idle yield to `_evictLive` and `_pruneBottom`.

**Affected file:** `static/js/chatHistory.js`, `_pruneTop`, `_pruneBottom`, `_evictLive`

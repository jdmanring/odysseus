# PR Draft: perf/chathistory-gc-improvements -> odysseus-dev/odysseus:dev

> **SUPERSEDED (2026-08-03).** `perf/chathistory-gc-improvements` (2 commits,
> 2026-06-22) was the first implementation of the chat-history message window.
> `fix/dom-oom-virtualization` (11 commits, 2026-07-18 -> 2026-08-03) is the
> matured version of the same feature and is the one to file.
>
> Verified rather than assumed: every helper this branch introduced
> (`_attachBottomSentinel`, `_evictLive`, `_histChildCount`, `_initMutObs`,
> `_deferAll`) is present on `develop` in equal or greater number, so the work
> landed via the successor. Rebased onto the current mirror it goes from 9 to 23
> failing source-assertion tests, because its tests pin a `sessions.js`/`chat.js`
> shape upstream has since restructured.
>
> The branch was already deleted once, deliberately. It was restored on
> 2026-08-03 during a draft audit that saw only "draft exists, branch missing",
> and re-deleted the same day once the supersession was established. Preserved at
> `refs/deleted/perf-chathistory-gc-improvements`.


**Branch:** `perf/chathistory-gc-improvements`
**Issue:** [#83](https://github.com/jdmanring/odysseus/issues/83)
**Base:** `upstream-mirror` (latest upstream commit)
**Status:** Ready to file (depends on `fix/dom-oom-virtualization`)

---

## Title

`perf(chatHistory): idle GC yield after prune/evict; clear timers before node removal`

---

## Summary

Two classes of cleanup gap in `chatHistory.js` that cause unnecessary GC pressure after DOM eviction.

### A. Missing idle GC signal after `_evictLive` and `_pruneBottom`

`_pruneTop` already yields to idle after removing a batch of nodes:

```javascript
if (typeof requestIdleCallback !== 'undefined') {
  requestIdleCallback(function () {}, { timeout: 3000 });
}
```

This yields control to V8/Oilpan so it can incrementally collect the detached subtrees before the next frame. `_evictLive` and `_pruneBottom` create the same detached subtrees but had no equivalent yield. Without the hint, Oilpan accumulates detached nodes across multiple prune cycles before a full GC sweep.

Added the same four-line block to both functions. The `_evictLive` call fires in the Phase 2 eviction path (long sessions); the `_pruneBottom` call fires when the user scrolls back up through history.

### B. Missing timer/renderer teardown in `_pruneTop` and `_pruneBottom`

`_evictLive` correctly clears three types of references before every `.remove()` call:

```javascript
if (el._waveInterval)   { clearInterval(el._waveInterval);   el._waveInterval   = null; }
if (el._elapsedTicker)  { clearInterval(el._elapsedTicker);  el._elapsedTicker  = null; }
if (el._streamRenderer) { el._streamRenderer = null; }
// ... same walk over el.querySelectorAll('*')
```

`_pruneTop` and `_pruneBottom` only called `hljsDeferForgetNode` and then `.remove()`, leaving any live `_waveInterval` or `_elapsedTicker` timers running on the detached nodes. The timers continued firing against nodes that no longer exist in the DOM. The `_streamRenderer` reference on detached nodes held the full response text (`lastText`) in old-gen memory.

Added the `_evictLive` teardown pattern before each of the four `.remove()` call sites in both functions (main removal loop + boundary cleanup loop in each).

### C. `_purgeStaleBackgroundStreams` on session switch

`_purgeStaleBackgroundStreams()` sweeps `_backgroundStreams` for completed/error entries and deletes them. It was called only in `handleChatSubmit`. Completed entries accumulated across session switches until the next submit.

Added one call at the top of `checkBackgroundStream`, which `sessions.js` invokes on every session switch. No new API surface.

---

## Files changed

- `static/js/chatHistory.js`: idle yield in `_evictLive` and `_pruneBottom`; full teardown in all four removal loops of `_pruneTop` and `_pruneBottom`
- `static/js/chat.js`: `_purgeStaleBackgroundStreams()` at top of `checkBackgroundStream`
- `tests/test_chat_history_js.py`: +4 tests
- `tests/test_chat_gc_hint_js.py`: +1 test

## Tests

5 new static-analysis tests:

**`tests/test_chat_history_js.py`** (+4):
- `test_evict_live_yields_to_idle`: `requestIdleCallback` present in `_evictLive`
- `test_prune_bottom_yields_to_idle`: `requestIdleCallback` present in `_pruneBottom`
- `test_prune_top_clears_intervals_before_remove`: `_waveInterval` cleared in `_pruneTop`
- `test_prune_bottom_clears_intervals_before_remove`: `_waveInterval` cleared in `_pruneBottom`

**`tests/test_chat_gc_hint_js.py`** (+1):
- `test_check_background_stream_purges_stale`: `_purgeStaleBackgroundStreams()` at top of `checkBackgroundStream`

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Relates to #4644 ("browser tab OOM during long agent interactions"). This reduces one
source of that growth: it idle-yields after eviction and fully tears down listeners and
background streams when chat history is pruned. File a focused upstream issue if warranted
and link it here before submitting. (Do not use the bare number from the fork tracker as
an upstream issue reference.)

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [x] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/odysseus-dev/odysseus/issues) and [open PRs](https://github.com/odysseus-dev/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

1. Run a long session until Phase 1 pruning fires (scroll up far enough to trigger `_pruneTop` or `_pruneBottom`: look for `[chatHistory] pruned` in console). Confirm no `setInterval` callbacks fire after pruned nodes are removed (DevTools -> Performance -> check for orphaned timer callbacks).
2. Run a session until Phase 2 eviction fires (`[chatHistory] Phase 2 evict` in console). In DevTools -> Memory, confirm the heap snapshot shows fewer detached nodes in the 5 s after eviction vs. before this patch.
3. Open a background stream in one session, let it complete, switch sessions. Confirm `_backgroundStreams` no longer contains the completed entry (instrument via DevTools console: `chatModule._backgroundStreams.size`).
4. Run `pytest tests/test_chat_history_js.py tests/test_chat_gc_hint_js.py -q`: covers both the new tests and the existing 15 tests.

---

## Filing Notes

- 2 commits from `upstream-mirror`: base chatHistory.js (`337fedc5`), GC improvements (`d05e9e2e`).
- Branch: `perf/chathistory-gc-improvements`, built from `upstream-mirror`.
- **Depends on `fix/dom-oom-virtualization`**: chatHistory.js is introduced by that PR. This branch can be filed as a follow-up once the virtualization PR lands upstream. Alternatively, include it in the virtualization PR as an additional commit.
- **File upstream issue first.** Issue is tracked at jdmanring/odysseus#83; upstream issue number needed before filing.
- The change C (`_purgeStaleBackgroundStreams` on session switch) is also present in `perf/gc-micro-improvements`. File only one; the other branch's version can be dropped.

## Visual / UI changes

None. Pruning and eviction behavior is unchanged; this only affects what is cleaned up before removal and whether Oilpan receives a collection hint.

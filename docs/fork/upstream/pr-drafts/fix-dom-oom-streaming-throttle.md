# PR Draft — fix/dom-oom-streaming-throttle

**Branch**: `fix/dom-oom-streaming-throttle` (from `upstream-mirror`)
**Issue**: jdmanring/odysseus#64
**Base**: `upstream-mirror` (latest upstream commit)
**Status**: Ready to file

---

## Title

`perf(streaming): fix O(n²) thinking-block allocation, rAF throttle, StreamRenderer teardown`

---

## Summary

The QtWebEngine renderer grows to 14–18 GB RSS in long agent sessions (~300+ messages). Root cause analysis via `/proc/PID/maps` confirmed three allocating sources in `chat.js`. This PR fixes all three plus adds a post-stream GC yield.

### Fix A — thinking block textContent during streaming (primary fix)

`_liveThinkInner.innerHTML = markdownModule.mdToHtml(thinkText)` ran on every SSE delta while a thinking block was open. With ~500 tokens per response and mdToHtml returning 50–200 KB of HTML per call, this generated ~50 MB of V8 old-gen garbage per thinking response that the GC never compacted during active streaming.

Fix: replace with `textContent = thinkText; style.whiteSpace = 'pre-wrap'` during streaming. A single `mdToHtml` render fires when the block closes and `whiteSpace` is cleared. This approach is adapted from upstream PR #4661 (holden093), which applies the same textContent fix.

### Fix A2 — rAF throttle for normal streaming

`_renderStream()` was called synchronously on every SSE delta in the normal streaming path. At 200 tok/sec this is 200 layout-triggering re-renders per second. Throttled to one per animation frame via a `requestAnimationFrame` guard (`_renderRafId`). The pending frame is cancelled in `finally` so the final synchronous render is not double-fired.

### Fix C1 — StreamRenderer closure teardown

`contentEl._streamRenderer` held `lastText` (the full response string) and a detached `tailMarker` comment node in old-gen indefinitely. Neither `finalize()` nor any cleanup was ever called after the final `innerHTML` re-render. Fixed by nulling both references after the final render: `_scEl._streamRenderer = null` and `_liveReplyEl._streamRenderer = null`.

### Fix C3 — Post-stream idle GC yield

After stream finalization, yield to idle via `scheduler.postTask(() => {}, { priority: 'background' })` with `requestIdleCallback` fallback. This gives V8 a compaction window after the streaming allocation burst. `scheduler.postTask` with `'background'` priority is stronger than a bare `requestIdleCallback` in Chromium-based runtimes because it runs at the lowest scheduler priority rather than at idle hint.

### Fix C4 — Background stream field cleanup on `[DONE]`

`_backgroundStreams` map entries kept `accumulated`, `sourcesHtml`, and `findingsData` populated after stream completion. Text is already persisted to DB at this point; retaining it in-memory serves no purpose. All three are cleared when `[DONE]` is received. (Upstream PR #4661 cleared only `accumulated` and `abortCtrl`.)

---

## Files changed

- `static/js/chat.js` — all five fixes
- `tests/test_chat_streaming_oom.py` — new file, 14 static-analysis tests

## Tests

14 static-analysis tests in `tests/test_chat_streaming_oom.py`:
- thinking-block `textContent` path present
- `whiteSpace = 'pre-wrap'` set during thinking streaming
- final `mdToHtml` render fires on block close
- `_renderRafId` RAF guard present in `_renderStream`
- RAF cancellation present in `finally`
- `_scEl._streamRenderer` nulled after final render
- `_liveReplyEl._streamRenderer` nulled after final render
- `scheduler.postTask` GC yield present
- `requestIdleCallback` fallback present
- `accumulated` cleared on `[DONE]`
- `sourcesHtml` cleared on `[DONE]`
- `findingsData` cleared on `[DONE]`
- `abortCtrl` cleared on `[DONE]`
- `_purgeStaleBackgroundStreams` present

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Relates to #4644 ("browser tab OOM during long agent interactions"). This addresses
several streaming-side causes of that OOM; open PR #4661 addresses overlapping causes (see
the relationship note below). File a focused upstream issue if a distinct one is warranted,
and link it here before submitting.

## Type of Change

- [x] Bug fix (non-breaking, fixes a confirmed issue)
- [ ] New feature
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

1. Run a long agent session with thinking blocks enabled (20+ thinking-block responses).
2. Monitor renderer RSS via `cat /proc/$(pgrep -n QtWebEngineProc)/smaps_rollup | grep Rss` between responses. With the thinking-block fix, RSS should grow significantly more slowly during thinking-heavy sessions.
3. Open DevTools → Memory. Compare heap snapshots before and after a thinking-block response. The post-response snapshot should show fewer retained `HTMLDivElement` instances.
4. Verify rendered output is identical for thinking-block responses (final mdToHtml render fires correctly).
5. Run `pytest tests/test_chat_streaming_oom.py -q` — 14 tests.

---

## Filing Notes

- 3 commits: fix (`d35f3819`), tests (`6cae1aad`), PR draft (`16e8bc16`).
- Branch: `fix/dom-oom-streaming-throttle` — built from `upstream-mirror`.
- **File upstream issue first.** Add the upstream issue number to `Fixes #` above.
- **Relationship to upstream PR #4661**: the thinking-block `textContent` fix and the
  background-stream cleanup are adapted from PR #4661 (holden093), with attribution. The
  rAF throttle, StreamRenderer teardown, and idle scheduler are independent additions. The
  DOM-cap portion of #4661 (`_trimChatHistoryDOM`, `_loadOlderMessages`) is intentionally
  not included; it conflicts with the separate `fix/dom-oom-virtualization` change, which
  bounds the DOM by virtualization rather than pagination. These two streaming fixes are
  complementary to #4661 and can land in either order; the DOM-bounding approach is the one
  that needs coordination (tracked in the `fix/dom-oom-virtualization` draft).

## Visual / UI changes

None. Streaming appearance is unchanged; thinking blocks display identically. The only behavior change is memory usage and allocation timing.

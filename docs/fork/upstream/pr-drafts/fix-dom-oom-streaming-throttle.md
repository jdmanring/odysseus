# PR Draft — fix/dom-oom-streaming-throttle

**Branch**: `fix/dom-oom-streaming-throttle` (from `upstream-mirror`)
**Issue**: jdmanring/odysseus#64
**Upstream issue**: file before PR

---

## Title

`perf(streaming): fix O(n²) thinking-block allocation, rAF throttle, StreamRenderer teardown`

## Summary

The QtWebEngine renderer grows to 14–18 GB RSS in long agent sessions (~300+ messages). Root cause analysis via `/proc/PID/maps` confirmed three sources in `chat.js`. This PR fixes all three plus adds a post-stream GC yield.

**Fix A — thinking block textContent during streaming** (primary fix, adapted from upstream PR #4661):

`_liveThinkInner.innerHTML = markdownModule.mdToHtml(thinkText)` was called on every SSE delta while a thinking block was open. With ~500 tokens per response and the markdown pipeline returning 50–200 KB of HTML per call, this generated ~50 MB of V8 old-gen garbage per thinking response that the GC never compacted during active streaming.

Replace with `textContent = thinkText; style.whiteSpace = 'pre-wrap'` during streaming. A single `mdToHtml` render fires when the block closes and the `whiteSpace` style is cleared.

**Fix A2 — rAF throttle for normal streaming**:

`_renderStream()` was called synchronously on every SSE delta in the normal streaming path. At 200 tok/sec this is 200 layout-triggering re-renders per second. Throttled to one per animation frame via a `requestAnimationFrame` guard (`_renderRafId`). The pending frame is cancelled in `finally` so the final synchronous render is not double-fired.

**Fix C1 — StreamRenderer closure teardown**:

`contentEl._streamRenderer` holds `lastText` (the full response string) and a detached `tailMarker` comment node in old-gen indefinitely. Neither `finalize()` nor any cleanup was ever called. After the final `innerHTML` re-render the references are nulled out: `_scEl._streamRenderer = null` and `_liveReplyEl._streamRenderer = null`.

**Fix C3 — Post-stream idle GC yield**:

After stream finalization, `scheduler.postTask(() => {}, { priority: 'background' })` yields to idle (with `requestIdleCallback` fallback). This gives V8 a compaction window after the streaming allocation burst. `scheduler.postTask` with `'background'` priority is stronger than a bare `requestIdleCallback` in Chromium-based runtimes.

**Fix C4 — Background stream field cleanup on `[DONE]`**:

`_backgroundStreams` map entries kept `accumulated`, `sourcesHtml`, and `findingsData` populated after stream completion. Text is already persisted to DB at this point. All three are cleared when `[DONE]` is received. (Upstream PR #4661 cleared only `accumulated` and `abortCtrl`.)

## Test plan

- `tests/test_chat_streaming_oom.py` — 14 new static-analysis tests lock in all five fixes
- Run a long agent session with thinking enabled and observe renderer RSS via `cat /proc/$(pgrep QtWebEngineProc)/smaps_rollup | grep Rss` before and after each message exchange

## Files changed

- `static/js/chat.js` — all fixes
- `tests/test_chat_streaming_oom.py` — new test file

## Relationship to upstream PR #4661

This branch adapts the thinking-block textContent fix and background stream cleanup approach from upstream PR #4661. The rAF throttle, StreamRenderer teardown, and idle scheduler are independent additions. The DOM-cap portion of PR #4661 (`_trimChatHistoryDOM`, `_loadOlderMessages`) is NOT included — it is incompatible with the chatHistory.js virtualization system and is handled separately in `fix/dom-oom-phase2-guard`.

File this PR after upstream PR #4661 either merges (take the safe cherry-picks via the pipeline) or is closed. If filing independently, note the relationship in the PR body.

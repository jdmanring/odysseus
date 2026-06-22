# Upstream Issue Draft: fix-dom-oom-streaming-throttle

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-dom-oom-streaming-throttle.md`
**Branch:** `fix/dom-oom-streaming-throttle`
**Type:** Bug / Performance

---

## Title

`[Chat] Renderer OOM in long agent sessions — thinking-block innerHTML allocation, no rAF throttle, StreamRenderer not torn down`

---

## Body

**Install method:** Docker / manual Python / Qt wrapper

**OS / device:** Any (most visible in embedded Chromium / Qt wrapper)

**Summary:**

The QtWebEngine renderer reaches 14–18 GB RSS in long agent sessions (~300+ messages with thinking blocks). Three distinct allocation sources in `chat.js` compound to cause this. Each is independently measurable; together they cause OOM in long sessions.

**Root cause 1 — O(n²) thinking-block innerHTML (primary):**

`_liveThinkInner.innerHTML = markdownModule.mdToHtml(thinkText)` is called on every SSE delta while a thinking block is open. `mdToHtml` parses the entire accumulated thinking text and returns 50–200 KB of HTML per call. At ~500 tokens per response, one thinking-block response generates approximately 50 MB of V8 old-gen garbage that the GC cannot compact during active streaming (Chromium's streaming GC only runs between frames, not mid-SSE). This garbage accumulates across responses.

The fix: during streaming, set `_liveThinkInner.textContent = thinkText` with `style.whiteSpace = 'pre-wrap'`. Fire the single `mdToHtml` render when the thinking block closes. This approach matches upstream PR #4661 (holden093, open).

**Root cause 2 — No rAF throttle on `_renderStream`:**

`_renderStream()` is called synchronously on every SSE delta in the normal streaming path. At 200 tok/sec this is 200 layout-triggering re-renders per second. Each re-render creates a new DOM subtree in Oilpan; the old subtree is detached and queued for GC. At 200/sec, Oilpan queues detached subtrees faster than its cooperative collector can reclaim them.

The fix: a `requestAnimationFrame` guard (`_renderRafId`) throttles `_renderStream` to one call per animation frame (~60/sec max). The pending frame is cancelled in `finally` so the final synchronous render is not skipped.

**Root cause 3 — StreamRenderer not torn down after final render:**

After the final `innerHTML` assignment, `contentEl._streamRenderer` continues to hold a reference to `lastText` (the full response string) and a detached `tailMarker` comment node. Neither is cleared. In a session with 100 responses, this is 100 full response strings and 100 detached comment nodes retained in old-gen indefinitely.

**Additional: background stream fields not cleared on completion:**

`_backgroundStreams` map entries retain `accumulated`, `sourcesHtml`, and `findingsData` after `[DONE]`. These fields are already persisted to DB at that point; keeping them in the Map serves no purpose.

**Steps to reproduce:**

1. Start the app with an agent that uses thinking blocks (Claude 3.7 Sonnet extended thinking enabled).
2. Run 20+ multi-round agent sessions without reloading.
3. Monitor renderer RSS: `cat /proc/$(pgrep -n QtWebEngineProc)/smaps_rollup | grep Rss`
4. RSS grows monotonically, typically reaching 4–8 GB after 100 responses and crashing (SIGKILL from OOM) after 200–300 responses.

**Expected:**

RSS stabilizes after each GC cycle. Thinking-block rendering does not allocate proportional to the thinking text length per token. StreamRenderer state is released after finalization.

**Related:** upstream PR #4661 (holden093) addresses the thinking-block allocation and background stream cleanup. This issue also covers the rAF throttle and StreamRenderer teardown, which are not part of #4661.

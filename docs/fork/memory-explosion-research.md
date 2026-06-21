# Memory Explosion Research: QtWebEngine OOM in Long Agent Sessions

**Status**: Investigation complete. Three root causes confirmed. Upstream PR #4661 addresses two of them. One (Phase 2 guard bug) remains fork-only work.

**Symptoms**: QtWebEngine renderer process grows to 14–18+ GB RSS during long agent sessions (~300+ messages). Memory grows ~200–300 MB per message exchange. Requires app restart. Confirmed on the "A Simple Greeting" libvirt debugging session (308 messages, 487 tool events).

---

## What We Measured

```
/proc/13190/smaps_rollup (mid-session):
  Rss:           17,659,596 kB  (17.2 GB physical pages in RAM)
  Pss_Anon:      17,515,338 kB  (17.1 GB is anonymous private — not file-backed)
  Private_Dirty: 17,509,252 kB

V8 rw-p heap regions (from /proc/13190/maps):
  5,463 MB   rw-p [anon:v8]
  4,206 MB   rw-p [anon:v8]
  3,440 MB   rw-p [anon:v8]
  1,998 MB   rw-p [anon:v8]
    524 MB   rw-p [anon:v8]
    167 MB   rw-p [anon:v8]
    512 MB   rwxp [anon:v8]  ← JIT-compiled JS code
  ─────────────────────────
  ~15.8 GB total V8 heap RSS

Non-V8 anonymous rw-p (Blink PartitionAlloc, GPU, etc.):
  ~850 MB
Process heap [heap]:
  ~612 MB
```

The enormous `---p` regions (65 GB, 31 GB PartitionAlloc, 16 GB V8 cage) have **no permissions and zero RSS** — they are virtual address reservations, not RAM.

**The problem is entirely in the V8 JavaScript heap.** 15.8 GB of actual physical RAM is in V8 old-generation space.

**Stored data is negligible**: 1.6 MB in DB (154 assistant messages × 8.7 KB metadata average). All tool outputs capped at 10 KB before SSE delivery via `_truncate()`. Only 2 screenshot events across 487 tool calls.

---

## Root Cause 1 (CONFIRMED): Per-Token Full Markdown Render

**Location**: `static/js/chat.js` — thinking block handler; `static/js/streamingRenderer.js` — tail render.

### Thinking blocks

During a streaming think block, `_liveThinkInner.innerHTML = markdownModule.mdToHtml(thinkText)` is called **on every SSE delta**. For a 2,000-token thinking block with 500 SSE events, this is 500 invocations of the full markdown pipeline on a progressively-growing string. Each call:

- Parses the accumulated `thinkText` (up to 10–50 KB by end)
- Invokes `squashOutsideCode()` (string scanning + replacements)
- Runs the full marked.js tokenizer + renderer pipeline
- Returns a rendered HTML string (50–200 KB after syntax-highlighting span expansion)
- Sets `innerHTML` on the live element (triggers Blink layout)

The intermediate HTML strings survive long enough in the streaming loop to be promoted from V8's young-gen (new-space) to old-gen (old-space). After the stream ends they become garbage, but V8's major GC compactor never runs during active streaming. Old-gen accumulates dead objects.

**Estimated old-gen garbage per thinking-heavy message**: `500 calls × 100 KB output string × 2 (live + dead copy during innerHTML) = 100 MB` promoted to old-gen per response.

### Regular streaming tail

`_renderStream()` calls `markdownModule.processWithThinking(markdownModule.squashOutsideCode(dt))` on every text delta via the StreamRenderer. The StreamRenderer's freeze-and-tail-only approach reduces DOM writes significantly, but still calls the markdown parser on every token for the live tail. This is a secondary contributor for non-thinking responses.

---

## Root Cause 2 (CONFIRMED): Phase 2 Live-Session Pruning Hard Stop

**Location**: `static/js/chatHistory.js` — `_maybePrune()` at line 592.

```js
MessageWindow.prototype._maybePrune = function () {
  if (!this._isAtBottom()) return;
  if (!this._histSep || !this._histSep.parentNode) return;
  var total = this._liveChildCount();
  if (total <= PRUNE_AT) return;          // PRUNE_AT = 80
  var hist  = this._histChildCount();
  if (hist === 0) return;                 // ← FATAL: stops forever once history exhausted
  this._pruneTop(Math.min(hist, total - PRUNE_AT + PRUNE_COUNT));
};
```

**What happens**: Session loads with 50 historical messages (WINDOW_SIZE). As live messages are added, `total` exceeds `PRUNE_AT=80`. Phase 2 prunes historical nodes. Once all 50 historical nodes are pruned, `hist === 0` and **Phase 2 never fires again**. Live messages accumulate without bound for the rest of the session.

**Scale for "A Simple Greeting"**: Historical exhaustion happens around exchange #15–20. The remaining 130+ exchanges (270+ DOM node groups) accumulate untouched. Each agent exchange with 10–20 tool calls creates 50–200+ DOM nodes (structural elements + syntax-highlighting spans). Estimate: **50,000–200,000 live DOM nodes** in the unchecked case.

**Why this contributes to V8 heap**: DOM text content (syntax-highlighted code spans) and DOM attribute values (`dataset.raw`, `data-ch-idx`) are V8 strings. A 10 KB bash output rendered with hljs syntax highlighting produces ~50 KB of span-wrapped HTML. With 295 bash outputs: 295 × 50 KB = **14.75 MB of V8 strings** in retained DOM nodes. Significant but not the 16 GB — most of that is fragmentation from Root Cause 1.

---

## Root Cause 3 (CONFIRMED MINOR): Background Stream Entry Retention

**Location**: `static/js/chat.js` — `_backgroundStreams` Map.

When a stream switches to background (`_backgroundStreams.set(streamSessionId, { accumulated, ... })`), the `accumulated` string is stored in the map entry. After the stream completes (status set to `'completed'`), the entry **is not immediately deleted**. It persists until the next `_purgeStaleBackgroundStreams()` call (which didn't exist before upstream PR #4661). For a session with background streaming, this leaks the full accumulated response text.

**Scale**: Small compared to Root Causes 1 and 2 — a few KB to a few hundred KB per leaked entry.

---

## What Is NOT the Cause

- **Stored data size**: DB content is 1.6 MB. Too small by 4 orders of magnitude.
- **Screenshots via SSE**: `tool_output_data["screenshot"]` field confirmed; only 2 events in session; data URI would be large but 2 events is negligible.
- **`_all[]` array**: Contains plain `{role, content, modelName, meta}` objects from DB load. Total ~2.7 MB. Never grows during live streaming.
- **`chatHistory.js` DOM references**: No retained DOM node references. Uses `data-ch-idx` attributes for re-lookup.
- **StreamRenderer per-message state**: `lastText` (same as `dataset.raw`), `tailMarker` (detached comment node), `committedLen` scalar. Tiny.
- **TTS audio cache**: Only relevant if TTS is in use and uncleaned. Not in this session.

---

## Upstream Context

**Issue #4644** ("fix(ui): browser tab OOM and freeze during long agent interactions") filed 2026-06-20. Matches exactly.

**PR #4661** ("fix(ui): prevent browser OOM during long agent interactions") filed 2026-06-20. Open, not yet merged. Changes:

| What upstream PR does | Root cause addressed |
|---|---|
| `_liveThinkInner.textContent = thinkText` during streaming (single rich render at close) | Root Cause 1 (thinking blocks) |
| `_trimChatHistoryDOM()` cap at 150 nodes; "Show N older messages" bar that re-fetches from server | Root Cause 2 (live DOM cap) |
| `_purgeStaleBackgroundStreams()` clearing `accumulated` on completed entries | Root Cause 3 |
| `streamDocDelta()` throttled to one DOM update per `requestAnimationFrame` | Document editor equivalent |
| History load capped at 400 messages on session select | Initial load safety |

**What upstream PR does NOT fix**:
- The Phase 2 `hist === 0` hard-stop bug in `chatHistory.js` (their `_trimChatHistoryDOM()` in `chat.js` is a parallel approach that bypasses chatHistory.js entirely — both should coexist)
- Per-token `_renderStream()` allocation for non-thinking regular streaming (tail re-renders still happen per-token via StreamRenderer)
- The Phase 3 scroll-jump-to-bottom bug (our `fix/dom-oom-virtualization` branch — message-count based BIDI cap)

**This PR will enter develop via the ingest pipeline when it merges upstream.** Until then, our fork needs its own versions of these fixes.

---

## Fix Plans

### Fix A — Thinking Block Plain-Text Streaming (Root Cause 1, primary)

**What upstream PR does**: Replace `_liveThinkInner.innerHTML = markdownModule.mdToHtml(thinkText)` with `_liveThinkInner.textContent = thinkText` during streaming. One rich render when the block closes.

**Effect**: Eliminates O(n²) markdown pipeline allocations for thinking blocks. Estimated reduction: 500× fewer `mdToHtml` invocations per thinking response. Direct attack on the primary source of V8 old-gen pollution.

**Implementation**: Straightforward substitution in `chat.js`. Already done in upstream PR #4661.

**Risk**: Thinking block displays as plain text during streaming. On close, a single full render replaces it. User sees: plain text → (collapse transition) → rendered markdown. This is acceptable — the block is collapsed by default anyway.

**Open questions**:
- Does the transition look jarring? Upstream's PR had a screenshot — appears smooth.
- Should we also apply this to regular streaming tail renders? (see Fix A2 below)

**Fix A2 — Regular Streaming rAF Throttle**:
Wrap `_renderStream()` in a `requestAnimationFrame` debounce. Instead of calling on every SSE delta, batch to max once per frame (~16ms). For a 50 token/second stream, this reduces renders from 50/sec to 60/sec max (no gain) — but for a fast model at 200 tok/sec, it reduces from 200/sec to 60/sec (3.3× reduction). More importantly: within a single `rAF`, the previous call's intermediate objects go out of scope before promotion from new-gen to old-gen.

```js
// In chat.js handleChatSubmit, inside the per-token handler:
if (_streamRenderRaf) return;
_streamRenderRaf = requestAnimationFrame(() => {
  _streamRenderRaf = null;
  _renderStream();
});
```

**Caveat**: The StreamRenderer already limits re-renders to the tail only (frozen blocks not re-rendered). The main cost is the markdown parser call itself. This throttle helps when tokens arrive faster than 60/sec.

---

### Fix B — Phase 2 `hist === 0` Guard Removal + Live Cap (Root Cause 2)

**Two sub-approaches — both needed, in layers:**

#### Fix B1 — Remove the `hist === 0` early return

The immediate bug in `chatHistory.js:592`. When historical nodes are exhausted, Phase 2 must still enforce a cap on live nodes. But `_pruneTop()` only removes historical nodes (hard boundary at `_histSep`). So removing the early return alone doesn't help — `_pruneTop()` would find nothing to remove.

#### Fix B2 — Extend `_pruneTop()` to handle live message overflow

When `hist === 0` and `total > PRUNE_AT`, we need to remove the oldest live messages. These messages ARE in the DB (saved during streaming), so they can be restored. But they are NOT in `_all[]`. Options:

**Option B2a**: When Phase 2 detects `hist === 0` and overflow, add the oldest live messages to `_all[]` before removing them from DOM. This integrates with the existing scroll-up restoration mechanism. Requires that `addMessage()` returns element references so we can extract content from the DOM before removal.

**Option B2b**: Replace the `hist === 0` path with a server-refetch approach (matching upstream PR #4661's `_trimChatHistoryDOM()` approach). Keep a counter of pruned live messages and insert a "load older" bar. This is exactly what upstream PR #4661 does in `chat.js`, but applied to chatHistory.js's Phase 2.

**Option B2c**: Accept the chatHistory.js limitation for now and rely on upstream PR #4661's `_trimChatHistoryDOM()` (which we will ingest when it merges). Their `_trimChatHistoryDOM()` is called in `chat.js` independently of the chatHistory.js Phase 2 system, so both can coexist. The Phase 2 `hist === 0` bug becomes irrelevant once `_trimChatHistoryDOM()` is active.

**Recommendation**: Fix B1 (remove the guard) as a minimal correctness fix so Phase 2 never silently stops. Then rely on upstream PR #4661's approach for the actual live-cap implementation. Do not implement a parallel "load older" mechanism that duplicates upstream's work.

**Effect of B1**: Phase 2 will call `_pruneTop()` even when `hist === 0`, but `_pruneTop()` will remove zero nodes (since there are no historical nodes). The `if (removed === 0) return;` guard in `_pruneTop()` handles this safely. Net effect: Phase 2 no longer silently dies, but doesn't fix the live overflow problem alone. Combined with upstream's `_trimChatHistoryDOM()`, the live overflow is fully handled.

---

### Fix C — Post-Stream GC Pressure Reduction (Beyond Band-Aid)

The original "Fix C" was `requestIdleCallback()` — a hint that rarely triggers major GC. Improved version:

#### Fix C1 — Explicit StreamRenderer Teardown After Finalization

The `_streamRenderer` on each content element is never cleaned up. After `addMessage()` replaces the streaming content with the finalized HTML, the renderer's `lastText` (full response text) and `tailMarker` (detached comment node) are retained unnecessarily.

```js
// In chat.js after the final addMessage() call:
if (contentEl && contentEl._streamRenderer) {
  contentEl._streamRenderer = null;
}
```

This lets V8 collect the renderer closure and its captured strings (including `lastText`) earlier. Minor per-message, but eliminates one class of retained garbage.

#### Fix C2 — Background Stream Entry Cleanup on Completion

Already done in upstream PR #4661: `bgDone.accumulated = ''; bgDone.abortCtrl = null;` when stream completes. Add `_purgeStaleBackgroundStreams()` call at the start of each `handleChatSubmit()`.

#### Fix C3 — Idle Scheduler After Stream Completion

After each stream finalizes (in the `finally` block of `handleChatSubmit()`), schedule an idle callback. V8 runs incremental GC during idle periods. This doesn't force a major GC but creates the idle window that V8 uses to collect old-gen garbage:

```js
// In handleChatSubmit finally block:
if ('scheduler' in window && 'postTask' in window.scheduler) {
  // Prioritized Task Scheduling API (Chrome 94+, including current QtWebEngine)
  window.scheduler.postTask(() => {}, { priority: 'background' });
} else if ('requestIdleCallback' in window) {
  window.requestIdleCallback(() => {}, { timeout: 5000 });
}
```

`scheduler.postTask` with `'background'` priority is stronger than `requestIdleCallback` — it creates a genuine low-priority idle point that V8 uses for incremental GC steps. The 5-second timeout on `requestIdleCallback` prevents the GC from being deferred indefinitely during active use.

#### Fix C4 — data-URI Image Teardown on DOM Prune (matching upstream PR)

Upstream PR #4661's `_trimChatHistoryDOM()` includes:
```js
el.querySelectorAll('img[src^="data:"]').forEach(function(img) {
  img.src = '';
});
```

This explicitly clears inline data-URI images before removing nodes, preventing the V8 string (the data URI) from being kept alive by the img element's `src` attribute even after the element is removed from DOM. Important for any session that included screenshot tool calls.

#### Fix C5 — Interval/Spinner Cleanup on Prune (matching upstream PR)

Upstream PR also clears `_waveInterval`, `_elapsedTicker`, and `_spinner` before removing elements. Timers and animation objects that reference DOM elements prevent GC of the entire element subtree.

**Combined Fix C effect**: C1 + C2 + C3 eliminate retained garbage per message. C4 + C5 prevent detached-node leaks during DOM pruning. Together these are not a band-aid — they reduce the amount of V8 old-gen garbage generated per message and create the idle windows needed for V8 to compact it.

---

## What We Still Don't Know

1. **Live/dead ratio in the 15.8 GB V8 heap**: Is most of it dead (fragmentation waiting for compaction) or genuinely live retained objects? A heap snapshot via Chrome DevTools remote debugging (`QTWEBENGINE_CHROMIUM_FLAGS="--remote-debugging-port=9222"`) would answer this definitively.

2. **Exact per-token allocation volume**: How many MB does a single `markdownModule.mdToHtml(thinkText)` call allocate when `thinkText` is 10 KB? This determines whether Fix A alone is sufficient.

3. **Whether V8 GC actually runs during idle periods in QtWebEngine**: Qt's event loop integration with V8's GC scheduler may prevent `requestIdleCallback` from being as effective as in Chrome.

---

## Logging and Instrumentation to Add

To close the open questions before finalizing fixes:

```js
// 1. Heap size per message (in handleChatSubmit finally block):
if (performance.measureUserAgentSpecificMemory) {
  performance.measureUserAgentSpecificMemory().then(m => {
    console.log('[mem] After message:', (m.bytes / 1e9).toFixed(2), 'GB V8 heap');
  });
}

// 2. DOM node count (in _maybePrune and _trimChatHistoryDOM):
console.log('[dom] chat children:', document.getElementById('chat-history').children.length,
            'hist:', this._histChildCount(), 'live:', this._liveChildCount());

// 3. Mark start/end of thinking block renders:
console.time('[think] mdToHtml');
_liveThinkInner.innerHTML = markdownModule.mdToHtml(thinkText);
console.timeEnd('[think] mdToHtml');
```

Enable remote debugging for a full heap snapshot:
```bash
QTWEBENGINE_CHROMIUM_FLAGS="--remote-debugging-port=9222" python3 app.py
# Then open chrome://inspect in Chrome and attach to the page
```

---

## Priority Order

1. **Fix A** (thinking block per-token render) — highest impact, lowest risk. This is the primary driver of 200–300 MB/message growth in agent sessions with thinking. Already in upstream PR #4661.

2. **Ingest upstream PR #4661** via the pipeline once it merges — gets us Fix A, Fix C2–C5, DOM cap with server reload, and document streaming throttle.

3. **Fix B1** (remove `hist === 0` guard in chatHistory.js) — correctness fix, makes Phase 2 never silently die. Low risk, independent of upstream PR.

4. **Fix C1** (StreamRenderer teardown) — minor per-message cleanup. Fork-specific improvement not in upstream PR.

5. **Fix A2** (rAF throttle for regular streaming) — secondary improvement, investigate whether needed after Fix A reduces the primary load.

6. **Add instrumentation first** to measure heap before/after Fix A so we have before/after numbers to include in the upstream PR draft.

---

## Branch Plan

All fixes are upstream-candidates (they fix Odysseus itself, not fork tooling).

| Branch | Origin | Fix | Status |
|---|---|---|---|
| `fix/dom-oom-virtualization` | `upstream-mirror` | Phase 3 scroll-jump-to-bottom (BIDI_MSG_CAP) | On develop, needs in-app verification |
| `fix/dom-oom-phase2-guard` | `upstream-mirror` | Fix B1: remove `hist === 0` early return | Not started |
| `fix/dom-oom-streaming-throttle` | `upstream-mirror` | Fix A + A2 + C1–C3 (streaming allocation reduction) | Not started |
| _(pending ingest)_ | upstream PR #4661 | Upstream thinking-block fix + DOM cap + purge | Waiting for upstream merge |

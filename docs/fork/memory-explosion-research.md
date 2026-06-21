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

**PR #4661** ("fix(ui): prevent browser OOM during long agent interactions") filed 2026-06-20. Open, not yet merged. No comments yet.

Test branches: `test/upstream-pr-4661` (on upstream-mirror), `test/pr-4661` (on develop, one conflict resolved in `sessions.js`).

### What the PR gets right

| Change | Root cause | Assessment |
|---|---|---|
| `_liveThinkInner.textContent` during streaming; single `mdToHtml` on close | Root Cause 1 (primary) | Clean and correct. Take as-is. |
| `_purgeStaleBackgroundStreams()` + clear `accumulated`/`abortCtrl` on done | Root Cause 3 | Correct but incomplete — `sourcesHtml` and `findingsData` not cleared. Adapt. |
| `streamDocDelta()` rAF throttle | Document editor thrash | Clean and correct. Take as-is. |
| Pagination (`?limit=400`, `?offset=`) in history route | Initial load safety | Well-designed. Take as-is. |
| `content-visibility: auto` on `.msg`, `.agent-thread`, `.thinking-content` | Paint/layout overhead | Valid CSS optimization. Take as-is. |

### What the PR gets wrong — incompatibility with the chatHistory.js virtualization system

**`_trimChatHistoryDOM()` destroys chatHistory.js control elements.**

The function iterates `#chat-history.children` from index 0 and calls `el.remove()` unconditionally until `children.length <= 150`. It only skips incrementing `_unloadedMsgCount` for non-message nodes — it does not skip *removing* them. Nodes destroyed:
- `.chat-history-sentinel` — kills Phase 1 IntersectionObserver permanently
- `.chat-history-spacer` — breaks scroll-position restoration after top prune
- `.chat-history-sep` (`_histSep`) — destroys the historical/live boundary; Phase 2 and Phase 3 stop working

There is zero coordination with chatHistory.js state (`_all[]`, `_startIdx`, `_endIdx`, `_sentinel` reference). After `_trimChatHistoryDOM()` runs once in a session with history, the entire Phase 1/2/3 virtualization system is broken.

**`_loadOlderMessages()` breaks multi-round agent messages.**

`addMessage()` creates multiple top-level DOM nodes for a multi-round agent response (one bubble per round + tool thread per round) but returns only `lastWrap` (the final round's text bubble). `_loadOlderMessages()` does `box.insertBefore(el, bar)` which moves only `lastWrap` to the correct position near the top; all earlier rounds were appended by `addMessage()` to the *bottom* of the chat and are not moved. A saved agent session with 3 rounds renders as: [round3-text near top] ... [round1-text, tool-thread, round2-text at bottom].

**`_loadOlderMessages()` bypasses `_all[]` entirely.**

Loaded messages are not registered with chatHistory.js. If Phase 1's sentinel is still present (not yet destroyed by `_trimChatHistoryDOM()`), scrolling past the sentinel would re-render the same messages from `_all[]`, causing duplicates.

### What the PR does not address

- Phase 2 `hist === 0` hard-stop — confirmed bug in this fork, not fixed
- Regular streaming tail per-token allocations — StreamRenderer still runs markdown pipeline per-token for non-thinking text
- Phase 3 scroll-jump-to-bottom — fixed in `fix/dom-oom-virtualization`

### Verdict

**Take the safe parts directly; replace `_trimChatHistoryDOM()` and `_loadOlderMessages()` with a proper Phase 2 live-message cap.**

The upstream PR cannot be ingested as-is once it merges. The DOM-cap piece must be adapted to coordinate with chatHistory.js. The safe parts (thinking-block fix, background cleanup, doc streaming throttle, pagination, CSS) can be cherry-picked without modification.

---

## Fix Plans

### Fix A — Thinking Block Plain-Text Streaming (Root Cause 1, primary)

**Source**: Upstream PR #4661 identified this fix. The root cause was independently confirmed here from the `/proc/PID/maps` analysis and code trace. The implementation matches PR #4661's approach: `textContent` during streaming, single `mdToHtml` render on block close.

**Effect**: Eliminates O(n²) markdown pipeline allocations for thinking blocks. Estimated reduction: 500× fewer `mdToHtml` invocations per thinking response. Direct attack on the primary source of V8 old-gen pollution.

**Implementation**: Substitution in `chat.js` at line 1580. Adapted from upstream PR #4661.

**Risk**: Thinking block displays as plain text during streaming. On close, a single full render replaces it. User sees: plain text → (collapse transition) → rendered markdown. This is acceptable — the block is collapsed by default anyway.

**Open questions**:
- Does the transition look jarring? Upstream's PR had a screenshot — appears smooth.
- Consider also applying this to regular streaming tail renders. (see Fix A2 below)

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

### Fix B — Extend Phase 2 to Cap Live Messages (Root Cause 2)

Upstream PR #4661's `_trimChatHistoryDOM()` is the right concept but the wrong implementation for this codebase — it destroys chatHistory.js control elements and bypasses `_all[]`. The correct fix is to extend Phase 2 inside `chatHistory.js` so it handles live overflow using the same infrastructure that already handles historical overflow.

#### The architecture

Phase 2 already:
- Knows about sentinels, spacers, and histSep (skips them during prune)
- Tracks `_startIdx`/`_endIdx` for Phase 1 reload
- Has `_pruneTop()` with proper scroll-position compensation via spacer

What it lacks: a way to prune live messages (nodes after `_histSep`) and register them for later reload.

#### How live messages get into `_all[]`

When a stream finishes, `chat.js` finalizes the message and it is saved to the DB. That message is *already* available via `/api/history/:id`. But it is not in `_all[]` — `_all[]` was populated at session load and never updated during the session.

The fix: when Phase 2 detects `hist === 0` and `total > PRUNE_AT`, it evacuates the oldest live messages from the DOM back into `_all[]`. Because live messages are saved to DB, `_all[]` can be extended and Phase 1 can reload them exactly as it reloads any other historical message.

#### Implementation

**Step 1 — Remove the `hist === 0` early return** (`chatHistory.js:592`):

```js
// Before (bug):
if (hist === 0) return;
this._pruneTop(Math.min(hist, total - PRUNE_AT + PRUNE_COUNT));

// After:
if (hist > 0) {
  this._pruneTop(Math.min(hist, total - PRUNE_AT + PRUNE_COUNT));
} else {
  this._evictLive(total - PRUNE_AT + PRUNE_COUNT);
}
```

**Step 2 — Add `_evictLive(count)`** to chatHistory.js:

```js
MessageWindow.prototype._evictLive = function (count) {
  // Identify the oldest 'count' live message elements (immediately after histSep).
  // Extract their rendered data so _all[] can restore them later.
  // Remove from DOM.  Update _all[], _endIdx, and move _histSep forward.
};
```

The function walks DOM children after `_histSep`, finds the oldest `count` message elements, captures `{ role, innerHTML, modelName, meta }` from each (using `data-ch-role`, `data-ch-model`, `dataset.raw`, and existing data attributes), prepends them to `_all[]` with adjusted indices, removes them from DOM (with the same resource cleanup upstream PR does: timer teardown, data-URI clear), and moves `_histSep` forward to just before the first remaining live message.

**Step 3 — Extend `_pruneTop()` spacer logic** to cover the new evicted-live case (already works — the spacer insertion after pruning top is structural, not historical-specific).

**Step 4 — Handle `_loadOlderMessages()` correctly**: upstream PR's `_loadOlderMessages()` bypasses `_all[]` and breaks multi-round agent messages. Phase 1's IntersectionObserver already handles loading older messages from `_all[]` on scroll-up — by routing evicted live messages through `_all[]`, Phase 1 handles the reload automatically with no special "load older" bar needed.

#### What to take from upstream PR #4661's DOM cap approach

The cleanup code in upstream PR #4661's `_trimChatHistoryDOM()` before removing each element is correct and reusable. This pattern was adapted into `_evictLive()`:
```js
if (el._waveInterval) { clearInterval(el._waveInterval); el._waveInterval = null; }
if (el._elapsedTicker) { clearInterval(el._elapsedTicker); el._elapsedTicker = null; }
if (el._spinner) { try { el._spinner.destroy(); } catch (_) {} }
el.querySelectorAll('.agent-thread-node').forEach(function(n) {
  if (n._waveInterval) { clearInterval(n._waveInterval); n._waveInterval = null; }
  if (n._elapsedTicker) { clearInterval(n._elapsedTicker); n._elapsedTicker = null; }
});
el.querySelectorAll('img[src^="data:"]').forEach(function(img) { img.src = ''; });
```

This teardown should be extracted into a shared `_teardownNode(el)` helper and called both in `_pruneTop()` and `_evictLive()`.

#### Data attributes needed on live message elements

For `_evictLive()` to capture message metadata without re-fetching from the server, live message elements need data attributes set during `addMessage()`. Currently `data-ch-idx` is set only for historical messages. Required:
- `data-ch-role` — already set via element class (`msg-user`, `msg-ai`)
- `data-ch-model` — not currently set; needs to be added to the role label element
- `dataset.raw` — already set on all finalized messages for copy/regenerate; contains the markdown source

For tool-event metadata (`meta.tool_events`, `meta.round_texts`): the fully-rendered HTML in the DOM element's innerHTML is sufficient for re-display. Reconstructing tool_events for scroll-up reload is not necessary — re-rendering the stored HTML is enough. This is exactly what `addMessage(role, storedHtml, modelName, null)` does for historical messages.

#### Effect

After this fix, Phase 2 enforces a unified cap on the total DOM (historical + live). Live messages overflow gracefully into `_all[]`. Phase 1 reloads them on scroll-up via the existing IntersectionObserver mechanism. No second DOM manager. No control-element destruction. No multi-round-agent rendering bug.

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

1. **Add instrumentation** (heap size + DOM count logging) before implementing any fix, to establish a baseline and validate each fix's impact.

2. **Fix A** — thinking block per-token render. Highest impact, lowest risk. Primary driver of 200–300 MB/message growth in agent sessions with thinking.

3. **Fix C2 + background stream cleanup** — clear `accumulated`, `sourcesHtml`, `findingsData`, `abortCtrl` from completed background stream entries. Fast win, independent of all other work.

4. **Fix B** — Phase 2 live-message eviction. Fixes unbounded live DOM accumulation for all session types. More complex but architecturally complete — no second DOM manager, no sentinel destruction, no multi-round rendering bug.

5. **Fix A2** — rAF throttle for regular streaming tail. Investigate whether needed after Fix A reduces the primary load. May be redundant.

6. **Fix C1 + C3** — StreamRenderer teardown, idle scheduler. Polish after the main fixes.

7. **Ingest upstream PR #4661 when it merges** — take the safe parts (thinking-block fix, doc streaming throttle, pagination, background cleanup, CSS) via the pipeline. **Do not take `_trimChatHistoryDOM()` or `_loadOlderMessages()` as-is** — replace with the Phase 2 live-eviction fix (Fix B). File a comment on the upstream PR noting the chatHistory.js incompatibility and proposing the `_evictLive()` approach as an improvement.

---

## Branch Plan

All fixes are upstream-candidates.

| Branch | Origin | Scope | Status |
|---|---|---|---|
| `fix/dom-oom-virtualization` | `upstream-mirror` | Phase 3 scroll-jump-to-bottom (BIDI_MSG_CAP) | On develop; needs in-app verification |
| `fix/dom-oom-streaming-throttle` | `upstream-mirror` | Fix A (thinking-block textContent, adapted from upstream PR #4661) + Fix A2 (rAF throttle) + Fix C1–C3 (C4 partial — teardown pattern adapted from PR #4661) | Built and pushed (commit `d35f3819`) |
| `fix/dom-oom-phase2-guard` | `fix/dom-oom-virtualization` | Fix B: Phase 2 `_evictLive()` replaces `hist===0` hard-stop; teardown cleanup adapted from upstream PR #4661's `_trimChatHistoryDOM()` teardown | Built and pushed (commit `d1222f42`) |
| `test/upstream-pr-4661` | `upstream-mirror` | Upstream PR #4661 cherry-picked on upstream-mirror — for comparison only | Created, pushed |
| `test/pr-4661` | `develop` | Upstream PR #4661 cherry-picked on develop (one conflict resolved in sessions.js) — for comparison only | Created, pushed |
| _(pending ingest)_ | upstream PR #4661 | Safe parts only — see "Ingest" note above | Waiting for upstream merge |

### Attribution

The following elements were adapted from upstream PR #4661 ("fix(ui): prevent browser OOM during long agent interactions") by holden093:

- **Fix A thinking-block approach** (`fix/dom-oom-streaming-throttle`): The `textContent` substitution for `_liveThinkInner` during streaming and the deferred single rich render on block close. The root cause was independently confirmed from `/proc/PID/maps` analysis, but the specific fix approach matches PR #4661's implementation.
- **Background stream cleanup** (`fix/dom-oom-streaming-throttle`): Clearing `accumulated`, `sourcesHtml`, `findingsData` on `[DONE]`. PR #4661 cleared only `accumulated` and `abortCtrl`; `sourcesHtml` and `findingsData` were added here.
- **`_evictLive()` teardown pattern** (`fix/dom-oom-phase2-guard`): The per-node cleanup (clear `_waveInterval`, `_elapsedTicker`, `_streamRenderer`, recurse into descendants) mirrors the teardown block inside PR #4661's `_trimChatHistoryDOM()`. That function could not be used directly because it destroys chatHistory.js control elements.

What was NOT taken from PR #4661:
- `_trimChatHistoryDOM()` — incompatible with chatHistory.js virtualization system
- `_loadOlderMessages()` — breaks multi-round agent message rendering
- History pagination (`routes/history_routes.py` `?limit=`/`?offset=`) — separate concern, taken during ingest after PR merges
- Document editor rAF throttle — separate concern, same as above
- `content-visibility: auto` CSS — separate concern, same as above

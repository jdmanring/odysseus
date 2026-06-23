# Memory Explosion Research: QtWebEngine OOM in Long Agent Sessions

**Status**: Active investigation. Root cause revised 2026-06-21 — see Session 2 findings below. Original analysis (V8 old-gen theory) was based on `/proc/PID/maps` labels which are misleading for Oilpan allocations. CDP diagnosis overturned it.

**Symptoms**: QtWebEngine renderer process grows to 14–18+ GB RSS during long agent sessions (~300+ messages). Memory grows ~200–300 MB per message exchange (or faster during active streaming). Requires app restart. Confirmed on multiple sessions. Growth visible from the very first session restart (~600 MB/min during active use in new sessions).

---

## Session 2 Findings — 2026-06-21 (CDP Diagnosis)

### Revised root cause: Oilpan/Blink, not V8

CDP (`Memory.getDOMCounters()`, enabled via `--remote-debugging-port=9222`) gave a direct reading that invalidated the Session 1 analysis:

```
documents:       5
nodes:           224,986   ← total DOM nodes in Blink heap
jsEventListeners: 5,427
```

At the same time, the V8 heap report showed only **82 MB** in V8 JavaScript heap — negligibly small.

**The memory explosion is almost entirely Oilpan (Blink's garbage collector for DOM nodes, CSS objects, and layout trees)**, not V8's JavaScript old-generation space. The `/proc/PID/maps` labels from Session 1 that showed `[anon:v8]` regions totalling 15.8 GB were misleading — Chromium's PartitionAlloc (used by Oilpan) does not label its regions `[anon:oilpan]`; they appear as generic anonymous mappings, some of which are labelled `v8` by the kernel's AnonVma naming for the renderer process as a whole.

**Confirmed**: 224,986 total Blink nodes vs ~9,195 live nodes = ~215,000 **detached nodes** sitting in Oilpan's heap, not yet collected. Each streaming response creates and discards a large DOM subtree (the streaming tail is cleared and rebuilt on every render, each clearTail + rebuild cycle leaving one full response tree detached). Oilpan does not collect these in a timely way because:

1. **No OS memory pressure signals**: QtWebEngine is an embedded renderer — it does not participate in the browser-level memory pressure notification system that signals Oilpan to run a major collection. In a real Chrome tab, when the OS reports low memory, Blink's memory coordinator forces a GC. In QtWebEngine, this path is not wired up.

2. **Oilpan incremental GC is insufficient**: Oilpan's default schedule is based on allocation rate heuristics. During active streaming, the allocation rate is high enough to trigger frequent minor cycles but not major ones. Detached subtrees (Oilpan's "old objects") accumulate between major GCs.

3. **No external pressure to trigger a major cycle**: Without the OS signal and without an explicit `gc()` call, major Oilpan GC does not run between responses.

### What Session 1 fixes did and didn't do

All Session 1 fixes (thinking-block textContent throttle, rAF throttle, in-place tail patch, `_purgeStaleBackgroundStreams()`, `content-visibility: auto`, idle callbacks, history pagination, 30fps `_RENDER_INTERVAL`) were applied to `develop` before the Session 2 monitoring started.

**Measured results (new session, pid=18573, all fixes applied)**:

```
337 MB   start
474 MB   +137 MB/min  (light initial load)
1,599 MB +1,125 MB/min ← first burst of conversation
1,607 MB +8 MB/min    (brief stability)
1,617 MB +10 MB/min   (brief stability)
1,748 MB +131 MB/min  (next exchange)
2,380 MB +632 MB/min  (continued use)
2,996 MB +616 MB/min  (continued use)
3,178 MB +182 MB/min  (continued use)
```

**Conclusion**: The Session 1 fixes reduced the *continuous drip* rate during idle periods (~8–10 MB/min vs ~200–300 MB/min before) but did NOT stop the per-response spike pattern. Memory climbs monotonically during active use, just at a somewhat slower rate. The session would still hit OOM within 20–40 more exchanges.

**Why content-visibility: auto didn't fix it**: `content-visibility: auto` defers layout and paint for off-screen elements, reducing Oilpan's *cost to access* those elements. But the detached nodes from streaming still exist in Oilpan's heap — they just aren't laid out. The node count (215,000) is unchanged; only the CPU time to process them is reduced.

**Why idle callbacks didn't fix it**: `scheduler.postTask('background')` and `requestIdleCallback()` create the idle window that V8 uses for incremental GC steps. But V8's incremental GC handles *JavaScript* objects, not Oilpan's C++ DOM node graph. Oilpan has its own GC scheduler that idle callbacks do not directly influence.

### The only mechanism that works: --expose-gc

During Session 1, `--expose-gc` was added to Chromium flags (enabling `gc()` in JS) and `gc()` was called in the `finally` block after each response. Memory **oscillated** (went up during streaming, then came back down after each GC call) instead of climbing monotonically. This was the only observed mechanism that caused RSS to decrease.

The V8 `gc()` API, when called via `--expose-gc`, triggers a full major collection that includes **both** V8 old-gen and Oilpan. Specifically, `gc({ type: 'major', execution: 'async' })` runs incremental major GC slices during idle periods, which collects detached Oilpan nodes.

**Tradeoff**: Both synchronous `gc()` and `gc({ type: 'major', execution: 'async' })` caused brief gray-frame flicker during testing. The flicker is likely Chromium temporarily suspending the compositor during GC. With a 2.5-second post-response delay (allowing the UI to settle before GC starts), flicker is expected to be minimized.

### Current approach (as of 2026-06-21, updated)

1. `--expose-gc` flag re-added to `qt_wrapper.py` Chromium flags
2. In `chat.js` `finally` block: `setTimeout(() => gc({ type: 'major', execution: 'async' }), 2500)` with `_gcPending` / `_gcMissed` catch-up scheduling (see Session 3 below)
3. Falls back to `requestIdleCallback` no-op if `gc()` is absent (non-QtWebEngine environments)
4. All Session 1 fixes remain in place (they reduce DOM churn, which reduces the volume of detached nodes that GC must collect)

**Not yet verified**: Whether the 2.5s delay + async mode eliminates the gray flicker. Requires a new session after restart with the updated qt_wrapper.py.

---

## Session 3 Findings — 2026-06-21 (GC Scheduling Analysis)

### Diagnosis: `_gcPending` lockout blocks GC in agent sessions

The `_gcPending` guard (originally 5000ms lockout) was designed to prevent stacking concurrent GC cycles. However, in a rapid agent tool-call batch, it prevents GC from firing for any response except the first:

```
T=0s   Response 1 finishes → gc() dispatched → _gcPending = true
T=2s   Response 2 finishes → gc() BLOCKED (_gcPending)
T=4s   Response 3 finishes → gc() BLOCKED
T=6s   Response 4 finishes → gc() BLOCKED
T=5s   _gcPending = false  ← no catch-up; 3 responses' Oilpan garbage stranded
```

A run of 4 tool-call responses accumulates 3×(response Oilpan garbage) with no collection until the next manual response triggers a new 2.5s timer.

### Fix: `_gcMissed` catch-up flag

Branch `perf/agent-gc-catchup` (issue #80) adds:

1. `_gcMissed` flag alongside `_gcPending`. When a response completes while GC is running, `_gcMissed = true` is set and `[GC] blocked — catch-up queued` is logged.
2. When the primary GC cycle completes (`_gcPending = false` reset), if `_gcMissed` is true, one catch-up GC cycle fires immediately and logs `[GC] catch-up dispatched`.
3. Lockout reduced from 5000ms → 3000ms: `gc({ type: 'major', execution: 'async' })` runs incremental slices during idle; 3s is sufficient for a sweep over 50k–200k Oilpan nodes.

**Result**: A burst of N rapid agent responses gets exactly 2 GC cycles (primary + catch-up) rather than 1 (or 0 if the next response arrives within 5s).

### Diagnostic signals (check in wrapper_system.log)

| Log line | Meaning |
|----------|---------|
| `[GC] major async dispatched` | Primary GC fired; Oilpan collection started |
| `[GC] blocked — catch-up queued` | Response completed while GC was running; catch-up scheduled |
| `[GC] catch-up dispatched` | Catch-up cycle fired for the blocked batch |
| `[CDP] nodes=N documents=D listeners=L` | 60s Oilpan snapshot; N should oscillate, not climb monotonically |
| `[GC] CDP purge ok — focus-loss` | Focus-loss CDP purge succeeded |

A healthy session shows nodes go up during streaming and drop after each GC cycle. Monotonically climbing nodes indicate GC is failing to fire or collect.

### Revised understanding of PR #4661

The PR was solving a **real but secondary problem** — reducing unnecessary DOM allocation rate (V8 side). The primary problem in QtWebEngine is Oilpan collection failure. The PR's fixes are still valid and are pre-applied to `develop`, but they are not sufficient on their own for QtWebEngine-embedded use.

The correct long-term fix for upstream would include either:
- Wiring QtWebEngine's memory pressure notifications to Oilpan's coordinator (requires C++ changes to Qt or Chromium embedding code — out of scope for a JS-level PR)
- Making the JS-level `--expose-gc` approach part of the wrapper with documentation explaining why it's necessary for the embedded case

---

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

---

## Session 3 Deep Analysis — 2026-06-21

### All current garbage generation sources (ranked by estimated impact)

The following sources have been identified by code audit of `streamingRenderer.js`, `chat.js`, and `chatHistory.js`. Where possible, the Oilpan pressure type (detached nodes, retained closures, fragmentation) is noted.

#### Source 1 — renderTail() holder div (PRIMARY, unresolved)

**Location**: `streamingRenderer.js:78–108`

Every `renderTail()` call — 30 times per second during streaming — does:
```js
const holder = document.createElement('div');
holder.innerHTML = render(tailText);          // full markdown parse → full DOM subtree
const newNodes = Array.from(holder.childNodes); // array allocation
```

Then, on the fast path (in-place patch): the `holder` and its entire parsed DOM subtree are discarded. On the slow path (structure changed): the old `_tailNodes` are removed (detached) AND a new tree from `holder` is inserted.

**Critical misunderstanding in previous analysis**: The in-place patch avoids removing/re-inserting live tail nodes, but it does NOT avoid creating the shadow DOM tree. Every call to `renderTail()` still creates a full parsed DOM tree inside `holder`, even when fast-path patching succeeds. This shadow tree immediately becomes garbage.

For a 10-second streaming response at 30fps: **300 complete DOM trees created and discarded** in Oilpan. Each tree mirrors the full visible tail — typically 1–5 block elements with text nodes. Multiply by session length.

**This is the highest-volume ongoing Oilpan pressure source currently unaddressed.**

**Fix (not yet implemented)**: Before calling `render(tailText)`, count structural blocks with a fast regex that doesn't build a DOM tree. If the count matches `_tailNodes.length` and node types match, update text content directly using the diff between `lastTailText` and `tailText` — no parsing required.

```js
// Candidate approach: plain-text delta for stable streaming
function _countBlocks(text) {
  // Count top-level block boundaries (paragraph breaks, code fence markers)
  // Returns {count, types[]} without building any DOM
}
// If _countBlocks(tailText).count === _tailNodes.length and types match,
// walk _tailNodes and update only the text nodes using direct .data assignment
// based on the last known text. This skips render() entirely.
```

The difficulty: markdown is not a context-free grammar — a new character can change the meaning of preceding text (e.g., closing a fence, completing a link). The regex approach must be conservative: any ambiguous case falls through to the full render path.

#### Source 2 — Final render double-allocation (AGENT PATH)

**Location**: `chat.js:2725–2750` (agent round finalization)

After `streamingRenderer.finalize()` closes the streaming path (freezing remaining tail into live DOM), the agent path does:
```js
_liveReplyEl.innerHTML = _replyHtml;  // fresh mdToHtml() render of full text
```

This creates an entirely new DOM tree from the final markdown. All the nodes that `streamingRenderer.finalize()` just placed into `_liveReplyEl` become detached at this moment — one complete response worth of DOM nodes, all detached simultaneously. This is the largest single-event Oilpan deposition per response.

**Why this exists**: The streaming path renders incrementally (frozen blocks + live tail) while the final path needs a single clean render that can apply `extractThinkingBlocks()` and sources boxes in the correct positions. The streaming renderer can't position these because it doesn't know the full structure until the stream ends.

**Potential fix**: Call `streamingRenderer.finalize()` with the post-processed `finalDisplay` text rather than re-rendering separately. The streaming renderer already does a `freeze(rest)` on the remaining tail — if we pass the full `finalDisplay` as the text rather than the raw stream text, we get the correct output without a second render. This requires threading `finalDisplay` earlier in the pipeline.

#### Source 3 — Tool output double-render (AGENT PATH)

**Location**: `chat.js:2129` (tool start) and `chat.js:2242` (tool end)

When a tool runs:
1. `node.innerHTML = placeholder_html` — creates DOM for the running state
2. `currentToolBubble.innerHTML = final_html` — replaces with completed state

The placeholder nodes (`.agent-thread-wave`, running state) become detached when the final innerHTML fires. For an agent session with 50 tool calls, this is 50 placeholder subtrees detached and left in Oilpan.

**Fix**: Patch the tool state in-place — update only the changed elements (status indicator, chevron, output content) rather than replacing the entire `innerHTML`. Reduces Oilpan pressure for every tool call.

#### Source 4 — hljs highlighting allocation (EVERY FINALIZATION)

**Location**: `streamingRenderer.js:47–49`, `chat.js:2769–2771`, `chat.js:2080–2081`

After each finalized code block, `hljs.highlightElement(block)` replaces `<code>` text content with a tree of `<span class="hljs-...">` elements. For a 100-line bash output, this produces 200–500 `<span>` elements. The original text node is detached.

More importantly: `highlightElement` is called immediately at finalization time for ALL code blocks in the message, including those that may be off-screen. A message with 10 code blocks allocates 2,000–5,000 span elements at once.

**Fix**: Defer `highlightElement()` until the code block is scrolled into view, using `IntersectionObserver`. Off-screen blocks remain as plain text. When the user scrolls to them, highlight just-in-time. This reduces per-response Oilpan pressure by 50–90% for tool-heavy agent sessions.

Implementation:
```js
// In streamingRenderer.highlight() — replace immediate highlight with deferred
function highlight(root) {
  if (!hljs) return;
  root.querySelectorAll('pre code').forEach((block) => {
    if (!block.dataset.highlighted) {
      _deferHighlight(block);
    }
  });
}

const _highlightObserver = new IntersectionObserver((entries) => {
  entries.forEach((e) => {
    if (e.isIntersecting && !e.target.dataset.highlighted) {
      e.target.dataset.highlighted = '1';
      hljs.highlightElement(e.target);
      _highlightObserver.unobserve(e.target);
    }
  });
}, { rootMargin: '200px' });

function _deferHighlight(block) {
  _highlightObserver.observe(block);
}
```

#### Source 5 — Event listeners on per-response elements (SUSPECTED MINOR)

**Location**: `chat.js` — `contBtn`, `_cont`, variant nav buttons, `closeBtn` (ask-user modal)

Per-response UI buttons get `addEventListener('click', () => { ... })` with closures. When the button's parent message is evicted by Phase 2 (`_evictLive()`), the button is removed from DOM but the listener closure is NOT explicitly removed.

**Assessment**: In modern Chromium, detached nodes with event listeners ARE GC-able if no external code holds a strong reference to the node itself. The listener closure doesn't prevent collection. However, if any closure captures a live object (e.g., `_session`, `_backgroundStreams` Map) without going through a weak reference, that object's reachability chain could prevent collection.

**Verification needed**: A `Runtime.evaluate` CDP call to count listeners on detached nodes would confirm whether this is a genuine leak or not. Until verified, treat as suspected minor contributor.

**Partial mitigation already in place**: `_evictLive()` clears `_waveInterval`, `_elapsedTicker`, and `_streamRenderer` on evicted nodes, which breaks the most obvious retention chains.

#### Source 6 — Round holder innerHTML resets (AGENT MULTI-ROUND)

**Location**: `chat.js:2750`, `chat.js:2757`

For multi-round agent responses, each round's body is reset multiple times during the stream:
- Initial round structure set
- Source box added
- Final round text rendered

Each `innerHTML` reset discards the previous DOM tree. For a 5-round agent session with sources, this is 5×3 = 15 detached subtrees per session.

**Scale**: Small relative to Sources 1 and 2, but compounds over long sessions.

---

### gc() behavior in depth

**Does `gc({ type: 'major', execution: 'async' })` collect Oilpan nodes?**

Yes. Since Chrome 96 (unified heap milestone), V8 and Oilpan share a single GC cycle called "Unified Heap". When a V8 major GC runs, it includes Oilpan's marking phase — DOM nodes, CSS objects, and layout trees are traced and collected alongside V8 heap objects. The `gc()` call via `--expose-gc` triggers this unified cycle.

**Synchronous vs asynchronous execution**:

- `gc({ type: 'major', execution: 'sync' })` — one blocking pause. GC runs to completion before the next JS task. Total pause: 50–500ms depending on heap size. Causes gray frames.
- `gc({ type: 'major', execution: 'async' })` — incremental, runs in slices during idle time between JS tasks. Individual slice: ~1ms. Total GC work is the same, spread over multiple frames. Theoretically no gray frames, but QtWebEngine's event loop integration may still cause compositor hiccups.

**Why we saw gray flicker with async GC**: The gray is likely the Qt compositor repainting the WebView background during a brief stall in the renderer's compositing pipeline, not from the GC slices themselves. The 2.5s post-response delay should push GC past the compositing flush, reducing (but possibly not eliminating) the flicker.

**Measuring GC effectiveness**:
```js
// In the setTimeout callback, sandwich gc() with CDP queries:
// Before gc():  Memory.getDOMCounters() → log node count
// After gc() settles (another setTimeout 3s later): Memory.getDOMCounters() → log node count
// Delta = nodes collected
```

Currently we have no way to confirm how many nodes each gc() call actually collects. This measurement is essential for tuning.

**Optimal gc() call frequency**: Too frequent = wasted CPU on GC overhead. Too infrequent = large accumulation between collections. The current approach (once per response, 2.5s after [DONE]) is a reasonable starting point. If each response takes 10s and produces 5,000 detached nodes, and GC takes 200ms spread across frames, the overhead is ~2% — acceptable.

**Minor GC between renders**: `gc({ type: 'minor', execution: 'sync' })` collects only V8 new-space objects (young generation). Since Oilpan nodes are not in V8 new-space, minor GC does NOT help with our primary problem. Do not add minor GC calls.

---

### Chromium flags for GC and memory tuning

These flags can be added to `QTWEBENGINE_CHROMIUM_FLAGS` in `qt_wrapper.py`. Each has tradeoffs.

#### Currently in use
- `--js-flags=--expose-gc` — enables `gc()` JS API. Required for our primary fix.

#### Worth evaluating

**`--js-flags=--max-old-space-size=N`** (e.g., 512)
Caps V8 old-generation heap at N MB. When V8 old-gen approaches the cap, it triggers major GC more aggressively — including Oilpan (unified heap). This is a backstop that forces GC even if our explicit `gc()` calls are insufficient.

Tradeoff: If Oilpan plus V8 together exceed N MB, GC will thrash (constant major cycles). Set conservatively — 512 MB leaves room for the application's legitimate V8 usage (~100 MB) plus one large response worth of streaming churn.

**`--enable-features=PartitionAllocMemoryReclaimer`**
PartitionAlloc's memory reclaimer periodically decommits free pages back to the OS, reducing RSS even when objects have been logically collected but memory not returned. Has no effect until GC has run and freed Oilpan objects. Reduces the RSS waterline after successful GC.

**`--enable-features=BlinkHeapCompaction`**
Oilpan heap compaction moves live objects to consolidate free pages, reducing fragmentation. Standard GC marks objects as free but doesn't relocate them — fragmentation means 20 small live objects spread across 5 pages prevent those pages from being returned to OS. Compaction solves this.

Tradeoff: Compaction requires relocating pointers (Oilpan uses handles that support relocation). Increases individual GC pause time but reduces long-term RSS. Worth testing — may explain some of the RSS that doesn't drop fully after gc() even when nodes are collected.

**`--disable-features=RendererCodeIntegrity`** (security tradeoff, not recommended)
Disables code signing in the renderer — allows JIT code to be generated more freely. Not memory-related.

**`--renderer-process-limit=1`**
Limits the number of renderer processes. Irrelevant for single-tab use (we only have one renderer), but ensures no additional renderer is spawned for popups.

**`--js-flags=--incremental-marking-wrappers`**
Forces incremental marking for wrapper objects (objects that bridge V8 and Oilpan). May improve collection of cross-heap references. Experimental.

#### Avoid
- `--js-flags=--gc-interval=N` — triggers GC every N allocations. Too aggressive, causes constant GC pauses.
- `--memory-pressure-off` — disables Chromium's memory pressure system entirely. Would make things worse.
- `--disable-background-timer-throttling` — unrelated; affects timer firing rate in background tabs.

---

### New instrumentation to implement

#### Instrument 1 — CDP node count alongside RSS (Python-side)

Add to `qt_wrapper.py`: a background thread that polls CDP's `Memory.getDOMCounters()` every 60s and writes node counts to `wrapper_system.log` alongside the existing RSS log.

```python
import asyncio, json, threading
import websockets

async def _poll_cdp_memory(ws_url):
    async with websockets.connect(ws_url) as ws:
        while True:
            await asyncio.sleep(60)
            await ws.send(json.dumps({"id": 1, "method": "Memory.getDOMCounters"}))
            resp = json.loads(await ws.recv())
            r = resp.get("result", {})
            print(f"[CDP] nodes={r.get('nodes')} documents={r.get('documents')} listeners={r.get('jsEventListeners')}", flush=True)
```

This gives us the node count curve over time, correlated with RSS, so we can see exactly how many nodes each response produces and how many gc() collects.

#### Instrument 2 — GC effectiveness log (JS-side)

In the `setTimeout` callback in `chat.js` that calls `gc()`, add before/after node counts using CDP via the existing debugging port. Since JS can't directly read node counts, instead use `performance.measureUserAgentSpecificMemory()` if available (requires cross-origin isolation), or time the GC via `performance.now()` delta:

```js
setTimeout(function () {
  if (typeof gc === 'function') {
    const t0 = performance.now();
    gc({ type: 'major', execution: 'async' });
    // Async GC doesn't block, so this just measures dispatch time, not completion.
    // Useful only to confirm gc() was called without throwing.
    console.log('[gc] major async dispatched, t=' + t0.toFixed(0) + 'ms');
  }
}, 2500);
```

Full effectiveness measurement requires CDP-side polling (Instrument 1), not JS-side.

#### Instrument 3 — renderTail() call rate and fast-path ratio

Add counters to `streamingRenderer.js`:

```js
let _renderTailCalls = 0;
let _renderTailFastPath = 0;

function renderTail(tailText) {
  _renderTailCalls++;
  // ... existing code ...
  if (/* fast path condition */) {
    _renderTailFastPath++;
    // ...
    return;
  }
  // slow path continues
}

// In finalize():
if (_renderTailCalls > 0) {
  console.log('[streamRenderer] renderTail calls=' + _renderTailCalls +
    ' fast=' + _renderTailFastPath +
    ' (' + ((_renderTailFastPath/_renderTailCalls)*100).toFixed(0) + '%)');
  _renderTailCalls = 0;
  _renderTailFastPath = 0;
}
```

This tells us: for a typical response, what fraction of renders are fast-path vs full-rebuild? If 95% are fast-path, we know the holder-div allocation is the dominant cost. If 50% are full-rebuild, structure changes are also a significant source.

#### Instrument 4 — Heap snapshot diff via CDP

A one-time manual procedure to identify which types of objects make up the detached node count:

```bash
# 1. Start app, send 3–5 messages
# 2. In a Python script:
import asyncio, json, websockets

async def snapshot():
    async with websockets.connect('ws://localhost:9222/json') as ws:
        # Get the page WS URL
        pass

# 3. Use chrome://inspect to take heap snapshot
# 4. Filter by "Detached" in the snapshot viewer
# 5. Look at object types and counts in "Detached DOM tree" group
```

This would confirm whether the 215,000 detached nodes are predominantly:
- Streaming tail nodes (from renderTail())
- Frozen block nodes (from freeze())
- Tool output nodes (from tool bubble replacement)
- hljs span elements (from highlight())

Each has a different fix priority.

#### Instrument 5 — Event listener audit

One-time CDP evaluation to map event listeners on detached nodes:

```bash
# Via CDP Runtime.evaluate:
python3 -c "
import json, asyncio, websockets

async def audit():
    async with websockets.connect('ws://localhost:9222/json') as ws:
        await ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate', 'params': {
            'expression': '''
                (function() {
                    const result = { detachedWithListeners: 0, totalListeners: 0 };
                    // Walk all nodes via TreeWalker on a clone is not possible for detached.
                    // Use getEventListeners() which is a DevTools API.
                    return JSON.stringify(result);
                })()
            ''',
            'returnByValue': True
        }}))
        print(await ws.recv())
asyncio.run(audit())
"
```

Note: `getEventListeners()` is only available in DevTools context, not via `Runtime.evaluate`. The correct approach is to use the DevTools Profiler → Event Listeners tab while attached to the page. Do this manually during a long session.

---

### DOM production reduction — unimplemented opportunities

These are concrete optimizations that reduce how many DOM nodes are created per response. Ranked by estimated impact and implementation difficulty.

#### Opportunity 1 — Deferred hljs highlighting (HIGH IMPACT, MEDIUM EFFORT)

Implement `IntersectionObserver`-based deferred highlighting as described in Source 4 above. For a tool-heavy agent session (50 tool calls, 2 code blocks each = 100 code blocks), this would defer ~90% of hljs span allocation until the user actually scrolls to each block.

**Estimated Oilpan reduction**: 50–90% reduction in hljs-related detached nodes. hljs spans are currently created and immediately become candidates for collection when messages are evicted — deferring creation eliminates them entirely for blocks the user never sees.

**Required changes**: `streamingRenderer.highlight()`, `chat.js` post-finalization highlight calls, `chatHistory.js` (observer cleanup on eviction).

#### Opportunity 2 — In-place tool bubble patching (MEDIUM IMPACT, MEDIUM EFFORT)

Replace the tool start/end `innerHTML` replace with targeted DOM updates:

```js
// Tool start: create structure once, mark elements for later update
node.querySelector('.agent-thread-icon').textContent = toolIcon;
node.querySelector('.agent-thread-tool').textContent = toolLabel;
// leave wave spinner in place

// Tool end: patch only what changed
const header = node.querySelector('.agent-thread-header');
header.querySelector('.agent-thread-icon').textContent = ok ? '✓' : '✗';
header.querySelector('.agent-thread-tool').textContent = json.tool;
// replace wave with status
const wave = header.querySelector('.agent-thread-wave');
if (wave) wave.replaceWith(statusSpan);
// update content directly
node.querySelector('.agent-thread-content').innerHTML = cmdHtml2 + outHtml + diffHtml;
```

Eliminates one complete detached subtree per tool call. For 50 tool calls per session, this is significant.

#### Opportunity 3 — Avoid double final render in agent path (HIGH IMPACT, HIGH EFFORT)

Thread `finalDisplay` through `streamingRenderer.update()` so that `finalize()` produces the fully-processed output directly, eliminating the secondary `_liveReplyEl.innerHTML = _replyHtml` call. The challenge: `finalDisplay` isn't known until `[DONE]` arrives, and thinking block extraction (`extractThinkingBlocks()`) needs the full response. Possible approach: pass a post-processor callback into the renderer that runs on finalize.

#### Opportunity 4 — Render-free fast path for renderTail() (HIGH IMPACT, HIGH EFFORT)

As described in Source 1: a pre-parse block counter that skips `render(tailText)` entirely when structure is stable. Requires careful handling of markdown edge cases (fence completion, link parsing, etc.).

#### Opportunity 5 — content-visibility for code blocks (MEDIUM IMPACT, LOW EFFORT)

Already applied `content-visibility: auto` to `.msg`, `.thinking-content`, `.agent-thread`. Additionally apply it to individual `<pre>` blocks within messages — long code outputs are the largest per-message DOM structures and benefit most from deferred layout.

```css
.msg pre {
  content-visibility: auto;
  contain-intrinsic-size: auto 200px;
}
```

This doesn't reduce node count but reduces Oilpan *layout tree* cost for off-screen code blocks.

---

### GC optimization — if --expose-gc is permanent

Assuming `--expose-gc` remains in `qt_wrapper.py` as a permanent fixture, the following optimizations improve GC effectiveness:

#### Optimization 1 — Verify async GC collects before next message

Currently GC fires 2.5s after `[DONE]`. If the user sends another message before GC completes (incremental slices still running), the next response's DOM churn overlaps with ongoing collection. Consider: check whether a previous gc() is still running before dispatching another. There is no JS API to query GC state, but we can approximate with a flag:

```js
let _gcPending = false;
// In setTimeout callback:
if (!_gcPending && typeof gc === 'function') {
  _gcPending = true;
  gc({ type: 'major', execution: 'async' });
  // Assume incremental GC completes within 5s; reset flag after
  setTimeout(() => { _gcPending = false; }, 5000);
}
```

This prevents stacking multiple concurrent async GC cycles, which would increase total GC overhead.

#### Optimization 2 — gc() when tab loses visibility

QtWebEngine doesn't have a "tab hidden" concept (it's always visible), but Qt's window focus events could be used. When the main window loses focus (user switches to another app), trigger a synchronous major GC — the user won't see the gray frame because the window isn't visible:

```python
# In qt_wrapper.py MainWindow:
def changeEvent(self, event):
    if event.type() == QEvent.Type.WindowDeactivate:
        # Window lost focus — safe to run synchronous GC
        self.web_view.page().runJavaScript(
            "if (typeof gc === 'function') gc({ type: 'major', execution: 'sync' });"
        )
    super().changeEvent(event)
```

This is a zero-flicker path to full major GC.

#### Optimization 3 — Flag combination for autonomous Oilpan GC

Add these flags alongside `--expose-gc` to make Chromium's own GC more aggressive without needing explicit `gc()` calls:

```python
"--js-flags=--expose-gc --max-old-space-size=512",
"--enable-features=PartitionAllocMemoryReclaimer",
"--enable-features=BlinkHeapCompaction",
```

`--max-old-space-size=512` acts as a pressure valve — when V8+Oilpan unified heap exceeds 512 MB, Chromium triggers its own major GC. This backstop means even if our `gc()` call is skipped (e.g., user sends rapid messages), memory can't grow unbounded.

**Risk**: If 512 MB is too low for legitimate use (large responses, many open docs), GC will thrash. Tune based on measured baseline usage.

#### Optimization 4 — Track gc() call in active-work.md logging

Add a `[GC]` log line to `wrapper_system.log` each time `gc()` fires (via Qt's `runJavaScript()` callback mechanism), correlated with the RSS reading that follows. This lets us see whether the RSS reading after a GC call shows a drop, confirming Oilpan actually collected:

```js
// In the gc setTimeout:
setTimeout(function () {
  if (typeof gc === 'function') {
    gc({ type: 'major', execution: 'async' });
    // Post a message that qt_wrapper.py can intercept via QWebChannel or console
    console.log('[GC] major async triggered');
  }
}, 2500);
```

---

## Session 4 Findings — 2026-06-22 (Typing Lag + GC Freeze)

### Problem: typing lag and 1-second lockups

Two distinct performance problems were reported during typing:

**1-second lockups**: Diagnosed as `Memory.forciblyPurgeJavaScriptMemory` via CDP. This
method calls `V8::LowMemoryNotification()` synchronously in the renderer, blocking the JS
event loop for 100 ms–1 s+ during large-heap collections. Three trigger sites:
- PSI monitor every 5 s when `avg10 > 5 %` — no cooldown, could fire every 5 s under
  sustained memory pressure
- `changeEvent(WindowDeactivate)` — fires on every focus shift on KDE/Wayland (tooltip
  popups, notification banners, clicking into a dialog)
- Node-threshold in `_log_renderer_memory` — fires when node count exceeds 50,000

**General jankiness**: `autoResize` in `ui.js` forced 2 DOM layout reflows per keystroke
via a hidden clone (`getComputedStyle` + `offsetWidth` → first reflow; `clone.scrollHeight`
→ second reflow). At 8 chars/sec: 16 forced layouts/sec in QtWebEngine.

### Fix: async JS GC replaces synchronous CDP purge

`gc({ type: 'major', execution: 'async' })` is already available via `--expose-gc` and
covers both V8 and Oilpan (Blink GC). The `async` execution mode runs incremental GC
slices during idle periods without blocking the main thread — eliminating the freeze.

**`qt_wrapper.py` changes** (branch `feat/qt-native-linux-app`, commit `7d288485`):
- Removed `_cdp_purge_memory()` entirely
- Added `_gc_request_pending: list[bool] = [False]` + `_request_async_gc()` for
  cross-thread scheduling (PSI monitor is a daemon thread with no Qt event loop; using a
  module-level flag polled every 250 ms by `_gc_drain_timer` on the main thread is the
  correct pattern)
- Focus-loss: 500 ms single-shot debounce via `_gc_focus_timer` — `WindowActivate`
  within 500 ms cancels the GC (skips transient focus shifts); `WindowDeactivate` restarts
  the timer
- PSI monitor: 30 s cooldown (`_COOLDOWN = 30`) prevents repeated GC bursts under
  sustained pressure
- Node-threshold: direct `page.runJavaScript(...)` call (already on Qt main thread)

**`static/js/ui.js` change** (branch `perf/smooth-typing`, commit `4ba75a26`):
- Replaced clone-based autoResize with `requestAnimationFrame`-coalesced
  `height: 'auto'` + `scrollHeight` measurement
- `textarea._arRafId` guard coalesces all keystrokes in a 16 ms frame to one layout reflow
- Clone (`_resizeClone`, `cloneNode`, `offsetWidth`) removed entirely

### Diagnostic log lines after fix

| Log line | Meaning |
|---|---|
| `[GC] focus-loss — async JS GC` | Window was inactive for 500 ms; async GC queued |
| `[MEM] PSI avg10=X% > 5.0% — queuing async JS GC` | System memory pressure; cooldown respected |
| `[GC] async JS GC — PSI` | Drain timer dispatched the PSI-requested GC |
| `[GC] node-count threshold (N > 50000) — async JS GC` | Node threshold triggered direct GC |

`[GC] CDP purge ok` and `[GC] CDP purge failed` no longer appear.

---

### Open questions (prioritized)

1. **Does `gc({ type: 'major', execution: 'async' })` eliminate the gray flicker at 2.5s delay?** Not yet measured. First observation needed after next restart.

2. **What fraction of renderTail() calls are fast-path?** Determines whether Source 1 is worth addressing with the render-free optimization.

3. **What types of objects make up the 215,000 detached nodes?** CDP heap snapshot would reveal whether hljs spans, streaming tail nodes, or tool bubbles dominate.

4. **Does `--max-old-space-size=512` cause thrashing in normal use?** Baseline V8 heap in a fresh session is ~82 MB; peak during streaming is unknown. Measure before setting a cap.

5. **Does BlinkHeapCompaction reduce post-GC RSS?** If gc() collects nodes but memory doesn't drop much, fragmentation (not live objects) is the problem, and compaction would fix it.

6. **Are event listeners on evicted DOM nodes causing retention?** Manual DevTools listener audit during a long session.

7. **Does the focus-change gc() (Optimization 2) work in QtWebEngine?** `changeEvent(WindowDeactivate)` may not fire as expected in all Qt configurations.

---

## Session 5 Findings — 2026-06-22 (GC Micro-Improvements)

Full audit of the GC stack identified six additional improvements not covered in
previous sessions. All implemented. Test count: 287 → 302 static-analysis.

### Source A: Missing idle GC signal in `_evictLive` and `_pruneBottom`

`_pruneTop` already yields with `requestIdleCallback(() => {}, { timeout: 3000 })`
after detaching subtrees. `_evictLive` and `_pruneBottom` create detached subtrees
but did not call rIC, leaving V8/Oilpan without the scheduler hint.

**Fix:** Added rIC call at the end of `_evictLive` and inside the `if (removed > 0)`
block of `_pruneBottom`.

**Log to watch:** `[chatHistory] Phase 2 evict: removed N live nodes` followed within
a few seconds by V8's incremental GC collecting the detached subtrees (Oilpan node
count drop visible in CDP `Memory.getDOMCounters`).

### Source A+: Timer/renderer teardown gap in `_pruneTop` and `_pruneBottom`

`_evictLive` correctly clears `_waveInterval`, `_elapsedTicker`, and `_streamRenderer`
on every removed element and its descendants before `.remove()`. `_pruneTop` and
`_pruneBottom` only called `hljsDeferForgetNode`, leaving live timers running on
detached nodes and `_streamRenderer` references preventing SR collection.

**Fix:** Added the same teardown loop to all four removal paths in `_pruneTop` and
`_pruneBottom` (main loop + boundary cleanup in each).

**Log to watch:** After `[chatHistory] Phase 2 prune:` or `Phase 3 prune:`, CDP
listener delta should drop by approximately the node count removed.

### Source B: `squashOutsideCode` allocs on every render frame

`squashOutsideCode` was called at ~30 fps during streaming. For plain-text responses
(no code blocks — the common case), it allocated a `split` array and `join` string on
every invocation, discarded immediately after the three regex replacements.

**Fix:** `str.includes('```')` short-circuit returns after normalizing the whole string
directly. No allocation for the common case. Code-fence path unchanged.

**Savings:** For a 120-second plain-text stream at 30 fps, eliminates ~3600 array
allocations and ~3600 string allocations per session.

### Source C: 7 direct `highlightElement` calls bypass IntersectionObserver

`deferHighlightAll` (introduced in `perf/hljs-deferred-highlight`) uses a shared
IntersectionObserver to highlight code blocks only when they scroll into the viewport.
The original migration replaced 1 of 8 call sites. The remaining 7 sites in chat.js
called `window.hljs.highlightElement` directly, highlighting all blocks in a container
synchronously — including off-screen blocks in history loads and completed background
streams.

**Fix:** All 7 remaining sites replaced with `deferHighlightAll(container)`.

**Impact:** hljs.highlightElement allocates hundreds of `<span>` nodes per code block.
For a response with 10 code blocks loaded off-screen, this eliminates ~thousands of
immediate allocations that Oilpan must track and eventually collect.

### Source D: V8 and Chromium flags undertune memory (qt_wrapper.py)

Three V8 flags added to `--js-flags`, two Chromium flags added:

- `--initial-old-space-size=128`: old-gen heap starts at 128 MB (was unset — V8 heuristic
  default varies but typically 256–512 MB on desktop). Reduces baseline RSS for short sessions.
- `--optimize-for-size`: V8 produces smaller JIT code at slight throughput tradeoff.
  For I/O-bound chat workloads where JS is not the bottleneck, ~5–15% JIT footprint reduction.
- `--minor-mc`: Replaces Scavenger with MinorMC for young-gen GC. Compacts on every collection;
  10–20% better retention for DOM-heavy allocation patterns. Overrides `--max-semi-space-size`.
- `--renderer-process-limit=1`: Single renderer process. Saves ~30–50 MB vs default multi-process
  behaviour in some Qt 6.x builds.
- `--disable-extensions`: Removes extension loader overhead (~1–5 MB). No downside for embedded app.

**Log to watch:** `[MEM] VmRSS` at session start should be lower after these flags take effect.
VmRSS at first CDP poll (60 s after launch) is the baseline comparison point.

### Source F: `_purgeStaleBackgroundStreams` called only on chat submit

`_purgeStaleBackgroundStreams()` sweeps `_backgroundStreams` for completed/error
entries and deletes them. Previously called only in `handleChatSubmit` (line 291).
Completed entries accumulated across session switches until the next submit.

**Fix:** Added a call at the top of `checkBackgroundStream`, which fires on every
session switch. One line added, no new API surface.

### Researched but excluded

- **`dataset.raw` → WeakMap:** The `dataset.raw` string is used across 6 files
  (chat.js, chatRenderer.js, group.js, slashCommands.js, composerArrowUpRecall.js).
  A WeakMap would require a shared export module, teardown coordination in chatHistory.js
  (currently uncoordinated with prune), and ~200 LOC for <1% of measured RSS. Not worth it.
- **`--gc-interval=N`:** Not a real V8 user-facing flag. Internal build-time constant only.
- **`--max-semi-space-size`:** Overridden by `--minor-mc` (different memory layout). Excluded.

---

## Session 6 Findings — 2026-06-22 (CSS Animation Raster-Tile Accumulation)

**Trigger:** User reported 14–18 GB RSS while using the Brain panel (mousing over memory
entries). Accompanied by a gray-frame flash on hover. Symptoms were distinct from the
streaming OOM (no active agent session; growth appeared immediately on panel open).

### Root cause: main-thread CSS animations in Qt

The Oilpan/DOM findings above describe garbage from detached DOM nodes (streaming). This
is a separate mechanism: raster tiles produced by CSS animations that require main-thread
painting. The same Qt limitation applies — the renderer receives no OS memory pressure
signals — so the compositor's tile manager never evicts tiles either.

Any animation that triggers per-frame style recalculation or gradient repaint deposits
fresh raster tiles that accumulate for the lifetime of the session, regardless of how
well the Oilpan and V8 GC are tuned.

**Key distinction from Oilpan:** Raster tiles are compositor-managed (cc::TileManager).
They are not Oilpan C++ objects and are not collected by `gc()`. The only remediation is
to eliminate per-frame main-thread painting by switching to compositor-promoted properties
(`transform`, `opacity`).

### Four patterns found (all in static/style.css)

**Pattern A — @property --sweep (memory-synapse-sweep, Brain panel):**

The memory item sweep animation used `@property --sweep { syntax: '<percentage>'; }` to
animate gradient stop positions. Typed registered CSS custom properties participate in
computed-value cascading: every frame `--sweep` changed forced a style recalculation for
every element using `var(--sweep)` in a computed value. At 60 fps with N memories visible,
that is 60 * N style recalculations per second, each producing a raster tile. The
`-webkit-mask` on the same pseudo-element added a second compositor pass per item per frame.

Secondary: hover suppression used `animation: none`, destroying the promoted compositor
layer. It was recreated on mouse-leave, causing the gray-frame flash users reported.

**Pattern B — filter: drop-shadow() in note-ai-shine (Notes panel):**

Every `.note-card-ai-chip svg` element runs `note-ai-shine`. Animating `filter:
drop-shadow()` requires the compositor to reapply the filter every frame as values change,
preventing frame elision. With many note cards visible the per-frame filter work deposits
raster tiles that are never evicted.

**Pattern C — animation: none on hover/focus (notes-quick-add):**

`.notes-quick-add:hover` and `.notes-quick-add:focus-within` set `animation: none`,
destroying the compositor layer promoted for `notes-quick-pulse`. Recreated on mouse-leave
and focus-leave, causing a flash on every interaction.

**Pattern D — background-position animation (notes-drag-shimmer):**

The drag shimmer animated `background-position` across a 250%-wide gradient on every
`.note-card::after` during drag. `background-position` is not compositor-promoted; each
frame re-rasterizes the gradient on every visible card. With 30 cards visible during
drag: 30 gradient repaints per frame.

### Fix

Replace each main-thread animation pattern with compositor-promoted equivalents:

- Patterns A and D: animate `transform: translateX()` instead. The strip starts
  off-screen and sweeps into view. `overflow: hidden` on the parent parks it off-screen
  between cycles without an opacity toggle; the compositor layer stays promoted
  continuously.
- Pattern B: animate `opacity` only. `opacity` is compositor-promoted; the drop-shadow
  at the animation endpoints (0.85 opacity) is effectively invisible anyway.
- Pattern C: use `animation-play-state: paused` instead of `animation: none`. The
  animation freezes at the current keyframe; the compositor layer is not removed.

Note: `will-change: transform` was initially added to `#memory-list .memory-item::after`
but removed in a follow-up commit. A continuously running `transform` animation
auto-promotes the composited layer; `will-change` is redundant for visible items and
forces GPU backing texture allocation for off-screen items in the scrollable list.

### Branch and tests

Branch: `fix/brain-panel-oom` (from `upstream-mirror`)  
Tests: `tests/test_brain_panel_oom_css.py` — 13 regression tests, all 4 patterns  
PR draft: `docs/fork/upstream/pr-drafts/fix-brain-panel-oom.md`

The fixes are also cherry-picked onto `develop`.

---

## Session 7 Findings — 2026-06-22 (Scroll-Hover Raster-Tile Accumulation)

**Trigger:** User reported ~1 GB RSS growth from repeatedly scrolling the mouse up and
down over the Brain memory list. Growth was absent during idle and appeared only during
active scroll-over-items behavior.

### Root cause: transition: all on .memory-item

The base `.memory-item` class carries `transition: all 0.15s`. In the `#memory-list`
scroll context, as the cursor moves over list items during scroll each item cycles through
enter-hover and leave-hover state. The hover rule changes `background` and `border-color`.
Neither property is compositor-promoted; each transition fires at 60 fps for ~9 frames
(0.15 s). Every hover entry/exit cycle per item deposits approximately 9 raster tile
frames. Qt does not forward OS memory pressure to the renderer; these tiles accumulate
without eviction.

This is a separate mechanism from the idle-animation patterns in Session 6. Those were
caused by continuously animating CSS properties. This is caused by the browser producing
raster tiles for paint transitions triggered by scroll interaction. The accumulation is
unbounded because there is no eviction signal and no session-level cap on tile memory.

**Distinction from Session 6:** The Session 6 patterns deposit tiles continuously at
60 fps regardless of user action. The Session 7 pattern deposits tiles only during active
scroll-over behavior, but the rate is proportional to scroll speed and item count. At
high scroll speeds with 20+ items, the tile generation rate can rival idle animation.

### Secondary factor: will-change: transform on all list items

As noted in Session 6: `will-change: transform` on `#memory-list .memory-item::after`
pre-promotes GPU backing textures for every item in the DOM, including those off-screen.
For a scrollable list, this allocates textures for items that never enter the viewport
during a given session. This is fixed memory overhead (not unbounded growth) proportional
to item count, but it compounds the overall memory pressure.

### Fix

Override `transition: all 0.15s` in the `#memory-list .memory-item` context:

```css
#memory-list .memory-item {
  transition: opacity 0.15s;  /* overrides transition: all from base class */
}
```

`opacity` is compositor-promoted and safe to transition without main-thread paint.
`background` and `border-color` changes in this context take effect immediately
(no transition). The animated sweep on `::after` remains the primary hover-interactive
visual, so the loss of background/border transitions is not perceptible.

The `will-change: transform` removal was covered in the Session 6 fix update above.

### Branch and tests

Branch: `fix/memory-list-scroll-oom` (from `upstream-mirror`)  
Tests: `tests/test_memory_list_scroll_oom_css.py` — 4 regression tests  
Issue: jdmanring/odysseus#88  
PR draft: `docs/fork/upstream/pr-drafts/fix-memory-list-scroll-oom.md`

Cherry-picked to `develop` (commit `7e9a2203`). The `will-change` change is a separate
commit on `fix/brain-panel-oom` (commit `18dbbd25`), also cherry-picked to `develop`
(`91082bca`).


---

## Session 8 — Event Listener Accumulation in Brain Memory List (2026-06-22)

**Trigger:** User reported ~956 MiB permanent RSS growth from the Brain memory list that
did not reclaim after closing the Brain panel. The fix from Sessions 6 and 7 (CSS
animation patterns) addressed compositor tile accumulation but left the JavaScript-side
listener accumulation unaddressed.

### Root cause 1: document.addEventListener accumulation (primary leak)

`renderMemoryList()` registered a `document`-level click listener per memory item per
render call. The purpose was to dismiss the item action dropdown when the user clicked
outside it. The listener used the default `{ once: false }`, so it never self-removed.

With 50 items and 10 render passes (from filter changes, CRUD operations, sort changes):

```
50 items × 10 renders = 500 listeners on document
```

Each listener held a closure over a dropdown DOM element (a `<div>` appended to
`document.body`). When `renderMemoryList()` cleared the list via `memoryList.innerHTML = ''`,
the old dropdown elements were detached from the DOM but still referenced by those
closures. In Qt-embedded Chromium, where Oilpan (the Blink C++ garbage collector) never
receives OS memory pressure signals, these closures prevented the old nodes from being
collected. Each render pass compounded the problem.

**Why Qt never triggers collection:** The Chromium renderer relies on the OS to send
memory pressure notifications (`base::MemoryPressureLevel::MEMORY_PRESSURE_LEVEL_CRITICAL`)
to trigger Oilpan major GC cycles. Qt's embedded Chromium does not implement this signal
path. Without it, the GC only runs minor cycles (young-generation) during normal
execution, and major cycles (old-generation, which would collect these detached nodes)
are triggered only at process exit or by explicit `--js-flags=--expose-gc` calls.

### Root cause 2: item-level listener closure retention

Item-level listeners (checkbox change, click/select mode, dblclick/inline-edit,
pointer events for long-press, and 5 dropdown item buttons) were registered on each item
during `renderMemoryList()`. No AbortController or removeEventListener call cleaned
them up before the next render. When `innerHTML = ''` cleared the list, those item DOM
nodes were detached but their listener closures — capturing `memory.id`, `item` refs,
`dropdown` refs, `menuBtn` refs — kept them in Oilpan's reachable graph.

51 addEventListener calls, 0 removeEventListener calls in the file before this fix.

### Root cause 3: animation while panel is hidden

The `::after` sweep animation on `.memory-item` (addressed in Session 6) continued
running when `#memory-modal` received the `.hidden` class. Compositor tile allocations
for the entire hidden list remained active. No JavaScript was needed to pause them — a
CSS selector rule suffices.

### Fix

**AbortController per render pass (root cause 2):**

Module-level state:
```javascript
let _listAbortCtrl = null;
let _activeDropdown = null;

function _closeActiveDropdown() {
  if (_activeDropdown && _activeDropdown.parentNode) _activeDropdown.remove();
  _activeDropdown = null;
}
```

Start of `renderMemoryList()`:
```javascript
if (_listAbortCtrl) _listAbortCtrl.abort();  // release previous pass closures
_closeActiveDropdown();
_listAbortCtrl = new AbortController();
const _sig = _listAbortCtrl.signal;
```

All 14+ item-level `addEventListener` calls updated to carry `{ signal: _sig }`.
When abort fires, every registered listener is removed synchronously — the old-school
equivalent of calling `free()` before the next `malloc()`.

**document listener fix (root cause 1):**

Moved from the `forEach` body to inside the `menuBtn` click handler:

```javascript
menuBtn.addEventListener('click', (e) => {
  // ... build and append dropdown ...
  _activeDropdown = dropdown;
  document.addEventListener('click', () => {
    if (dropdown.parentNode) dropdown.remove();
    _activeDropdown = null;
  }, { once: true, signal: _sig });  // two removal paths: click and abort
}, { signal: _sig });
```

This changes the registration model from "N listeners per render call" to "1 listener
per open dropdown," and gives each listener two removal paths: the user's next click
(`once: true`) and the next render's abort (`signal: _sig`).

**CSS animation pause (root cause 3):**

```css
#memory-modal.hidden #memory-list .memory-item::after {
  animation-play-state: paused;
}
```

Halts compositor tile work when the panel is not visible. No JavaScript required.

**Panel close cleanup:**

A MutationObserver on `#memory-modal` observes `attributeFilter: ['class']`. On
`.hidden`, it calls `_closeActiveDropdown()` (defensive cleanup) and `gc()` (if exposed).

Important: the observer does NOT abort `_listAbortCtrl` on close. The abort belongs
at the start of `renderMemoryList()` (immediately before `innerHTML = ''`), not at
panel close. Aborting on close without a corresponding `odysseus:modal-opened` listener
in `memory.js` would leave DOM items with dead event handlers until the next
`memory-refresh` event fired — a UI regression where buttons appear but don't work.

**odysseus:modal-closed event (modalManager.js):**

Added `_emitModalClosed()` mirroring the existing `_emitModalOpened()`. Fired in the
existing MutationObserver when the visibility transition goes from true to false.

### Design notes

The AbortController pattern is the modern equivalent of the old-school "cancel all
outstanding work before starting a new allocation cycle" discipline. Before ES2022
`AbortSignal`, the standard idiom was to maintain a list of listeners and call
`removeEventListener` on each before re-rendering. AbortController consolidates this
into a single `abort()` call that releases every registered listener simultaneously.

The `once: true` pattern for the document click listener is superior to `{ once: false }`
with a manual `removeEventListener`, because it eliminates the need to retain a reference
to the handler function — which itself creates a closure.

### Branch and tests

Branch: `fix/memory-panel-listener-leak` (from `upstream-mirror`)  
Commits: `d89d93a6` (primary fix), `ab8a5f21` (abort-on-close correctness)  
Tests: `tests/test_memory_panel_listener_leak.py` — 14 regression tests  
Issue: jdmanring/odysseus#89  
PR draft: `docs/fork/upstream/pr-drafts/fix-memory-panel-listener-leak.md`

Cherry-picked to `develop`: `fd646bce` (primary), `ac70b23f` (abort-on-close fix).

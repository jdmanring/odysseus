# Upstream Issue Draft: perf-rewrite-streaming-renderer

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/perf-rewrite-streaming-renderer.md`
**Branch:** `perf/rewrite-streaming-renderer`
**Type:** Performance

---

## Title

`[Performance] rewriteWith() does full markdown parse + innerHTML on every SSE token — O(n²) total work`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Problem:**

`rewriteWith()` in `chat.js` streams a rewritten response token-by-token. On every SSE `delta` token it executes:

```javascript
bodyEl.innerHTML = markdownModule.processWithThinking(
  markdownModule.squashOutsideCode(newText)
);
```

This is an O(n²) pattern: each of N tokens triggers a full markdown parse (O(n) in token length), DOMPurify sanitization, and complete DOM reconstruction of the entire accumulated text. For a 200-token rewrite, this is 200 complete parse+sanitize+build cycles, with each cycle operating on progressively longer input. The `[DONE]` handler then assigns `bodyEl.innerHTML` a second time, discarding the entire streaming-built tree immediately after construction.

The main chat streaming path was fixed to use incremental `streamingRenderer.renderTail()` instead of per-token `innerHTML`. The rewrite path was overlooked.

**Impact:**

Heap allocation during a 200-token rewrite grows as O(n²): the first token builds a 1-node tree, the second builds a 2-node tree discarding the first, ..., the 200th builds a 200-node tree discarding the 199th. Total allocation is proportional to n²/2. For a 500-token rewrite in a long session, this is a significant allocation spike that the GC may not fully reclaim before the next response.

**Steps to observe:**

1. Trigger a rewrite response (depends on how rewrite mode is activated in your setup).
2. Open DevTools → Memory → Record allocation timeline during the rewrite.
3. Observe: `bodyEl.innerHTML` allocation creates and immediately discards a DOM tree on each token, visible as a sawtooth pattern in the allocation timeline.

**Proposed fix:**

Lazy-initialize a `createStreamRenderer` on the first delta token and call `.update(newText)` per token — identical to the main streaming path pattern. After the SSE loop completes, finalize the renderer and perform a single final `bodyEl.innerHTML` render with the stripped text (thinking blocks removed by `_stripThink`). Total allocation changes from O(n²) to O(n).

**Affected file:** `static/js/chat.js` — `rewriteWith()` function's SSE delta handler

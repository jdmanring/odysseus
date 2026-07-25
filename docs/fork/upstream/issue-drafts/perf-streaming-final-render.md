# Upstream Issue Draft: perf-streaming-final-render

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** *(no dedicated PR draft, see perf series)*
**Branch:** `perf/streaming-final-render`
**Type:** Performance

---

## Title

`[Performance] streamingRenderer.finalize() re-renders plain-text responses via innerHTML, discarding the streamed DOM tree`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Problem:**

`streamingRenderer.finalize()` (or the equivalent `_unwrapTail` + `innerHTML` path in `chat.js`) re-renders the final response content via `bodyEl.innerHTML = mdToHtml(finalText)` even for plain-text responses where the streaming-built DOM is already the correct final output.

For a response with no code blocks, no tables, and no special markdown structure, the streaming path (via `renderTail()` incremental updates) has already built the correct DOM. The final `innerHTML = mdToHtml()` call:
1. Re-parses the entire response text (full O(n) markdown parse)
2. Discards all the incrementally-built nodes (detached into Oilpan)
3. Creates an identical new DOM subtree from the parse output

This is a full response's worth of Oilpan garbage on every plain-text response completion, even though the existing DOM already represents the correct output.

**Impact:**

For a 100-message session of plain-text responses, the finalize path alone creates 100 full response DOM trees as garbage. Combined with the streaming allocation, this means every response is effectively allocated twice: once incrementally via `renderTail()`, and once via the final `innerHTML`.

**Proposed fix:**

Add a fast path in the finalize sequence: if the final text is plain prose (no markdown structural characters requiring a fresh full render), skip the `innerHTML` replacement and unwrap the streaming DOM in-place (remove the tail marker, freeze the tail nodes). This detects the common case where no additional cleanup is needed and avoids the full discard+rebuild.

For responses with code blocks, the existing `innerHTML` path runs unchanged (code blocks need hljs re-processing, which the in-place path cannot handle).

**Affected file:** `static/js/streamingRenderer.js` or `static/js/chat.js`, finalize/unwrap path after stream completion

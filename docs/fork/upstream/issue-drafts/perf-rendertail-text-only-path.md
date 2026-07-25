# Upstream Issue Draft: perf-rendertail-text-only-path

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/perf-rendertail-text-only-path.md`
**Branch:** `perf/rendertail-text-only-path`
**Type:** Performance

---

## Title

`[Performance] renderTail() creates a holder div on every SSE token, even for plain-text appends`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Problem:**

`renderTail(tailText)` in `static/js/streamingRenderer.js` is called once per SSE token during streaming, 20-60 times per second. Every call runs:

```javascript
const holder = document.createElement('div');
holder.innerHTML = render(tailText);
```

This parses the full accumulated tail markdown and builds a complete DOM subtree in Blink's Oilpan heap on every token, including for the common case of a plain-text word append: a case where no markdown structure changed, no code fence opened or closed, and the existing live text node could be extended with a single `appendData()` call instead.

At 30 fps over a 10-second plain-text response, this is ~300 holder divs deposited into Oilpan as garbage before the GC can collect them. Since Oilpan's cooperative GC runs during idle, and streaming is never idle, these accumulate across the full streaming duration. The `_rtCalls` counter (issue #68) confirms this: fast-path hit rate for plain prose is 0% before this fix.

**Impact:**

The holder allocation is the largest single source of allocation pressure during normal (non-thinking) streaming. For a 10K token plain-text response, `renderTail()` creates ~10,000 discarded holder divs. Combined with the multi-round finalize rebuild (issue #77) and the rewrite path (issue #79), this compounds significantly in long agent sessions.

**Proposed fix:**

Add a text-only append fast path that fires before the holder is created. The path tracks `_lastTailText`, the tail content from the last successful call. On each call, if the new text is a pure suffix of `_lastTailText` with no markdown structural characters, extend the existing live tail text node via `appendData(suffix)` instead of rebuilding. The structural-character regex (`/[!\[*_\`#\[\]<>\n\\{]/`) ensures any markdown-relevant token falls through to the existing full-render paths. This path is estimated to apply to 60-80% of tokens in prose-heavy responses.

**Affected file:** `static/js/streamingRenderer.js`, `renderTail()` function

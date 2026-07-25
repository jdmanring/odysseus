# Upstream Issue Draft: perf-gc-rendertail-instrumentation

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** *(no dedicated PR draft; instrumentation-only change)*
**Branch:** `perf/gc-rendertail-instrumentation`
**Type:** Performance / Observability

---

## Title

`[Performance] Add renderTail() call counters to measure holder-div allocation pressure`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Problem:**

`renderTail(tailText)` in `streamingRenderer.js` is called once per SSE token during streaming. Each call that does not hit the text-only fast path creates a holder `div` and calls `innerHTML = render(tailText)`. In a long streaming session, the rate at which `renderTail` allocates holder divs is the primary driver of Oilpan node accumulation, but there is no way to measure this rate without adding instrumentation.

Without counters, it is impossible to verify:
- Whether the text-only fast path (issue #75) is firing as expected for prose responses
- What percentage of tokens require a full holder allocation vs. the fast path
- Whether a specific response type (code-heavy vs. prose) is more allocation-intensive

**Proposed fix:**

Add two counters to `streamingRenderer.js`:

- `_rtCalls`: incremented on every `renderTail()` invocation
- `_rtFast`: incremented when the fast path fires (text-only append or in-place node patch, where no holder div is created)

At `finalize()`, log the combined rate:

```javascript
console.log(`[streamRenderer] renderTail calls=${_rtCalls} fast=${_rtFast} (${Math.round(_rtFast*100/_rtCalls)}%)`);
```

This log line is routed through `javaScriptConsoleMessage` in the Qt wrapper into `wrapper_system.log`, making it available in production sessions without DevTools. The percentage tells you immediately whether a given session benefited from the fast path or hit the full allocation path for most tokens.

**Note:** This is instrumentation-only, no behavior change. The counters are local to the `createStreamRenderer` closure and reset to zero at `start()`. No global state is modified.

**Affected file:** `static/js/streamingRenderer.js`: `renderTail()`, `finalize()`

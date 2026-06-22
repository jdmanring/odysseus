# PR Draft: perf(chat): improve GC scheduling for agent sessions

**Branch**: `perf/agent-gc-catchup`
**Issue**: jdmanring/odysseus#80
**Base**: upstream-mirror (clean, no fork-specific history)

---

## Problem

In embedded Chromium environments (QtWebEngine, Electron, native wrappers), Oilpan's
automatic GC is not triggered by OS memory pressure because the embedder is not wired
into Blink's memory coordinator. The `--expose-gc` flag + `gc({ type: 'major', execution:
'async' })` call in the `finally` block is the only mechanism that causes detached DOM
nodes to be collected between responses.

However, the `_gcPending` lockout (originally 5000ms) creates a blind spot during
rapid agent tool-call sequences. When 4 tool responses arrive in quick succession:

```
T=0s   Response 1 → gc() dispatched → _gcPending = true
T=2s   Response 2 → gc() BLOCKED
T=4s   Response 3 → gc() BLOCKED
T=6s   Response 4 → gc() BLOCKED
T=5s   _gcPending = false  ← no catch-up fires; 3 responses' Oilpan garbage stranded
```

Memory grows monotonically during agent sessions even though `gc()` fires after each
batch — only one collection happens instead of one per response.

## Solution

### `_gcMissed` catch-up flag (chat.js)

Add `_gcMissed` alongside `_gcPending`. When a response completes while GC is running:
- `_gcMissed = true` is set
- `[GC] blocked — catch-up queued` is logged (visible in wrapper_system.log via
  `javaScriptConsoleMessage` in the Qt wrapper)

When the primary cycle completes:
- If `_gcMissed` is set, immediately dispatch one catch-up GC cycle
- Log `[GC] catch-up dispatched`
- The catch-up uses its own 3000ms reset to prevent stacking

**Effect**: A burst of N rapid responses gets 2 GC cycles (primary + catch-up) instead of
1, without creating a cascade. The catch-up is guaranteed to collect the garbage from all
responses that arrived while the primary cycle ran.

### Lockout reduction 5000ms → 3000ms

`gc({ type: 'major', execution: 'async' })` runs incremental slices during idle periods
and does not block the renderer thread. A 3s window is sufficient for a full sweep over
50k–200k Oilpan nodes (typical long-session node count). The shorter window reduces the
window in which agent responses go uncollected from 5s to 3s.

## Files changed

- `static/js/chat.js` — `_gcMissed` declaration, updated GC block with catch-up logic
- `tests/test_chat_gc_hint_js.py` — 14 static-analysis tests (NEW FILE)

## Test coverage

14 source-text contract tests in `tests/test_chat_gc_hint_js.py`:
- Guard variable declarations (`_gcPending`, `_gcMissed`)
- Primary GC block: feature detection, ordering guards, delay, fallback
- Catch-up mechanism: blocked-path flag set, log line, catch-up dispatch, ordering guard

## Embedding context

This change is most impactful for embedded Chromium (Qt, Electron) where OS memory
pressure signals are not wired to Oilpan. In regular Chrome tabs, Blink's memory
coordinator handles collection automatically. The `typeof gc === 'function'` guard and
`requestIdleCallback` fallback ensure no-op behavior in standard browser environments.

## Related branches

- `fix/qtwebengine-oilpan-gc` (#67, #69) — introduced the initial `_gcPending` guard and
  `--expose-gc` flag; this branch improves the catch-up behaviour
- `perf/gc-rendertail-instrumentation` (#68) — adds `_rtCalls`/`_rtFast` counters to
  measure holder-div allocation pressure per SSE token
- `perf/rendertail-text-only-path` (#75) — skips holder-div creation for plain-prose
  tokens; directly reduces the Oilpan node volume that GC must collect

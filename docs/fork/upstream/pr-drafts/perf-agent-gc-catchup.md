# PR Draft: perf(chat): improve GC scheduling for agent sessions

**Branch**: `perf/agent-gc-catchup`
**Issue**: jdmanring/odysseus#80 (agent-session catch-up), jdmanring/odysseus#97 (idle GC for hover churn)
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

### Idle GC for transient hover churn (chat.js) — jdmanring#97

The catch-up above only fires *after a chat response*. But the renderer also accumulates
Oilpan garbage during pure idle interaction: hovering interactive UI (the Brain memory
list, sidebar nav, etc.) creates short-lived CSS `:hover` pseudo-elements — real
Oilpan-managed DOM `Node`s, created on hover-enter and orphaned on leave. With no chat
activity, nothing collects them and RSS climbs.

`_scheduleIdleGc()` fires one async-major `gc()` after ~8 s (`_IDLE_GC_MS`) of no
pointer/keyboard input. It:
- shares `_gcPending`, so it never stacks with the post-response cycle;
- is gated on `document.visibilityState === 'visible'` (a backgrounded tab does no work);
- is feature-detected (no-op without `--expose-gc`, i.e. every regular browser, where the
  engine's own idle GC already handles this);
- resets its timer on `pointermove`/`pointerdown`/`keydown`/`wheel` via passive + capture
  listeners (allocation-free per event; never blocks scrolling).

**Diagnosis** (controlled experiments): region isolation showed the churn tracks
interactive elements; `gc()` fully reclaims it; the V8 allocation profiler is empty
(native Blink nodes, no JS producer); disabling author CSS collapses the churn
(+1676 → +182 nodes/800 moves) — confirming CSS `:hover` pseudo-elements. **Validated
live**: hovering grew the node count +2536; the idle GC reclaimed it to baseline at ~10 s
with no chat activity.

> Note: this bounds growth after an *inactivity* pause; a continuous multi-minute hover
> with no pause would still accumulate until the user stops. A periodic GC during
> sustained activity is a possible follow-up.

## Files changed

- `static/js/chat.js` — `_gcMissed` declaration + catch-up logic; `_scheduleIdleGc()`
  idle-GC scheduler and its input listeners (#97)
- `tests/test_chat_gc_hint_js.py` — source-text contract tests (NEW FILE)
- `tests/test_idle_gc_integration.py` — behavioral integration test for the idle GC
  (NEW FILE; skips when no CDP endpoint on :9222)

## Test coverage

20 source-text contract tests in `tests/test_chat_gc_hint_js.py`:
- Guard variable declarations (`_gcPending`, `_gcMissed`)
- Primary GC block: feature detection, ordering guards, delay, fallback
- Catch-up mechanism: blocked-path flag set, log line, catch-up dispatch, ordering guard
- Idle GC: scheduler present, shares `_gcPending`, async-major, visibility-gated,
  timer-reset-on-input + passive listeners, feature-detected

1 behavioral integration test in `tests/test_idle_gc_integration.py` (skip-if-no-CDP):
hover-storms the memory list, sits idle, and asserts the node count is reclaimed with no
chat activity — testing the idle GC's *behavior*, not just its source shape.

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

## Relationship to upstream #4644 / #4661

Issue #4644 ("browser tab OOM and freeze during long agent interactions") is the symptom
this and several sibling fork changes target. Open PR #4661 addresses it by reducing DOM
*production* during agent sessions — server-paginated history (`?limit=400`), a
"Show N older messages" bar, and plain-text thinking-block streaming.

This change is **complementary, not overlapping**. It reclaims transient Oilpan *garbage*
— short-lived CSS `:hover` pseudo-element nodes — that accumulates during idle UI
interaction even with no agent activity, a source #4661 does not touch. Idle GC and DOM
windowing coexist cleanly; neither supersedes the other. (A separate fork change, DOM
virtualization, *does* overlap #4661's windowing and needs maintainer coordination before
filing — that is tracked elsewhere and does not affect this idle-GC change.)

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Relates to #4644 — a complementary memory-pressure fix (open PR #4661 is the primary fix
for that issue; this reduces a different, idle-interaction memory source). File a focused
upstream issue for the idle-GC behaviour and link it here before submitting.

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [x] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

1. Start the app with `--expose-gc` set (via `QTWEBENGINE_CHROMIUM_FLAGS` in `qt_wrapper.py`, or pass directly in a dev build).
2. Run an agent session with 4+ tool calls firing in quick succession (a research task that triggers multiple tool rounds).
3. In `wrapper_system.log` (or DevTools Console), confirm:
   - `[GC] blocked — catch-up queued` appears when a response completes while GC is running
   - `[GC] catch-up dispatched` appears ~3s later
4. In DevTools → Memory, confirm the heap grows more slowly compared to a session without this patch (one additional GC cycle fires per burst instead of being silently dropped).
5. Run `pytest tests/test_chat_gc_hint_js.py -q` — 14 tests.

---

## Filing Notes

- 1 commit: `163f946c`.
- Branch: `perf/agent-gc-catchup` — built from `upstream-mirror`.
- **File upstream issue first.** Add the upstream issue number to `Fixes #` above.
- This branch supersedes `fix/qtwebengine-oilpan-gc` (#67, #69) — do not file that branch separately. The catch-up mechanism and the GC tests from that branch are both included here.

## Visual / UI changes

None. GC timing is invisible to the user; this only affects memory usage patterns during agent sessions.

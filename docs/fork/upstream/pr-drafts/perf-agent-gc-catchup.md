# PR Draft: perf(chat): improve GC scheduling (agent-session catch-up and idle reclaim)

**Branch**: `perf/agent-gc-catchup`
**Issue**: jdmanring/odysseus#80 (agent-session catch-up), jdmanring/odysseus#97 (idle GC for hover churn)
**Base**: upstream-mirror (clean, no fork-specific history)

---

## Problem

In embedded Chromium environments (QtWebEngine, Electron, native wrappers), Oilpan's
automatic GC is not triggered by OS memory pressure, because the embedder is not wired
into Blink's memory coordinator. The `--expose-gc` flag plus the
`gc({ type: 'major', execution: 'async' })` call in the `finally` block is the only
mechanism that collects detached DOM nodes between responses.

The `_gcPending` lockout (originally 5000ms) creates a blind spot during rapid agent
tool-call sequences. When four tool responses arrive in quick succession:

```
T=0s   Response 1 → gc() dispatched → _gcPending = true
T=2s   Response 2 → gc() BLOCKED
T=4s   Response 3 → gc() BLOCKED
T=6s   Response 4 → gc() BLOCKED
T=5s   _gcPending = false  ← no catch-up fires; 3 responses' Oilpan garbage stranded
```

Memory grows monotonically during agent sessions even though `gc()` fires after each
batch, because only one collection happens instead of one per response.

## Solution

### `_gcMissed` catch-up flag (chat.js)

Add `_gcMissed` alongside `_gcPending`. When a response completes while GC is running,
`_gcMissed` is set to `true` and the event is logged (visible in `wrapper_system.log`
via `javaScriptConsoleMessage` in the Qt wrapper). When the primary cycle completes, if
`_gcMissed` is set, one catch-up GC cycle is dispatched and logged. The catch-up uses its
own 3000ms reset to prevent stacking.

Effect: a burst of N rapid responses gets two GC cycles (primary plus catch-up) instead
of one, without creating a cascade. The catch-up collects the garbage from all responses
that arrived while the primary cycle ran.

### Lockout reduction 5000ms to 3000ms

`gc({ type: 'major', execution: 'async' })` runs incremental slices during idle periods
and does not block the renderer thread. A 3s window is sufficient for a full sweep over
the 50k to 200k Oilpan nodes typical of a long session. The shorter window narrows the
interval in which agent responses go uncollected from 5s to 3s.

### Idle GC for transient hover churn (chat.js, jdmanring#97)

The catch-up above only fires after a chat response. The renderer also accumulates Oilpan
garbage during pure idle interaction: hovering interactive UI (the Brain memory list,
sidebar nav) creates short-lived CSS `:hover` pseudo-elements. These are real
Oilpan-managed DOM `Node`s, created on hover-enter and orphaned on leave. With no chat
activity, nothing collects them and RSS climbs.

`_scheduleIdleGc()` fires one async-major `gc()` after roughly 8s (`_IDLE_GC_MS`) of no
pointer or keyboard input. It:

- shares `_gcPending`, so it never stacks with the post-response cycle;
- is gated on `document.visibilityState === 'visible'`, so a backgrounded tab does no work;
- is feature-detected, so it is a no-op without `--expose-gc` (every regular browser,
  where the engine's own idle GC already handles this);
- resets its timer on `pointermove`, `pointerdown`, `keydown`, and `wheel` via passive
  capture-phase listeners (allocation-free per event; never blocks scrolling).

Diagnosis (controlled experiments): region isolation showed the churn tracks interactive
elements; `gc()` fully reclaims it; the V8 allocation profiler is empty (native Blink
nodes, no JS producer); disabling author CSS collapses the churn from +1676 to +182 nodes
per 800 moves, confirming CSS `:hover` pseudo-elements as the source. Validated live in
QtWebEngine (Chromium 140): hovering grew the node count by +2536, and the idle GC
reclaimed it to baseline within about 10s with no chat activity.

Scope note: this bounds growth after an inactivity pause. A continuous multi-minute hover
with no pause still accumulates until the user stops; a periodic GC during sustained
activity is a possible follow-up.

## Files changed

- `static/js/chat.js`: `_gcMissed` declaration and catch-up logic; `_scheduleIdleGc()`
  idle-GC scheduler and its input listeners (#97).
- `tests/test_chat_gc_hint_js.py`: source-text contract tests (new file).
- `tests/test_idle_gc_integration.py`: behavioral integration test for the idle GC (new
  file; skips when no CDP endpoint is on :9222).

## Test coverage

20 source-text contract tests in `tests/test_chat_gc_hint_js.py`:

- Guard variable declarations (`_gcPending`, `_gcMissed`).
- Primary GC block: feature detection, ordering guards, delay, fallback.
- Catch-up mechanism: blocked-path flag set, log line, catch-up dispatch, ordering guard.
- Idle GC: scheduler present, shares `_gcPending`, async-major, visibility-gated,
  timer reset on input, passive listeners, feature-detected.

1 behavioral integration test in `tests/test_idle_gc_integration.py` (skips without a CDP
endpoint): hover-storms the memory list, sits idle, and asserts the node count is
reclaimed with no chat activity. This tests the idle GC's behavior, not just its source
shape.

## Embedding context

This change matters most for embedded Chromium (Qt, Electron), where OS memory-pressure
signals are not wired to Oilpan. In regular Chrome tabs, Blink's memory coordinator
handles collection automatically. The `typeof gc === 'function'` guard and the
`requestIdleCallback` fallback keep behavior a no-op in standard browser environments.

## Related branches

- `fix/qtwebengine-oilpan-gc` (#67, #69): introduced the initial `_gcPending` guard and
  the `--expose-gc` flag. This branch improves the catch-up behavior and supersedes it.
- `perf/gc-rendertail-instrumentation` (#68): adds `_rtCalls`/`_rtFast` counters that
  measure holder-div allocation pressure per SSE token.
- `perf/rendertail-text-only-path` (#75): skips holder-div creation for plain-prose
  tokens, reducing the Oilpan node volume that GC must collect.

## Relationship to upstream #4644 / #4661

Issue #4644 ("browser tab OOM and freeze during long agent interactions") is the symptom
this and several sibling fork changes target. Open PR #4661 addresses it by reducing DOM
production during agent sessions: server-paginated history (`?limit=400`), a
"Show N older messages" bar, and plain-text thinking-block streaming.

This change is complementary, not overlapping. It reclaims transient Oilpan garbage
(short-lived CSS `:hover` pseudo-element nodes) that accumulates during idle UI
interaction even with no agent activity, a source #4661 does not touch. Idle GC and DOM
windowing coexist cleanly; neither supersedes the other. A separate fork change, DOM
virtualization, does overlap #4661's windowing and needs maintainer coordination before
filing; that is tracked separately and does not affect this idle-GC change.

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Relates to #4644. This is a complementary memory-pressure fix; open PR #4661 is the
primary fix for that issue, and this reduces a different, idle-interaction memory source.
File a focused upstream issue for the idle-GC behavior and link it here before submitting.

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [x] Refactor / cleanup (behavior unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls); this is not a duplicate. Related: #4644, #4661 (see above).
- [x] This PR targets `dev`.
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes are mixed in.
- [ ] I reviewed and tested this change personally before submitting.

### How to Test

1. Start the app with `--expose-gc` set (via `QTWEBENGINE_CHROMIUM_FLAGS` in
   `qt_wrapper.py`, or pass it directly in a dev build).
2. Run an agent session with four or more tool calls firing in quick succession (a
   research task that triggers multiple tool rounds).
3. In `wrapper_system.log` or the DevTools console, confirm that the blocked-and-queued
   log line appears when a response completes while GC is running, and that the catch-up
   dispatch line appears about 3s later.
4. In the DevTools Memory panel, confirm the heap grows more slowly than in a session
   without this patch (one additional GC cycle fires per burst instead of being dropped).
5. Run `pytest tests/test_chat_gc_hint_js.py -q` (20 tests). With the app running and CDP
   on :9222, `pytest tests/test_idle_gc_integration.py -q` exercises the idle reclaim.

---

## Filing Notes

- 4 commits on `perf/agent-gc-catchup`: `163f946c`, `35144b93`, `5f4c3347`, `8f414836`.
- Branch built from `upstream-mirror`.
- File the upstream issue first, then link it under "Linked Issue" above.
- This branch supersedes `fix/qtwebengine-oilpan-gc` (#67, #69); do not file that branch
  separately. Its catch-up mechanism and GC tests are both included here.

## Visual / UI changes

None. GC timing is invisible to the user. This affects only memory-usage patterns during
agent sessions and idle interaction.
